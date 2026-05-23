from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class GuardDecision(str, Enum):
    ALLOW = "allow"
    REQUIRE_HUMAN = "require_human"
    DENY = "deny"


class UserContext(BaseModel):
    user_id: str = "anonymous"
    tenant_id: str = "default"
    roles: set[str] = Field(default_factory=set)


class ToolInvocation(BaseModel):
    name: str
    tenant_id: str = "default"
    args: dict[str, Any] = Field(default_factory=dict)


class PolicyResult(BaseModel):
    decision: GuardDecision
    reason: str | None = None


class ToolPolicyEngine:
    high_risk_tools: set[str] = {
        "sql_exec_write",
        "shell_exec",
        "webhook_post",
        "filesystem_write",
    }

    def __init__(
        self,
        *,
        allowed_tools: set[str] | None = None,
        high_risk_tools: set[str] | None = None,
    ) -> None:
        self.allowed_tools = allowed_tools
        self.high_risk_tools = high_risk_tools or set(self.high_risk_tools)

    def evaluate(self, user: UserContext, invocation: ToolInvocation) -> PolicyResult:
        if user.tenant_id != invocation.tenant_id:
            return PolicyResult(
                decision=GuardDecision.DENY,
                reason="tenant mismatch",
            )

        if (
            self.allowed_tools is not None
            and invocation.name not in self.allowed_tools
            and "tool:*" not in user.roles
        ):
            return PolicyResult(
                decision=GuardDecision.DENY,
                reason=f"tool '{invocation.name}' is not allowlisted",
            )

        if invocation.name in self.high_risk_tools and "tool:approve" not in user.roles:
            return PolicyResult(
                decision=GuardDecision.REQUIRE_HUMAN,
                reason=f"tool '{invocation.name}' requires human approval",
            )

        if f"tool:use:{invocation.name}" not in user.roles and "tool:*" not in user.roles:
            return PolicyResult(
                decision=GuardDecision.DENY,
                reason=f"missing permission for '{invocation.name}'",
            )

        return PolicyResult(decision=GuardDecision.ALLOW)
