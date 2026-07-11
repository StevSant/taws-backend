from dataclasses import dataclass


@dataclass(slots=True)
class SimulateCommand:
    """A parsed `/simular <text>` command from a Telegram webhook update (issue #19).

    `text` is the free-form scenario description, fed straight into the Scenario
    Simulation graph's Intake step as `free_text`.
    """

    chat_id: str
    text: str
