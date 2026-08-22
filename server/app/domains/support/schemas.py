"""客服域 Pydantic 输入模型"""

from email_validator import EmailNotValidError, EmailSyntaxError, validate_email
from pydantic import BaseModel, Field, field_validator, model_validator


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
    """关单原因：数字枚举（1已解决 2重复 3无效 9其他）或自由文本（服务层归一为 9 其他）；
    兼容后台 ConfirmDialog 自由文本输入与旧数字枚举两种提交"""
    close_reason: int | str | None = None


class TicketStatusIn(BaseModel):
    """工单状态流转：status 仅允许 2/3/4（0/1 态只能经回复进入处理流）"""
    status: int = Field(ge=2, le=4)
    close_reason: int | str | None = None

    @model_validator(mode="after")
    def _close_reason_required(self):
        if self.status == 4 and self.close_reason is None:
            raise ValueError("close_reason required when status is 4")
        return self


class AssignIn(BaseModel):
    admin_id: int
