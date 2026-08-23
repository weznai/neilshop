"""AI 客服大模型客户端 —— OpenAI 兼容 chat/completions（任意兼容网关均可）

设计约定：
- 配置来源优先级：settings 表 key=llm_config（后台可配）> 环境变量 GM_LLM_*（.env）
- 未配置 API Key 时 llm_available()=False，调用方直接走规则引擎（chat 域）
- 任何网络/超时/格式异常一律返回 None，由调用方兜底 —— LLM 故障绝不拖垮会话
- 仅做同步短调用（单条客服回复），流式/重试/向量检索不在本层职责内
"""

import logging

import httpx

from app.core.config import settings

log = logging.getLogger("glowmag.llm")

LLM_SETTING_KEY = "llm_config"


def resolve_params(db=None) -> dict:
    """生效配置：env 兜底 + settings 表覆盖（DB 异常静默回退 env，客服不断供）"""
    params = {
        "api_key": settings.llm_api_key,
        "base_url": settings.llm_base_url,
        "model": settings.llm_model,
        "timeout": settings.llm_timeout,
        "max_tokens": settings.llm_max_tokens,
        # 以下仅 DB 可配（无 env 对应项）：人设/补充指令/温度/向量模型（提示词组装见 chat/prompt.py，检索见 chat/retrieval.py）
        "persona": "",
        "prompt_extra": "",
        "temperature": 0.4,
        "embedding_model": "",
    }
    if db is not None:
        try:
            from app.models import Setting

            row = db.get(Setting, LLM_SETTING_KEY)
            if row and isinstance(row.value, dict):
                for k in ("api_key", "base_url", "model", "persona", "prompt_extra", "embedding_model"):
                    v = row.value.get(k)
                    if isinstance(v, str) and v.strip():
                        params[k] = v.strip()
                for k in ("timeout", "max_tokens"):
                    v = row.value.get(k)
                    if isinstance(v, int) and v > 0:
                        params[k] = v
                v = row.value.get("temperature")
                if isinstance(v, (int, float)) and 0 <= v <= 2:
                    params["temperature"] = float(v)
        except Exception as exc:  # DB 故障不影响 env 配置
            log.warning("llm config load failed: %s", exc)
    return params


def mask_key(key: str) -> str:
    """脱敏展示：sk-ab***wxyz（≤8 位全隐藏）"""
    if not key:
        return ""
    if len(key) <= 8:
        return "***"
    return key[:3] + "***" + key[-4:]


def llm_available(params: dict | None = None) -> bool:
    p = params if params is not None else resolve_params()
    return bool(p.get("api_key"))


def chat_completion(system: str, messages: list[dict], temperature: float | None = None,
                    params: dict | None = None) -> str | None:
    """OpenAI 风格补全：messages=[{"role":"user"|"assistant","content":...}]；
    temperature=None 用配置值（后台可调），显式传入则覆盖（连通测试传 0）。
    成功返回回复文本，未配置/失败返回 None（调用方回退规则引擎）。"""
    p = params if params is not None else resolve_params()
    if not p.get("api_key"):
        return None
    temp = p.get("temperature", 0.4) if temperature is None else temperature
    payload = {
        "model": p.get("model"),
        "temperature": temp,
        "max_tokens": p.get("max_tokens", 500),
        "messages": [{"role": "system", "content": system}, *messages],
    }
    headers = {"Authorization": f"Bearer {p['api_key']}"}
    try:
        with httpx.Client(timeout=p.get("timeout", 20)) as client:
            r = client.post(f"{p.get('base_url', 'https://api.openai.com/v1')}/chat/completions",
                            json=payload, headers=headers)
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
