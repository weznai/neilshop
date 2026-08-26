"""GlowBot 系统提示词组装 —— 三层结构：

1. persona（人设，后台可配）：名字/语气/身份认同
2. SAFETY_RULES（安全红线，硬编码不可配）：不编造订单/价格/折扣码、语言跟随、超出 KB 转人工
3. prompt_extra（补充指令，后台可配）：大促话术/临时规则等运营自主内容
4. facts + KB（自动注入）：settings 运营参数摘要（运费/退货窗口）+ FAQ 全量

配置存 settings.llm_config（与 API Key 同行，见 services/llm.resolve_params），
未配置回退 DEFAULT_PERSONA / 无 extra。

智能体（Agent）扩展路线 —— 本模块是唯一提示词出口，演进不打散调用方：
- Phase 2 在此注册 TOOLS schema（order_lookup/faq_search/product_search…），
  build_system_prompt 追加工具使用规范；
- Phase 3 send_message 的 LLM 分支升级 agent loop（LLM → tool_calls →
  执行器脱敏查库 → 结果回灌 → 最终回复，限制轮数），
  意图路由仍 rules 优先，订单类问题由「LLM 禁入」升级为「受控 tool」
  （LLM 只拿到执行器脱敏后的结构化结果，依然不直接接触订单库）。
"""

from sqlalchemy.orm import Session

DEFAULT_PERSONA = (
    "You are GlowBot, the friendly AI assistant of GLOWMAG, "
    "a press-on nail & lash e-commerce shop."
)

KB_CHAR_BUDGET = 8000  # 全量注入总字符预算：防大 KB 撑爆 system prompt（约 2k token）

SAFETY_RULES = (
    "Rules:\n"
    "- Reply in the same language as the customer (English or Chinese).\n"
    "- Be concise (under ~120 words), warm and helpful; at most 2 emojis.\n"
    "- Answer shop-policy questions ONLY from the knowledge base below; "
    "if the answer is not there, say you will connect a human agent.\n"
    "- Never invent order status, tracking numbers, prices or discount codes; "
    "for order tracking point customers to the /track page."
)


def build_system_prompt(db: Session, query: str | None = None) -> str:
    """组装最终提示词：人设 + 安全红线 + 补充指令 + 政策摘要 + FAQ 知识库

    知识注入两种模式（chat/retrieval.py）：
    - RAG：query 非空且向量检索就绪 → 仅注入 top-k 相关片段（KB 大时省 token、提相关性）
    - 全量：未配 embedding / 覆盖率不足 / 检索无命中 → 注入全部启用 FAQ（现状兼容）
    """
    from app.domains.ai.service import _return_summary, _shipping_summary
    from app.domains.chat import repository as repo
    from app.domains.chat.retrieval import retrieve
    from app.services.llm import resolve_params

    p = resolve_params(db)
    persona = (p.get("persona") or "").strip() or DEFAULT_PERSONA
    extra = (p.get("prompt_extra") or "").strip()

    hits = retrieve(db, query) if query else None
    if hits is not None:
        kb = "\n\n".join(f"Q: {q}\nA: {a}" for _, q, a in hits)
        kb_head = "Knowledge base (most relevant excerpts):"
    else:
        # 全量注入受总字符预算约束：按运营排序（category/sort_order 即权重序）截断，
        # 至少保留首条防空 KB 误报；RAG 分支 top-k 天然有界不设预算
        kb_lines = [f"Q: {f.question}\nA: {f.answer_md}" for f in repo.active_faqs(db)]
        kept: list[str] = []
        used = 0
        for line in kb_lines:
            if kept and used + len(line) > KB_CHAR_BUDGET:
                break
            kept.append(line)
            used += len(line) + 2  # +2 补连接符 \n\n
        kb = "\n\n".join(kept) if kept else "(knowledge base is empty)"
        kb_head = "Knowledge base:"

    facts = "\n".join(filter(None, [_shipping_summary(db, False), _return_summary(db, False)]))

    parts = [persona, SAFETY_RULES]
    if extra:
        parts.append("Additional instructions from the shop owner:\n" + extra)
    parts.append(f"Shop policy digest: {facts}")
    parts.append(f"{kb_head}\n{kb}")
    return "\n\n".join(parts)
