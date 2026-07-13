from pydantic import BaseModel


class SendTestNewsResponse(BaseModel):
    status: str
    event_title: str
