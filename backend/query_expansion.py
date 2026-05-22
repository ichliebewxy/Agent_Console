"""Query expansion helpers for RAG."""
from langchain.chat_models import init_chat_model

from settings import CHAT_API_KEY, CHAT_BASE_URL, QUERY_EXPANSION_MODEL

_stepback_model = None


def _get_stepback_model():
    global _stepback_model
    if not CHAT_API_KEY or not QUERY_EXPANSION_MODEL:
        return None
    if _stepback_model is None:
        _stepback_model = init_chat_model(
            model=QUERY_EXPANSION_MODEL,
            model_provider="deepseek",
            api_key=CHAT_API_KEY,
            base_url=CHAT_BASE_URL,
            temperature=0.2,
        )
    return _stepback_model


def _invoke_prompt(prompt: str) -> str:
    model = _get_stepback_model()
    if not model:
        return ""
    try:
        return (model.invoke(prompt).content or "").strip()
    except Exception:
        return ""


def generate_step_back_question(query: str) -> str:
    return _invoke_prompt(
        "请将用户的具体问题抽象成更高层次、更概括的退步问题，"
        "用于探寻背后的通用原理或核心概念。只输出一句话，不要解释。\n"
        f"用户问题：{query}"
    )


def answer_step_back_question(step_back_question: str) -> str:
    if not step_back_question:
        return ""
    return _invoke_prompt(
        "请简要回答以下退步问题，提供通用原理/背景知识，控制在120字以内。"
        "只输出答案，不要列出推理过程。\n"
        f"退步问题：{step_back_question}"
    )


def generate_hypothetical_document(query: str) -> str:
    return _invoke_prompt(
        "请基于用户问题生成一段假设性文档，内容应像真实资料片段，"
        "用于帮助检索相关信息。只输出文档正文，不要标题或解释。\n"
        f"用户问题：{query}"
    )


def step_back_expand(query: str) -> dict:
    question = generate_step_back_question(query)
    answer = answer_step_back_question(question)
    expanded_query = query
    if question or answer:
        expanded_query = f"{query}\n\n退步问题：{question}\n退步问题答案：{answer}"
    return {
        "step_back_question": question,
        "step_back_answer": answer,
        "expanded_query": expanded_query,
    }
