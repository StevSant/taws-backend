from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel

# A tool handler takes the DI container (to reach real ports/use-cases), the already
# validated Pydantic args model, and the JWT-derived user id, and returns a
# JSON-serializable dict. `Any` for the container avoids a domain/infra import cycle —
# handlers only call `get_*` accessors on it.
ToolHandler = Callable[[Any, BaseModel, str], Awaitable[dict[str, Any]]]


@dataclass(frozen=True, slots=True)
class RealtimeTool:
    """One server-side realtime tool: its name, arg schema, handler, and description.

    `args_model` validates the model-supplied arguments before dispatch (defense against
    hallucinated/malicious parameters); `handler` delegates to an existing use-case/port.
    `description` and the JSON schema derived from `args_model` are what the OpenAI
    session is told about the tool.
    """

    name: str
    description: str
    args_model: type[BaseModel]
    handler: ToolHandler
