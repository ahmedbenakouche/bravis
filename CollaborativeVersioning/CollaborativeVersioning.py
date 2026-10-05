import html
import importlib
import logging
import os
import re
import shutil
import sys
import time
from datetime import datetime

import ctk
import qt
import slicer
import vtk
from slicer.ScriptedLoadableModule import *
from slicer.i18n import tr as _
from slicer.i18n import translate
from slicer.util import VTKObservationMixin

import CollaborativeVersioningLib
import CollaborativeVersioningLib.GraphCanvas
import CollaborativeVersioningLib.UiStyles

# Change this string to verify that Reload picked up your edits.
_UI_BUILD_TAG = "2026-10-05-remove-dead-code"

_LIB_MODULE_NAMES = (
    "CollaborativeVersioningLib.UiStyles",
    "CollaborativeVersioningLib.DataManager",
    "CollaborativeVersioningLib.GitHubAuth",
    "CollaborativeVersioningLib.OntologyLoader",
    "CollaborativeVersioningLib.GraphCanvas",
    "CollaborativeVersioningLib",
)


def _refreshLibModules() -> None:
    for module_name in _LIB_MODULE_NAMES:
        module = sys.modules.get(module_name)
        if module is not None:
            importlib.reload(module)


_refreshLibModules()

from CollaborativeVersioningLib.DataManager import DataManager
from CollaborativeVersioningLib.GitHubAuth import (
    GitHubAuthError,
    GitHubMissingDeletePermissionError,
    GitHubNotSignedInError,
    accept_project_invitation,
    commit_and_push,
    commit_local_version,
    connect_session,
    create_private_repository,
    current_login,
    decline_project_invitation,
    delete_owned_repository,
    ensure_tools,
    ensure_project_info_branch,
    extract_project_version,
    find_gh,
    forget_people_access,
    has_delete_repo_scope,
    inspect_local_project,
    invite_project_colleague,
    list_accessible_repos,
    incoming_invitations_fetch_args,
    notification_review_fetch_args,
    parse_incoming_invitations_output,
    parse_share_request_search_output,
    list_project_people,
    parse_project_messages_output,
    normalize_task_title,
    project_messages_fetch_args,
    project_messages_put_args,
    build_project_message,
    is_project_messages_conflict,
    logout_github_cli,
    open_delete_permission_window,
    open_login_window,
    open_or_update_local_project,
    people_access_for,
    read_project_history,
    remove_project_colleague,
    cancel_project_invitation,
    set_wait_callback,
    share_local_versions,
    submit_share_request,
    fetch_share_request_sha,
    accept_share_request,
    decline_share_request,
    suggest_github_usernames,
    PEOPLE_ACCESS_APPROVAL,
)
from CollaborativeVersioningLib.OntologyLoader import (
    _qt_input_text,
    OntologyEditorDialog,
    OntologyJsonHelpDialog,
    ONTOLOGY_JSON_FILE_FILTER,
    document_to_graph_specs,
    load_ontology_file,
    load_preset,
    preset_choices,
    save_ontology_file,
)
from CollaborativeVersioningLib.UiStyles import (
    ACCENT_ICE,
    ACCENT_INDIGO,
    ACCENT_MINT,
    BTN_CONNECT,
    BTN_CREATE,
    BTN_DELETE,
    BTN_DEPENDENCY,
    BTN_HISTORY,
    BTN_PEOPLE,
    BTN_PULL,
    BTN_PUSH,
    BTN_SAVE_VERSION,
    BTN_SECONDARY,
    BTN_NOTIFICATIONS,
    CHECKED_OUT_LABEL_STYLE,
    COMMIT_STATUS_COLORS,
    DIALOG_HINT_STYLE,
    DOCK_LOCK_BANNER_STYLE,
    DOCK_BTN_LOCKED_STYLE,
    DOCK_LOCKED_STYLE,
    DOCK_STYLE,
    DOCK_WIDGET_LOCKED_STYLE,
    FEED_COLOR_ERROR,
    FEED_COLOR_INFO,
    FEED_LOCKED_STYLE,
    FEED_STYLE,
    FIELD_STYLE,
    MESSAGES_HEADER_STYLE,
    MESSAGES_VIEW_STYLE,
    NOTIFICATIONS_BADGE_STYLE,
    PLACEHOLDER_LOCKED_STYLE,
    PLACEHOLDER_STYLE,
    SECTION_TITLE_LOCKED_STYLE,
    SECTION_TITLE_STYLE,
    SEPARATOR_STYLE,
    STATUS_NEUTRAL,
    STATUS_OK,
    TABLE_LOCKED_STYLE,
    TABLE_STYLE,
    TEXT_MUTED,
    TEXT_SECONDARY,
    notification_bell_url,
)

ONTOLOGY_COMBO_NONE_LABEL = "None"
ONTOLOGY_COMBO_NONE_INDEX = 0
PROJECT_NONE_LABEL = "None"
_NOTIFICATIONS_POLL_MS = 15000
_MESSAGES_POLL_MS = 1000
_MESSAGE_MONTHS = (
    "Jan", "Feb", "Mar", "Apr", "May", "Jun",
    "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
)

_STYLE_EXPORTS = (
    "ACCENT_ICE",
    "ACCENT_INDIGO",
    "ACCENT_MINT",
    "BTN_CONNECT",
    "BTN_CREATE",
    "BTN_DELETE",
    "BTN_DEPENDENCY",
    "BTN_HISTORY",
    "BTN_PEOPLE",
    "BTN_PULL",
    "BTN_PUSH",
    "BTN_SAVE_VERSION",
    "BTN_SECONDARY",
    "BTN_NOTIFICATIONS",
    "CHECKED_OUT_LABEL_STYLE",
    "COMMIT_STATUS_COLORS",
    "DIALOG_HINT_STYLE",
    "DOCK_LOCK_BANNER_STYLE",
    "DOCK_BTN_LOCKED_STYLE",
    "DOCK_LOCKED_STYLE",
    "DOCK_STYLE",
    "DOCK_WIDGET_LOCKED_STYLE",
    "FEED_COLOR_ERROR",
    "FEED_COLOR_INFO",
    "FEED_LOCKED_STYLE",
    "FEED_STYLE",
    "FIELD_STYLE",
    "MESSAGES_HEADER_STYLE",
    "MESSAGES_VIEW_STYLE",
    "NOTIFICATIONS_BADGE_STYLE",
    "PLACEHOLDER_LOCKED_STYLE",
    "PLACEHOLDER_STYLE",
    "SECTION_TITLE_LOCKED_STYLE",
    "SECTION_TITLE_STYLE",
    "SEPARATOR_STYLE",
    "STATUS_NEUTRAL",
    "STATUS_OK",
    "TABLE_LOCKED_STYLE",
    "TABLE_STYLE",
    "TEXT_MUTED",
    "TEXT_SECONDARY",
)


def _bindIceClinicTheme() -> None:
    from CollaborativeVersioningLib import UiStyles

    UiStyles.apply_theme()
    module_globals = globals()
    for name in _STYLE_EXPORTS:
        module_globals[name] = getattr(UiStyles, name)


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


class ProjectConfigDialog(qt.QDialog):
    """Configuration dialog shown when creating a new project."""

    def __init__(self, parent=None) -> None:
        qt.QDialog.__init__(self, parent)
        self.setWindowTitle("New project")
        self.setMinimumWidth(420)
        self.setModal(True)

        layout = qt.QVBoxLayout(self)
        layout.setSpacing(10)

        form = qt.QFormLayout()
        form.setSpacing(8)
        self.nameEdit = qt.QLineEdit()
        self.nameEdit.setPlaceholderText("My annotation project")
        self.nameEdit.setStyleSheet(FIELD_STYLE)
        form.addRow("Project name:", self.nameEdit)

        self.descriptionEdit = qt.QLineEdit()
        self.descriptionEdit.setPlaceholderText("Optional short description")
        self.descriptionEdit.setStyleSheet(FIELD_STYLE)
        form.addRow("Description:", self.descriptionEdit)
        layout.addLayout(form)

        buttons = qt.QHBoxLayout()
        buttons.addStretch(1)
        cancelButton = qt.QPushButton("Cancel")
        createButton = qt.QPushButton("Create")
        cancelButton.setStyleSheet(BTN_SECONDARY)
        createButton.setStyleSheet(BTN_CREATE)
        cancelButton.connect("clicked()", self.reject)
        createButton.connect("clicked()", self.accept)
        buttons.addWidget(cancelButton)
        buttons.addWidget(createButton)
        layout.addLayout(buttons)
        self.nameEdit.setFocus()

    def values(self) -> dict:
        return {
            "name": self.nameEdit.text.strip(),
            "description": self.descriptionEdit.text.strip(),
        }


class NotificationsDialog(qt.QDialog):
    """Bell popup: click a notification to open it."""

    def __init__(self, parent=None, items=None, empty_text="") -> None:
        qt.QDialog.__init__(self, parent)
        self.setWindowTitle("Notifications")
        self.setMinimumWidth(360)
        self.setModal(True)
        self.chosen = None
        self._items = list(items or [])
        layout = qt.QVBoxLayout(self)
        layout.setSpacing(10)
        hint = qt.QLabel(empty_text if not self._items else "Click a notification to open it.")
        hint.setWordWrap(True)
        hint.setStyleSheet(DIALOG_HINT_STYLE)
        layout.addWidget(hint)
        if self._items:
            group = qt.QButtonGroup(self)
            for index, item in enumerate(self._items):
                kind = item.get("kind") or "review"
                project = item.get("full_name") or "a project"
                if kind == "invite":
                    label = "You were invited to %s" % project
                    tip = "Join or decline this project"
                else:
                    author = item.get("author") or "A colleague"
                    label = "%s sent a version to review on %s" % (author, project)
                    tip = "Open this version to review"
                button = qt.QPushButton(label)
                button.setStyleSheet(BTN_SECONDARY)
                button.setToolTip(tip)
                group.addButton(button, index)
                layout.addWidget(button)
            try:
                group.connect("idClicked(int)", self._onPick)
            except (TypeError, RuntimeError, AttributeError):
                group.connect("buttonClicked(int)", self._onPick)
            self._group = group
        closeButton = qt.QPushButton("Close")
        closeButton.setStyleSheet(BTN_SECONDARY)
        closeButton.connect("clicked()", self.reject)
        layout.addWidget(closeButton)

    def _onPick(self, index) -> None:
        try:
            index = int(index)
        except (TypeError, ValueError):
            return
        if 0 <= index < len(self._items):
            self.chosen = self._items[index]
        self.close()


class PeopleDialog(qt.QDialog):
    """See who is on the project. Owners can add or remove a colleague."""

    def __init__(self, parent=None, people=None, can_add=False) -> None:
        qt.QDialog.__init__(self, parent)
        self.setWindowTitle("People")
        self.setMinimumWidth(460)
        self.setModal(True)
        self._people = []
        self._can_add = bool(can_add)
        self._add_handler = None
        self._remove_handler = None

        layout = qt.QVBoxLayout(self)
        layout.setSpacing(10)

        people_label = qt.QLabel("People on this project:")
        people_label.setStyleSheet(DIALOG_HINT_STYLE)
        layout.addWidget(people_label)

        self.peopleList = qt.QListWidget()
        self.peopleList.setMinimumHeight(110)
        self.peopleList.setMaximumHeight(170)
        try:
            self.peopleList.setWordWrap(True)
        except (TypeError, AttributeError, RuntimeError):
            pass
        if self._can_add:
            self.peopleList.setSelectionMode(qt.QAbstractItemView.SingleSelection)
        else:
            self.peopleList.setSelectionMode(qt.QAbstractItemView.NoSelection)
        self.peopleList.setStyleSheet(FIELD_STYLE)
        layout.addWidget(self.peopleList)

        self.addPanel = qt.QWidget()
        add_layout = qt.QVBoxLayout(self.addPanel)
        add_layout.setContentsMargins(0, 0, 0, 0)
        add_layout.setSpacing(10)
        form = qt.QFormLayout()
        form.setSpacing(8)
        self.usernameEdit = qt.QLineEdit()
        self.usernameEdit.setPlaceholderText("GitHub username")
        self.usernameEdit.setStyleSheet(FIELD_STYLE)
        form.addRow("GitHub username:", self.usernameEdit)
        self.accessCombo = qt.QComboBox()
        self.accessCombo.setStyleSheet(FIELD_STYLE)
        self.accessCombo.addItem("Can share")
        self.accessCombo.addItem("Needs approval")
        form.addRow("Access:", self.accessCombo)
        self.taskTitleEdit = qt.QLineEdit()
        self.taskTitleEdit.setPlaceholderText("Optional — what they should work on")
        self.taskTitleEdit.setMaxLength(80)
        self.taskTitleEdit.setStyleSheet(FIELD_STYLE)
        form.addRow("Task title:", self.taskTitleEdit)
        add_layout.addLayout(form)
        self.suggestionList = qt.QListWidget()
        self.suggestionList.setMaximumHeight(120)
        self.suggestionList.setFocusPolicy(qt.Qt.StrongFocus)
        self.suggestionList.setVerticalScrollBarPolicy(qt.Qt.ScrollBarAsNeeded)
        self.suggestionList.setHorizontalScrollBarPolicy(qt.Qt.ScrollBarAlwaysOff)
        self.suggestionList.setSelectionMode(qt.QAbstractItemView.SingleSelection)
        self.suggestionList.setStyleSheet(
            "QListWidget { background: palette(base); color: palette(text);"
            " border: 1px solid palette(mid); border-radius: 4px; }"
            "QListWidget::item { padding: 5px 8px; }"
            "QListWidget::item:selected { background: palette(highlight); color: palette(highlighted-text); }"
        )
        self.suggestionList.setVisible(False)
        if self._can_add:
            self.suggestionList.connect("currentRowChanged(int)", self._onSuggestionRowChanged)
        add_layout.addWidget(self.suggestionList)
        owner_hint = qt.QLabel(
            "They will receive a GitHub invitation. After they accept, this project appears in their list.\n"
            "Can share: they publish versions themselves. Needs approval: they send a request for you to review.\n"
            "Task title is optional. Everyone on People can see it."
        )
        owner_hint.setWordWrap(True)
        owner_hint.setStyleSheet(DIALOG_HINT_STYLE)
        add_layout.addWidget(owner_hint)
        layout.addWidget(self.addPanel)

        self.colleagueHint = qt.QLabel("Only the owner can add or remove colleagues.")
        self.colleagueHint.setWordWrap(True)
        self.colleagueHint.setStyleSheet(DIALOG_HINT_STYLE)
        layout.addWidget(self.colleagueHint)

        self.statusLabel = qt.QLabel("")
        self.statusLabel.setWordWrap(True)
        self.statusLabel.setVisible(False)
        layout.addWidget(self.statusLabel)

        buttons = qt.QHBoxLayout()
        buttons.addStretch(1)
        closeButton = qt.QPushButton("Close")
        self.removeButton = qt.QPushButton("Remove")
        self.addButton = qt.QPushButton("Add")
        closeButton.setStyleSheet(BTN_SECONDARY)
        self.removeButton.setStyleSheet(BTN_DELETE)
        self.addButton.setStyleSheet(BTN_CREATE)
        closeButton.connect("clicked()", self.reject)
        self.removeButton.connect("clicked()", self._onRemoveClicked)
        self.addButton.connect("clicked()", self._onAddClicked)
        self.addButton.setDefault(True)
        buttons.addWidget(closeButton)
        buttons.addWidget(self.removeButton)
        buttons.addWidget(self.addButton)
        layout.addLayout(buttons)

        self.addPanel.setVisible(self._can_add)
        self.colleagueHint.setVisible(not self._can_add)
        self.addButton.setVisible(self._can_add)
        self.removeButton.setVisible(self._can_add)
        if self._can_add:
            self.peopleList.connect("currentRowChanged(int)", self._onRowChanged)
        self.set_people(people or [])
        if self._can_add:
            self.usernameEdit.setFocus()
        self._suggestionNames = []
        self._fillingSuggestions = False
        self._pickingSuggestion = False
        self._idleSize = None
        try:
            self.adjustSize()
            self._captureIdleSize()
        except RuntimeError:
            pass
        if self._can_add:
            self._startUsernameSearchTimer()

    def _startUsernameSearchTimer(self) -> None:
        self._searchLast = None
        self._searchWanted = None
        self._searchWantedAt = 0.0
        self._searchReady = False
        self._searchBusy = False
        self._needRestoreIdleSize = False
        try:
            self.usernameEdit.connect("textChanged(QString)", self._onUsernameText)
        except (TypeError, RuntimeError, AttributeError):
            pass
        timer = qt.QTimer(self)
        timer.setInterval(100)
        timer.connect("timeout()", self._tickUsernameSearch)
        self._searchTimer = timer
        timer.start()

    def _onUsernameText(self, _text=None) -> None:
        if getattr(self, "_pickingSuggestion", False):
            return
        if len(self.username()) < 2:
            self.hide_username_dropdown()

    def _captureIdleSize(self) -> None:
        try:
            size = self.size
            if callable(size):
                size = size()
            if size is None:
                return
            self._idleSize = qt.QSize(int(size.width()), int(size.height()))
        except (TypeError, RuntimeError, ValueError):
            pass

    def _restoreIdleSize(self) -> None:
        try:
            self.setMinimumHeight(0)
            self.setMinimumWidth(460)
        except RuntimeError:
            pass
        idle = getattr(self, "_idleSize", None)
        if idle is not None:
            try:
                self.resize(idle)
                return
            except (TypeError, RuntimeError):
                pass
        try:
            self.adjustSize()
        except RuntimeError:
            pass

    def _showSuggestionList(self, height: int) -> None:
        try:
            self.suggestionList.setMinimumHeight(height)
            self.suggestionList.setMaximumHeight(120)
            self.suggestionList.setVisible(True)
            self.adjustSize()
        except RuntimeError:
            pass

    def _showSearching(self) -> None:
        visible = False
        try:
            visible = bool(self.suggestionList.isVisible())
        except (TypeError, RuntimeError, AttributeError):
            pass
        if not visible:
            self._captureIdleSize()
        self._fillingSuggestions = True
        try:
            self.suggestionList.clear()
            self._suggestionNames = None
            self.suggestionList.addItem("Searching…")
            self._showSuggestionList(72)
        except RuntimeError:
            pass
        self._fillingSuggestions = False

    def _tickUsernameSearch(self) -> None:
        if getattr(self, "_needRestoreIdleSize", False):
            visible = False
            try:
                visible = bool(self.suggestionList.isVisible())
            except (TypeError, RuntimeError, AttributeError):
                pass
            self._needRestoreIdleSize = False
            if not visible:
                self._restoreIdleSize()
        if getattr(self, "_pickingSuggestion", False):
            return
        if getattr(self, "_searchBusy", False):
            return
        query = self.username()
        if len(query) < 2:
            if query != getattr(self, "_searchLast", None):
                self._searchLast = query
                self._searchReady = False
                self.hide_username_dropdown()
            return
        if query != getattr(self, "_searchWanted", None):
            self._searchWanted = query
            self._searchWantedAt = time.monotonic()
            self._searchReady = False
            return
        if time.monotonic() - getattr(self, "_searchWantedAt", 0) < 0.4:
            return
        if query != getattr(self, "_searchLast", None):
            self._searchLast = query
            self._showSearching()
            self._searchReady = True
            return
        if not getattr(self, "_searchReady", False):
            return
        self._searchReady = False
        self._searchBusy = True
        set_wait_callback(None)
        try:
            names = suggest_github_usernames(query)
        except (GitHubAuthError, OSError, RuntimeError, ValueError):
            names = []
        finally:
            self._searchBusy = False
        if self.username() != query:
            return
        self.show_username_suggestions(names)

    def hide_username_dropdown(self) -> None:
        if not getattr(self, "suggestionList", None):
            return
        try:
            self.suggestionList.clear()
            self.suggestionList.setMinimumHeight(0)
            self.suggestionList.setMaximumHeight(0)
            self.suggestionList.setVisible(False)
        except RuntimeError:
            pass
        self._suggestionNames = []
        self._needRestoreIdleSize = True
        self._restoreIdleSize()

    def show_username_suggestions(self, names) -> None:
        if not self._can_add:
            return
        new_names = [str(name).strip() for name in (names or []) if str(name).strip()]
        if new_names == getattr(self, "_suggestionNames", None):
            return
        self._fillingSuggestions = True
        try:
            self.suggestionList.clear()
            self._suggestionNames = new_names
            if not self._suggestionNames:
                self.suggestionList.addItem("No matching GitHub username.")
                self._showSuggestionList(36)
                return
            for login in self._suggestionNames:
                self.suggestionList.addItem(login)
            self.suggestionList.setCurrentRow(-1)
            self._showSuggestionList(72)
        finally:
            self._fillingSuggestions = False

    def _onSuggestionRowChanged(self, row) -> None:
        if getattr(self, "_fillingSuggestions", False):
            return
        try:
            row = int(row)
        except (TypeError, ValueError):
            return
        names = getattr(self, "_suggestionNames", [])
        if row < 0 or row >= len(names):
            return
        login = names[row]
        self._pickingSuggestion = True
        try:
            self.usernameEdit.setText(login)
        finally:
            self._pickingSuggestion = False
        self._searchLast = login
        self._searchWanted = login
        self._searchReady = False
        self.hide_username_dropdown()
        self.usernameEdit.setFocus()

    def reject(self):
        self.hide_username_dropdown()
        qt.QDialog.reject(self)

    def accept(self):
        self.hide_username_dropdown()
        qt.QDialog.accept(self)

    def set_add_handler(self, handler) -> None:
        self._add_handler = handler

    def set_remove_handler(self, handler) -> None:
        self._remove_handler = handler

    def selected_access(self) -> str:
        if not getattr(self, "accessCombo", None):
            return "share"
        try:
            index = self.accessCombo.currentIndex
            if callable(index):
                index = index()
            if int(index) == 1:
                return "approval"
        except (TypeError, ValueError, RuntimeError, AttributeError):
            pass
        return "share"

    def username(self) -> str:
        try:
            text = self.usernameEdit.text
            if callable(text):
                text = text()
        except (TypeError, AttributeError, RuntimeError):
            text = ""
        return str(text or "").strip().lstrip("@")

    def task_title(self) -> str:
        try:
            text = self.taskTitleEdit.text
            if callable(text):
                text = text()
        except (TypeError, AttributeError, RuntimeError):
            text = ""
        return normalize_task_title(text)

    def people(self) -> list:
        return list(self._people)

    def set_people(self, people) -> None:
        self._people = list(people or [])
        self.peopleList.clear()
        if not self._people:
            self.peopleList.addItem("No one listed yet.")
            self._updateRemoveEnabled()
            return
        for person in self._people:
            login = str(person.get("login") or "").strip()
            role = str(person.get("role") or "")
            access = str(person.get("access") or "share")
            task = str(person.get("task") or "").strip()
            access_label = "Needs approval" if access == "approval" else "Can share"
            if role == "owner":
                label = "%s (owner)" % login
            elif role == "pending":
                label = "%s (invitation pending · %s)" % (login, access_label)
            else:
                label = "%s (%s)" % (login, access_label)
            if task:
                label = "%s — %s" % (label, task)
            self.peopleList.addItem(label)
            if task:
                try:
                    count = self.peopleList.count
                    if callable(count):
                        count = count()
                    item = self.peopleList.item(int(count) - 1)
                    if item is not None:
                        item.setToolTip(task)
                except (TypeError, RuntimeError, AttributeError, ValueError):
                    pass
        self._updateRemoveEnabled()

    def selected_person(self):
        if not self._can_add:
            return None
        row = self.peopleList.currentRow
        if callable(row):
            row = row()
        row = int(row)
        if row < 0 or row >= len(self._people):
            return None
        return self._people[row]

    def _onRowChanged(self, _row) -> None:
        self._updateRemoveEnabled()

    def _updateRemoveEnabled(self) -> None:
        if not self._can_add:
            return
        person = self.selected_person()
        can_remove = bool(person) and person.get("role") != "owner"
        self.removeButton.setEnabled(can_remove)

    def set_status(self, message: str, error: bool = False) -> None:
        text = (message or "").strip()
        self.statusLabel.setText(text)
        self.statusLabel.setVisible(bool(text))
        if not text:
            return
        color = FEED_COLOR_ERROR if error else ACCENT_MINT
        self.statusLabel.setStyleSheet("color: %s; font-size: 11px; font-weight: 600;" % color)

    def _onAddClicked(self) -> None:
        handler = self._add_handler
        if handler is not None:
            handler(self)

    def _onRemoveClicked(self) -> None:
        handler = self._remove_handler
        if handler is not None:
            handler(self)


DISCONNECT_GITHUB_HELP = (
    "The next connection will ask you to sign in again in the browser. "
    "Use this to change account or leave a shared computer."
)


class CollaborativeVersioning(ScriptedLoadableModule):
    def __init__(self, parent):
        ScriptedLoadableModule.__init__(self, parent)
        self.parent.title = _("Collaborative Versioning")
        self.parent.categories = [translate("qSlicerAbstractCoreModule", "Informatics")]
        self.parent.dependencies = []
        self.parent.contributors = ["Ahmed Ben Akouche (ISIR)", "Julien Gori (CNRS)"]
        self.parent.helpText = _(
            """
            Collaborative versioning for 3D image annotations — UI MVP.<br><br>
            Connect with GitHub, then create or open a project.<br>
            Right panel: graphs, history, and activity feed.
            """
        )
        self.parent.acknowledgementText = _("ISIR/ICM project — collaborative 3D annotation versioning.")


class CollaborativeVersioningWidget(ScriptedLoadableModuleWidget, VTKObservationMixin):
    def __init__(self, parent=None) -> None:
        ScriptedLoadableModuleWidget.__init__(self, parent)
        VTKObservationMixin.__init__(self)
        self.logic = None
        self._currentVersionId = None
        self._rightDock = None
        self._rightDockContainer = None
        self._server_pulled = False
        self._ontology_document = None
        self._ontology_preset_ids = [preset_id for preset_id, _label in preset_choices()]
        self._connected = False
        self._loaded_project_name = None
        self._local_project_path = None
        self._ontology_server_combo_index = -1
        self._project_ontology_path = None
        self._project_ontology_document = None
        self._suppress_asset_ui_updates = 0
        self._suppress_history_selection_signal = False
        self._project_history_bundle = None
        self._github_session = None
        self._progressDialog = None
        self._progressLabel = None
        self._progressBar = None
        self._progressTimer = None
        self._pulsing_progress = False
        self._unsaved_changes = False
        self._dirty_segmentation = False
        self._dirty_ontology = False
        self._unshared_version = False
        self._suppress_dirty = 0
        self._ignore_data_modified = False
        self._dirty_settle_token = 0
        self._clean_volume_id = None
        self._clean_seg_id = None
        self._dataProbeWasCollapsed = None
        self._collecting_coverage = False
        self._anatomyCoverageTimer = None
        self._painted_ids_cache_key = None
        self._painted_ids_cache = set()
        self._people_access_cache = {}
        self._notifications = []
        self._notificationsTimer = None
        self._refreshing_notifications = False
        self._notificationsProcess = None
        self._notificationFetchQueue = []
        self._notificationFetchResults = []
        self._notificationFetchAnnounce = False
        self._notificationFetchKind = ""
        self._people_dialog_open = False
        self._notifications_popup_open = False
        self._ontology_graph_pending = False
        self._messages = []
        self._messagesTimer = None
        self._refreshing_messages = False
        self._sending_message = False
        self._messages_read_ids = set()
        self._messages_baseline_ready = False
        self._messages_unread = 0
        self._messages_project = ""
        self._messagesProcess = None
        self._messagesFetchProject = ""
        self._messageSendQueue = []
        self._messageSendProcess = None
        self._messageSendPhase = ""
        self._messageSendCurrent = None
        self._messageSendProject = ""
        self._messageSendAttempt = 0
        self._messageSendExisting = []

    def setup(self) -> None:
        try:
            self._setupUi()
        except Exception as error:
            import traceback
            logging.error("CollaborativeVersioning setup failed: %s", traceback.format_exc())
            slicer.util.errorDisplay(
                "Collaborative Versioning UI failed to load:\n%s" % error
            )
            raise

    def _setupUi(self) -> None:
        _bindIceClinicTheme()
        self._clearLayout()
        self.logic = CollaborativeVersioningLogic()
        self.logic.setWidget(self)
        self._buildLeftPanel()
        self._buildRightDock()
        self._connected = False
        self.connectionStatusLabel.text = "Not connected"
        self.connectionStatusLabel.setStyleSheet(STATUS_NEUTRAL)
        self._applyDisconnectedUi()
        self.setupDeveloperSection()
        if getattr(self, "reloadCollapsibleButton", None) is not None:
            self.reloadCollapsibleButton.collapsed = True

    def _clearLayout(self) -> None:
        self._stopNotificationsPolling()
        self._stopMessagesPolling()
        self._disconnectProjectAssetSignals()
        while self.layout.count():
            item = self.layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()

    def _closeLogicDialogs(self) -> None:
        if not self.logic:
            return
        for attribute_name in ("dependencyDialog", "historyDialog"):
            dialog = getattr(self.logic, attribute_name, None)
            if dialog is not None:
                dialog.close()
                dialog.deleteLater()
                setattr(self.logic, attribute_name, None)
        self.logic._dependencyCanvas = None
        self.logic._historyCanvas = None

    def _buildLeftPanel(self) -> None:
        connexionButton = ctk.ctkCollapsibleButton()
        connexionButton.text = "Connection"
        connexionButton.collapsed = False
        self.layout.addWidget(connexionButton)
        connexionLayout = qt.QVBoxLayout(connexionButton)
        connexionLayout.setSpacing(8)
        connexionLayout.setContentsMargins(8, 8, 8, 10)

        connectRow = qt.QWidget()
        connectRowLayout = qt.QVBoxLayout(connectRow)
        connectRowLayout.setContentsMargins(0, 0, 0, 0)
        connectRowLayout.setSpacing(6)
        connectButtons = qt.QWidget()
        connectButtonsLayout = qt.QHBoxLayout(connectButtons)
        connectButtonsLayout.setContentsMargins(0, 0, 0, 0)
        connectButtonsLayout.setSpacing(6)
        self.connectButton = qt.QPushButton("Connect with GitHub")
        self.connectButton.setStyleSheet(BTN_CONNECT)
        self.connectButton.setMinimumHeight(32)
        self.connectButton.setSizePolicy(qt.QSizePolicy.Expanding, qt.QSizePolicy.Fixed)
        self.notificationsBell = qt.QPushButton()
        self.notificationsBell.setToolTip("Notifications")
        self.notificationsBell.setStyleSheet(BTN_NOTIFICATIONS)
        self.notificationsBell.setFixedSize(36, 32)
        self.notificationsBell.setIcon(qt.QIcon(notification_bell_url()))
        self.notificationsBell.setIconSize(qt.QSize(18, 18))
        self.notificationsBell.setEnabled(False)
        self.notificationsBadge = qt.QLabel(self.notificationsBell)
        self.notificationsBadge.setAlignment(qt.Qt.AlignCenter)
        self.notificationsBadge.setFixedSize(16, 16)
        self.notificationsBadge.move(20, 0)
        self.notificationsBadge.setStyleSheet(NOTIFICATIONS_BADGE_STYLE)
        try:
            self.notificationsBadge.setAttribute(qt.Qt.WA_TransparentForMouseEvents, True)
        except (AttributeError, TypeError, RuntimeError):
            pass
        self.notificationsBadge.hide()
        connectButtonsLayout.addWidget(self.connectButton, 1)
        connectButtonsLayout.addWidget(self.notificationsBell, 0)
        self.connectionStatusLabel = qt.QLabel("Not connected")
        self.connectionStatusLabel.setStyleSheet(STATUS_NEUTRAL)
        self.connectionStatusLabel.setWordWrap(True)
        connectRowLayout.addWidget(connectButtons)
        connectRowLayout.addWidget(self.connectionStatusLabel)
        connexionLayout.addWidget(connectRow)

        projectButton = ctk.ctkCollapsibleButton()
        projectButton.text = "Active project"
        projectButton.collapsed = False
        self.projectButton = projectButton
        self.layout.addWidget(projectButton)
        projectLayout = qt.QVBoxLayout(projectButton)
        projectLayout.setSpacing(10)

        sourceForm = qt.QFormLayout()
        sourceForm.setSpacing(8)
        sourceForm.setRowWrapPolicy(qt.QFormLayout.WrapAllRows)

        self.projectCombo = qt.QComboBox()
        self.projectCombo.setStyleSheet(FIELD_STYLE)
        self._makeComboShrinkable(self.projectCombo)
        self.projectCombo.addItem(PROJECT_NONE_LABEL)
        self.projectCombo.setCurrentIndex(0)
        sourceForm.addRow("Project:", self.projectCombo)
        projectLayout.addLayout(sourceForm)

        assetsForm = qt.QFormLayout()
        assetsForm.setSpacing(8)
        assetsForm.setRowWrapPolicy(qt.QFormLayout.WrapAllRows)

        self.volumeSelector = slicer.qMRMLNodeComboBox()
        self._configureDataNodeSelector(
            self.volumeSelector,
            ["vtkMRMLScalarVolumeNode"],
            none_enabled=True,
            hide_labelmaps=True,
        )
        assetsForm.addRow("3D Volume:", self.volumeSelector)

        self.segmentationSelector = slicer.qMRMLNodeComboBox()
        self._configureDataNodeSelector(
            self.segmentationSelector,
            ["vtkMRMLSegmentationNode", "vtkMRMLLabelMapVolumeNode"],
            none_enabled=True,
        )
        assetsForm.addRow("Segmentation:", self.segmentationSelector)

        ontologyPanel = qt.QWidget()
        ontologyPanelLayout = qt.QVBoxLayout(ontologyPanel)
        ontologyPanelLayout.setContentsMargins(0, 0, 0, 0)
        ontologyPanelLayout.setSpacing(4)

        self.ontologyPresetCombo = qt.QComboBox()
        self.ontologyPresetCombo.addItem(ONTOLOGY_COMBO_NONE_LABEL)
        for _preset_id, label in preset_choices():
            self.ontologyPresetCombo.addItem(label)
        self.ontologyPresetCombo.setStyleSheet(FIELD_STYLE)
        self._makeComboShrinkable(self.ontologyPresetCombo)
        self.ontologyPresetCombo.setCurrentIndex(ONTOLOGY_COMBO_NONE_INDEX)
        ontologyPanelLayout.addWidget(self.ontologyPresetCombo)
        ontologyLocalActions = qt.QHBoxLayout()
        ontologyLocalActions.setContentsMargins(0, 0, 0, 0)
        ontologyLocalActions.setSpacing(3)
        self.ontologyHelpButton = qt.QPushButton("Help")
        self.loadOntologyButton = qt.QPushButton("Load")
        self.editOntologyButton = qt.QPushButton("Edit")
        self.exportOntologyButton = qt.QPushButton("Export")
        self.loadOntologyButton.setToolTip("Load ontology JSON")
        for btn in (self.ontologyHelpButton, self.loadOntologyButton, self.editOntologyButton, self.exportOntologyButton):
            btn.setStyleSheet(BTN_SECONDARY + " font-size: 9px; padding: 2px 4px;")
            btn.setSizePolicy(qt.QSizePolicy.Expanding, qt.QSizePolicy.Fixed)
            ontologyLocalActions.addWidget(btn)
        ontologyPanelLayout.addLayout(ontologyLocalActions)

        assetsForm.addRow("Ontology map (JSON):", ontologyPanel)
        projectLayout.addLayout(assetsForm)

        actionsRow = qt.QHBoxLayout()
        actionsRow.setSpacing(6)
        actionsRow.setContentsMargins(0, 0, 0, 0)
        leftCol = qt.QVBoxLayout()
        leftCol.setSpacing(6)
        leftCol.setContentsMargins(0, 0, 0, 0)
        rightCol = qt.QVBoxLayout()
        rightCol.setSpacing(6)
        rightCol.setContentsMargins(0, 0, 0, 0)
        self.createButton = qt.QPushButton("Create")
        self.peopleButton = qt.QPushButton("People")
        self.deleteButton = qt.QPushButton("Delete")
        self.openButton = qt.QPushButton("Open")
        self.saveVersionButton = qt.QPushButton("Save")
        self.shareButton = qt.QPushButton("Share")
        self.createButton.setStyleSheet(BTN_CREATE)
        self.peopleButton.setStyleSheet(BTN_PEOPLE)
        self.deleteButton.setStyleSheet(BTN_DELETE)
        self.openButton.setStyleSheet(BTN_PULL)
        self.saveVersionButton.setStyleSheet(BTN_SAVE_VERSION)
        self.shareButton.setStyleSheet(BTN_PUSH)
        self.createButton.setToolTip("Create a new project")
        self.peopleButton.setToolTip("See who is on this project")
        self.deleteButton.setToolTip("Delete this project (owner only)")
        self.openButton.setToolTip("Open a selected project that is not loaded yet")
        self.saveVersionButton.setToolTip("Save a version when the current work has changed")
        self.shareButton.setToolTip("Share a saved version that is not shared yet")
        for btn in (self.createButton, self.peopleButton, self.deleteButton):
            btn.setEnabled(False)
            btn.setSizePolicy(qt.QSizePolicy.Expanding, qt.QSizePolicy.Fixed)
            leftCol.addWidget(btn)
        for btn in (self.openButton, self.saveVersionButton, self.shareButton):
            btn.setEnabled(False)
            btn.setSizePolicy(qt.QSizePolicy.Expanding, qt.QSizePolicy.Fixed)
            rightCol.addWidget(btn)
        actionsRow.addLayout(leftCol, 1)
        actionsRow.addLayout(rightCol, 1)
        projectLayout.addLayout(actionsRow)

        self._buildMessagesSection()

        self.layout.addStretch(1)

        self.connectButton.connect("clicked()", self.onConnect)
        self.notificationsBell.connect("clicked()", self._onNotificationsBellClicked)
        self.projectCombo.connect("currentIndexChanged(int)", self.onProjectChanged)
        self.ontologyPresetCombo.connect("currentIndexChanged(int)", self.onOntologyPresetChanged)
        self.ontologyHelpButton.connect("clicked()", self.onOntologyJsonHelp)
        self.loadOntologyButton.connect("clicked()", self.onLoadOntologyJson)
        self.editOntologyButton.connect("clicked()", self.onEditOntology)
        self.exportOntologyButton.connect("clicked()", self.onExportOntologyJson)
        self.createButton.connect("clicked()", self.onCreateProject)
        self.openButton.connect("clicked()", self.onOpenProject)
        self.saveVersionButton.connect("clicked()", self.onSaveVersion)
        self.shareButton.connect("clicked()", self.onShare)
        self.peopleButton.connect("clicked()", self.onPeople)
        self.deleteButton.connect("clicked()", self.onDeleteProject)
        self.messagesSend.connect("clicked()", self._onSendMessage)
        self.messagesInput.connect("returnPressed()", self._onSendMessage)
        self.volumeSelector.connect("currentNodeChanged(vtkMRMLNode*)", self._onVolumeAssetChanged)
        self.segmentationSelector.connect("currentNodeChanged(vtkMRMLNode*)", self._onSegmentationAssetChanged)

    def _buildMessagesSection(self) -> None:
        messagesButton = qt.QPushButton("Messages")
        messagesButton.setCheckable(True)
        messagesButton.setChecked(False)
        messagesButton.setStyleSheet(MESSAGES_HEADER_STYLE)
        messagesButton.setMinimumHeight(32)
        messagesButton.setSizePolicy(qt.QSizePolicy.Expanding, qt.QSizePolicy.Fixed)
        messagesButton.setToolTip("Messages")
        self.messagesButton = messagesButton
        self.layout.addWidget(messagesButton)

        self.messagesBadge = qt.QLabel(messagesButton)
        self.messagesBadge.setAlignment(qt.Qt.AlignCenter)
        self.messagesBadge.setFixedSize(16, 16)
        self.messagesBadge.setStyleSheet(NOTIFICATIONS_BADGE_STYLE)
        try:
            self.messagesBadge.setAttribute(qt.Qt.WA_TransparentForMouseEvents, True)
        except (AttributeError, TypeError, RuntimeError):
            pass
        self.messagesBadge.hide()

        messagesBody = qt.QWidget()
        self.messagesBody = messagesBody
        messagesLayout = qt.QVBoxLayout(messagesBody)
        messagesLayout.setSpacing(6)
        messagesLayout.setContentsMargins(0, 6, 0, 0)

        self.messagesView = qt.QTextEdit()
        self.messagesView.setReadOnly(True)
        self.messagesView.setStyleSheet(MESSAGES_VIEW_STYLE)
        self.messagesView.setMinimumHeight(120)
        self.messagesView.setMaximumHeight(200)
        try:
            self.messagesView.setAcceptRichText(True)
        except (AttributeError, TypeError, RuntimeError):
            pass

        compose = qt.QWidget()
        composeLayout = qt.QHBoxLayout(compose)
        composeLayout.setContentsMargins(0, 0, 0, 0)
        composeLayout.setSpacing(6)
        self.messagesInput = qt.QLineEdit()
        self.messagesInput.setStyleSheet(FIELD_STYLE)
        self.messagesInput.setPlaceholderText("Write a message")
        self.messagesSend = qt.QPushButton("Send")
        self.messagesSend.setStyleSheet(BTN_SECONDARY)
        self.messagesSend.setMinimumHeight(32)
        composeLayout.addWidget(self.messagesInput, 1)
        composeLayout.addWidget(self.messagesSend, 0)

        messagesLayout.addWidget(self.messagesView)
        messagesLayout.addWidget(compose)
        messagesBody.hide()
        self.layout.addWidget(messagesBody)
        self._renderMessagesView()
        self._setMessagesComposerEnabled(False)
        messagesButton.connect("toggled(bool)", self._onMessagesToggled)
        qt.QTimer.singleShot(0, self._positionMessagesBadge)

    def _configureDataNodeSelector(self, selector, node_types, none_enabled=False, hide_labelmaps=False) -> None:
        """Existing scene nodes only (no create/delete entries). Default selection is None."""
        selector.setMRMLScene(slicer.mrmlScene)
        selector.nodeTypes = node_types
        selector.addEnabled = False
        selector.removeEnabled = False
        selector.editEnabled = False
        selector.renameEnabled = False
        selector.noneEnabled = none_enabled
        if hide_labelmaps and hasattr(selector, "hideChildNodeTypes"):
            # Hide segmentation labelmaps only. Do not use addAttribute("LabelMap"):
            # that filter hides every volume that does not have the attribute set.
            selector.hideChildNodeTypes = ["vtkMRMLLabelMapVolumeNode"]
        if hasattr(selector, "selectNodeUponCreation"):
            selector.selectNodeUponCreation = False
        if none_enabled and hasattr(selector, "noneDisplay"):
            selector.noneDisplay = PROJECT_NONE_LABEL
        selector.setStyleSheet(FIELD_STYLE)
        self._makeComboShrinkable(selector)
        selector.setCurrentNode(None)

    def _makeComboShrinkable(self, widget) -> None:
        """Stop long item names from locking the left panel width."""
        widget.setSizePolicy(qt.QSizePolicy.Ignored, qt.QSizePolicy.Fixed)
        if hasattr(widget, "setSizeAdjustPolicy"):
            widget.setSizeAdjustPolicy(qt.QComboBox.AdjustToMinimumContentsLengthWithIcon)
        if hasattr(widget, "setMinimumContentsLength"):
            widget.setMinimumContentsLength(6)

    def _clearOntologyDocument(self) -> None:
        self._ontology_document = None
        if self.logic and self.logic._dependencyCanvas:
            self.logic._dependencyCanvas.set_specs(
                [],
                graph_title="Ontology",
                graph_description="No ontology loaded.",
                painted_ids=[],
            )
        self._updateRightDockAvailability()
        self._markAssetDirty("ontology")
        self._updateVersionActionButtons()

    def _setOntologyComboNone(self) -> None:
        self.ontologyPresetCombo.blockSignals(True)
        self.ontologyPresetCombo.setCurrentIndex(ONTOLOGY_COMBO_NONE_INDEX)
        self.ontologyPresetCombo.blockSignals(False)

    def _removeServerOntologyComboEntry(self) -> None:
        combo = self.ontologyPresetCombo
        if self._ontology_server_combo_index < 0:
            self._project_ontology_path = None
            self._project_ontology_document = None
            return
        combo.blockSignals(True)
        if 0 <= self._ontology_server_combo_index < _qt_combo_count(combo):
            combo.removeItem(self._ontology_server_combo_index)
        self._ontology_server_combo_index = -1
        self._project_ontology_path = None
        self._project_ontology_document = None
        combo.blockSignals(False)

    def _ontologyComboLabelFromPath(self, path: str) -> str:
        name = os.path.basename(path or "")
        if name.lower().endswith(".json"):
            name = name[:-5]
        return name or "ontology"

    def _projectFileStem(self, project_name: str) -> str:
        return "".join(
            c if c.isalnum() or c in "-_" else "_" for c in (project_name or "project")
        ).strip("_") or "project"

    def _setOntologyComboLoadedFilename(self, document=None, filename=None) -> None:
        if filename:
            self._project_ontology_path = filename
            label = self._ontologyComboLabelFromPath(filename)
        elif document:
            label = self._ontologyComboLabelFromPath(document.get("source_path") or "ontology.json")
        else:
            return
        if document is not None:
            self._project_ontology_document = document
        elif self._ontology_document is not None:
            self._project_ontology_document = self._ontology_document
        combo = self.ontologyPresetCombo
        combo.blockSignals(True)
        if 0 <= self._ontology_server_combo_index < _qt_combo_count(combo):
            combo.setItemText(self._ontology_server_combo_index, label)
            combo.setCurrentIndex(self._ontology_server_combo_index)
        else:
            combo.addItem(label)
            self._ontology_server_combo_index = _qt_combo_count(combo) - 1
            combo.setCurrentIndex(self._ontology_server_combo_index)
        combo.blockSignals(False)

    def _restoreProjectOntology(self, notify=False) -> None:
        document = getattr(self, "_project_ontology_document", None)
        path = getattr(self, "_project_ontology_path", None)
        if document is None and path and os.path.isfile(path):
            try:
                document = load_ontology_file(path)
                self._project_ontology_document = document
            except (OSError, ValueError) as error:
                if notify:
                    self._appendFeed("Ontology error: %s" % error, error=True)
                return
        if document is None:
            return
        self._applyOntologyDocument(document)

    def _rightDockUiAlive(self) -> bool:
        return (
            _qt_widget_is_valid(getattr(self, "_rightDock", None))
            and _qt_widget_is_valid(getattr(self, "btnDependencyGraph", None))
            and _qt_widget_is_valid(getattr(self, "btnHistoryGraph", None))
        )

    def _teardownRightDock(self) -> None:
        table = getattr(self, "historyTableWidget", None)
        if table is not None:
            try:
                table.disconnect("itemSelectionChanged()", self.onHistorySelectionChanged)
            except (RuntimeError, ValueError, TypeError):
                pass
        for button, slot in (
            (getattr(self, "btnDependencyGraph", None), self.onOpenDependencyGraph),
            (getattr(self, "btnHistoryGraph", None), self.onOpenHistoryGraph),
        ):
            if button is None:
                continue
            try:
                button.disconnect("clicked()", slot)
            except (RuntimeError, ValueError, TypeError):
                pass
        self.btnDependencyGraph = None
        self.btnHistoryGraph = None
        self.feedTextEdit = None
        self.feedClearButton = None
        self.historyTableWidget = None
        self.historyPlaceholder = None
        self._dockLockBanner = None
        self._dockGraphsTitle = None
        self._dockHistoryTitle = None
        self._dockActivityTitle = None
        self._dockSeparator = None
        self._rightDockContainer = None

    def _blockProjectAssetSignals(self, blocked: bool) -> None:
        for name in ("volumeSelector", "segmentationSelector"):
            selector = getattr(self, name, None)
            if _qt_widget_is_valid(selector):
                selector.blockSignals(blocked)

    def _disconnectProjectAssetSignals(self) -> None:
        for name in ("volumeSelector", "segmentationSelector"):
            selector = getattr(self, name, None)
            if selector is None:
                continue
            for handler in (
                getattr(self, "_onVolumeAssetChanged", None),
                getattr(self, "_onSegmentationAssetChanged", None),
            ):
                if handler is None:
                    continue
                try:
                    selector.disconnect("currentNodeChanged(vtkMRMLNode*)", handler)
                except (RuntimeError, ValueError, TypeError):
                    pass
            setattr(self, name, None)

    def _refreshProjectAssetUi(self) -> None:
        if not self._connected or self._suppress_asset_ui_updates > 0:
            return
        if not _qt_widget_is_valid(getattr(self, "openButton", None)):
            return
        self._updateVersionActionButtons()
        self._updateRightDockAvailability()

    def _clearProjectAssetFields(self) -> None:
        self._blockProjectAssetSignals(True)
        try:
            if _qt_widget_is_valid(getattr(self, "volumeSelector", None)):
                self.volumeSelector.setCurrentNode(None)
            if _qt_widget_is_valid(getattr(self, "segmentationSelector", None)):
                self.segmentationSelector.setCurrentNode(None)
            self._clearOntologyDocument()
            self._removeServerOntologyComboEntry()
            self._setOntologyComboNone()
        finally:
            self._blockProjectAssetSignals(False)

    def _setProjectAssetFieldsEnabled(self, enabled: bool) -> None:
        self.volumeSelector.setEnabled(enabled)
        self.segmentationSelector.setEnabled(enabled)
        self.ontologyPresetCombo.setEnabled(enabled)
        self.loadOntologyButton.setEnabled(enabled)
        self.editOntologyButton.setEnabled(enabled)
        self.exportOntologyButton.setEnabled(enabled)
        self.ontologyHelpButton.setEnabled(True)

    def _buildRightDock(self) -> None:
        mainWin = slicer.util.mainWindow()
        self._teardownRightDock()
        for oldDock in mainWin.findChildren(qt.QDockWidget, "CollaborativeVersioning_RightDock"):
            mainWin.removeDockWidget(oldDock)
            oldDock.deleteLater()
        self._rightDock = None

        self._rightDock = qt.QDockWidget("Collaborative Versioning — Collaborative mode", mainWin)
        self._rightDock.setObjectName("CollaborativeVersioning_RightDock")
        self._rightDock.setAllowedAreas(qt.Qt.RightDockWidgetArea)
        self._rightDock.setStyleSheet(DOCK_STYLE)

        container = qt.QWidget()
        self._rightDockContainer = container
        container.setStyleSheet(DOCK_STYLE)
        layout = qt.QVBoxLayout(container)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(12)

        self._dockLockBanner = qt.QLabel("Locked — connect to the server first.")
        self._dockLockBanner.setWordWrap(True)
        self._dockLockBanner.setStyleSheet(DOCK_LOCK_BANNER_STYLE)
        self._dockLockBanner.setVisible(False)
        layout.addWidget(self._dockLockBanner)

        self._dockGraphsTitle = qt.QLabel("VISUAL EXPLORATION")
        self._dockGraphsTitle.setStyleSheet(SECTION_TITLE_STYLE)
        layout.addWidget(self._dockGraphsTitle)

        self.btnDependencyGraph = qt.QPushButton("View anatomy tree")
        self.btnDependencyGraph.setStyleSheet(BTN_DEPENDENCY)
        layout.addWidget(self.btnDependencyGraph)

        self.btnHistoryGraph = qt.QPushButton("View version tree")
        self.btnHistoryGraph.setStyleSheet(BTN_HISTORY)
        layout.addWidget(self.btnHistoryGraph)

        self._dockHistoryTitle = qt.QLabel("VERSION HISTORY")
        self._dockHistoryTitle.setStyleSheet(SECTION_TITLE_STYLE)
        layout.addWidget(self._dockHistoryTitle)

        self.checkedOutLabel = qt.QLabel("")
        self.checkedOutLabel.setWordWrap(True)
        self.checkedOutLabel.setStyleSheet(CHECKED_OUT_LABEL_STYLE)
        self.checkedOutLabel.setVisible(False)
        layout.addWidget(self.checkedOutLabel)

        self.historyPlaceholder = qt.QLabel(
            "Version history appears after you create or open a project."
        )
        self.historyPlaceholder.setWordWrap(True)
        self.historyPlaceholder.setStyleSheet(PLACEHOLDER_STYLE)
        layout.addWidget(self.historyPlaceholder)

        self.historyTableWidget = qt.QTableWidget()
        self.historyTableWidget.setColumnCount(5)
        self.historyTableWidget.setHorizontalHeaderLabels(["Version", "Date", "Author", "Message", "Status"])
        self.historyTableWidget.setAlternatingRowColors(True)
        self.historyTableWidget.setSelectionBehavior(qt.QAbstractItemView.SelectRows)
        self.historyTableWidget.setSelectionMode(qt.QAbstractItemView.SingleSelection)
        self.historyTableWidget.setEditTriggers(qt.QAbstractItemView.NoEditTriggers)
        self.historyTableWidget.setStyleSheet(TABLE_STYLE)
        self.historyTableWidget.verticalHeader().setVisible(False)
        self.historyTableWidget.horizontalHeader().setStretchLastSection(True)
        self.historyTableWidget.setMinimumHeight(130)
        self.historyTableWidget.setMaximumHeight(180)
        self.historyTableWidget.setVisible(False)
        layout.addWidget(self.historyTableWidget)

        separator = qt.QFrame()
        separator.setFrameShape(qt.QFrame.HLine)
        separator.setFrameShadow(qt.QFrame.Plain)
        separator.setStyleSheet(SEPARATOR_STYLE)
        self._dockSeparator = separator
        layout.addWidget(separator)

        self._dockActivityTitle = qt.QLabel("LIVE ACTIVITY FEED")
        self._dockActivityTitle.setStyleSheet(SECTION_TITLE_STYLE)
        feedHeader = qt.QWidget()
        feedHeaderLayout = qt.QHBoxLayout(feedHeader)
        feedHeaderLayout.setContentsMargins(0, 0, 0, 0)
        feedHeaderLayout.setSpacing(6)
        feedHeaderLayout.addWidget(self._dockActivityTitle, 1)
        self.feedClearButton = qt.QPushButton("Clear")
        self.feedClearButton.setToolTip("Clear the activity feed")
        self.feedClearButton.setStyleSheet(BTN_SECONDARY + " font-size: 9px; padding: 2px 8px;")
        self.feedClearButton.setSizePolicy(qt.QSizePolicy.Fixed, qt.QSizePolicy.Fixed)
        feedHeaderLayout.addWidget(self.feedClearButton, 0)
        layout.addWidget(feedHeader)

        self.feedTextEdit = qt.QTextEdit()
        self.feedTextEdit.setReadOnly(True)
        self.feedTextEdit.setStyleSheet(FEED_STYLE)
        layout.addWidget(self.feedTextEdit, 1)

        self._rightDock.setWidget(container)
        mainWin.addDockWidget(qt.Qt.RightDockWidgetArea, self._rightDock)

        self.btnDependencyGraph.connect("clicked()", self.onOpenDependencyGraph)
        self.btnHistoryGraph.connect("clicked()", self.onOpenHistoryGraph)
        self.historyTableWidget.connect("itemSelectionChanged()", self.onHistorySelectionChanged)
        self.feedClearButton.connect("clicked()", self._clearActivityFeed)
        self._setRightDockLocked(True)

    def _applyDockGraphButtonsLocked(self) -> None:
        for button in (
            getattr(self, "btnDependencyGraph", None),
            getattr(self, "btnHistoryGraph", None),
        ):
            if _qt_widget_is_valid(button):
                button.setStyleSheet(DOCK_BTN_LOCKED_STYLE)
                button.setEnabled(False)

    def _styleDockGraphButton(self, button, enabled: bool, active_style: str) -> None:
        if not _qt_widget_is_valid(button):
            return
        try:
            button.setEnabled(enabled)
            button.setStyleSheet(active_style if enabled else DOCK_BTN_LOCKED_STYLE)
            button.update()
        except (RuntimeError, ValueError):
            pass

    def _promptCommitMessage(self, title: str, label: str, default: str = "") -> str | None:
        message, ok = _qt_input_text(slicer.util.mainWindow(), title, label, default)
        if not ok or not message:
            return None
        return message

    def _promptOpenUnsharedChoice(self, full_name: str) -> str:
        """Return update, local, replace, or cancel."""
        try:
            info = inspect_local_project(full_name)
        except GitHubAuthError:
            return "update"
        if not info.get("exists") or not info.get("unshared_count"):
            return "update"
        count = int(info.get("unshared_count") or 0)
        box = qt.QMessageBox(slicer.util.mainWindow())
        box.setWindowTitle("Open project")
        if count == 1:
            box.setText(
                "This project has 1 version saved on this computer that is not shared yet."
            )
        else:
            box.setText(
                "This project has %d versions saved on this computer that are not shared yet."
                % count
            )
        box.setInformativeText(
            "Open this computer's work (keep those versions), or replace it with the shared project?\n\n"
            "Replacing discards versions saved here but not shared."
        )
        local_btn = box.addButton("Open this computer's work", qt.QMessageBox.AcceptRole)
        shared_btn = box.addButton("Open shared project", qt.QMessageBox.DestructiveRole)
        box.addButton("Cancel", qt.QMessageBox.RejectRole)
        box.setDefaultButton(local_btn)
        box.exec_()
        clicked = box.clickedButton()
        if clicked == local_btn:
            return "local"
        if clicked == shared_btn:
            return "replace"
        return "cancel"

    def _promptSwitchVersion(self, version_id: str) -> bool:
        box = qt.QMessageBox(slicer.util.mainWindow())
        box.setWindowTitle("Switch version")
        box.setText("Switch to %s?" % self._versionDisplayTag(version_id))
        box.setInformativeText(
            "Click Save first if you want to keep your current work."
        )
        switch_btn = box.addButton("Switch version", qt.QMessageBox.AcceptRole)
        cancel_btn = box.addButton("Cancel", qt.QMessageBox.RejectRole)
        box.setDefaultButton(cancel_btn)
        box.exec_()
        return box.clickedButton() == switch_btn

    def _githubLogin(self) -> str:
        session = getattr(self, "_github_session", None) or {}
        return str(session.get("login") or "annotator")

    def _currentRemoteRepo(self) -> dict | None:
        if not self._hasSelectedProject():
            return None
        session = getattr(self, "_github_session", None) or {}
        name = self._currentProjectName()
        for repo in session.get("repos") or []:
            if repo.get("full_name") == name:
                return repo
        return None

    def _populateProjectCombo(self) -> None:
        blocked = self.projectCombo.signalsBlocked()
        self.projectCombo.blockSignals(True)
        previous = _qt_combo_text(self.projectCombo)
        self.projectCombo.clear()
        self.projectCombo.addItem(PROJECT_NONE_LABEL)
        session = getattr(self, "_github_session", None) or {}
        remote_names = []
        if self._connected:
            for repo in session.get("repos") or []:
                full_name = repo.get("full_name")
                if full_name:
                    self.projectCombo.addItem(full_name)
                    remote_names.append(full_name)
        if previous and previous != PROJECT_NONE_LABEL and previous in remote_names:
            restore_index = self.projectCombo.findText(previous)
            self.projectCombo.setCurrentIndex(restore_index)
        else:
            self.projectCombo.setCurrentIndex(0)
        self.projectCombo.blockSignals(blocked)

    def _hasSelectedProject(self) -> bool:
        name = self._currentProjectName()
        return bool(name) and name != PROJECT_NONE_LABEL

    def _currentProjectName(self) -> str:
        name = _qt_combo_text(self.projectCombo)
        if name == PROJECT_NONE_LABEL:
            return ""
        return name

    def _refreshUiState(self) -> None:
        if not self._connected:
            self._applyDisconnectedUi()
            return
        self._setNotificationsEnabled(True)
        self._setRightDockLocked(False)
        self._setActiveProjectSectionEnabled(True)
        self._setMessagesSectionEnabled(True)
        self._syncMessagesPolling()
        self._updateCommitHistoryPanel()

    def _applyDisconnectedUi(self) -> None:
        self._stopNotificationsPolling()
        self._clearNotificationsDisplay()
        self._setNotificationsEnabled(False)
        self._stopMessagesPolling()
        self._resetMessagesState("")
        self._setMessagesSectionEnabled(False)
        self._setActiveProjectSectionEnabled(False)
        self._setRightDockLocked(True)
        self._updateCommitHistoryPanel()

    def _setRightDockLocked(self, locked: bool) -> None:
        if getattr(self, "_dockLockBanner", None):
            self._dockLockBanner.setVisible(locked)
        if getattr(self, "_rightDock", None):
            self._rightDock.setStyleSheet(DOCK_WIDGET_LOCKED_STYLE if locked else "")
        if getattr(self, "_rightDockContainer", None):
            self._rightDockContainer.setStyleSheet(DOCK_LOCKED_STYLE if locked else DOCK_STYLE)
        if getattr(self, "_dockSeparator", None):
            self._dockSeparator.setStyleSheet(
                "background-color: #282828; max-height: 1px; border: none;"
                if locked
                else SEPARATOR_STYLE
            )
        title_style = SECTION_TITLE_LOCKED_STYLE if locked else SECTION_TITLE_STYLE
        for title in (
            getattr(self, "_dockGraphsTitle", None),
            getattr(self, "_dockHistoryTitle", None),
            getattr(self, "_dockActivityTitle", None),
        ):
            if title is not None:
                title.setStyleSheet(title_style)
        if getattr(self, "historyPlaceholder", None):
            self.historyPlaceholder.setStyleSheet(
                PLACEHOLDER_LOCKED_STYLE if locked else PLACEHOLDER_STYLE
            )
        if locked:
            self._applyDockGraphButtonsLocked()
            if getattr(self, "feedTextEdit", None):
                self.feedTextEdit.setEnabled(False)
                self.feedTextEdit.setStyleSheet(FEED_LOCKED_STYLE)
            if getattr(self, "feedClearButton", None):
                self.feedClearButton.setEnabled(False)
            if getattr(self, "historyTableWidget", None):
                self.historyTableWidget.setEnabled(False)
                self.historyTableWidget.setStyleSheet(TABLE_LOCKED_STYLE)
            return
        if getattr(self, "feedTextEdit", None):
            self.feedTextEdit.setStyleSheet(FEED_STYLE)
        if getattr(self, "feedClearButton", None):
            self.feedClearButton.setEnabled(True)
        if getattr(self, "historyTableWidget", None):
            self.historyTableWidget.setEnabled(True)
            self.historyTableWidget.setStyleSheet(TABLE_STYLE)
        self._updateRightDockAvailability()

    def _setActiveProjectSectionEnabled(self, enabled: bool) -> None:
        if getattr(self, "projectButton", None):
            self.projectButton.setEnabled(enabled)
        for widget_name in (
            "projectCombo",
            "volumeSelector",
            "segmentationSelector",
            "ontologyPresetCombo",
            "loadOntologyButton",
            "editOntologyButton",
            "exportOntologyButton",
            "createButton",
            "openButton",
            "saveVersionButton",
            "shareButton",
            "peopleButton",
            "deleteButton",
        ):
            widget = getattr(self, widget_name, None)
            if widget is not None:
                widget.setEnabled(enabled)
        if not enabled:
            return
        self._setProjectAssetFieldsEnabled(True)
        self._updateVersionActionButtons()

    def _setMessagesSectionEnabled(self, enabled: bool) -> None:
        button = getattr(self, "messagesButton", None)
        if button is not None:
            button.setEnabled(bool(enabled))
        if not enabled:
            self._setMessagesComposerEnabled(False)

    def _setMessagesComposerEnabled(self, enabled: bool) -> None:
        can_write = bool(enabled and self._connected and self._hasSelectedProject())
        for name in ("messagesInput", "messagesSend"):
            widget = getattr(self, name, None)
            if widget is not None:
                widget.setEnabled(can_write)

    def _canOpenDependencyGraph(self) -> bool:
        if not self._connected:
            return False
        if not self._ontology_document:
            return False
        if self._hasSelectedProject():
            return self._server_pulled
        return True

    def _canOpenVersionTree(self) -> bool:
        if not self._connected:
            return False
        if not self._hasSelectedProject():
            return False
        return self._server_pulled

    def _updateRightDockAvailability(self) -> None:
        if not self._connected or self._suppress_asset_ui_updates > 0:
            return
        if not self._rightDockUiAlive():
            return
        dependency_ok = self._canOpenDependencyGraph()
        version_tree_ok = self._canOpenVersionTree()
        self._styleDockGraphButton(self.btnDependencyGraph, dependency_ok, BTN_DEPENDENCY)
        self._styleDockGraphButton(self.btnHistoryGraph, version_tree_ok, BTN_HISTORY)
        _safe_qt_call(getattr(self, "feedTextEdit", None), "setEnabled", True)
        _safe_qt_call(getattr(self, "feedClearButton", None), "setEnabled", True)
        feed = getattr(self, "feedTextEdit", None)
        if _qt_widget_is_valid(feed):
            try:
                feed.setStyleSheet(FEED_STYLE)
            except (RuntimeError, ValueError):
                pass

    def _hasVolume(self) -> bool:
        selector = getattr(self, "volumeSelector", None)
        if selector is None or not _qt_widget_is_valid(selector):
            return False
        try:
            node = selector.currentNode()
        except (RuntimeError, ValueError):
            return False
        if node is None:
            return False
        try:
            node_id = node.GetID()
        except (RuntimeError, ValueError):
            return False
        if not node_id:
            return False
        scene = slicer.mrmlScene
        if scene is None:
            return True
        try:
            return scene.GetNodeByID(node_id) is not None
        except (RuntimeError, ValueError):
            return True

    def _ontologyReadyForCreate(self) -> bool:
        combo = getattr(self, "ontologyPresetCombo", None)
        if combo is None or not _qt_widget_is_valid(combo):
            return False
        try:
            if _qt_combo_index(combo) <= ONTOLOGY_COMBO_NONE_INDEX:
                return False
            text = str(combo.currentText or "").strip()
            return bool(text) and text != ONTOLOGY_COMBO_NONE_LABEL
        except (RuntimeError, ValueError, AttributeError, TypeError):
            return False

    def _ensureOntologyFromCombo(self) -> None:
        """Load the selected preset if the combo shows one but the document was not applied."""
        if self._ontology_document is not None:
            return
        combo = getattr(self, "ontologyPresetCombo", None)
        if combo is None:
            return
        index = _qt_combo_index(combo)
        if index <= ONTOLOGY_COMBO_NONE_INDEX:
            return
        if index == self._ontology_server_combo_index:
            self._restoreProjectOntology(notify=False)
            return
        preset_index = index - 1
        if preset_index < 0 or preset_index >= len(self._ontology_preset_ids):
            return
        try:
            document = load_preset(self._ontology_preset_ids[preset_index])
        except (OSError, ValueError):
            return
        self._applyOntologyDocument(document)

    def _onVolumeAssetChanged(self, *_args) -> None:
        self._onProjectAssetSelectorChanged("volume")

    def _onSegmentationAssetChanged(self, *_args) -> None:
        self._onProjectAssetSelectorChanged("segmentation")

    def _onProjectAssetSelectorChanged(self, kind: str) -> None:
        if not self._connected or self._suppress_asset_ui_updates > 0:
            return
        if not _qt_widget_is_valid(getattr(self, "openButton", None)):
            return
        self._syncAssetDataObservers()
        selector_name = "volumeSelector" if kind == "volume" else "segmentationSelector"
        node = self._selectorCurrentNode(selector_name)
        if node is not None:
            clean_id = (
                getattr(self, "_clean_volume_id", None)
                if kind == "volume"
                else getattr(self, "_clean_seg_id", None)
            )
            if self._nodeStableId(node) != clean_id:
                self._markAssetDirty(kind)
        if kind == "segmentation":
            self._scheduleAnatomyTreeCoverageRefresh()
        qt.QTimer.singleShot(0, self._refreshProjectAssetUi)

    def _projectDataIsLoaded(self) -> bool:
        return bool(
            self._connected
            and self._hasSelectedProject()
            and self._server_pulled
            and getattr(self, "_loaded_project_name", None) == self._currentProjectName()
        )

    def _markUnsavedChanges(self) -> None:
        if getattr(self, "_suppress_dirty", 0):
            return
        if getattr(self, "_ignore_data_modified", False):
            return
        if self._suppress_asset_ui_updates > 0:
            return
        if not self._projectDataIsLoaded():
            return
        if self._unsaved_changes:
            return
        self._unsaved_changes = True
        self._updateVersionActionButtons()

    def _markAssetDirty(self, kind: str) -> None:
        if getattr(self, "_suppress_dirty", 0):
            return
        if getattr(self, "_ignore_data_modified", False):
            return
        if self._suppress_asset_ui_updates > 0:
            return
        if not self._projectDataIsLoaded():
            return
        if kind == "volume":
            return
        if kind == "segmentation":
            self._dirty_segmentation = True
        elif kind == "ontology":
            self._dirty_ontology = True
        else:
            return
        self._markUnsavedChanges()

    def _clearDirtyAssets(self) -> None:
        self._dirty_segmentation = False
        self._dirty_ontology = False
        self._unsaved_changes = False

    def _selectorCurrentNode(self, selector_name: str):
        selector = getattr(self, selector_name, None)
        if selector is None or not _qt_widget_is_valid(selector):
            return None
        try:
            return selector.currentNode()
        except (RuntimeError, ValueError):
            return None

    def _nodeStableId(self, node) -> str | None:
        if node is None:
            return None
        getter = getattr(node, "GetID", None)
        if not callable(getter):
            return None
        try:
            return getter() or None
        except (RuntimeError, ValueError):
            return None

    def _markSceneClean(self) -> None:
        self._clearDirtyAssets()
        volume = self._selectorCurrentNode("volumeSelector")
        segmentation = self._selectorCurrentNode("segmentationSelector")
        self._clean_volume_id = self._nodeStableId(volume)
        self._clean_seg_id = self._nodeStableId(segmentation)
        self._painted_ids_cache_key = None
        self._painted_ids_cache = set()

    def _armLoadSettle(self) -> None:
        """Ignore Slicer display/load events so they are not treated as edits."""
        self._ignore_data_modified = True
        self._dirty_settle_token = getattr(self, "_dirty_settle_token", 0) + 1
        token = self._dirty_settle_token
        self._markSceneClean()
        def _finish(expected=token):
            if getattr(self, "_dirty_settle_token", 0) != expected:
                return
            self._markSceneClean()
            self._ignore_data_modified = False
            self._updateVersionActionButtons()
            self._refreshAnatomyTreeCoverage()
        qt.QTimer.singleShot(1200, _finish)

    def _hasExplicitUnsavedEdits(self) -> bool:
        return bool(
            getattr(self, "_dirty_segmentation", False)
            or getattr(self, "_dirty_ontology", False)
        )

    def _clearChangeFlags(self) -> None:
        self._clearDirtyAssets()
        self._unshared_version = False

    def _dirtyAssetsToWrite(self) -> tuple[bool, bool, bool]:
        segmentation = bool(getattr(self, "_dirty_segmentation", False))
        ontology = bool(getattr(self, "_dirty_ontology", False))
        if self._unsaved_changes and not (segmentation or ontology):
            return False, True, True
        return False, segmentation, ontology

    def _syncAssetDataObservers(self) -> None:
        try:
            self.removeObservers(self._onAssetDataModified)
        except Exception:
            pass
        self._observeAssetNode("volumeSelector")
        self._observeAssetNode("segmentationSelector")

    def _observeAssetNode(self, selector_name: str) -> None:
        node = self._selectorCurrentNode(selector_name)
        if node is None:
            return
        command = getattr(vtk, "vtkCommand", None)
        modified = getattr(command, "ModifiedEvent", None) if command is not None else None
        if modified is not None:
            self.addObserver(node, modified, self._onAssetDataModified)
        if not node.IsA("vtkMRMLSegmentationNode"):
            return
        segmentation = node.GetSegmentation()
        if segmentation is None:
            return
        seg_cls = getattr(slicer, "vtkSegmentation", None)
        event_names = (
            "SegmentAdded",
            "SegmentRemoved",
            "SegmentModified",
            "RepresentationModified",
        )
        for event_name in event_names:
            event = getattr(seg_cls, event_name, None) if seg_cls is not None else None
            if event is not None:
                self.addObserver(segmentation, event, self._onAssetDataModified)

    def _callerAssetKind(self, caller) -> str | None:
        if caller is None:
            return None
        volume = self._selectorCurrentNode("volumeSelector")
        segmentation = self._selectorCurrentNode("segmentationSelector")
        caller_id = None
        try:
            getter = getattr(caller, "GetID", None)
            if callable(getter):
                caller_id = getter()
        except (RuntimeError, ValueError, AttributeError):
            caller_id = None
        if caller_id:
            if volume is not None and self._nodeStableId(volume) == caller_id:
                return "volume"
            if segmentation is not None and self._nodeStableId(segmentation) == caller_id:
                return "segmentation"
        try:
            if segmentation is not None and caller == segmentation.GetSegmentation():
                return "segmentation"
        except (RuntimeError, AttributeError):
            pass
        class_name = ""
        try:
            class_name = str(caller.GetClassName() if hasattr(caller, "GetClassName") else "")
        except (RuntimeError, AttributeError):
            class_name = ""
        if "Volume" in class_name:
            return "volume"
        if "Segmentation" in class_name:
            return "segmentation"
        return None

    def _onAssetDataModified(self, caller=None, event=None) -> None:
        if self._collecting_coverage:
            return
        kind = self._callerAssetKind(caller)
        if kind:
            self._markAssetDirty(kind)
        else:
            self._markAssetDirty("segmentation")
        if kind != "volume":
            self._scheduleAnatomyTreeCoverageRefresh()

    def _canOpenProject(self) -> bool:
        return bool(self._connected and self._hasSelectedProject() and not self._projectDataIsLoaded())

    def _openDisabledReason(self) -> str:
        if not self._connected:
            return "Connect with GitHub first."
        if not self._hasSelectedProject():
            return "Select a project first."
        if self._projectDataIsLoaded():
            return "This project is already open."
        return ""

    def _canShare(self) -> bool:
        if not self._projectDataIsLoaded():
            return False
        if not self._unshared_version:
            return False
        repo = self._currentRemoteRepo()
        if repo and not repo.get("can_push"):
            return False
        return True

    def _shareDisabledReason(self) -> str:
        if not self._connected:
            return "Connect with GitHub first."
        if not self._hasSelectedProject():
            return "Create or open a project first."
        if not self._projectDataIsLoaded():
            return "Open the project first."
        repo = self._currentRemoteRepo()
        if repo and not repo.get("can_push"):
            return "This project is read-only for your account."
        if not self._unshared_version:
            return "Save a version first."
        return ""

    def _canSaveVersion(self) -> bool:
        if not self._projectDataIsLoaded():
            return False
        if not self._hasExplicitUnsavedEdits():
            return False
        return self._hasVolume() and self._ontologyReadyForCreate()

    def _saveVersionDisabledReason(self) -> str:
        if not self._connected:
            return "Connect with GitHub first."
        if not self._hasSelectedProject():
            return "Create or open a project first."
        if not self._projectDataIsLoaded():
            return "Open the project first."
        if not self._hasExplicitUnsavedEdits():
            return "No changes to save."
        missing = []
        if not self._hasVolume():
            missing.append("3D Volume")
        if not self._ontologyReadyForCreate():
            missing.append("Ontology map")
        if missing:
            return "Fill project data first: %s." % missing
        return ""

    def _canCreateProject(self) -> bool:
        return bool(self._connected and not self._createMissingAssets())

    def _createMissingAssets(self) -> list:
        missing = []
        if not self._hasVolume():
            missing.append("3D Volume")
        if not self._ontologyReadyForCreate():
            missing.append("Ontology map")
        return missing

    def _createDisabledReason(self) -> str:
        if not self._connected:
            return "Connect with GitHub first."
        missing = self._createMissingAssets()
        if missing:
            return "Create needs: %s." % ", ".join(missing)
        return ""

    def _updateVersionActionButtons(self) -> None:
        if not self._connected or self._suppress_asset_ui_updates > 0:
            return
        if not _qt_widget_is_valid(getattr(self, "shareButton", None)):
            return
        create_ok = self._canCreateProject()
        self.createButton.setStyleSheet(BTN_CREATE)
        self.createButton.setEnabled(True)
        self.createButton.setToolTip("Create a new project" if create_ok else self._createDisabledReason())
        open_ok = self._canOpenProject()
        self.openButton.setStyleSheet(BTN_PULL)
        self.openButton.setEnabled(True)
        self.openButton.setToolTip("Open the selected project" if open_ok else self._openDisabledReason())
        save_ok = self._canSaveVersion()
        self.saveVersionButton.setStyleSheet(BTN_SAVE_VERSION)
        self.saveVersionButton.setEnabled(True)
        self.saveVersionButton.setToolTip("" if save_ok else self._saveVersionDisabledReason())
        share_ok = self._canShare()
        self.shareButton.setStyleSheet(BTN_PUSH)
        self.shareButton.setEnabled(True)
        if not share_ok:
            self.shareButton.setToolTip(self._shareDisabledReason())
        elif self._shareNeedsApproval():
            self.shareButton.setToolTip("Send this version to the owner for review")
        else:
            self.shareButton.setToolTip("Share a saved version that is not shared yet")
        can_people = self._canOpenPeople()
        self.peopleButton.setStyleSheet(BTN_PEOPLE)
        self.peopleButton.setEnabled(True)
        self.peopleButton.setToolTip(
            "See who is on this project" if can_people else self._peopleDisabledReason()
        )
        can_delete = self._canDeleteProject()
        self.deleteButton.setStyleSheet(BTN_DELETE)
        self.deleteButton.setEnabled(True)
        self.deleteButton.setToolTip("" if can_delete else self._deleteDisabledReason())

    def _isCurrentProjectOwner(self) -> bool:
        repo = self._currentRemoteRepo()
        return bool(self._connected and repo and repo.get("role") == "owner")

    def _rememberPeopleAccess(self, full_name: str, access: str | None = None) -> str:
        name = (full_name or "").strip()
        if not name:
            return "share"
        if access is None:
            if self._isCurrentProjectOwner():
                access = "share"
            else:
                access = people_access_for(name, self._githubLogin())
        cache = getattr(self, "_people_access_cache", None)
        if cache is None:
            self._people_access_cache = {}
            cache = self._people_access_cache
        cache[name.lower()] = access
        return access

    def _shareNeedsApproval(self) -> bool:
        if self._isCurrentProjectOwner():
            return False
        full_name = self._currentProjectName()
        if not full_name:
            return False
        cache = getattr(self, "_people_access_cache", {}) or {}
        access = cache.get(full_name.lower())
        return access == PEOPLE_ACCESS_APPROVAL

    def _canOpenPeople(self) -> bool:
        return bool(self._connected and self._hasSelectedProject())

    def _peopleDisabledReason(self) -> str:
        if not self._connected:
            return "Connect with GitHub first."
        return "Select a project first."

    def _canDeleteProject(self) -> bool:
        return self._isCurrentProjectOwner()

    def _deleteDisabledReason(self) -> str:
        if not self._connected:
            return "Connect with GitHub first."
        if not self._hasSelectedProject():
            return "Select a project first."
        repo = self._currentRemoteRepo()
        if repo and repo.get("role") != "owner":
            return "Only the owner can delete this project."
        return "Select a project first."

    def _clearProjectSelection(self) -> None:
        self.projectCombo.blockSignals(True)
        none_index = self.projectCombo.findText(PROJECT_NONE_LABEL)
        self.projectCombo.setCurrentIndex(none_index if none_index >= 0 else 0)
        self.projectCombo.blockSignals(False)

    def _applyProjectHistoryBundle(self, history: dict | None) -> str | None:
        previous_id = getattr(self, "_currentVersionId", None)
        previous_sha = (
            ((getattr(self, "_project_history_bundle", None) or {}).get("sha_by_id") or {}).get(
                previous_id
            )
            if previous_id
            else None
        )
        bundle = history or {}
        self._project_history_bundle = bundle
        sha_by_id = bundle.get("sha_by_id") or {}
        id_by_sha = {sha: version_id for version_id, sha in sha_by_id.items()}
        if previous_sha and previous_sha in id_by_sha:
            self._currentVersionId = id_by_sha[previous_sha]
        else:
            self._currentVersionId = bundle.get("head_id")
            if not self._currentVersionId:
                specs = bundle.get("version_specs") or []
                self._currentVersionId = specs[-1].get("id") if specs else None
        return self._currentVersionId

    def _historyHasUnsharedVersion(self, history: dict | None = None) -> bool:
        bundle = history if history is not None else getattr(self, "_project_history_bundle", None)
        for row in (bundle or {}).get("commit_history") or []:
            if len(row) > 4 and str(row[4]).lower() == "local":
                return True
        return False

    def _shouldShowCommitHistory(self) -> bool:
        return self._hasSelectedProject() and self._server_pulled

    def _updateCommitHistoryPanel(self) -> None:
        if not getattr(self, "historyTableWidget", None):
            return
        if self._shouldShowCommitHistory():
            self.historyPlaceholder.setVisible(False)
            self.historyTableWidget.setVisible(True)
            self._refreshHistoryTable()
            return

        self.historyPlaceholder.setVisible(True)
        self.historyTableWidget.setVisible(False)
        self.historyTableWidget.setRowCount(0)
        if getattr(self, "checkedOutLabel", None):
            self.checkedOutLabel.setVisible(False)
        if not self._connected:
            self.historyPlaceholder.setText("Connect with GitHub to begin.")
        elif self._hasSelectedProject():
            self.historyPlaceholder.setText("Open a project to load version history.")
        else:
            self.historyPlaceholder.setText(
                "Version history appears after you create or open a project."
            )

    def _applyOntologyDocument(self, document) -> None:
        self._ontology_document = document
        combo = getattr(self, "ontologyPresetCombo", None)
        if (
            combo is not None
            and self._ontology_server_combo_index >= 0
            and _qt_combo_index(combo) == self._ontology_server_combo_index
        ):
            self._project_ontology_document = document
        progress = getattr(self, "_progressDialog", None)
        if progress is not None and _qt_widget_is_valid(progress):
            self._ontology_graph_pending = True
        else:
            self._applyOntologyGraph(document)
            self._updateRightDockAvailability()
        self._markAssetDirty("ontology")
        self._updateVersionActionButtons()

    def _applyOntologyGraph(self, document) -> None:
        if not document or not self.logic:
            return
        canvas = getattr(self.logic, "_dependencyCanvas", None)
        if canvas is None or not _qt_widget_is_valid(canvas):
            self.logic._dependencyCanvas = None
            return
        try:
            self._painted_ids_cache_key = None
            canvas.set_specs(
                document_to_graph_specs(document),
                graph_title=document.get("name"),
                painted_ids=self._collectPaintedOntologyIds(),
                preserve_expansion=True,
            )
            self._scheduleAnatomyTreeCoverageRefresh()
        except (RuntimeError, ValueError):
            self.logic._dependencyCanvas = None

    def _flushPendingOntologyGraph(self) -> None:
        if not getattr(self, "_ontology_graph_pending", False):
            return
        self._ontology_graph_pending = False
        self._applyOntologyGraph(getattr(self, "_ontology_document", None))
        self._updateRightDockAvailability()

    def getOntologyGraphPayload(self):
        if not self._connected:
            return {
                "specs": [],
                "title": "Ontology",
                "description": "Connect with GitHub to begin.",
            }
        if self._hasSelectedProject() and not self._server_pulled:
            return {
                "specs": [],
                "title": "Ontology",
                "description": "Anatomy tree is not available — Open a project first.",
            }
        if not self._ontology_document:
            return {
                "specs": [],
                "title": "Ontology",
                "description": "No ontology loaded — choose a preset or load JSON.",
            }
        document = self._ontology_document
        return {
            "specs": document_to_graph_specs(document),
            "title": document.get("name", "Ontology"),
            "description": "",
        }

    def onProjectChanged(self, _index: int) -> None:
        if self._hasSelectedProject() and not self._connected:
            self._appendFeed("Connect with GitHub to open a remote project.", error=True)
            self.projectCombo.blockSignals(True)
            self._clearProjectSelection()
            self.projectCombo.blockSignals(False)
            return

        if self._hasSelectedProject():
            name = self._currentProjectName()
            if name == getattr(self, "_loaded_project_name", None):
                self._server_pulled = True
            else:
                self._server_pulled = False
                self._project_history_bundle = None
            self._refreshUiState()
            self._appendFeed("Project selected: %s" % name)
            return

        self._currentVersionId = None
        self._refreshUiState()
        self._appendFeed("No project selected — Create a new project or wait for an invitation.")

    def _versionDisplayTag(self, version_id: str) -> str:
        bundle = getattr(self, "_project_history_bundle", None) or {}
        tags = bundle.get("tags_by_id") or {}
        return str(tags.get(version_id, version_id))

    def getVersionTreePayload(self):
        if not self._connected:
            return {
                "specs": [],
                "title": "Version tree",
                "description": "Connect with GitHub to begin.",
            }
        if not self._hasSelectedProject():
            return {
                "specs": [],
                "title": "Version tree",
                "description": "Version tree is not available — no project selected.",
            }
        if not self._server_pulled:
            return {
                "specs": [],
                "title": "Version tree",
                "description": "Version tree is not available — Open a project first.",
            }
        return {
            "specs": list((getattr(self, "_project_history_bundle", None) or {}).get("version_specs", [])),
            "title": self._currentProjectName() or "Version tree",
            "description": "",
        }

    def onOntologyPresetChanged(self, index: int) -> None:
        try:
            if index == ONTOLOGY_COMBO_NONE_INDEX:
                self._clearOntologyDocument()
                return
            if index == self._ontology_server_combo_index:
                self._restoreProjectOntology(notify=True)
                return
            preset_index = index - 1
            if preset_index < 0 or preset_index >= len(self._ontology_preset_ids):
                return
            preset_id = self._ontology_preset_ids[preset_index]
            try:
                document = load_preset(preset_id)
            except (OSError, ValueError) as error:
                self._appendFeed("Ontology preset error: %s" % error, error=True)
                return
            self._applyOntologyDocument(document)
        finally:
            qt.QTimer.singleShot(0, self._refreshProjectAssetUi)

    def onOntologyJsonHelp(self) -> None:
        dialog = OntologyJsonHelpDialog(slicer.util.mainWindow())
        dialog.exec_()

    def onLoadOntologyJson(self) -> None:
        path = qt.QFileDialog.getOpenFileName(
            None,
            "Load ontology JSON",
            os.path.expanduser("~"),
            ONTOLOGY_JSON_FILE_FILTER,
        )
        if isinstance(path, tuple):
            path = path[0]
        if not path:
            return
        try:
            document = load_ontology_file(path)
        except (OSError, ValueError) as error:
            self._appendFeed("Invalid ontology JSON: %s" % error, error=True)
            return
        self._applyOntologyDocument(document)
        self._setOntologyComboLoadedFilename(document=document)
        self._appendFeed("Ontology imported: %s (%d node(s))" % (document["name"], len(document["nodes"])))

    def onEditOntology(self) -> None:
        self._ensureOntologyFromCombo()
        if not self._ontology_document:
            self._appendFeed("No ontology loaded — choose a preset or load JSON first.", error=True)
            return
        try:
            dialog = OntologyEditorDialog(self._ontology_document, slicer.util.mainWindow())
            if dialog.exec_() != qt.QDialog.Accepted:
                return
            self._applyOntologyDocument(dialog.result_document())
            self._appendFeed("Ontology edited: %s (UI)" % self._ontology_document["name"])
        except Exception as exc:
            logging.exception("Ontology editor failed")
            self._appendFeed("Ontology editor failed: %s" % exc, error=True)

    def onExportOntologyJson(self) -> None:
        if not self._ontology_document:
            self._appendFeed("No ontology to export.", error=True)
            return
        default_name = (self._ontology_document.get("name") or "ontology").replace(" ", "_") + ".json"
        path = qt.QFileDialog.getSaveFileName(
            None,
            "Export ontology JSON",
            os.path.join(os.path.expanduser("~"), default_name),
            ONTOLOGY_JSON_FILE_FILTER,
        )
        if isinstance(path, tuple):
            path = path[0]
        if not path:
            return
        try:
            save_ontology_file(self._ontology_document, path)
        except OSError as error:
            self._appendFeed("Export failed: %s" % error, error=True)
            return
        self._appendFeed("Ontology exported: %s" % path)

    def enter(self) -> None:
        if getattr(self, "volumeSelector", None):
            self.volumeSelector.setMRMLScene(slicer.mrmlScene)
        if getattr(self, "segmentationSelector", None):
            self.segmentationSelector.setMRMLScene(slicer.mrmlScene)
        self._collapseDataProbe()

    def exit(self) -> None:
        self._restoreDataProbe()

    def _dataProbeWidget(self):
        mw = slicer.util.mainWindow()
        if mw is None:
            return None
        try:
            return slicer.util.findChild(mw, "DataProbeCollapsibleWidget")
        except (IndexError, LookupError, RuntimeError, AttributeError):
            return mw.findChild("QWidget", "DataProbeCollapsibleWidget")

    def _collapseDataProbe(self) -> None:
        data_probe = self._dataProbeWidget()
        if data_probe is None or not hasattr(data_probe, "collapsed"):
            return
        if self._dataProbeWasCollapsed is None:
            self._dataProbeWasCollapsed = bool(data_probe.collapsed)
        data_probe.collapsed = True

    def _restoreDataProbe(self) -> None:
        data_probe = self._dataProbeWidget()
        if data_probe is None or not hasattr(data_probe, "collapsed"):
            self._dataProbeWasCollapsed = None
            return
        if self._dataProbeWasCollapsed is not None:
            data_probe.collapsed = self._dataProbeWasCollapsed
        self._dataProbeWasCollapsed = None

    def cleanup(self) -> None:
        self._stopNotificationsPolling()
        self._stopMessagesPolling()
        self._stopMessageSend()
        self._restoreDataProbe()
        self._closeProgress()
        self._closeLogicDialogs()
        self._disconnectProjectAssetSignals()
        self._teardownRightDock()
        if self._rightDock and slicer.util.mainWindow():
            slicer.util.mainWindow().removeDockWidget(self._rightDock)
            self._rightDock.deleteLater()
        self._rightDock = None
        self.removeObservers()

    def _openProgress(self, title: str, label: str) -> None:
        self._closeProgress()
        dialog = qt.QDialog(slicer.util.mainWindow())
        dialog.setWindowTitle(title)
        dialog.setModal(True)
        dialog.setWindowModality(qt.Qt.ApplicationModal)
        dialog.setWindowFlags(qt.Qt.Dialog | qt.Qt.CustomizeWindowHint | qt.Qt.WindowTitleHint)
        layout = qt.QVBoxLayout(dialog)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)
        text = qt.QLabel(label)
        text.setWordWrap(True)
        bar = qt.QProgressBar()
        bar.setRange(0, 0)
        bar.setTextVisible(False)
        bar.setMinimumWidth(280)
        layout.addWidget(text)
        layout.addWidget(bar)
        dialog.resize(340, 90)
        dialog.show()
        slicer.app.processEvents()
        self._progressDialog = dialog
        self._progressLabel = text
        self._progressBar = bar
        set_wait_callback(self._pulseProgress)
        timer = qt.QTimer(dialog)
        timer.setInterval(50)
        timer.connect("timeout()", self._pulseProgress)
        timer.start()
        self._progressTimer = timer

    def _pulseProgress(self) -> None:
        if getattr(self, "_pulsing_progress", False):
            return
        self._pulsing_progress = True
        try:
            bar = getattr(self, "_progressBar", None)
            if bar is not None:
                try:
                    bar.repaint()
                except (RuntimeError, ValueError):
                    pass
            slicer.app.processEvents()
        finally:
            self._pulsing_progress = False

    def _setProgressStep(self, step: int, total: int, label: str) -> None:
        bar = getattr(self, "_progressBar", None)
        if bar is not None:
            try:
                bar.setRange(0, max(1, total))
                bar.setValue(max(0, min(step, total)))
            except (RuntimeError, ValueError):
                pass
        self._updateProgress(label)

    def _updateProgress(self, label: str) -> None:
        widget = getattr(self, "_progressLabel", None)
        if widget is None:
            return
        try:
            widget.setText(label)
        except (RuntimeError, ValueError):
            return
        self._flushProgress()

    def _flushProgress(self) -> None:
        """Paint the dialog now, before a blocking C++ load freezes the UI thread."""
        dialog = getattr(self, "_progressDialog", None)
        label = getattr(self, "_progressLabel", None)
        bar = getattr(self, "_progressBar", None)
        for widget in (label, bar, dialog):
            if widget is None:
                continue
            try:
                widget.update()
                widget.repaint()
            except (RuntimeError, ValueError):
                pass
        try:
            qt.QCoreApplication.sendPostedEvents()
        except (AttributeError, RuntimeError, TypeError):
            pass
        self._pulseProgress()
        try:
            slicer.app.processEvents(qt.QEventLoop.ExcludeUserInputEvents, 80)
        except (AttributeError, TypeError, RuntimeError):
            self._pulseProgress()

    def _pauseProgressPulse(self) -> None:
        set_wait_callback(None)
        timer = getattr(self, "_progressTimer", None)
        if timer is None:
            return
        try:
            timer.stop()
        except (RuntimeError, ValueError):
            pass

    def _closeProgress(self) -> None:
        set_wait_callback(None)
        timer = getattr(self, "_progressTimer", None)
        self._progressTimer = None
        if timer is not None:
            try:
                timer.stop()
                timer.deleteLater()
            except (RuntimeError, ValueError):
                pass
        self._progressLabel = None
        self._progressBar = None
        dialog = getattr(self, "_progressDialog", None)
        self._progressDialog = None
        if dialog is not None:
            try:
                dialog.hide()
                dialog.close()
                dialog.deleteLater()
            except (RuntimeError, ValueError):
                pass
        slicer.app.processEvents()
        self._flushPendingOntologyGraph()

    def onConnect(self) -> None:
        if self._connected:
            self._promptDisconnect()
            return

        self.connectButton.setEnabled(False)
        self.connectionStatusLabel.text = "Connecting…"
        self.connectionStatusLabel.setStyleSheet(STATUS_NEUTRAL)
        self._appendFeed("Connecting…")
        self._openProgress("GitHub", "Checking GitHub CLI…")
        try:
            self._updateProgress("Checking GitHub CLI…")
            ensure_tools()
            existing_login = current_login()
        except GitHubAuthError as error:
            self._connectFailed(error)
            return
        self._closeProgress()

        if existing_login:
            choice = self._promptExistingGitHubAccount(existing_login)
            if choice == "cancel":
                self.connectButton.setEnabled(True)
                self.connectionStatusLabel.text = "Not connected"
                self.connectionStatusLabel.setStyleSheet(STATUS_NEUTRAL)
                self._appendFeed("Connection cancelled.")
                return
            if choice == "switch":
                session = self._switchGitHubAccount(existing_login)
                if session is None:
                    return
                self.connectButton.setEnabled(True)
                self._applyGitHubSession(session)
                return

        if not existing_login:
            session = self._signInThenConnect()
            if session is None:
                return
            self.connectButton.setEnabled(True)
            self._applyGitHubSession(session)
            return

        self._openProgress("GitHub", "Connecting…")
        try:
            self._updateProgress("Reading GitHub account…")
            session = connect_session()
            self._updateProgress("Connected")
        except GitHubNotSignedInError:
            self._closeProgress()
            session = self._signInThenConnect()
            if session is None:
                return
        except GitHubAuthError as error:
            self._closeProgress()
            self._connectFailed(error)
            return
        self._closeProgress()
        self.connectButton.setEnabled(True)
        self._applyGitHubSession(session)

    def _promptExistingGitHubAccount(self, login: str) -> str:
        box = qt.QMessageBox(slicer.util.mainWindow())
        box.setWindowTitle("GitHub account")
        box.setText("This computer is already signed in to GitHub as %s." % login)
        box.setInformativeText(
            "Continue with this account, or switch to a different GitHub account?"
        )
        continue_btn = box.addButton("Continue", qt.QMessageBox.AcceptRole)
        switch_btn = box.addButton("Switch account", qt.QMessageBox.DestructiveRole)
        box.addButton("Cancel", qt.QMessageBox.RejectRole)
        box.setDefaultButton(continue_btn)
        box.exec_()
        clicked = box.clickedButton()
        if clicked == continue_btn:
            return "continue"
        if clicked == switch_btn:
            return "switch"
        return "cancel"

    def _switchGitHubAccount(self, login: str) -> dict | None:
        self._openProgress("GitHub", "Signing out of %s…" % login)
        try:
            self._updateProgress("Signing out of %s…" % login)
            logout_github_cli(login)
        except GitHubAuthError as error:
            self._connectFailed(error)
            return None
        self._closeProgress()
        self._appendFeed("Signed out of GitHub account %s." % login)
        return self._signInThenConnect()

    def _connectFailed(self, error) -> None:
        self._closeProgress()
        self.connectButton.setEnabled(True)
        self.connectionStatusLabel.text = "Not connected"
        self.connectionStatusLabel.setStyleSheet(STATUS_NEUTRAL)
        slicer.util.warningDisplay(str(error))
        self._appendFeed(str(error).split("\n")[0], error=True)

    def _signInThenConnect(self) -> dict | None:
        try:
            open_login_window()
        except GitHubAuthError as error:
            self._connectFailed(error)
            return None
        self._appendFeed("GitHub sign-in window opened.")
        box = qt.QMessageBox(slicer.util.mainWindow())
        box.setWindowTitle("GitHub sign-in")
        box.setText(
            "A GitHub sign-in window opened. Complete these steps there:\n\n"
            "1. Choose Yes if asked to authenticate Git with your GitHub credentials.\n"
            "2. A one-time code is shown in that window (it is also copied to the clipboard).\n"
            "3. Press Enter to open the browser at github.com/login/device.\n"
            "4. Paste the one-time code in the browser and authorize GitHub.\n\n"
            "When that is done, click I have signed in."
        )
        box.setStandardButtons(qt.QMessageBox.Ok | qt.QMessageBox.Cancel)
        box.button(qt.QMessageBox.Ok).setText("I have signed in")
        box.setDefaultButton(qt.QMessageBox.Ok)
        if box.exec_() != qt.QMessageBox.Ok:
            self.connectButton.setEnabled(True)
            self.connectionStatusLabel.text = "Not connected"
            self.connectionStatusLabel.setStyleSheet(STATUS_NEUTRAL)
            self._appendFeed("GitHub sign-in cancelled.")
            return None
        slicer.app.processEvents()
        self._openProgress("GitHub", "Finishing sign-in…")
        try:
            self._updateProgress("Reading GitHub account…")
            session = connect_session()
            self._updateProgress("Connected")
        except GitHubNotSignedInError:
            self._closeProgress()
            self._connectFailed(
                "GitHub sign-in was not completed. Click Connect with GitHub to try again."
            )
            return None
        except GitHubAuthError as error:
            self._closeProgress()
            self._connectFailed(error)
            return None
        self._closeProgress()
        return session

    def _applyGitHubSession(self, session: dict) -> None:
        self._closeProgress()
        self._github_session = session
        self._connected = True
        login = session.get("login") or "unknown"
        repo_count = len(session.get("repos") or [])
        self.connectionStatusLabel.text = "Connected — %s" % login
        self.connectionStatusLabel.setStyleSheet(STATUS_OK)
        self.connectButton.setText("Disconnect")
        self._populateProjectCombo()
        self._refreshUiState()
        self._appendFeed(
            "Connected as %s — %d repository(ies) (owner or collaborator)."
            % (login, repo_count)
        )
        self._startNotificationsPolling()

    def _promptDisconnect(self) -> None:
        box = qt.QMessageBox(slicer.util.mainWindow())
        box.setWindowTitle("Disconnect")
        box.setText(
            "Sign out of GitHub?\n\n"
            + DISCONNECT_GITHUB_HELP
        )
        box.setStandardButtons(qt.QMessageBox.Ok | qt.QMessageBox.Cancel)
        box.button(qt.QMessageBox.Ok).setText("Sign out")
        box.setDefaultButton(qt.QMessageBox.Ok)
        if box.exec_() != qt.QMessageBox.Ok:
            return
        self._disconnectGitHub()

    def _disconnectGitHub(self) -> None:
        login = (self._github_session or {}).get("login") or ""
        self._openProgress("GitHub", "Signing out of GitHub…")
        try:
            self._updateProgress("Signing out of GitHub…")
            logout_github_cli(login or None)
        except GitHubAuthError as error:
            self._closeProgress()
            slicer.util.warningDisplay(str(error))
            self._appendFeed(str(error).split("\n")[0], error=True)
            return
        self._closeProgress()
        self._connected = False
        self._github_session = None
        self.connectButton.setText("Connect with GitHub")
        self.connectionStatusLabel.text = "Not connected"
        self.connectionStatusLabel.setStyleSheet(STATUS_NEUTRAL)
        self._clearProjectSelection()
        self._populateProjectCombo()
        self._loaded_project_name = None
        self._local_project_path = None
        self._server_pulled = False
        self._people_access_cache = {}
        self._clearChangeFlags()
        try:
            self.removeObservers(self._onAssetDataModified)
        except Exception:
            pass
        self._refreshUiState()
        self._appendFeed("Disconnected and signed out of GitHub.")

    def _promptNewProjectConfig(self) -> dict | None:
        dialog = ProjectConfigDialog(slicer.util.mainWindow())
        if dialog.exec_() != qt.QDialog.Accepted:
            return None
        values = dialog.values()
        if not values["name"]:
            self._appendFeed("Project name is required.", error=True)
            return None
        return values

    def onCreateProject(self) -> None:
        try:
            if not self._connected:
                self._appendFeed("Connect with GitHub first.", error=True)
                return
            missing = self._createMissingAssets()
            if missing:
                self._appendFeed("Create needs: %s." % ", ".join(missing), error=True)
                return
        except Exception as error:
            logging.exception("Create validation failed")
            self._appendFeed("Create needs: 3D Volume, Ontology map.", error=True)
            return
        volume_node = self.volumeSelector.currentNode()
        existing_seg = self.segmentationSelector.currentNode() if self.segmentationSelector else None
        name_error = self._segmentationOntologyNameError(existing_seg)
        if name_error:
            self._appendFeed(name_error, error=True)
            return
        config = self._promptNewProjectConfig()
        if config is None:
            return
        try:
            segmentation_node, created_empty = self._ensureSegmentationFromVolume(volume_node)
        except Exception as error:
            slicer.util.warningDisplay("Could not prepare the segmentation:\n%s" % error)
            self._appendFeed("Could not prepare the segmentation: %s" % error, error=True)
            return
        name_error = self._segmentationOntologyNameError(segmentation_node)
        if name_error:
            self._appendFeed(name_error, error=True)
            return
        self.createButton.setEnabled(False)
        self._appendFeed("Creating project « %s »…" % config["name"])
        self._openProgress("Create project", "Creating GitHub project…")
        created = None
        ontology_path = ""
        history = {}
        try:
            self._updateProgress("Creating GitHub project…")
            created = create_private_repository(config["name"], config["description"])
            local_path = created.get("local_path") or ""
            ontology_path = self._writeInitialProjectFiles(
                local_path,
                volume_node,
                segmentation_node,
                config["name"],
            )
            self._updateProgress("Publishing the first version…")
            commit_and_push(local_path, "Initial version")
            self._updateProgress("Preparing project info…")
            ensure_project_info_branch(created["full_name"])
            self._updateProgress("Refreshing project list…")
            history = read_project_history(local_path)
        except (GitHubAuthError, OSError, RuntimeError, ValueError) as error:
            self._closeProgress()
            self.createButton.setEnabled(True)
            self._updateVersionActionButtons()
            slicer.util.warningDisplay(str(error))
            self._appendFeed(str(error).split("\n")[0], error=True)
            return
        login = self._githubLogin()
        try:
            self._github_session["repos"] = list_accessible_repos(login)
        except GitHubAuthError:
            repos = list(self._github_session.get("repos") or [])
            if not any(item.get("full_name") == created["full_name"] for item in repos):
                repos.append(created)
            self._github_session["repos"] = repos
        full_name = created["full_name"]
        local_path = created.get("local_path") or ""
        self.projectCombo.blockSignals(True)
        self._populateProjectCombo()
        restore = self.projectCombo.findText(full_name)
        if restore >= 0:
            self.projectCombo.setCurrentIndex(restore)
        self._loaded_project_name = full_name
        self._local_project_path = local_path
        self._server_pulled = True
        self.projectCombo.blockSignals(False)
        self._applyProjectHistoryBundle(history)
        self._suppress_dirty += 1
        try:
            if ontology_path:
                self._setOntologyComboLoadedFilename(filename=ontology_path)
            self._clearChangeFlags()
            self._syncAssetDataObservers()
            self.createButton.setEnabled(True)
            self._closeProgress()
            self._refreshUiState()
        finally:
            self._suppress_dirty -= 1
        self._clearChangeFlags()
        self._updateVersionActionButtons()
        self._armLoadSettle()
        self._appendFeed("Project created: %s (private, you are the owner)." % full_name)
        if created_empty:
            self._appendFeed("Empty segmentation created from the 3D volume (same dimensions).")
        if config["description"]:
            self._appendFeed("Description: %s" % config["description"])
        if local_path:
            self._appendFeed("Local folder: %s" % local_path)

    def _ensureSegmentationFromVolume(self, volume_node):
        current = self.segmentationSelector.currentNode() if self.segmentationSelector else None
        if current is not None:
            return current, False
        logic = slicer.modules.volumes.logic()
        empty_name = "%s_segmentation" % (volume_node.GetName() if volume_node else "Segmentation")
        labelmap = logic.CreateAndAddLabelVolume(slicer.mrmlScene, volume_node, empty_name)
        if labelmap is None:
            raise RuntimeError("Could not create an empty segmentation from the 3D volume.")
        self._blockProjectAssetSignals(True)
        try:
            self.segmentationSelector.setCurrentNode(labelmap)
        finally:
            self._blockProjectAssetSignals(False)
        return labelmap, True

    def _labelValueFromSegmentName(self, name: str) -> int:
        """Ontology ID from the required name Segment_ID (example: Segment_64)."""
        match = re.search(r"(?i)^segment_(\d+)$", (name or "").strip())
        if not match:
            return 0
        return int(match.group(1))

    def _isAnatomyTreeOpen(self) -> bool:
        canvas = getattr(self.logic, "_dependencyCanvas", None) if self.logic else None
        return _qt_widget_is_valid(canvas)

    def _scheduleAnatomyTreeCoverageRefresh(self) -> None:
        if not self._isAnatomyTreeOpen():
            return
        timer = getattr(self, "_anatomyCoverageTimer", None)
        if timer is None:
            parent = getattr(self, "btnDependencyGraph", None)
            timer = qt.QTimer(parent) if parent is not None else qt.QTimer()
            timer.setSingleShot(True)
            timer.setInterval(400)
            timer.connect("timeout()", self._refreshAnatomyTreeCoverage)
            self._anatomyCoverageTimer = timer
        timer.start()
        later = getattr(self, "_anatomyCoverageRetryTimer", None)
        if later is None:
            parent = getattr(self, "btnDependencyGraph", None)
            later = qt.QTimer(parent) if parent is not None else qt.QTimer()
            later.setSingleShot(True)
            later.setInterval(1400)
            later.connect("timeout()", self._refreshAnatomyTreeCoverage)
            self._anatomyCoverageRetryTimer = later
        later.start()

    def _refreshAnatomyTreeCoverage(self) -> None:
        if not self._isAnatomyTreeOpen():
            return
        canvas = self.logic._dependencyCanvas
        setter = getattr(canvas, "set_painted_ids", None)
        if not callable(setter):
            return
        self._painted_ids_cache_key = None
        setter(self._collectPaintedOntologyIds())

    def _collectPaintedOntologyIds(self) -> set:
        """Ontology IDs that have a Segment_ID in the current segmentation."""
        selector = getattr(self, "segmentationSelector", None)
        if selector is None or not _qt_widget_is_valid(selector):
            return set()
        try:
            node = selector.currentNode()
        except (RuntimeError, ValueError):
            return set()
        if node is None:
            return set()
        cache_key = self._paintedIdsCacheKey(node)
        if cache_key is not None and cache_key == getattr(self, "_painted_ids_cache_key", None):
            return set(self._painted_ids_cache)
        self._collecting_coverage = True
        segment_count = 0
        try:
            class_name = node.GetClassName() if hasattr(node, "GetClassName") else ""
            if "Segmentation" in class_name:
                painted, segment_count = self._paintedIdsFromSegmentation(node)
            else:
                painted = set()
        except Exception:
            logging.exception("Could not read ontology IDs from the segmentation")
            painted = set()
        finally:
            self._collecting_coverage = False
        if painted or segment_count == 0:
            self._painted_ids_cache_key = cache_key
            self._painted_ids_cache = set(painted)
        else:
            self._painted_ids_cache_key = None
            self._painted_ids_cache = set()
        return painted

    def _paintedIdsFromSegmentation(self, segmentation_node) -> tuple[set, int]:
        segmentation = segmentation_node.GetSegmentation()
        if segmentation is None:
            return set(), 0
        painted = set()
        count = int(segmentation.GetNumberOfSegments())
        for index in range(count):
            segment_id = segmentation.GetNthSegmentID(index)
            segment = segmentation.GetSegment(segment_id)
            if segment is None:
                continue
            name = segment.GetName() if hasattr(segment, "GetName") else ""
            value = self._ontologyIdFromSegment(segment, name)
            if value > 0:
                painted.add(str(value))
        return painted, count

    def _ontologyIdFromSegment(self, segment, name: str) -> int:
        value = self._labelValueFromSegmentName(name)
        if value > 0:
            return value
        getter = getattr(segment, "GetLabelValue", None)
        if callable(getter):
            try:
                value = int(getter() or 0)
                if value > 0:
                    return value
            except Exception:
                pass
        match = re.search(r"(?i)(?:segment_|label_)?(\d+)$", (name or "").strip())
        if match:
            return int(match.group(1))
        return 0

    def _paintedIdsCacheKey(self, node):
        try:
            node_id = node.GetID()
            mtime = int(node.GetMTime())
        except (RuntimeError, ValueError, AttributeError):
            return None
        extra = 0
        try:
            if node.IsA("vtkMRMLSegmentationNode"):
                segmentation = node.GetSegmentation()
                if segmentation is not None:
                    extra = int(segmentation.GetMTime())
        except (RuntimeError, ValueError, AttributeError):
            extra = 0
        return (node_id, mtime, extra)

    def _invalidSegmentNameHint(self, name: str) -> str:
        stripped = (name or "").strip()
        if stripped.isdigit():
            return "%s (rename to Segment_%s)" % (stripped, stripped)
        return stripped or "(unnamed)"

    def _segmentationOntologyNameError(self, node) -> str:
        """Return a feed-safe error if segment names are not Segment_ID. Empty if OK."""
        if node is None:
            return ""
        class_name = node.GetClassName() if hasattr(node, "GetClassName") else ""
        if "Segmentation" not in class_name:
            return ""
        _ids, _labels, error = self._collectSegmentationOntologyIds(node)
        return error

    def _collectSegmentationOntologyIds(self, segmentation_node):
        segmentation = segmentation_node.GetSegmentation()
        count = int(segmentation.GetNumberOfSegments())
        ids_array = vtk.vtkStringArray()
        label_values = vtk.vtkIntArray()
        label_values.SetNumberOfValues(count)
        used = {}
        invalid = []
        duplicates = []
        for index in range(count):
            segment_id = segmentation.GetNthSegmentID(index)
            ids_array.InsertNextValue(segment_id)
            segment = segmentation.GetSegment(segment_id)
            name = segment.GetName() if segment is not None else ""
            value = self._labelValueFromSegmentName(name)
            if value <= 0:
                invalid.append(self._invalidSegmentNameHint(name))
                continue
            if value in used:
                duplicates.append("%s and %s (ID %d)" % (used[value], name, value))
                continue
            used[value] = name
            label_values.SetValue(index, value)
            setter = getattr(segment, "SetLabelValue", None)
            if callable(setter):
                setter(value)
        if invalid or duplicates:
            parts = []
            if invalid:
                parts.append(
                    "Name each segment Segment_ID (example: Segment_64). Invalid: "
                    + ", ".join(invalid)
                )
            if duplicates:
                parts.append("Duplicate ontology IDs: " + "; ".join(duplicates))
            return ids_array, label_values, " ".join(parts)
        return ids_array, label_values, ""

    def _segmentationLabelValues(self, segmentation_node):
        ids_array, label_values, error = self._collectSegmentationOntologyIds(segmentation_node)
        if error:
            raise ValueError(error)
        return ids_array, label_values

    def _exportSegmentationPreservingLabels(self, segmentation_node, labelmap, reference_volume=None) -> bool:
        ids_array, label_values = self._segmentationLabelValues(segmentation_node)
        extent_mode = slicer.vtkSegmentation.EXTENT_UNION_OF_EFFECTIVE_SEGMENTS
        merged = slicer.vtkOrientedImageData()
        exported = slicer.vtkSlicerSegmentationsModuleLogic.GenerateMergedLabelmapInReferenceGeometry(
            segmentation_node,
            reference_volume,
            ids_array,
            extent_mode,
            merged,
            label_values,
        )
        if exported:
            return bool(
                slicer.vtkSlicerSegmentationsModuleLogic.CreateLabelmapVolumeFromOrientedImageData(
                    merged, labelmap
                )
            )
        color_table = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLColorTableNode")
        try:
            max_label = 0
            for index in range(label_values.GetNumberOfValues()):
                max_label = max(max_label, int(label_values.GetValue(index)))
            color_table.SetTypeToUser()
            color_table.SetNumberOfColors(max_label + 1)
            if hasattr(color_table, "SetNamesInitialisedOn"):
                color_table.SetNamesInitialisedOn()
            segmentation = segmentation_node.GetSegmentation()
            for index in range(ids_array.GetNumberOfValues()):
                segment = segmentation.GetSegment(ids_array.GetValue(index))
                value = int(label_values.GetValue(index))
                color = segment.GetColor() if segment is not None else (0.5, 0.5, 0.5)
                name = segment.GetName() if segment is not None else "Segment_%d" % value
                color_table.SetColor(
                    value,
                    name,
                    float(color[0]),
                    float(color[1]),
                    float(color[2]),
                    1.0,
                )
            return bool(
                slicer.vtkSlicerSegmentationsModuleLogic.ExportSegmentsToLabelmapNode(
                    segmentation_node,
                    [],
                    labelmap,
                    reference_volume,
                    extent_mode,
                    color_table,
                )
            )
        finally:
            slicer.mrmlScene.RemoveNode(color_table)

    def _saveNodeAsNifti(self, manager: DataManager, node, folder: str, filename: str, reference_volume=None) -> str:
        path = os.path.join(folder, filename)
        class_name = node.GetClassName() if node else ""
        if "Segmentation" in class_name:
            labelmap = slicer.mrmlScene.AddNewNodeByClass(
                "vtkMRMLLabelMapVolumeNode", "%s_labelmap" % node.GetName()
            )
            try:
                exported = self._exportSegmentationPreservingLabels(node, labelmap, reference_volume)
                if not exported:
                    raise RuntimeError(
                        "Could not save the segmentation with ontology IDs from segment names."
                    )
                manager.save_volume(labelmap, path)
            finally:
                slicer.mrmlScene.RemoveNode(labelmap)
            return path
        manager.save_volume(node, path)
        return path

    def _savedProjectFileStem(self, folder: str) -> str:
        files = DataManager().discover_project_files(folder)
        volume_path = files.get("volume")
        if volume_path:
            base = DataManager._basename_without_extension(volume_path)
            suffix = "_volume"
            if base.lower().endswith(suffix):
                return base[: -len(suffix)] or "project"
            return base or "project"
        full_name = self._currentProjectName() or "project"
        repo = full_name.partition("/")[2] or full_name
        return self._projectFileStem(repo)

    def _writeProjectFiles(
        self,
        folder: str,
        volume_node,
        segmentation_node,
        stem: str,
        write_volume: bool = True,
        write_segmentation: bool = True,
        write_ontology: bool = True,
    ) -> str:
        if not folder:
            raise GitHubAuthError("The project folder is missing.")
        if not (write_volume or write_segmentation or write_ontology):
            raise GitHubAuthError("No new changes to save.")
        manager = DataManager()
        if write_volume:
            self._saveNodeAsNifti(manager, volume_node, folder, "%s_volume.nii.gz" % stem)
        if write_segmentation:
            self._saveNodeAsNifti(
                manager,
                segmentation_node,
                folder,
                "%s_segmentation.nii.gz" % stem,
                reference_volume=volume_node,
            )
        ontology_path = os.path.join(folder, "%s_ontologie.json" % stem)
        if write_ontology:
            save_ontology_file(self._ontology_document, ontology_path)
        return ontology_path

    def _writeInitialProjectFiles(self, folder: str, volume_node, segmentation_node, project_name: str) -> str:
        return self._writeProjectFiles(
            folder,
            volume_node,
            segmentation_node,
            self._projectFileStem(project_name),
        )

    def onPeople(self) -> None:
        if not self._canOpenPeople():
            reason = self._peopleDisabledReason()
            if reason:
                self._appendFeed(reason, error=True)
            return
        full_name = self._currentProjectName()
        can_add = self._isCurrentProjectOwner()
        self.peopleButton.setEnabled(False)
        self._openProgress("People", "Reading who is on this project…")
        try:
            self._updateProgress("Reading who is on this project…")
            people = list_project_people(full_name)
        except (GitHubAuthError, OSError, RuntimeError, ValueError) as error:
            self._closeProgress()
            self._updateVersionActionButtons()
            self._appendFeed(str(error).split("\n")[0], error=True)
            return
        self._closeProgress()
        self._updateVersionActionButtons()
        qt.QTimer.singleShot(
            0,
            lambda n=full_name, p=people, a=can_add: self._showPeopleDialog(n, p, a),
        )

    def _showPeopleDialog(self, full_name: str, people, can_add: bool) -> None:
        current = list(people or [])
        while True:
            self._pending_people_action = None
            dialog = None
            try:
                dialog = PeopleDialog(slicer.util.mainWindow(), current, can_add=can_add)
                if can_add:
                    dialog.set_add_handler(
                        lambda dlg, name=full_name: self._queueAddColleague(name, dlg)
                    )
                    dialog.set_remove_handler(
                        lambda dlg, name=full_name: self._queueRemoveColleague(name, dlg)
                    )
                self._people_dialog_open = True
                try:
                    dialog.exec_()
                finally:
                    self._people_dialog_open = False
            except (RuntimeError, TypeError, AttributeError, ValueError) as error:
                self._appendFeed(str(error).split("\n")[0], error=True)
                return
            action = self._pending_people_action
            self._pending_people_action = None
            if not action:
                return
            kind, payload = action
            if kind == "add":
                current = self._applyAddColleague(full_name, payload, current)
            else:
                current = self._applyRemoveColleague(full_name, payload, current)

    def _closePeopleDialog(self, dialog) -> None:
        try:
            dialog.hide_username_dropdown()
        except (RuntimeError, AttributeError):
            pass
        try:
            qt.QDialog.done(dialog, 1)
        except (TypeError, RuntimeError, AttributeError):
            try:
                dialog.close()
            except (TypeError, RuntimeError, AttributeError):
                pass

    def _queueAddColleague(self, full_name: str, dialog) -> None:
        username = dialog.username()
        if not username:
            dialog.set_status("Enter a GitHub username.", error=True)
            return
        for person in dialog.people():
            login = str(person.get("login") or "")
            if login.lower() != username.lower():
                continue
            role = person.get("role")
            if role == "pending":
                dialog.set_status("An invitation is already waiting for %s." % login, error=True)
            elif role == "owner":
                dialog.set_status("You are already the owner of this project.", error=True)
            else:
                dialog.set_status("%s is already on this project." % login, error=True)
            return
        self._pending_people_action = ("add", {
            "username": username,
            "access": dialog.selected_access(),
            "task": dialog.task_title(),
        })
        self._closePeopleDialog(dialog)

    def _queueRemoveColleague(self, full_name: str, dialog) -> None:
        person = dialog.selected_person()
        if not person:
            dialog.set_status("Select a colleague first.", error=True)
            return
        login = str(person.get("login") or "").strip()
        role = person.get("role")
        if role == "owner":
            dialog.set_status("You cannot remove the owner.", error=True)
            return
        if role == "pending":
            question = "Cancel the invitation for %s?" % login
        else:
            question = (
                "Remove %s from this project?\n\n"
                "They will no longer see it after they Connect."
                % login
            )
        confirmed = slicer.util.confirmYesNoDisplay(question, windowTitle="People")
        if not confirmed:
            return
        self._pending_people_action = ("remove", dict(person))
        self._closePeopleDialog(dialog)

    def _applyAddColleague(self, full_name: str, payload, current):
        if isinstance(payload, dict):
            username = str(payload.get("username") or "").strip()
            access = str(payload.get("access") or "share")
            task = str(payload.get("task") or "").strip()
        else:
            username = str(payload or "").strip()
            access = "share"
            task = ""
        access_label = "Needs approval" if access == "approval" else "Can share"
        self._openProgress("People", "Adding colleague…")
        try:
            self._updateProgress("Adding colleague…")
            outcome = invite_project_colleague(full_name, username, access, task=task)
            self._updateProgress("Updating the people list…")
            people = list_project_people(full_name)
        except (GitHubAuthError, OSError, RuntimeError, ValueError) as error:
            self._closeProgress()
            self._appendFeed(str(error).split("\n")[0], error=True)
            return current
        self._closeProgress()
        if outcome == "already":
            message = "%s is already on this project." % username
        else:
            message = (
                "Invitation sent to %s (%s). They can join from 3D Slicer after they Connect."
                % (username, access_label)
            )
            if task:
                message = "%s Task: %s." % (message, task)
        self._appendFeed(message)
        return people

    def _applyRemoveColleague(self, full_name: str, person: dict, current):
        login = str(person.get("login") or "").strip()
        role = person.get("role")
        if role == "pending":
            progress_label = "Cancelling invitation…"
        else:
            progress_label = "Removing colleague…"
        self._openProgress("People", progress_label)
        try:
            self._updateProgress(progress_label)
            if role == "pending":
                cancel_project_invitation(full_name, person.get("invitation_id"))
            else:
                remove_project_colleague(full_name, login)
            forget_people_access(full_name, login)
        except (GitHubAuthError, OSError, RuntimeError, ValueError) as error:
            self._closeProgress()
            self._appendFeed(str(error).split("\n")[0], error=True)
            return current
        self._closeProgress()
        login_key = login.lower()
        people = [
            item
            for item in (current or [])
            if str(item.get("login") or "").strip().lower() != login_key
            or item.get("role") == "owner"
        ]
        if role == "pending":
            message = "Cancelled the invitation for %s." % login
        else:
            message = "Removed %s from the project." % login
        self._appendFeed(message)
        return people

    def _promptJoinProject(self, invitation: dict) -> str:
        full_name = invitation.get("full_name") or "this project"
        box = qt.QMessageBox(slicer.util.mainWindow())
        box.setWindowTitle("Join project")
        box.setText("You were invited to %s." % full_name)
        box.setInformativeText("Join this project now? You can Open it afterwards.")
        join_btn = box.addButton("Join", qt.QMessageBox.AcceptRole)
        decline_btn = box.addButton("Decline", qt.QMessageBox.DestructiveRole)
        box.addButton("Later", qt.QMessageBox.RejectRole)
        box.setDefaultButton(join_btn)
        box.exec_()
        clicked = box.clickedButton()
        if clicked == join_btn:
            return "join"
        if clicked == decline_btn:
            return "decline"
        return "later"

    def _joinIncomingInvitation(self, invitation: dict) -> None:
        full_name = invitation.get("full_name") or ""
        self._openProgress("Join project", "Joining %s…" % full_name)
        try:
            self._updateProgress("Joining %s…" % full_name)
            accept_project_invitation(invitation.get("id"))
            self._updateProgress("Refreshing project list…")
            session = connect_session()
            self._github_session = session
            self._populateProjectCombo()
            restore = self.projectCombo.findText(full_name)
            if restore >= 0:
                self.projectCombo.blockSignals(True)
                self.projectCombo.setCurrentIndex(restore)
                self.projectCombo.blockSignals(False)
            self._refreshUiState()
        except (GitHubAuthError, OSError, RuntimeError, ValueError) as error:
            self._closeProgress()
            self._appendFeed(str(error).split("\n")[0], error=True)
            return
        self._closeProgress()
        self._appendFeed("Joined %s. Open it when you are ready." % full_name)

    def _declineIncomingInvitation(self, invitation: dict) -> None:
        full_name = invitation.get("full_name") or "the project"
        try:
            decline_project_invitation(invitation.get("id"))
        except (GitHubAuthError, OSError, RuntimeError, ValueError) as error:
            self._appendFeed(str(error).split("\n")[0], error=True)
            return
        self._appendFeed("Declined the invitation to %s." % full_name)

    def _startNotificationsPolling(self) -> None:
        self._stopNotificationsPolling()
        parent = getattr(self, "notificationsBell", None)
        if parent is None or not _qt_widget_is_valid(parent):
            parent = slicer.util.mainWindow()
        timer = qt.QTimer(parent)
        timer.setInterval(_NOTIFICATIONS_POLL_MS)
        timer.connect("timeout()", self._onNotificationsPoll)
        self._notificationsTimer = timer
        timer.start()
        self._runNotificationChecks(announce=False)

    def _stopNotificationsPolling(self) -> None:
        timer = getattr(self, "_notificationsTimer", None)
        self._notificationsTimer = None
        if timer is not None:
            try:
                timer.stop()
                timer.deleteLater()
            except (RuntimeError, ValueError):
                pass
        self._stopNotificationsFetch()

    def _stopNotificationsFetch(self) -> None:
        process = getattr(self, "_notificationsProcess", None)
        self._notificationsProcess = None
        self._notificationFetchQueue = []
        self._notificationFetchResults = []
        self._notificationFetchKind = ""
        self._refreshing_notifications = False
        if process is None:
            return
        try:
            if int(process.state()) != 0:
                process.kill()
            process.deleteLater()
        except (AttributeError, RuntimeError, TypeError, ValueError):
            pass

    def _ownedProjectNames(self) -> list[str]:
        names = []
        for repo in ((self._github_session or {}).get("repos") or []):
            if repo.get("role") != "owner":
                continue
            full_name = repo.get("full_name")
            if full_name:
                names.append(full_name)
        return names

    def _notificationOwnerLogins(self) -> list[str]:
        owners = []
        seen = set()
        for name in self._ownedProjectNames():
            owner = str(name or "").partition("/")[0].strip()
            key = owner.lower()
            if not owner or key in seen:
                continue
            seen.add(key)
            owners.append(owner)
        return owners

    def _onNotificationsPoll(self) -> None:
        self._runNotificationChecks(announce=True)

    def _runNotificationChecks(self, announce: bool = False) -> None:
        process = getattr(self, "_notificationsProcess", None)
        if process is not None:
            try:
                if int(process.state()) != 0:
                    return
            except (AttributeError, RuntimeError, TypeError, ValueError):
                return
        if not self._connected:
            self._clearNotificationsDisplay()
            return
        progress = getattr(self, "_progressDialog", None)
        if progress is not None and _qt_widget_is_valid(progress):
            return
        if getattr(self, "_offering_invitations", False):
            return
        if getattr(self, "_people_dialog_open", False):
            return
        if getattr(self, "_notifications_popup_open", False):
            return
        queue = []
        for owner in self._notificationOwnerLogins():
            queue.append({"kind": "review", "args": notification_review_fetch_args(owner)})
        queue.append({"kind": "invite", "args": incoming_invitations_fetch_args()})
        self._notificationFetchQueue = queue
        self._notificationFetchResults = []
        self._notificationFetchAnnounce = bool(announce)
        self._refreshing_notifications = True
        self._startNextNotificationFetch()

    def _startNextNotificationFetch(self) -> None:
        queue = getattr(self, "_notificationFetchQueue", None) or []
        if not queue:
            incoming = list(getattr(self, "_notificationFetchResults", []) or [])
            announce = bool(getattr(self, "_notificationFetchAnnounce", False))
            self._notificationsProcess = None
            self._notificationFetchKind = ""
            self._refreshing_notifications = False
            self._applyNotificationRequests(incoming, announce=announce)
            return
        job = queue.pop(0)
        self._notificationFetchQueue = queue
        self._notificationFetchKind = job.get("kind") or ""
        gh = find_gh()
        if not gh:
            self._startNextNotificationFetch()
            return
        parent = getattr(self, "notificationsBell", None)
        if parent is None or not _qt_widget_is_valid(parent):
            parent = slicer.util.mainWindow()
        fetch = qt.QProcess(parent)
        try:
            env = qt.QProcessEnvironment.systemEnvironment()
            env.insert("GH_PAGER", "")
            env.insert("GIT_PAGER", "")
            env.insert("GH_PROMPT_DISABLED", "1")
            env.insert("GIT_TERMINAL_PROMPT", "0")
            fetch.setProcessEnvironment(env)
        except (AttributeError, TypeError, RuntimeError):
            pass
        fetch.connect("finished(int)", self._onNotificationFetchFinished)
        self._notificationsProcess = fetch
        fetch.start(gh, job.get("args") or [])

    def _onNotificationFetchFinished(self, _code=0) -> None:
        process = getattr(self, "_notificationsProcess", None)
        kind = getattr(self, "_notificationFetchKind", "")
        self._notificationsProcess = None
        self._notificationFetchKind = ""
        if not getattr(self, "_refreshing_notifications", False):
            if process is not None:
                try:
                    process.deleteLater()
                except (RuntimeError, ValueError):
                    pass
            return
        if process is None:
            self._startNextNotificationFetch()
            return
        stdout = self._qprocess_text(process)
        stderr = self._qprocess_text(process, standard_error=True)
        try:
            code = int(process.exitCode())
        except (AttributeError, RuntimeError, TypeError, ValueError):
            code = 1
        try:
            process.deleteLater()
        except (RuntimeError, ValueError):
            pass
        try:
            if kind == "invite":
                items = parse_incoming_invitations_output(stdout, stderr, code)
            else:
                items = parse_share_request_search_output(stdout, stderr, code)
        except (GitHubAuthError, OSError, RuntimeError, ValueError):
            items = []
        results = getattr(self, "_notificationFetchResults", None)
        if results is None:
            results = []
            self._notificationFetchResults = results
        results.extend(items or [])
        self._startNextNotificationFetch()

    def _notificationKey(self, item: dict) -> str:
        kind = item.get("kind") or "review"
        if kind == "invite":
            return "invite#%s" % item.get("id")
        return "review#%s#%s" % (item.get("full_name") or "", item.get("number"))

    def _applyNotificationRequests(self, requests: list, announce: bool = False) -> None:
        previous_keys = {self._notificationKey(item) for item in getattr(self, "_notifications", [])}
        incoming = list(requests or [])
        if announce:
            for item in incoming:
                if self._notificationKey(item) in previous_keys:
                    continue
                project = item.get("full_name") or "a project"
                if item.get("kind") == "invite":
                    self._appendFeed("You were invited to %s." % project)
                else:
                    author = item.get("author") or "A colleague"
                    self._appendFeed("%s sent a version to review on %s." % (author, project))
        self._notifications = incoming
        self._updateNotificationsBadge()

    def _clearNotificationsDisplay(self) -> None:
        self._notifications = []
        self._updateNotificationsBadge()

    def _notificationsEmptyText(self) -> str:
        if not self._connected:
            return "Connect with GitHub to see notifications."
        return "No new notifications."

    def _updateNotificationsBadge(self) -> None:
        badge = getattr(self, "notificationsBadge", None)
        bell = getattr(self, "notificationsBell", None)
        count = len(getattr(self, "_notifications", []) or [])
        if badge is None:
            return
        if count <= 0:
            badge.hide()
            if bell is not None:
                bell.setToolTip("Notifications")
            return
        badge.setText("9+" if count > 9 else str(count))
        badge.show()
        badge.raise_()
        if bell is not None:
            if count == 1:
                bell.setToolTip("1 version to review")
            else:
                bell.setToolTip("%d versions to review" % count)

    def _setNotificationsEnabled(self, enabled: bool) -> None:
        bell = getattr(self, "notificationsBell", None)
        if bell is not None:
            bell.setEnabled(bool(enabled))
        if not enabled:
            self._updateNotificationsBadge()

    def _messagesPanelOpen(self) -> bool:
        button = getattr(self, "messagesButton", None)
        if button is None:
            return False
        try:
            checked = button.checked
            if callable(checked):
                checked = checked()
            return bool(checked)
        except (AttributeError, RuntimeError, TypeError, ValueError):
            return False

    def _onMessagesToggled(self, checked: bool) -> None:
        body = getattr(self, "messagesBody", None)
        if body is not None:
            body.setVisible(bool(checked))
        if checked:
            self._markMessagesRead()
            self._scrollMessagesToEnd()
        self._positionMessagesBadge()

    def _resetMessagesState(self, project: str) -> None:
        self._stopMessageSend()
        self._messages = []
        self._messages_read_ids = set()
        self._messages_baseline_ready = False
        self._messages_unread = 0
        self._messages_project = project or ""
        self._renderMessagesView()
        self._updateMessagesBadge()

    def _syncMessagesPolling(self) -> None:
        name = self._currentProjectName() if self._connected and self._hasSelectedProject() else ""
        changed = name != getattr(self, "_messages_project", "")
        if changed:
            self._resetMessagesState(name)
        self._setMessagesComposerEnabled(bool(name))
        if not name:
            self._stopMessagesPolling()
            self._renderMessagesView()
            self._updateMessagesBadge()
            return
        timer = getattr(self, "_messagesTimer", None)
        if changed or timer is None:
            self._startMessagesPolling()

    def _startMessagesPolling(self) -> None:
        self._stopMessagesPolling()
        parent = getattr(self, "messagesButton", None)
        if parent is None or not _qt_widget_is_valid(parent):
            parent = slicer.util.mainWindow()
        timer = qt.QTimer(parent)
        timer.setInterval(_MESSAGES_POLL_MS)
        timer.connect("timeout()", self._onMessagesPoll)
        self._messagesTimer = timer
        timer.start()
        self._runMessageChecks()

    def _stopMessagesPolling(self) -> None:
        timer = getattr(self, "_messagesTimer", None)
        self._messagesTimer = None
        if timer is not None:
            try:
                timer.stop()
                timer.deleteLater()
            except (RuntimeError, ValueError):
                pass
        self._stopMessagesFetch()

    def _stopMessagesFetch(self) -> None:
        process = getattr(self, "_messagesProcess", None)
        self._messagesProcess = None
        self._messagesFetchProject = ""
        self._refreshing_messages = False
        if process is None:
            return
        try:
            if int(process.state()) != 0:
                process.kill()
            process.deleteLater()
        except (AttributeError, RuntimeError, TypeError, ValueError):
            pass

    def _onMessagesPoll(self) -> None:
        self._runMessageChecks()

    def _qprocess_text(self, process, standard_error: bool = False) -> str:
        try:
            data = process.readAllStandardError() if standard_error else process.readAllStandardOutput()
        except (AttributeError, RuntimeError, TypeError):
            return ""
        try:
            return bytes(data).decode("utf-8", "replace")
        except (TypeError, ValueError, UnicodeDecodeError):
            try:
                return str(data.data(), "utf-8", "replace")
            except (AttributeError, TypeError, ValueError):
                return str(data or "")

    def _runMessageChecks(self) -> None:
        if getattr(self, "_sending_message", False):
            return
        process = getattr(self, "_messagesProcess", None)
        if process is not None:
            try:
                if int(process.state()) != 0:
                    return
            except (AttributeError, RuntimeError, TypeError, ValueError):
                return
        if not self._connected or not self._hasSelectedProject():
            return
        progress = getattr(self, "_progressDialog", None)
        if progress is not None and _qt_widget_is_valid(progress):
            return
        if getattr(self, "_offering_invitations", False):
            return
        if getattr(self, "_people_dialog_open", False):
            return
        if getattr(self, "_notifications_popup_open", False):
            return
        gh = find_gh()
        if not gh:
            return
        name = self._currentProjectName()
        parent = getattr(self, "messagesButton", None)
        if parent is None or not _qt_widget_is_valid(parent):
            parent = slicer.util.mainWindow()
        fetch = qt.QProcess(parent)
        try:
            env = qt.QProcessEnvironment.systemEnvironment()
            env.insert("GH_PAGER", "")
            env.insert("GIT_PAGER", "")
            env.insert("GH_PROMPT_DISABLED", "1")
            env.insert("GIT_TERMINAL_PROMPT", "0")
            fetch.setProcessEnvironment(env)
        except (AttributeError, TypeError, RuntimeError):
            pass
        fetch.connect("finished(int)", self._onMessagesFetchFinished)
        self._messagesProcess = fetch
        self._messagesFetchProject = name
        self._refreshing_messages = True
        fetch.start(gh, project_messages_fetch_args(name))

    def _onMessagesFetchFinished(self, _code=0) -> None:
        process = getattr(self, "_messagesProcess", None)
        expected = getattr(self, "_messagesFetchProject", "")
        self._messagesProcess = None
        self._messagesFetchProject = ""
        self._refreshing_messages = False
        if process is None:
            return
        stdout = self._qprocess_text(process)
        stderr = self._qprocess_text(process, standard_error=True)
        try:
            code = int(process.exitCode())
        except (AttributeError, RuntimeError, TypeError, ValueError):
            code = 1
        try:
            process.deleteLater()
        except (RuntimeError, ValueError):
            pass
        if expected != self._currentProjectName():
            return
        try:
            incoming, _sha = parse_project_messages_output(stdout, stderr, code)
        except (GitHubAuthError, OSError, RuntimeError, ValueError):
            return
        self._applyProjectMessages(incoming)

    def _applyProjectMessages(self, incoming: list) -> None:
        messages = list(incoming or [])
        me = (self._githubLogin() or "").lower()
        if not getattr(self, "_messages_baseline_ready", False):
            self._messages_read_ids = {item.get("id") for item in messages if item.get("id")}
            self._messages_baseline_ready = True
            self._messages_unread = 0
        else:
            read_ids = getattr(self, "_messages_read_ids", set())
            if self._messagesPanelOpen():
                for item in messages:
                    mid = item.get("id")
                    if mid:
                        read_ids.add(mid)
                self._messages_read_ids = read_ids
                self._messages_unread = 0
            else:
                unread = 0
                for item in messages:
                    mid = item.get("id")
                    author = str(item.get("author") or "").lower()
                    if not mid or mid in read_ids or author == me:
                        continue
                    unread += 1
                self._messages_unread = unread
        self._messages = self._mergePendingMessages(messages)
        self._renderMessagesView()
        self._updateMessagesBadge()

    def _markMessagesRead(self) -> None:
        self._messages_read_ids = {item.get("id") for item in getattr(self, "_messages", []) if item.get("id")}
        self._messages_unread = 0
        self._updateMessagesBadge()

    def _updateMessagesBadge(self) -> None:
        badge = getattr(self, "messagesBadge", None)
        button = getattr(self, "messagesButton", None)
        count = int(getattr(self, "_messages_unread", 0) or 0)
        if badge is None:
            return
        if count <= 0:
            badge.hide()
            if button is not None:
                button.setToolTip("Messages")
        else:
            badge.setText("9+" if count > 9 else str(count))
            badge.show()
            if button is not None:
                if count == 1:
                    button.setToolTip("1 new message")
                else:
                    button.setToolTip("%d new messages" % count)
        self._positionMessagesBadge()

    def _positionMessagesBadge(self) -> None:
        button = getattr(self, "messagesButton", None)
        badge = getattr(self, "messagesBadge", None)
        if button is None or badge is None or not _qt_widget_is_valid(button):
            return
        try:
            width = button.width
            if callable(width):
                width = width()
            badge.move(max(8, int(width) - 22), 3)
            badge.raise_()
        except (AttributeError, RuntimeError, TypeError, ValueError):
            pass

    def _messagesEmptyText(self) -> str:
        if not self._connected:
            return "Connect with GitHub to use messages."
        if not self._hasSelectedProject():
            return "Select a project to use messages."
        return "No messages yet."

    def _formatMessageTime(self, stamp: str) -> str:
        text = str(stamp or "").strip()
        if not text:
            return ""
        parsed = None
        try:
            normalized = text[:-1] + "+0000" if text.endswith("Z") else text
            parsed = datetime.strptime(normalized.replace("+00:00", "+0000"), "%Y-%m-%dT%H:%M:%S%z")
        except ValueError:
            try:
                parsed = datetime.strptime(text[:19], "%Y-%m-%dT%H:%M:%S")
            except ValueError:
                return ""
        if parsed.tzinfo is None:
            local = parsed
            now = datetime.now()
        else:
            local = parsed.astimezone()
            now = datetime.now().astimezone()
        time_part = local.strftime("%H:%M")
        if local.date() == now.date():
            return time_part
        month = _MESSAGE_MONTHS[local.month - 1]
        if local.year == now.year:
            return "%d %s %s" % (local.day, month, time_part)
        return "%d %s %d %s" % (local.day, month, local.year, time_part)

    def _formatMessageHtml(self, item: dict) -> str:
        raw_author = str(item.get("author") or "Someone")
        author = html.escape(raw_author)
        body = html.escape(str(item.get("text") or "")).replace("\n", "<br>")
        when = html.escape(self._formatMessageTime(item.get("at") or ""))
        mine = raw_author.lower() == (self._githubLogin() or "").lower()
        pending = bool(item.get("pending"))
        name_color = TEXT_MUTED if pending else (ACCENT_ICE if mine else TEXT_SECONDARY)
        time_html = (
            ' <span style="color:%s;font-size:10px;">%s</span>' % (TEXT_MUTED, when)
            if when
            else ""
        )
        return (
            '<p style="margin:0 0 8px 0;">'
            '<span style="color:%s;font-weight:600;">%s</span>%s<br>'
            "<span>%s</span></p>"
        ) % (name_color, author, time_html, body)

    def _messagesScrollBar(self):
        view = getattr(self, "messagesView", None)
        if view is None or not _qt_widget_is_valid(view):
            return None
        try:
            bar = view.verticalScrollBar
            if callable(bar):
                bar = bar()
            return bar
        except (AttributeError, RuntimeError, TypeError, ValueError):
            return None

    def _messagesViewAtBottom(self) -> bool:
        bar = self._messagesScrollBar()
        if bar is None:
            return True
        try:
            value = bar.value
            if callable(value):
                value = value()
            maximum = bar.maximum
            if callable(maximum):
                maximum = maximum()
            return int(maximum) - int(value) <= 12
        except (AttributeError, RuntimeError, TypeError, ValueError):
            return True

    def _restoreMessagesScroll(self, value) -> None:
        bar = self._messagesScrollBar()
        if bar is None:
            return
        try:
            bar.setValue(int(value))
        except (AttributeError, RuntimeError, TypeError, ValueError):
            pass

    def _renderMessagesView(self, force_bottom: bool = False) -> None:
        view = getattr(self, "messagesView", None)
        if view is None or not _qt_widget_is_valid(view):
            return
        stay_at_bottom = bool(force_bottom) or self._messagesViewAtBottom()
        saved = 0
        if not stay_at_bottom:
            bar = self._messagesScrollBar()
            try:
                saved = bar.value
                if callable(saved):
                    saved = saved()
            except (AttributeError, RuntimeError, TypeError, ValueError):
                saved = 0
        messages = getattr(self, "_messages", []) or []
        if not messages:
            markup = '<span style="color:%s">%s</span>' % (
                TEXT_MUTED,
                html.escape(self._messagesEmptyText()),
            )
        else:
            markup = "".join(self._formatMessageHtml(item) for item in messages)
        try:
            view.setHtml(markup)
        except (RuntimeError, TypeError, ValueError):
            return
        if stay_at_bottom:
            self._scrollMessagesToEnd()
            return
        self._messagesScrollRestore = saved
        qt.QTimer.singleShot(0, self._applyMessagesScrollRestore)

    def _applyMessagesScrollRestore(self) -> None:
        value = getattr(self, "_messagesScrollRestore", None)
        self._messagesScrollRestore = None
        if value is None:
            return
        self._restoreMessagesScroll(value)

    def _scrollMessagesToEnd(self) -> None:
        view = getattr(self, "messagesView", None)
        if view is None or not _qt_widget_is_valid(view):
            return
        try:
            view.moveCursor(qt.QTextCursor.End)
            view.ensureCursorVisible()
        except (AttributeError, RuntimeError, TypeError, ValueError):
            pass

    def _mergePendingMessages(self, incoming: list) -> list:
        merged = list(incoming or [])
        seen = {item.get("id") for item in merged if item.get("id")}
        for item in getattr(self, "_messages", []) or []:
            if not item.get("pending"):
                continue
            mid = item.get("id")
            if mid and mid not in seen:
                merged.append(item)
        return merged

    def _stopMessageSendProcess(self) -> None:
        process = getattr(self, "_messageSendProcess", None)
        self._messageSendProcess = None
        if process is None:
            return
        try:
            if int(process.state()) != 0:
                process.kill()
            process.deleteLater()
        except (AttributeError, RuntimeError, TypeError, ValueError):
            pass

    def _stopMessageSend(self) -> None:
        self._sending_message = False
        self._messageSendQueue = []
        self._messageSendCurrent = None
        self._messageSendPhase = ""
        self._messageSendProject = ""
        self._messageSendAttempt = 0
        self._messageSendExisting = []
        self._stopMessageSendProcess()

    def _storedMessage(self, message: dict) -> dict:
        return {
            "id": str(message.get("id") or ""),
            "author": str(message.get("author") or "Someone"),
            "text": str(message.get("text") or ""),
            "at": str(message.get("at") or ""),
        }

    def _startNextQueuedSend(self) -> None:
        if getattr(self, "_sending_message", False):
            return
        queue = list(getattr(self, "_messageSendQueue", []) or [])
        if not queue:
            return
        message = queue.pop(0)
        self._messageSendQueue = queue
        self._messageSendCurrent = message
        self._messageSendProject = self._currentProjectName()
        self._messageSendAttempt = 0
        self._messageSendExisting = []
        self._sending_message = True
        self._startMessageSendGet()

    def _startMessageSendGet(self) -> None:
        project = getattr(self, "_messageSendProject", "") or ""
        if not project:
            self._failPendingMessage(
                getattr(self, "_messageSendCurrent", None) or {},
                "Could not send the message.",
            )
            return
        self._messageSendPhase = "get"
        self._startMessageSendProcess(project_messages_fetch_args(project))

    def _startMessageSendProcess(self, args: list) -> None:
        self._stopMessageSendProcess()
        gh = find_gh()
        if not gh:
            self._failPendingMessage(
                getattr(self, "_messageSendCurrent", None) or {},
                "Could not send the message.",
            )
            return
        parent = getattr(self, "messagesButton", None)
        if parent is None or not _qt_widget_is_valid(parent):
            parent = slicer.util.mainWindow()
        fetch = qt.QProcess(parent)
        try:
            env = qt.QProcessEnvironment.systemEnvironment()
            env.insert("GH_PAGER", "")
            env.insert("GIT_PAGER", "")
            env.insert("GH_PROMPT_DISABLED", "1")
            env.insert("GIT_TERMINAL_PROMPT", "0")
            fetch.setProcessEnvironment(env)
        except (AttributeError, TypeError, RuntimeError):
            pass
        fetch.connect("finished(int)", self._onMessageSendFinished)
        self._messageSendProcess = fetch
        fetch.start(gh, args)

    def _onMessageSendFinished(self, _code=0) -> None:
        process = getattr(self, "_messageSendProcess", None)
        self._messageSendProcess = None
        if not getattr(self, "_sending_message", False):
            if process is not None:
                try:
                    process.deleteLater()
                except (RuntimeError, ValueError):
                    pass
            return
        current = getattr(self, "_messageSendCurrent", None) or {}
        project = getattr(self, "_messageSendProject", "") or ""
        phase = getattr(self, "_messageSendPhase", "")
        stdout = self._qprocess_text(process) if process is not None else ""
        stderr = self._qprocess_text(process, standard_error=True) if process is not None else ""
        try:
            code = int(process.exitCode()) if process is not None else 1
        except (AttributeError, RuntimeError, TypeError, ValueError):
            code = 1
        if process is not None:
            try:
                process.deleteLater()
            except (RuntimeError, ValueError):
                pass
        if project != self._currentProjectName():
            self._failPendingMessage(current, "Could not send the message.")
            return
        if phase == "get":
            try:
                existing, sha = parse_project_messages_output(stdout, stderr, code)
            except (GitHubAuthError, OSError, RuntimeError, ValueError) as error:
                self._failPendingMessage(current, str(error))
                return
            if any(item.get("id") == current.get("id") for item in existing):
                self._confirmPendingMessage(current, existing)
                return
            self._messageSendExisting = existing
            self._messageSendPhase = "put"
            payload = list(existing) + [self._storedMessage(current)]
            self._startMessageSendProcess(project_messages_put_args(project, payload, sha))
            return
        if code == 0:
            existing = list(getattr(self, "_messageSendExisting", []) or [])
            stored = self._storedMessage(current)
            if not any(item.get("id") == stored.get("id") for item in existing):
                existing.append(stored)
            self._confirmPendingMessage(current, existing)
            return
        if is_project_messages_conflict(stdout, stderr):
            attempt = int(getattr(self, "_messageSendAttempt", 0) or 0) + 1
            self._messageSendAttempt = attempt
            if attempt >= 4:
                self._failPendingMessage(current, "Could not send the message. Try again.")
                return
            self._startMessageSendGet()
            return
        self._failPendingMessage(current, "Could not send the message.")

    def _confirmPendingMessage(self, message: dict, existing: list) -> None:
        self._sending_message = False
        self._messageSendCurrent = None
        self._messageSendPhase = ""
        self._applyProjectMessages(existing)
        self._startNextQueuedSend()

    def _failPendingMessage(self, message: dict, error_text: str) -> None:
        mid = (message or {}).get("id")
        if mid:
            self._messages = [
                item for item in (getattr(self, "_messages", []) or []) if item.get("id") != mid
            ]
            self._renderMessagesView()
        text = str((message or {}).get("text") or "")
        if text and _qt_widget_is_valid(getattr(self, "messagesInput", None)):
            if not _qt_line_text(self.messagesInput):
                self.messagesInput.setText(text)
        self._appendFeed(str(error_text or "Could not send the message.").split("\n")[0], error=True)
        self._sending_message = False
        self._messageSendCurrent = None
        self._messageSendPhase = ""
        self._startNextQueuedSend()

    def _onSendMessage(self) -> None:
        if not self._connected or not self._hasSelectedProject():
            return
        text = _qt_line_text(self.messagesInput)
        if not text:
            return
        try:
            message = build_project_message(self._githubLogin(), text)
        except (GitHubAuthError, OSError, RuntimeError, ValueError) as error:
            self._appendFeed(str(error).split("\n")[0], error=True)
            return
        self.messagesInput.setText("")
        message["pending"] = True
        current = list(getattr(self, "_messages", []) or [])
        current.append(message)
        self._messages = current
        self._messages_baseline_ready = True
        read_ids = getattr(self, "_messages_read_ids", set())
        if message.get("id"):
            read_ids.add(message.get("id"))
        self._messages_read_ids = read_ids
        self._renderMessagesView(force_bottom=True)
        queue = list(getattr(self, "_messageSendQueue", []) or [])
        queue.append(message)
        self._messageSendQueue = queue
        if not getattr(self, "_sending_message", False):
            self._startNextQueuedSend()

    def _onNotificationsBellClicked(self) -> None:
        try:
            self._showNotificationsPopup()
        except Exception as error:
            logging.exception("Notifications popup failed")
            self._appendFeed(str(error).split("\n")[0], error=True)

    def _showNotificationsPopup(self) -> None:
        items = list(getattr(self, "_notifications", []) or [])
        dialog = NotificationsDialog(
            slicer.util.mainWindow(),
            items=items,
            empty_text=self._notificationsEmptyText(),
        )
        self._notifications_popup_open = True
        try:
            dialog.exec_()
        finally:
            self._notifications_popup_open = False
        chosen = getattr(dialog, "chosen", None)
        if not chosen:
            return
        if chosen.get("kind") == "invite":
            self._openInvitationNotification(chosen)
        else:
            self._reviewShareRequest(chosen)

    def _openInvitationNotification(self, invitation: dict) -> None:
        self._offering_invitations = True
        try:
            choice = self._promptJoinProject(invitation)
            if choice == "join":
                self._joinIncomingInvitation(invitation)
            elif choice == "decline":
                self._declineIncomingInvitation(invitation)
        finally:
            self._offering_invitations = False
            if self._connected:
                self._runNotificationChecks(announce=False)

    def _reviewShareRequest(self, request: dict) -> None:
        full_name = request.get("full_name") or ""
        author = request.get("author") or "a colleague"
        branch = request.get("branch") or ""
        number = request.get("number")
        self._openProgress("Review version", "Opening the version from %s…" % author)
        snapshot = None
        try:
            self._updateProgress("Opening the version from %s…" % author)
            local_path, sha = fetch_share_request_sha(full_name, branch)
            snapshot = extract_project_version(local_path, sha)
            self._updateProgress("Loading segmentation and ontology…")
            loaded = self._loadOpenedProjectAssets(snapshot, volume_folder=local_path)
            self._updateProgress("Reading version history…")
            history = read_project_history(local_path)
        except (GitHubAuthError, OSError, RuntimeError, ValueError) as error:
            self._closeProgress()
            self._deferRemoveSnapshot(snapshot)
            self._appendFeed(str(error).split("\n")[0], error=True)
            return
        unshared = self._historyHasUnsharedVersion(history)
        self._suppress_dirty += 1
        self._suppress_asset_ui_updates += 1
        try:
            self._selectProjectName(full_name)
            self._loaded_project_name = full_name
            self._local_project_path = local_path
            self._server_pulled = True
            self._applyProjectHistoryBundle(history)
            self._clearChangeFlags()
            self._unshared_version = unshared
            self._syncAssetDataObservers()
            self._rememberPeopleAccess(full_name, "share")
        finally:
            self._suppress_asset_ui_updates -= 1
            self._suppress_dirty -= 1
        self._closeProgress()
        self._refreshUiState()
        self._clearChangeFlags()
        self._unshared_version = unshared
        self._updateVersionActionButtons()
        self._armLoadSettle()
        self._appendFeed("Reviewing a version from %s. It is not on the project yet." % author)
        if loaded.get("volume"):
            self._appendFeed("Volume loaded: %s" % loaded["volume"])
        if loaded.get("segmentation"):
            self._appendFeed("Segmentation loaded: %s" % loaded["segmentation"])
        if loaded.get("ontology"):
            self._appendFeed("Ontology loaded: %s" % loaded["ontology"])
        decision = self._promptAcceptShareRequest(author)
        if decision == "accept":
            self._acceptReviewedShareRequest(request)
        elif decision == "decline":
            self._declineReviewedShareRequest(request)
        self._deferRemoveSnapshot(snapshot)

    def _promptAcceptShareRequest(self, author: str) -> str:
        box = qt.QMessageBox(slicer.util.mainWindow())
        box.setWindowTitle("Review version")
        box.setText("This is the version %s wants to share." % author)
        box.setInformativeText("Accept adds it to the project. Decline discards it.")
        accept_btn = box.addButton("Accept", qt.QMessageBox.AcceptRole)
        decline_btn = box.addButton("Decline", qt.QMessageBox.DestructiveRole)
        box.addButton("Later", qt.QMessageBox.RejectRole)
        box.setDefaultButton(accept_btn)
        box.exec_()
        clicked = box.clickedButton()
        if clicked == accept_btn:
            return "accept"
        if clicked == decline_btn:
            return "decline"
        return "later"

    def _selectProjectName(self, full_name: str) -> None:
        combo = getattr(self, "projectCombo", None)
        if combo is None:
            return
        index = combo.findText(full_name)
        if index < 0:
            return
        combo.blockSignals(True)
        combo.setCurrentIndex(index)
        combo.blockSignals(False)

    def _acceptReviewedShareRequest(self, request: dict) -> None:
        full_name = request.get("full_name") or ""
        author = request.get("author") or "the colleague"
        self._openProgress("Review version", "Adding the version to the project…")
        try:
            self._updateProgress("Adding the version to the project…")
            local_path = accept_share_request(full_name, request.get("branch") or "", request.get("number"))
            self._updateProgress("Updating version history…")
            history = read_project_history(local_path)
        except (GitHubAuthError, OSError, RuntimeError, ValueError) as error:
            self._closeProgress()
            self._appendFeed(str(error).split("\n")[0], error=True)
            return
        self._closeProgress()
        unshared = self._historyHasUnsharedVersion(history)
        self._suppress_dirty += 1
        self._suppress_asset_ui_updates += 1
        try:
            self._loaded_project_name = full_name
            self._local_project_path = local_path
            self._server_pulled = True
            self._applyProjectHistoryBundle(history)
            self._clearChangeFlags()
            self._unshared_version = unshared
            self._syncAssetDataObservers()
        finally:
            self._suppress_asset_ui_updates -= 1
            self._suppress_dirty -= 1
        self._refreshUiState()
        self._clearChangeFlags()
        self._unshared_version = unshared
        self._updateVersionActionButtons()
        self._armLoadSettle()
        self._appendFeed("Accepted the version from %s. It is now on the project." % author)
        self._runNotificationChecks(announce=False)

    def _declineReviewedShareRequest(self, request: dict) -> None:
        author = request.get("author") or "the colleague"
        self._openProgress("Review version", "Declining the version…")
        try:
            self._updateProgress("Declining the version…")
            decline_share_request(
                request.get("full_name") or "",
                request.get("number"),
                branch=request.get("branch") or "",
            )
            local_path = getattr(self, "_local_project_path", None) or ""
            if (
                local_path
                and (request.get("full_name") or "") == (self._currentProjectName() or "")
            ):
                self._updateProgress("Updating version history…")
                history = read_project_history(local_path)
                previous_unshared = self._unshared_version
                self._applyProjectHistoryBundle(history)
                self._unshared_version = previous_unshared or self._historyHasUnsharedVersion(history)
        except (GitHubAuthError, OSError, RuntimeError, ValueError) as error:
            self._closeProgress()
            self._appendFeed(str(error).split("\n")[0], error=True)
            return
        self._closeProgress()
        self._appendFeed(
            "Declined the version from %s. Their versions stay in the version tree." % author
        )
        self._refreshUiState()
        self._runNotificationChecks(announce=False)

    def onDeleteProject(self) -> None:
        if not self._canDeleteProject():
            reason = self._deleteDisabledReason()
            if reason:
                self._appendFeed(reason, error=True)
            return
        full_name = self._currentProjectName()
        confirmed = slicer.util.confirmYesNoDisplay(
            "Delete project %s?\n\n"
            "This cannot be undone. The GitHub repository and the local folder "
            "will be removed." % full_name,
            windowTitle="Delete project",
        )
        if not confirmed:
            return
        if has_delete_repo_scope() is False:
            if not self._authorizeDeletePermission():
                return
        self.deleteButton.setEnabled(False)
        self._appendFeed("Deleting project %s…" % full_name)
        self._openProgress("Delete project", "Deleting %s…" % full_name)
        try:
            self._updateProgress("Deleting the GitHub project…")
            delete_owned_repository(full_name)
        except GitHubMissingDeletePermissionError:
            self._closeProgress()
            if not self._authorizeDeletePermission():
                self._updateVersionActionButtons()
                return
            self._openProgress("Delete project", "Deleting %s…" % full_name)
            try:
                self._updateProgress("Deleting the GitHub project…")
                delete_owned_repository(full_name)
            except GitHubAuthError as error:
                self._closeProgress()
                self._updateVersionActionButtons()
                slicer.util.warningDisplay(str(error))
                self._appendFeed(str(error).split("\n")[0], error=True)
                return
        except GitHubAuthError as error:
            self._closeProgress()
            self._updateVersionActionButtons()
            slicer.util.warningDisplay(str(error))
            self._appendFeed(str(error).split("\n")[0], error=True)
            return
        repos = list((self._github_session or {}).get("repos") or [])
        if self._github_session is not None:
            self._github_session["repos"] = [
                item for item in repos if item.get("full_name") != full_name
            ]
        self._currentVersionId = None
        self._server_pulled = False
        self._loaded_project_name = None
        self._local_project_path = None
        self._clearChangeFlags()
        try:
            self.removeObservers(self._onAssetDataModified)
        except Exception:
            pass
        self._closeProgress()
        self._populateProjectCombo()
        self._clearProjectSelection()
        self._clearProjectAssetFields()
        self._refreshUiState()
        self._appendFeed("Project deleted: %s" % full_name)

    def _authorizeDeletePermission(self) -> bool:
        try:
            open_delete_permission_window()
        except GitHubAuthError as error:
            slicer.util.warningDisplay(str(error))
            self._appendFeed(str(error).split("\n")[0], error=True)
            self._updateVersionActionButtons()
            return False
        self._appendFeed("GitHub permission window opened.")
        box = qt.QMessageBox(slicer.util.mainWindow())
        box.setWindowTitle("GitHub permission")
        box.setText(
            "GitHub needs an extra permission to delete a project.\n\n"
            "A window opened. Complete these steps there:\n\n"
            "1. Choose Yes if asked to authenticate Git with your GitHub credentials.\n"
            "2. A one-time code is shown in that window (it is also copied to the clipboard).\n"
            "3. Press Enter to open the browser.\n"
            "4. In the browser, authorize the extra permission.\n\n"
            "When that is done, click I have authorized."
        )
        box.setStandardButtons(qt.QMessageBox.Ok | qt.QMessageBox.Cancel)
        box.button(qt.QMessageBox.Ok).setText("I have authorized")
        box.setDefaultButton(qt.QMessageBox.Ok)
        if box.exec_() != qt.QMessageBox.Ok:
            self._appendFeed("Delete cancelled — extra GitHub permission was not granted.")
            self._updateVersionActionButtons()
            return False
        slicer.app.processEvents()
        if has_delete_repo_scope() is False:
            slicer.util.warningDisplay(
                "GitHub did not grant the extra permission.\n\n"
                "Click Delete to try again."
            )
            self._appendFeed("GitHub did not grant the extra delete permission.", error=True)
            self._updateVersionActionButtons()
            return False
        return True

    def onSaveVersion(self) -> None:
        if not self._connected:
            self._appendFeed("Connect with GitHub first.", error=True)
            return
        if not self._canSaveVersion():
            reason = self._saveVersionDisabledReason()
            if reason:
                self._appendFeed(reason, error=True)
            return
        local_path = getattr(self, "_local_project_path", None) or ""
        if not local_path or not os.path.isdir(os.path.join(local_path, ".git")):
            self._appendFeed("Open the project first.", error=True)
            return
        write_volume, write_segmentation, write_ontology = self._dirtyAssetsToWrite()
        if not (write_volume or write_segmentation or write_ontology):
            self._appendFeed("No changes to save.", error=True)
            return
        volume_node = self.volumeSelector.currentNode() if self.volumeSelector else None
        segmentation_node = (
            self.segmentationSelector.currentNode() if self.segmentationSelector else None
        )
        if write_segmentation and volume_node is None:
            self._appendFeed("Save needs a 3D volume.", error=True)
            return
        if write_segmentation and segmentation_node is None:
            self._appendFeed("Save needs a segmentation.", error=True)
            return
        if write_segmentation:
            name_error = self._segmentationOntologyNameError(segmentation_node)
            if name_error:
                self._appendFeed(name_error, error=True)
                return
        if write_ontology:
            self._ensureOntologyFromCombo()
            if not self._ontology_document:
                self._appendFeed("Fill project data first: Ontology map.", error=True)
                return
        default_message = "First version" if not self._currentVersionId else "New version"
        message = self._promptCommitMessage(
            "Save version",
            "Version message:",
            default_message,
        )
        if message is None:
            return
        if write_segmentation and not write_volume and not write_ontology:
            progress_label = "Saving the segmentation…"
        elif write_volume and not write_segmentation and not write_ontology:
            progress_label = "Saving the 3D volume…"
        elif write_ontology and not write_volume and not write_segmentation:
            progress_label = "Saving the ontology map…"
        else:
            progress_label = "Saving project files…"
        self.saveVersionButton.setEnabled(False)
        self._appendFeed("Saving version…")
        self._openProgress("Save version", progress_label)
        version_id = None
        self._suppress_dirty += 1
        try:
            self._updateProgress(progress_label)
            self._writeProjectFiles(
                local_path,
                volume_node,
                segmentation_node,
                self._savedProjectFileStem(local_path),
                write_volume=write_volume,
                write_segmentation=write_segmentation,
                write_ontology=write_ontology,
            )
            self._updateProgress("Saving the version…")
            commit_local_version(local_path, message)
            self._updateProgress("Updating version history…")
            history = read_project_history(local_path)
            version_id = self._applyProjectHistoryBundle(history)
            self._clearDirtyAssets()
            self._unshared_version = True
            self._syncAssetDataObservers()
            self._closeProgress()
            self._refreshUiState()
        except (GitHubAuthError, OSError, RuntimeError, ValueError) as error:
            self._closeProgress()
            self._updateVersionActionButtons()
            slicer.util.warningDisplay(str(error))
            self._appendFeed(str(error).split("\n")[0], error=True)
            return
        finally:
            self._suppress_dirty -= 1
        self._clearDirtyAssets()
        self._unshared_version = True
        self._updateVersionActionButtons()
        self._armLoadSettle()
        if version_id:
            self._appendFeed("Version saved: %s — %s" % (version_id, message))
        else:
            self._appendFeed("Version saved: %s" % message)

    def onShare(self) -> None:
        if not self._connected:
            self._appendFeed("Connect with GitHub first.", error=True)
            return
        if not self._canShare():
            reason = self._shareDisabledReason()
            if reason:
                self._appendFeed(reason, error=True)
            return
        local_path = getattr(self, "_local_project_path", None) or ""
        if not local_path or not os.path.isdir(os.path.join(local_path, ".git")):
            self._appendFeed("Open the project first.", error=True)
            return
        full_name = self._currentProjectName()
        needs_approval = False
        try:
            needs_approval = (
                not self._isCurrentProjectOwner()
                and self._rememberPeopleAccess(full_name) == PEOPLE_ACCESS_APPROVAL
            )
        except (GitHubAuthError, OSError, RuntimeError, ValueError):
            needs_approval = self._shareNeedsApproval()
        self.shareButton.setEnabled(False)
        if needs_approval:
            self._shareForReview(local_path, full_name)
        else:
            self._shareToProject(local_path)

    def _shareToProject(self, local_path: str) -> None:
        self._appendFeed("Sharing project…")
        self._openProgress("Share", "Sharing the project…")
        history = {}
        try:
            self._updateProgress("Sharing the project…")
            share_local_versions(local_path)
            self._updateProgress("Updating version history…")
            history = read_project_history(local_path)
        except (GitHubAuthError, OSError, RuntimeError, ValueError) as error:
            self._closeProgress()
            self._updateVersionActionButtons()
            slicer.util.warningDisplay(str(error))
            self._appendFeed(str(error).split("\n")[0], error=True)
            return
        unshared = self._historyHasUnsharedVersion(history)
        self._applyProjectHistoryBundle(history)
        self._unshared_version = unshared
        self._closeProgress()
        self._refreshUiState()
        self._unshared_version = unshared
        self._updateVersionActionButtons()
        self._appendFeed("Project shared.")
        if self._unsaved_changes:
            self._appendFeed(
                "Unsaved changes are still on this computer. Save a version if you want them shared later."
            )

    def _shareForReview(self, local_path: str, full_name: str) -> None:
        self._appendFeed("Sending the version to the owner…")
        self._openProgress("Share", "Sending the version to the owner…")
        try:
            self._updateProgress("Sending the version to the owner…")
            outcome = submit_share_request(local_path, full_name)
        except (GitHubAuthError, OSError, RuntimeError, ValueError) as error:
            self._closeProgress()
            self._updateVersionActionButtons()
            slicer.util.warningDisplay(str(error))
            self._appendFeed(str(error).split("\n")[0], error=True)
            return
        self._closeProgress()
        self._updateVersionActionButtons()
        if outcome == "updated":
            self._appendFeed("Updated the review request. The owner can open it after they Connect.")
        else:
            self._appendFeed("Sent to the owner for review. It is not on the project yet.")

    def onOpenProject(self) -> None:
        if not self._canOpenProject():
            reason = self._openDisabledReason()
            if reason:
                self._appendFeed(reason, error=True)
            return
        full_name = self._currentProjectName()
        choice = self._promptOpenUnsharedChoice(full_name)
        if choice == "cancel":
            self._appendFeed("Open cancelled.")
            self._updateVersionActionButtons()
            return
        self.openButton.setEnabled(False)
        self._appendFeed("Opening project %s…" % full_name)
        if choice == "local":
            progress_label = "Opening this computer's work…"
        elif choice == "replace":
            progress_label = "Getting the shared project…"
        else:
            progress_label = "Opening %s…" % full_name
        self._openProgress("Open project", progress_label)
        try:
            self._updateProgress(progress_label)
            local_path = open_or_update_local_project(full_name, mode=choice)
            loaded = self._loadOpenedProjectAssets(local_path)
            self._updateProgress("Reading version history…")
            history = read_project_history(local_path)
        except (GitHubAuthError, OSError, RuntimeError, ValueError) as error:
            self._closeProgress()
            self._updateVersionActionButtons()
            slicer.util.warningDisplay(str(error))
            self._appendFeed(str(error).split("\n")[0], error=True)
            return
        unshared = self._historyHasUnsharedVersion(history)
        self._suppress_dirty += 1
        self._suppress_asset_ui_updates += 1
        try:
            self._loaded_project_name = full_name
            self._local_project_path = local_path
            self._server_pulled = True
            self._applyProjectHistoryBundle(history)
            self._clearChangeFlags()
            self._unshared_version = unshared
            self._syncAssetDataObservers()
            try:
                self._rememberPeopleAccess(full_name)
            except (GitHubAuthError, OSError, RuntimeError, ValueError):
                pass
        finally:
            self._suppress_asset_ui_updates -= 1
            self._suppress_dirty -= 1
        self._closeProgress()
        self._refreshUiState()
        self._clearChangeFlags()
        self._unshared_version = unshared
        self._updateVersionActionButtons()
        self._armLoadSettle()
        self._appendFeed("Project opened: %s" % full_name)
        if choice == "local":
            self._appendFeed("Opened this computer's work — some versions are not shared yet.")
        elif choice == "replace":
            self._appendFeed("Opened the shared project. Unshared versions from this computer were discarded.")
        if loaded.get("volume"):
            self._appendFeed("Volume loaded: %s" % loaded["volume"])
        if loaded.get("segmentation"):
            self._appendFeed("Segmentation loaded: %s" % loaded["segmentation"])
        if loaded.get("ontology"):
            self._appendFeed("Ontology loaded: %s" % loaded["ontology"])
        if local_path:
            self._appendFeed("Local folder: %s" % local_path)
        count = len(history.get("commit_history") or [])
        if count:
            self._appendFeed("%d version(s) in history." % count)

    def _reusableVolumeNode(self, volume_path: str | None):
        current = self._selectorCurrentNode("volumeSelector")
        if current is None:
            return None
        if not volume_path:
            return current
        expected = DataManager()._basename_without_extension(volume_path)
        try:
            name = current.GetName()
        except (RuntimeError, ValueError, AttributeError):
            return None
        if name == expected:
            return current
        return None

    def _loadOpenedProjectAssets(self, folder: str, volume_folder: str | None = None) -> dict[str, str]:
        manager = DataManager()
        from_snapshot = volume_folder is not None
        files = manager.discover_project_files(folder)
        volume_path = files.get("volume")
        if not volume_path and volume_folder:
            volume_path = manager.discover_project_files(volume_folder).get("volume")
        volume_node = self._reusableVolumeNode(volume_path)
        if volume_node is None and not volume_path:
            raise RuntimeError("This project has no 3D volume to open.")
        load_volume = volume_node is None
        has_segmentation = bool(files.get("segmentation"))
        steps = (1 if load_volume else 0) + (1 if has_segmentation else 0) + 1
        if load_volume:
            self._setProgressStep(1, steps, "Loading 3D volume…")
        elif has_segmentation:
            self._setProgressStep(1, steps, "Loading segmentation…")
        else:
            self._setProgressStep(1, steps, "Loading ontology map…")
        ontology_path, ontology_document = self._firstValidOntology(files.get("ontologies") or [])
        if ontology_document is None:
            raise RuntimeError("This project has no ontology map to open.")
        step = 0
        names_to_replace = set()
        current_seg = self._selectorCurrentNode("segmentationSelector")
        can_inject = bool(
            from_snapshot
            and files.get("segmentation")
            and current_seg is not None
            and hasattr(current_seg, "IsA")
            and current_seg.IsA("vtkMRMLSegmentationNode")
        )
        if load_volume:
            names_to_replace.add(manager._basename_without_extension(volume_path))
        if files.get("segmentation") and not can_inject:
            names_to_replace.add(manager._basename_without_extension(files["segmentation"]))
        manager.remove_scene_nodes_by_names(names_to_replace)
        before_ids = self._sceneDataNodeIds()
        if load_volume:
            step += 1
            self._setProgressStep(step, steps, "Loading 3D volume…")
            volume_node = manager.load_volume(volume_path, isolate=False)
        keep_ids = set()
        if volume_node is not None:
            keep_ids.add(volume_node.GetID())
        segmentation_node = None
        segmentation_path = files.get("segmentation")
        if segmentation_path:
            step += 1
            self._setProgressStep(step, steps, "Loading segmentation…")
            self._suppress_dirty += 1
            self._suppress_asset_ui_updates += 1
            try:
                if can_inject and manager.inject_segmentation_from_file(
                    current_seg,
                    segmentation_path,
                    isolate=False,
                ):
                    segmentation_node = current_seg
                else:
                    if can_inject:
                        names_to_replace = {
                            manager._basename_without_extension(segmentation_path)
                        }
                        manager.remove_scene_nodes_by_names(names_to_replace)
                    segmentation_node = manager.load_segmentation(
                        segmentation_path,
                        isolate=not from_snapshot,
                    )
            finally:
                self._suppress_asset_ui_updates -= 1
                self._suppress_dirty -= 1
            if segmentation_node is not None:
                keep_ids.add(segmentation_node.GetID())
        step += 1
        self._setProgressStep(step, steps, "Loading ontology map…")
        self._pauseProgressPulse()
        self._removeUnexpectedLoadedNodes(before_ids, keep_ids)
        self._blockProjectAssetSignals(True)
        self._suppress_dirty += 1
        self._suppress_asset_ui_updates += 1
        try:
            self.volumeSelector.setCurrentNode(volume_node)
            self.segmentationSelector.setCurrentNode(segmentation_node)
            self._applyOntologyDocument(ontology_document)
            self._setOntologyComboLoadedFilename(document=ontology_document, filename=ontology_path)
            self._blockProjectAssetSignals(False)
        finally:
            self._blockProjectAssetSignals(False)
            self._suppress_asset_ui_updates -= 1
            self._suppress_dirty -= 1
        try:
            if not (from_snapshot and not load_volume and segmentation_node is current_seg):
                manager.present_in_slice_views(volume_node, segmentation_node)
        except Exception:
            logging.exception("Could not show the opened project in the slice views")
        loaded = {
            "volume": volume_node.GetName() if volume_node else "",
            "ontology": ontology_document.get("name") or os.path.basename(ontology_path),
        }
        if segmentation_node is not None:
            loaded["segmentation"] = segmentation_node.GetName()
        return loaded

    def _sceneDataNodeIds(self) -> set[str]:
        ids = set()
        scene = slicer.mrmlScene
        for class_name in (
            "vtkMRMLScalarVolumeNode",
            "vtkMRMLLabelMapVolumeNode",
            "vtkMRMLSegmentationNode",
        ):
            for index in range(scene.GetNumberOfNodesByClass(class_name)):
                node = scene.GetNthNodeByClass(index, class_name)
                if node is not None:
                    ids.add(node.GetID())
        return ids

    def _removeUnexpectedLoadedNodes(self, before_ids: set[str], keep_ids: set[str]) -> None:
        scene = slicer.mrmlScene
        for class_name in (
            "vtkMRMLScalarVolumeNode",
            "vtkMRMLLabelMapVolumeNode",
            "vtkMRMLSegmentationNode",
        ):
            for index in range(scene.GetNumberOfNodesByClass(class_name) - 1, -1, -1):
                node = scene.GetNthNodeByClass(index, class_name)
                if node is None:
                    continue
                node_id = node.GetID()
                if node_id in keep_ids or node_id in before_ids:
                    continue
                scene.RemoveNode(node)

    def _firstValidOntology(self, paths: list[str]):
        for path in paths:
            try:
                return path, load_ontology_file(path)
            except (OSError, ValueError):
                continue
        return None, None

    def onHistorySelectionChanged(self) -> None:
        if getattr(self, "_suppress_history_selection_signal", False):
            return
        selected_version_id = self._selectedVersionId()
        if not selected_version_id:
            return
        if selected_version_id == self._currentVersionId:
            return
        if not self._checkoutVersion(selected_version_id, notify=True, sync_table=False):
            self._selectHistoryRowForVersion(self._currentVersionId)

    def _checkoutVersion(
        self,
        version_id: str,
        notify: bool = False,
        sync_table: bool = True,
    ) -> bool:
        if not version_id:
            return False
        if version_id == self._currentVersionId:
            if sync_table:
                self._selectHistoryRowForVersion(version_id)
            self._updateActiveVersionIndicators()
            return True
        if not self._projectDataIsLoaded():
            self._appendFeed("Open the project first.", error=True)
            return False
        if not self._promptSwitchVersion(version_id):
            self._appendFeed("Switch version cancelled.")
            return False
        sha = ((getattr(self, "_project_history_bundle", None) or {}).get("sha_by_id") or {}).get(
            version_id
        )
        local_path = getattr(self, "_local_project_path", None) or ""
        if not sha or not local_path:
            self._appendFeed(
                "Could not switch to %s." % self._versionDisplayTag(version_id),
                error=True,
            )
            return False
        display = self._versionDisplayTag(version_id)
        previous_id = self._currentVersionId
        snapshot = None
        self._suppress_history_selection_signal = True
        try:
            self._currentVersionId = version_id
            self._updateActiveVersionIndicators()
            self._selectHistoryRowForVersion(version_id)
            self._openProgress("Switch version", "Loading %s…" % display)
            try:
                snapshot = extract_project_version(local_path, sha)
                self._loadOpenedProjectAssets(snapshot, volume_folder=local_path)
                clone_files = DataManager().discover_project_files(local_path)
                clone_ontologies = clone_files.get("ontologies") or []
                if clone_ontologies:
                    self._suppress_dirty += 1
                    try:
                        self._setOntologyComboLoadedFilename(filename=clone_ontologies[0])
                    finally:
                        self._suppress_dirty -= 1
                self._syncAssetDataObservers()
                self._clearDirtyAssets()
            except (GitHubAuthError, OSError, RuntimeError, ValueError) as error:
                self._currentVersionId = previous_id
                self._updateActiveVersionIndicators()
                if previous_id:
                    self._selectHistoryRowForVersion(previous_id)
                try:
                    self._loadOpenedProjectAssets(local_path)
                    self._syncAssetDataObservers()
                    self._clearDirtyAssets()
                except Exception:
                    pass
                self._deferRemoveSnapshot(snapshot)
                slicer.util.warningDisplay(str(error))
                self._appendFeed(str(error).split("\n")[0], error=True)
                return False
            self._currentVersionId = version_id
            self._updateActiveVersionIndicators()
            self._selectHistoryRowForVersion(version_id)
        finally:
            self._suppress_history_selection_signal = False
            self._closeProgress()
        if notify:
            self._appendFeed("Checked out %s." % display)
        self._painted_ids_cache_key = None
        self._painted_ids_cache = set()
        self._scheduleAnatomyTreeCoverageRefresh()
        self._updateVersionActionButtons()
        self._deferRemoveSnapshot(snapshot)
        self._armLoadSettle()
        return True

    def _deferRemoveSnapshot(self, snapshot: str | None) -> None:
        if not snapshot:
            return
        qt.QTimer.singleShot(8000, lambda path=snapshot: shutil.rmtree(path, ignore_errors=True))

    def _selectHistoryRowForVersion(self, version_id: str) -> None:
        table = self.historyTableWidget
        if not version_id or not _qt_widget_is_valid(table):
            return
        was_suppressed = bool(getattr(self, "_suppress_history_selection_signal", False))
        self._suppress_history_selection_signal = True
        table.blockSignals(True)
        try:
            for row in range(_qt_table_row_count(table)):
                id_item = table.item(row, 0)
                if id_item and self._historyVersionIdFromItem(id_item) == version_id:
                    table.selectRow(row)
                    break
        finally:
            table.blockSignals(False)
            self._suppress_history_selection_signal = was_suppressed

    def _updateActiveVersionIndicators(self) -> None:
        active = self._currentVersionId
        table = self.historyTableWidget
        if _qt_widget_is_valid(table) and table.isVisible():
            for row in range(_qt_table_row_count(table)):
                id_item = table.item(row, 0)
                if not id_item:
                    continue
                version_id = self._historyVersionIdFromItem(id_item)
                display = self._versionDisplayTag(version_id)
                if version_id == active:
                    display = "▸ " + display
                id_item.setText(display)
        if _qt_widget_is_valid(getattr(self, "checkedOutLabel", None)):
            if active and self._shouldShowCommitHistory():
                self.checkedOutLabel.setText("Checked out: %s" % self._versionDisplayTag(active))
                self.checkedOutLabel.setVisible(True)
            else:
                self.checkedOutLabel.setVisible(False)
        canvas = getattr(self.logic, "_historyCanvas", None) if self.logic else None
        if canvas is not None and hasattr(canvas, "set_active_version_id"):
            try:
                canvas.active_version_id = None
                canvas.set_active_version_id(active)
            except (RuntimeError, ValueError):
                pass

    def onOpenDependencyGraph(self) -> None:
        if not self._canOpenDependencyGraph():
            self._appendFeed(
                self.getOntologyGraphPayload()["description"],
                error=True,
            )
            return
        self.logic.openDependencyGraph()

    def onOpenHistoryGraph(self) -> None:
        if not self._canOpenVersionTree():
            payload = self.getVersionTreePayload()
            self._appendFeed(payload["description"], error=True)
            return
        self.logic.openVersionHistoryGraph()

    def _normalizeHistoryVersionId(self, value) -> str:
        text = str(value or "").strip()
        if text.startswith("▸"):
            text = text.lstrip("▸").strip()
        return text

    def _selectedVersionId(self) -> str | None:
        selected_items = self.historyTableWidget.selectedItems()
        if not selected_items:
            return None
        row = selected_items[0].row()
        id_item = self.historyTableWidget.item(row, 0)
        if not id_item:
            return None
        version_id = id_item.data(qt.Qt.UserRole)
        if version_id:
            return self._normalizeHistoryVersionId(version_id)
        return self._normalizeHistoryVersionId(id_item.text() if id_item else "") or None

    def _historyVersionIdFromItem(self, item: qt.QTableWidgetItem) -> str:
        version_id = self._normalizeHistoryVersionId(item.data(qt.Qt.UserRole))
        if version_id:
            return version_id
        return self._normalizeHistoryVersionId(item.text())

    def _styleHistoryCell(self, item: qt.QTableWidgetItem, column: int, status: str = "", version_id: str = "") -> None:
        if column == 0:
            branch = self._normalizeHistoryVersionId(
                version_id or item.data(qt.Qt.UserRole) or item.text()
            ).split("/", 1)[0]
            if branch == "main":
                item.setForeground(qt.QColor(ACCENT_MINT))
            elif branch:
                item.setForeground(qt.QColor(ACCENT_INDIGO))
            else:
                item.setForeground(qt.QColor(TEXT_MUTED))
            font = item.font()
            font.setBold(True)
            item.setFont(font)
        elif column == 2:
            item.setForeground(qt.QColor(TEXT_SECONDARY))
        elif column == 4:
            color = COMMIT_STATUS_COLORS.get(status.lower(), TEXT_SECONDARY)
            item.setForeground(qt.QColor(color))
            font = item.font()
            font.setBold(True)
            item.setFont(font)

    def _refreshHistoryTable(self) -> None:
        bundle = getattr(self, "_project_history_bundle", None) or {}
        commit_history = bundle.get("commit_history", [])
        self.historyTableWidget.setRowCount(len(commit_history))
        for row_index, row_values in enumerate(commit_history):
            status = row_values[4] if len(row_values) > 4 else ""
            version_id = row_values[0]
            for column_index, value in enumerate(row_values):
                if column_index == 0:
                    display = self._versionDisplayTag(version_id)
                    item = qt.QTableWidgetItem(display)
                    item.setData(qt.Qt.UserRole, version_id)
                else:
                    item = qt.QTableWidgetItem(str(value))
                self._styleHistoryCell(item, column_index, status, version_id=version_id)
                self.historyTableWidget.setItem(row_index, column_index, item)
        self.historyTableWidget.resizeColumnsToContents()
        if self._currentVersionId:
            self._selectHistoryRowForVersion(self._currentVersionId)
        self._updateActiveVersionIndicators()

    def _clearActivityFeed(self) -> None:
        feed = getattr(self, "feedTextEdit", None)
        if not _qt_widget_is_valid(feed):
            return
        try:
            feed.clear()
        except (RuntimeError, ValueError, TypeError):
            try:
                feed.setHtml("")
            except (RuntimeError, ValueError, TypeError):
                return

    def _appendFeed(self, message: str, error: bool = False) -> None:
        timestamp = datetime.now().strftime("%H:%M")
        prefix = "[ERROR]" if error else "[INFO]"
        line = f"[{timestamp}] {prefix} {message}"
        logging.info(line)
        feed = getattr(self, "feedTextEdit", None)
        if not _qt_widget_is_valid(feed):
            return
        color = FEED_COLOR_ERROR if error else FEED_COLOR_INFO
        markup = '<span style="color:%s">%s</span>' % (color, html.escape(line, quote=False))
        try:
            feed.append(markup)
            feed.moveCursor(qt.QTextCursor.End)
            feed.ensureCursorVisible()
        except (RuntimeError, ValueError):
            try:
                feed.insertHtml(markup + "<br>")
            except (RuntimeError, ValueError):
                logging.exception("Could not write to the activity feed")


class CollaborativeVersioningLogic(ScriptedLoadableModuleLogic):
    """Opens the anatomy tree and version tree dialogs."""

    def __init__(self) -> None:
        ScriptedLoadableModuleLogic.__init__(self)
        self.widget = None
        self.dependencyDialog = None
        self.historyDialog = None
        self._dependencyCanvas = None
        self._historyCanvas = None

    def setWidget(self, widget) -> None:
        self.widget = widget

    def onVersionCheckedOut(self, version_id: str) -> None:
        widget = self.widget
        if not widget:
            return
        widget._checkoutVersion(version_id, notify=True, sync_table=True)

    def _loadGraphModule(self):
        import CollaborativeVersioningLib.GraphCanvas as graph_module
        importlib.reload(graph_module)
        return graph_module

    def openDependencyGraph(self) -> None:
        graph_module = self._loadGraphModule()
        widget = self.widget

        if self.dependencyDialog:
            self.dependencyDialog.close()
            self.dependencyDialog.deleteLater()
            self.dependencyDialog = None

        self.dependencyDialog = qt.QDialog(slicer.util.mainWindow())
        self.dependencyDialog.setWindowFlags(qt.Qt.Window)
        self.dependencyDialog.setWindowTitle("Anatomy tree")
        self.dependencyDialog.resize(980, 640)

        layout = qt.QVBoxLayout(self.dependencyDialog)
        layout.setContentsMargins(12, 12, 12, 12)

        payload = widget.getOntologyGraphPayload() if widget else {
            "specs": [],
            "title": "Ontology",
            "description": "No ontology loaded.",
        }

        hint = qt.QLabel(
            payload["description"] or "Anatomy tree built from the project ontology map."
        )
        hint.setStyleSheet(DIALOG_HINT_STYLE)
        hint.setWordWrap(True)
        layout.addWidget(hint)

        self._dependencyCanvas = graph_module.DependencyGraphCanvas(
            self,
            dependency_specs=payload["specs"],
            graph_title=payload["title"],
            graph_description=payload["description"],
            painted_ids=None,
        )
        layout.addWidget(self._dependencyCanvas.create_toolbar())
        layout.addWidget(self._dependencyCanvas, 1)
        layout.addWidget(self._dependencyCanvas.create_legend_bar())

        self.dependencyDialog.show()
        self.dependencyDialog.raise_()
        self.dependencyDialog.activateWindow()
        qt.QTimer.singleShot(50, self._dependencyCanvas.reset_view)
        if widget:
            qt.QTimer.singleShot(100, widget._refreshAnatomyTreeCoverage)

    def openVersionHistoryGraph(self) -> None:
        graph_module = self._loadGraphModule()

        if self.historyDialog:
            self.historyDialog.close()
            self.historyDialog.deleteLater()
            self.historyDialog = None

        widget = self.widget
        version_specs = []
        graph_title = "Version tree"
        graph_description = ""
        commit_history_by_id = {}
        if widget:
            payload = widget.getVersionTreePayload()
            version_specs = payload["specs"]
            graph_title = payload["title"]
            graph_description = payload["description"]
            commit_history_by_id = graph_module.commit_history_lookup(
                (getattr(widget, "_project_history_bundle", None) or {}).get("commit_history", [])
            )

        self.historyDialog = qt.QDialog(slicer.util.mainWindow())
        self.historyDialog.setWindowFlags(qt.Qt.Window)
        self.historyDialog.setWindowTitle("Version tree")
        self.historyDialog.resize(820, 620)

        layout = qt.QVBoxLayout(self.historyDialog)
        layout.setContentsMargins(12, 12, 12, 12)

        hint = qt.QLabel(graph_description or "Version tree built from the project version history.")
        hint.setStyleSheet(DIALOG_HINT_STYLE)
        hint.setWordWrap(True)
        layout.addWidget(hint)

        canvas = graph_module.VersionHistoryCanvas(
            self,
            version_specs=version_specs,
            graph_title=graph_title,
            graph_description=graph_description,
            active_version_id=getattr(widget, "_currentVersionId", None) if widget else None,
            commit_history_by_id=commit_history_by_id,
        )
        self._historyCanvas = canvas
        layout.addWidget(canvas.create_toolbar())
        layout.addWidget(canvas, 1)

        self.historyDialog.show()
        self.historyDialog.raise_()
        self.historyDialog.activateWindow()
        qt.QTimer.singleShot(50, canvas.reset_view)


class CollaborativeVersioningTest(ScriptedLoadableModuleTest):
    def setUp(self):
        slicer.mrmlScene.Clear()

    def runTest(self):
        self.setUp()
        self.test_WidgetBuildTagPresent()

    def test_WidgetBuildTagPresent(self):
        self.assertTrue(_UI_BUILD_TAG.startswith("2026-"))
        self.delayDisplay("CollaborativeVersioning UI layout tests passed")
