from typing import Annotated

from pydantic import Field

from app.infrastructure.agents.macro_source import MacroSource
from app.infrastructure.agents.news_source import NewsSource
from app.infrastructure.agents.quant_source import QuantSource
from app.infrastructure.agents.signal_source import SignalSource

Source = Annotated[
    NewsSource | SignalSource | QuantSource | MacroSource,
    Field(discriminator="kind"),
]
