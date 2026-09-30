"""Map session memory policy to isolated mem0 user namespaces."""

from dataclasses import dataclass
from hashlib import sha256

from session_resources import SessionResources


@dataclass(frozen=True)
class MemoryAccess:
    reads: tuple[tuple[str, str], ...]
    write: tuple[str, str]


def namespace_for_scope(user_id: str, session_id: str, resources: SessionResources, scope: str) -> str:
    if scope not in {"user", "project", "session"}:
        raise ValueError("Invalid memory scope.")
    if scope == "project" and not resources.project_id:
        raise ValueError("Project memory requires project_id.")
    if scope == "user":
        # Keep existing user memories readable after the upgrade.
        return user_id
    owner = f"{user_id}\0{resources.project_id if scope == 'project' else session_id}"
    digest = sha256(owner.encode("utf-8")).hexdigest()
    return f"scope:{scope}:{digest}"


def resolve_memory_access(user_id: str, session_id: str, resources: SessionResources) -> MemoryAccess:
    reads = tuple(
        (scope, namespace_for_scope(user_id, session_id, resources, scope))
        for scope in resources.memory_read_scopes
    )
    write_scope = resources.memory_write_scope
    return MemoryAccess(reads, (
        write_scope,
        namespace_for_scope(user_id, session_id, resources, write_scope),
    ))
