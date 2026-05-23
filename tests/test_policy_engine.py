from backend.core.policy import GuardDecision, ToolInvocation, ToolPolicyEngine, UserContext


def test_high_risk_tool_requires_human_review():
    user = UserContext(
        user_id="u-1",
        tenant_id="t-1",
        roles={"tool:use:shell_exec"},
    )
    invocation = ToolInvocation(
        name="shell_exec",
        tenant_id="t-1",
        args={"cmd": "rm -rf /"},
    )

    result = ToolPolicyEngine().evaluate(user, invocation)

    assert result.decision == GuardDecision.REQUIRE_HUMAN
    assert "requires human approval" in result.reason


def test_tenant_mismatch_is_denied():
    user = UserContext(user_id="u-1", tenant_id="tenant-a", roles={"tool:*"})
    invocation = ToolInvocation(name="get_current_weather", tenant_id="tenant-b", args={"city": "上海"})

    result = ToolPolicyEngine().evaluate(user, invocation)

    assert result.decision == GuardDecision.DENY
    assert result.reason == "tenant mismatch"


def test_allowlisted_tool_with_permission_is_allowed():
    user = UserContext(user_id="u-1", tenant_id="tenant-a", roles={"tool:use:get_current_weather"})
    invocation = ToolInvocation(name="get_current_weather", tenant_id="tenant-a", args={"city": "北京"})

    result = ToolPolicyEngine(allowed_tools={"get_current_weather"}).evaluate(user, invocation)

    assert result.decision == GuardDecision.ALLOW
