"""运营域 Pydantic 输入模型与静态映射表（就近存放）"""

from pydantic import BaseModel, EmailStr, Field, field_validator

REASON_TEXT = {
    1: "下单获得（冻结中）",
    2: "解冻",
    3: "评价奖励",
    4: "签到",
    5: "推荐奖励",
    6: "生日礼",
    7: "消费扣除",
    8: "退款作废",
    9: "退款返还",
    10: "过期",
    11: "管理员调整",
    12: "买家秀奖励",
}

# 管理账号可用角色：2运营 / 3仓库 / 9超管（1客服不进后台管理面）
ADMIN_ROLES = {2, 3, 9}


class RiskIn(BaseModel):
    flag: int = Field(ge=0, le=2)


class BulkModerationIn(BaseModel):
    """评价/UGC 批量审核入参基类：仅待审(0)记录会被处理，非待审静默跳过"""
    ids: list[int] = Field(min_length=1)
    action: str = Field(pattern="^(approve|reject)$")


class ReviewBulkIn(BulkModerationIn):
    reason: str | None = None  # 仅 reject 使用


class UgcBulkIn(BulkModerationIn):
    pass


class PointsAdjustIn(BaseModel):
    """积分人工调整入参：delta 非零且 |delta| ≤ 100 万；reason 必填（审计留痕）"""
    delta: int = Field(ge=-1_000_000, le=1_000_000)
    reason: str = Field(min_length=1, max_length=200)

    @field_validator("delta")
    @classmethod
    def _delta_not_zero(cls, v: int) -> int:
        if v == 0:
            raise ValueError("delta must not be zero")
        return v


class AdminCreateIn(BaseModel):
    """管理员建号入参（仅超管）：email 唯一 / 密码 ≥8 位 / role ∈ {2,3,9}"""
    email: EmailStr
    name: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=8, max_length=128)
    role: int

    @field_validator("role")
    @classmethod
    def _role_allowed(cls, v: int) -> int:
        if v not in ADMIN_ROLES:
            raise ValueError("role must be one of 2,3,9")
        return v


class AdminUpdateIn(BaseModel):
    """管理员资料更新入参（仅超管）：name/role/status 三选皆可选；
    不能改自己 role / 停用自己（service 层 400 cannot modify self）"""
    name: str | None = Field(default=None, min_length=1, max_length=100)
    role: int | None = None
    status: int | None = None

    @field_validator("role")
    @classmethod
    def _role_allowed(cls, v: int | None) -> int | None:
        if v is not None and v not in ADMIN_ROLES:
            raise ValueError("role must be one of 2,3,9")
        return v

    @field_validator("status")
    @classmethod
    def _status_allowed(cls, v: int | None) -> int | None:
        if v is not None and v not in (0, 1):
            raise ValueError("status must be 0 or 1")
        return v
