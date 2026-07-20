import asyncio
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from skill_service import SKILL_REGISTRY, SkillRegistry
from runtime_context import bind_runtime_context
from workspace_tools import (
    _safe_path,
    list_workspace_files,
    read_workspace_file,
    write_workspace_file,
)


class SkillRegistryTests(unittest.TestCase):
    def _registry(self, root: Path) -> SkillRegistry:
        skill = root / "demo"
        skill.mkdir(parents=True)
        (skill / "SKILL.md").write_text(
            "---\nname: demo\ndescription: Demo metadata only\n---\n"
            "# Secret body\nFollow the full workflow.\n",
            encoding="utf-8",
        )
        (skill / "reference.md").write_text("reference content", encoding="utf-8")
        return SkillRegistry(root)

    def test_catalog_is_metadata_only_and_load_is_on_demand(self):
        with tempfile.TemporaryDirectory() as directory:
            registry = self._registry(Path(directory))
            self.assertEqual(registry.names, ("demo",))
            self.assertIn("Demo metadata only", registry.catalog())
            self.assertNotIn("Secret body", registry.catalog())
            self.assertIn("Secret body", registry.load("demo"))

    def test_exact_name_and_resource_root_are_enforced(self):
        with tempfile.TemporaryDirectory() as directory:
            registry = self._registry(Path(directory))
            self.assertTrue(registry.load("../demo").startswith("SKILL_ERROR:"))
            self.assertEqual(registry.read_resource("demo", "reference.md"), "reference content")
            self.assertTrue(
                registry.read_resource("demo", "../outside.txt").startswith("SKILL_ERROR:")
            )

    def test_catalog_budget_is_strict(self):
        with tempfile.TemporaryDirectory() as directory:
            registry = self._registry(Path(directory))
            self.assertLessEqual(len(registry.catalog(max_chars=24)), 24)

    def test_migrated_skill_set_is_available(self):
        self.assertEqual(
            set(SKILL_REGISTRY.names),
            {"agent-builder", "code-review", "mcp-builder", "pdf"},
        )

    def test_workspace_escape_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(ValueError):
                _safe_path("../outside.txt", Path(directory))

    def test_workspace_text_round_trip_and_explicit_overwrite(self):
        async def round_trip(directory: str):
            with patch("runtime_context.AGENT_WORKSPACE_DIR", Path(directory).resolve()):
                with bind_runtime_context("test-user", "test-session"):
                    first = await write_workspace_file.ainvoke(
                        {
                            "path": "reports/result.md",
                            "content": "first",
                            "overwrite": False,
                        }
                    )
                    blocked = await write_workspace_file.ainvoke(
                        {
                            "path": "reports/result.md",
                            "content": "second",
                            "overwrite": False,
                        }
                    )
                    replaced = await write_workspace_file.ainvoke(
                        {
                            "path": "reports/result.md",
                            "content": "second",
                            "overwrite": True,
                        }
                    )
                    self.assertTrue(first.startswith("Wrote"))
                    self.assertTrue(blocked.startswith("WORKSPACE_ERROR:"))
                    self.assertTrue(replaced.startswith("Wrote"))
                    self.assertEqual(
                        await read_workspace_file.ainvoke({"path": "reports/result.md"}),
                        "second",
                    )
                    self.assertIn(
                        "reports/result.md",
                        await list_workspace_files.ainvoke({"pattern": "**/*.md"}),
                    )

        with tempfile.TemporaryDirectory() as directory:
            asyncio.run(round_trip(directory))


if __name__ == "__main__":
    unittest.main()
