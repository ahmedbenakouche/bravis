"""Notification / task label helpers (split from CollaborativeVersioning.py)."""
from __future__ import annotations

from CollaborativeVersioningLib.ModuleConstants import (
    _NOTIFICATION_TEXT_LEN,
    _TASK_EXCERPT_LEN,
)

def _task_excerpt(description: str) -> str:
    text = " ".join(str(description or "").split())
    if len(text) <= _TASK_EXCERPT_LEN:
        return text
    return text[:_TASK_EXCERPT_LEN].rstrip() + "…"


def _task_junior_logins(task) -> list[str]:
    """Juniors on a task (multi-assign). Falls back to legacy single ``junior``."""
    names = []
    seen = set()
    raw = (task or {}).get("juniors") if isinstance(task, dict) else None
    if isinstance(raw, (list, tuple)):
        candidates = raw
    else:
        one = (task or {}).get("junior") if isinstance(task, dict) else None
        candidates = [one] if one else []
    for item in candidates:
        login = str(item or "").strip()
        key = login.lower()
        if not login or key in seen:
            continue
        seen.add(key)
        names.append(login)
    return names


def _task_juniors_label(task) -> str:
    names = _task_junior_logins(task)
    if not names:
        return "no juniors"
    if len(names) == 1:
        return names[0]
    if len(names) == 2:
        return "%s and %s" % (names[0], names[1])
    return "%s, and %s" % (", ".join(names[:-1]), names[-1])


def _task_status_mark(task) -> str:
    """List / detail mark: in progress, submitted (awaiting review), or closed."""
    status = str((task or {}).get("status") or "").strip().lower()
    if status == "accepted":
        return "✅"
    if status == "submitted":
        return "🔵"
    return "🟠"


def _task_status_label(task) -> str:
    status = str((task or {}).get("status") or "").strip().lower()
    if status == "accepted":
        return "Closed"
    if status == "submitted":
        return "Submitted — awaiting review"
    return "In progress"


def _notification_text(text: str, limit: int = _NOTIFICATION_TEXT_LEN) -> str:
    cleaned = " ".join(str(text or "").split())
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[:limit].rstrip() + "…"


def _notification_list_label(item: dict) -> str:
    kind = str((item or {}).get("kind") or "")
    project = str((item or {}).get("full_name") or "").strip()
    when = str((item or {}).get("when") or (item or {}).get("at_label") or "").strip()
    if kind == "invite":
        label = "Invitation to %s" % (project or "a project")
    else:
        label = _notification_text(item.get("text") or "Project update", 56)
    if when:
        label = "%s · %s" % (label, when)
    return _notification_text(label, _NOTIFICATION_TEXT_LEN)


def _notification_detail_title(item: dict) -> str:
    kind = str((item or {}).get("kind") or "")
    if kind == "invite":
        return "Invitation"
    activity_kind = str((item or {}).get("activity_kind") or "").strip().lower()
    titles = {
        "share": "New share",
        "accept": "New accept",
        "submit": "Review requested",
        "assign": "New task",
        "update": "Task updated",
        "cancel": "Task cancelled",
        "decline": "Review declined",
        "join": "New join",
        "people_add": "People update",
        "people_remove": "People update",
    }
    return titles.get(activity_kind, "Notification")


