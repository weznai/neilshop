"""AI 域路由 —— /api/ai/*（HTTP 编排，业务在 service）"""

import math
import threading
import time
from collections import deque

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import get_current_user_optional
from app.domains.ai import service
from app.domains.ai.schemas import ChatIn
from app.models import User

router = APIRouter(prefix="/api/ai", tags=["ai"])

# /chat 域内轻量限流：公开无鉴权 + 直连 DB；全局限流（observability.RATE_RULES）未覆盖 ai 前缀故此处补位
CHAT_RATE_LIMIT = 30     # 每 IP 每窗口次数（测试可 monkeypatch）
CHAT_RATE_WINDOW = 60.0  # 窗口秒数，与 observability.RATE_WINDOW 同口径
_MAX_BUCKETS = 10000     # 桶表上限（防伪造海量 IP 撑内存，超限顺手清过期桶）
_rate_lock = threading.Lock()
_rate_buckets: dict[str, deque] = {}


def _chat_retry_after(ip: str) -> int:
    """滑动窗计数：超限返回建议等待秒数，未超限记账并返回 0"""
    now = time.monotonic()
    with _rate_lock:
        if len(_rate_buckets) > _MAX_BUCKETS:
            for k in [k for k, b in _rate_buckets.items() if not b or b[-1] <= now - CHAT_RATE_WINDOW]:
                del _rate_buckets[k]
        bucket = _rate_buckets.setdefault(ip, deque())
        while bucket and bucket[0] <= now - CHAT_RATE_WINDOW:
            bucket.popleft()
        if len(bucket) >= CHAT_RATE_LIMIT:
            return max(1, math.ceil(bucket[0] + CHAT_RATE_WINDOW - now))
        bucket.append(now)
        return 0


@router.get("/recommend")
def recommend(
    product_id: int | None = None,
    cart_ids: str | None = None,
    size: int = Query(6, ge=1, le=20),
    db: Session = Depends(get_db),
):
    ids: list[int] = []
    if cart_ids:
        ids = [int(x) for x in cart_ids.split(",") if x.strip().isdigit()][:20]  # 钳制防超长 IN 列表
    return {"items": service.recommend_items(db, product_id=product_id, cart_ids=ids, size=size)}


@router.get("/hot")
def hot(size: int = Query(8, ge=1, le=20), db: Session = Depends(get_db)):
    return {"items": service.hot_items(db, size=size)}


@router.post("/chat")
def chat(
    body: ChatIn,
    request: Request,
    user: User | None = Depends(get_current_user_optional),
    db: Session = Depends(get_db),
):
    retry = _chat_retry_after(request.client.host if request.client else "unknown")
    if retry:
        raise HTTPException(status_code=429, detail="rate_limited",
                            headers={"Retry-After": str(retry)})
    return service.chat(db, body, user)
