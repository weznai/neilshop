"""系统域（4 表）"""

from sqlalchemy import JSON, BigInteger, Column, DateTime, Index, Integer, SmallInteger, String

from app.core.db import Base, utcnow


class AdminLog(Base):
    __tablename__ = "admin_logs"
    __table_args__ = (
        Index("idx_entity", "entity", "entity_id"),
        Index("idx_admin_created", "admin_id", "created_at"),
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    admin_id = Column(BigInteger, nullable=False)
    action = Column(String(50), nullable=False)   # update/ship/refund/adjust...
    entity = Column(String(30), nullable=False)   # order/product/return/ticket
    entity_id = Column(BigInteger, nullable=False)
    diff_json = Column(JSON)
    ip = Column(String(45))
    created_at = Column(DateTime, nullable=False, default=utcnow)


class Setting(Base):
    __tablename__ = "settings"

    key = Column(String(100), primary_key=True)   # free_shipping_threshold/tax_rate/...
    value = Column(JSON, nullable=False)
    description = Column(String(200))
    updated_by = Column(BigInteger)
    updated_at = Column(DateTime, nullable=False, default=utcnow, onupdate=utcnow)


class OutboxEvent(Base):
    __tablename__ = "outbox_events"
    __table_args__ = (Index("idx_unpublished", "published", "created_at"),)

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    aggregate_type = Column(String(30), nullable=False)  # order/refund/review
    aggregate_id = Column(BigInteger, nullable=False)
    event_type = Column(String(60), nullable=False)      # order.paid / order.refunded
    payload = Column(JSON, nullable=False)
    published = Column(SmallInteger, nullable=False, default=0)
    published_at = Column(DateTime)
    retry_count = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, nullable=False, default=utcnow)


class NewsletterSubscriber(Base):
    __tablename__ = "newsletter_subscribers"

    email = Column(String(191), primary_key=True)
    source = Column(String(30), nullable=False)   # popup/checkout/footer
    klaviyo_synced = Column(SmallInteger, nullable=False, default=0)
    created_at = Column(DateTime, nullable=False, default=utcnow)
