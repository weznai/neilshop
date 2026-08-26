"""P0-3 补测 —— TTLCache maxsize 上限与最旧淘汰（纯单元，不落库；
GM_CACHE_MAXSIZE 默认值/覆盖映射一并验证）"""

import os
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))
os.chdir(BASE)

from app.core.config import settings  # noqa: E402
from app.services.cache import MISS, TTLCache  # noqa: E402

PASSED = 0
FAILED = []


def check(name, cond, info=""):
    global PASSED
    if cond:
        PASSED += 1
        print(f"  ok {PASSED:02d} - {name}")
    else:
        FAILED.append(name)
        print(f"FAIL {PASSED + 1:02d} - {name}  {info}")


class FakeClock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


clock = FakeClock()

# ---- maxsize 淘汰：最旧（最早写入序）先走 ----
c = TTLCache(ttl=60, clock=clock, maxsize=3)
c.set("k1", "v1")
c.set("k2", "v2")
c.set("k3", "v3")
c.set("k4", "v4")  # 超限 → k1（最旧）被淘汰
check("超限后 size 钳制在 maxsize", c.stats()["size"] == 3, c.stats())
check("最旧键 k1 被淘汰", c.get("k1") is MISS)
check("其余键完好", c.get("k2") == "v2" and c.get("k3") == "v3" and c.get("k4") == "v4")

c.set("k2", "v2b")  # 原键覆写不增 size
check("原键覆写不增加条目", c.stats()["size"] == 3 and c.get("k2") == "v2b")
c.set("k5", "v5")
check("再写仍淘汰当前最旧 k2", c.get("k2") is MISS and c.get("k3") == "v3"
      and c.get("k4") == "v4" and c.get("k5") == "v5")

# ---- maxsize=1 极限 ----
c1 = TTLCache(ttl=60, clock=clock, maxsize=1)
c1.set("a", 1)
c1.set("b", 2)
check("maxsize=1 只留最新", c1.stats()["size"] == 1 and c1.get("a") is MISS and c1.get("b") == 2)

# ---- 默认 maxsize 来自配置 ----
check("settings.cache_maxsize 默认 10000", settings.cache_maxsize == 10000,
      settings.cache_maxsize)
cdef = TTLCache(ttl=60, clock=clock)
check("未显式传 maxsize 时走配置默认", cdef.maxsize == 10000, cdef.maxsize)

# ---- 淘汰与 TTL 过期互不干扰（stats 口径兼容） ----
clock.now += 61
check("淘汰后剩余键仍按 TTL 过期清除",
      c1.get("b") is MISS and c1.stats()["size"] == 0)

print(f"\nALL PASS: {PASSED}/{PASSED + len(FAILED)}")
if FAILED:
    print("FAILED:", FAILED)
    sys.exit(1)
