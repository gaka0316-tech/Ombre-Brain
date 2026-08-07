"""
Darkroom — private reflection space with timed locks.
暗房 — 带锁门时间的私密反思空间。
写下还没想透的想法，锁门时间到了才能查看内容。
"""

import json
import logging
import os
import re
import uuid
from datetime import datetime, timedelta
from typing import Optional

logger = logging.getLogger("ombre_brain.darkroom")

LOCK_FOR_RE = re.compile(
    r"^\s*(\d+)\s*(h|hr|hour|hours|小时|d|day|days|天)\s*$",
    re.IGNORECASE,
)


def _parse_lock_for(value: str) -> Optional[timedelta]:
    """Parse '6h' / '3d' into timedelta."""
    raw = str(value or "").strip()
    if not raw:
        return None
    match = LOCK_FOR_RE.match(raw)
    if not match:
        return None
    amount = int(match.group(1))
    if amount <= 0:
        return None
    unit = match.group(2).lower()
    if unit in {"h", "hr", "hour", "hours", "小时"}:
        return timedelta(hours=amount)
    return timedelta(days=amount)


class DarkroomStore:
    def __init__(self, store_path: str):
        self.store_path = store_path
        os.makedirs(os.path.dirname(store_path), exist_ok=True)
        if not os.path.exists(store_path):
            self._save({"rooms": []})

    def _load(self) -> dict:
        try:
            with open(self.store_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data if isinstance(data, dict) else {"rooms": []}
        except (json.JSONDecodeError, FileNotFoundError):
            return {"rooms": []}

    def _save(self, data: dict) -> None:
        with open(self.store_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def enter(
        self,
        note: str,
        *,
        mood: str = "",
        tags: str = "",
        lock_for: str = "",
        new_room: bool = True,
    ) -> dict:
        """Write a private reflection. Returns door status, never echoes content."""
        text = str(note or "").strip()
        if not text:
            return {"error": "note is empty"}
        if len(text) > 12000:
            return {"error": "note too long (max 12000 chars)"}

        now = datetime.now()
        now_iso = now.isoformat()
        lock_delta = _parse_lock_for(lock_for)
        unlock_at = (now + lock_delta).isoformat() if lock_delta else ""

        data = self._load()
        rooms = data.get("rooms", [])

        tag_list = [t.strip() for t in tags.split(",") if t.strip()] if tags else []

        if new_room or not rooms:
            # New room
            room = {
                "id": uuid.uuid4().hex[:12],
                "created": now_iso,
                "updated": now_iso,
                "visibility": "active",
                "unlock_at": unlock_at,
                "mood": mood.strip(),
                "tags": tag_list,
                "notes": [
                    {
                        "id": uuid.uuid4().hex[:8],
                        "created": now_iso,
                        "content": text,
                    }
                ],
            }
            rooms.append(room)
        else:
            # Continue latest active room
            active = [r for r in rooms if r.get("visibility") == "active"]
            if not active:
                return {"error": "no active room to continue"}
            room = active[-1]
            room["notes"].append(
                {
                    "id": uuid.uuid4().hex[:8],
                    "created": now_iso,
                    "content": text,
                }
            )
            room["updated"] = now_iso
            if lock_delta:
                room["unlock_at"] = unlock_at
            if mood.strip():
                room["mood"] = mood.strip()
            if tag_list:
                room["tags"] = list(set(room.get("tags", []) + tag_list))

        data["rooms"] = rooms
        self._save(data)

        return {
            "status": "entered",
            "room_id": room["id"],
            "notes_count": len(room["notes"]),
            "locked": bool(unlock_at),
            "unlock_at": unlock_at or "unlocked",
        }

    def rooms(self, limit: int = 20, visibility: str = "active") -> list[dict]:
        """List rooms (door status only, no content)."""
        data = self._load()
        all_rooms = data.get("rooms", [])
        if visibility != "all":
            all_rooms = [r for r in all_rooms if r.get("visibility") == visibility]
        all_rooms.sort(key=lambda r: r.get("updated", ""), reverse=True)

        result = []
        now = datetime.now()
        for room in all_rooms[:limit]:
            unlock_at = room.get("unlock_at", "")
            is_locked = False
            if unlock_at:
                try:
                    is_locked = datetime.fromisoformat(unlock_at) > now
                except (ValueError, TypeError):
                    pass
            result.append({
                "room_id": room["id"],
                "created": room.get("created", ""),
                "updated": room.get("updated", ""),
                "notes_count": len(room.get("notes", [])),
                "mood": room.get("mood", ""),
                "tags": room.get("tags", []),
                "locked": is_locked,
                "unlock_at": unlock_at or "unlocked",
                "visibility": room.get("visibility", "active"),
            })
        return result

    def view(self, room_id: str) -> dict:
        """View a room's content. Locked rooms only show door status."""
        data = self._load()
        target = None
        for room in data.get("rooms", []):
            if room.get("id") == room_id:
                target = room
                break
        if not target:
            return {"error": "room not found"}

        now = datetime.now()
        unlock_at = target.get("unlock_at", "")
        is_locked = False
        if unlock_at:
            try:
                is_locked = datetime.fromisoformat(unlock_at) > now
            except (ValueError, TypeError):
                pass

        if is_locked:
            return {
                "room_id": room_id,
                "locked": True,
                "unlock_at": unlock_at,
                "message": "这间暗房还没到开门时间。",
            }

        return {
            "room_id": room_id,
            "created": target.get("created", ""),
            "mood": target.get("mood", ""),
            "tags": target.get("tags", []),
            "locked": False,
            "notes": target.get("notes", []),
        }

    def delete(self, room_id: str, confirm: str = "") -> dict:
        """Delete a room. Must pass confirm='DELETE'."""
        if confirm != "DELETE":
            return {
                "error": "must pass confirm='DELETE' to delete a room",
                "room_id": room_id,
            }
        data = self._load()
        rooms = data.get("rooms", [])
        new_rooms = [r for r in rooms if r.get("id") != room_id]
        if len(new_rooms) == len(rooms):
            return {"error": "room not found"}
        data["rooms"] = new_rooms
        self._save(data)
        return {"status": "deleted", "room_id": room_id}
