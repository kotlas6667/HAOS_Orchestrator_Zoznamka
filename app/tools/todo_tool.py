from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from datetime import datetime

from app.tools.base import Tool

_TODO_FILE = Path(__file__).resolve().parent.parent.parent / "todo.json"


def _load_todos() -> list[dict[str, Any]]:
    """Load todos from disk."""
    if _TODO_FILE.exists():
        return json.loads(_TODO_FILE.read_text(encoding="utf-8"))
    return []


def _save_todos(todos: list[dict[str, Any]]) -> None:
    """Save todos to disk."""
    _TODO_FILE.write_text(json.dumps(todos, ensure_ascii=False, indent=2), encoding="utf-8")


class TodoTool(Tool):
    name = "todo"
    description = "Manage personal TODO list — add, list, complete, remove tasks."

    async def run(self, prompt: str, context: dict[str, Any] | None = None) -> dict[str, Any]:
        ctx = context or {}
        action = ctx.get("action", "list")
        task_text = ctx.get("task", "").strip()
        task_id = ctx.get("id")

        if action == "add" and task_text:
            # Support multiple tasks separated by |
            tasks = [t.strip() for t in task_text.split("|") if t.strip()]
            if len(tasks) > 1:
                return self._add_multiple(tasks)
            return self._add(task_text)

        if action == "list":
            return self._list()

        if action == "complete" and task_id is not None:
            return self._complete(task_id)

        if action == "remove" and task_id is not None:
            return self._remove(task_id)

        if action == "clear_done":
            return self._clear_done()

        return {
            "status": "error",
            "error": f"Neznáma akcia '{action}' alebo chýbajúce parametre.",
        }

    def _add(self, task: str) -> dict[str, Any]:
        todos = _load_todos()

        # Check for duplicates (case-insensitive, only among pending tasks)
        existing = [t for t in todos if not t["done"] and t["task"].lower() == task.lower()]
        if existing:
            return {
                "status": "duplicate",
                "action": "add",
                "task": task,
                "reply": f"Úloha '{task}' už je v zozname (#{existing[0]['id']}).",
            }

        new_task = {
            "id": (max(t["id"] for t in todos) + 1) if todos else 1,
            "task": task,
            "done": False,
            "created": datetime.now().isoformat(timespec="minutes"),
        }
        todos.append(new_task)
        _save_todos(todos)
        return {
            "status": "success",
            "action": "add",
            "task": task,
            "id": new_task["id"],
            "message": f"Pridané: {task}",
        }

    def _add_multiple(self, tasks: list[str]) -> dict[str, Any]:
        """Add multiple tasks at once, skip duplicates."""
        todos = _load_todos()
        added = []
        skipped = []

        for task in tasks:
            existing = [t for t in todos if not t["done"] and t["task"].lower() == task.lower()]
            if existing:
                skipped.append(task)
                continue
            new_task = {
                "id": (max(t["id"] for t in todos) + 1) if todos else 1,
                "task": task,
                "done": False,
                "created": datetime.now().isoformat(timespec="minutes"),
            }
            todos.append(new_task)
            added.append(task)

        _save_todos(todos)

        parts = []
        if added:
            parts.append(f"Pridané: {', '.join(added)}")
        if skipped:
            parts.append(f"Preskočené (duplicity): {', '.join(skipped)}")

        return {
            "status": "success",
            "action": "add",
            "task": ", ".join(added),
            "added": added,
            "skipped": skipped,
            "message": " | ".join(parts),
        }

    def _list(self) -> dict[str, Any]:
        todos = _load_todos()
        pending = [t for t in todos if not t["done"]]
        done = [t for t in todos if t["done"]]
        return {
            "status": "success",
            "action": "list",
            "pending": pending,
            "done": done,
            "total": len(todos),
            "pending_count": len(pending),
        }

    def _complete(self, task_id: Any) -> dict[str, Any]:
        todos = _load_todos()
        try:
            task_id = int(task_id)
        except (ValueError, TypeError):
            return {"status": "error", "error": f"Neplatné ID: {task_id}"}

        for t in todos:
            if t["id"] == task_id:
                t["done"] = True
                _save_todos(todos)
                return {
                    "status": "success",
                    "action": "complete",
                    "task": t["task"],
                    "message": f"Hotovo: {t['task']}",
                }
        return {"status": "error", "error": f"Úloha s ID {task_id} neexistuje."}

    def _remove(self, task_id: Any) -> dict[str, Any]:
        todos = _load_todos()
        try:
            task_id = int(task_id)
        except (ValueError, TypeError):
            return {"status": "error", "error": f"Neplatné ID: {task_id}"}

        original_len = len(todos)
        todos = [t for t in todos if t["id"] != task_id]
        if len(todos) == original_len:
            return {"status": "error", "error": f"Úloha s ID {task_id} neexistuje."}
        _save_todos(todos)
        return {"status": "success", "action": "remove", "message": f"Úloha {task_id} odstránená."}

    def _clear_done(self) -> dict[str, Any]:
        todos = _load_todos()
        remaining = [t for t in todos if not t["done"]]
        removed = len(todos) - len(remaining)
        _save_todos(remaining)
        return {
            "status": "success",
            "action": "clear_done",
            "message": f"Vyčistené {removed} dokončených úloh.",
        }
