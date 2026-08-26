"""数据模型聚合 —— 各域按未来微服务边界分文件（拆分时文件直接跟着服务走）"""

from app.models.user import User, UserAddress, EmailPreference, CookieConsent, DataRequest
from app.models.product import (
    Category, Product, Variant, VariantImage, StockNotification,
    ProductTranslation, Collection, CollectionProduct,
)
from app.models.trade import Cart, Order, OrderItem, PaymentMethod, Payment, WebhookEvent
from app.models.fulfill import Shipment, Rma, Exchange, OrderTimeline, ShippingRate
from app.models.promo import (
    DiscountCode, DiscountRedemption, Bundle, GiftCard, GiftCardLedger,
    Referral, Subscription, PopupConfig, UserCoupon,
)
from app.models.content import Review, Article, Faq, UgcSubmission
from app.models.support import (
    Ticket, TicketMessage, ReplyTemplate, ChatConversation, ChatMessage,
)
from app.models.inventory import (
    StockMovement, Supplier, PurchaseOrder, PurchaseOrderItem, StockCount,
)
from app.models.points import PointsLedger, WishlistItem
from app.models.system import AdminLog, Setting, OutboxEvent, NewsletterSubscriber
from app.models.reconcile import ReconciliationDaily

__all__ = [name for name in dir() if not name.startswith("_")]
