"""Centralized runtime configuration."""
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

PROJECT_ROOT = Path(__file__).resolve().parent.parent


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


def env_float(name: str, default: float) -> float:
    try:
        return float(env(name, str(default)))
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

AGENT_WORKSPACE_DIR = env_path("AGENT_WORKSPACE_DIR", PROJECT_ROOT / "agent_workspace")
AGENT_SKILLS_DIR = env_path("AGENT_SKILLS_DIR", AGENT_WORKSPACE_DIR / "skills")
SKILL_CATALOG_MAX_CHARS = env_int("SKILL_CATALOG_MAX_CHARS", 8000)
SKILL_CONTENT_MAX_CHARS = env_int("SKILL_CONTENT_MAX_CHARS", 60000)
WORKSPACE_FILE_MAX_CHARS = env_int("WORKSPACE_FILE_MAX_CHARS", 50000)
ARTIFACT_SIGNING_KEY = env("ARTIFACT_SIGNING_KEY")

SANDBOX_ENABLED = env_bool("SANDBOX_ENABLED", True)
SANDBOX_DOCKER_BIN = env("SANDBOX_DOCKER_BIN", "docker")
SANDBOX_IMAGE = env("SANDBOX_IMAGE", "agent-console-sandbox:py312")
SANDBOX_TIMEOUT = env_int("SANDBOX_TIMEOUT", 120)
SANDBOX_MEMORY_MB = env_int("SANDBOX_MEMORY_MB", 512)
SANDBOX_CPUS = env_float("SANDBOX_CPUS", 1.0)
SANDBOX_PIDS_LIMIT = env_int("SANDBOX_PIDS_LIMIT", 128)
SANDBOX_OUTPUT_MAX_CHARS = env_int("SANDBOX_OUTPUT_MAX_CHARS", 20000)
SANDBOX_COMMAND_MAX_CHARS = env_int("SANDBOX_COMMAND_MAX_CHARS", 8000)
SANDBOX_WORKSPACE_MAX_MB = env_int("SANDBOX_WORKSPACE_MAX_MB", 256)
SANDBOX_FILE_MAX_MB = env_int("SANDBOX_FILE_MAX_MB", 64)
SANDBOX_MAX_FILES = env_int("SANDBOX_MAX_FILES", 1000)
SANDBOX_DOCKER_CLEANUP_TIMEOUT = env_int("SANDBOX_DOCKER_CLEANUP_TIMEOUT", 10)
_HOST_UID = os.getuid() if hasattr(os, "getuid") else 65534
_HOST_GID = os.getgid() if hasattr(os, "getgid") else 65534
SANDBOX_UID = env_int("SANDBOX_UID", _HOST_UID if _HOST_UID > 0 else 65534)
SANDBOX_GID = env_int("SANDBOX_GID", _HOST_GID if _HOST_UID > 0 else 65534)
