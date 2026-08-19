"""评价与内容域（4 表）"""

from sqlalchemy import JSON, BigInteger, Column, DateTime, Index, Integer, SmallInteger, String, Text

from app.core.db import Base, utcnow


class Review(Base):
    __tablename__ = "reviews"
    __table_args__ = (Index("idx_product_status", "product_id", "status", "created_at"),)

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    product_id = Column(BigInteger, nullable=False)
    user_id = Column(BigInteger, nullable=False)
    order_item_id = Column(BigInteger, nullable=False, unique=True)  # 一单一评
    rating = Column(SmallInteger, nullable=False)  # 1-5
    content = Column(String(2000))
    images = Column(JSON)
    status = Column(SmallInteger, nullable=False, default=0)  # 0待审 1通过 2拒绝
    reject_reason = Column(String(100))
    edited_after_reject = Column(SmallInteger, nullable=False, default=0)
    created_at = Column(DateTime, nullable=False, default=utcnow)


class Article(Base):
    __tablename__ = "articles"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    slug = Column(String(200), nullable=False, unique=True)
    title = Column(String(200), nullable=False)
    cover = Column(String(500))
    content_md = Column(Text, nullable=False)
    author = Column(String(100), nullable=False)   # Maya Chen / Jordan Lee / Team GLOWMAG
    tags = Column(JSON)
    status = Column(SmallInteger, nullable=False, default=0)  # 0草稿 1发布
    published_at = Column(DateTime)
    created_at = Column(DateTime, nullable=False, default=utcnow)


class Faq(Base):
    __tablename__ = "faqs"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    category = Column(SmallInteger, nullable=False, index=True)  # 1尺码 2佩戴 3物流 4退换 5保养 6账户
    question = Column(String(300), nullable=False)
    answer_md = Column(Text, nullable=False)
    sort_order = Column(Integer, nullable=False, default=0)
    active = Column(SmallInteger, nullable=False, default=1)


class UgcSubmission(Base):
    __tablename__ = "ugc_submissions"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger)
    instagram_handle = Column(String(100))
    image_url = Column(String(500), nullable=False)
    caption = Column(String(500))
    related_product_id = Column(BigInteger)
    status = Column(SmallInteger, nullable=False, default=0)  # 0待审 1上墙 2拒绝
    points_rewarded = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, nullable=False, default=utcnow)
