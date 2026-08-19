"""智能体 B（P0）自测 —— 变体级图片 + UGC 买家秀公开接口
（GM_DB=sqlite:///test_p0b.sqlite 独立库；BigInteger 垫片同 test_payments.py）"""

import os
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_DB = os.path.join(_ROOT, "test_p0b.sqlite").replace("\\", "/")
for _suffix in ("", "-wal", "-shm"):
    _p = _DB + _suffix
    if os.path.exists(_p):
        os.remove(_p)
os.environ["GM_DB"] = f"sqlite:///{_DB}"
os.environ["GM_COOKIE_AUTH"] = "0"  # 纯 Bearer 通道：登录 Cookie 不进 TestClient 会话
sys.path.insert(0, _ROOT)

from app.core.config import settings as app_settings  # noqa: E402

if app_settings.db_url.startswith("sqlite"):
    from sqlalchemy import BigInteger
    from sqlalchemy.ext.compiler import compiles

    @compiles(BigInteger, "sqlite")
    def _bigint_as_integer(type_, compiler, **kw):
        return "INTEGER"

from fastapi.testclient import TestClient  # noqa: E402

from app.core.db import SessionLocal, init_db, utcnow  # noqa: E402
from app.core.security import create_token, hash_password  # noqa: E402
from app.main import app  # noqa: E402
from app.models import (  # noqa: E402
    Category, Product, UgcSubmission, User, Variant, VariantImage,
)

PASSED = 0
FAILED = []


def check(name, cond, info=""):
    global PASSED
    if cond:
        PASSED += 1
        print(f"  ok  {name}")
    else:
        FAILED.append(name)
        print(f"FAIL  {name}  {info}")


init_db()
db = SessionLocal()

admin = User(email="admin@glowmag.test", name="P0B Admin", role=2, status=1,
              password_hash=hash_password("p0bpass123"))
db.add(admin)
db.flush()

cat = Category(slug="press-on-nails", name="Press-on Nails")
db.add(cat)
db.flush()

bare = Product(slug="bare-gems", title="Bare Gems", subtitle="Nude base with crystal accents",
               category_id=cat.id, status=1, price_min=1599, price_max=1799,
               hero_image="/img/bare.jpg", images=["/img/bare-1.jpg", "/img/bare-2.jpg"],
               tags=["french", "nude"], published_at=utcnow())
venus = Product(slug="venus", title="Venus", subtitle="Pearl chrome masterpiece",
                category_id=cat.id, status=1, price_min=1999, price_max=2199,
                hero_image="/img/venus.jpg", tags=["chrome"], published_at=utcnow())
db.add_all([bare, venus])
db.flush()
v1 = Variant(product_id=bare.id, sku="BG-SA-24", option1_value="Short Almond",
             option2_value="24 pcs", price=1599, stock=40, safety_stock=5)
v2 = Variant(product_id=bare.id, sku="BG-MS-24", option1_value="Medium Square",
             option2_value="24 pcs", price=1799, stock=12, safety_stock=5)
db.add_all([v1, v2])
db.flush()

for uid, handle, img, cap, pid, st in [
    (admin.id, "@olivia.bennett", "/img/ugc-1.jpg", "Sunday reset with Bare Gems.", bare.id, 1),
    (admin.id, "@ava.wearsit", "/img/ugc-2.jpg", "French tips era, week two.", None, 1),
    (admin.id, "@sophia.naildiary", "/img/ugc-3.jpg", "Pearl chrome indeed.", venus.id, 1),
    (admin.id, "@mia.foster", "/img/ugc-4.jpg", "My whole summer in a set.", 424242, 1),
    (admin.id, "@harper.reed", "/img/ugc-5.jpg", "Still waiting for review.", bare.id, 0),
    (admin.id, "@anon", "/img/ugc-6.jpg", "Rejected one.", bare.id, 2),
]:
    db.add(UgcSubmission(user_id=uid, instagram_handle=handle, image_url=img,
                         caption=cap, related_product_id=pid, status=st,
                         points_rewarded=100 if st == 1 else 0))
db.commit()
WALL_IDS = [row.id for row in
            db.query(UgcSubmission.id).filter(UgcSubmission.status == 1)
            .order_by(UgcSubmission.id.desc()).all()]
db.close()


def detail_variants(client):
    d = client.get("/api/catalog/products/bare-gems").json()
    return {v["id"]: v for v in d["variants"]}


def main() -> int:
    with TestClient(app) as client:
        r = client.get("/api/content/ugc")
        check("未登录可访问 UGC 墙（无 token 200）", r.status_code == 200, r.text)
        body = r.json()
        check("仅 status=1 上墙（4/6 条）",
              body["total"] == 4 and len(body["items"]) == 4
              and {i["image_url"] for i in body["items"]} ==
              {"/img/ugc-1.jpg", "/img/ugc-2.jpg", "/img/ugc-3.jpg", "/img/ugc-4.jpg"},
              body)
        ids = [i["id"] for i in body["items"]]
        check("id 倒序（最新上墙在前）", ids == WALL_IDS and ids == sorted(ids, reverse=True), ids)
        by_id = {i["id"]: i for i in body["items"]}
        check("product 关联懒加载（slug/title/hero_image）",
              by_id[WALL_IDS[-1]]["product"] == {"slug": "bare-gems", "title": "Bare Gems",
                                                 "hero_image": "/img/bare.jpg"})
        check("product 关联 venus",
              by_id[WALL_IDS[-3]]["product"]["slug"] == "venus")
        check("product 为 null（无关联或失效关联）",
              by_id[WALL_IDS[-2]]["product"] is None and by_id[WALL_IDS[0]]["product"] is None)
        pg = client.get("/api/content/ugc", params={"page": 2, "size": 3}).json()
        check("分页 total/页内容", pg["total"] == 4 and len(pg["items"]) == 1
              and pg["items"][0]["id"] == WALL_IDS[-1], pg)

        atok = create_token(admin.id, admin.role)
        h = {"Authorization": f"Bearer {atok}"}
        imgs = ["/img/v3-macro.jpg", "/img/v3-hand.jpg", "/img/v3-flatlay.jpg"]
        r = client.post(f"/api/admin/catalog/products/{bare.id}/variants", headers=h, json={
            "sku": "BG-LS-24", "option1_value": "Long Stiletto", "option2_value": "24 pcs",
            "price": 1899, "stock": 15, "images": imgs})
        check("admin 建变体带 images（201 回显）",
              r.status_code == 201 and r.json()["images"] == imgs, r.text)
        vid = r.json()["id"]
        vs = detail_variants(client)
        check("商品详情新变体 images 按序就位", vs[vid]["images"] == imgs)
        check("旧变体无图 images=[]",
              vs[v1.id]["images"] == [] and vs[v2.id]["images"] == [])
        check("详情 variants[] 纯加法键（原键齐全）",
              all(set(v) >= {"id", "sku", "price", "stock", "safety_stock",
                             "option1_value", "option2_value", "stock_status", "images"}
                  for v in vs.values()))

        new_imgs = ["/img/v3-new-1.jpg", "/img/v3-new-2.jpg"]
        r = client.put(f"/api/admin/catalog/variants/{vid}", headers=h,
                       json={"images": new_imgs})
        check("PUT 替换 images（响应回显）",
              r.status_code == 200 and r.json()["images"] == new_imgs, r.text)
        fresh = SessionLocal()
        try:
            rows = fresh.query(VariantImage).filter(
                VariantImage.variant_id == vid).order_by(VariantImage.sort_order).all()
            old_left = fresh.query(VariantImage).filter(
                VariantImage.image_url.in_(imgs)).count()
            check("PUT 整表替换：旧删新存 + sort_order 重排",
                  [row.image_url for row in rows] == new_imgs
                  and [row.sort_order for row in rows] == [0, 1] and old_left == 0)
        finally:
            fresh.close()
        r = client.put(f"/api/admin/catalog/variants/{vid}", headers=h,
                       json={"price": 1949})
        check("PUT 不传 images 不动",
              r.status_code == 200 and r.json()["price"] == 1949
              and detail_variants(client)[vid]["images"] == new_imgs)
        r = client.put(f"/api/admin/catalog/variants/{vid}", headers=h,
                       json={"images": []})
        fresh = SessionLocal()
        try:
            left = fresh.query(VariantImage).filter(
                VariantImage.variant_id == vid).count()
        finally:
            fresh.close()
        check("PUT images=[] 清空",
              r.status_code == 200 and r.json()["images"] == []
              and detail_variants(client)[vid]["images"] == [] and left == 0)
        r = client.post(f"/api/admin/catalog/products/{bare.id}/variants", headers=h, json={
            "sku": "BG-XX-24", "option1_value": "Coffin", "option2_value": "24 pcs",
            "price": 1699, "images": [f"/img/over-{i}.jpg" for i in range(7)]})
        check("超过 6 张 images 422", r.status_code == 422, r.text)

    print(f"{PASSED} passed, {len(FAILED)} failed")
    return 0 if not FAILED else 1


if __name__ == "__main__":
    raise SystemExit(main())
