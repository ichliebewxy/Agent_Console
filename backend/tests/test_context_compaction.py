import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from context_compaction import ToolResultCompactionMiddleware, compact_session_history
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage


class FakeStorage:
    def __init__(self):
        self.summary = None

    def load_context_summary(self, *_args):
        return self.summary

    def save_context_summary(self, *_args):
        self.summary = _args[-1]


class FakeModel:
    def __init__(self):
        self.prompts = []

    def invoke(self, prompt):
        self.prompts.append(prompt)
        return SimpleNamespace(content="goal and constraints preserved")


class ContextCompactionTests(unittest.TestCase):
    def test_first_request_is_not_summarized(self):
        storage, model = FakeStorage(), FakeModel()

        messages = compact_session_history([], "x" * 51_000, storage, model, "u", "s")

        self.assertEqual([message.content for message in messages], ["x" * 51_000])
        self.assertEqual(model.prompts, [])

    def test_long_content_triggers_summary_before_fifty_messages_and_reuses_cache(self):
        history = [
            HumanMessage(content="original task " + "x" * 51_000),
            AIMessage(content="done"),
        ]
        storage, model = FakeStorage(), FakeModel()

        first = compact_session_history(history, "continue", storage, model, "u", "s")
        second = compact_session_history(history, "continue", storage, model, "u", "s")

        self.assertEqual(first[-1].content, "continue")
        self.assertEqual(second[-1].content, "continue")
        self.assertIn("goal and constraints preserved", first[0].content)
        self.assertEqual(len(model.prompts), 1)
        self.assertEqual(history[0].content, "original task " + "x" * 51_000)

    def test_large_tool_result_is_archived_without_breaking_call_pair(self):
        with tempfile.TemporaryDirectory() as directory:
            middleware = ToolResultCompactionMiddleware(Path(directory))
            original = "result " + "x" * 210_000
            call = AIMessage(
                content="",
                tool_calls=[{"name": "read_file", "args": {}, "id": "call-1"}],
            )
            result = ToolMessage(content=original, tool_call_id="call-1")
            messages = [HumanMessage(content="inspect"), call, result]

            edited = middleware.prepare(messages)

            self.assertIs(edited[1], call)
            self.assertEqual(edited[2].tool_call_id, "call-1")
            self.assertEqual(messages[2].content, original)
            self.assertIn("Preview:", edited[2].content)
            index = next(Path(directory).glob("*.index.txt"))
            part_paths = [
                Path(line)
                for line in index.read_text(encoding="utf-8").splitlines()[1:]
            ]
            self.assertEqual(
                "".join(path.read_text(encoding="utf-8") for path in part_paths),
                original,
            )

    def test_provider_rejection_retries_once_with_complete_tool_round(self):
        class FakeRequest:
            def __init__(self, messages, model):
                self.messages, self.model = messages, model

            def override(self, *, messages):
                return FakeRequest(messages, self.model)

        with tempfile.TemporaryDirectory() as directory:
            middleware = ToolResultCompactionMiddleware(Path(directory))
            call = AIMessage(
                content="",
                tool_calls=[{"name": "read_file", "args": {}, "id": "call-1"}],
            )
            result = ToolMessage(content="small result", tool_call_id="call-1")
            messages = [
                HumanMessage(content="current goal"),
                AIMessage(content="starting"),
                HumanMessage(content="read it"),
                call,
                result,
            ]
            seen = []

            def handler(request):
                seen.append(request.messages)
                if len(seen) == 1:
                    raise ValueError("prompt_too_long")
                return "ok"

            output = middleware.wrap_model_call(
                FakeRequest(messages, FakeModel()), handler
            )

            self.assertEqual(output, "ok")
            self.assertEqual(len(seen), 2)
            self.assertEqual(seen[1][-2].tool_calls[0]["id"], seen[1][-1].tool_call_id)
            self.assertIn("Current user request", seen[1][0].content)
            self.assertEqual(len(list(Path(directory).glob("*.txt"))), 1)

    def test_message_snip_keeps_tool_call_and_result_together(self):
        with tempfile.TemporaryDirectory() as directory:
            middleware = ToolResultCompactionMiddleware(Path(directory))
            messages = [
                HumanMessage(content="current goal"),
                AIMessage(content="starting"),
                HumanMessage(content="continue"),
            ]
            for number in range(28):
                identifier = f"call-{number}"
                messages.extend(
                    [
                        AIMessage(
                            content="",
                            tool_calls=[
                                {"name": "read_file", "args": {}, "id": identifier}
                            ],
                        ),
                        ToolMessage(content="result", tool_call_id=identifier),
                    ]
                )
            messages.append(AIMessage(content="last response"))

            edited = middleware.prepare(messages)

            self.assertLess(len(edited), len(messages))
            self.assertIn("archived", edited[3].content)
            for index, message in enumerate(edited):
                if isinstance(message, ToolMessage):
                    self.assertIsInstance(edited[index - 1], AIMessage)
                    self.assertEqual(
                        edited[index - 1].tool_calls[0]["id"], message.tool_call_id
                    )


if __name__ == "__main__":
    unittest.main()
