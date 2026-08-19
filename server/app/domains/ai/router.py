"""AI 域路由 —— /api/ai/*（HTTP 编排，业务在 service）"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.domains.ai import service
from app.domains.ai.schemas import ChatIn

router = APIRouter(prefix="/api/ai", tags=["ai"])


@router.get("/recommend")
def recommend(
    product_id: int | None = None,
    cart_ids: str | None = None,
    size: int = Query(6, ge=1, le=20),
    db: Session = Depends(get_db),
):
    ids: list[int] = []
    if cart_ids:
        ids = [int(x) for x in cart_ids.split(",") if x.strip().isdigit()]
    return {"items": service.recommend_items(db, product_id=product_id, cart_ids=ids, size=size)}


@router.get("/hot")
def hot(size: int = Query(8, ge=1, le=20), db: Session = Depends(get_db)):
    return {"items": service.hot_items(db, size=size)}


@router.post("/chat")
def chat(body: ChatIn, db: Session = Depends(get_db)):
    return service.chat(db, body)
