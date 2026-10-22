"""Module-level constants (split from CollaborativeVersioning.py)."""
from __future__ import annotations

# Change this string to verify that Reload picked up your edits.
_UI_BUILD_TAG = "2026-10-12-notif-read-ids"

ONTOLOGY_COMBO_NONE_LABEL = "None"
ONTOLOGY_COMBO_NONE_INDEX = 0
PROJECT_NONE_LABEL = "None"
# Local clone with no matching GitHub repo (deleted or never published).
PROJECT_NOT_ON_GITHUB_SUFFIX = " (not on GitHub)"
_NOTIFICATIONS_POLL_MS = 15000
_MESSAGES_POLL_MS = 1000
_MESSAGE_MONTHS = (
    "Jan", "Feb", "Mar", "Apr", "May", "Jun",
    "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
)


# Activity that means "remote graph changed" → ⚠ until Compare / Update.
_VERSIONS_SYNC_ACTIVITY_KINDS = frozenset(("share", "accept", "assign"))

_TASK_EXCERPT_LEN = 18
_NOTIFICATION_TEXT_LEN = 72

DISCONNECT_GITHUB_HELP = (
    "The next connection will ask you to sign in again in the browser. "
    "Use this to change account or leave a shared computer."
)

