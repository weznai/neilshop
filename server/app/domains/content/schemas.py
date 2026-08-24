"""内容域 Pydantic 输入模型与静态映射表（就近存放）"""

from pydantic import BaseModel, Field

FAQ_CATEGORY = {1: "尺码", 2: "佩戴", 3: "物流", 4: "退换", 5: "保养", 6: "账户"}

UGC_REWARD = 100

# 评价过审奖励积分（enums.PointsReason.REVIEW_REWARD 无运营配置项，先用常量）
REVIEW_REWARD = 10


class ReviewIn(BaseModel):
    order_no: str
    order_item_id: int
    rating: int = Field(ge=1, le=5)
    content: str | None = None
    images: list[str] | None = None


class UgcIn(BaseModel):
    image_url: str
    # DB 列 500/100，收安全值（超长垃圾入库前拦截）
    caption: str | None = Field(default=None, max_length=200)
    instagram_handle: str | None = Field(default=None, max_length=60)
    related_product_id: int | None = None


class ReasonIn(BaseModel):
    reason: str


class ArticleCreateIn(BaseModel):
    slug: str
    title: str
    author: str
    content_md: str
    cover: str | None = Field(default=None, max_length=500)  # 封面图 URL/路径，空串清除
    tags: list | None = None
    status: int = Field(default=0, ge=0, le=1)


class ArticleUpdateIn(BaseModel):
    slug: str | None = None
    title: str | None = None
    author: str | None = None
    content_md: str | None = None
    cover: str | None = Field(default=None, max_length=500)  # 传空串清除封面
    tags: list | None = None
    status: int | None = Field(default=None, ge=0, le=1)


class FaqCreateIn(BaseModel):
    category: int = Field(ge=1, le=6)
    question: str
    answer_md: str
    sort_order: int = 0


class FaqUpdateIn(BaseModel):
    category: int | None = Field(default=None, ge=1, le=6)
    question: str | None = None
    answer_md: str | None = None
    sort_order: int | None = None
    active: int | None = Field(default=None, ge=0, le=1)
