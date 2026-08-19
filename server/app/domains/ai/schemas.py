"""AI 域 Pydantic 输入模型与静态映射表（意图规则/状态文案/建议话术，就近存放）"""

import re

from pydantic import BaseModel

from app.core.enums import OrderStatus

RULES = [
    ("order", re.compile(r"track|order|package|parcel|shipped|shipment|订单|物流|快递|包裹|到哪|发货|单号", re.I)),
    ("size", re.compile(r"size|sizing|fit|measure|尺码|尺寸|选码|大小|合适", re.I)),
    ("return", re.compile(r"return|refund|exchange|退|换货|退款", re.I)),
    ("wear", re.compile(r"wear|apply|put on|last|reuse|repeat|佩戴|怎么戴|上手|重复|复用|持久|戴多久", re.I)),
    ("care", re.compile(r"care|remove|removal|soak|take off|保养|卸|摘|护理|清洁", re.I)),
    ("points", re.compile(r"point|reward|积分|奖励", re.I)),
    ("account", re.compile(r"account|log ?in|sign ?in|password|email|profile|账户|账号|登录|密码|邮箱|资料", re.I)),
    ("code", re.compile(r"code|coupon|discount|promo|voucher|折扣|优惠|兑换码|券", re.I)),
    ("shipping", re.compile(r"ship|deliver|international|customs|duty|运费|运输|邮寄|国际|清关|几天|配送|多久到", re.I)),
    ("recommend", re.compile(r"recommend|suggest|best seller|popular|which (nail|lash|set|style)|推荐|爆款|热卖|热销|好看|哪款|种草|安利", re.I)),
    ("human", re.compile(r"human|agent|staff|person|representative|complaint|人工|客服|真人|投诉", re.I)),
]

FAQ_CATEGORY = {"size": 1, "wear": 2, "shipping": 3, "return": 4, "care": 5, "points": 6, "account": 6}

STATUS_TEXT = {
    int(OrderStatus.PENDING): ("Awaiting payment", "待支付"),
    int(OrderStatus.PAID): ("Paid", "已支付"),
    int(OrderStatus.FULFILLING): ("Packing", "拣货打包中"),
    int(OrderStatus.SHIPPED): ("Shipped", "已发货"),
    int(OrderStatus.DELIVERED): ("Delivered", "已送达"),
    int(OrderStatus.COMPLETED): ("Completed", "已完成"),
    int(OrderStatus.CANCELED): ("Canceled", "已取消"),
    int(OrderStatus.REFUNDED): ("Refunded", "已退款"),
}

SUGGESTIONS = {
    "order": (["退换货怎么办理？", "折扣码有哪些？", "转人工"],
              ["How do I return an item?", "Any promo codes?", "Talk to a human"]),
    "size": (["一套能戴多久？", "退换货政策", "推荐几款"],
             ["How long does a set last?", "Return policy", "Recommend some sets"]),
    "wear": (["怎么安全卸除？", "怎么选尺码？", "推荐几款"],
             ["How do I remove them safely?", "Help me pick a size", "Recommend some sets"]),
    "return": (["退货要运费吗？", "订单到哪了？", "转人工"],
               ["Is return shipping free?", "Where is my order?", "Talk to a human"]),
    "care": (["能重复戴几次？", "怎么选尺码？", "折扣码有哪些？"],
             ["How many reuses?", "Help me pick a size", "Any promo codes?"]),
    "points": (["积分怎么兑换？", "订单到哪了？", "转人工"],
               ["How do I redeem points?", "Where is my order?", "Talk to a human"]),
    "account": (["忘记密码怎么办？", "订单到哪了？", "转人工"],
                ["Forgot my password", "Where is my order?", "Talk to a human"]),
    "shipping": (["国际配送多久？", "订单到哪了？", "转人工"],
                 ["International delivery time?", "Where is my order?", "Talk to a human"]),
    "code": (["推荐几款热卖", "怎么选尺码？", "订单到哪了？"],
             ["Recommend best sellers", "Help me pick a size", "Where is my order?"]),
    "recommend": (["折扣码有哪些？", "怎么选尺码？", "退换货政策"],
                  ["Any promo codes?", "Help me pick a size", "Return policy"]),
    "human": (["订单到哪了？", "折扣码有哪些？", "怎么选尺码？"],
              ["Where is my order?", "Any promo codes?", "Help me pick a size"]),
    "fallback": (["订单到哪了？", "怎么选尺码？", "折扣码有哪些？"],
                 ["Where is my order?", "Help me pick a size", "Any promo codes?"]),
}

FALLBACK_REPLY = (
    "这个问题我还在学习 🤖 可以问我订单/尺码/退换/折扣码等问题，"
    "或到 contact.html 提交工单，人工客服平均 4 小时内回复。",
    "I'm still learning that one 🤖 Try asking about orders, sizing, returns or promo codes, "
    "or open a ticket at contact.html and our team will reply within ~4 hours.",
)


class ChatIn(BaseModel):
    message: str
    order_no: str | None = None
