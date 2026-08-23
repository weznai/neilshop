"""AI 客服大模型客户端 —— OpenAI 兼容 chat/completions（任意兼容网关均可）

设计约定：
- 未配置 GM_LLM_API_KEY 时 llm_available()=False，调用方直接走规则引擎（chat 域）
- 任何网络/超时/格式异常一律返回 None，由调用方兜底 —— LLM 故障绝不拖垮会话
- 仅做同步短调用（单条客服回复），流式/重试/向量检索不在本层职责内
"""

import logging

import httpx

from app.core.config import settings

log = logging.getLogger("glowmag.llm")


def llm_available() -> bool:
    return bool(settings.llm_api_key)


def chat_completion(system: str, messages: list[dict], temperature: float = 0.4) -> str | None:
    """OpenAI 风格补全：messages=[{"role":"user"|"assistant","content":...}]；
    成功返回回复文本，未配置/失败返回 None（调用方回退规则引擎）。"""
    if not llm_available():
        return None
    payload = {
        "model": settings.llm_model,
        "temperature": temperature,
        "max_tokens": settings.llm_max_tokens,
        "messages": [{"role": "system", "content": system}, *messages],
    }
    headers = {"Authorization": f"Bearer {settings.llm_api_key}"}
    try:
        with httpx.Client(timeout=settings.llm_timeout) as client:
            r = client.post(f"{settings.llm_base_url}/chat/completions", json=payload, headers=headers)
        if r.status_code != 200:
            log.warning("llm http %s: %s", r.status_code, r.text[:200])
            return None
        data = r.json()
        content = ((data.get("choices") or [{}])[0].get("message") or {}).get("content")
        text = (content or "").strip()
        return text or None
    except Exception as exc:  # 网络/超时/JSON 解析等全部兜底
        log.warning("llm call failed: %s", exc)
        return None
