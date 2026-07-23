"""Runtime MCP/Skill configuration APIs."""
from fastapi import APIRouter, HTTPException

from config_service import CONFIG_STORE
from mcp_config_service import MCP_STORE
from mcp_service import discover_configured_mcp_tools
from runtime_catalog_service import refresh_runtime_catalogs, refresh_skill_catalog
from schemas import (
    MCPServerUpsertRequest,
    MutationResponse,
    RuntimeConfigResponse,
    RuntimeRefreshResponse,
    SkillCreateRequest,
)
from skill_service import SKILL_REGISTRY


router = APIRouter()


def _runtime_config_snapshot(*, public: bool = True) -> dict:
    """Keep the existing API shape while sourcing MCP from its own file."""
    snapshot = CONFIG_STORE.snapshot(public=public)
    mcp_snapshot = (
        CONFIG_STORE.snapshot(public=public)
        if getattr(CONFIG_STORE, "_legacy_mcp_mode", False)
        else MCP_STORE.snapshot(public=public)
    )
    snapshot["mcpServers"] = mcp_snapshot.get("mcpServers", {})
    return snapshot


async def _reload_main_agent() -> None:
    from agent import init_agent_async

    await init_agent_async()


@router.get("/runtime-config", response_model=RuntimeConfigResponse)
async def get_runtime_config():
    return RuntimeConfigResponse(config=_runtime_config_snapshot())


@router.post("/runtime-config/refresh", response_model=RuntimeRefreshResponse)
async def refresh_runtime_config():
    result = await refresh_runtime_catalogs()
    await _reload_main_agent()
    return RuntimeRefreshResponse(**result)


@router.post("/runtime-config/mcp", response_model=RuntimeConfigResponse)
async def upsert_mcp_server(request: MCPServerUpsertRequest):
    transport = request.transport.strip()
    if transport not in {"streamable_http", "sse", "stdio"}:
        raise HTTPException(status_code=422, detail="Unsupported MCP transport")
    if transport == "stdio" and not request.command.strip():
        raise HTTPException(status_code=422, detail="stdio MCP requires command")
    if transport != "stdio" and not request.url.strip():
        raise HTTPException(status_code=422, detail="HTTP MCP requires url")
    mcp_server = {
        "transport": transport,
        "url": request.url.strip(),
        "command": request.command.strip(),
        "args": request.args,
        "headers": request.headers,
        "env": request.env,
        "enabled": request.enabled,
    }
    if getattr(CONFIG_STORE, "_legacy_mcp_mode", False):
        CONFIG_STORE.upsert_mcp_server(request.name, mcp_server)
    else:
        MCP_STORE.upsert(request.name, mcp_server)
    await discover_configured_mcp_tools()
    await _reload_main_agent()
    return RuntimeConfigResponse(config=_runtime_config_snapshot())


@router.delete("/runtime-config/mcp/{name}", response_model=MutationResponse)
async def delete_mcp_server(name: str):
    removed = (
        CONFIG_STORE.remove_mcp_server(name)
        if getattr(CONFIG_STORE, "_legacy_mcp_mode", False)
        else MCP_STORE.remove(name)
    )
    if not removed:
        raise HTTPException(status_code=404, detail="MCP server not found")
    await discover_configured_mcp_tools()
    await _reload_main_agent()
    return MutationResponse(message=f"Removed MCP server: {name}")


@router.post("/runtime-config/skills", response_model=RuntimeConfigResponse)
async def create_skill(request: SkillCreateRequest):
    try:
        SKILL_REGISTRY.create(
            request.name,
            request.description,
            request.instructions,
            overwrite=request.overwrite,
        )
    except FileExistsError:
        raise HTTPException(status_code=409, detail="Skill already exists")
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    refresh_skill_catalog()
    await _reload_main_agent()
    return RuntimeConfigResponse(config=_runtime_config_snapshot())


@router.delete("/runtime-config/skills/{name}", response_model=MutationResponse)
async def delete_skill(name: str):
    if not SKILL_REGISTRY.delete(name):
        raise HTTPException(status_code=404, detail="Skill not found")
    refresh_skill_catalog()
    await _reload_main_agent()
    return MutationResponse(message=f"Removed skill: {name}")
