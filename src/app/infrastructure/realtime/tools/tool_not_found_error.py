class ToolNotFoundError(Exception):
    """Raised when a `/chat/realtime/tool` call names a tool not in the allowlist.

    A security boundary: the browser relays whatever function name the model emits, so an
    unknown/renamed name must be rejected rather than dispatched. The endpoint maps this
    to a 4xx, never a 500.
    """

    def __init__(self, name: str) -> None:
        self.name = name
        super().__init__(f"Unknown realtime tool: {name}")
