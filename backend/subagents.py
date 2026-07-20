"""Lazy specialist agents exposed to the supervisor through one broad tool."""
import asyncio
from typing import Literal

from langchain.agents import create_agent
from langchain_core.messages import AIMessage
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

from agent_prompt import (
    KNOWLEDGE_AGENT_PROMPT,
    MCP_AGENT_PROMPT,
    OPENCLI_AGENT_PROMPT,
    WEATHER_AGENT_PROMPT,
    build_skill_agent_prompt,
)
from tool_instrumentation import instrument_tools


SpecialistName = Literal["knowledge", "weather", "mcp", "opencli", "skills"]


class DelegationRequest(BaseModel):
    specialist: SpecialistName = Field(
        description=(
            "Specialist domain: knowledge=uploaded/internal documents; "
            "weather=current weather; mcp=maps/routes/POIs/addresses/coordinates; "
            "opencli=web browsing, page extraction, or browser interaction; "
            "skills=specialized procedures and sandboxed workspace tasks."
        )
    )
    task: str = Field(
        min_length=1,
        description=(
            "Self-contained task with all relevant user context, constraints, "
            "locations, URLs, and desired output."
        ),
    )


def _content_text(content) -> str:
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return str(content or "")
    parts = []
    for block in content:
        if isinstance(block, str):
            parts.append(block)
        elif isinstance(block, dict) and block.get("type") == "text":
            parts.append(str(block.get("text", "")))
    return "".join(parts)


def _final_agent_text(result) -> str:
    messages = result.get("messages", []) if isinstance(result, dict) else []
    for message in reversed(messages):
        if isinstance(message, AIMessage):
            text = _content_text(message.content).strip()
            if text:
                return text
    return "SPECIALIST_ERROR: 小 Agent 未返回可用结果。"


class SpecialistRegistry:
    """Builds each LangGraph specialist only when the supervisor delegates to it."""

    def __init__(self, model):
        self._model = model
        self._agents = {}
        self._locks = {
            name: asyncio.Lock()
            for name in ("knowledge", "weather", "mcp", "opencli", "skills")
        }
        self._mcp_client = None

    async def _get_agent(self, specialist: SpecialistName):
        cached = self._agents.get(specialist)
        if cached is not None:
            return cached

        async with self._locks[specialist]:
            cached = self._agents.get(specialist)
            if cached is not None:
                return cached

            if specialist == "knowledge":
                from tools import search_knowledge_base

                tools = [search_knowledge_base]
                prompt = KNOWLEDGE_AGENT_PROMPT
            elif specialist == "weather":
                from tools import get_current_weather

                tools = [get_current_weather]
                prompt = WEATHER_AGENT_PROMPT
            elif specialist == "opencli":
                from opencli_tools import OPENCLI_TOOLS

                tools = OPENCLI_TOOLS
                prompt = OPENCLI_AGENT_PROMPT
            elif specialist == "mcp":
                from mcp_service import load_mcp_tools

                mcp_result = await load_mcp_tools(record_init_failure=True)
                if not mcp_result.tools:
                    detail = f"：{mcp_result.error}" if mcp_result.error else ""
                    raise RuntimeError(f"MCP 当前没有可用工具{detail}")
                self._mcp_client = mcp_result.client
                tools = mcp_result.tools
                prompt = MCP_AGENT_PROMPT
            elif specialist == "skills":
                from sandbox_service import SANDBOX_TOOLS
                from skill_service import SKILL_REGISTRY, SKILL_TOOLS
                from workspace_tools import WORKSPACE_TOOLS

                tools = [*SKILL_TOOLS, *WORKSPACE_TOOLS, *SANDBOX_TOOLS]
                prompt = build_skill_agent_prompt(SKILL_REGISTRY.catalog())
            else:
                raise ValueError(f"Unknown specialist: {specialist}")

            cached = create_agent(
                model=self._model,
                tools=instrument_tools(tools),
                system_prompt=prompt,
                name=f"{specialist}_specialist",
            )
            self._agents[specialist] = cached
            return cached

    async def run(self, specialist: SpecialistName, task: str) -> str:
        try:
            specialist_agent = await self._get_agent(specialist)
            result = await specialist_agent.ainvoke(
                {"messages": [{"role": "user", "content": task}]},
                # Keep specialist model tokens private to the subgraph. Tool
                # instrumentation still emits user-visible execution steps.
                config={"recursion_limit": 30, "callbacks": []},
            )
            return _final_agent_text(result)
        except Exception as exc:
            return f"SPECIALIST_ERROR: {specialist} 小 Agent 执行失败：{exc}"


def build_delegation_tool(model) -> StructuredTool:
    """Create the supervisor's only broad capability gateway."""
    registry = SpecialistRegistry(model)

    async def delegate_to_specialist(specialist: SpecialistName, task: str) -> str:
        return await registry.run(specialist, task)

    delegation_tool = StructuredTool.from_function(
        coroutine=delegate_to_specialist,
        name="delegate_to_specialist",
        description=(
            "Delegate a self-contained task to one isolated specialist LangGraph agent. "
            "The specialist receives its domain tools only after delegation and returns "
            "an evidence report. Use this gateway for knowledge, live weather, MCP map "
            "capabilities, OpenCLI browser work, or skill-guided workspace work."
        ),
        args_schema=DelegationRequest,
    )
    return delegation_tool
