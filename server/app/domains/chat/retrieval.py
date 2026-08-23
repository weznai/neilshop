"""FAQ RAG 检索 —— 向量化（services/embedding）+ 余弦 top-k + 内存缓存

数据流：
- 索引：FAQ 保存时 best-effort 向量化（content/service.py 钩子），
  或后台「重建索引」批量补齐（chat/router_admin rag/reindex）
- 检索：build_system_prompt(query) → retrieve() 余弦 top-k，
  命中则注入相关片段；embedding 不可用/覆盖率过低 → 返回 None，
  调用方回退全量注入（prompt.py），客服不断供

缓存：FAQ 向量集进程内 TTL 60s（千级 FAQ × 1536 维 JSON 解析不便宜），
FAQ 增删改后由 invalidate() 主动失效。
"""

import math
import time

from sqlalchemy.orm import Session

from app.services.embedding import embed_texts, faq_text

RAG_TOP_K = 5          # 每次注入的 FAQ 片段数
RAG_MIN_SCORE = 0.30   # 余弦相似度阈值（低于视为不相关，不注入）
RAG_MIN_COVERAGE = 0.5  # 已索引 FAQ 占比低于此值 → 视为 RAG 未就绪，回退全量
_CACHE_TTL = 60

_cache: dict = {"at": 0.0, "rows": []}  # rows = [(id, question, answer_md, vector)]


def invalidate() -> None:
    _cache["at"] = 0.0
    _cache["rows"] = []


def _load_rows(db: Session) -> list[tuple]:
    """启用中的 FAQ 向量集（TTL 缓存；无向量的行不进缓存，检索时直接跳过）"""
    if time.monotonic() - _cache["at"] < _CACHE_TTL:
        return _cache["rows"]
    from app.domains.chat import repository as repo

    rows = [
        (f.id, f.question, f.answer_md, f.embedding)
        for f in repo.active_faqs(db)
        if isinstance(f.embedding, list) and f.embedding
    ]
    _cache["at"] = time.monotonic()
    _cache["rows"] = rows
    return rows


def _cosine(a: list[float], b: list[float]) -> float:
    if len(a) != len(b):
        return -1.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return -1.0
    return dot / (na * nb)


def rag_ready(db: Session) -> bool:
    """RAG 可用性：embedding 网关已配 + 已索引 FAQ 覆盖率达标"""
    from app.services.embedding import embedding_available
    from app.services.llm import resolve_params

    if not embedding_available(resolve_params(db)):
        return False
    from app.domains.chat import repository as repo

    total = repo.active_faqs(db)
    if not total:
        return False  # 空 KB 本就走全量分支（注入 empty 提示）
    embedded = sum(1 for f in total if isinstance(f.embedding, list) and f.embedding)
    return embedded / len(total) >= RAG_MIN_COVERAGE


def retrieve(db: Session, query: str, k: int = RAG_TOP_K) -> list[tuple[int, str, str]] | None:
    """top-k 检索：返回 [(id, question, answer_md)]；
    RAG 未就绪/查询向量化失败/无过阈值片段 → None（回退全量注入）"""
    if not query or not rag_ready(db):
        return None
    rows = _load_rows(db)
    if not rows:
        return None
    qv = embed_texts([query])
    if not qv:
        return None
    scored = [( _cosine(qv[0], vec), fid, q, a) for fid, q, a, vec in rows]
    scored.sort(key=lambda x: x[0], reverse=True)
    hits = [(fid, q, a) for s, fid, q, a in scored[:k] if s >= RAG_MIN_SCORE]
    return hits or None


def rag_status(db: Session) -> dict:
    """RAG 状态（后台展示）：网关配置 + 覆盖率"""
    from app.domains.chat import repository as repo
    from app.services.llm import resolve_params

    p = resolve_params(db)
    faqs = repo.active_faqs(db)
    embedded = sum(1 for f in faqs if isinstance(f.embedding, list) and f.embedding)
    total = len(faqs)
    ready = bool(p.get("api_key")) and total > 0 and embedded / total >= RAG_MIN_COVERAGE
    return {
        "ready": ready,
        "embedded": embedded,
        "total": total,
        "embedding_model": p.get("embedding_model") or "",
    }


def reindex(db: Session, only_missing: bool = True) -> dict:
    """（重建）索引：批量向量化启用中的 FAQ；only_missing=True 跳过已索引行。
    返回 {ok, indexed, failed}；网关不可用 ok=False。"""
    from app.domains.chat import repository as repo
    from app.services.llm import resolve_params

    p = resolve_params(db)
    if not p.get("api_key"):
        return {"ok": False, "reason": "未配置 API Key", "indexed": 0, "failed": 0}
    faqs = repo.active_faqs(db)
    targets = [f for f in faqs if not only_missing or not (isinstance(f.embedding, list) and f.embedding)]
    if not targets:
        invalidate()
        return {"ok": True, "indexed": 0, "failed": 0}
    indexed = failed = 0
    B = 64  # 分批防单请求超限
    for i in range(0, len(targets), B):
        batch = targets[i:i + B]
        vectors = embed_texts([faq_text(f.question, f.answer_md) for f in batch], p)
        if vectors is None:
            failed += len(batch)
            continue
        for f, v in zip(batch, vectors):
            f.embedding = v
            indexed += 1
        db.flush()
    db.commit()
    invalidate()
    return {"ok": failed == 0, "indexed": indexed, "failed": failed}
