class UnknownPresetError(ValueError):
    """Raised when a requested preset scenario id isn't in the curated seed list.

    Same shape as `application/signals/unknown_instrument_error.py`'s
    `UnknownInstrumentError` — a router translates this into a `404`.
    """

    def __init__(self, preset_id: str) -> None:
        super().__init__(f"Unknown preset scenario id: {preset_id!r}")
        self.preset_id = preset_id
