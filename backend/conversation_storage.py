"""Persistent chat session storage."""
import json
import os
from datetime import datetime

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage


class ConversationStorage:
    def __init__(self, storage_file: str | None = None):
        if storage_file:
            self.storage_file = os.path.abspath(storage_file)
            return
        package_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        data_dir = os.path.join(package_root, "data")
        os.makedirs(data_dir, exist_ok=True)
        self.storage_file = os.path.join(data_dir, "customer_service_history.json")

    def save(self, user_id: str, session_id: str, messages: list, metadata: dict | None = None, extra_message_data: list | None = None):
        data = self._load()
        data.setdefault(user_id, {})
        serialized = []
        for idx, msg in enumerate(messages):
            record = {
                "type": msg.type,
                "content": msg.content,
                "timestamp": datetime.now().isoformat(),
            }
            if extra_message_data and idx < len(extra_message_data):
                extra = extra_message_data[idx] or {}
                if "rag_trace" in extra:
                    record["rag_trace"] = extra["rag_trace"]
            serialized.append(record)

        data[user_id][session_id] = {
            "messages": serialized,
            "metadata": metadata or {},
            "updated_at": datetime.now().isoformat(),
        }
        with open(self.storage_file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def load(self, user_id: str, session_id: str) -> list:
        data = self._load()
        if user_id not in data or session_id not in data[user_id]:
            return []
        messages = []
        for item in data[user_id][session_id].get("messages", []):
            if item.get("type") == "human":
                messages.append(HumanMessage(content=item.get("content", "")))
            elif item.get("type") == "ai":
                messages.append(AIMessage(content=item.get("content", "")))
            elif item.get("type") == "system":
                messages.append(SystemMessage(content=item.get("content", "")))
        return messages

    def list_sessions(self, user_id: str) -> list:
        data = self._load()
        return list(data.get(user_id, {}).keys())

    def delete_session(self, user_id: str, session_id: str) -> bool:
        data = self._load()
        if user_id not in data or session_id not in data[user_id]:
            return False
        del data[user_id][session_id]
        if not data[user_id]:
            del data[user_id]
        with open(self.storage_file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return True

    def _load(self) -> dict:
        if not os.path.exists(self.storage_file):
            return {}
        try:
            with open(self.storage_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}
