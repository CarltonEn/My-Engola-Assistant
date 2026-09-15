"""Persistent chief-of-staff workspace entities recovered from Engola v0.9/v0.10.
All operations are local and owner-scoped; external actions remain elsewhere.
"""
from __future__ import annotations
import time
from core.db import db

def snapshot(limit: int = 50) -> dict:
    with db() as c:
        tasks = c.execute("SELECT id,title,notes,status,priority,due_at,created_at,updated_at FROM tasks ORDER BY CASE priority WHEN 'high' THEN 0 WHEN 'normal' THEN 1 ELSE 2 END, COALESCE(due_at,9999999999), id DESC LIMIT ?", (limit,)).fetchall()
        projects = c.execute("SELECT id,name,goal,status,priority,created_at,updated_at FROM projects ORDER BY updated_at DESC LIMIT ?", (limit,)).fetchall()
        decisions = c.execute("SELECT id,title,rationale,status,created_at,updated_at FROM decisions ORDER BY updated_at DESC LIMIT ?", (limit,)).fetchall()
        reminders = c.execute("SELECT id,title,due_at,status,created_at,updated_at FROM reminders WHERE status='pending' ORDER BY due_at LIMIT ?", (limit,)).fetchall()
    return {
        "tasks": [dict(zip(("id","title","notes","status","priority","due_at","created_at","updated_at"), r)) for r in tasks],
        "projects": [dict(zip(("id","name","goal","status","priority","created_at","updated_at"), r)) for r in projects],
        "decisions": [dict(zip(("id","title","rationale","status","created_at","updated_at"), r)) for r in decisions],
        "reminders": [dict(zip(("id","title","due_at","status","created_at","updated_at"), r)) for r in reminders],
        "now": time.time(),
    }

def create_project(name: str, goal: str = "", priority: str = "normal") -> int:
    if not name.strip(): raise ValueError("Project name is required.")
    if priority not in {"low","normal","high"}: raise ValueError("Invalid priority.")
    now=time.time()
    with db() as c:
        cur=c.execute("INSERT INTO projects(name,goal,status,priority,created_at,updated_at) VALUES(?,?,?,?,?,?)", (name.strip(),goal.strip(),"active",priority,now,now)); c.commit(); return cur.lastrowid

def record_decision(title: str, rationale: str = "") -> int:
    if not title.strip(): raise ValueError("Decision title is required.")
    now=time.time()
    with db() as c:
        cur=c.execute("INSERT INTO decisions(title,rationale,status,created_at,updated_at) VALUES(?,?,?,?,?)", (title.strip(),rationale.strip(),"active",now,now)); c.commit(); return cur.lastrowid

def create_reminder(title: str, due_at: float) -> int:
    if not title.strip(): raise ValueError("Reminder title is required.")
    now=time.time()
    with db() as c:
        cur=c.execute("INSERT INTO reminders(title,due_at,status,created_at,updated_at) VALUES(?,?,?,?,?)", (title.strip(),float(due_at),"pending",now,now)); c.commit(); return cur.lastrowid
