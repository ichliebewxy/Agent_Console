"""Centralized runtime configuration."""
import os
from dotenv import load_dotenv

load_dotenv()


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


CHAT_MODEL = env("CHAT_MODEL", "deepseek-v4-flash")
CHAT_API_KEY = env("CHAT_API_KEY")
CHAT_BASE_URL = env("CHAT_BASE_URL", "https://api.deepseek.com")
GRADE_MODEL = env("GRADE_MODEL", "deepseek-v4-flash")

DASHSCOPE_MCP_API_KEY = env("DASHSCOPE_MCP_API_KEY")
QUERY_EXPANSION_MODEL = env("QUERY_EXPANSION_MODEL", CHAT_MODEL)
AMAP_MCP_ENDPOINT = env("AMAP_MCP_ENDPOINT", "https://dashscope.aliyuncs.com/api/v1/mcps/amap-maps/mcp")

AMAP_WEATHER_API = env("AMAP_WEATHER_API", "https://restapi.amap.com/v3/weather/weatherInfo")
AMAP_API_KEY = env("AMAP_API_KEY")

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
BM25_STATE_PATH = env("BM25_STATE_PATH")
MILVUS_DENSE_DIM = env_int("MILVUS_DENSE_DIM", EMBEDDING_DIM)

AUTO_MERGE_ENABLED = env_bool("AUTO_MERGE_ENABLED", True)
AUTO_MERGE_THRESHOLD = env_int("AUTO_MERGE_THRESHOLD", 2)
LEAF_RETRIEVE_LEVEL = env_int("LEAF_RETRIEVE_LEVEL", 3)

OPENCLI_BIN = env("OPENCLI_BIN")
OPENCLI_SESSION = env("OPENCLI_SESSION", "lcagent")
OPENCLI_TIMEOUT = env_int("OPENCLI_TIMEOUT", 75)
OPENCLI_OUTPUT_MAX_CHARS = env_int("OPENCLI_OUTPUT_MAX_CHARS", 12000)
