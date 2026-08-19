from pydantic import BaseModel, Field


class TicketCreateIn(BaseModel):
    email: str
    order_no: str | None = None
    category: int = Field(ge=1, le=6)
    subject: str
    content: str


class TicketMessageIn(BaseModel):
    email: str
    content: str
