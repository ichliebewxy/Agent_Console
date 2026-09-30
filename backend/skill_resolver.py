"""Resolve visible skill names from the current session policy."""

from runtime_context import current_runtime_context
from session_resources import SESSION_RESOURCES
from skill_bindings import SKILL_BINDINGS


def visible_skill_names(installed: tuple[str, ...]) -> tuple[str, ...]:
    try:
        context = current_runtime_context()
    except RuntimeError:
        return installed
    return resolve_skill_names(installed, context.user_id, context.session_id)


def resolve_skill_names(installed: tuple[str, ...], user_id: str, session_id: str) -> tuple[str, ...]:
    resources = SESSION_RESOURCES.get(user_id, session_id)
    allowed = set(installed)
    for name, enabled in SKILL_BINDINGS.get(user_id).items():
        if enabled:
            allowed.add(name)
        else:
            allowed.discard(name)
    if resources.project_id:
        for name, enabled in SKILL_BINDINGS.get(user_id, resources.project_id).items():
            if enabled:
                allowed.add(name)
            else:
                allowed.discard(name)
    if resources.skills is not None:
        allowed = set(resources.skills)
    return tuple(name for name in installed if name in allowed)


def require_visible_skill(name: str, installed: tuple[str, ...]) -> bool:
    return name in visible_skill_names(installed)
