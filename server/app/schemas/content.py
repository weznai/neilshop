from pydantic import BaseModel, Field


class ReviewIn(BaseModel):
    order_no: str
    order_item_id: int
    rating: int = Field(ge=1, le=5)
    content: str | None = None
    images: list[str] | None = None


class UgcIn(BaseModel):
    image_url: str
    caption: str | None = None
    instagram_handle: str | None = None
    related_product_id: int | None = None
