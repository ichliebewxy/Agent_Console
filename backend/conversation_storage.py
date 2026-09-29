"""Persistent chat session storage."""
import json
import os
from datetime import UTC, datetime
from uuid import uuid4

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
        previous_session = data[user_id].get(session_id, {})
        previous_messages = previous_session.get("messages", [])
        serialized = []
        for idx, msg in enumerate(messages):
            previous = previous_messages[idx] if idx < len(previous_messages) else {}
            same_message = (
                previous.get("type") == msg.type
                and previous.get("content") == msg.content
            )
            record = {
                "type": msg.type,
                "content": msg.content,
                "timestamp": (
                    previous.get("timestamp")
                    if same_message and previous.get("timestamp")
                    else datetime.now().isoformat()
                ),
            }
            if same_message:
                for key in ("rag_trace", "artifacts", "plan", "workflow"):
                    if key in previous:
                        record[key] = previous[key]
            if extra_message_data and idx < len(extra_message_data):
                extra = extra_message_data[idx] or {}
                for key in ("rag_trace", "artifacts", "plan", "workflow"):
                    if key in extra:
                        record[key] = extra[key]
            serialized.append(record)

        session_record = {
            "messages": serialized,
            "metadata": metadata if metadata is not None else previous_session.get("metadata", {}),
            "updated_at": datetime.now().isoformat(),
        }
        if "context_summary" in previous_session:
            session_record["context_summary"] = previous_session["context_summary"]
        data[user_id][session_id] = session_record
        self._write(data)

    def load_context_summary(self, user_id: str, session_id: str) -> dict | None:
        summary = self._load().get(user_id, {}).get(session_id, {}).get("context_summary")
        return summary if isinstance(summary, dict) else None

    def save_context_summary(self, user_id: str, session_id: str, summary: dict) -> None:
        data = self._load()
        session = data.get(user_id, {}).get(session_id)
        if not isinstance(session, dict):
            raise ValueError("Cannot summarize a missing conversation")
        session["context_summary"] = summary
        self._write(data)

    def load_goal_state(self, user_id: str, session_id: str) -> dict | None:
        session = self._load().get(user_id, {}).get(session_id, {})
        goal = (session.get("metadata") or {}).get("goal")
        return dict(goal) if isinstance(goal, dict) else None

    def save_goal_state(self, user_id: str, session_id: str, goal: dict | None) -> None:
        data = self._load()
        session = data.setdefault(user_id, {}).setdefault(session_id, {
            "messages": [], "metadata": {}, "updated_at": datetime.now(UTC).isoformat(),
        })
        metadata = dict(session.get("metadata") or {})
        if goal is None:
            metadata.pop("goal", None)
        else:
            metadata["goal"] = dict(goal)
        session["metadata"] = metadata
        session["updated_at"] = datetime.now(UTC).isoformat()
        self._write(data)

    def update_workflow_projection(
        self,
        user_id: str,
        session_id: str,
        run_id: str,
        workflow: dict,
    ) -> bool:
        """Update the UI projection for an existing durable workflow run."""
        data = self._load()
        session = data.get(user_id, {}).get(session_id)
        if not isinstance(session, dict):
            return False
        messages = session.get("messages") or []
        for record in reversed(messages):
            current = record.get("workflow") or {}
            if current.get("run_id") != run_id:
                continue
            record["workflow"] = workflow
            record["plan"] = {
                "objective": workflow.get("objective", ""),
                "steps": workflow.get("steps", []),
                "reflections": (record.get("plan") or {}).get("reflections", []),
            }
            if workflow.get("final_response"):
                record["content"] = workflow["final_response"]
            record["rag_trace"] = workflow.get("rag_trace")
            session["updated_at"] = datetime.now().isoformat()
            self._write(data)
            return True
        return False

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
        self._write(data)
        return True

    def _write(self, data: dict) -> None:
        temporary_path = f"{self.storage_file}.{uuid4().hex}.tmp"
        try:
            with open(temporary_path, "w", encoding="utf-8") as handle:
                json.dump(data, handle, ensure_ascii=False, indent=2)
            os.replace(temporary_path, self.storage_file)
        finally:
            if os.path.exists(temporary_path):
                os.unlink(temporary_path)

    def _load(self) -> dict:
        if not os.path.exists(self.storage_file):
            return {}
        try:
            with open(self.storage_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}
