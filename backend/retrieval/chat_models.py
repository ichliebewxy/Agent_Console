"""DeepSeek model factory for RAG grading and query expansion only."""

from langchain.chat_models import init_chat_model

from backend.config.settings import CHAT_API_KEY, CHAT_BASE_URL, CHAT_MODEL


def build_chat_model(
    model_name: str = CHAT_MODEL,
    *,
    temperature: float = 0.0,
    stream_usage: bool = True,
):
    """Build a DeepSeek-backed LangChain chat model."""
    return init_chat_model(
        model=model_name,
        model_provider="deepseek",
        api_key=CHAT_API_KEY,
        base_url=CHAT_BASE_URL,
        temperature=temperature,
        stream_usage=stream_usage,
    )
