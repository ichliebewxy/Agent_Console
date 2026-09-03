"""mem0 记忆管理侧车，保留已有数据与前端记忆面板的 CRUD 接口。

本模块封装 mem0 (mem0ai 2.0.x) 的 Memory 实例，提供：
- 手动管理：列出 / 新增 / 更新 / 删除记忆，供前端“记忆”面板调用。
- 新增时可选择通过 LLM 抽取事实；Pi 会话记忆由独立的 pi-memory 插件负责。

存储全部落在本地 MEM0_DIR（默认 tmp/mem0）：
- Qdrant 本地模式向量库（语义检索）
- SQLite 历史库（history.db）

注意：mem0 在 import 时会把默认目录建到用户主目录 ~/.mem0，因此必须在
import mem0 之前设置 MEM0_DIR 与 MEM0_TELEMETRY 环境变量，保证“本地化”，
并关闭其默认的 posthog 遥测。
"""

from __future__ import annotations

import os
import threading

from backend.config.settings import (
    CHAT_API_KEY,
    CHAT_BASE_URL,
    EMBEDDING_DEVICE,
    EMBEDDING_DIM,
    EMBEDDING_LOCAL_FILES_ONLY,
    EMBEDDING_MODEL,
    MEM0_DIR,
    MEM0_MODEL,
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
    }


def init_memory():
    global _memory, _initialized, _init_error
    if _memory is not None:
        return _memory
    with _init_lock:
        if _memory is not None:
            return _memory
        try:
            from mem0 import Memory  # noqa: PLC0415

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
