"""Lazy LangChain subagents exposed through explicit loading and delegation tools."""
from agent_prompt import build_skill_agent_prompt
from goal_mode import AgentCircuitOpen, AgentCycleLimitMiddleware
from langchain.agents import create_agent
from langchain_core.messages import AIMessage
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field
from settings import AGENT_TOOL_CALL_LIMIT
from tool_instrumentation import instrument_tools


class SkillDelegationRequest(BaseModel):
    task: str = Field(
        min_length=1,
        description=(
            "Self-contained task containing the user outcome, relevant context, "
            "constraints, URLs, desired output, and requested file changes."
        ),
    )


class SubagentLoadRequest(BaseModel):
    name: str = Field(
        default="skills_specialist",
        description="Subagent name. Currently available: skills_specialist.",
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

    async def _get_agent(self):
        from core_tools import CORE_TOOLS, REVIEW_TOOLS
        from skill_resolver import visible_skill_names
        from skill_service import SKILL_REGISTRY, SKILL_TOOLS

        tools = [*CORE_TOOLS, *SKILL_TOOLS, *REVIEW_TOOLS]
        catalog = SKILL_REGISTRY.catalog(names=visible_skill_names(SKILL_REGISTRY.names))
        return create_agent(
            model=self._model,
            tools=instrument_tools(tools),
            middleware=[AgentCycleLimitMiddleware()],
            system_prompt=build_skill_agent_prompt(catalog),
            name="skills_specialist",
        )

    async def run(self, task: str) -> str:
        try:
            skill_agent = await self._get_agent()
            from resource_context import build_workspace_context
            from runtime_context import current_runtime_context

            messages = [{"role": "user", "content": task}]
            try:
                context = current_runtime_context()
            except RuntimeError:
                context = None
            if context is not None:
                messages.insert(0, build_workspace_context(context.user_id, context.session_id))
            result = await skill_agent.ainvoke(
                {"messages": messages},
                config={
                    "recursion_limit": AGENT_TOOL_CALL_LIMIT * 2 + 8,
                    "callbacks": [],
                },
            )
            return _final_agent_text(result)
        except AgentCircuitOpen:
            raise
        except Exception as exc:
            return f"SKILL_AGENT_ERROR: Skills 小 Agent 执行失败：{exc}"

    async def load(self, name: str = "skills_specialist") -> str:
        normalized = (name or "").strip()
        if normalized != "skills_specialist":
            return (
                "SUBAGENT_ERROR: Unknown subagent. "
                "Available subagents: skills_specialist"
            )
        from skill_resolver import visible_skill_names
        from skill_service import SKILL_REGISTRY
        names = visible_skill_names(SKILL_REGISTRY.names)
        return (
            "Loaded subagent: skills_specialist. It can load skills on demand, "
            "use the five core tools, review commands, and return a specialist result. "
            f"Visible skills: {', '.join(names) or '(none)'}."
        )


def _loader_tool(registry: SkillAgentRegistry) -> StructuredTool:
    async def load_subagent(name: str = "skills_specialist") -> str:
        return await registry.load(name)

    return StructuredTool.from_function(
        coroutine=load_subagent,
        name="load_subagent",
        description=(
            "Load a named LangChain subagent before delegating work. "
            "Currently available: skills_specialist."
        ),
        args_schema=SubagentLoadRequest,
    )


def _delegation_tool(registry: SkillAgentRegistry) -> StructuredTool:
    async def delegate_to_skill_agent(task: str) -> str:
        return await registry.run(task)

    return StructuredTool.from_function(
        coroutine=delegate_to_skill_agent,
        name="delegate_to_skill_agent",
        description=(
            "Delegate a self-contained specialized workflow to the Skills subagent. "
            "It inspects the current skill catalog, loads matching skills, uses the "
            "reviewed five-tool workspace, and returns its result."
        ),
        args_schema=SkillDelegationRequest,
    )


def build_skill_delegation_tool(model) -> StructuredTool:
    """Create the main Agent's single gateway to skill selection and execution."""
    return _delegation_tool(SkillAgentRegistry(model))


def build_subagent_tools(model) -> list[StructuredTool]:
    """Build loader and delegation tools backed by the same lazy registry."""
    registry = SkillAgentRegistry(model)
    return [_loader_tool(registry), _delegation_tool(registry)]
