"""商品域请求模型（Pydantic v2，含后台管理）。原 app/schemas/catalog.py。"""

from datetime import datetime, timezone
from urllib.parse import urlparse

from pydantic import BaseModel, Field, field_validator


class ProductCreateIn(BaseModel):
    slug: str = Field(min_length=1, max_length=150)
    title: str = Field(min_length=1, max_length=200)
    subtitle: str | None = Field(default=None, max_length=300)
    description_md: str | None = Field(default=None, max_length=50000)
    category_id: int
    price_min: int = Field(ge=0)
    price_max: int = Field(ge=0)
    compare_at_price: int | None = Field(default=None, ge=0)
    hero_image: str = Field(default="", max_length=500)
    images: list[str] | None = Field(default=None, max_length=8)
    video_url: str | None = Field(default=None, max_length=500)
    tags: list[str] | None = None
    is_new: bool = False
    is_best_seller: bool = False


class ProductUpdateIn(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    subtitle: str | None = Field(default=None, max_length=300)
    description_md: str | None = Field(default=None, max_length=50000)
    category_id: int | None = None
    compare_at_price: int | None = Field(default=None, ge=0)
    tags: list[str] | None = None
    price_min: int | None = Field(default=None, ge=0)
    price_max: int | None = Field(default=None, ge=0)
    hero_image: str | None = Field(default=None, max_length=500)
    images: list[str] | None = Field(default=None, max_length=8)
    video_url: str | None = Field(default=None, max_length=500)
    is_new: bool | None = None
    is_best_seller: bool | None = None
    published_at: datetime | None = None  # 定时上架：ISO 字符串或 null（前台查询时生效）

    @field_validator("published_at", mode="before")
    @classmethod
    def _parse_published_at(cls, v):
        if v is None or isinstance(v, datetime):
            return v
        if isinstance(v, str):
            s = v.strip()
            if s.lower() in ("", "null"):
                return None
            try:
                d = datetime.fromisoformat(s.replace("Z", "+00:00"))
            except ValueError:
                raise ValueError("invalid published_at (ISO 8601 expected)")
            if d.tzinfo is not None:  # 统一落 naive UTC，与列口径一致
                d = d.astimezone(timezone.utc).replace(tzinfo=None)
            return d
        raise ValueError("invalid published_at (ISO 8601 expected)")


class ProductBulkIn(BaseModel):
    items: list[ProductCreateIn] = Field(min_length=1, max_length=100)


class VariantCreateIn(BaseModel):
    sku: str = Field(min_length=1, max_length=64)
    option1_value: str = Field(min_length=1, max_length=50)
    option2_value: str = Field(min_length=1, max_length=50)
    price: int = Field(ge=0)
    stock: int = Field(default=0, ge=0)
    weight_gram: int = Field(default=30, ge=0)
    images: list[str] | None = Field(default=None, max_length=6)


class VariantUpdateIn(BaseModel):
    price: int | None = Field(default=None, ge=0)
    is_active: bool | None = None
    safety_stock: int | None = Field(default=None, ge=0)
    images: list[str] | None = Field(default=None, max_length=6)


class CategoryCreateIn(BaseModel):
    slug: str = Field(min_length=1, max_length=100)
    name: str = Field(min_length=1, max_length=100)
    parent_id: int | None = None


class CollectionCreateIn(BaseModel):
    slug: str = Field(min_length=1, max_length=100)
    title: str = Field(min_length=1, max_length=150)
    rule_json: dict
    banner_image: str | None = Field(default=None, max_length=500)

    @field_validator("banner_image")
    @classmethod
    def _check_banner_image(cls, v):
        if v is None or not v.strip():
            return v
        parsed = urlparse(v.strip())
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            raise ValueError("banner_image must be an http(s) URL")
        return v


class CollectionUpdateIn(BaseModel):
    """集合部分更新：仅传需要改的字段（未传保持原值）"""
    title: str | None = Field(default=None, min_length=1, max_length=150)
    banner_image: str | None = Field(default=None, max_length=500)
    sort_order: int | None = None
    is_active: bool | None = None


class CollectionProductIn(BaseModel):
    product_id: int
    sort_order: int = 0


class CollectionProductsIn(BaseModel):
    products: list[CollectionProductIn]


class StockNotifyIn(BaseModel):
    variant_id: int = Field(ge=1)
    email: str = Field(min_length=3, max_length=191)


class TranslationUpsertIn(BaseModel):
    locale: str = Field(pattern=r"^[a-z]{2}-[A-Z]{2}$")  # zh-CN/en-US/fr-FR...
    title: str = Field(min_length=1, max_length=200)
    subtitle: str | None = Field(default=None, max_length=300)
    description_md: str | None = None
