"""Engola v0.10 local agent engine.

Provider-independent orchestration layer.

KNOW -> THINK -> PREPARE -> ACT -> VERIFY -> REMEMBER

This module handles capabilities that can be executed locally.
It does not pretend that external integrations exist when they
are not actually connected.
"""

import re
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from core.db import db, memory_text, remember
from core.persona import conversational, owner_snapshot


@dataclass
class AgentResult:
    answer: str
    intent: str
    action: Optional[str] = None
    data: Dict[str, Any] = field(default_factory=dict)
    needs_approval: bool = False
    executed: bool = False
    verified: bool = False


def _now() -> float:
    return time.time()


def _create_task(
    title: str,
    notes: str = "",
    priority: str = "normal",
) -> Dict[str, Any]:
    if priority not in {"low", "normal", "high"}:
        priority = "normal"

    now = _now()
    conn = db()

    cur = conn.execute(
        """
        INSERT INTO tasks
        (title, notes, status, priority, due_at, created_at, updated_at)
        VALUES (?, ?, 'todo', ?, NULL, ?, ?)
        """,
        (title, notes, priority, now, now),
    )

    task_id = cur.lastrowid
    conn.commit()

    row = conn.execute(
        """
        SELECT id, title, notes, status, priority,
               due_at, created_at, updated_at
        FROM tasks
        WHERE id = ?
        """,
        (task_id,),
    ).fetchone()

    conn.close()

    return {
        "id": row[0],
        "title": row[1],
        "notes": row[2],
        "status": row[3],
        "priority": row[4],
        "due_at": row[5],
        "created_at": row[6],
        "updated_at": row[7],
    }


def _tasks() -> List[Dict[str, Any]]:
    conn = db()

    rows = conn.execute(
        """
        SELECT id, title, notes, status, priority,
               due_at, created_at, updated_at
        FROM tasks
        ORDER BY
            CASE priority
                WHEN 'high' THEN 0
                WHEN 'normal' THEN 1
                ELSE 2
            END,
            created_at DESC
        """
    ).fetchall()

    conn.close()

    return [
        {
            "id": row[0],
            "title": row[1],
            "notes": row[2],
            "status": row[3],
            "priority": row[4],
            "due_at": row[5],
            "created_at": row[6],
            "updated_at": row[7],
        }
        for row in rows
    ]


def _complete_task(task_id: int) -> Optional[Dict[str, Any]]:
    now = _now()
    conn = db()

    cur = conn.execute(
        """
        UPDATE tasks
        SET status = 'done', updated_at = ?
        WHERE id = ?
        """,
        (now, task_id),
    )

    if cur.rowcount == 0:
        conn.close()
        return None

    conn.commit()

    row = conn.execute(
        """
        SELECT id, title, notes, status, priority,
               due_at, created_at, updated_at
        FROM tasks
        WHERE id = ?
        """,
        (task_id,),
    ).fetchone()

    conn.close()

    return {
        "id": row[0],
        "title": row[1],
        "notes": row[2],
        "status": row[3],
        "priority": row[4],
        "due_at": row[5],
        "created_at": row[6],
        "updated_at": row[7],
    }


def _extract_task_title(text: str) -> str:
    patterns = [
        r"(?:create|add|make)\s+(?:a\s+)?task\s+(?:called|named)\s+(.+)$",
        r"(?:create|add|make)\s+(?:a\s+)?task\s+to\s+(.+)$",
        r"(?:create|add|make)\s+(?:a\s+)?task\s+(.+)$",
        r"(?:remind me to)\s+(.+)$",
        r"(?:task:)\s*(.+)$",
    ]

    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            title = match.group(1).strip()
            title = re.sub(r"\s+", " ", title)
            return title.rstrip(". ")

    return text.strip()


def _extract_memory(text: str) -> Optional[tuple]:
    patterns = [
        r"remember\s+that\s+(.+?)\s+is\s+called\s+(.+)$",
        r"remember\s+that\s+(.+?)\s*=\s*(.+)$",
        r"remember\s+that\s+(.+?)\s+is\s+(.+)$",
        r"remember\s+(.+?)\s*=\s*(.+)$",
    ]

    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            key = match.group(1).strip()
            value = match.group(2).strip()

            if key and value:
                return key, value

    return None


def _briefing() -> Dict[str, Any]:
    tasks = _tasks()

    high_priority = [
        task for task in tasks
        if task["priority"] == "high"
        and task["status"] != "done"
    ]

    active = [
        task for task in tasks
        if task["status"] == "doing"
    ]

    outstanding = [
        task for task in tasks
        if task["status"] != "done"
    ]

    return {
        "high_priority": high_priority,
        "active": active,
        "outstanding": outstanding,
        "total_tasks": len(tasks),
    }


def _format_briefing(data: Dict[str, Any]) -> str:
    outstanding = data["outstanding"]
    high = data["high_priority"]
    active = data["active"]

    lines = ["Your current briefing:"]

    if high:
        lines.append(f"- High priority: {len(high)}")

        for task in high[:5]:
            lines.append(
                f"  • #{task['id']} {task['title']}"
            )
    else:
        lines.append("- High priority: none")

    if active:
        lines.append(f"- In progress: {len(active)}")

        for task in active[:5]:
            lines.append(
                f"  • #{task['id']} {task['title']}"
            )

    lines.append(
        f"- Outstanding tasks: {len(outstanding)}"
    )

    if not outstanding:
        lines.append(
            "- Workspace is clear of outstanding tasks."
        )

    return "\n".join(lines)


def _capability_answer(capability: str) -> AgentResult:
    names = {
        "email": "email",
        "github": "GitHub",
        "browser": "browser",
    }

    name = names[capability]

    return AgentResult(
        answer=(
            f"{name} is not connected as an executable Engola "
            f"capability yet. I won't claim that I can use {name} "
            "until the integration is actually connected, "
            "permissioned, and verified."
        ),
        intent=f"capability.{capability}",
        action="capability.check",
        executed=False,
        verified=False,
    )


def run_local(text: str) -> AgentResult:
    """Route and execute a locally supported Engola request."""

    raw = (text or "").strip()
    normalized = raw.lower()

    if not raw:
        return AgentResult(
            answer="I need a request to work on.",
            intent="empty",
        )

    # ---------------------------------------------------------
    # MEMORY: save
    # ---------------------------------------------------------
    memory = _extract_memory(raw)

    if memory:
        key, value = memory
        remember(key, value)

        return AgentResult(
            answer=f"Remembered: {key} = {value}",
            intent="memory.save",
            action="memory.save",
            data={
                "key": key,
                "value": value,
            },
            executed=True,
            verified=True,
        )

    # ---------------------------------------------------------
    # MEMORY: list
    # ---------------------------------------------------------
    if (
        "show my memory" in normalized
        or "show memory" in normalized
        or "what do you remember" in normalized
        or normalized == "memory"
    ):
        saved = memory_text() or "(no saved memory)"

        return AgentResult(
            answer=saved,
            intent="memory.list",
            action="memory.list",
            data={
                "memory": saved,
            },
            executed=True,
            verified=True,
        )

    # ---------------------------------------------------------
    # TASK: complete
    # ---------------------------------------------------------
    match = re.search(
        r"(?:complete|finish|done with|mark done)"
        r"\s+task\s*#?\s*(\d+)",
        normalized,
    )

    if match:
        task_id = int(match.group(1))
        task = _complete_task(task_id)

        if task is None:
            return AgentResult(
                answer=f"I couldn't find task #{task_id}.",
                intent="task.complete",
                action="task.complete",
                data={
                    "task_id": task_id,
                },
                executed=False,
                verified=False,
            )

        return AgentResult(
            answer=(
                f"Completed task #{task_id}: "
                f"{task['title']}"
            ),
            intent="task.complete",
            action="task.complete",
            data={
                "task": task,
            },
            executed=True,
            verified=True,
        )

    # ---------------------------------------------------------
    # TASK: list
    # ---------------------------------------------------------
    if (
        "show my tasks" in normalized
        or "list my tasks" in normalized
        or normalized in {
            "tasks",
            "my tasks",
        }
    ):
        tasks = _tasks()

        if tasks:
            lines = ["Your tasks:"]

            for task in tasks:
                lines.append(
                    f"- #{task['id']} "
                    f"[{task['status']}] "
                    f"{task['title']} "
                    f"({task['priority']})"
                )

            answer = "\n".join(lines)

        else:
            answer = "You currently have no tasks."

        return AgentResult(
            answer=answer,
            intent="task.list",
            action="task.list",
            data={
                "tasks": tasks,
            },
            executed=True,
            verified=True,
        )

    # ---------------------------------------------------------
    # TASK: create
    # ---------------------------------------------------------
    if (
        re.search(
            r"\b(create|add|make)\s+"
            r"(?:a\s+)?task\b",
            normalized,
        )
        or normalized.startswith("remind me to ")
    ):
        title = _extract_task_title(raw)

        priority = "normal"

        if any(
            word in normalized
            for word in (
                "urgent",
                "critical",
                "asap",
                "high priority",
            )
        ):
            priority = "high"

        task = _create_task(
            title=title,
            priority=priority,
        )

        return AgentResult(
            answer=(
                f"Created task #{task['id']}: "
                f"{task['title']}"
            ),
            intent="task.create",
            action="task.create",
            data={
                "task": task,
            },
            executed=True,
            verified=True,
        )

    # ---------------------------------------------------------
    # BRIEFING
    # ---------------------------------------------------------
    if (
        "briefing" in normalized
        or "what should i focus on" in normalized
        or "what should i do today" in normalized
    ):
        data = _briefing()

        return AgentResult(
            answer=_format_briefing(data),
            intent="briefing",
            action="workspace.briefing",
            data=data,
            executed=True,
            verified=True,
        )

    # ---------------------------------------------------------
    # WORKSPACE STATUS
    # ---------------------------------------------------------
    if (
        "workspace status" in normalized
        or "status of my workspace" in normalized
        or normalized in {
            "status",
            "workspace",
        }
    ):
        tasks = _tasks()

        data = {
            "tasks": tasks,
            "task_count": len(tasks),
            "memory": memory_text() or "",
        }

        memory_state = (
            "saved memory available"
            if data["memory"]
            else "no saved memory"
        )

        return AgentResult(
            answer=(
                f"Workspace status: {len(tasks)} task(s), "
                f"{memory_state}."
            ),
            intent="workspace.status",
            action="workspace.status",
            data=data,
            executed=True,
            verified=True,
        )

    # ---------------------------------------------------------
    # PERMISSIONS
    # ---------------------------------------------------------
    if (
        "show permissions" in normalized
        or "list permissions" in normalized
        or "my permissions" in normalized
        or normalized == "permissions"
    ):
        conn = db()

        rows = conn.execute(
            """
            SELECT name, status, scope
            FROM permissions
            ORDER BY name
            """
        ).fetchall()

        conn.close()

        permissions = [
            {
                "name": row[0],
                "status": row[1],
                "scope": row[2],
            }
            for row in rows
        ]

        if permissions:
            answer = "\n".join(
                f"- {item['name']}: "
                f"{item['status']} "
                f"({item['scope']})"
                for item in permissions
            )
        else:
            answer = "No permissions are configured."

        return AgentResult(
            answer=answer,
            intent="permissions.list",
            action="permissions.list",
            data={
                "permissions": permissions,
            },
            executed=True,
            verified=True,
        )

    # ---------------------------------------------------------
    # OWNER PROFILE
    # ---------------------------------------------------------
    if any(phrase in normalized for phrase in (
        "what do you know about me",
        "what do you know about me?",
        "tell me about myself",
        "what do you remember about me",
        "who am i to you",
    )):
        saved = memory_text() or "No extra saved notes yet."
        answer = (
            "Quite a bit, Sir. You’re Engola Innocent, based in Uganda, and you’re building Engola as a serious personal AI chief of staff. "
            "Your main working territory is accounting, tax and business advisory, alongside technology, AI, Linux, Android and hardware. "
            "Right now we’re also working on the Engola platform itself, your dx7300 revival, and practical accounting workflows.\n\n"
            f"I also have these saved notes: {saved}"
        )
        return AgentResult(
            answer=conversational(answer),
            intent="owner.profile",
            action="owner.profile",
            data={"profile": owner_snapshot(), "saved_memory": saved},
            executed=True,
            verified=True,
        )

    # ---------------------------------------------------------
    # EMAIL CAPABILITY
    # ---------------------------------------------------------
    if any(
        phrase in normalized
        for phrase in (
            "send an email",
            "send email",
            "read my email",
            "check my email",
            "search my email",
            "email me",
        )
    ):
        return _capability_answer("email")

    # ---------------------------------------------------------
    # GITHUB CAPABILITY
    # ---------------------------------------------------------
    if any(
        phrase in normalized
        for phrase in (
            "github",
            "push to github",
            "commit to github",
            "open a pull request",
        )
    ):
        return _capability_answer("github")

    # ---------------------------------------------------------
    # BROWSER CAPABILITY
    # ---------------------------------------------------------
    if any(
        phrase in normalized
        for phrase in (
            "open this website",
            "browse the web",
            "search the web",
            "use the browser",
        )
    ):
        return _capability_answer("browser")

    # ---------------------------------------------------------
    # HELP
    # ---------------------------------------------------------
    if normalized in {
        "help",
        "what can you do",
        "what can you do?",
    }:
        return AgentResult(
            answer=(
                "Right now I can execute local workspace "
                "actions: create, list, and complete tasks; "
                "save and read memory; show a briefing; "
                "show workspace status; and inspect "
                "permissions. Email, browser, and GitHub "
                "are not yet connected as executable "
                "capabilities."
            ),
            intent="help",
            action="help",
            executed=False,
            verified=True,
        )

    # ---------------------------------------------------------
    # HONEST FALLBACK
    # ---------------------------------------------------------
    return AgentResult(
        answer=(
            "I understand the request, but I don't currently "
            "have a verified local capability or connected "
            "provider that can execute or reliably answer it. "
            "I won't invent an answer or pretend an action "
            "happened."
        ),
        intent="unhandled",
        action=None,
        executed=False,
        verified=False,
    )
