import math
import os
import subprocess
import sys
import threading
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import httpx
import pymysql

BASE_DIR = Path(__file__).resolve().parents[1]
PY = BASE_DIR / ".venv" / "Scripts" / "python.exe"
PORT = 8019
BASE_URL = f"http://127.0.0.1:{PORT}"
DB_NAME = "glowmag_test_cc"
GM_DB_URL = f"mysql+pymysql://glowmag:glowmag123@127.0.0.1:3306/{DB_NAME}?charset=utf8mb4"
os.environ["GM_COOKIE_AUTH"] = "0"  # 纯 Bearer 通道
# 压测需瞬时打满 place（30 并发抢购 + 5 并发同用户幂等），把该规则阈值临时调高；
# 其余规则（password-reset 20/min 等）保持默认，rate-limit 用例不受影响
os.environ["GM_RATE_RULES"] = '{"/api/checkout/place": 120}'
TMP_DIR = Path(os.environ.get("TEMP", str(Path.home() / "AppData" / "Local" / "Temp"))) / "opencode"
LOG_PATH = TMP_DIR / "uvicorn_8019_cc.log"

PASSWORD = "cc-pass-12345678"
EMAILS = [f"cc_t1_u{i:02d}@glowmagcc.com" for i in range(30)]
ADDRESS = {
    "full_name": "CC Tester",
    "line1": "1 Concurrency Way",
    "city": "San Francisco",
    "state": "CA",
    "zip": "94105",
    "country": "US",
    "phone": "+14155550000",
}
PLACE_BODY = {"address": ADDRESS, "shipping_method": "standard"}

CASES = []
_tls = threading.local()


def cli() -> httpx.Client:
    c = getattr(_tls, "c", None)
    if c is None:
        c = httpx.Client(
            base_url=BASE_URL,
            timeout=60.0,
            limits=httpx.Limits(max_connections=64, max_keepalive_connections=64),
        )
        _tls.c = c
    return c


def auth(tok: str) -> dict:
    return {"Authorization": f"Bearer {tok}"}


def db_conn(user: str = "glowmag", password: str = "glowmag123") -> pymysql.connections.Connection:
    return pymysql.connect(
        host="127.0.0.1", user=user, password=password,
        database=DB_NAME, charset="utf8mb4", autocommit=True,
    )


def q(sql: str, args=None) -> list[tuple]:
    cn = db_conn()
    try:
        with cn.cursor() as cur:
            cur.execute(sql, args or ())
            return cur.fetchall()
    finally:
        cn.close()


def pct(vals: list[float], p: float) -> float:
    if not vals:
        return 0.0
    s = sorted(vals)
    i = max(0, min(len(s) - 1, math.ceil(p * len(s)) - 1))
    return s[i]


def log_tail(n: int = 80) -> str:
    try:
        lines = LOG_PATH.read_text(encoding="utf-8", errors="replace").splitlines()
        return "\n".join(lines[-n:])
    except OSError:
        return "<no uvicorn log>"


def reset_database() -> None:
    cn = pymysql.connect(host="127.0.0.1", user="root", password="123456", autocommit=True)
    try:
        with cn.cursor() as cur:
            cur.execute(f"DROP DATABASE IF EXISTS {DB_NAME}")
            cur.execute(
                f"CREATE DATABASE {DB_NAME} CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci"
            )
            for host in ("%", "localhost", "127.0.0.1"):
                try:
                    cur.execute(f"GRANT ALL PRIVILEGES ON {DB_NAME}.* TO 'glowmag'@'{host}'")
                except pymysql.err.MySQLError:
                    pass
    finally:
        cn.close()


def run_seed() -> None:
    env = dict(os.environ, GM_DB=GM_DB_URL)
    r = subprocess.run(
        [str(PY), "scripts/seed.py"], cwd=str(BASE_DIR), env=env,
        capture_output=True, text=True, timeout=300,
    )
    if r.returncode != 0:
        raise RuntimeError(f"seed failed rc={r.returncode}\n{r.stdout}\n{r.stderr}")


def make_variants() -> tuple[int, int]:
    cn = db_conn()
    try:
        with cn.cursor() as cur:
            cur.execute("SELECT id FROM products WHERE status=1 ORDER BY id LIMIT 1")
            pid = cur.fetchone()[0]
            cur.execute(
                "INSERT INTO variants (product_id, sku, option1_name, option1_value, "
                "option2_name, option2_value, price, stock, safety_stock, version, "
                "weight_gram, is_active, created_at, updated_at) "
                "VALUES (%s,'CC-SECKILL-SA','shape','Short Almond','length','24 pcs',"
                "999,10,0,0,30,1,NOW(),NOW())",
                (pid,),
            )
            seckill = cur.lastrowid
            cur.execute(
                "INSERT INTO variants (product_id, sku, option1_name, option1_value, "
                "option2_name, option2_value, price, stock, safety_stock, version, "
                "weight_gram, is_active, created_at, updated_at) "
                "VALUES (%s,'CC-IDEM-MS','shape','Medium Square','length','24 pcs',"
                "1099,10,0,0,30,1,NOW(),NOW())",
                (pid,),
            )
            idem = cur.lastrowid
            return seckill, idem
    finally:
        cn.close()


def start_server() -> tuple[subprocess.Popen, object]:
    TMP_DIR.mkdir(parents=True, exist_ok=True)
    log = open(LOG_PATH, "w", encoding="utf-8", errors="replace")
    env = dict(os.environ, GM_DB=GM_DB_URL)
    proc = subprocess.Popen(
        [str(PY), "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1",
         "--port", str(PORT), "--log-level", "info"],
        cwd=str(BASE_DIR), env=env, stdout=log, stderr=subprocess.STDOUT,
    )
    for _ in range(180):
        if proc.poll() is not None:
            log.flush()
            raise RuntimeError(f"uvicorn exited rc={proc.returncode}\n{log_tail()}")
        try:
            if httpx.get(f"{BASE_URL}/api/health", timeout=2).status_code == 200:
                return proc, log
        except httpx.HTTPError:
            pass
        time.sleep(0.5)
    raise RuntimeError(f"uvicorn health timeout\n{log_tail()}")


def register_users() -> list[str]:
    c = httpx.Client(base_url=BASE_URL, timeout=60.0)
    tokens = []
    for i, email in enumerate(EMAILS):
        r = c.post(
            "/api/account/register",
            json={"email": email, "password": PASSWORD, "name": f"CC User {i:02d}"},
        )
        if r.status_code != 201 or not r.json().get("token"):
            raise RuntimeError(f"register {email} -> {r.status_code} {r.text[:300]}")
        tokens.append(r.json()["token"])
    c.close()
    return tokens


def barrage(n: int, fn):
    barrier = threading.Barrier(n + 1, timeout=60)

    def warm(i: int) -> None:
        try:
            cli().get("/api/health")
        except httpx.HTTPError:
            pass

    def work(i: int) -> None:
        try:
            warm(i)
            barrier.wait()
            out[i] = fn(i)
        except threading.BrokenBarrierError:
            out[i] = {"status": 0, "body": "broken_barrier"}
        except Exception as e:
            out[i] = {"status": -1, "body": repr(e)}

    out = [None] * n
    with ThreadPoolExecutor(max_workers=n) as ex:
        futs = [ex.submit(work, i) for i in range(n)]
        try:
            barrier.wait()
        except threading.BrokenBarrierError:
            pass
        for f in futs:
            f.result()
    return out


def record(name: str, ok: bool, metrics: dict, errs: list[str]) -> bool:
    num = len(CASES) + 1
    CASES.append((name, ok, metrics, errs))
    tag = "PASS" if ok else "FAIL"
    print(f"CASE {num} [{name}] {tag}")
    for k, v in metrics.items():
        print(f"    {k} = {v}")
    for e in errs:
        print(f"    ERROR: {e}")
    if not ok:
        print(f"    ---- uvicorn log tail ----\n{log_tail()}")
    return ok


def case_oversell(tokens: list[str], vid: int):
    c = httpx.Client(base_url=BASE_URL, timeout=60.0)
    for i, tok in enumerate(tokens):
        r = c.post("/api/cart/items", json={"variant_id": vid, "qty": 1}, headers=auth(tok))
        if r.status_code != 201:
            return False, {"setup_cart_add": f"{EMAILS[i]} -> {r.status_code} {r.text[:200]}"}, \
                [f"cart add failed for {EMAILS[i]}"]
    c.close()

    def fire(i: int):
        t0 = time.perf_counter()
        r = cli().post(
            "/api/checkout/place",
            json=dict(PLACE_BODY, email=EMAILS[i]),
            headers=auth(tokens[i]),
        )
        ms = (time.perf_counter() - t0) * 1000
        try:
            body = r.json()
        except ValueError:
            body = {"raw": r.text[:200]}
        return {"status": r.status_code, "body": body, "ms": round(ms, 1)}

    res = barrage(30, fire)
    codes = Counter(r["status"] for r in res)
    n201 = codes.get(201, 0)
    n409 = codes.get(409, 0)
    others = {k: v for k, v in codes.items() if k not in (201, 409)}
    details_409 = [r["body"].get("detail", "") for r in res if r["status"] == 409]
    stock_insufficient = sum(1 for d in details_409 if str(d).startswith("insufficient_stock"))
    order_nos = [r["body"].get("order_no") for r in res if r["status"] == 201]
    stock, version = q("SELECT stock, version FROM variants WHERE id=%s", (vid,))[0]
    mv_cnt, mv_sum = q(
        "SELECT COUNT(*), COALESCE(SUM(`change`),0) FROM stock_movements WHERE variant_id=%s AND `type`=2",
        (vid,),
    )[0]
    order_cnt = q(
        "SELECT COUNT(*) FROM orders o WHERE EXISTS (SELECT 1 FROM order_items oi "
        "WHERE oi.order_id=o.id AND oi.variant_id=%s)",
        (vid,),
    )[0][0]

    errs = []
    if n201 != 10:
        errs.append(f"201 count {n201} != 10 (undersell: optimistic-lock version conflicts rejected buyers while stock left={stock})")
    if n409 != 20:
        errs.append(f"409 count {n409} != 20")
    if others:
        errs.append(f"unexpected status codes: {others}")
    if stock_insufficient != n409:
        errs.append(f"409 detail mismatch: insufficient_stock={stock_insufficient}/{n409}")
    if stock != 0:
        errs.append(f"final stock {stock} != 0 (negative would be oversell, positive means unsold stock with rejected buyers)")
    if mv_cnt != 10 or mv_sum != -10:
        errs.append(f"RESERVE movements cnt={mv_cnt} sum={mv_sum} != 10/-10")
    if order_cnt != 10:
        errs.append(f"orders in DB {order_cnt} != 10")
    if stock < 0:
        errs.append(f"OVERSOLD: stock {stock} < 0")

    metrics = {
        "201": n201, "409": n409, "other": dict(others) or 0,
        "stock_final": stock, "version_final": version,
        "reserve_moves(cnt,sum)": (mv_cnt, int(mv_sum)), "orders_in_db": order_cnt,
        "false_insufficient_409": (f"{n409}/{n409} (stock never hit 0, floor={stock})"
                                   if stock > 0 else "0 (sold out, all 409 true)"),
        "place_ms_p95": pct([r["ms"] for r in res], 0.95),
    }
    ok = not errs
    if ok:
        return True, metrics, []
    diag = []
    for r in res:
        if r["status"] not in (201, 409):
            diag.append(f"non-201/409: {r}")
    return ok, metrics, errs + diag[:5]


def case_same_user(tokens: list[str], vid: int):
    tok = tokens[1]
    email = EMAILS[1]
    c = httpx.Client(base_url=BASE_URL, timeout=60.0)
    for (seckill_vid,) in q("SELECT id FROM variants WHERE sku='CC-SECKILL-SA'"):
        c.delete(f"/api/cart/items/{seckill_vid}", headers=auth(tok))
    r = c.post("/api/cart/items", json={"variant_id": vid, "qty": 1}, headers=auth(tok))
    c.close()
    if r.status_code != 201:
        return False, {"setup_cart_add": r.status_code}, [f"cart add failed: {r.text[:200]}"]
    stock_before = q("SELECT stock FROM variants WHERE id=%s", (vid,))[0][0]

    def fire(_i: int):
        r = cli().post(
            "/api/checkout/place", json=dict(PLACE_BODY, email=email), headers=auth(tok),
        )
        try:
            body = r.json()
        except ValueError:
            body = {"raw": r.text[:200]}
        return {"status": r.status_code, "body": body}

    res = barrage(5, fire)
    codes = Counter(r["status"] for r in res)
    n201 = codes.get(201, 0)
    order_nos = {r["body"].get("order_no") for r in res if r["status"] == 201}
    stock_after = q("SELECT stock FROM variants WHERE id=%s", (vid,))[0][0]
    mv_cnt, mv_sum = q(
        "SELECT COUNT(*), COALESCE(SUM(`change`),0) FROM stock_movements WHERE variant_id=%s AND `type`=2",
        (vid,),
    )[0]
    qty_sum = q(
        "SELECT COALESCE(SUM(oi.qty),0) FROM order_items oi WHERE oi.variant_id=%s", (vid,),
    )[0][0]
    order_cnt = q(
        "SELECT COUNT(*) FROM orders o WHERE EXISTS (SELECT 1 FROM order_items oi "
        "WHERE oi.order_id=o.id AND oi.variant_id=%s)",
        (vid,),
    )[0][0]

    errs = []
    if n201 != 5:
        errs.append(f"status dist {dict(codes)} != 5x201 (idempotent replay should all succeed)")
    if len(order_nos) != 1:
        errs.append(f"idempotency broken: got {len(order_nos)} distinct order_nos {order_nos}")
    if (stock_before - stock_after) != 1 or qty_sum != 1:
        errs.append(
            f"inconsistent deduction: stock delta={stock_before - stock_after}, "
            f"order qty sum={qty_sum}, expected exactly 1 (dedup must not double-reserve)"
        )
    if mv_cnt != 1 or mv_sum != -1:
        errs.append(f"RESERVE movements cnt={mv_cnt} sum={mv_sum} != 1/-1")
    if order_cnt != 1:
        errs.append(f"orders for variant {order_cnt} != 1 (duplicate orders created)")

    metrics = {
        "status_dist": dict(codes), "distinct_orders": len(order_nos),
        "stock": f"{stock_before}->{stock_after}", "qty_sum": qty_sum,
        "reserve_moves": (mv_cnt, int(mv_sum)),
        "note": "same-user concurrent places dedup to one PENDING order within 90s window",
    }
    return not errs, metrics, errs


def case_payment_concurrency(order_nos: list[str]):
    if not order_nos:
        return False, {"orders": 0}, ["case 1 produced no orders"]
    c = httpx.Client(base_url=BASE_URL, timeout=60.0)
    for no in order_nos:
        r = c.post("/api/payments/create-intent", json={"order_no": no})
        if r.status_code != 200:
            c.close()
            return False, {"create_intent": f"{no} -> {r.status_code}"}, [r.text[:200]]
    c.close()

    def fire(i: int):
        r = cli().post("/api/payments/mock-pay", json={"order_no": order_nos[i], "succeed": True})
        try:
            body = r.json()
        except ValueError:
            body = {"raw": r.text[:200]}
        return {"status": r.status_code, "body": body}

    res = barrage(len(order_nos), fire)
    codes = Counter(r["status"] for r in res)
    n = len(order_nos)
    ph = ",".join(["%s"] * n)
    orders = q(
        f"SELECT id, order_no, grand_total, user_id FROM orders WHERE order_no IN ({ph})",
        tuple(order_nos),
    )
    ids = tuple(str(o[0]) for o in orders)
    ids_i = tuple(o[0] for o in orders)
    users_i = tuple(o[3] for o in orders)
    expected = sum(o[2] // 10 for o in orders)
    not_paid = q(
        f"SELECT order_no, status FROM orders WHERE id IN ({ph}) AND status<>1", ids
    )
    ledger = q(
        f"SELECT ref_id, COUNT(*), SUM(`change`) FROM points_ledger "
        f"WHERE reason=1 AND ref_type='order' AND ref_id IN ({ph}) GROUP BY ref_id",
        ids,
    )
    grant_sum = int(sum(r[2] for r in ledger))
    dup = [(r[0], r[1]) for r in ledger if r[1] != 1]
    u_ph = ",".join(["%s"] * len(users_i))
    user_points = int(q(f"SELECT COALESCE(SUM(points),0) FROM users WHERE id IN ({u_ph})", users_i)[0][0])
    pay_ok = q(
        f"SELECT COUNT(*) FROM payments WHERE order_id IN ({ph}) AND status=1", ids
    )[0][0]

    errs = []
    if codes.get(200, 0) != n:
        errs.append(f"mock-pay status dist {dict(codes)} != all 200")
    if any(r["body"].get("order_status") != 1 for r in res if r["status"] == 200):
        errs.append("some mock-pay order_status != 1")
    if not_paid:
        errs.append(f"orders not PAID: {not_paid}")
    if len(ledger) != n:
        errs.append(f"frozen grant rows {len(ledger)} != orders {n}")
    if dup:
        errs.append(f"duplicate grant rows per order: {dup}")
    if grant_sum != expected:
        errs.append(f"points granted {grant_sum} != expected {expected}")
    if user_points != expected:
        errs.append(f"users points sum {user_points} != expected {expected}")
    if pay_ok != n:
        errs.append(f"success payments {pay_ok} != {n}")

    metrics = {
        "mock_pay": dict(codes), "orders_paid": len(orders) - len(not_paid),
        "points_expected": expected, "points_granted": grant_sum,
        "users_points_sum": user_points, "grant_rows": len(ledger),
        "dup_grants": dup or 0, "payments_success": pay_ok,
    }
    return not errs, metrics, errs


def case_rate_limit():
    statuses = []
    health_ok = []
    retry_after = None
    c = httpx.Client(base_url=BASE_URL, timeout=60.0)
    for i in range(1, 22):
        r = c.post("/api/account/password-reset/request", json={"email": "nobody@glowmagcc.com"})
        if r.status_code == 429:
            retry_after = r.headers.get("Retry-After")
        statuses.append(r.status_code)
        if i in (1, 10, 20):
            h = c.get("/api/health")
            health_ok.append(h.status_code)
    c.close()

    errs = []
    if statuses[:20] != [200] * 20:
        errs.append(f"first 20 statuses {Counter(statuses[:20])} != all 200")
    if statuses[20] != 429:
        errs.append(f"21st status {statuses[20]} != 429")
    if retry_after is None:
        errs.append("429 without Retry-After header")
    if health_ok != [200] * 3:
        errs.append(f"health checks {health_ok} != all 200")

    metrics = {
        "first20_ok": statuses[:20].count(200), "21st": statuses[20],
        "retry_after": retry_after, "health_during": health_ok,
    }
    return not errs, metrics, errs


def case_read_load():
    targets = [
        ("list", "/api/catalog/products?sort=new&page=1&size=12"),
        ("detail", "/api/catalog/products/bare-gems"),
        ("search", "/api/catalog/search?q=nail"),
    ]

    def fire(_i: int):
        out = []
        for kind, url in targets:
            t0 = time.perf_counter()
            r = cli().get(url)
            ms = (time.perf_counter() - t0) * 1000
            out.append((kind, r.status_code, round(ms, 1)))
        return out

    res = barrage(50, fire)
    samples = [s for chunk in res for s in chunk]
    bad = [s for s in samples if s[1] != 200]
    lat = [s[2] for s in samples]
    by_kind = {
        k: [s[2] for s in samples if s[0] == k] for k, _ in targets
    }

    errs = []
    if bad:
        errs.append(f"non-200 responses: {bad[:5]} (total {len(bad)})")
    p95 = pct(lat, 0.95)
    if p95 > 2000:
        errs.append(f"P95 {p95}ms > 2000ms hard limit")

    metrics = {
        "requests": len(samples), "non200": len(bad),
        "P50/P95/P99_ms": (round(pct(lat, 0.5), 1), round(p95, 1), round(pct(lat, 0.99), 1)),
    }
    for k in by_kind:
        metrics[f"{k}_p95_ms"] = round(pct(by_kind[k], 0.95), 1)
    if p95 > 800 and p95 <= 2000:
        metrics["warning"] = f"P95 {p95}ms > 800ms SLO (soft, not failed)"
    return not errs, metrics, errs


def case_rate_window_recovery():
    for left in range(61, 0, -1):
        if left % 10 == 0:
            print(f"    ... rate window recovering, {left}s left")
        time.sleep(1)
    c = httpx.Client(base_url=BASE_URL, timeout=60.0)
    r = c.post("/api/account/password-reset/request", json={"email": "nobody@glowmagcc.com"})
    c.close()
    ok = r.status_code == 200
    return ok, {"after_61s": r.status_code, "body": r.text[:80]}, \
        [] if ok else [f"expected 200 after window, got {r.status_code} {r.text[:200]}"]


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    print(f"[setup] reset database {DB_NAME} (root) + GRANT glowmag")
    reset_database()
    print("[setup] seed.py ->", DB_NAME)
    run_seed()
    seckill_vid, idem_vid = make_variants()
    print(f"[setup] seckill variant={seckill_vid} (stock=10), idem variant={idem_vid} (stock=10)")

    proc = log = None
    try:
        proc, log = start_server()
        print(f"[setup] uvicorn :{PORT} up, log={LOG_PATH}")
        tokens = register_users()
        print(f"[setup] {len(tokens)} users registered")

        ok1, m1, e1 = case_oversell(tokens, seckill_vid)
        record("oversell-race", ok1, m1, e1)
        rows = q(
            "SELECT o.order_no FROM orders o JOIN order_items oi ON oi.order_id=o.id "
            "WHERE oi.variant_id=%s ORDER BY o.id",
            (seckill_vid,),
        )
        order_nos = [r[0] for r in rows]

        ok2, m2, e2 = case_same_user(tokens, idem_vid)
        record("same-user-idempotency", ok2, m2, e2)

        ok3, m3, e3 = case_payment_concurrency(order_nos)
        record("payment-concurrency", ok3, m3, e3)

        ok4, m4, e4 = case_rate_limit()
        record("rate-limit", ok4, m4, e4)

        ok5, m5, e5 = case_read_load()
        record("read-mixed-load", ok5, m5, e5)

        ok6, m6, e6 = case_rate_window_recovery()
        record("rate-window-recovery", ok6, m6, e6)
    finally:
        if proc is not None and proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(10)
            except subprocess.TimeoutExpired:
                subprocess.run(
                    ["taskkill", "/F", "/T", "/PID", str(proc.pid)], capture_output=True
                )
        if proc is not None and proc.poll() is None:
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)], capture_output=True)
        if log is not None:
            log.close()

    passed = sum(1 for _, ok, _, _ in CASES if ok)
    total = len(CASES)
    print("=" * 60)
    for idx, (name, ok, _, errs) in enumerate(CASES, 1):
        print(f"  {idx}. {name:<24} {'PASS' if ok else 'FAIL'}  {('; '.join(errs[:1])) if errs else ''}")
    print(f"CONCURRENCY: {passed}/{total} passed")
    if passed == total:
        try:
            LOG_PATH.unlink(missing_ok=True)
        except OSError:
            pass
    else:
        print(f"[diag] uvicorn log kept: {LOG_PATH}")
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
