"""聊天域自测 —— 三渠道会话（AI 规则/LLM 分流、人工转接、美甲师）+ 前后台流转 + 归属核验
（MySQL scratch 库 glowmag_test_w 共用惯例同 test_ai_ext/test_worker，DROP 重建）"""

import os
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))
os.chdir(BASE)

import pymysql

_cn = pymysql.connect(host="127.0.0.1", user="glowmag", password="glowmag123")
with _cn.cursor() as _cur:
    _cur.execute("DROP DATABASE IF EXISTS glowmag_test_w")
    _cur.execute("CREATE DATABASE glowmag_test_w CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci")
_cn.close()
os.environ["GM_DB"] = "mysql+pymysql://glowmag:glowmag123@127.0.0.1:3306/glowmag_test_w?charset=utf8mb4"
os.environ["GM_COOKIE_AUTH"] = "0"

from fastapi.testclient import TestClient  # noqa: E402

from app.core.db import SessionLocal, init_db  # noqa: E402
from app.core.enums import UserRole  # noqa: E402
from app.core.security import create_token, hash_password  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Faq, Setting, User  # noqa: E402

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


init_db()
db = SessionLocal()

for k, v in [("free_shipping_threshold", 3500), ("shipping_standard", 499),
             ("shipping_express", 1499), ("return_days", 30)]:
    db.add(Setting(key=k, value=v))
for cat, q, a in [
    (1, "How do I find my nail size?", "Use the interactive sizer or printable chart."),
    (3, "When will my order ship?", "Packed within 24h, delivered in 3-6 business days (US)."),
    (4, "What's your return policy?", "30-day window on unopened sets."),
]:
    db.add(Faq(category=cat, question=q, answer_md=a, sort_order=1))

ops = User(email="ops@glowmag.test", password_hash=hash_password("x"), name="Ops Agent",
           role=int(UserRole.OPS), email_verified_at=None)
artist = User(email="mia@glowmag.test", password_hash=hash_password("x"), name="Mia Chen",
              role=int(UserRole.ARTIST), artist_intro="法式与裸色系专精")
db.add_all([ops, artist])
db.commit()
H_OPS = {"Authorization": f"Bearer {create_token(ops.id, ops.role)}"}
H_ARTIST = {"Authorization": f"Bearer {create_token(artist.id, artist.role)}"}
db.close()

client = TestClient(app)
TOK = "guest-token-0001"
TOK2 = "guest-token-0002"

# ---- AI 会话：创建即欢迎语 ----
r = client.post("/api/chat/conversations", json={"channel": 0, "token": TOK, "lang": "en"})
j = r.json()
check("AI 会话创建 200 且含欢迎 bot 消息",
      r.status_code == 200 and j["channel"] == 0
      and [m for m in j["messages"] if m["sender"] == 4], r.text[:200])
AI_NO = j["conv_no"]

r = client.post("/api/chat/conversations", json={"channel": 0, "token": TOK})
check("重复创建复用同一进行中会话", r.json()["conv_no"] == AI_NO)

r = client.post("/api/chat/conversations", json={"channel": 9, "token": TOK})
check("非法 channel 422", r.status_code == 422)
r = client.post("/api/chat/conversations", json={"channel": 0, "token": "abc"})
check("非法 token 422", r.status_code == 422)

# ---- AI 规则引擎回复（LLM 未配置）----
r = client.post(f"/api/chat/conversations/{AI_NO}/messages",
                json={"token": TOK, "content": "How much is shipping? free over 35?"})
j = r.json()
bot_msgs = [m for m in j["new_messages"] if m["sender"] == 4]
check("shipping 问题走规则引擎（source=rules）并命中 $35 门槛",
      r.status_code == 200 and j["source"] == "rules" and bot_msgs
      and "$35.00" in bot_msgs[-1]["content"], r.text[:200])

# ---- LLM 分流：patch llm 客户端 ----
from app.services import llm as llm_mod  # noqa: E402

_orig_cc = llm_mod.chat_completion
try:
    llm_mod.chat_completion = lambda system, messages, temperature=0.4, params=None: (
        "LLM-KB-ANSWER: try Short Almond for short nail beds!"
    )
    r = client.post(f"/api/chat/conversations/{AI_NO}/messages",
                    json={"token": TOK, "content": "which shape suits short nail beds?"})
    j = r.json()
    check("非订单类问题命中 LLM（source=llm 且内容为 LLM 回复）",
          j["source"] == "llm" and j["new_messages"][-1]["sender"] == 4
          and j["new_messages"][-1]["content"].startswith("LLM-KB-ANSWER"), r.text[:200])

    # LLM 故障 → 回退规则引擎
    llm_mod.chat_completion = lambda system, messages, temperature=0.4, params=None: None
    r = client.post(f"/api/chat/conversations/{AI_NO}/messages",
                    json={"token": TOK, "content": "what is your return policy?"})
    j = r.json()
    check("LLM 失败回退规则引擎（source=rules 且含 30 天）",
          j["source"] == "rules" and "30-day" in j["new_messages"][-1]["content"])
finally:
    llm_mod.chat_completion = _orig_cc

# ---- 订单类意图固定规则引擎（LLM 开着也不走）----
try:
    llm_mod.chat_completion = lambda system, messages, temperature=0.4, params=None: "HACKED-LLM"
    r = client.post(f"/api/chat/conversations/{AI_NO}/messages",
                    json={"token": TOK, "content": "track my order NS999999ZZZZ01"})
    j = r.json()
    check("订单类意图固定走规则引擎（LLM 不接管）",
          j["source"] == "rules" and j["new_messages"][-1]["content"] != "HACKED-LLM")
finally:
    llm_mod.chat_completion = _orig_cc

# ---- 转人工：游客无邮箱 → 引导补邮箱；escalate 补邮箱后升级 ----
r = client.post(f"/api/chat/conversations/{AI_NO}/messages",
                json={"token": TOK, "content": "I want to talk to a human agent please"})
j = r.json()
check("human 意图无邮箱 → escalated 提示 + bot 引导补邮箱（渠道不变）",
      j["escalated"] and j["channel"] == 0
      and "email" in j["new_messages"][-1]["content"].lower(), r.text[:200])

r = client.post(f"/api/chat/conversations/{AI_NO}/escalate",
                json={"token": TOK, "email": "guest@glowmag.test", "name": "Guest One"})
j = r.json()
check("escalate 带邮箱 → 渠道升级人工且记录保留",
      r.status_code == 200 and j["channel"] == 1 and j["email"] == "guest@glowmag.test"
      and len(j["messages"]) >= 4, r.text[:200])

r = client.post(f"/api/chat/conversations/{AI_NO}/messages",
                json={"token": TOK, "content": "hello anyone there?"})
j = r.json()
check("升级后客户发言不再触发 AI 回复（new_messages 仅客户条）",
      r.status_code == 200 and [m for m in j["new_messages"] if m["sender"] == 4] == [])

# ---- 人工会话：邮箱必填 ----
r = client.post("/api/chat/conversations", json={"channel": 1, "token": TOK2})
check("人工渠道游客无邮箱 422", r.status_code == 422)
r = client.post("/api/chat/conversations",
                json={"channel": 1, "token": TOK2, "email": "h@glowmag.test", "name": "Hana"})
j = r.json()
check("人工会话创建含等待接入系统消息",
      r.status_code == 200 and any(m["sender"] == 3 for m in j["messages"]))
HUMAN_NO = j["conv_no"]

# ---- 美甲师：列表 / 会话 / 回复身份 ----
r = client.get("/api/chat/artists")
items = r.json()["items"]
check("美甲师公开列表只含 role=4（含简介不含邮箱）",
      r.status_code == 200 and len(items) == 1 and items[0]["name"] == "Mia Chen"
      and "intro" in items[0] and "email" not in items[0], r.text[:200])

r = client.post("/api/chat/conversations",
                json={"channel": 2, "token": TOK2, "email": "h@glowmag.test",
                      "artist_id": items[0]["id"]})
j = r.json()
check("美甲师会话创建（系统消息含美甲师姓名）",
      r.status_code == 200 and j["channel"] == 2
      and any("Mia Chen" in m["content"] for m in j["messages"]), r.text[:200])
ART_NO = j["conv_no"]

r = client.post(f"/api/chat/conversations/{ART_NO}/messages",
                json={"token": TOK2, "content": "婚礼想定制法式带珍珠可以吗？"})
check("美甲师会话客户发言 200", r.status_code == 200)

# ---- 归属核验：错误 token 403 ----
r = client.get(f"/api/chat/conversations/{HUMAN_NO}/messages", params={"token": "wrong-token-xxx"})
check("错误 token 读会话 403", r.status_code == 403)

# ---- 后台工作台 ----
r = client.get("/api/admin/chat/conversations", headers=H_OPS, params={"channel": 1, "status": 0})
j = r.json()
check("后台人工会话列表（红点=客户待回复）",
      r.status_code == 200 and j["total"] >= 2
      and any(it["pending_reply"] for it in j["items"]), r.text[:300])

r = client.post(f"/api/admin/chat/conversations/{HUMAN_NO}/take", headers=H_OPS)
j = r.json()
check("接单绑定客服 + 客户侧系统消息", j.get("agent_admin_id") == ops.id
      and any("Ops Agent" in m["content"] for m in j["messages"]))

r = client.post(f"/api/admin/chat/conversations/{HUMAN_NO}/reply", headers=H_OPS,
                json={"content": "在的～请讲"})
j = r.json()
check("客服回复 sender=2 且带姓名", j["messages"][-1]["sender"] == 2
      and j["messages"][-1]["sender_name"] == "Ops Agent")

r = client.post(f"/api/admin/chat/conversations/{ART_NO}/reply", headers=H_ARTIST,
                json={"content": "可以呀！先帮你量个甲片尺寸～"})
j = r.json()
check("美甲师本人回复 sender=5",
      j["messages"][-1]["sender"] == 5 and j["messages"][-1]["sender_name"] == "Mia Chen")

r = client.post(f"/api/admin/chat/conversations/{ART_NO}/reply", headers=H_OPS,
                json={"content": "代答一条"})
check("运营代答美甲师会话仍记 sender=2", r.json()["messages"][-1]["sender"] == 2)

# mine 过滤：美甲师登录只见自己的会话
r = client.get("/api/admin/chat/conversations", headers=H_ARTIST, params={"mine": 1})
j = r.json()
check("mine=1 美甲师只见本人会话",
      j["total"] == 1 and j["items"][0]["conv_no"] == ART_NO, r.text[:200])

# ---- 合并客服：AI/人工同一会话内部切换（0↔1） ----
TOK3 = "guest-token-0003"
r = client.post("/api/chat/conversations", json={"channel": 0, "token": TOK3})
MERGED_NO = r.json()["conv_no"]
r = client.post(f"/api/chat/conversations/{MERGED_NO}/messages",
                json={"token": TOK3, "content": "hi there"})
pre_count = len(r.json()["messages"])

r = client.post("/api/chat/conversations",
                json={"channel": 1, "token": TOK3, "email": "g3@glowmag.test"})
j = r.json()
check("人工请求复用进行中 AI 会话（同 conv_no 原地升级、记录保留）",
      j["conv_no"] == MERGED_NO and j["channel"] == 1 and len(j["messages"]) >= pre_count + 2,
      r.text[:200])

r = client.post("/api/chat/conversations", json={"channel": 0, "token": TOK3})
j = r.json()
check("人工会话进行中不再开平行 AI 会话（start 0 复用人工会话）",
      j["conv_no"] == MERGED_NO and j["channel"] == 1, r.text[:150])

r = client.post(f"/api/admin/chat/conversations/{MERGED_NO}/resume-ai", headers=H_OPS)
j = r.json()
check("后台转回 AI（channel 1→0 + 系统提示）",
      j["channel"] == 0 and any("GlowBot" in m["content"] for m in j["messages"][-2:]),
      r.text[:200])

r = client.post(f"/api/chat/conversations/{MERGED_NO}/messages",
                json={"token": TOK3, "content": "how long does shipping take?"})
j = r.json()
check("转回 AI 后 GlowBot 恢复自动回复",
      [m for m in j["new_messages"] if m["sender"] == 4], r.text[:200])

r = client.post(f"/api/admin/chat/conversations/{MERGED_NO}/reply", headers=H_OPS,
                json={"content": "人工补充说明一下"})
j = r.json()
check("客服在 AI 会话直接回复 → 自动转人工（channel=1 + 接入提示）",
      j["channel"] == 1 and any("Ops Agent" in m["content"] for m in j["messages"]),
      r.text[:200])

# 客户侧轮询可见客服/美甲师消息
r = client.get(f"/api/chat/conversations/{HUMAN_NO}/messages", params={"token": TOK2})
j = r.json()
check("客户轮询可见客服回复", any(m["sender"] == 2 for m in j["messages"]))

# 关闭：客户主动结束 + 后台再关 409
r = client.post(f"/api/chat/conversations/{HUMAN_NO}/close", json={"token": TOK2})
check("客户关闭会话 200 且状态=1", r.status_code == 200 and r.json()["status"] == 1)
r = client.post(f"/api/admin/chat/conversations/{HUMAN_NO}/close", headers=H_OPS)
check("重复关闭 409", r.status_code == 409)
r = client.post(f"/api/chat/conversations/{HUMAN_NO}/messages",
                json={"token": TOK2, "content": "still there?"})
check("已关闭会话拒收消息 409", r.status_code == 409)

# 权限：未登录访问后台聊天 401
r = client.get("/api/admin/chat/conversations")
check("后台聊天未登录 401", r.status_code == 401)

# ---- 快捷模板管理 CRUD（后台维护，工单/聊天工作台共用） ----
r = client.get("/api/admin/ops/templates", headers=H_OPS)
base_total = len((r.json() or {}).get("items", [])) if r.status_code == 200 else 0
check("模板列表 200", r.status_code == 200 and isinstance(base_total, int), r.text[:100])

r = client.post("/api/admin/ops/templates", headers=H_OPS,
                json={"category": 1, "title": "测试模板", "content": "您好，这是测试内容～", "active": 1})
j = r.json()
check("新增模板 200", r.status_code == 200 and j.get("id"), r.text[:150])
TPL_ID = j.get("id")

r = client.put(f"/api/admin/ops/templates/{TPL_ID}", headers=H_OPS,
               json={"category": 3, "title": "测试模板改", "content": "内容已改", "active": 0})
check("修改模板 200（含停用）", r.status_code == 200 and r.json().get("active") == 0)

r = client.get("/api/support/templates")
active_ids = [t["id"] for t in (r.json() or [])]
check("停用模板不再出现在公开列表", r.status_code == 200 and TPL_ID not in active_ids)

r = client.delete(f"/api/admin/ops/templates/{TPL_ID}", headers=H_OPS)
check("删除模板 200", r.status_code == 200 and r.json().get("ok") is True)
r = client.put(f"/api/admin/ops/templates/{TPL_ID}", headers=H_OPS,
               json={"category": 1, "title": "x", "content": "x", "active": 1})
check("删除后更新 404", r.status_code == 404)
r = client.post("/api/admin/ops/templates", headers=H_OPS,
                json={"category": 9, "title": "x", "content": "x"})
check("非法分类 422", r.status_code == 422)

# ---- 客户快捷问题配置（结构化：文案 + 动作 ask/link/human + 站内 url 校验） ----
r = client.get("/api/chat/quicks")
j = r.json()
check("公开 quicks 默认配置（含动作字段）",
      r.status_code == 200 and isinstance(j.get("zh"), list)
      and all("text" in x and "action" in x for x in j["zh"]) and len(j["zh"]) > 0, r.text[:150])

r = client.put("/api/admin/chat/quicks", headers=H_OPS, json={
    "zh": [
        {"text": "📦 查订单", "action": "ask"},
        {"text": "📖 退换政策", "action": "link", "url": "/returns-policy"},
        {"text": "👩‍💼 转人工", "action": "human"},
        {"text": "🚚 运费", "action": "link", "url": "https://evil.com"},  # 外链 → 降级 ask
    ],
    "en": [{"text": "Where is my order?", "action": "ask"}],
})
j = r.json()
check("保存结构化 quicks 200（link 保留 / human 保留）",
      r.status_code == 200 and j["zh"][1]["action"] == "link"
      and j["zh"][1]["url"] == "/returns-policy" and j["zh"][2]["action"] == "human", r.text[:200])
check("外链 url 被降级为 ask（防开放重定向）",
      j["zh"][3]["action"] == "ask" and "url" not in j["zh"][3])

r = client.get("/api/chat/quicks")
check("公开端点读回自定义配置",
      r.json()["zh"][0]["text"] == "📦 查订单")

r = client.get("/api/admin/chat/quicks", headers=H_OPS)
j = r.json()
check("管理端读取含 customized 与审计信息",
      j.get("customized") is True and j.get("updated_by") and j.get("updated_at"), r.text[:200])

r = client.put("/api/admin/chat/quicks", headers=H_OPS,
               json={"zh": [{"text": " ", "action": "ask"}], "en": []})
check("全空文本整语言被拒 422", r.status_code == 422)
r = client.put("/api/admin/chat/quicks", headers=H_OPS, json={"zh": "not-a-list"})
check("非列表 422", r.status_code == 422)

r = client.post("/api/admin/chat/quicks/reset", headers=H_OPS)
check("恢复默认 200（含默认转人工项）",
      r.status_code == 200 and any(x["action"] == "human" for x in r.json()["zh"]))
r = client.get("/api/admin/chat/quicks", headers=H_OPS)
check("reset 后 customized 回 False", r.json().get("customized") is False)

# 兼容：旧纯字符串数组读归一
from app.models import Setting as SettingModel  # noqa: E402
db2 = SessionLocal()
try:
    row = db2.query(SettingModel).filter(SettingModel.key == "chat_quick_replies").first()
    if row:
        row.value = {"zh": ["旧格式问题"], "en": ["legacy?"]}
    else:
        db2.add(SettingModel(key="chat_quick_replies", value={"zh": ["旧格式问题"], "en": ["legacy?"]}))
    db2.commit()
    r = client.get("/api/chat/quicks")
    j = r.json()
    check("旧纯字符串数组兼容归一为 ask 动作",
          j["zh"][0]["text"] == "旧格式问题" and j["zh"][0]["action"] == "ask")
finally:
    db2.close()

# ---- AI 大模型配置（settings key=llm_config，覆盖 GM_LLM_* 环境变量） ----
import json  # noqa: E402

r = client.get("/api/admin/ai/config", headers=H_OPS)
j = r.json()
check("AI 配置读取（未配置态：key 未设置 + source 空）",
      r.status_code == 200 and j["api_key_set"] is False
      and j["api_key_masked"] == "" and j["source"] == "", r.text[:150])
check("默认模型/端点来自 env 兜底",
      j["model"] == "gpt-4o-mini" and j["base_url"].startswith("http"), r.text[:150])

r = client.post("/api/admin/ai/test", headers=H_OPS)
j = r.json()
check("未配置 Key 时测试返回明确原因（ok=False）",
      j["ok"] is False and "API Key" in j["reason"], r.text[:150])

r = client.put("/api/admin/ai/config", headers=H_OPS, json={
    "api_key": "sk-test-1234567890abcdefwxyz",
    "base_url": "https://llm.example.com/v1",
    "model": "glm-4-flash",
    "timeout": 15, "max_tokens": 300,
})
j = r.json()
check("保存 AI 配置 200", r.status_code == 200 and j.get("ok") is True, r.text[:150])

r = client.get("/api/admin/ai/config", headers=H_OPS)
j = r.json()
check("读回生效配置（Key 脱敏 + source=db + 字段覆盖）",
      j["api_key_set"] is True and j["api_key_masked"].startswith("sk-")
      and "***" in j["api_key_masked"] and j["api_key_masked"].endswith("wxyz")
      and j["source"] == "db" and j["model"] == "glm-4-flash"
      and j["timeout"] == 15 and j["max_tokens"] == 300, r.text[:200])
check("明文 Key 不回传（脱敏后不含完整密钥）",
      "1234567890" not in json.dumps(j))

r = client.put("/api/admin/ai/config", headers=H_OPS, json={"base_url": "ftp://bad"})
check("非法 base_url 422", r.status_code == 422)
r = client.put("/api/admin/ai/config", headers=H_OPS, json={"timeout": 999})
check("timeout 超界 422", r.status_code == 422)
r = client.put("/api/admin/ai/config", headers=H_OPS, json={"model": " "})
check("空 model 422", r.status_code == 422)

# resolve_params 合并优先级：DB > env
from app.services import llm as llm_svc  # noqa: E402
db3 = SessionLocal()
try:
    p = llm_svc.resolve_params(db3)
    check("resolve_params DB 覆盖 env（api_key/model/base_url）",
          p["api_key"] == "sk-test-1234567890abcdefwxyz"
          and p["model"] == "glm-4-flash"
          and p["base_url"] == "https://llm.example.com/v1")
    check("llm_available 以生效配置判定", llm_svc.llm_available(p) is True)
finally:
    db3.close()

# 测试端点走真实 httpx → 指向不可达网关应优雅失败（ok=False + latency）
r = client.post("/api/admin/ai/test", headers=H_OPS)
j = r.json()
check("连通测试失败优雅返回（不 5xx）",
      r.status_code == 200 and j["ok"] is False and "latency_ms" in j, r.text[:150])

# 清除 Key：api_key 空串 → 回到未配置态
r = client.put("/api/admin/ai/config", headers=H_OPS, json={"api_key": ""})
check("清除 Key 200", r.status_code == 200)
r = client.get("/api/admin/ai/config", headers=H_OPS)
check("清除后回到未配置态（source 空）", r.json()["api_key_set"] is False and r.json()["source"] == "")

# ---- 提示词配置（persona/prompt_extra/temperature + 最终提示词预览） ----
r = client.get("/api/admin/ai/prompt-preview", headers=H_OPS)
j = r.json()
check("默认提示词预览（默认人设 + 安全红线 + FAQ 注入）",
      r.status_code == 200 and "GlowBot" in j["prompt"] and "Rules:" in j["prompt"]
      and "Knowledge base:" in j["prompt"] and "Q:" in j["prompt"], r.text[:200])

r = client.put("/api/admin/ai/config", headers=H_OPS, json={
    "persona": "你是小美，GLOWMAG 的资深美甲顾问，语气俏皮。",
    "prompt_extra": "大促期间主动提醒满 $35 免邮。",
    "temperature": 0.7,
})
check("保存提示词配置 200", r.status_code == 200)

r = client.get("/api/admin/ai/config", headers=H_OPS)
j = r.json()
check("读回提示词配置（persona/extra/temperature）",
      "小美" in (j["persona"] or "") and "免邮" in (j["prompt_extra"] or "") and j["temperature"] == 0.7, r.text[:200])

r = client.get("/api/admin/ai/prompt-preview", headers=H_OPS)
j = r.json()
check("预览含自定义人设与补充指令（且安全红线仍在）",
      "小美" in j["prompt"] and "免邮" in j["prompt"]
      and "Never invent order status" in j["prompt"], r.text[:200])

r = client.put("/api/admin/ai/config", headers=H_OPS, json={"temperature": 5})
check("temperature 超界 422", r.status_code == 422)
r = client.put("/api/admin/ai/config", headers=H_OPS, json={"persona": "x" * 501})
check("persona 超长 422", r.status_code == 422)

# resolve_params 生效温度；置空 persona 回默认人设
db4 = SessionLocal()
try:
    p = llm_svc.resolve_params(db4)
    check("temperature 配置生效（0.7）", p["temperature"] == 0.7)
finally:
    db4.close()
r = client.put("/api/admin/ai/config", headers=H_OPS, json={"persona": "", "prompt_extra": "", "temperature": 0.4})
check("重置提示词配置 200", r.status_code == 200)
r = client.get("/api/admin/ai/prompt-preview", headers=H_OPS)
check("置空后回到默认人设", "GlowBot" in r.json()["prompt"] and "小美" not in r.json()["prompt"])

# ---- RAG：FAQ 向量检索 top-k 注入（patch embedding 服务） ----
from app.domains.chat import retrieval as rag_mod  # noqa: E402
from app.services import embedding as emb_mod  # noqa: E402

_orig_embed = rag_mod.embed_texts
_orig_embed_svc = emb_mod.embed_texts
try:
    # 确定性向量：SHIPPINGTEST 文本 → [1,0]，SIZINGTEST → [0,1]，query 同规则
    def _fake_embed(texts, params=None):
        return [[1.0, 0.0] if ("SHIPPINGTEST" in t or "how long shipping" in t) else [0.0, 1.0] for t in texts]

    # 未配 Key：reindex 拒绝 + rag 未就绪（全量注入）
    r = client.post("/api/admin/ai/rag/reindex", headers=H_OPS, json={})
    j = r.json()
    check("未配 Key 时 reindex 明确拒绝", j["ok"] is False and "API Key" in j["reason"], r.text[:150])

    # 配 Key + 先 patch（保存钩子实时向量化）+ 建两条带标记的 FAQ
    r = client.put("/api/admin/ai/config", headers=H_OPS, json={
        "api_key": "sk-rag-test-000111222", "embedding_model": "text-embedding-3-small"})
    check("配 Key（RAG 前置）200", r.status_code == 200)
    rag_mod.embed_texts = _fake_embed
    emb_mod.embed_texts = _fake_embed  # 保存钩子函数内 import embedding 模块，双 patch 覆盖
    r = client.post("/api/admin/ops/faqs", headers=H_OPS,
                    json={"category": 3, "question": "SHIPPINGTEST how fast?", "answer_md": "3-5 days.", "sort_order": 1})
    sid1 = r.json()["id"]
    r = client.post("/api/admin/ops/faqs", headers=H_OPS,
                    json={"category": 1, "question": "SIZINGTEST which size?", "answer_md": "Measure your nail bed.", "sort_order": 2})
    sid2 = r.json()["id"]

    # 增量补建：seed 旧 FAQ 未索引（coverage 2/5 不足）→ 补建后 100%
    r = client.post("/api/admin/ai/rag/reindex", headers=H_OPS, json={})
    j = r.json()
    check("增量补建索引（只补缺失的 seed 行）",
          j["ok"] is True and j["indexed"] >= 1 and j["failed"] == 0, r.text[:200])

    db5 = SessionLocal()
    try:
        st = rag_mod.rag_status(db5)
        check("RAG 状态就绪（coverage 100%）",
              st["ready"] is True and st["total"] >= 2 and st["embedded"] == st["total"], str(st))
    finally:
        db5.close()

    # 检索注入：问 shipping → 只含 SHIPPINGTEST 片段，不含 SIZINGTEST
    r = client.get("/api/admin/ai/prompt-preview", headers=H_OPS,
                   params={"q": "how long shipping takes?"})
    j = r.json()
    check("RAG 命中：prompt 含相关片段 + 头标记",
          j["rag"] is True and "SHIPPINGTEST" in j["prompt"]
          and "most relevant excerpts" in j["prompt"], j["prompt"][:200])
    check("RAG 注入排除不相关 FAQ", "SIZINGTEST" not in j["prompt"])

    # 无命中（query 向量都不相关）→ 回退全量
    r = client.get("/api/admin/ai/prompt-preview", headers=H_OPS, params={"q": "SIZINGTEST which size?"})
    j = r.json()
    check("RAG 命中尺码片段（同样只注入相关的）",
          "SIZINGTEST" in j["prompt"] and "SHIPPINGTEST" not in j["prompt"], j["prompt"][:200])

    # 查询向量化失败 → 回退全量（两条都在）
    rag_mod.embed_texts = lambda texts, params=None: None
    r = client.get("/api/admin/ai/prompt-preview", headers=H_OPS, params={"q": "how long shipping takes?"})
    j = r.json()
    check("查询向量化失败回退全量注入（两条 FAQ 均在）",
          "SHIPPINGTEST" in j["prompt"] and "SIZINGTEST" in j["prompt"])

    # reindex 全量重建（换模型场景）：patch 恢复，清空向量后重建
    rag_mod.embed_texts = _fake_embed
    db6 = SessionLocal()
    try:
        from app.models import Faq as FaqModel
        db6.query(FaqModel).filter(FaqModel.id.in_([sid1, sid2])).update({FaqModel.embedding: None}, synchronize_session=False)
        db6.commit()
    finally:
        db6.close()
    r = client.post("/api/admin/ai/rag/reindex", headers=H_OPS, json={"full": True})
    j = r.json()
    check("全量重建索引 200（indexed=全部 active）",
          j["ok"] is True and j["indexed"] >= 2 and j["failed"] == 0, r.text[:200])
    r = client.get("/api/admin/ai/prompt-preview", headers=H_OPS, params={"q": "how long shipping takes?"})
    check("重建后检索恢复", "SHIPPINGTEST" in r.json()["prompt"] and "SIZINGTEST" not in r.json()["prompt"])

    # embedding_model 超长 422
    r = client.put("/api/admin/ai/config", headers=H_OPS, json={"embedding_model": "m" * 101})
    check("embedding_model 超长 422", r.status_code == 422)
finally:
    rag_mod.embed_texts = _orig_embed
    emb_mod.embed_texts = _orig_embed_svc
    # 清理：删标记 FAQ、清 Key、失效缓存
    try:
        client.delete(f"/api/admin/ops/faqs/{sid1}", headers=H_OPS)
        client.delete(f"/api/admin/ops/faqs/{sid2}", headers=H_OPS)
    except Exception:
        pass
    client.put("/api/admin/ai/config", headers=H_OPS, json={"api_key": "", "embedding_model": ""})
    rag_mod.invalidate()

print(f"\nALL PASS: {PASSED}/{PASSED + len(FAILED)}")
if FAILED:
    print("FAILED:", FAILED)
    sys.exit(1)
