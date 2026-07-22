"""Metadata-first skill catalog and safe on-demand skill content loading."""
import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from threading import RLock

import yaml
from langchain_core.tools import tool

from settings import AGENT_SKILLS_DIR, SKILL_CATALOG_MAX_CHARS, SKILL_CONTENT_MAX_CHARS


_VALID_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_USER_SKILL_NAME = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
_FRONTMATTER_MAX_CHARS = 32_000


@dataclass(frozen=True)
class SkillManifest:
    name: str
    description: str
    root: Path
    manifest: Path
    metadata: dict


def _read_frontmatter(path: Path) -> dict:
    """Read only YAML metadata; the skill body remains unloaded."""
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        if handle.readline().strip() != "---":
            raise ValueError(f"Skill frontmatter must start with '---': {path}")
        lines = []
        size = 0
        for line in handle:
            if line.strip() == "---":
                break
            size += len(line)
            if size > _FRONTMATTER_MAX_CHARS:
                raise ValueError(f"Skill frontmatter is too large: {path}")
            lines.append(line)
        else:
            raise ValueError(f"Skill frontmatter is not closed: {path}")
    parsed = yaml.safe_load("".join(lines)) or {}
    if not isinstance(parsed, dict):
        raise ValueError(f"Skill frontmatter must be a YAML mapping: {path}")
    return parsed


def _bounded_text(path: Path, limit: int) -> str:
    text = path.read_text(encoding="utf-8", errors="replace")
    if len(text) <= limit:
        return text
    return f"{text[:limit]}\n\n...[truncated at {limit} characters]"


class SkillRegistry:
    """Exact-name registry that prevents callers from supplying file paths."""

    def __init__(self, skills_dir: Path = AGENT_SKILLS_DIR):
        self.skills_dir = Path(skills_dir).resolve()
        self._skills: dict[str, SkillManifest] = {}
        self._errors: dict[str, str] = {}
        self._lock = RLock()
        self.refresh()

    def refresh(self) -> None:
        discovered = {}
        errors = {}
        if self.skills_dir.exists():
            for manifest_path in sorted(self.skills_dir.rglob("SKILL.md")):
                manifest = manifest_path.resolve()
                if not manifest.is_relative_to(self.skills_dir):
                    continue
                try:
                    metadata = _read_frontmatter(manifest)
                    name = str(metadata.get("name") or manifest.parent.name).strip()
                    if not _VALID_NAME.fullmatch(name):
                        raise ValueError(f"Invalid skill name '{name}'")
                    if name in discovered:
                        raise ValueError(f"Duplicate skill name '{name}'")
                except (OSError, ValueError, yaml.YAMLError) as exc:
                    relative = manifest.relative_to(self.skills_dir).as_posix()
                    errors[relative] = str(exc).replace(str(self.skills_dir), "<skills>")
                    continue
                description = " ".join(str(metadata.get("description") or name).split())
                discovered[name] = SkillManifest(
                    name=name,
                    description=description[:600],
                    root=manifest.parent,
                    manifest=manifest,
                    metadata=metadata,
                )
        with self._lock:
            self._skills = dict(sorted(discovered.items()))
            self._errors = errors

    def errors(self) -> list[dict[str, str]]:
        with self._lock:
            return [
                {"path": path, "error": error}
                for path, error in sorted(self._errors.items())
            ]

    @property
    def names(self) -> tuple[str, ...]:
        with self._lock:
            return tuple(self._skills)

    def catalog(self, max_chars: int = SKILL_CATALOG_MAX_CHARS) -> str:
        with self._lock:
            entries = list(self._skills.values())
        if not entries:
            return "- (no skills found)"
        lines = [f"- {entry.name}: {entry.description}" for entry in entries]
        text = "\n".join(lines)
        if len(text) <= max_chars:
            return text
        marker = "\n- ... (skill catalog truncated by budget)"
        if max_chars <= len(marker):
            return marker[-max_chars:]
        return text[: max_chars - len(marker)].rstrip() + marker

    def entries(self) -> list[dict]:
        with self._lock:
            entries = list(self._skills.values())
        rows = []
        for entry in entries:
            resources = sum(
                1
                for candidate in entry.root.rglob("*")
                if candidate.is_file() and candidate != entry.manifest
            )
            rows.append(
                {
                    "name": entry.name,
                    "description": entry.description,
                    "path": entry.root.relative_to(self.skills_dir.parent).as_posix(),
                    "resources": resources,
                }
            )
        return rows

    def create(
        self,
        name: str,
        description: str,
        instructions: str,
        *,
        overwrite: bool = False,
    ) -> SkillManifest:
        name = (name or "").strip()
        description = " ".join((description or "").split())
        instructions = (instructions or "").strip()
        if not _USER_SKILL_NAME.fullmatch(name):
            raise ValueError("Skill name must use lowercase letters, digits, and hyphens.")
        if not description:
            raise ValueError("Skill description cannot be empty.")
        if not instructions:
            raise ValueError("Skill instructions cannot be empty.")
        root = (self.skills_dir / name).resolve()
        if root.parent != self.skills_dir:
            raise ValueError("Skill path escapes the configured skills directory.")
        manifest = root / "SKILL.md"
        if manifest.exists() and not overwrite:
            raise FileExistsError(name)
        root.mkdir(parents=True, exist_ok=True)
        frontmatter = yaml.safe_dump(
            {"name": name, "description": description},
            allow_unicode=True,
            sort_keys=False,
        ).strip()
        manifest.write_text(
            f"---\n{frontmatter}\n---\n\n{instructions}\n",
            encoding="utf-8",
        )
        self.refresh()
        with self._lock:
            return self._skills[name]

    def delete(self, name: str) -> bool:
        if not _USER_SKILL_NAME.fullmatch(name or ""):
            return False
        root = (self.skills_dir / name).resolve()
        if root.parent != self.skills_dir or not root.is_dir():
            return False
        shutil.rmtree(root)
        self.refresh()
        return True

    def load(self, name: str) -> str:
        with self._lock:
            entry = self._skills.get(name)
        if entry is None:
            available = ", ".join(self.names) or "(none)"
            return f"SKILL_ERROR: Unknown skill '{name}'. Available: {available}"
        content = _bounded_text(entry.manifest, SKILL_CONTENT_MAX_CHARS)
        root = entry.root.relative_to(self.skills_dir.parent).as_posix()
        return (
            f"Loaded skill: {entry.name}\n"
            f"Skill root: {root}\n"
            "Resolve relative resources with read_skill_resource.\n\n"
            f"<skill name=\"{entry.name}\">\n{content}\n</skill>"
        )

    def read_resource(self, name: str, relative_path: str) -> str:
        with self._lock:
            entry = self._skills.get(name)
        if entry is None:
            return f"SKILL_ERROR: Unknown skill '{name}'."
        target = (entry.root / relative_path).resolve()
        if not target.is_relative_to(entry.root):
            return "SKILL_ERROR: Resource path escapes the skill root."
        if not target.is_file():
            return f"SKILL_ERROR: Resource not found: {relative_path}"
        return _bounded_text(target, SKILL_CONTENT_MAX_CHARS)


SKILL_REGISTRY = SkillRegistry()


@tool
def load_skill(name: str) -> str:
    """Load full instructions for an exact skill name from the visible catalog."""
    return SKILL_REGISTRY.load(name)


@tool
def read_skill_resource(skill_name: str, relative_path: str) -> str:
    """Read a text resource referenced by a loaded skill, relative to its root."""
    return SKILL_REGISTRY.read_resource(skill_name, relative_path)


SKILL_TOOLS = [load_skill, read_skill_resource]
