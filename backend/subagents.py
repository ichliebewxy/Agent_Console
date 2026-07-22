"""Lazy skills specialist exposed to the main Agent through one delegation tool."""
import asyncio

from langchain.agents import create_agent
from langchain_core.messages import AIMessage
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

from agent_prompt import build_skill_agent_prompt
from tool_instrumentation import instrument_tools


class SkillDelegationRequest(BaseModel):
    task: str = Field(
        min_length=1,
        description=(
            "Self-contained task containing the user outcome, relevant context, "
            "constraints, URLs, desired output, and requested file changes."
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
    return "SKILL_AGENT_ERROR: Skills 小 Agent 未返回可用结果。"


class SkillAgentRegistry:
    def __init__(self, model):
        self._model = model
        self._agent = None
        self._lock = asyncio.Lock()

    async def _get_agent(self):
        if self._agent is not None:
            return self._agent
        async with self._lock:
            if self._agent is not None:
                return self._agent
            from bash_tool import BASH_TOOLS
            from skill_service import SKILL_REGISTRY, SKILL_TOOLS
            from workspace_tools import WORKSPACE_TOOLS

            tools = [*SKILL_TOOLS, *WORKSPACE_TOOLS, *BASH_TOOLS]
            self._agent = create_agent(
                model=self._model,
                tools=instrument_tools(tools),
                system_prompt=build_skill_agent_prompt(SKILL_REGISTRY.catalog()),
                name="skills_specialist",
            )
            return self._agent

    async def run(self, task: str) -> str:
        try:
            skill_agent = await self._get_agent()
            result = await skill_agent.ainvoke(
                {"messages": [{"role": "user", "content": task}]},
                config={"recursion_limit": 36, "callbacks": []},
            )
            return _final_agent_text(result)
        except Exception as exc:
            return f"SKILL_AGENT_ERROR: Skills 小 Agent 执行失败：{exc}"


def build_skill_delegation_tool(model) -> StructuredTool:
    """Create the main Agent's single gateway to skill selection and execution."""
    registry = SkillAgentRegistry(model)

    async def delegate_to_skill_agent(task: str) -> str:
        return await registry.run(task)

    return StructuredTool.from_function(
        coroutine=delegate_to_skill_agent,
        name="delegate_to_skill_agent",
        description=(
            "Delegate a self-contained specialized workflow to the Skills small Agent. "
            "It inspects the current skill catalog, loads the best matching skill, may "
            "use the reviewed Bash and session workspace tools, and returns its result."
        ),
        args_schema=SkillDelegationRequest,
    )
