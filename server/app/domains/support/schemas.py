"""客服域 Pydantic 输入模型"""

from email_validator import EmailNotValidError, EmailSyntaxError, validate_email
from pydantic import BaseModel, Field, field_validator


def _email_format(value: str) -> str:
    """email-validator 校验（requirements 已有）。
    兼容性例外：仅放行「special-use/reserved 域名」（.test/.example 等内网与测试域），
    其余格式错误（缺 @/无域名/非法字符等）一律 422 —— 严格 EmailStr 会拒绝 .test
    测试域导致既有客户端/夹具回归，违背 API 向后兼容约束，故取语义等价的宽容实现。"""
    try:
        validate_email(value, check_deliverability=False)
    except EmailSyntaxError as exc:
        if "special-use or reserved" not in str(exc):
            raise ValueError("invalid email")
    except EmailNotValidError:
        raise ValueError("invalid email")
    return value


class TicketCreateIn(BaseModel):
    email: str
    order_no: str | None = None
    category: int = Field(ge=1, le=6)
    subject: str
    content: str

    _email_check = field_validator("email")(_email_format)


class TicketMessageIn(BaseModel):
    email: str
    content: str


class ReplyIn(BaseModel):
    content: str


class CloseIn(BaseModel):
    close_reason: int | None = None


class AssignIn(BaseModel):
    admin_id: int
