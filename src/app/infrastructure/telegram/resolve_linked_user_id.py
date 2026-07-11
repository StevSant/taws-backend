from app.domain.telegram.ports import TelegramLinkRepository


async def resolve_linked_user_id(
    link_repository: TelegramLinkRepository, chat_id: str
) -> str | None:
    """Resolve an inbound webhook `chat_id` to its linked `user_id`, or `None` if this
    chat hasn't completed the `/start <token>` linking flow yet (issue #19).

    Shared by every command handler that needs "whose data am I fetching" —
    `BriefingCommandHandler`, `SignalCommandHandler`, `SimulateCommandHandler` — so
    "not linked yet" is resolved (and, by each caller, messaged) identically
    everywhere, via `TelegramLinkRepository.get_by_chat_id` (the reverse lookup added
    alongside this issue — see that port method's docstring).
    """
    link = await link_repository.get_by_chat_id(chat_id)
    return link.user_id if link is not None else None
