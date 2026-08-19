"""购物车路由（薄路由）—— 游客 X-Cart-Token，登录后可合并；校验/鉴权走 deps，业务在 service_cart。"""

from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import get_cart, get_current_user
from app.domains.trade import service_cart
from app.schemas.cart import CartItemIn, CartMergeIn, CartQtyIn

router = APIRouter(prefix="/api/cart", tags=["cart"])


@router.get("")
@router.get("/")
def get_cart_view(
    response: Response,
    cart_token=Depends(get_cart),
    db: Session = Depends(get_db),
):
    cart, token = cart_token
    response.headers["X-Cart-Token"] = service_cart.token_of(cart, token)
    return service_cart.get_view(db, cart, token)


@router.post("/items", status_code=201)
def add_item(
    body: CartItemIn,
    response: Response,
    cart_token=Depends(get_cart),
    db: Session = Depends(get_db),
):
    cart, token = cart_token
    view = service_cart.add_item(db, cart, token, body.variant_id, body.qty)
    response.headers["X-Cart-Token"] = service_cart.token_of(cart, token)
    return view


@router.put("/items/{variant_id}")
def update_item(
    variant_id: int,
    body: CartQtyIn,
    response: Response,
    cart_token=Depends(get_cart),
    db: Session = Depends(get_db),
):
    cart, token = cart_token
    view = service_cart.update_item(db, cart, token, variant_id, body.qty)
    response.headers["X-Cart-Token"] = service_cart.token_of(cart, token)
    return view


@router.delete("/items/{variant_id}")
def delete_item(
    variant_id: int,
    response: Response,
    cart_token=Depends(get_cart),
    db: Session = Depends(get_db),
):
    cart, token = cart_token
    view = service_cart.delete_item(db, cart, token, variant_id)
    response.headers["X-Cart-Token"] = service_cart.token_of(cart, token)
    return view


@router.post("/merge")
def merge_cart(
    body: CartMergeIn,
    response: Response,
    user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    view, token = service_cart.merge(db, user, body.token)
    response.headers["X-Cart-Token"] = token
    return view
