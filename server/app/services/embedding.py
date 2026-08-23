"""FAQ 向量化服务 —— OpenAI 兼容 /embeddings（与 chat/completions 同网关同 Key）

设计约定（对齐 services/llm.py）：
- 配置复用 settings.llm_config（embedding_model 字段，默认 text-embedding-3-small）
- 未配置 API Key / 任何网络异常 → None，调用方回退全量注入（RAG 不可用不断供客服）
- 仅短批量同步调用（FAQ 索引规模 < 千级），分块/重试不在本层职责内
"""

import logging

import httpx

from app.services.llm import resolve_params

log = logging.getLogger("glowmag.embedding")

DEFAULT_EMBEDDING_MODEL = "text-embedding-3-small"


def embedding_available(params: dict | None = None) -> bool:
    p = params if params is not None else resolve_params()
    return bool(p.get("api_key"))


def embed_texts(texts: list[str], params: dict | None = None) -> list[list[float]] | None:
    """批量向量化：成功返回与 texts 等长的向量列表，未配置/失败返回 None。"""
    if not texts:
        return []
    p = params if params is not None else resolve_params()
    if not p.get("api_key"):
        return None
    payload = {
        "model": p.get("embedding_model") or DEFAULT_EMBEDDING_MODEL,
        "input": texts,
    }
    headers = {"Authorization": f"Bearer {p['api_key']}"}
    try:
        with httpx.Client(timeout=p.get("timeout", 20)) as client:
            r = client.post(f"{p.get('base_url', 'https://api.openai.com/v1')}/embeddings",
                            json=payload, headers=headers)
        if r.status_code != 200:
            log.warning("embedding http %s: %s", r.status_code, r.text[:200])
            return None
        data = sorted(r.json().get("data") or [], key=lambda x: x.get("index", 0))
        vectors = [item.get("embedding") for item in data]
        if len(vectors) != len(texts) or not all(isinstance(v, list) and v for v in vectors):
            log.warning("embedding count/shape mismatch: %d vs %d", len(vectors), len(texts))
            return None
        return vectors
    except Exception as exc:  # 网络/超时/JSON 解析等全部兜底
        log.warning("embedding call failed: %s", exc)
        return None


def faq_text(question: str, answer_md: str) -> str:
    """FAQ 索引文本：问 + 答（答案截断，控制向量表征聚焦问句）"""
    return f"{question}\n{(answer_md or '')[:600]}"
