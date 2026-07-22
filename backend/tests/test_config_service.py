import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from bash_tool import bash, review_bash_command
from config_service import ConfigStore
from fastapi import FastAPI
from fastapi.testclient import TestClient
from routes_config import router as config_router
from runtime_context import bind_runtime_context
from skill_service import SkillRegistry
from mcp_service import _adapter_config, _runtime_tool_name


class ConfigServiceTests(unittest.TestCase):
    def test_stdio_mcp_command_is_reviewed_and_runtime_names_do_not_collide(self):
        with self.assertRaises(PermissionError):
            _adapter_config(
                "unsafe",
                {"transport": "stdio", "command": "cmd", "args": ["/c", "whoami"]},
            )
        with self.assertRaises(PermissionError):
            _adapter_config(
                "inline",
                {"transport": "stdio", "command": "python", "args": ["-c", "print(1)"]},
            )
        with self.assertRaises(PermissionError):
            _adapter_config(
                "remote-install",
                {"transport": "stdio", "command": "npx", "args": ["-y", "demo-mcp"]},
            )
        safe = _adapter_config(
            "safe",
            {
                "transport": "stdio",
                "command": "npx",
                "args": ["--no-install", "demo-mcp"],
            },
        )
        self.assertEqual(safe["command"], "npx")
        used = set()
        first = _runtime_tool_name("server", "lookup.one", used)
        second = _runtime_tool_name("server", "lookup+one", used)
        self.assertNotEqual(first, second)

    def test_config_and_bash_audit_routes_are_readable(self):
        app = FastAPI()
        app.include_router(config_router)
        client = TestClient(app)
        config_response = client.get("/runtime-config")
        self.assertEqual(config_response.status_code, 200)
        config = config_response.json()["config"]
        self.assertIn("mcpServers", config)
        self.assertIn("skills", config)
        self.assertIn("permissions", config)
        self.assertEqual(client.get("/bash-audit").status_code, 200)

    def test_config_normalizes_mcp_and_persists_discovery(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            path.write_text(
                json.dumps(
                    {
                        "mcpServers": {
                            "demo": {
                                "type": "streamableHttp",
                                "url": "https://example.test/mcp",
                            }
                        }
                    }
                ),
                encoding="utf-8",
            )
            store = ConfigStore(path)
            self.assertEqual(
                store.snapshot()["mcpServers"]["demo"]["transport"],
                "streamable_http",
            )
            store.update_mcp_discovery(
                {"demo": {"tools": [{"name": "lookup"}], "error": ""}}
            )
            reloaded = ConfigStore(path).snapshot()
            self.assertEqual(reloaded["mcpServers"]["demo"]["tools"][0]["name"], "lookup")
            self.assertIn("bash", reloaded["permissions"])

    def test_public_runtime_config_redacts_composite_secrets_and_url_queries(self):
        with tempfile.TemporaryDirectory() as directory:
            store = ConfigStore(Path(directory) / "config.json")
            store.upsert_mcp_server(
                "private",
                {
                    "transport": "streamable_http",
                    "url": "https://user:real-secret@example.test/mcp?token=real-secret&city=beijing#real-secret",
                    "headers": {"Authorization": "Bearer real-secret ${TOKEN}"},
                    "args": ["--header", "Authorization: Bearer real-secret", "real-secret"],
                },
            )
            public = store.snapshot(public=True)["mcpServers"]["private"]
            self.assertNotIn("real-secret", str(public))
            self.assertIn("***configured***", public["headers"]["Authorization"])
            self.assertNotIn("real-secret", public["url"])
            self.assertNotIn("real-secret", public["args"])
            self.assertNotIn("real-secret", public["url"])

    def test_frontend_api_can_add_mcp_and_skill(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            store = ConfigStore(root / "config.json")
            registry = SkillRegistry(root / "skills")
            app = FastAPI()
            app.include_router(config_router)
            client = TestClient(app)
            with (
                patch("routes_config.CONFIG_STORE", store),
                patch("routes_config.SKILL_REGISTRY", registry),
                patch("routes_config.refresh_skill_catalog", return_value=[]),
                patch(
                    "routes_config.discover_configured_mcp_tools",
                    new=AsyncMock(),
                ),
                patch("routes_config._reload_main_agent", new=AsyncMock()),
            ):
                mcp_response = client.post(
                    "/runtime-config/mcp",
                    json={
                        "name": "demo",
                        "transport": "streamable_http",
                        "url": "https://example.test/mcp",
                    },
                )
                self.assertEqual(mcp_response.status_code, 200)
                self.assertIn("demo", store.snapshot()["mcpServers"])

                skill_response = client.post(
                    "/runtime-config/skills",
                    json={
                        "name": "demo-skill",
                        "description": "Use for demo tasks",
                        "instructions": "# Workflow\n\nComplete the demo task.",
                    },
                )
                self.assertEqual(skill_response.status_code, 200)
                self.assertIn("demo-skill", registry.names)

    def test_user_can_create_and_delete_skill(self):
        with tempfile.TemporaryDirectory() as directory:
            registry = SkillRegistry(Path(directory))
            registry.create("demo-skill", "Use for demos", "# Workflow\n\nDo the task.")
            self.assertIn("demo-skill", registry.names)
            self.assertIn("Do the task", registry.load("demo-skill"))
            self.assertTrue(registry.delete("demo-skill"))
            self.assertNotIn("demo-skill", registry.names)


class BashPermissionTests(unittest.IsolatedAsyncioTestCase):
    async def test_denied_command_never_starts_local_process(self):
        runtime = AsyncMock()
        audit = Mock()
        with (
            patch("bash_tool.run_local_command", new=runtime),
            patch("bash_tool.record_bash_audit", new=audit),
            bind_runtime_context("permission-user", "permission-session"),
        ):
            result = await bash.ainvoke({"command": "python -c \"print(1)\" && shutdown /s"})
        self.assertTrue(result.startswith("PERMISSION_DENIED:"))
        runtime.assert_not_awaited()
        audit.assert_called_once()

    def test_default_deny_and_safe_allow(self):
        self.assertEqual(review_bash_command("unknown-tool action").behavior, "deny")
        self.assertEqual(review_bash_command("opencli list -f json").behavior, "allow")
        self.assertEqual(
            review_bash_command("opencli hackernews top --limit 1 -f json").behavior,
            "allow",
        )
        self.assertEqual(review_bash_command("echo ok & whoami").rule_id, "deny-shell-chaining")
        self.assertEqual(review_bash_command('echo ^"x & whoami').rule_id, "deny-shell-chaining")
        self.assertEqual(
            review_bash_command('python -c "print(\'a;b\')"').behavior,
            "allow",
        )
        self.assertEqual(
            review_bash_command("opencli plugin install demo").rule_id,
            "deny-opencli-high-risk",
        )
        self.assertEqual(
            review_bash_command("opencli browser click --ref e1").rule_id,
            "authorize-opencli-external-write",
        )
        self.assertEqual(
            review_bash_command(
                "opencli browser click --ref e1",
                user_authorized_side_effect=True,
            ).behavior,
            "allow",
        )
        self.assertEqual(
            review_bash_command("opencli reddit reply --id 1").rule_id,
            "authorize-opencli-unknown",
        )
        self.assertEqual(
            review_bash_command(
                "opencli reddit lookup --id 1",
                opencli_access="read",
            ).rule_id,
            "allow-opencli-registry-read",
        )
        self.assertEqual(
            review_bash_command(
                "opencli reddit lookup --id 1",
                opencli_access="p4",
            ).rule_id,
            "deny-opencli-p4",
        )
        self.assertEqual(
            review_bash_command("opencli browser lcagent keys Enter").rule_id,
            "authorize-opencli-unknown",
        )
        self.assertEqual(
            review_bash_command(
                "opencli reddit reply --id 1",
                user_authorized_side_effect=True,
            ).behavior,
            "allow",
        )


if __name__ == "__main__":
    unittest.main()
