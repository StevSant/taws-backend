from app.infrastructure.telegram.briefing_command import BriefingCommand
from app.infrastructure.telegram.chat_message import ChatMessage
from app.infrastructure.telegram.event_callback import EventCallback
from app.infrastructure.telegram.impact_command import ImpactCommand
from app.infrastructure.telegram.signal_command import SignalCommand
from app.infrastructure.telegram.simulate_command import SimulateCommand
from app.infrastructure.telegram.start_command import StartCommand
from app.infrastructure.telegram.unknown_command import UnknownCommand

TelegramCommand = (
    StartCommand
    | BriefingCommand
    | ImpactCommand
    | SignalCommand
    | SimulateCommand
    | UnknownCommand
    | ChatMessage
    | EventCallback
)
"""Every inbound Telegram command this webhook understands (issue #19), as returned by
`parse_telegram_command`. A plain union (not a base class) — same "no shared behavior,
just a closed set of shapes to `match`/`isinstance` on" role `AgentStreamEvent`
(`domain/agents/entities`) plays for SSE frame kinds.

`EventCallback` is the odd one out: every other member comes from a `message` update, while
it comes from a `callback_query` (a tapped inline button on a broadcast news alert). It's in
the union anyway so the webhook keeps ONE dispatch point rather than growing a second,
parallel branch for button taps."""
