"""
Standalone reminder store — JSON-based, separate from memory buckets.
独立提醒存储 — 基于JSON，不进记忆桶、不触发embedding。
"""

import json
import logging
import os
import uuid
from datetime import datetime
from typing import Optional

logger = logging.getLogger("ombre_brain.reminder_store")

VALID_STATUSES = {"active", "done", "archived"}


class ReminderStore:
    def __init__(self, store_path: str):
        self.store_path = store_path
        os.makedirs(os.path.dirname(store_path), exist_ok=True)
        if not os.path.exists(store_path):
            self._save([])

    def _load(self) -> list[dict]:
        try:
            with open(self.store_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data if isinstance(data, list) else []
        except (json.JSONDecodeError, FileNotFoundError):
            return []

    def _save(self, reminders: list[dict]) -> None:
        with open(self.store_path, "w", encoding="utf-8") as f:
            json.dump(reminders, f, ensure_ascii=False, indent=2)

    def create(
        self,
        title: str,
        content: str = "",
        due_at: str = "",
    ) -> dict:
        """Create a new reminder."""
        entry = {
            "id": uuid.uuid4().hex[:12],
            "title": title.strip(),
            "content": content.strip(),
            "status": "active",
            "due_at": due_at.strip() if due_at else "",
            "created": datetime.now().isoformat(),
            "updated": datetime.now().isoformat(),
        }
        reminders = self._load()
        reminders.append(entry)
        self._save(reminders)
        return entry

    def list(self, status: str = "active", limit: int = 50) -> list[dict]:
        """List reminders filtered by status. status='all' returns everything."""
        reminders = self._load()
        if status != "all":
            reminders = [r for r in reminders if r.get("status") == status]
        reminders.sort(key=lambda r: r.get("created", ""), reverse=True)
        return reminders[:limit]

    def get(self, reminder_id: str) -> Optional[dict]:
        """Get a single reminder by ID."""
        for r in self._load():
            if r.get("id") == reminder_id:
                return r
        return None

    def update(
        self,
        reminder_id: str,
        *,
        title: str = "",
        content: str = "",
        status: str = "",
        due_at: str = "",
    ) -> Optional[dict]:
        """Update a reminder's fields. Only non-empty values are changed."""
        reminders = self._load()
        target = None
        for r in reminders:
            if r.get("id") == reminder_id:
                target = r
                break
        if not target:
            return None

        if title.strip():
            target["title"] = title.strip()
        if content.strip():
            target["content"] = content.strip()
        if status and status in VALID_STATUSES:
            target["status"] = status
            if status == "done":
                target["done_at"] = datetime.now().isoformat()
        if due_at.strip():
            target["due_at"] = due_at.strip()
        target["updated"] = datetime.now().isoformat()

        self._save(reminders)
        return target

    def delete(self, reminder_id: str) -> bool:
        """Permanently delete a reminder."""
        reminders = self._load()
        new_list = [r for r in reminders if r.get("id") != reminder_id]
        if len(new_list) == len(reminders):
            return False
        self._save(new_list)
        return True
