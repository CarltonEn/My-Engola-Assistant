"""Provider-neutral local tool definitions from the v0.10 agent-engine milestone.
The registry is intentionally limited to private workspace state. External
side-effecting tools must be added behind capability/permission/approval gates.
"""
from __future__ import annotations
from core import workspace
from core.db import db, remember

class ToolRegistry:
    def definitions(self):
        return [
            {"name":"get_workspace_snapshot","description":"Read current private tasks, projects, memories, decisions and pending reminders."},
            {"name":"create_project","description":"Create a private project."},
            {"name":"record_decision","description":"Record a private decision and rationale."},
            {"name":"create_reminder","description":"Create a private reminder."},
            {"name":"save_memory","description":"Save an explicit durable owner preference or fact."},
        ]
    def execute(self, name: str, args: dict):
        if name == "get_workspace_snapshot": return {"ok": True, "snapshot": workspace.snapshot()}
        if name == "create_project": return {"ok": True, "project_id": workspace.create_project(args.get("name",""), args.get("goal",""), args.get("priority","normal"))}
        if name == "record_decision": return {"ok": True, "decision_id": workspace.record_decision(args.get("title",""), args.get("rationale",""))}
        if name == "create_reminder": return {"ok": True, "reminder_id": workspace.create_reminder(args.get("title",""), args.get("due_at"))}
        if name == "save_memory": remember(str(args.get("key","")), str(args.get("value",""))); return {"ok": True, "key": args.get("key")}
        return {"ok": False, "error": "Unknown local tool."}
