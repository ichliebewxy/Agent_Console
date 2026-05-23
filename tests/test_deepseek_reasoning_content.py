import sys
from pathlib import Path

from langchain_core.messages import AIMessage, HumanMessage

from backend.conversation_storage import ConversationStorage


def _import_agent_symbols():
    backend_dir = Path(__file__).resolve().parents[1] / "backend"
    if str(backend_dir) not in sys.path:
        sys.path.insert(0, str(backend_dir))

    from agent import DeepSeekReasoningChatModel

    return DeepSeekReasoningChatModel


def test_deepseek_payload_replays_reasoning_content_for_tool_calls():
    chat_model_cls = _import_agent_symbols()
    chat_model = chat_model_cls(
        model="deepseek-v4-flash",
        api_key="test-key",
        api_base="https://api.deepseek.com",
    )
    messages = [
        HumanMessage(content="check weather"),
        AIMessage(
            content="",
            additional_kwargs={"reasoning_content": "I need to call the weather tool."},
            tool_calls=[
                {
                    "name": "get_current_weather",
                    "args": {"city": "Wuhan"},
                    "id": "call_1",
                }
            ],
        ),
    ]

    payload = chat_model._get_request_payload(messages)

    assistant_message = payload["messages"][1]
    assert assistant_message["tool_calls"][0]["function"]["name"] == "get_current_weather"
    assert assistant_message["reasoning_content"] == "I need to call the weather tool."


def test_storage_preserves_reasoning_content(tmp_path):
    storage = ConversationStorage(str(tmp_path / "history.json"))
    messages = [
        HumanMessage(content="hello"),
        AIMessage(
            content="hi",
            additional_kwargs={"reasoning_content": "internal reasoning"},
        ),
    ]

    storage.save("u-1", "s-1", messages)
    loaded = storage.load("u-1", "s-1")

    assert isinstance(loaded[1], AIMessage)
    assert loaded[1].content == "hi"
    assert loaded[1].additional_kwargs["reasoning_content"] == "internal reasoning"
