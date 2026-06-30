from typing import Optional
import asyncio

import requests

try:
    from langchain_core.tools import tool
except ImportError:
    from langchain_core.tools import tool

from ops_store import record_tool_failure
from settings import AMAP_API_KEY, AMAP_WEATHER_API

_LAST_RAG_CONTEXT = None
_KNOWLEDGE_TOOL_CALLS_THIS_TURN = 0
_RAG_STEP_QUEUE = None
_RAG_STEP_LOOP = None
_TOOL_STEP_QUEUE = None
_TOOL_STEP_LOOP = None


def _set_last_rag_context(context: dict):
    global _LAST_RAG_CONTEXT
    _LAST_RAG_CONTEXT = context


def get_last_rag_context(clear: bool = True) -> Optional[dict]:
    global _LAST_RAG_CONTEXT
    context = _LAST_RAG_CONTEXT
    if clear:
        _LAST_RAG_CONTEXT = None
    return context


def reset_tool_call_guards():
    global _KNOWLEDGE_TOOL_CALLS_THIS_TURN
    _KNOWLEDGE_TOOL_CALLS_THIS_TURN = 0


def set_rag_step_queue(queue):
    global _RAG_STEP_QUEUE, _RAG_STEP_LOOP
    _RAG_STEP_QUEUE = queue
    if queue:
        try:
            _RAG_STEP_LOOP = asyncio.get_running_loop()
        except RuntimeError:
            _RAG_STEP_LOOP = asyncio.get_event_loop()
    else:
        _RAG_STEP_LOOP = None


def emit_rag_step(icon: str, label: str, detail: str = ""):
    global _RAG_STEP_QUEUE, _RAG_STEP_LOOP
    if _RAG_STEP_QUEUE is None or _RAG_STEP_LOOP is None:
        return
    step = {"icon": icon, "label": label, "detail": detail}
    try:
        if not _RAG_STEP_LOOP.is_closed():
            try:
                current_loop = asyncio.get_running_loop()
            except RuntimeError:
                current_loop = None
            if current_loop is _RAG_STEP_LOOP:
                _RAG_STEP_QUEUE.put_nowait(step)
            else:
                _RAG_STEP_LOOP.call_soon_threadsafe(_RAG_STEP_QUEUE.put_nowait, step)
    except Exception:
        pass


def set_tool_step_queue(queue):
    global _TOOL_STEP_QUEUE, _TOOL_STEP_LOOP
    _TOOL_STEP_QUEUE = queue
    if queue:
        try:
            _TOOL_STEP_LOOP = asyncio.get_running_loop()
        except RuntimeError:
            _TOOL_STEP_LOOP = asyncio.get_event_loop()
    else:
        _TOOL_STEP_LOOP = None


def emit_tool_step(step: dict):
    global _TOOL_STEP_QUEUE, _TOOL_STEP_LOOP
    if _TOOL_STEP_QUEUE is None or _TOOL_STEP_LOOP is None:
        return
    try:
        if not _TOOL_STEP_LOOP.is_closed():
            try:
                current_loop = asyncio.get_running_loop()
            except RuntimeError:
                current_loop = None
            if current_loop is _TOOL_STEP_LOOP:
                _TOOL_STEP_QUEUE.put_nowait(step)
            else:
                _TOOL_STEP_LOOP.call_soon_threadsafe(_TOOL_STEP_QUEUE.put_nowait, step)
    except Exception:
        pass


@tool
def get_current_weather(city: str) -> str:
    """Get current weather for a city by calling the configured AMap weather API."""
    city = (city or "").strip()
    if not city:
        return "city 参数不能为空"
    if not AMAP_API_KEY:
        fallback = "天气工具未配置 AMAP_API_KEY，无法查询实时天气。"
        record_tool_failure("get_current_weather", "missing AMAP_API_KEY", {"city": city}, fallback)
        return fallback

    payload = {
        "key": AMAP_API_KEY,
        "city": city,
        "extensions": "base",
        "output": "JSON",
    }

    try:
        resp = requests.get(AMAP_WEATHER_API, params=payload, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        if data.get("status") != "1":
            error = data.get("info") or data.get("infocode") or "AMap weather API returned non-success status"
            record_tool_failure("get_current_weather", str(error), payload, "Returned weather API error to the model.")
            return f"天气查询失败：{error}"

        lives = data.get("lives") or []
        if not lives:
            return f"未查询到 {city} 的实时天气数据"

        live = lives[0]
        province = live.get("province") or ""
        actual_city = live.get("city") or city
        weather_text = live.get("weather") or "未知"
        temperature = live.get("temperature") or "未知"
        wind_direction = live.get("winddirection") or "未知"
        wind_power = live.get("windpower") or "未知"
        humidity = live.get("humidity") or "未知"
        report_time = live.get("reporttime") or "未知"

        location = f"{province}{actual_city}" if province and province != actual_city else actual_city
        return (
            f"【{location} 实时天气】\n"
            f"天气状况：{weather_text}\n"
            f"温度：{temperature}℃\n"
            f"湿度：{humidity}%\n"
            f"风向：{wind_direction}\n"
            f"风力：{wind_power}\n"
            f"更新时间：{report_time}"
        )
    except requests.exceptions.Timeout:
        fallback = "天气服务超时，已记录失败回调，请稍后重试。"
        record_tool_failure("get_current_weather", "timeout", payload, fallback)
        return fallback
    except requests.exceptions.RequestException as e:
        fallback = "天气服务网络请求失败，已记录失败回调。"
        record_tool_failure("get_current_weather", str(e), payload, fallback)
        return f"{fallback} 原因：{e}"
    except Exception as e:
        fallback = "天气数据解析失败，已记录失败回调。"
        record_tool_failure("get_current_weather", str(e), payload, fallback)
        return f"{fallback} 原因：{e}"


@tool("search_knowledge_base")
def search_knowledge_base(query: str) -> str:
    """Search for information in the knowledge base using hybrid retrieval."""
    global _KNOWLEDGE_TOOL_CALLS_THIS_TURN
    if _KNOWLEDGE_TOOL_CALLS_THIS_TURN >= 1:
        return (
            "TOOL_CALL_LIMIT_REACHED: search_knowledge_base has already been called once in this turn. "
            "Use the existing retrieval result and provide the final answer directly."
        )
    _KNOWLEDGE_TOOL_CALLS_THIS_TURN += 1

    from rag_pipeline import run_rag_graph

    try:
        rag_result = run_rag_graph(query)
    except Exception as e:
        fallback = "知识库检索失败，已记录失败回调；请根据已有上下文谨慎回答，并说明检索不可用。"
        record_tool_failure("search_knowledge_base", str(e), {"query": query}, fallback)
        return fallback

    docs = rag_result.get("docs", []) if isinstance(rag_result, dict) else []
    rag_trace = rag_result.get("rag_trace", {}) if isinstance(rag_result, dict) else {}
    if rag_trace:
        _set_last_rag_context({"rag_trace": rag_trace})

    if not docs:
        return "No relevant documents found in the knowledge base."

    formatted = []
    for i, result in enumerate(docs, 1):
        source = result.get("filename", "Unknown")
        page = result.get("page_number", "N/A")
        text = result.get("text", "")
        retrieval_source = result.get("retrieval_source", "local")
        formatted.append(f"[{i}] {source} (Page {page}, Source {retrieval_source}):\n{text}")

    return "Retrieved Chunks:\n" + "\n\n---\n\n".join(formatted)
