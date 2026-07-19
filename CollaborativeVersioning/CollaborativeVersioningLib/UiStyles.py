"""Shared styles for the Collaborative Versioning UI — Ice Clinic theme."""

# ── Palette (cool slate, clinical flat) ──────────────────────────────────────
BG_DEEP = "#161920"
BG_PANEL = "#1c2029"
BG_ELEVATED = "#242933"
BG_INPUT = "#2a303c"
BORDER = "#353d4d"
BORDER_FOCUS = "#5b9fd4"
TEXT_PRIMARY = "#eef2f7"
TEXT_SECONDARY = "#a8b4c4"
TEXT_MUTED = "#6b7789"
ACCENT_ICE = "#5b9fd4"
ACCENT_ICE_HOVER = "#4a8bc0"
ACCENT_MINT = "#6ee7b7"
ACCENT_MINT_HOVER = "#4ade9a"
ACCENT_INDIGO = "#818cf8"
ACCENT_INDIGO_HOVER = "#6366f1"
ACCENT_AMBER = "#fbbf24"
ACCENT_RED = "#f87171"

COMMIT_STATUS_COLORS = {
    "pushed": ACCENT_MINT,
    "merged": ACCENT_INDIGO,
    "local": TEXT_MUTED,
}

FEED_COLOR_INFO = "#b8d4f0"
FEED_COLOR_ERROR = ACCENT_RED

# ── Panels ───────────────────────────────────────────────────────────────────
DOCK_STYLE = f"""
QWidget {{
  background-color: {BG_DEEP};
  color: {TEXT_PRIMARY};
}}
"""

# ── Fields ───────────────────────────────────────────────────────────────────
FIELD_STYLE = f"""
QLineEdit, QComboBox, qMRMLNodeComboBox {{
  background-color: {BG_INPUT};
  color: {TEXT_PRIMARY};
  border: 1px solid {BORDER};
  border-radius: 4px;
  padding: 6px 8px;
  min-height: 24px;
  selection-background-color: {ACCENT_ICE};
  selection-color: {BG_DEEP};
}}
QLineEdit:focus, QComboBox:focus, qMRMLNodeComboBox:focus {{
  border: 1px solid {BORDER_FOCUS};
}}
QComboBox::drop-down {{
  border: none;
  width: 20px;
}}
QComboBox::down-arrow {{
  image: none;
  border-left: 4px solid transparent;
  border-right: 4px solid transparent;
  border-top: 5px solid {TEXT_MUTED};
  margin-right: 6px;
}}
QComboBox QAbstractItemView {{
  background-color: {BG_ELEVATED};
  color: {TEXT_PRIMARY};
  border: 1px solid {BORDER};
  selection-background-color: {ACCENT_ICE};
  selection-color: {BG_DEEP};
  outline: none;
}}
QLineEdit:disabled, QComboBox:disabled, qMRMLNodeComboBox:disabled {{
  background-color: {BG_DEEP};
  color: {TEXT_MUTED};
  border-color: {BORDER};
}}
"""

# ── Section headers ──────────────────────────────────────────────────────────
SECTION_TITLE_STYLE = f"""
font-weight: 600;
font-size: 10px;
color: {ACCENT_ICE};
letter-spacing: 2px;
padding: 0 0 5px 8px;
border-left: 3px solid {ACCENT_ICE};
"""

PLACEHOLDER_STYLE = f"""
color: {TEXT_MUTED};
font-size: 10px;
padding: 8px 4px;
background-color: {BG_ELEVATED};
border-radius: 4px;
border: 1px dashed {BORDER};
"""

SEPARATOR_STYLE = f"""
background-color: {BORDER};
max-height: 1px;
border: none;
"""

# ── Status labels ────────────────────────────────────────────────────────────
STATUS_WARNING = f"color: {ACCENT_AMBER}; font-weight: 600; font-size: 11px;"
STATUS_OK = f"color: {ACCENT_MINT}; font-weight: 600; font-size: 11px;"
STATUS_ERROR = f"color: {ACCENT_RED}; font-weight: 600; font-size: 11px;"
STATUS_NEUTRAL = f"color: {TEXT_SECONDARY}; font-weight: 600; font-size: 11px;"

# ── Buttons (flat, clinical) ───────────────────────────────────────────────────
_BTN_DISABLED = f"""
QPushButton:disabled {{
  background-color: {BG_ELEVATED};
  color: {TEXT_MUTED};
  border: 1px solid {BORDER};
}}
"""

BTN_PRIMARY = f"""
QPushButton {{
  background-color: {ACCENT_MINT};
  color: {BG_DEEP};
  font-weight: 700;
  border-radius: 4px;
  border: none;
  padding: 9px 14px;
}}
QPushButton:hover {{ background-color: {ACCENT_MINT_HOVER}; }}
QPushButton:pressed {{ background-color: #34d399; }}
{_BTN_DISABLED}
"""

BTN_SECONDARY = f"""
QPushButton {{
  background-color: {BG_ELEVATED};
  color: {TEXT_PRIMARY};
  border: 1px solid {BORDER};
  font-weight: 600;
  border-radius: 4px;
  padding: 6px 10px;
}}
QPushButton:hover {{
  border-color: {ACCENT_ICE};
  color: {ACCENT_ICE};
}}
QPushButton:pressed {{ background-color: {BG_INPUT}; }}
{_BTN_DISABLED}
"""

BTN_CONNECT = f"""
QPushButton {{
  background-color: {ACCENT_ICE};
  color: {BG_DEEP};
  font-weight: 700;
  padding: 8px 16px;
  border-radius: 4px;
  border: none;
}}
QPushButton:hover {{ background-color: {ACCENT_ICE_HOVER}; color: white; }}
QPushButton:pressed {{ background-color: #3b82c4; }}
{_BTN_DISABLED}
"""

BTN_DEPENDENCY = f"""
QPushButton {{
  background-color: {ACCENT_ICE};
  color: {BG_DEEP};
  font-weight: 700;
  padding: 10px;
  border-radius: 4px;
  border: none;
}}
QPushButton:hover {{ background-color: {ACCENT_ICE_HOVER}; color: white; }}
QPushButton:pressed {{ background-color: #3b82c4; }}
"""

BTN_HISTORY = f"""
QPushButton {{
  background-color: {ACCENT_INDIGO};
  color: white;
  font-weight: 700;
  padding: 10px;
  border-radius: 4px;
  border: none;
}}
QPushButton:hover {{ background-color: {ACCENT_INDIGO_HOVER}; }}
QPushButton:pressed {{ background-color: #4f46e5; }}
"""

BTN_CREATE = f"""
QPushButton {{
  background-color: {BG_ELEVATED};
  color: {ACCENT_MINT};
  border: 1px solid {ACCENT_MINT};
  font-weight: 700;
  border-radius: 4px;
  padding: 8px;
}}
QPushButton:hover {{
  background-color: {ACCENT_MINT};
  color: {BG_DEEP};
}}
{_BTN_DISABLED}
"""

BTN_PULL = f"""
QPushButton {{
  background-color: {BG_ELEVATED};
  color: {ACCENT_ICE};
  border: 1px solid {ACCENT_ICE};
  font-weight: 700;
  border-radius: 4px;
  padding: 8px;
}}
QPushButton:hover {{
  background-color: {ACCENT_ICE};
  color: {BG_DEEP};
}}
{_BTN_DISABLED}
"""

BTN_PUSH = f"""
QPushButton {{
  background-color: {BG_ELEVATED};
  color: {ACCENT_INDIGO};
  border: 1px solid {ACCENT_INDIGO};
  font-weight: 700;
  border-radius: 4px;
  padding: 8px;
}}
QPushButton:hover {{
  background-color: {ACCENT_INDIGO};
  color: white;
}}
{_BTN_DISABLED}
"""

# ── Feed & table ─────────────────────────────────────────────────────────────
FEED_STYLE = f"""
QTextEdit {{
  background-color: {BG_DEEP};
  color: {FEED_COLOR_INFO};
  font-family: "Segoe UI", sans-serif;
  font-size: 11px;
  border: 1px solid {BORDER};
  border-radius: 4px;
  padding: 8px;
}}
"""

TABLE_STYLE = f"""
QTableWidget {{
  background-color: {BG_ELEVATED};
  alternate-background-color: {BG_PANEL};
  color: {TEXT_PRIMARY};
  gridline-color: {BORDER};
  border: 1px solid {BORDER};
  border-radius: 4px;
  selection-background-color: rgba(91, 159, 212, 0.20);
  selection-color: {TEXT_PRIMARY};
  outline: none;
}}
QTableWidget::item {{
  padding: 4px 6px;
  border: none;
}}
QHeaderView::section {{
  background-color: {BG_DEEP};
  color: {ACCENT_ICE};
  font-weight: 600;
  font-size: 10px;
  letter-spacing: 0.5px;
  padding: 6px 8px;
  border: none;
  border-bottom: 1px solid {BORDER};
}}
QTableWidget QTableCornerButton::section {{
  background-color: {BG_DEEP};
  border: none;
}}
"""

DIALOG_HINT_STYLE = f"""
font-weight: 500;
font-size: 10px;
color: {TEXT_MUTED};
margin-bottom: 4px;
"""

DIALOG_HEADER_STYLE = f"""
font-weight: 700;
font-size: 11px;
color: {ACCENT_ICE};
margin-bottom: 4px;
"""
