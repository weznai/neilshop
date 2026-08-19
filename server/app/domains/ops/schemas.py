"""运营域 Pydantic 输入模型与静态映射表（就近存放）"""

from pydantic import BaseModel, Field

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


class RiskIn(BaseModel):
    flag: int = Field(ge=0, le=2)
