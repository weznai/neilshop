"""枚举契约 —— 与《数据库设计文档》各表注释一一对应，禁止改动取值"""

from enum import IntEnum


class UserRole(IntEnum):
    CUSTOMER = 0   # 顾客
    CS = 1         # 客服
    OPS = 2        # 运营
    WAREHOUSE = 3  # 仓库
    ARTIST = 4     # 美甲师（可登录后台受限视图，处理美甲师会话）
    SUPER = 9      # 超管


class ChatChannel(IntEnum):
    AI = 0      # AI 机器人
    HUMAN = 1   # 人工客服
    ARTIST = 2  # 美甲师


class ChatSender(IntEnum):
    CUSTOMER = 1  # 客户
    AGENT = 2     # 人工客服（后台）
    SYSTEM = 3    # 系统提示（转接/接入/关闭）
    BOT = 4       # AI 机器人
    ARTIST = 5    # 美甲师（后台，sender=5 仅 channel=2）


class UserStatus(IntEnum):
    DELETED = -1
    DISABLED = 0
    ACTIVE = 1


class ProductStatus(IntEnum):
    DRAFT = 0
    ACTIVE = 1
    ARCHIVED = 2


class OrderStatus(IntEnum):
    PENDING = 0     # 待付
    PAID = 1        # 已付
    FULFILLING = 2  # 履约中(拣货打包)
    SHIPPED = 3     # 已发货
    DELIVERED = 4   # 已送达
    COMPLETED = 5   # 已完成
    CANCELED = 8    # 已取消
    REFUNDED = 9    # 已退款(全额)


class ShippingStatus(IntEnum):
    NONE = 0
    PARTIAL = 1
    ALL = 2


class PaymentProvider(IntEnum):
    STRIPE = 1
    PAYPAL = 2
    KLARNA = 3
    GIFTCARD = 4
    POINTS = 5


class PaymentStatus(IntEnum):
    PENDING = 0
    SUCCESS = 1
    FAILED = 2
    REFUNDED = 3
    PARTIAL_REFUNDED = 4


class RmaStatus(IntEnum):
    REQUESTED = 0   # 申请中
    APPROVED = 1    # 已批准
    LABEL_SENT = 2  # 标签已发
    IN_TRANSIT = 3  # 在途
    RECEIVED = 4    # 已收货
    REFUNDED = 5    # 已退款
    REJECTED = 6    # 已拒绝
    PARTIAL = 7     # 部分退款


class RmaReason(IntEnum):
    SIZE = 1        # 尺码不合
    QUALITY = 2     # 质量
    DISLIKE = 3     # 不喜欢
    DAMAGED = 4     # 损坏
    WRONG_ITEM = 5  # 发错货
    OTHER = 6       # 其他


class ShipmentStatus(IntEnum):
    AWAITING = 0    # 待打单
    LABELED = 1     # 已打单待拣货
    READY = 2       # 待交接
    IN_TRANSIT = 3  # 运输中
    DELIVERED = 4   # 送达
    EXCEPTION = 5   # 异常
    VOIDED = 6      # 面单作废


class DiscountType(IntEnum):
    PERCENT = 1       # 百分比
    FIXED = 2         # 固定金额
    FREE_SHIPPING = 3  # 免邮


class TicketStatus(IntEnum):
    NEW = 0
    PROCESSING = 1
    WAITING_USER = 2
    RESOLVED = 3
    CLOSED = 4


class TicketCategory(IntEnum):
    SHIPPING = 1   # 物流
    QUALITY = 2    # 质量
    RETURN = 3     # 退换
    ACCOUNT = 4    # 账户
    PRESALE = 5    # 售前
    OTHER = 6      # 其他


class PointsReason(IntEnum):
    ORDER_EARN_FROZEN = 1  # 下单获得(冻结)
    UNFREEZE = 2           # 解冻
    REVIEW_REWARD = 3      # 评价奖励
    CHECKIN = 4            # 签到
    REFERRAL = 5           # 推荐奖励
    BIRTHDAY = 6           # 生日礼
    SPEND = 7              # 消费扣除
    REFUND_VOID = 8        # 退款作废
    REFUND_RETURN = 9      # 退款返还(已用积分部分)
    EXPIRE = 10            # 过期扣减
    ADMIN_ADJUST = 11      # 管理员调整
    UGC_REWARD = 12        # UGC 采用奖励


class StockMovementType(IntEnum):
    PURCHASE = 1     # 采购入库
    RESERVE = 2      # 预扣
    DEDUCT = 3       # 实扣
    RELEASE = 4      # 释放
    RESTOCK = 5      # 退货回补
    COUNT_ADJUST = 6 # 盘点调整
    MANUAL = 7       # 手工调整
    LOSS = 8         # 损耗


class ReferralStatus(IntEnum):
    CLICKED = 0
    REGISTERED = 1
    FIRST_ORDER = 2
    REWARDED = 3
    INVALID = 4


class GiftCardStatus(IntEnum):
    INACTIVE = 0
    ACTIVE = 1
    FROZEN = 2
    EXHAUSTED = 3
    VOIDED = 4


class ReviewStatus(IntEnum):
    PENDING = 0
    APPROVED = 1
    REJECTED = 2
