import logging

from app.domain.telegram.ports import TelegramLinkRepository, TelegramMessenger
from app.infrastructure.agents.scenario import ScenarioSimulationRunner
from app.infrastructure.telegram.format_scenario_result_reply import format_scenario_result_reply
from app.infrastructure.telegram.resolve_linked_user_id import resolve_linked_user_id
from app.infrastructure.telegram.simulate_command import SimulateCommand
from app.infrastructure.telegram.unlinked_account_message import UNLINKED_ACCOUNT_MESSAGE

logger = logging.getLogger(__name__)

_ACK_MESSAGE = (
    "Got it — running your scenario simulation. This involves several data lookups and "
    "model calls, so it can take up to a minute. I'll send the result here when it's ready."
)
_FAILURE_MESSAGE = (
    "Sorry, that scenario simulation failed to complete. Try rephrasing it, or run it "
    "from the Scenario Lab in the TAWS app."
)


class SimulateCommandHandler:
    """Handles `/simular <text>` (issue #19): a fast, synchronous acknowledgement
    (`send_acknowledgement`) plus a separate, slow follow-up delivery
    (`deliver_result`) that runs the FULL Scenario Simulation graph (issue #12's
    `ScenarioSimulationRunner`, reused as-is — same compiled graph
    `POST /api/v1/scenarios/generate` and the `run_scenario_simulation` chat tool use)
    and sends its condensed result as a second, independent `sendMessage` call.

    ## Why ack-then-follow-up, not a blocking webhook response

    The Scenario Simulation graph is a genuinely slow, multi-step pipeline — Intake ->
    Context gathering -> Causal chain -> Quantification -> Synthesis -> Compliance,
    several LLM calls and external data fetches per issue #12's own review notes.
    Blocking the webhook's HTTP response on the full run risks exceeding Telegram's
    expectation of a prompt ack (Telegram may retry-send the same update if it doesn't
    see a timely response, which — combined with this graph's real, non-idempotent
    side effects, e.g. `ScenarioRepository.create`, unlike `/start`'s idempotent
    `consume()` — could trigger a duplicate run). So the router
    (`api/v1/routers/telegram.py`) calls `send_acknowledgement` synchronously (fast:
    one Telegram API call, no graph execution) BEFORE returning its own 200, then
    schedules `deliver_result` as a FastAPI `BackgroundTasks` callback that runs AFTER
    the response is already sent — mirroring how a real Telegram bot handles slow
    commands (ack immediately, deliver the real result via a follow-up message once
    ready) instead of holding the connection open.

    `BackgroundTasks` itself is a `fastapi` type and must stay in `api/`
    (`telegram.py`) per this repo's hexagonal rule — this class only exposes the two
    plain async methods the router schedules/awaits; it never imports `fastapi`.

    Same "infrastructure, not application" placement rationale as
    `BriefingCommandHandler` — see its docstring.
    """

    def __init__(
        self,
        link_repository: TelegramLinkRepository,
        scenario_simulation_runner: ScenarioSimulationRunner,
        messenger: TelegramMessenger,
        frontend_base_url: str,
    ) -> None:
        self._link_repository = link_repository
        self._scenario_simulation_runner = scenario_simulation_runner
        self._messenger = messenger
        self._frontend_base_url = frontend_base_url

    async def send_acknowledgement(self, command: SimulateCommand) -> bool:
        """Fast, synchronous path — awaited by the router BEFORE it responds to
        Telegram. Returns `True` if the command passed the linked-account check and an
        ack was sent (the caller should then schedule `deliver_result` as a background
        task); `False` if it was rejected here (unlinked chat) and nothing further
        should run.
        """
        user_id = await resolve_linked_user_id(self._link_repository, command.chat_id)
        if user_id is None:
            await self._messenger.send_text(command.chat_id, UNLINKED_ACCOUNT_MESSAGE)
            return False
        await self._messenger.send_text(command.chat_id, _ACK_MESSAGE)
        return True

    async def deliver_result(self, command: SimulateCommand) -> None:
        """Slow path — runs the full Scenario Simulation graph and delivers a condensed
        result as a follow-up message. Meant to run as a `BackgroundTasks` callback,
        strictly AFTER the webhook has already responded to Telegram — see class
        docstring. Never raises: by the time this runs, the request/response cycle
        that could have surfaced an error is long gone, same "background work must
        never crash silently uncaught, only log and degrade" contract
        `TelegramNotificationChannel` follows for the Watchdog scan loop.
        """
        try:
            result = await self._scenario_simulation_runner.execute(free_text=command.text)
        except Exception:  # noqa: BLE001 — runs detached from any request; must never raise.
            logger.exception(
                "Scenario simulation failed for Telegram /simular, chat_id=%s", command.chat_id
            )
            await self._try_send(command.chat_id, _FAILURE_MESSAGE)
            return

        await self._try_send(
            command.chat_id,
            format_scenario_result_reply(result, self._frontend_base_url),
            parse_mode="HTML",
        )

    async def _try_send(self, chat_id: str, text: str, *, parse_mode: str | None = None) -> None:
        try:
            await self._messenger.send_text(chat_id, text, parse_mode=parse_mode)
        except Exception:  # noqa: BLE001 — detached background delivery; must never raise.
            logger.exception("Failed to deliver Telegram /simular result to chat_id=%s", chat_id)
