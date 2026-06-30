"""LangGraph RAG orchestration."""
from langchain.chat_models import init_chat_model
from langgraph.graph import END, StateGraph

from query_expansion import generate_hypothetical_document, step_back_expand
from rag_expanded import retrieve_expanded
from rag_state import GRADE_PROMPT, GradeDocuments, RAGState, RewriteStrategy, empty_rag_state, format_docs
from rag_utils import retrieve_documents
from settings import CHAT_API_KEY, CHAT_BASE_URL, CHAT_MODEL
from tools import emit_rag_step

_grader_model = None
_router_model = None


def _build_model(temperature: float = 0):
    return init_chat_model(
        model=CHAT_MODEL,
        model_provider="deepseek",
        api_key=CHAT_API_KEY,
        base_url=CHAT_BASE_URL,
        temperature=temperature,
        stream_usage=True,
    )


def _get_grader_model():
    global _grader_model
    if _grader_model is None:
        _grader_model = _build_model()
    return _grader_model


def _get_router_model():
    global _router_model
    if not CHAT_API_KEY or not CHAT_MODEL:
        return None
    if _router_model is None:
        _router_model = _build_model()
    return _router_model


def retrieve_initial(state: RAGState) -> RAGState:
    query = state["question"]
    emit_rag_step("🔍", "正在检索知识库...", f"查询: {query[:50]}")
    retrieved = retrieve_documents(query, top_k=5)
    results = retrieved.get("docs", [])
    meta = retrieved.get("meta", {})
    emit_rag_step("🧱", "三级分块检索", f"叶子层 L{meta.get('leaf_retrieve_level', 3)} 召回，候选 {meta.get('candidate_k', 0)}")
    emit_rag_step(
        "🧩",
        "Auto-merging 合并",
        f"启用: {bool(meta.get('auto_merge_enabled'))}，应用: {bool(meta.get('auto_merge_applied'))}",
    )
    emit_rag_step("✅", f"检索完成，找到 {len(results)} 个片段", f"模式: {meta.get('retrieval_mode', 'hybrid')}")
    rag_trace = {
        "tool_used": True,
        "tool_name": "search_knowledge_base",
        "query": query,
        "expanded_query": query,
        "retrieved_chunks": results,
        "initial_retrieved_chunks": results,
        "retrieval_stage": "initial",
    }
    for key in [
        "rerank_enabled", "rerank_applied", "rerank_model", "rerank_endpoint", "rerank_error",
        "retrieval_mode", "candidate_k", "leaf_retrieve_level", "auto_merge_enabled",
        "auto_merge_applied", "auto_merge_threshold", "auto_merge_replaced_chunks",
        "auto_merge_steps", "candidate_count",
    ]:
        rag_trace[key] = meta.get(key)
    return {"query": query, "docs": results, "context": format_docs(results), "rag_trace": rag_trace}


def grade_documents_node(state: RAGState) -> RAGState:
    if not state.get("docs"):
        emit_rag_step("⚠️", "未检索到片段，准备改写查询")
        return _grade_update(state, "no_docs", "rewrite_question")
    emit_rag_step("📊", "正在评估文档相关性...")
    grader = _get_grader_model()
    if not grader:
        return _grade_update(state, "unknown", "rewrite_question")
    prompt = GRADE_PROMPT.format(question=state["question"], context=state.get("context", ""))
    response = grader.with_structured_output(GradeDocuments).invoke([{"role": "user", "content": prompt}])
    score = (response.binary_score or "").strip().lower()
    route = "generate_answer" if score == "yes" else "rewrite_question"
    emit_rag_step("✅" if route == "generate_answer" else "⚠️", "文档相关性评估完成", f"评分: {score}")
    return _grade_update(state, score, route)


def _grade_update(state: RAGState, score: str, route: str) -> RAGState:
    rag_trace = state.get("rag_trace", {}) or {}
    rag_trace.update({
        "grade_score": score,
        "grade_route": route,
        "rewrite_needed": route == "rewrite_question",
    })
    return {"route": route, "rag_trace": rag_trace}


def _choose_strategy(question: str) -> str:
    router = _get_router_model()
    if not router:
        return "step_back"
    prompt = (
        "请根据用户问题选择最合适的查询扩展策略，仅输出策略名。\n"
        "- step_back：包含具体名称、日期、代码等细节，需要先理解通用概念的问题。\n"
        "- hyde：模糊、概念性、需要解释或定义的问题。\n"
        "- complex：多步骤、需要分解或综合多种信息的复杂问题。\n"
        f"用户问题：{question}"
    )
    try:
        decision = router.with_structured_output(RewriteStrategy).invoke([{"role": "user", "content": prompt}])
        return decision.strategy
    except Exception:
        return "step_back"


def rewrite_question_node(state: RAGState) -> RAGState:
    question = state["question"]
    strategy = _choose_strategy(question)
    emit_rag_step("✏️", "正在重写查询...", f"策略: {strategy}")
    expanded_query = question
    step_back_question = ""
    step_back_answer = ""
    hypothetical_doc = ""

    if strategy in ("step_back", "complex"):
        step_back = step_back_expand(question)
        step_back_question = step_back.get("step_back_question", "")
        step_back_answer = step_back.get("step_back_answer", "")
        expanded_query = step_back.get("expanded_query", question)
    if strategy in ("hyde", "complex"):
        emit_rag_step("📝", "HyDE 假设性文档生成中...")
        hypothetical_doc = generate_hypothetical_document(question)

    rag_trace = state.get("rag_trace", {}) or {}
    rag_trace.update({"rewrite_strategy": strategy, "rewrite_query": expanded_query})
    return {
        "expansion_type": strategy,
        "expanded_query": expanded_query,
        "step_back_question": step_back_question,
        "step_back_answer": step_back_answer,
        "hypothetical_doc": hypothetical_doc,
        "rag_trace": rag_trace,
    }


def build_rag_graph():
    graph = StateGraph(RAGState)
    graph.add_node("retrieve_initial", retrieve_initial)
    graph.add_node("grade_documents", grade_documents_node)
    graph.add_node("rewrite_question", rewrite_question_node)
    graph.add_node("retrieve_expanded", retrieve_expanded)
    graph.set_entry_point("retrieve_initial")
    graph.add_edge("retrieve_initial", "grade_documents")
    graph.add_conditional_edges(
        "grade_documents",
        lambda state: state.get("route"),
        {"generate_answer": END, "rewrite_question": "rewrite_question"},
    )
    graph.add_edge("rewrite_question", "retrieve_expanded")
    graph.add_edge("retrieve_expanded", END)
    return graph.compile()


rag_graph = build_rag_graph()


def run_rag_graph(question: str) -> dict:
    return rag_graph.invoke(empty_rag_state(question))
