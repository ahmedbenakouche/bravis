"""Small Qt accessors (split from CollaborativeVersioning.py)."""
from __future__ import annotations


def _qt_combo_index(combo) -> int:
    value = combo.currentIndex
    if callable(value):
        value = value()
    return int(value)


def _qt_combo_count(combo) -> int:
    value = combo.count
    if callable(value):
        value = value()
    return int(value)


def _qt_combo_text(combo) -> str:
    value = combo.currentText
    if callable(value):
        value = value()
    return str(value).strip()


def _qt_line_text(widget) -> str:
    value = widget.text
    if callable(value):
        value = value()
    return str(value).strip()


def _qt_table_row_count(table) -> int:
    value = table.rowCount
    if callable(value):
        value = value()
    return int(value)


def _qt_widget_is_valid(widget) -> bool:
    if widget is None:
        return False
    try:
        if hasattr(widget, "isWidgetType"):
            widget.isWidgetType()
        else:
            widget.metaObject()
        return True
    except (RuntimeError, ValueError):
        return False


def _safe_qt_call(widget, method_name: str, *args):
    if not _qt_widget_is_valid(widget):
        return False
    method = getattr(widget, method_name, None)
    if method is None:
        return False
    try:
        method(*args)
        return True
    except (RuntimeError, ValueError):
        return False


