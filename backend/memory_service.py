"""mem0 长期记忆服务 — 让主 Agent 具备跨会话的持久记忆（本地存储）。

本模块封装 mem0 (mem0ai 2.0.x) 的 Memory 实例，提供：
- 选择性记忆：只把跨会话仍有价值的用户信息持久化（LLM 抽取，语义去重）。
- 上下文召回：对话开始前按当前问题检索相关记忆，注入 Agent 上下文。
- 手动管理：列出 / 新增 / 更新 / 删除记忆，供前端“记忆”面板调用。

存储全部落在本地 MEM0_DIR（默认 data/mem0）：
- Qdrant 本地模式向量库（语义检索）
- SQLite 历史库（history.db）

注意：mem0 在 import 时会把默认目录建到用户主目录 ~/.mem0，因此必须在
import mem0 之前设置 MEM0_DIR 与 MEM0_TELEMETRY 环境变量，保证“本地化”，
并关闭其默认的 posthog 遥测。
"""

from __future__ import annotations

import os
import re
import threading

from settings import (
    CHAT_API_KEY,
    CHAT_BASE_URL,
    EMBEDDING_DEVICE,
    EMBEDDING_DIM,
    EMBEDDING_LOCAL_FILES_ONLY,
    EMBEDDING_MODEL,
    MEM0_DIR,
    MEM0_MODEL,
    MEM0_TOP_K,
    MEMORY_ENABLED,
)

# —— 必须在 import mem0 之前设定，避免 mem0 把数据写到用户主目录或上报遥测 ——
os.environ.setdefault("MEM0_DIR", str(MEM0_DIR))
os.environ.setdefault("MEM0_TELEMETRY", "False")
os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")

# mem0 的 Memory 采用懒加载：仅在首次真正使用记忆时才 import，
# 避免 mem0 安装失败/配置错误时拖垮整个 FastAPI 启动。

_memory = None
_init_lock = threading.Lock()  # 保证 Memory 只初始化一次（加载本地 BGE 模型较重）
_call_lock = threading.Lock()  # 串行化对 mem0 的调用（Qdrant 本地模式非线程安全）
_initialized = False
_init_error = None


# 这些指令会交给 mem0 的抽取模型做第二道判断。原版默认 prompt
# 会把“正在找一家餐厅”等一次性意图也当作记忆，不符合长期记忆的边界。
LONG_TERM_MEMORY_INSTRUCTIONS = """
Only extract durable, user-specific information that is likely to remain useful in future,
unrelated conversations. Good memories include stable identity/profile facts, enduring
preferences, recurring working habits, accessibility or dietary needs, long-running goals,
and explicit instructions about how the user wants future conversations handled.

Return no facts for the current request, task details, code/content being discussed,
one-off plans, temporary status, recent events, questions, general knowledge, assistant
responses, tool results, or information that is only useful inside the current session.
Never store passwords, API keys, tokens, cookies, private keys, or other credentials.
When durability is uncertain, return an empty facts list. Extract facts only from the user.
""".strip()

_SENSITIVE_MEMORY_RE = re.compile(
    r"(?i)(api[ _-]?key|access[ _-]?token|\btoken\b|authorization|bearer|"
    r"password|passwd|secret|cookie|密码|口令|令牌|密钥|授权码|私钥|助记词)"
)
_EXPLICIT_MEMORY_RE = re.compile(
    r"(?i)(请?记住|请?记下|长期记忆|从今往后|以后.{0,16}(?:都|请|要|不要)|"
    r"remember (?:that|this|my)|from now on|always .{0,24}(?:reply|respond|use|avoid))"
)
_TRANSIENT_MEMORY_RE = re.compile(
    r"(?i)(今天|昨天|明天|刚才|现在|当前|这次|本次|本轮|暂时|临时|"
    r"today|yesterday|tomorrow|right now|currently|this time|temporary|temporarily)"
)
_DURABLE_MEMORY_RE = re.compile(
    r"(?i)("
    r"(?:我|本人)(?:叫|是|住在|来自|从事|任职|喜欢|偏好|习惯|通常|一直|不喜欢|不吃|患有)|"
    r"我的(?:名字|职业|工作|职位|公司|团队|项目|技术栈|母语|时区|所在地|偏好|习惯|长期目标|忌口|过敏)|"
    r"我对.{0,20}过敏|"
    r"(?:回答|回复|输出|报告|代码).{0,20}(?:一律|默认|始终)|"
    r"\b(?:my name is|i am|i'm|i live|i work|i prefer|i like|i dislike|"
    r"i always|i never|i am allergic|i'm allergic)\b"
    r")"
)


def is_long_term_memory_candidate(user_message: str) -> bool:
    """Conservatively decide whether a turn merits long-term extraction.

    Same-session continuity is handled by ``ConversationStorage``; this gate is only for
    cross-session memory. False negatives are preferable to filling memory with task noise.
    """
    text = (user_message or "").strip()
    if not text or _SENSITIVE_MEMORY_RE.search(text):
        return False
    if _EXPLICIT_MEMORY_RE.search(text):
        return True
    if _TRANSIENT_MEMORY_RE.search(text):
        return False
    return bool(_DURABLE_MEMORY_RE.search(text))


def _build_config():
    embedder_kwargs = {"device": EMBEDDING_DEVICE}
    if EMBEDDING_LOCAL_FILES_ONLY:
        embedder_kwargs["model_kwargs"] = {"local_files_only": True}

    return {
        "vector_store": {
            "provider": "qdrant",
            "config": {
                "collection_name": "memories",
                "path": str(MEM0_DIR / "qdrant"),
                "embedding_model_dims": EMBEDDING_DIM,
                "on_disk": True,
            },
        },
        "llm": {
            "provider": "deepseek",
            "config": {
                "model": MEM0_MODEL,
                "api_key": CHAT_API_KEY,
                "deepseek_base_url": CHAT_BASE_URL,
            },
        },
        "embedder": {
            "provider": "huggingface",
            "config": {
                "model": EMBEDDING_MODEL,
                "embedding_dims": EMBEDDING_DIM,
                "model_kwargs": embedder_kwargs,
            },
        },
        "history_db_path": str(MEM0_DIR / "history.db"),
        "version": "v1.1",
        "custom_instructions": LONG_TERM_MEMORY_INSTRUCTIONS,
    }


def init_memory():
    global _memory, _initialized, _init_error
    if _memory is not None:
        return _memory
    with _init_lock:
        if _memory is not None:
            return _memory
        try:
            from mem0 import Memory

            MEM0_DIR.mkdir(parents=True, exist_ok=True)
            # 本地化加载 BGE 模型时临时强制离线，避免 sentence-transformers
            # 加载时向 HF Hub 发起 HEAD 请求导致反复超时重试。加载完恢复原值。
            prev_offline = os.environ.get("HF_HUB_OFFLINE")
            if EMBEDDING_LOCAL_FILES_ONLY:
                os.environ["HF_HUB_OFFLINE"] = "1"
            try:
                _memory = Memory.from_config(config_dict=_build_config())
            finally:
                if prev_offline is None:
                    os.environ.pop("HF_HUB_OFFLINE", None)
                else:
                    os.environ["HF_HUB_OFFLINE"] = prev_offline
            _initialized = True
        except Exception as exc:
            _init_error = exc
            raise
    return _memory


def is_enabled():
    return MEMORY_ENABLED


def status():
    return {
        "enabled": MEMORY_ENABLED,
        "initialized": _initialized,
        "dir": str(MEM0_DIR),
        "model": MEM0_MODEL,
        "error": str(_init_error) if _init_error else None,
    }


def search_for_context(query, user_id, top_k=None):
    memory = init_memory()
    limit = top_k or MEM0_TOP_K
    with _call_lock:
        result = memory.search(query, filters={"user_id": user_id}, top_k=limit)
    return [
        item.get("memory", "")
        for item in result.get("results", [])
        if item.get("memory")
    ]


def get_all(user_id, top_k=100):
    memory = init_memory()
    with _call_lock:
        result = memory.get_all(filters={"user_id": user_id}, top_k=top_k)
    return list(result.get("results", []))


def add_memory(text, user_id, metadata=None, infer=False):
    memory = init_memory()
    with _call_lock:
        result = memory.add(
            [{"role": "user", "content": text}],
            user_id=user_id,
            metadata=metadata,
            infer=infer,
        )
    return result


def remember_conversation(user_id, user_message, session_id=None):
    if not is_long_term_memory_candidate(user_message):
        return {"results": [], "skipped": True, "reason": "not_long_term"}

    memory = init_memory()
    # 长期记忆只描述用户；Agent 回复只属于当前会话上下文。
    messages = [{"role": "user", "content": user_message}]
    metadata = {"source": "automatic", "scope": "long_term"}
    if session_id:
        metadata["session_id"] = session_id
    with _call_lock:
        result = memory.add(messages, user_id=user_id, metadata=metadata, infer=True)
    return result


def update_memory(memory_id, text):
    memory = init_memory()
    with _call_lock:
        return memory.update(memory_id, text=text)


def delete_memory(memory_id):
    memory = init_memory()
    with _call_lock:
        return memory.delete(memory_id)


def delete_all(user_id):
    memory = init_memory()
    with _call_lock:
        return memory.delete_all(user_id=user_id)
