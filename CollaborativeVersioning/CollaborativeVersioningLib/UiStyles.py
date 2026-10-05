"""Shared styles for the Collaborative Versioning UI — Ice Clinic theme.

Follows the current 3D Slicer Light / Dark palette so the module does not stay
dark when Slicer is in Light mode.
"""

import os

_STYLE_DIR = os.path.dirname(os.path.abspath(__file__))

IS_DARK = True

# Palette keys are filled by apply_theme().
BG_ELEVATED = ""
BORDER = ""
BORDER_FOCUS = ""
TEXT_SECONDARY = ""
TEXT_MUTED = ""
TEXT_ON_ICE = ""
ACCENT_ICE = ""
ACCENT_ICE_HOVER = ""
ACCENT_MINT = ""
ACCENT_INDIGO = ""
ACCENT_INDIGO_HOVER = ""
ACCENT_AMBER = ""
ACCENT_RED = ""
ACCENT_TEAL = ""
FEED_COLOR_INFO = ""
FEED_COLOR_ERROR = ""
GRAPH_BG = ""
GRAPH_NODE_FILL = ""
GRAPH_NODE_TEXT = ""
GRAPH_EDGE = ""
GRAPH_HINT = ""
GRAPH_TITLE = ""
COMMIT_STATUS_COLORS = {}

DOCK_STYLE = ""
DOCK_LOCKED_STYLE = ""
DOCK_WIDGET_LOCKED_STYLE = ""
DOCK_BTN_LOCKED_STYLE = ""
TABLE_LOCKED_STYLE = ""
DOCK_LOCK_BANNER_STYLE = ""
SECTION_TITLE_LOCKED_STYLE = ""
PLACEHOLDER_LOCKED_STYLE = ""
FEED_LOCKED_STYLE = ""
FIELD_STYLE = ""
SECTION_TITLE_STYLE = ""
PLACEHOLDER_STYLE = ""
SEPARATOR_STYLE = ""
STATUS_OK = ""
STATUS_NEUTRAL = ""
BTN_SECONDARY = ""
BTN_CONNECT = ""
BTN_DEPENDENCY = ""
BTN_HISTORY = ""
BTN_CREATE = ""
BTN_PULL = ""
BTN_PUSH = ""
BTN_DELETE = ""
BTN_PEOPLE = ""
BTN_SAVE_VERSION = ""
BTN_NOTIFICATIONS = ""
NOTIFICATIONS_BADGE_STYLE = ""
FEED_STYLE = ""
MESSAGES_VIEW_STYLE = ""
MESSAGES_HEADER_STYLE = ""
TABLE_STYLE = ""
DIALOG_HINT_STYLE = ""
CHECKED_OUT_LABEL_STYLE = ""


def _palette_dark() -> dict:
    return {
        "BG_ELEVATED": "#383838",
        "BORDER": "#505050",
        "BORDER_FOCUS": "#5b9fd4",
        "TEXT_SECONDARY": "#b8bcc4",
        "TEXT_MUTED": "#888888",
        "TEXT_ON_ICE": "#0f172a",
        "ACCENT_ICE": "#5b9fd4",
        "ACCENT_ICE_HOVER": "#4a8bc0",
        "ACCENT_MINT": "#6ee7b7",
        "ACCENT_INDIGO": "#818cf8",
        "ACCENT_INDIGO_HOVER": "#6366f1",
        "ACCENT_AMBER": "#fbbf24",
        "ACCENT_RED": "#f87171",
        "ACCENT_TEAL": "#2dd4bf",
        "FEED_COLOR_INFO": "#b8d4f0",
        "FEED_COLOR_ERROR": "#f87171",
        "GRAPH_BG": "#2a2a2a",
        "GRAPH_NODE_FILL": "#252525",
        "GRAPH_NODE_TEXT": "#eeeeee",
        "GRAPH_EDGE": "#555555",
        "GRAPH_HINT": "#6b7789",
        "GRAPH_TITLE": "#777777",
    }


def _palette_light() -> dict:
    return {
        "BG_ELEVATED": "#ffffff",
        "BORDER": "#c5cdd6",
        "BORDER_FOCUS": "#3d7eb5",
        "TEXT_SECONDARY": "#4b5563",
        "TEXT_MUTED": "#6b7280",
        "TEXT_ON_ICE": "#ffffff",
        "ACCENT_ICE": "#3d7eb5",
        "ACCENT_ICE_HOVER": "#2f6a9a",
        "ACCENT_MINT": "#0d9488",
        "ACCENT_INDIGO": "#4f46e5",
        "ACCENT_INDIGO_HOVER": "#4338ca",
        "ACCENT_AMBER": "#d97706",
        "ACCENT_RED": "#dc2626",
        "ACCENT_TEAL": "#0f766e",
        "FEED_COLOR_INFO": "#1e4a73",
        "FEED_COLOR_ERROR": "#dc2626",
        "GRAPH_BG": "#f4f6f8",
        "GRAPH_NODE_FILL": "#ffffff",
        "GRAPH_NODE_TEXT": "#1f2933",
        "GRAPH_EDGE": "#9aa3ad",
        "GRAPH_HINT": "#6b7280",
        "GRAPH_TITLE": "#4b5563",
    }


def _qt_int(value) -> int:
    if callable(value):
        value = value()
    return int(value)


def _color_luma(color):
    if color is None:
        return None
    try:
        return 0.299 * color.red() + 0.587 * color.green() + 0.114 * color.blue()
    except Exception:
        pass
    try:
        name = str(color.name())
        if name.startswith("#") and len(name) >= 7:
            red = int(name[1:3], 16)
            green = int(name[3:5], 16)
            blue = int(name[5:7], 16)
            return 0.299 * red + 0.587 * green + 0.114 * blue
    except Exception:
        return None
    return None


def _slicer_style_name() -> str:
    try:
        import qt
        name = qt.QSettings().value("Styles/Style")
        if name:
            return str(name)
    except Exception:
        pass
    try:
        import slicer
        return str(slicer.util.settingsValue("Styles/Style", "") or "")
    except Exception:
        return ""


def _palette_luma():
    try:
        import qt
        import slicer
        app = getattr(slicer, "app", None) or qt.QApplication.instance()
        if app is None:
            return None
        palette = app.palette()
        for role_name in ("Window", "Base", "Button"):
            role = getattr(qt.QPalette, role_name, None)
            if role is None:
                continue
            luma = _color_luma(palette.color(role))
            if luma is not None:
                return luma
    except Exception:
        return None
    return None


def _grab_widget_luma(widget):
    """Read the color Slicer actually paints — stylesheets can ignore QPalette."""
    try:
        import qt
        width = _qt_int(widget.width)
        height = _qt_int(widget.height)
        if width < 16 or height < 16:
            return None
        pixmap = widget.grab(qt.QRect(10, 10, 16, 16))
        image = pixmap.toImage()
        if hasattr(image, "pixelColor"):
            color = image.pixelColor(8, 8)
        else:
            color = qt.QColor(image.pixel(8, 8))
        return _color_luma(color)
    except Exception:
        return None


def _live_chrome_luma():
    """Sample Slicer chrome we do not style (never our dock)."""
    try:
        import slicer
        mw = slicer.util.mainWindow()
    except Exception:
        return None
    if mw is None:
        return None
    names = (
        "ModuleSelectorToolBar",
        "MainToolBar",
        "ModulePanel",
        "PanelDockWidget",
        "DataProbeCollapsibleWidget",
    )
    for name in names:
        try:
            widget = slicer.util.findChild(mw, name)
        except Exception:
            widget = mw.findChild("QWidget", name)
        luma = _grab_widget_luma(widget)
        if luma is not None:
            return luma
    return _grab_widget_luma(mw)


def slicer_prefers_dark() -> bool:
    """True when the visible Slicer UI is dark.

    Prefer the painted chrome color. Settings alone are not enough: the default
    style is named "Slicer" (no Light/Dark in the name), and a style change may
    not be written to disk until restart.
    """
    live = _live_chrome_luma()
    if live is not None:
        return live < 140

    name = _slicer_style_name().strip().lower()
    if name.startswith("light"):
        return False
    if name.startswith("dark"):
        return True

    palette = _palette_luma()
    if palette is not None:
        return palette < 140
    return True


def _down_arrow_url(dark: bool) -> str:
    name = "down-arrow.svg" if dark else "down-arrow-light.svg"
    return os.path.join(_STYLE_DIR, name).replace("\\", "/")


def notification_bell_url(dark: bool | None = None) -> str:
    if dark is None:
        dark = IS_DARK
    name = "notification-bell.svg" if dark else "notification-bell-light.svg"
    return os.path.join(_STYLE_DIR, name).replace("\\", "/")


def apply_theme(force_dark=None) -> bool:
    """Rebuild Ice Clinic styles for the current Slicer Light / Dark theme."""
    dark = slicer_prefers_dark() if force_dark is None else bool(force_dark)
    palette = _palette_dark() if dark else _palette_light()
    globals().update(palette)
    globals()["IS_DARK"] = dark
    globals()["COMMIT_STATUS_COLORS"] = {
        "pushed": palette["ACCENT_MINT"],
        "merged": palette["ACCENT_INDIGO"],
        "local": palette["TEXT_MUTED"],
    }
    _rebuild_styles(dark)
    return dark


def _rebuild_styles(dark: bool) -> None:
    down_arrow = _down_arrow_url(dark)
    btn_disabled = f"""
QPushButton:disabled {{
  background-color: palette(button);
  color: {TEXT_MUTED};
  border: 1px solid palette(mid);
}}
"""
    globals().update({
        "DOCK_STYLE": """
QWidget {
  background-color: palette(window);
  color: palette(window-text);
}
""",
        "DOCK_LOCKED_STYLE": f"""
QWidget {{
  background-color: palette(window);
  color: {TEXT_MUTED};
}}
QLabel {{
  color: {TEXT_MUTED};
}}
QPushButton:disabled {{
  background-color: palette(button);
  color: {TEXT_MUTED};
  border: 1px solid palette(mid);
  font-weight: 600;
  border-radius: 4px;
  padding: 10px;
}}
QTextEdit:disabled {{
  background-color: palette(base);
  color: {TEXT_MUTED};
  border: 1px solid palette(mid);
  border-radius: 4px;
}}
QTableWidget {{
  background-color: palette(base);
  color: {TEXT_MUTED};
  border: 1px solid palette(mid);
}}
QFrame {{
  background-color: palette(mid);
}}
""",
        "DOCK_WIDGET_LOCKED_STYLE": f"""
QDockWidget {{
  background-color: palette(window);
  color: {TEXT_MUTED};
}}
QDockWidget::title {{
  background-color: palette(button);
  color: {TEXT_MUTED};
  padding: 6px;
  border: 1px solid palette(mid);
}}
""",
        "DOCK_BTN_LOCKED_STYLE": f"""
QPushButton {{
  background-color: palette(button);
  color: {TEXT_MUTED};
  border: 1px solid palette(mid);
  font-weight: 600;
  border-radius: 4px;
  padding: 10px;
}}
""",
        "TABLE_LOCKED_STYLE": f"""
QTableWidget {{
  background-color: palette(base);
  color: {TEXT_MUTED};
  gridline-color: palette(mid);
  border: 1px solid palette(mid);
  border-radius: 4px;
}}
QHeaderView::section {{
  background-color: palette(window);
  color: {TEXT_MUTED};
  border: none;
  border-bottom: 1px solid palette(mid);
}}
""",
        "DOCK_LOCK_BANNER_STYLE": f"""
color: {TEXT_MUTED};
font-size: 10px;
font-weight: 600;
font-style: italic;
padding: 8px 10px;
background-color: palette(button);
border: 1px dashed palette(mid);
border-radius: 4px;
""",
        "SECTION_TITLE_LOCKED_STYLE": f"""
font-weight: 600;
font-size: 10px;
color: {TEXT_MUTED};
letter-spacing: 2px;
padding: 0 0 5px 8px;
border-left: 3px solid {BORDER};
""",
        "PLACEHOLDER_LOCKED_STYLE": f"""
color: {TEXT_MUTED};
font-size: 10px;
padding: 8px 4px;
background-color: palette(button);
border-radius: 4px;
border: 1px dashed palette(mid);
""",
        "FEED_LOCKED_STYLE": f"""
QTextEdit {{
  background-color: palette(base);
  color: {TEXT_MUTED};
  font-family: "Segoe UI", sans-serif;
  font-size: 11px;
  border: 1px solid palette(mid);
  border-radius: 4px;
  padding: 8px;
}}
""",
        "FIELD_STYLE": f"""
QLineEdit, QComboBox, qMRMLNodeComboBox {{
  background-color: palette(base);
  color: palette(text);
  border: 1px solid palette(mid);
  border-radius: 4px;
  padding: 6px 8px;
  min-height: 24px;
  selection-background-color: {ACCENT_ICE};
  selection-color: {TEXT_ON_ICE};
}}
QLineEdit:focus, QComboBox:focus, qMRMLNodeComboBox:focus {{
  border: 1px solid {BORDER_FOCUS};
}}
QComboBox::drop-down, qMRMLNodeComboBox QComboBox::drop-down {{
  subcontrol-origin: padding;
  subcontrol-position: center right;
  width: 22px;
  border: none;
  background: transparent;
}}
QComboBox::down-arrow, qMRMLNodeComboBox QComboBox::down-arrow {{
  image: url("{down_arrow}");
  width: 12px;
  height: 12px;
}}
QComboBox QAbstractItemView {{
  background-color: palette(base);
  color: palette(text);
  border: 1px solid palette(mid);
  selection-background-color: {ACCENT_ICE};
  selection-color: {TEXT_ON_ICE};
  outline: none;
}}
QLineEdit:disabled, QComboBox:disabled, qMRMLNodeComboBox:disabled {{
  background-color: palette(window);
  color: {TEXT_MUTED};
  border-color: palette(mid);
}}
""",
        "SECTION_TITLE_STYLE": f"""
font-weight: 600;
font-size: 10px;
color: {ACCENT_ICE};
letter-spacing: 2px;
padding: 0 0 5px 8px;
border-left: 3px solid {ACCENT_ICE};
""",
        "PLACEHOLDER_STYLE": f"""
color: {TEXT_MUTED};
font-size: 10px;
padding: 8px 4px;
background-color: palette(button);
border-radius: 4px;
border: 1px dashed palette(mid);
""",
        "SEPARATOR_STYLE": """
background-color: palette(mid);
max-height: 1px;
border: none;
""",
        "STATUS_OK": f"color: {ACCENT_MINT}; font-weight: 600; font-size: 11px;",
        "STATUS_NEUTRAL": f"color: {TEXT_SECONDARY}; font-weight: 600; font-size: 11px;",
        "BTN_SECONDARY": f"""
QPushButton {{
  background-color: palette(button);
  color: palette(button-text);
  border: 1px solid palette(mid);
  font-weight: 600;
  border-radius: 4px;
  padding: 6px 10px;
}}
QPushButton:hover {{
  border-color: {ACCENT_ICE};
  color: {ACCENT_ICE};
}}
QPushButton:pressed {{ background-color: palette(midlight); }}
{btn_disabled}
""",
        "BTN_CONNECT": f"""
QPushButton {{
  background-color: {ACCENT_ICE};
  color: {TEXT_ON_ICE};
  font-weight: 700;
  padding: 8px 16px;
  min-height: 24px;
  border-radius: 4px;
  border: none;
}}
QPushButton:hover {{ background-color: {ACCENT_ICE_HOVER}; color: {TEXT_ON_ICE}; }}
QPushButton:pressed {{ background-color: {ACCENT_ICE_HOVER}; }}
{btn_disabled}
""",
        "BTN_DEPENDENCY": f"""
QPushButton {{
  background-color: {ACCENT_ICE};
  color: {TEXT_ON_ICE};
  font-weight: 700;
  padding: 10px;
  border-radius: 4px;
  border: none;
}}
QPushButton:hover:enabled {{ background-color: {ACCENT_ICE_HOVER}; color: {TEXT_ON_ICE}; }}
QPushButton:pressed:enabled {{ background-color: {ACCENT_ICE_HOVER}; }}
QPushButton:disabled {{
  background-color: {BG_ELEVATED};
  color: {ACCENT_ICE};
  border: 1px solid {BORDER};
}}
""",
        "BTN_HISTORY": f"""
QPushButton {{
  background-color: {ACCENT_INDIGO};
  color: white;
  font-weight: 700;
  padding: 10px;
  border-radius: 4px;
  border: none;
}}
QPushButton:hover:enabled {{ background-color: {ACCENT_INDIGO_HOVER}; }}
QPushButton:pressed:enabled {{ background-color: {ACCENT_INDIGO_HOVER}; }}
QPushButton:disabled {{
  background-color: {BG_ELEVATED};
  color: {ACCENT_INDIGO};
  border: 1px solid {BORDER};
}}
""",
        "BTN_CREATE": f"""
QPushButton {{
  background-color: palette(button);
  color: {ACCENT_MINT};
  border: 1px solid {ACCENT_MINT};
  font-weight: 700;
  border-radius: 4px;
  padding: 8px;
}}
QPushButton:hover {{
  background-color: {ACCENT_MINT};
  color: {TEXT_ON_ICE};
}}
{btn_disabled}
""",
        "BTN_PULL": f"""
QPushButton {{
  background-color: palette(button);
  color: {ACCENT_ICE};
  border: 1px solid {ACCENT_ICE};
  font-weight: 700;
  border-radius: 4px;
  padding: 8px;
}}
QPushButton:hover {{
  background-color: {ACCENT_ICE};
  color: {TEXT_ON_ICE};
}}
{btn_disabled}
""",
        "BTN_PUSH": f"""
QPushButton {{
  background-color: palette(button);
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
{btn_disabled}
""",
        "BTN_DELETE": f"""
QPushButton {{
  background-color: palette(button);
  color: {ACCENT_RED};
  border: 1px solid {ACCENT_RED};
  font-weight: 700;
  border-radius: 4px;
  padding: 8px;
}}
QPushButton:hover {{
  background-color: {ACCENT_RED};
  color: {TEXT_ON_ICE};
}}
{btn_disabled}
""",
        "BTN_PEOPLE": f"""
QPushButton {{
  background-color: palette(button);
  color: {ACCENT_TEAL};
  border: 1px solid {ACCENT_TEAL};
  font-weight: 700;
  border-radius: 4px;
  padding: 8px;
}}
QPushButton:hover {{
  background-color: {ACCENT_TEAL};
  color: {TEXT_ON_ICE};
}}
{btn_disabled}
""",
        "BTN_SAVE_VERSION": f"""
QPushButton {{
  background-color: palette(button);
  color: {ACCENT_AMBER};
  border: 1px solid {ACCENT_AMBER};
  font-weight: 700;
  border-radius: 4px;
  padding: 8px;
}}
QPushButton:hover {{
  background-color: {ACCENT_AMBER};
  color: {TEXT_ON_ICE};
}}
{btn_disabled}
""",
        "BTN_NOTIFICATIONS": f"""
QPushButton {{
  background-color: palette(button);
  color: {ACCENT_ICE};
  border: 1px solid palette(mid);
  font-weight: 700;
  border-radius: 4px;
  padding: 4px;
}}
QPushButton:hover:enabled {{
  border-color: {ACCENT_ICE};
  color: {ACCENT_ICE};
}}
QPushButton:pressed:enabled {{ background-color: palette(midlight); }}
{btn_disabled}
""",
        "NOTIFICATIONS_BADGE_STYLE": f"""
QLabel {{
  background-color: {ACCENT_RED};
  color: white;
  font-size: 9px;
  font-weight: 700;
  border-radius: 8px;
  padding: 0px;
}}
""",
        "FEED_STYLE": f"""
QTextEdit {{
  background-color: palette(base);
  color: {FEED_COLOR_INFO};
  font-family: "Segoe UI", sans-serif;
  font-size: 11px;
  border: 1px solid palette(mid);
  border-radius: 4px;
  padding: 8px;
}}
""",
        "MESSAGES_VIEW_STYLE": f"""
QTextEdit {{
  background-color: palette(base);
  color: palette(text);
  font-family: "Segoe UI", sans-serif;
  font-size: 11px;
  border: 1px solid palette(mid);
  border-radius: 4px;
  padding: 6px;
}}
""",
        "MESSAGES_HEADER_STYLE": f"""
QPushButton {{
  background-color: {ACCENT_ICE};
  color: {TEXT_ON_ICE};
  font-weight: 700;
  text-align: left;
  padding: 8px 28px 8px 16px;
  min-height: 24px;
  border-radius: 4px;
  border: none;
}}
QPushButton:hover:enabled {{ background-color: {ACCENT_ICE_HOVER}; color: {TEXT_ON_ICE}; }}
QPushButton:checked {{ background-color: {ACCENT_ICE_HOVER}; color: {TEXT_ON_ICE}; }}
QPushButton:pressed:enabled {{ background-color: {ACCENT_ICE_HOVER}; color: {TEXT_ON_ICE}; }}
{btn_disabled}
""",
        "TABLE_STYLE": f"""
QTableWidget {{
  background-color: palette(base);
  alternate-background-color: palette(window);
  color: palette(text);
  gridline-color: palette(mid);
  border: 1px solid palette(mid);
  border-radius: 4px;
  selection-background-color: rgba(91, 159, 212, 0.20);
  selection-color: palette(text);
  outline: none;
}}
QTableWidget::item {{
  padding: 4px 6px;
  border: none;
}}
QHeaderView::section {{
  background-color: palette(window);
  color: {ACCENT_ICE};
  font-weight: 600;
  font-size: 10px;
  letter-spacing: 0.5px;
  padding: 6px 8px;
  border: none;
  border-bottom: 1px solid palette(mid);
}}
QTableWidget QTableCornerButton::section {{
  background-color: palette(window);
  border: none;
}}
""",
        "DIALOG_HINT_STYLE": f"""
font-weight: 500;
font-size: 10px;
color: {TEXT_MUTED};
margin-bottom: 4px;
""",
        "CHECKED_OUT_LABEL_STYLE": f"""
font-size: 10px;
font-weight: 600;
color: {ACCENT_ICE};
margin-bottom: 2px;
""",
    })


apply_theme()
