"""Refresh skill metadata and startup-discovered MCP tools."""
from config_service import CONFIG_STORE
from mcp_service import MCPDiscoveryResult, discover_configured_mcp_tools
from skill_service import SKILL_REGISTRY


def refresh_skill_catalog() -> list[dict]:
    SKILL_REGISTRY.refresh()
    entries = SKILL_REGISTRY.entries()
    CONFIG_STORE.sync_skills(entries, SKILL_REGISTRY.errors())
    return entries


async def refresh_runtime_catalogs() -> dict:
    skills = refresh_skill_catalog()
    mcp: MCPDiscoveryResult = await discover_configured_mcp_tools()
    return {
        "skills": skills,
        "skill_errors": SKILL_REGISTRY.errors(),
        "mcp_server_count": mcp.server_count,
        "mcp_tool_count": mcp.tool_count,
        "mcp_errors": mcp.errors,
    }
