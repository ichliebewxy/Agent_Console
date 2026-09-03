"""Centralized runtime configuration."""
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def env(name: str, default: str = "") -> str:
    return (os.getenv(name, default) or "").strip()


def env_bool(name: str, default: bool = False) -> bool:
    value = env(name)
    if not value:
        return default
    return value.lower() in {"1", "true", "yes", "on"}


def env_int(name: str, default: int) -> int:
    try:
        return int(env(name, str(default)))
    except ValueError:
        return default


def env_path(name: str, default: Path) -> Path:
    configured = env(name)
    path = Path(configured).expanduser() if configured else default
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return path.resolve()


CHAT_MODEL = env("CHAT_MODEL", "deepseek-v4-flash")
CHAT_API_KEY = env("CHAT_API_KEY")
CHAT_BASE_URL = env("CHAT_BASE_URL", "https://api.deepseek.com")
GRADE_MODEL = env("GRADE_MODEL", "deepseek-v4-flash")

QUERY_EXPANSION_MODEL = env("QUERY_EXPANSION_MODEL", CHAT_MODEL)

MILVUS_HOST = env("MILVUS_HOST", "127.0.0.1")
MILVUS_PORT = env("MILVUS_PORT", "19530")
MILVUS_COLLECTION = env("MILVUS_COLLECTION", "embeddings_bge_m3")
MILVUS_TIMEOUT = env_int("MILVUS_TIMEOUT", 8)

RERANK_MODEL = env("RERANK_MODEL")
RERANK_BINDING_HOST = env("RERANK_BINDING_HOST")
RERANK_API_KEY = env("RERANK_API_KEY")

EMBEDDING_MODEL = env("EMBEDDING_MODEL", "BAAI/bge-m3")
EMBEDDING_DEVICE = env("EMBEDDING_DEVICE", "cpu")
EMBEDDING_DIM = env_int("EMBEDDING_DIM", 1024)
EMBEDDING_BATCH_SIZE = env_int("EMBEDDING_BATCH_SIZE", 16)
# 置为 true 时，嵌入模型只从本地缓存加载，绝不联网下载。
# 先运行 `python -m backend.preload_embedding_model` 一次性下载完成后再开启。
EMBEDDING_LOCAL_FILES_ONLY = env_bool("EMBEDDING_LOCAL_FILES_ONLY", False)
BM25_STATE_PATH = env("BM25_STATE_PATH")
MILVUS_DENSE_DIM = env_int("MILVUS_DENSE_DIM", EMBEDDING_DIM)

AUTO_MERGE_ENABLED = env_bool("AUTO_MERGE_ENABLED", True)
AUTO_MERGE_THRESHOLD = env_int("AUTO_MERGE_THRESHOLD", 2)
LEAF_RETRIEVE_LEVEL = env_int("LEAF_RETRIEVE_LEVEL", 3)

# ===== mem0 长期记忆（本地持久化）=====
# 侧车记忆面板的启用状态；Pi 的会话记忆由 pi-memory 插件负责。
MEMORY_ENABLED = env_bool("MEMORY_ENABLED", True)
# 本地记忆数据目录（Qdrant 向量库 + SQLite 历史库）。相对路径基于项目根。
MEM0_DIR = env_path("MEM0_DIR", PROJECT_ROOT / "tmp" / "mem0")
# 用于 mem0 事实抽取/检索重排的对话模型（默认复用主聊天模型）。
MEM0_MODEL = env("MEM0_MODEL", CHAT_MODEL)
