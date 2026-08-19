"""商品域（8 表）"""

from sqlalchemy import (
    JSON, BigInteger, Column, DateTime, Index, Integer,
    SmallInteger, String, Text,
)
from sqlalchemy.dialects.mysql import MEDIUMTEXT

from app.core.db import Base, utcnow


class Category(Base):
    __tablename__ = "categories"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    parent_id = Column(BigInteger)
    slug = Column(String(100), nullable=False, unique=True)  # press-on-nails/magnetic-lashes/accessories
    name = Column(String(100), nullable=False)
    sort_order = Column(Integer, nullable=False, default=0)
    is_active = Column(SmallInteger, nullable=False, default=1)


class Product(Base):
    __tablename__ = "products"
    __table_args__ = (
        Index("idx_cat_status_pub", "category_id", "status", "published_at"),
        Index("idx_best", "is_best_seller", "status"),
        Index("idx_new", "is_new", "status", "published_at"),
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    slug = Column(String(150), nullable=False, unique=True)   # bare-gems
    title = Column(String(200), nullable=False)
    subtitle = Column(String(300))
    description_md = Column(Text().with_variant(MEDIUMTEXT(), "mysql"))
    category_id = Column(BigInteger, nullable=False)
    status = Column(SmallInteger, nullable=False, default=0)  # 0草稿 1上架 2下架
    compare_at_price = Column(Integer)                        # 划线价（美分），NULL=无
    price_min = Column(Integer, nullable=False, default=0)    # 冗余，列表页免 JOIN
    price_max = Column(Integer, nullable=False, default=0)
    hero_image = Column(String(500), nullable=False, default="")
    images = Column(JSON, nullable=False, default=list)
    video_url = Column(String(500))
    tags = Column(JSON)                                       # ["new","french"]
    is_new = Column(SmallInteger, nullable=False, default=0)
    is_best_seller = Column(SmallInteger, nullable=False, default=0)
    rating_avg = Column(Integer, nullable=False, default=0)   # ×100 存储，4.87 → 487
    rating_count = Column(Integer, nullable=False, default=0)
    sold_count = Column(Integer, nullable=False, default=0)
    published_at = Column(DateTime)
    created_at = Column(DateTime, nullable=False, default=utcnow)
    updated_at = Column(DateTime, nullable=False, default=utcnow, onupdate=utcnow)


class Variant(Base):
    __tablename__ = "variants"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    product_id = Column(BigInteger, nullable=False, index=True)
    sku = Column(String(64), nullable=False, unique=True)     # BG-SA-SHORT
    option1_name = Column(String(50), nullable=False, default="shape")
    option1_value = Column(String(50), nullable=False)        # Short Almond
    option2_name = Column(String(50), nullable=False, default="length")
    option2_value = Column(String(50), nullable=False)        # 24pcs
    price = Column(Integer, nullable=False)                   # 计价唯一来源（美分）
    cost = Column(Integer)
    stock = Column(Integer, nullable=False, default=0)        # DB 权威值
    safety_stock = Column(Integer, nullable=False, default=5)
    weight_gram = Column(Integer, nullable=False, default=30)
    version = Column(Integer, nullable=False, default=0)      # 乐观锁
    is_active = Column(SmallInteger, nullable=False, default=1)
    created_at = Column(DateTime, nullable=False, default=utcnow)
    updated_at = Column(DateTime, nullable=False, default=utcnow, onupdate=utcnow)


class VariantImage(Base):
    __tablename__ = "variant_images"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    variant_id = Column(BigInteger, nullable=False, index=True)
    image_url = Column(String(500), nullable=False)
    sort_order = Column(Integer, nullable=False, default=0)


class StockNotification(Base):
    __tablename__ = "stock_notifications"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    variant_id = Column(BigInteger, nullable=False)
    email = Column(String(191), nullable=False)
    notified_at = Column(DateTime)      # NULL=待通知
    clicked_at = Column(DateTime)
    converted_order_no = Column(String(20))
    created_at = Column(DateTime, nullable=False, default=utcnow)


class ProductTranslation(Base):
    __tablename__ = "product_translations"

    product_id = Column(BigInteger, primary_key=True)
    locale = Column(String(5), primary_key=True)  # en-US/zh-CN
    title = Column(String(200), nullable=False)
    subtitle = Column(String(300))
    description_md = Column(Text().with_variant(MEDIUMTEXT(), "mysql"))


class Collection(Base):
    __tablename__ = "collections"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    slug = Column(String(100), nullable=False, unique=True)   # best-sellers/under-20/sale
    title = Column(String(150), nullable=False)
    rule_json = Column(JSON, nullable=False)                  # {"tags":["new"],"price_lt":2000}
    banner_image = Column(String(500))
    sort_order = Column(Integer, nullable=False, default=0)
    is_active = Column(SmallInteger, nullable=False, default=1)


class CollectionProduct(Base):
    __tablename__ = "collection_products"

    collection_id = Column(BigInteger, primary_key=True)
    product_id = Column(BigInteger, primary_key=True, index=True)
    sort_order = Column(Integer, nullable=False, default=0)
    added_at = Column(DateTime, nullable=False, default=utcnow)
