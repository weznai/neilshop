"""客服域 Pydantic 输入模型"""

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


class ReplyIn(BaseModel):
    content: str


class CloseIn(BaseModel):
    close_reason: int | None = None


class AssignIn(BaseModel):
    admin_id: int
