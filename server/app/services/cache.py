"""进程内 TTL 只读缓存（架构文档"Redis 预热热销商品缓存"的单机降级版）。

默认关闭：settings.cache_enable False 或 cache_ttl_seconds<=0 时一切直查 DB。
命中返回同引用（响应 dict 只读场景），调用方勿改写缓存返回值；
含 stock 的列表在 TTL 内可能滞后（30-60s，checklist 已接受该权衡）。
"""

import threading
import time
from collections import OrderedDict

from app.core.config import settings

MISS = object()


class TTLCache:
    def __init__(self, ttl: int, clock=time.time):
        self.ttl = ttl
        self.clock = clock
        self._lock = threading.Lock()
        self._data: OrderedDict = OrderedDict()
        self._hits = 0
        self._misses = 0

    def get(self, key: str):
        with self._lock:
            item = self._data.get(key)
            if item is None:
                self._misses += 1
                return MISS
            expires_at, value = item
            if self.clock() >= expires_at:
                del self._data[key]
                self._misses += 1
                return MISS
            self._hits += 1
            return value

    def set(self, key: str, value) -> None:
        if self.ttl <= 0:
            return
        with self._lock:
            self._data[key] = (self.clock() + self.ttl, value)

    def clear(self, prefix: str = "") -> None:
        with self._lock:
            if not prefix:
                self._data.clear()
                return
            for key in [k for k in self._data if k.startswith(prefix)]:
                del self._data[key]

    def stats(self) -> dict:
        with self._lock:
            return {"size": len(self._data), "hits": self._hits, "misses": self._misses}


_cache = TTLCache(ttl=settings.cache_ttl_seconds if settings.cache_enable else 0)


def _effective_ttl(ttl_from_settings: bool, ttl: int | None) -> int:
    if ttl is not None and not ttl_from_settings:
        return ttl
    return settings.cache_ttl_seconds if settings.cache_enable else 0


def _make_key(prefix: str, kwargs: dict) -> str:
    parts = []
    for name in sorted(kwargs):
        value = kwargs[name]
        if isinstance(value, (list, set)):
            value = sorted(value)
        parts.append(f"{name}={value!r}")
    return f"{prefix}:{'|'.join(parts)}"


def cached(prefix: str, ttl_from_settings: bool = True, ttl: int | None = None):
    """函数级缓存装饰器：kwargs 全量组键（首参 db 会话不进键）；ttl<=0 直接执行不缓存。"""

    def deco(fn):
        def wrapper(*args, **kwargs):
            if _effective_ttl(ttl_from_settings, ttl) <= 0:
                return fn(*args, **kwargs)
            key = _make_key(prefix, kwargs)
            value = _cache.get(key)
            if value is not MISS:
                return value
            value = fn(*args, **kwargs)
            _cache.set(key, value)
            return value

        return wrapper

    return deco
