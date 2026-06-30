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

DASHSCOPE_MCP_API_KEY = env("DASHSCOPE_MCP_API_KEY")
DASHSCOPE_EMBEDDING_API_KEY = env("DASHSCOPE_EMBEDDING_API_KEY") or env("ARK_API_KEY")
DASHSCOPE_BASE_URL = env("DASHSCOPE_BASE_URL", env("BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1"))
DASHSCOPE_EMBEDDING_MODEL = env("DASHSCOPE_EMBEDDING_MODEL", env("EMBEDDER", "text-embedding-v3"))
QUERY_EXPANSION_MODEL = env("QUERY_EXPANSION_MODEL", CHAT_MODEL)
AMAP_MCP_ENDPOINT = env("AMAP_MCP_ENDPOINT", "https://dashscope.aliyuncs.com/api/v1/mcps/amap-maps/mcp")

AMAP_WEATHER_API = env("AMAP_WEATHER_API", "https://restapi.amap.com/v3/weather/weatherInfo")
AMAP_API_KEY = env("AMAP_API_KEY")

MILVUS_HOST = env("MILVUS_HOST", "127.0.0.1")
MILVUS_PORT = env("MILVUS_PORT", "19530")
MILVUS_COLLECTION = env("MILVUS_COLLECTION", "embeddings_collection")

RERANK_MODEL = env("RERANK_MODEL")
RERANK_BINDING_HOST = env("RERANK_BINDING_HOST")
RERANK_API_KEY = env("RERANK_API_KEY")

AUTO_MERGE_ENABLED = env_bool("AUTO_MERGE_ENABLED", True)
AUTO_MERGE_THRESHOLD = env_int("AUTO_MERGE_THRESHOLD", 2)
LEAF_RETRIEVE_LEVEL = env_int("LEAF_RETRIEVE_LEVEL", 3)

RAGFLOW_ENABLED = env_bool("RAGFLOW_ENABLED", False)
RAGFLOW_BASE_URL = env("RAGFLOW_BASE_URL").rstrip("/")
RAGFLOW_API_KEY = env("RAGFLOW_API_KEY")
RAGFLOW_DATASET_IDS = [
    item.strip()
    for item in env("RAGFLOW_DATASET_IDS").split(",")
    if item.strip()
]
RAGFLOW_TOP_K = env_int("RAGFLOW_TOP_K", 5)

OPENCLI_BIN = env("OPENCLI_BIN")
OPENCLI_SESSION = env("OPENCLI_SESSION", "lcagent")
OPENCLI_TIMEOUT = env_int("OPENCLI_TIMEOUT", 75)
OPENCLI_OUTPUT_MAX_CHARS = env_int("OPENCLI_OUTPUT_MAX_CHARS", 12000)
