import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from langchain_core.tools import tool

from core_tools import CORE_TOOLS, edit_file, glob, read_file, review, write_file
from mcp_config_service import MCPServerStore
from mcp_service import discover_configured_mcp_tools
from runtime_context import bind_runtime_context


class CoreLangChainToolTests(unittest.IsolatedAsyncioTestCase):
    async def test_fixed_five_tool_surface_and_file_round_trip(self):
        self.assertEqual(
            [item.name for item in CORE_TOOLS],
            ["bash", "read_file", "write_file", "edit_file", "glob"],
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            with (
                patch("runtime_context.BACKEND_TMP_DIR", root),
                bind_runtime_context("langchain-user", "langchain-session"),
            ):
                written = await write_file.ainvoke(
                    {"path": "src/demo.txt", "content": "alpha\nbeta\n"}
                )
                original = await read_file.ainvoke({"path": "src/demo.txt"})
                edited = await edit_file.ainvoke(
                    {
                        "path": "src/demo.txt",
                        "old_text": "beta",
                        "new_text": "gamma",
                    }
                )
                matches = await glob.ainvoke({"pattern": "**/*.txt"})
                final = await read_file.ainvoke({"path": "src/demo.txt"})
                escaped = await read_file.ainvoke({"path": "../secret.txt"})

        self.assertIn("Wrote", written)
        self.assertEqual(original, "alpha\nbeta\n")
        self.assertIn("Edited", edited)
        self.assertEqual(matches, "src/demo.txt")
        self.assertEqual(final, "alpha\ngamma\n")
        self.assertTrue(escaped.startswith("TOOL_ERROR:"))

    def test_review_is_non_executing_langchain_tool(self):
        result = json.loads(review.invoke({"command": "shutdown /s"}))
        self.assertEqual(result["behavior"], "deny")
        self.assertEqual(result["rule_id"], "deny-system-destructive")


class MCPStartupDiscoveryTests(unittest.IsolatedAsyncioTestCase):
    async def test_independent_store_is_discovered_into_langchain_tools(self):
        @tool("lookup")
        async def lookup(query: str) -> str:
            """Look up a demo record."""
            return query

        class FakeClient:
            def __init__(self, config):
                self.config = config

            async def get_tools(self):
                return [lookup]

        with tempfile.TemporaryDirectory() as directory:
            store_path = Path(directory) / "mcp_servers.json"
            store = MCPServerStore(store_path)
            store.upsert(
                "demo",
                {
                    "transport": "streamable_http",
                    "url": "https://example.test/mcp",
                    "headers": {},
                },
            )
            with (
                patch("mcp_service.MCP_STORE", store),
                patch("mcp_service.MultiServerMCPClient", FakeClient),
            ):
                result = await discover_configured_mcp_tools(record_init_failure=False)

            self.assertEqual(result.server_count, 1)
            self.assertEqual(result.tool_count, 1)
            self.assertEqual(result.tools[0].name, "mcp_demo_lookup")
            persisted = MCPServerStore(store_path).snapshot()
            self.assertNotIn("tools", persisted["mcpServers"]["demo"])
            self.assertEqual(persisted["mcpServers"]["demo"]["tool_count"], 1)


if __name__ == "__main__":
    unittest.main()
