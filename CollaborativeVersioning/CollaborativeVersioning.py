import copy
import html
import importlib
import logging
import os
import re
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
_UI_BUILD_TAG = "2026-10-12-notif-read-ids"

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
    GitHubMissingProjectError,
    GitHubOfflineError,
    is_missing_project_error,
    is_offline_error,
    looks_like_offline_error,
    missing_project_message,
    offline_message,
    user_facing_github_error,
    accept_project_invitation,
    commit_and_push,
    commit_local_version,
    checkout_local_version,
    connect_session,
    create_private_repository,
    decline_project_invitation,
    delete_remote_owned_repository,
    remove_local_project_dir,
    ensure_tools,
    ensure_project_info_branch,
    find_gh,
    forget_people_access,
    has_delete_repo_scope,
    local_project_dir,
    invite_project_colleague,
    list_accessible_repos,
    list_local_project_full_names,
    local_cli_login,
    merge_remote_and_local_repos,
    read_local_project_info,
    incoming_invitations_fetch_args,
    parse_incoming_invitations_output,
    list_project_people,
    parse_project_messages_output,
    project_messages_fetch_args,
    project_messages_put_args,
    build_project_activity,
    publish_project_activity,
    build_project_message,
    normalize_task_title,
    is_project_messages_conflict,
    logout_github_cli,
    open_delete_permission_window,
    open_login_window,
    open_or_update_local_project,
    fetch_remote_updates,
    fetch_local_project_info,
    adopt_shared_lanes,
    integrate_shared_lanes,
    capture_remote_sync_caps,
    derive_remote_sync_caps_from_history,
    save_remote_sync_caps,
    people_access_for,
    remote_people_access_or_none,
    read_project_history,
    read_compare_project_histories,
    remove_project_colleague,
    cancel_project_invitation,
    set_wait_callback,
    publish_current_line,
    ensure_can_share_with_shared,
    start_local_review_branch,
    create_and_publish_task_branch,
    delete_local_unshared_version,
    sha_is_shared_on_remote,
    accept_share_request,
    decline_share_request,
    suggest_github_usernames,
    work_is_on_review_branch,
    is_viewing_older_than_branch_tip,
    review_branch_for,
    current_review_branch_slug,
    normalize_branch_slug,
    submit_review_line,
    find_open_review_request,
    find_open_review_request_for_branch,
    PEOPLE_ACCESS_SENIOR,
    PEOPLE_ACCESS_JUNIOR,
    PRESENCE_PUBLISH_INTERVAL_SECONDS,
    presence_is_online,
    format_presence_ago,
    utc_now_stamp,
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
    ACCENT_MINT,
    BG_ELEVATED,
    BORDER,
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
    TEXT_ON_ICE,
    TEXT_SECONDARY,
    notification_bell_url,
)

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

_STYLE_EXPORTS = (
    "ACCENT_ICE",
    "ACCENT_INDIGO",
    "ACCENT_MINT",
    "BG_ELEVATED",
    "BORDER",
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
    "TEXT_ON_ICE",
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


# Activity that means "remote graph changed" → ⚠ until Compare / Update.
_VERSIONS_SYNC_ACTIVITY_KINDS = frozenset(("share", "accept", "assign"))


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


class NotificationsDialog(qt.QDialog):
    """Bell list: unread rows stand out; click opens the detail."""

    def __init__(
        self,
        parent=None,
        items=None,
        empty_text="",
        unread_keys=None,
        lagging_keys=None,
        sync_status_text="",
        show_sync_button: bool = False,
    ) -> None:
        qt.QDialog.__init__(self, parent)
        self.setWindowTitle("Notifications")
        self.setMinimumWidth(420)
        self.setMaximumHeight(560)
        self.setModal(True)
        self.chosen = None
        self.mark_all = False
        self.compare_requested = False
        self.sync_requested = False  # alias kept for older call sites
        self._items = list(items or [])
        unread = set(unread_keys or [])
        lagging = set(lagging_keys or [])
        layout = qt.QVBoxLayout(self)
        layout.setSpacing(8)
        if sync_status_text:
            status = qt.QLabel(sync_status_text)
            status.setWordWrap(True)
            status.setStyleSheet(
                "color: %s; font-weight: 600;" % (TEXT_SECONDARY or "#c8c8c8")
            )
            if show_sync_button:
                status.setToolTip(
                    "⚠ means your local project is not aligned with the remote copy."
                )
            else:
                status.setToolTip(
                    "✅ means this computer is aligned with the shared project."
                )
            layout.addWidget(status)
            if show_sync_button:
                sync_btn = qt.QPushButton("Compare with shared")
                accent = ACCENT_ICE or "#5b9fd4"
                sync_btn.setStyleSheet(
                    "QPushButton {"
                    " background-color: palette(button); color: %s;"
                    " border: 1px solid %s; font-weight: 600;"
                    " border-radius: 4px; padding: 6px 10px;"
                    "}"
                    "QPushButton:hover {"
                    " background-color: palette(midlight); color: %s;"
                    " border: 2px solid %s; font-weight: 700;"
                    "}"
                    "QPushButton:pressed { background-color: palette(mid); }"
                    % (accent, accent, accent, accent)
                )
                sync_btn.setToolTip(
                    "Compare your local versions with the shared project before updating."
                )
                sync_btn.connect("clicked()", self._onSync)
                layout.addWidget(sync_btn)
        if not self._items:
            hint = qt.QLabel(empty_text or "No notifications.")
            hint.setWordWrap(True)
            hint.setStyleSheet(DIALOG_HINT_STYLE)
            layout.addWidget(hint)
        else:
            scroll = qt.QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setFrameShape(qt.QFrame.NoFrame)
            scroll.setHorizontalScrollBarPolicy(qt.Qt.ScrollBarAlwaysOff)
            scroll.setMaximumHeight(360)
            holder = qt.QWidget()
            hold_layout = qt.QVBoxLayout(holder)
            hold_layout.setContentsMargins(0, 0, 2, 0)
            hold_layout.setSpacing(6)
            group = qt.QButtonGroup(self)
            last_section = None
            for index, item in enumerate(self._items):
                kind = str(item.get("kind") or "")
                section = "Invitations" if kind == "invite" else "This project"
                if section != last_section:
                    header = qt.QLabel(section)
                    header.setStyleSheet(DIALOG_HINT_STYLE)
                    hold_layout.addWidget(header)
                    last_section = section
                key = str(item.get("_key") or "")
                is_unread = key in unread
                is_lagging = key in lagging
                label = _notification_list_label(item)
                if is_unread:
                    label = "●  %s" % label
                if is_lagging:
                    label = "%s  ⚠" % label
                button = qt.QPushButton(label)
                if is_lagging:
                    tip = "Local project is not aligned with the remote copy"
                elif kind == "invite":
                    tip = "Open invitation"
                else:
                    tip = "Open notification"
                button.setToolTip(tip)
                if is_unread:
                    button.setStyleSheet(
                        "QPushButton {"
                        " text-align: left; padding: 9px 12px;"
                        " border: 1px solid %s; border-radius: 6px;"
                        " background-color: %s; font-weight: 600;"
                        "}"
                        "QPushButton:hover { border: 1px solid %s; }"
                        % (ACCENT_ICE, BG_ELEVATED or "#383838", ACCENT_ICE)
                    )
                else:
                    button.setStyleSheet(
                        "QPushButton {"
                        " text-align: left; padding: 9px 12px;"
                        " border: 1px solid %s; border-radius: 6px;"
                        " background: transparent; color: %s; font-weight: 400;"
                        "}"
                        "QPushButton:hover { border: 1px solid %s; }"
                        % (BORDER or "#505050", TEXT_MUTED, ACCENT_ICE)
                    )
                group.addButton(button, index)
                hold_layout.addWidget(button)
            hold_layout.addStretch(1)
            try:
                group.connect("idClicked(int)", self._onPick)
            except (TypeError, RuntimeError, AttributeError):
                group.connect("buttonClicked(int)", self._onPick)
            self._group = group
            scroll.setWidget(holder)
            layout.addWidget(scroll)

        buttons = qt.QHBoxLayout()
        buttons.addStretch(1)
        if self._items:
            markAllButton = qt.QPushButton("Mark all as read")
            markAllButton.setStyleSheet(BTN_SECONDARY)
            markAllButton.connect("clicked()", self._onMarkAll)
            buttons.addWidget(markAllButton)
        closeButton = qt.QPushButton("Close")
        closeButton.setStyleSheet(BTN_SECONDARY)
        closeButton.connect("clicked()", self.reject)
        buttons.addWidget(closeButton)
        layout.addLayout(buttons)

    def _onMarkAll(self) -> None:
        self.mark_all = True
        self.chosen = None
        self.compare_requested = False
        self.sync_requested = False
        self.reject()

    def _onSync(self) -> None:
        self.compare_requested = True
        self.sync_requested = True
        self.chosen = None
        self.mark_all = False
        self.reject()

    def _onPick(self, index) -> None:
        try:
            index = int(index)
        except (TypeError, ValueError):
            return
        if 0 <= index < len(self._items):
            self.chosen = self._items[index]
        self.accept()


class CompareWithSharedDialog(qt.QDialog):
    """Compare local vs shared graphs, preview a choice, then Validate to apply."""

    ACTION_NONE = ""
    ACTION_UPDATE = "update"
    ACTION_KEEP = "keep"
    ACTION_RESET = "reset"
    ACTION_LINEAR = "linear"
    ACTION_MERGE = "merge"

    def __init__(self, parent, compare: dict | None = None) -> None:
        qt.QDialog.__init__(self, parent)
        self.setWindowTitle("Compare with shared")
        self.setModal(True)
        # Independent window with Minimize / Maximize (Restore) / Close.
        try:
            self.setWindowFlags(
                qt.Qt.Window
                | qt.Qt.WindowTitleHint
                | qt.Qt.WindowSystemMenuHint
                | qt.Qt.WindowMinMaxButtonsHint
                | qt.Qt.WindowCloseButtonHint
            )
        except (AttributeError, TypeError, RuntimeError):
            self.setWindowFlags(qt.Qt.Window)
        try:
            screen = qt.QApplication.primaryScreen()
            geo = screen.availableGeometry() if screen is not None else None
            if geo is not None and geo.width() > 0 and geo.height() > 0:
                # Stay inside the screen even when Result preview adds a third graph.
                self.setMaximumSize(geo.width(), geo.height())
                self.resize(
                    min(geo.width(), max(900, int(geo.width() * 0.85))),
                    min(geo.height(), max(640, int(geo.height() * 0.85))),
                )
            else:
                self.resize(1280, 820)
        except (AttributeError, TypeError, RuntimeError):
            self.resize(1280, 820)
        self.action = self.ACTION_NONE
        self._pending = self.ACTION_NONE
        self._compare = dict(compare or {})
        self._conflict = bool(self._compare.get("conflict"))
        self._conflict_lanes = [
            str(name).strip()
            for name in (self._compare.get("conflict_lanes") or ())
            if str(name).strip()
        ]
        self._obsolete_merged = bool(self._compare.get("obsolete_merged"))
        self._obsolete_merged_lanes = [
            str(name).strip()
            for name in (self._compare.get("obsolete_merged_lanes") or ())
            if str(name).strip()
        ]
        self._reset_lanes = [
            str(name).strip()
            for name in (self._compare.get("reset_lanes") or ())
            if str(name).strip()
        ]
        self._aligned = bool(self._compare.get("aligned"))
        self._has_remote = bool(self._compare.get("has_remote_extras"))
        self._has_new_remote_lanes = bool(self._compare.get("has_new_remote_lanes"))
        self._new_remote_lanes = [
            str(name).strip()
            for name in (self._compare.get("new_remote_lanes") or ())
            if str(name).strip()
        ]
        self._has_local = bool(self._compare.get("has_local_extras"))
        self._graph_module = None

        layout = qt.QVBoxLayout(self)
        layout.setSpacing(8)
        layout.setContentsMargins(10, 10, 10, 10)

        import CollaborativeVersioningLib.GraphCanvas as graph_module

        self._graph_module = graph_module
        logic = _CompareGraphLogic()
        local_model = self._compare.get("local") or {}
        remote_model = self._compare.get("remote") or {}
        # Any differing nodes — not only main-line conflict.
        diff_local = set(self._compare.get("only_local_ids_local") or set())
        diff_remote = set(self._compare.get("only_remote_ids_remote") or set())

        graphs_row = qt.QWidget()
        graphs_layout = qt.QHBoxLayout(graphs_row)
        graphs_layout.setContentsMargins(0, 0, 0, 0)
        graphs_layout.setSpacing(8)

        title_style = (
            "font-size: 15px; font-weight: 800; padding: 6px 0 2px 0;"
        )

        local_col = qt.QVBoxLayout()
        local_title = qt.QLabel("Local (this computer)")
        local_title.setAlignment(qt.Qt.AlignHCenter)
        local_title.setStyleSheet(title_style)
        local_col.addWidget(local_title)
        self._local_canvas = graph_module.VersionHistoryCanvas(
            logic,
            version_specs=list(local_model.get("version_specs") or []),
            graph_title="Local",
            graph_description="",
            active_version_id=None,
            commit_history_by_id=graph_module.commit_history_lookup(
                local_model.get("commit_history") or []
            ),
            read_only=True,
            conflict_ids=diff_local,
            diff_side="local",
            minimum_height=200,
            fit_tight=True,
        )
        local_col.addWidget(self._local_canvas, 1)
        graphs_layout.addLayout(local_col, 1)

        remote_col = qt.QVBoxLayout()
        remote_title = qt.QLabel("Shared (remote)")
        remote_title.setAlignment(qt.Qt.AlignHCenter)
        remote_title.setStyleSheet(title_style)
        remote_col.addWidget(remote_title)
        self._remote_canvas = graph_module.VersionHistoryCanvas(
            logic,
            version_specs=list(remote_model.get("version_specs") or []),
            graph_title="Shared",
            graph_description="",
            active_version_id=None,
            commit_history_by_id=graph_module.commit_history_lookup(
                remote_model.get("commit_history") or []
            ),
            read_only=True,
            conflict_ids=diff_remote,
            diff_side="shared",
            minimum_height=200,
            fit_tight=True,
        )
        remote_col.addWidget(self._remote_canvas, 1)
        graphs_layout.addLayout(remote_col, 1)
        layout.addWidget(graphs_row, 5)

        # Legend under the two graphs, above the Conflicts section.
        self._diff_legend = qt.QLabel(
            "The red dashed boxes mark versions that differ "
            "between this computer and the shared project."
        )
        self._diff_legend.setWordWrap(True)
        self._diff_legend.setAlignment(qt.Qt.AlignHCenter)
        self._diff_legend.setStyleSheet(DIALOG_HINT_STYLE)
        if self._aligned or (not diff_local and not diff_remote):
            self._diff_legend.hide()
        layout.addWidget(self._diff_legend)

        # Fixed Conflicts section (same place for OK / conflict).
        ice = ACCENT_ICE or "#5b9fd4"
        border = BORDER or "#505050"
        elevated = BG_ELEVATED or "#383838"
        self._conflicts_box = qt.QFrame()
        self._conflicts_box.setObjectName("conflictsBox")
        self._conflicts_box.setStyleSheet(
            "QFrame#conflictsBox {"
            " border: 1px solid %s; border-radius: 8px;"
            " background-color: %s; padding: 4px;"
            "}"
            % (border, elevated)
        )
        conflicts_layout = qt.QVBoxLayout(self._conflicts_box)
        conflicts_layout.setContentsMargins(14, 10, 14, 12)
        conflicts_layout.setSpacing(8)
        conflicts_header = qt.QLabel("Conflicts")
        conflicts_header.setAlignment(qt.Qt.AlignHCenter)
        conflicts_header.setStyleSheet(
            "font-size: 15px; font-weight: 800; color: %s; border: none;"
            " background: transparent; padding: 0;"
            % ice
        )
        conflicts_layout.addWidget(conflicts_header)
        self._conflicts_body = qt.QLabel("")
        self._conflicts_body.setWordWrap(True)
        self._conflicts_body.setAlignment(qt.Qt.AlignHCenter)
        self._conflicts_body.setStyleSheet(
            "font-size: 12px; font-weight: 500; border: none;"
            " background: transparent; color: %s;"
            % (TEXT_SECONDARY or "#b8bcc4")
        )
        conflicts_layout.addWidget(self._conflicts_body)

        choice_row = qt.QHBoxLayout()
        choice_row.setSpacing(10)
        choice_row.addStretch(1)
        self._update_choice_btn = qt.QPushButton("Update version tree")
        self._update_choice_btn.setStyleSheet(BTN_SECONDARY)
        self._update_choice_btn.setToolTip(
            "Preview: refresh the version tree from shared (does not replace open assets)."
        )
        self._update_choice_btn.connect(
            "clicked()", lambda: self._selectChoice(self.ACTION_UPDATE)
        )
        self._keep_btn = qt.QPushButton("Keep mine")
        self._keep_btn.setStyleSheet(BTN_SECONDARY)
        self._keep_btn.setToolTip(
            "Preview: keep this computer's main tip. Shared tip is not applied."
        )
        self._keep_btn.connect("clicked()", lambda: self._selectChoice(self.ACTION_KEEP))
        self._reset_btn = qt.QPushButton("Reset to shared")
        self._reset_btn.setStyleSheet(BTN_SECONDARY)
        self._reset_btn.setToolTip(
            "Replace conflicting local branches with the shared tips. "
            "Other local branches stay. Conflicting local versions leave those lines."
        )
        self._reset_btn.connect(
            "clicked()", lambda: self._selectChoice(self.ACTION_RESET)
        )
        self._linear_btn = qt.QPushButton("Add shared, then mine")
        self._linear_btn.setStyleSheet(BTN_SECONDARY)
        self._linear_btn.setToolTip(
            "On conflicting branches only: take the shared versions first, "
            "then keep your local work on top. Other local branches stay."
        )
        self._linear_btn.connect(
            "clicked()", lambda: self._selectChoice(self.ACTION_LINEAR)
        )
        self._merge_btn = qt.QPushButton("Keep both (merge) — coming")
        self._merge_btn.setStyleSheet(BTN_SECONDARY)
        self._merge_btn.setToolTip(
            "Keep both sides by merging annotations. Not available yet."
        )
        self._merge_btn.connect(
            "clicked()", lambda: self._selectChoice(self.ACTION_MERGE)
        )
        choice_row.addWidget(self._update_choice_btn)
        choice_row.addWidget(self._keep_btn)
        choice_row.addWidget(self._reset_btn)
        choice_row.addWidget(self._linear_btn)
        choice_row.addWidget(self._merge_btn)
        choice_row.addStretch(1)
        conflicts_layout.addLayout(choice_row)

        self._conflict_options_help = qt.QLabel(
            "• Reset to shared — conflicting branches match shared; other local branches stay. "
            "Warning: conflicting saved versions leave those branch lines.\n"
            "• Add shared, then mine — on conflicting branches only, take shared first, "
            "then keep your local work on top. Other local branches stay.\n"
            "• Keep both (merge) — coming — keep both sides by merging annotations "
            "(not available yet)."
        )
        self._conflict_options_help.setWordWrap(True)
        self._conflict_options_help.setAlignment(qt.Qt.AlignLeft | qt.Qt.AlignTop)
        self._conflict_options_help.setStyleSheet(
            "font-size: 11px; font-weight: 500; border: none;"
            " background: transparent; color: %s; padding: 2px 4px;"
            % (TEXT_SECONDARY or "#b8bcc4")
        )
        self._conflict_options_help.hide()
        conflicts_layout.addWidget(self._conflict_options_help)
        layout.addWidget(self._conflicts_box)

        self._result_panel = qt.QWidget()
        result_layout = qt.QVBoxLayout(self._result_panel)
        result_layout.setContentsMargins(0, 0, 0, 0)
        result_layout.setSpacing(4)
        result_title = qt.QLabel("Result (preview)")
        result_title.setAlignment(qt.Qt.AlignHCenter)
        result_title.setStyleSheet(
            "font-size: 15px; font-weight: 800; padding: 6px 0 2px 0;"
        )
        result_layout.addWidget(result_title)
        self._result_legend = qt.QLabel(
            "Green dashed boxes show what this choice applies "
            "(from shared and/or yours on top)."
        )
        self._result_legend.setWordWrap(True)
        self._result_legend.setAlignment(qt.Qt.AlignHCenter)
        self._result_legend.setStyleSheet(DIALOG_HINT_STYLE)
        self._result_legend.hide()
        result_layout.addWidget(self._result_legend)
        self._result_canvas = graph_module.VersionHistoryCanvas(
            logic,
            version_specs=[],
            graph_title="Result",
            graph_description="",
            read_only=True,
            minimum_height=200,
            fit_tight=True,
        )
        result_layout.addWidget(self._result_canvas, 1)
        # Same stretch as the Local | Shared row so graph 3 matches their size.
        layout.addWidget(self._result_panel, 5)

        bottom = qt.QHBoxLayout()
        bottom.addStretch(1)
        self._validate_btn = qt.QPushButton("Validate")
        self._validate_btn.setStyleSheet(BTN_CREATE)
        self._validate_btn.setEnabled(False)
        self._validate_btn.setToolTip("Apply the selected choice to this computer.")
        self._validate_btn.connect("clicked()", self._onValidate)
        close_btn = qt.QPushButton("Close")
        close_btn.setStyleSheet(BTN_SECONDARY)
        close_btn.connect("clicked()", self.reject)
        bottom.addWidget(self._validate_btn)
        bottom.addWidget(close_btn)
        layout.addLayout(bottom)

        self._setupInitialState()

    def _clampDialogToScreen(self) -> None:
        """Keep the dialog inside the available screen after Result preview appears."""
        try:
            screen = None
            if hasattr(self, "screen"):
                screen = self.screen()
            if screen is None:
                screen = qt.QApplication.primaryScreen()
            geo = screen.availableGeometry() if screen is not None else None
            if geo is None or geo.width() <= 0 or geo.height() <= 0:
                return
            self.setMaximumSize(geo.width(), geo.height())
            frame = self.frameGeometry() if hasattr(self, "frameGeometry") else self.geometry()
            width = min(max(int(self.width()), 640), int(geo.width()))
            height = min(max(int(self.height()), 480), int(geo.height()))
            if self.width() != width or self.height() != height:
                self.resize(width, height)
            x = int(frame.x()) if frame is not None else int(self.x())
            y = int(frame.y()) if frame is not None else int(self.y())
            x = max(int(geo.left()), min(x, int(geo.right()) - width + 1))
            y = max(int(geo.top()), min(y, int(geo.bottom()) - height + 1))
            self.move(x, y)
        except (AttributeError, TypeError, RuntimeError, ValueError):
            pass

    def _fitCompareGraphs(self) -> None:
        """Scale local / shared / result graphs once to fill the current window."""
        self._clampDialogToScreen()
        for canvas in (
            getattr(self, "_local_canvas", None),
            getattr(self, "_remote_canvas", None),
            getattr(self, "_result_canvas", None),
        ):
            if canvas is None:
                continue
            try:
                canvas.reset_view()
            except (AttributeError, RuntimeError, TypeError):
                pass

    def showEvent(self, event) -> None:
        qt.QDialog.showEvent(self, event)
        # Single fit after the dialog is laid out — no resize loop.
        qt.QTimer.singleShot(0, self._fitCompareGraphs)

    def _choiceButtonStyle(self, selected: bool) -> str:
        if not selected:
            return BTN_SECONDARY
        accent = ACCENT_ICE or "#5b9fd4"
        return (
            "QPushButton {"
            " background-color: palette(midlight); color: %s;"
            " border: 2px solid %s; font-weight: 700;"
            " border-radius: 4px; padding: 6px 10px;"
            "}"
            % (accent, accent)
        )

    def _refreshChoiceStyles(self) -> None:
        self._update_choice_btn.setStyleSheet(
            self._choiceButtonStyle(self._pending == self.ACTION_UPDATE)
        )
        self._keep_btn.setStyleSheet(
            self._choiceButtonStyle(self._pending == self.ACTION_KEEP)
        )
        self._reset_btn.setStyleSheet(
            self._choiceButtonStyle(self._pending == self.ACTION_RESET)
        )
        self._linear_btn.setStyleSheet(
            self._choiceButtonStyle(self._pending == self.ACTION_LINEAR)
        )
        self._merge_btn.setStyleSheet(
            self._choiceButtonStyle(self._pending == self.ACTION_MERGE)
        )

    def _hideAllChoiceButtons(self) -> None:
        self._update_choice_btn.hide()
        self._keep_btn.hide()
        self._reset_btn.hide()
        self._linear_btn.hide()
        self._merge_btn.hide()
        help_lbl = getattr(self, "_conflict_options_help", None)
        if help_lbl is not None:
            help_lbl.hide()

    def _setConflictsMessage(self, text: str) -> None:
        body = getattr(self, "_conflicts_body", None)
        if body is not None:
            body.setText(str(text or "").strip())

    def _lanesLabel(self, lanes) -> str:
        names = [str(name).strip() for name in (lanes or ()) if str(name).strip()]
        if not names:
            return "the same branch"
        if len(names) == 1:
            return names[0]
        if len(names) == 2:
            return "%s and %s" % (names[0], names[1])
        return "%s, and %s" % (", ".join(names[:-1]), names[-1])

    def _conflictLanesLabel(self) -> str:
        return self._lanesLabel(self._conflict_lanes)

    def _setupInitialState(self) -> None:
        # Handled flows: tip conflict alone, obsolete merged alone, shared ahead
        # (Update). Tip conflict + obsolete together → not handled (integration TBD).
        self._hideAllChoiceButtons()
        if self._conflict and self._obsolete_merged:
            self._setConflictsMessage(
                "This case is not handled yet.\n"
                "Tip conflict and an obsolete merged branch at the same time.\n"
                "Ask the developer to integrate it."
            )
            self._result_panel.hide()
            self._validate_btn.setEnabled(False)
            return
        if self._conflict:
            self._setConflictsMessage(
                "Local and shared have diverged on: %s.\n"
                "Reset / Add shared only change those branches; other local versions stay.\n"
                "Choose how to integrate, then Validate."
                % self._conflictLanesLabel()
            )
            self._update_choice_btn.hide()
            self._keep_btn.hide()
            self._reset_btn.show()
            self._linear_btn.show()
            self._merge_btn.show()
            self._conflict_options_help.show()
            self._result_panel.hide()
            self._validate_btn.setEnabled(False)
            return

        if self._obsolete_merged:
            branches = self._lanesLabel(self._obsolete_merged_lanes)
            many = len(self._obsolete_merged_lanes) > 1
            reset_also = self._lanesLabel(
                self._reset_lanes or (["main"] + list(self._obsolete_merged_lanes))
            )
            self._setConflictsMessage(
                (
                    "Branches %s were already merged onto main on the shared project.\n"
                    "Your local versions on those branches are obsolete.\n"
                    "Reset moves these tips to shared: %s "
                    "(main included — unshared main versions leave the tree).\n"
                    "Click Validate to apply."
                    if many
                    else "Branch %s was already merged onto main on the shared project.\n"
                    "Your local versions on that branch are obsolete.\n"
                    "Reset moves these tips to shared: %s "
                    "(main included — unshared main versions leave the tree).\n"
                    "Click Validate to apply."
                )
                % (branches, reset_also)
            )
            self._reset_btn.show()
            self._selectChoice(self.ACTION_RESET, silent=True)
            return
        if self._has_remote or self._has_new_remote_lanes:
            # No tip fork: show shared updates / new empty lanes. Local unshared stay.
            lanes = self._lanesLabel(self._new_remote_lanes)
            if self._has_local:
                if self._has_new_remote_lanes and not self._has_remote:
                    self._setConflictsMessage(
                        "No tip conflict — the shared project has new branches (%s), "
                        "and you also have local versions not shared yet.\n"
                        "Preview: Update version tree (your local unshared versions stay). "
                        "Click Validate to apply."
                        % lanes
                    )
                else:
                    self._setConflictsMessage(
                        "No tip conflict — the shared project has newer versions, "
                        "and you also have local versions not shared yet.\n"
                        "Preview: Update version tree (your local unshared versions stay). "
                        "Click Validate to apply."
                    )
            elif self._has_new_remote_lanes and not self._has_remote:
                self._setConflictsMessage(
                    "No conflicts — the shared project has new branches (%s). "
                    "Preview below shows the result after integrating them into your local folder. "
                    "Click Validate to apply."
                    % lanes
                )
            else:
                self._setConflictsMessage(
                    "No conflicts — the shared project has newer versions. "
                    "Preview below shows the result after integrating them into your local folder. "
                    "Click Validate to apply."
                )
            self._selectChoice(self.ACTION_UPDATE, silent=True)
            return

        self._setConflictsMessage(
            "This case is not handled yet.\n"
            "Ask the developer to integrate it."
        )
        self._result_panel.hide()
        self._validate_btn.setEnabled(False)

    def _idsForShas(self, model: dict, shas) -> set:
        sha_by_id = (model or {}).get("sha_by_id") or {}
        wanted = set(shas or ())
        return {vid for vid, sha in sha_by_id.items() if sha in wanted}

    def _resultMarksForChoice(self, choice: str, model: dict) -> tuple:
        """Green marks for Result: (result_ids, result_roles)."""
        only_remote = set(self._compare.get("only_remote_shas") or ())
        only_local = set(self._compare.get("only_local_shas") or ())
        local_model = self._compare.get("local") or {}
        local_sha_by_id = local_model.get("sha_by_id") or {}
        conflict_local_ids = set(self._compare.get("conflict_ids_local") or ())
        conflict_local_shas = {
            local_sha_by_id[vid]
            for vid in conflict_local_ids
            if vid in local_sha_by_id and local_sha_by_id[vid]
        }
        roles = {}
        if choice == self.ACTION_RESET:
            # Same as Shared reds → green (taking shared).
            mark_shas = only_remote
            if not mark_shas:
                remote_model = self._compare.get("remote") or {}
                remote_sha_by_id = remote_model.get("sha_by_id") or {}
                for vid in set(self._compare.get("conflict_ids_remote") or ()):
                    sha = remote_sha_by_id.get(vid)
                    if sha:
                        mark_shas.add(sha)
            for vid in self._idsForShas(model, mark_shas):
                roles[vid] = "shared"
        elif choice == self.ACTION_LINEAR:
            # Shared reds + local versions kept on top.
            local_mark = conflict_local_shas or only_local
            for vid in self._idsForShas(model, only_remote):
                roles[vid] = "shared"
            for vid in self._idsForShas(model, local_mark):
                roles[vid] = "local"
        elif choice == self.ACTION_UPDATE:
            # Shared tips acknowledged + local unshared kept.
            # Include new empty remote lanes (same SHA as main — not in only_remote_shas).
            shared_ids = set(self._idsForShas(model, only_remote))
            shared_ids.update(self._compare.get("only_remote_ids_result") or ())
            shared_ids.update(self._compare.get("only_remote_ids_remote") or ())
            model_ids = set((model or {}).get("sha_by_id") or {})
            for vid in shared_ids:
                if vid in model_ids:
                    roles[vid] = "shared"
            for vid in self._idsForShas(model, only_local):
                roles[vid] = "local"
        elif choice == self.ACTION_KEEP:
            for vid in self._idsForShas(model, only_local):
                roles[vid] = "local"
        return set(roles.keys()), roles

    def _modelForChoice(self, choice: str) -> tuple:
        """Return (model, title, description) for the result preview."""
        local_model = self._compare.get("local") or {}
        remote_model = self._compare.get("remote") or {}
        # Union preview: shared tips + local review tips (Update keeps unshared).
        update_model = self._compare.get("result") or remote_model
        linear_model = self._compare.get("linear") or remote_model
        reset_model = self._compare.get("reset") or remote_model
        lanes = self._conflictLanesLabel()

        if choice == self.ACTION_KEEP:
            return (
                local_model,
                "Result — Keep mine",
                "Local tip stays; shared tip is not applied",
            )
        if choice == self.ACTION_RESET:
            reset_names = (
                self._reset_lanes or self._conflict_lanes or self._obsolete_merged_lanes
            )
            reset_lanes = self._lanesLabel(reset_names)
            includes_main = any(
                str(name).strip().lower() == "main" for name in (reset_names or ())
            )
            detail = "Branches (%s) match shared; other local versions stay" % reset_lanes
            if includes_main:
                detail += " — unshared main versions leave the tree"
            return (
                reset_model,
                "Result — Reset to shared",
                detail,
            )
        if choice == self.ACTION_UPDATE:
            if self._has_local:
                return (
                    update_model,
                    "Result — Update from shared",
                    "Shared versions added; your local unshared versions stay",
                )
            return (
                remote_model,
                "Result — Update from shared",
                "This computer follows the shared tips",
            )
        if choice == self.ACTION_LINEAR:
            return (
                linear_model,
                "Result — Add shared, then mine",
                "On %s: shared first, then your local work; other branches stay"
                % lanes,
            )
        return (
            {},
            "Result — Keep both (merge)",
            "Coming soon",
        )

    def _selectChoice(self, choice: str, silent: bool = False) -> None:
        self._pending = choice
        self._refreshChoiceStyles()
        if choice == self.ACTION_MERGE:
            self._result_panel.hide()
            legend = getattr(self, "_result_legend", None)
            if legend is not None:
                legend.hide()
            self._validate_btn.setEnabled(False)
            self._validate_btn.setToolTip(
                "Keep both (merge) is not available yet — "
                "choose Reset to shared or Add shared, then mine."
            )
            if not silent:
                self._setConflictsMessage(
                    "Keep both (merge) is coming soon.\n"
                    "Choose Reset to shared or Add shared, then mine, then Validate."
                )
            return

        model, title, description = self._modelForChoice(choice)
        result_ids, result_roles = self._resultMarksForChoice(choice, model)
        gm = self._graph_module
        self._result_canvas.set_compare_content(
            version_specs=list(model.get("version_specs") or []),
            graph_title=title,
            graph_description=description,
            active_version_id=model.get("head_id"),
            commit_history_by_id=gm.commit_history_lookup(
                model.get("commit_history") or []
            ),
            conflict_ids=set(),
            result_ids=result_ids,
            result_roles=result_roles,
        )
        legend = getattr(self, "_result_legend", None)
        if legend is not None:
            if result_ids:
                legend.show()
            else:
                legend.hide()
        self._result_panel.show()
        qt.QTimer.singleShot(0, self._fitCompareGraphs)
        self._validate_btn.setEnabled(True)
        self._validate_btn.setToolTip("Apply this choice to this computer.")
        if not silent:
            labels = {
                self.ACTION_KEEP: "Keep mine",
                self.ACTION_RESET: "Reset to shared",
                self.ACTION_LINEAR: "Add shared, then mine",
                self.ACTION_UPDATE: "Update version tree",
            }
            self._setConflictsMessage(
                "Preview: %s.\nClick Validate to apply, or pick another option."
                % labels.get(choice, choice)
            )

    def _onValidate(self) -> None:
        if self._pending in (
            self.ACTION_UPDATE,
            self.ACTION_KEEP,
            self.ACTION_RESET,
            self.ACTION_LINEAR,
        ):
            self.action = self._pending
            self.accept()


class _CompareGraphLogic(object):
    """No-op logic so compare canvases stay read-only."""

    def onVersionCheckedOut(self, node_id) -> None:
        return

    def reviewActionsForVersion(self, spec, history) -> dict:
        return {}


class NotificationDetailDialog(qt.QDialog):
    """Read one notification. Invitations can Join / Decline here."""

    def __init__(self, parent, item: dict, guidance: str = "") -> None:
        qt.QDialog.__init__(self, parent)
        self.setWindowTitle("Notification")
        self.setFixedWidth(420)
        self.setModal(True)
        self.choice = ""
        item = item or {}
        kind = str(item.get("kind") or "")
        layout = qt.QVBoxLayout(self)
        layout.setSpacing(10)

        if kind == "invite":
            title = "Invitation"
            body = "You were invited to %s." % (item.get("full_name") or "a project")
        else:
            title = _notification_detail_title(item)
            body = _notification_text(item.get("text") or "Project update", 160)
        head = qt.QLabel(title)
        head.setStyleSheet("font-weight: 600; font-size: 13px;")
        layout.addWidget(head)

        body_label = qt.QLabel(body)
        body_label.setWordWrap(True)
        body_label.setTextInteractionFlags(qt.Qt.TextSelectableByMouse)
        try:
            body_label.setMaximumHeight(120)
        except (AttributeError, TypeError, RuntimeError):
            pass
        layout.addWidget(body_label)

        guide = str(guidance or item.get("guidance") or "").strip()
        if guide:
            guide_label = qt.QLabel(guide)
            guide_label.setWordWrap(True)
            guide_label.setTextInteractionFlags(qt.Qt.TextSelectableByMouse)
            guide_label.setStyleSheet(
                "color: %s; font-size: 11px; font-weight: 600;"
                % (TEXT_SECONDARY or "#c8c8c8")
            )
            layout.addWidget(guide_label)

        when = str(item.get("when") or item.get("at_label") or "").strip()
        if when:
            meta = qt.QLabel(when)
            meta.setWordWrap(True)
            meta.setStyleSheet(DIALOG_HINT_STYLE)
            layout.addWidget(meta)

        buttons = qt.QHBoxLayout()
        buttons.addStretch(1)
        if kind == "invite":
            decline_btn = qt.QPushButton("Decline")
            join_btn = qt.QPushButton("Join")
            later_btn = qt.QPushButton("Close")
            decline_btn.setStyleSheet(BTN_DELETE)
            join_btn.setStyleSheet(BTN_CREATE)
            later_btn.setStyleSheet(BTN_SECONDARY)
            decline_btn.connect("clicked()", lambda: self._finish("decline"))
            join_btn.connect("clicked()", lambda: self._finish("join"))
            later_btn.connect("clicked()", self.reject)
            buttons.addWidget(later_btn)
            buttons.addWidget(decline_btn)
            buttons.addWidget(join_btn)
        else:
            close_btn = qt.QPushButton("Close")
            close_btn.setStyleSheet(BTN_SECONDARY)
            close_btn.connect("clicked()", self.accept)
            buttons.addWidget(close_btn)
        layout.addLayout(buttons)

    def _finish(self, choice: str) -> None:
        self.choice = choice
        self.accept()


class PeopleDialog(qt.QDialog):
    """See who is on the project. Owners can add or remove a colleague."""

    def __init__(
        self,
        parent=None,
        people=None,
        can_add=False,
        presence=None,
        me="",
    ) -> None:
        qt.QDialog.__init__(self, parent)
        self.setWindowTitle("People")
        self.setMinimumWidth(460)
        self.setModal(True)
        self._people = []
        self._presence = dict(presence or {})
        self._me = str(me or "").strip()
        self._can_add = bool(can_add)
        self._add_handler = None
        self._remove_handler = None

        layout = qt.QVBoxLayout(self)
        layout.setSpacing(10)

        people_label = qt.QLabel("People on this project:")
        people_label.setStyleSheet(DIALOG_HINT_STYLE)
        layout.addWidget(people_label)
        presence_hint = qt.QLabel(
            "🟢 Online = active in the last ~2–3 min   ·   ⚫ Offline = last seen earlier"
        )
        presence_hint.setWordWrap(True)
        presence_hint.setStyleSheet(DIALOG_HINT_STYLE)
        layout.addWidget(presence_hint)

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
        self.accessCombo.addItem("Senior")
        self.accessCombo.addItem("Junior")
        form.addRow("Role:", self.accessCombo)
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
            "They will receive an invitation. After they accept, the project appears in their list.\n"
            "Senior: can assign Tasks, share onto main, "
            "and Accept / Decline a junior's review request.\n"
            "Junior: can work on the project and share on their own branch "
            "(after a senior assigns a Task)."
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
        self.set_people(people or [], presence=self._presence)
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
            return PEOPLE_ACCESS_JUNIOR
        try:
            index = self.accessCombo.currentIndex
            if callable(index):
                index = index()
            if int(index) == 0:
                return PEOPLE_ACCESS_SENIOR
        except (TypeError, ValueError, RuntimeError, AttributeError):
            pass
        return PEOPLE_ACCESS_JUNIOR

    def username(self) -> str:
        try:
            text = self.usernameEdit.text
            if callable(text):
                text = text()
        except (TypeError, AttributeError, RuntimeError):
            text = ""
        return str(text or "").strip().lstrip("@")

    def people(self) -> list:
        return list(self._people)

    def _presence_label_for(self, login: str) -> str:
        name = str(login or "").strip()
        key = name.lower()
        me = str(getattr(self, "_me", "") or "").strip().lower()
        entry = (getattr(self, "_presence", {}) or {}).get(key) or {}
        stamp = str(entry.get("at") or "").strip()
        if me and key == me:
            return "🟢 Online"
        if presence_is_online(stamp):
            return "🟢 Online"
        ago = format_presence_ago(stamp)
        if ago:
            return "⚫ Offline · last seen %s" % ago
        return "⚫ Offline"

    def set_people(self, people, presence=None) -> None:
        self._people = list(people or [])
        if presence is not None:
            self._presence = dict(presence or {})
        self.peopleList.clear()
        if not self._people:
            self.peopleList.addItem("No one listed yet.")
            self._updateRemoveEnabled()
            return
        for person in self._people:
            login = str(person.get("login") or "").strip()
            role = str(person.get("role") or "")
            access = str(person.get("access") or PEOPLE_ACCESS_JUNIOR)
            if access == PEOPLE_ACCESS_SENIOR:
                role_label = "senior"
            else:
                role_label = "junior"
            status = self._presence_label_for(login)
            if role == "owner":
                label = "%s (owner-senior)  %s" % (login, status)
            elif role == "pending":
                label = "%s (invitation pending · %s)  %s" % (login, role_label, status)
            else:
                label = "%s (%s)  %s" % (login, role_label, status)
            self.peopleList.addItem(label)
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


_TASK_EXCERPT_LEN = 18
_NOTIFICATION_TEXT_LEN = 72


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


class TaskDialog(qt.QDialog):
    """Assign tasks to one or more juniors (senior), or browse all project tasks."""

    def __init__(
        self,
        parent,
        people=None,
        tasks=None,
        me="",
        can_assign=False,
        is_senior=False,
        draft=None,
    ) -> None:
        qt.QDialog.__init__(self, parent)
        self.setWindowTitle("Tasks")
        self.setFixedWidth(520)
        self.setModal(True)
        self._people = list(people or [])
        # Voluntary tasks are retired — only assigned tasks remain.
        self._all_tasks = [
            task for task in (tasks or []) if self._is_assigned_task(task)
        ]
        self._tasks = list(self._all_tasks)
        self._me = str(me or "").strip()
        self._can_assign = bool(can_assign)
        # Owner/senior viewing without assign (e.g. local mode): empty hint differs.
        self._is_senior = bool(is_senior) or bool(can_assign)
        self._assign_handler = None
        self._update_handler = None
        self._cancel_handler = None
        self._pick_start_handler = None
        self._anchor_sha = ""
        self._anchor_label = ""
        self._editing_task_id = ""

        layout = qt.QVBoxLayout(self)
        layout.setSpacing(10)

        self.assignPanel = qt.QWidget()
        form = qt.QFormLayout(self.assignPanel)
        form.setContentsMargins(0, 0, 0, 0)
        form.setSpacing(8)
        self.descriptionEdit = qt.QPlainTextEdit()
        self.descriptionEdit.setStyleSheet(FIELD_STYLE)
        self.descriptionEdit.setPlaceholderText("What should they work on?")
        self.descriptionEdit.setFixedHeight(72)
        self.descriptionEdit.setLineWrapMode(qt.QPlainTextEdit.WidgetWidth)
        self.descriptionEdit.setSizePolicy(qt.QSizePolicy.Ignored, qt.QSizePolicy.Fixed)
        try:
            self.descriptionEdit.setTabChangesFocus(True)
        except (AttributeError, TypeError, RuntimeError):
            pass
        form.addRow("Description:", self.descriptionEdit)
        self.juniorList = qt.QListWidget()
        # Slicer's default list indicators are often invisible; draw a clear box.
        accent = ACCENT_ICE or "#5b9fd4"
        self.juniorList.setStyleSheet(
            """
            QListWidget {
                background-color: palette(base);
                color: palette(text);
                border: 1px solid palette(mid);
                border-radius: 4px;
                outline: none;
                padding: 2px;
            }
            QListWidget::item {
                padding: 4px 6px;
                margin: 1px 0px;
            }
            QListWidget::indicator {
                width: 15px;
                height: 15px;
                border: 1px solid palette(text);
                border-radius: 3px;
                background-color: palette(base);
            }
            QListWidget::indicator:unchecked {
                border: 1px solid palette(text);
                background-color: palette(base);
            }
            QListWidget::indicator:checked {
                border: 1px solid %s;
                background-color: %s;
            }
            """
            % (accent, accent)
        )
        self.juniorList.setMinimumHeight(96)
        self.juniorList.setMaximumHeight(140)
        self.juniorList.setSelectionMode(qt.QAbstractItemView.NoSelection)
        form.addRow("Juniors:", self.juniorList)
        hint = qt.QLabel(
            "Check one or more juniors. A junior can be on several tasks."
        )
        hint.setWordWrap(True)
        hint.setStyleSheet(DIALOG_HINT_STYLE)
        form.addRow(hint)
        start_row = qt.QWidget()
        start_layout = qt.QHBoxLayout(start_row)
        start_layout.setContentsMargins(0, 0, 0, 0)
        start_layout.setSpacing(8)
        self.startVersionLabel = qt.QLabel("")
        self.startVersionLabel.setWordWrap(True)
        self.startVersionLabel.setMinimumHeight(32)
        self.startVersionLabel.setAlignment(qt.Qt.AlignVCenter | qt.Qt.AlignLeft)
        self.pickStartButton = qt.QPushButton("Choose on tree")
        self.pickStartButton.setStyleSheet(BTN_HISTORY)
        self.pickStartButton.setMinimumHeight(32)
        self.pickStartButton.connect("clicked()", self._onPickStartClicked)
        start_layout.addWidget(self.startVersionLabel, 1)
        start_layout.addWidget(self.pickStartButton, 0)
        form.addRow("Start version:", start_row)
        start_hint = qt.QLabel(
            "Required. Choose on tree — only already shared versions "
            "(solid border). Dashed = share that version first."
        )
        start_hint.setWordWrap(True)
        start_hint.setStyleSheet(DIALOG_HINT_STYLE)
        form.addRow(start_hint)
        self._refreshStartVersionUi()
        layout.addWidget(self.assignPanel)
        self.assignPanel.setVisible(self._can_assign)

        active_label = qt.QLabel("Tasks:")
        active_label.setStyleSheet(DIALOG_HINT_STYLE)
        layout.addWidget(active_label)
        legend = qt.QLabel(
            "🟠 In progress   ·   🔵 Submitted (awaiting review)   ·   ✅ Closed"
        )
        legend.setWordWrap(True)
        legend.setStyleSheet(DIALOG_HINT_STYLE)
        layout.addWidget(legend)
        self.taskList = qt.QListWidget()
        self.taskList.setMinimumHeight(200)
        self.taskList.setMaximumHeight(280)
        self.taskList.setSpacing(2)
        try:
            self.taskList.setWordWrap(True)
        except (TypeError, AttributeError, RuntimeError):
            pass
        self.taskList.setHorizontalScrollBarPolicy(qt.Qt.ScrollBarAlwaysOff)
        self.taskList.setSizePolicy(qt.QSizePolicy.Ignored, qt.QSizePolicy.Fixed)
        accent = ACCENT_ICE or "#5b9fd4"
        # Dark panel behind the cards so tasks stay readable in Light and Dark Slicer.
        self.taskList.setStyleSheet(
            """
            QListWidget {
                background: #1a1a1a;
                border: 1px solid #333333;
                border-radius: 8px;
                outline: none;
                padding: 4px;
                color: #e8e8e8;
            }
            QListWidget::item {
                margin: 1px 0px;
                padding: 6px 10px;
                border: 1px solid #3a3a3a;
                border-radius: 6px;
                background: #2a2a2a;
            }
            QListWidget::item:selected {
                border: 1px solid %s;
                background: #333333;
            }
            QListWidget::item:hover {
                border: 1px solid %s;
            }
            """
            % (accent, accent)
        )
        layout.addWidget(self.taskList)
        self.detailLabel = qt.QLabel("Double-click a task to read the full description.")
        self.detailLabel.setWordWrap(True)
        self.detailLabel.setStyleSheet(DIALOG_HINT_STYLE)
        layout.addWidget(self.detailLabel)

        self.statusLabel = qt.QLabel("")
        self.statusLabel.setWordWrap(True)
        self.statusLabel.setVisible(False)
        layout.addWidget(self.statusLabel)

        buttons = qt.QHBoxLayout()
        buttons.addStretch(1)
        closeButton = qt.QPushButton("Close")
        self.newTaskButton = qt.QPushButton("New task")
        self.cancelTaskButton = qt.QPushButton("Cancel task")
        self.updateTaskButton = qt.QPushButton("Update task")
        self.assignButton = qt.QPushButton("Assign")
        closeButton.setStyleSheet(BTN_SECONDARY)
        self.newTaskButton.setStyleSheet(BTN_SECONDARY)
        self.cancelTaskButton.setStyleSheet(BTN_DELETE)
        self.updateTaskButton.setStyleSheet(BTN_SAVE_VERSION)
        self.assignButton.setStyleSheet(BTN_CREATE)
        closeButton.connect("clicked()", self.reject)
        self.newTaskButton.connect("clicked()", self._onNewTaskClicked)
        self.cancelTaskButton.connect("clicked()", self._onCancelTaskClicked)
        self.updateTaskButton.connect("clicked()", self._onUpdateTaskClicked)
        self.assignButton.connect("clicked()", self._onAssignClicked)
        buttons.addWidget(closeButton)
        buttons.addWidget(self.newTaskButton)
        buttons.addWidget(self.cancelTaskButton)
        buttons.addWidget(self.updateTaskButton)
        buttons.addWidget(self.assignButton)
        layout.addLayout(buttons)
        self.assignButton.setVisible(self._can_assign)
        self.assignButton.setDefault(self._can_assign)
        self.updateTaskButton.setVisible(self._can_assign)
        self.newTaskButton.setVisible(self._can_assign)
        self.cancelTaskButton.setVisible(True)

        self.taskList.connect("currentRowChanged(int)", self._onTaskRowChanged)
        self.taskList.connect("itemDoubleClicked(QListWidgetItem*)", self._onTaskDoubleClicked)
        if self._can_assign:
            self._fillJuniorList()
            self.apply_draft(draft)
        self._fillTasks()
        self._updateDetail()
        self._updateActionButtons()

    def set_assign_handler(self, handler) -> None:
        self._assign_handler = handler

    def set_update_handler(self, handler) -> None:
        self._update_handler = handler

    def set_cancel_handler(self, handler) -> None:
        self._cancel_handler = handler

    def set_pick_start_handler(self, handler) -> None:
        self._pick_start_handler = handler

    def refresh_tasks(self, tasks=None) -> None:
        """Reload the task list after Assign / Update / Cancel (dialog stays open)."""
        self._all_tasks = [
            task for task in (tasks or []) if self._is_assigned_task(task)
        ]
        self._tasks = list(self._all_tasks)
        selected_id = str(getattr(self, "_editing_task_id", "") or "").strip()
        self._fillTasks()
        if selected_id:
            for index, task in enumerate(self._tasks):
                if str((task or {}).get("id") or "") == selected_id:
                    self.taskList.setCurrentRow(index)
                    break
        self._updateDetail()
        self._updateActionButtons()

    def apply_draft(self, draft) -> None:
        data = draft if isinstance(draft, dict) else {}
        text = str(data.get("description") or "")
        try:
            self.descriptionEdit.setPlainText(text)
        except (AttributeError, TypeError, RuntimeError):
            pass
        chosen = {
            str(name or "").strip().lower()
            for name in (data.get("juniors") or [])
            if str(name or "").strip()
        }
        if chosen:
            try:
                count = self.juniorList.count
                if callable(count):
                    count = count()
                count = int(count)
            except (TypeError, AttributeError, RuntimeError, ValueError):
                count = 0
            for index in range(count):
                item = self.juniorList.item(index)
                if item is None:
                    continue
                try:
                    login = str(item.data(qt.Qt.UserRole) or "").strip().lower()
                except (AttributeError, TypeError, RuntimeError):
                    login = ""
                if login and login in chosen:
                    item.setCheckState(qt.Qt.Checked)
        self.set_start_version(
            data.get("anchor_sha") or "",
            data.get("anchor_label") or "",
        )

    def set_start_version(self, sha: str, label: str) -> None:
        self._anchor_sha = str(sha or "").strip()
        self._anchor_label = str(label or "").strip()
        self._refreshStartVersionUi()

    def _refreshStartVersionUi(self) -> None:
        label = getattr(self, "startVersionLabel", None)
        if label is None:
            return
        accent = ACCENT_ICE or "#5b9fd4"
        muted = TEXT_MUTED or "#8a8a8a"
        border = BORDER or "#505050"
        if self._anchor_label:
            label.setText(self._anchor_label)
            label.setStyleSheet(
                "QLabel {"
                " background-color: palette(base);"
                " color: %s;"
                " border: 1px solid %s;"
                " border-radius: 6px;"
                " padding: 6px 10px;"
                " font-weight: 700;"
                " font-size: 12px;"
                "}"
                % (accent, accent)
            )
        else:
            label.setText("No start version yet")
            label.setStyleSheet(
                "QLabel {"
                " background-color: palette(window);"
                " color: %s;"
                " border: 1px dashed %s;"
                " border-radius: 6px;"
                " padding: 6px 10px;"
                " font-weight: 600;"
                " font-size: 11px;"
                "}"
                % (muted, border)
            )

    def selected_start_version(self) -> tuple[str, str]:
        return (str(self._anchor_sha or "").strip(), str(self._anchor_label or "").strip())

    def _onPickStartClicked(self) -> None:
        handler = self._pick_start_handler
        if handler is None:
            self.set_status("Could not open the Version tree.", error=True)
            return
        self.set_status("Click a shared version in the Version tree…")
        handler(self)

    def set_status(self, message: str, error: bool = False) -> None:
        text = (message or "").strip()
        self.statusLabel.setText(text)
        self.statusLabel.setVisible(bool(text))
        if not text:
            return
        color = FEED_COLOR_ERROR if error else ACCENT_MINT
        self.statusLabel.setStyleSheet("color: %s; font-size: 11px; font-weight: 600;" % color)

    def selected_juniors(self) -> list[str]:
        names = []
        try:
            count = self.juniorList.count
            if callable(count):
                count = count()
            count = int(count)
        except (TypeError, AttributeError, RuntimeError, ValueError):
            count = 0
        for index in range(count):
            item = self.juniorList.item(index)
            if item is None:
                continue
            try:
                checked = item.checkState() == qt.Qt.Checked
            except (AttributeError, TypeError, RuntimeError):
                checked = False
            if not checked:
                continue
            try:
                login = str(item.data(qt.Qt.UserRole) or "").strip()
            except (AttributeError, TypeError, RuntimeError):
                login = ""
            if not login:
                try:
                    text = item.text()
                    if callable(text):
                        text = text()
                    login = str(text or "").strip()
                except (AttributeError, TypeError, RuntimeError):
                    login = ""
            if login and login != "No junior on this project":
                names.append(login)
        return names

    def task_description(self) -> str:
        try:
            text = self.descriptionEdit.toPlainText()
            if callable(text):
                text = text()
        except (TypeError, AttributeError, RuntimeError):
            text = ""
        return normalize_task_title(text)

    def selected_task(self):
        row = self.taskList.currentRow
        if callable(row):
            row = row()
        row = int(row)
        if row < 0 or row >= len(self._tasks):
            return None
        return self._tasks[row]

    @staticmethod
    def _is_assigned_task(task: dict) -> bool:
        kind = str((task or {}).get("kind") or "").strip().lower()
        if kind == "voluntary":
            return False
        if kind == "assigned":
            return True
        # Legacy rows without kind: keep only if a senior is set.
        return bool(str((task or {}).get("senior") or "").strip())

    def _fillJuniorList(self) -> None:
        juniors = []
        for person in self._people:
            login = str(person.get("login") or "").strip()
            role = str(person.get("role") or "")
            if not login or role in ("pending", "owner"):
                continue
            access = str(person.get("access") or PEOPLE_ACCESS_JUNIOR)
            if access == PEOPLE_ACCESS_JUNIOR:
                juniors.append(login)
        self.juniorList.clear()
        if juniors:
            for login in juniors:
                item = qt.QListWidgetItem(login)
                item.setFlags(
                    item.flags()
                    | qt.Qt.ItemIsUserCheckable
                    | qt.Qt.ItemIsEnabled
                )
                item.setFlags(item.flags() & ~qt.Qt.ItemIsSelectable)
                item.setData(qt.Qt.UserRole, login)
                item.setCheckState(qt.Qt.Unchecked)
                self.juniorList.addItem(item)
            self.assignButton.setEnabled(True)
        else:
            item = qt.QListWidgetItem("No junior on this project")
            item.setFlags(qt.Qt.NoItemFlags)
            self.juniorList.addItem(item)
            self.assignButton.setEnabled(False)

    def _isMyActiveTask(self, task: dict) -> bool:
        if self._can_assign:
            return False
        me = self._me.lower()
        if not me:
            return False
        if str(task.get("status") or "") == "accepted":
            return False
        return me in {name.lower() for name in _task_junior_logins(task)}

    def _task_list_label(self, task: dict) -> str:
        juniors = _task_juniors_label(task)
        senior = str(task.get("senior") or "").strip()
        excerpt = _task_excerpt(task.get("description") or "") or "No description."
        mark = _task_status_mark(task)
        start = str(task.get("anchor_label") or "").strip()
        if start:
            label = "%s  %s -> %s · %s : %s" % (mark, senior, juniors, start, excerpt)
        else:
            label = "%s  %s -> %s : %s" % (mark, senior, juniors, excerpt)
        if self._isMyActiveTask(task):
            return "● Your task — %s" % label
        return label

    def _emptyTasksMessage(self) -> str:
        if self._can_assign:
            return "No task yet."
        if self._is_senior:
            return "No task yet. Assign needs Connect with GitHub."
        return "No task yet. Wait for a senior to assign one."

    def _fillTasks(self) -> None:
        self.taskList.clear()
        if not self._tasks:
            self.taskList.addItem(self._emptyTasksMessage())
            return
        mine_row = -1
        accent = qt.QColor(ACCENT_ICE or "#5b9fd4")
        for index, task in enumerate(self._tasks):
            item = qt.QListWidgetItem(self._task_list_label(task))
            if self._isMyActiveTask(task):
                mine_row = index
                try:
                    font = item.font()
                    font.setBold(True)
                    item.setFont(font)
                    item.setForeground(accent)
                except (AttributeError, TypeError, RuntimeError):
                    pass
            self.taskList.addItem(item)
        if mine_row >= 0:
            self.taskList.setCurrentRow(mine_row)
        else:
            self.taskList.clearSelection()
            self.taskList.setCurrentRow(-1)

    def _canCancelSelected(self) -> bool:
        task = self.selected_task()
        if not task:
            return False
        if str(task.get("status") or "") == "accepted":
            return False
        me = self._me.lower()
        if not me or not self._can_assign:
            return False
        senior = str(task.get("senior") or "").strip().lower()
        return bool(senior) and me == senior

    def _canUpdateSelected(self) -> bool:
        """Same gate as Cancel: senior who owns the open (not closed) task."""
        return self._canCancelSelected()

    def _setJuniorChecks(self, logins) -> None:
        chosen = {
            str(name or "").strip().lower()
            for name in (logins or [])
            if str(name or "").strip()
        }
        try:
            count = self.juniorList.count
            if callable(count):
                count = count()
            count = int(count)
        except (TypeError, AttributeError, RuntimeError, ValueError):
            count = 0
        for index in range(count):
            item = self.juniorList.item(index)
            if item is None:
                continue
            try:
                login = str(item.data(qt.Qt.UserRole) or "").strip().lower()
            except (AttributeError, TypeError, RuntimeError):
                login = ""
            try:
                item.setCheckState(
                    qt.Qt.Checked if login and login in chosen else qt.Qt.Unchecked
                )
            except (AttributeError, TypeError, RuntimeError):
                pass

    def _loadTaskIntoForm(self, task: dict) -> None:
        if not self._can_assign:
            return
        self._editing_task_id = str((task or {}).get("id") or "").strip()
        try:
            self.descriptionEdit.setPlainText(
                str((task or {}).get("description") or "")
            )
        except (AttributeError, TypeError, RuntimeError):
            pass
        self._setJuniorChecks(_task_junior_logins(task))
        self.set_start_version(
            (task or {}).get("anchor_sha") or "",
            (task or {}).get("anchor_label") or "",
        )
        try:
            self.pickStartButton.setEnabled(False)
            self.pickStartButton.setToolTip(
                "Start version is fixed for an existing task."
            )
        except (AttributeError, RuntimeError, TypeError):
            pass

    def _clearFormForNewAssign(self) -> None:
        if not self._can_assign:
            return
        self._editing_task_id = ""
        try:
            self.descriptionEdit.setPlainText("")
        except (AttributeError, TypeError, RuntimeError):
            pass
        self._setJuniorChecks([])
        self.set_start_version("", "")
        try:
            self.pickStartButton.setEnabled(True)
            self.pickStartButton.setToolTip("")
        except (AttributeError, RuntimeError, TypeError):
            pass

    def _onTaskRowChanged(self, _row) -> None:
        if self._can_assign:
            task = self.selected_task()
            if task and self._canUpdateSelected():
                self._loadTaskIntoForm(task)
            else:
                # Other senior's / closed / no row: do not keep a half-loaded edit form.
                self._clearFormForNewAssign()
        self._updateDetail()
        self._updateActionButtons()

    def _onNewTaskClicked(self) -> None:
        """Leave Update mode — empty form + Assign for a brand-new task."""
        try:
            self.taskList.clearSelection()
            self.taskList.setCurrentRow(-1)
        except (AttributeError, RuntimeError, TypeError):
            pass
        self._clearFormForNewAssign()
        self._updateDetail()
        self._updateActionButtons()
        self.set_status("New task — choose juniors, description, and start version.")

    def _updateDetail(self) -> None:
        if self._can_assign and self._canUpdateSelected():
            self.detailLabel.setText(
                "Selected task — edit juniors / description, then Update task. "
                "Start version stays fixed. New task clears the form. "
                "Double-click to read the full text."
            )
            self.detailLabel.setVisible(True)
            return
        double_click = "Double-click a task to read the full description."
        if self._can_assign:
            self.detailLabel.setText(
                "Select one of your tasks to update it, or Assign a new one. "
                + double_click
            )
            self.detailLabel.setVisible(True)
            return
        if self._tasks:
            self.detailLabel.setText(double_click)
        else:
            self.detailLabel.setText(self._emptyTasksMessage())
        self.detailLabel.setVisible(True)

    def _task_at_row(self, row) -> dict | None:
        try:
            row = int(row)
        except (TypeError, ValueError):
            return None
        if row < 0 or row >= len(self._tasks):
            return None
        return self._tasks[row]

    def _onTaskDoubleClicked(self, item) -> None:
        row = -1
        try:
            row = self.taskList.row(item)
        except (TypeError, AttributeError, RuntimeError):
            row = -1
        task = self._task_at_row(row) or self.selected_task()
        if not task:
            return
        qt.QTimer.singleShot(0, lambda chosen=task: self._showTaskText(chosen))

    def _showTaskText(self, task) -> None:
        senior = str(task.get("senior") or "").strip()
        juniors = _task_juniors_label(task)
        description = str(task.get("description") or "").strip() or "No description."
        start = str(task.get("anchor_label") or "").strip()
        dialog = qt.QDialog(self)
        dialog.setWindowTitle("Task")
        dialog.setFixedWidth(420)
        dialog.setModal(True)
        layout = qt.QVBoxLayout(dialog)
        status_line = qt.QLabel(
            "%s  %s" % (_task_status_mark(task), _task_status_label(task))
        )
        status_line.setWordWrap(True)
        status_line.setStyleSheet(DIALOG_HINT_STYLE)
        layout.addWidget(status_line)
        title = qt.QLabel("%s assigned %s to this task." % (senior, juniors))
        title.setWordWrap(True)
        title.setStyleSheet(DIALOG_HINT_STYLE)
        layout.addWidget(title)
        if start:
            start_line = qt.QLabel("Start version: %s" % start)
            start_line.setWordWrap(True)
            start_line.setStyleSheet(DIALOG_HINT_STYLE)
            layout.addWidget(start_line)
        branch = str(task.get("branch_slug") or "").strip()
        if branch:
            branch_line = qt.QLabel("Task branch: %s" % branch)
            branch_line.setWordWrap(True)
            branch_line.setStyleSheet(DIALOG_HINT_STYLE)
            layout.addWidget(branch_line)
        body = qt.QPlainTextEdit()
        body.setReadOnly(True)
        body.setPlainText(description)
        body.setLineWrapMode(qt.QPlainTextEdit.WidgetWidth)
        body.setFixedHeight(160)
        body.setSizePolicy(qt.QSizePolicy.Ignored, qt.QSizePolicy.Fixed)
        body.setStyleSheet(FIELD_STYLE)
        layout.addWidget(body)
        closeButton = qt.QPushButton("Close")
        closeButton.setStyleSheet(BTN_SECONDARY)
        closeButton.connect("clicked()", dialog.accept)
        layout.addWidget(closeButton)
        dialog.exec_()

    def _updateActionButtons(self) -> None:
        can_update = self._canUpdateSelected()
        self.cancelTaskButton.setEnabled(self._canCancelSelected())
        self.updateTaskButton.setEnabled(can_update)
        self.updateTaskButton.setVisible(self._can_assign)
        if getattr(self, "newTaskButton", None) is not None:
            self.newTaskButton.setVisible(self._can_assign)
            # Useful mainly while editing an existing task.
            self.newTaskButton.setEnabled(self._can_assign and can_update)
        # Assign = new task only (when not editing a selected one).
        if self._can_assign:
            self.assignButton.setVisible(not can_update)
            self.assignButton.setEnabled(not can_update)
            self.assignButton.setDefault(not can_update)
            self.updateTaskButton.setDefault(can_update)

    def _onAssignClicked(self) -> None:
        if self._canUpdateSelected():
            self.set_status("This task is selected — use Update task.", error=True)
            return
        juniors = self.selected_juniors()
        if not juniors:
            self.set_status("Select at least one junior.", error=True)
            return
        description = self.task_description()
        if not description:
            self.set_status("Write a short description first.", error=True)
            return
        anchor_sha, anchor_label = self.selected_start_version()
        if not anchor_sha or not anchor_label:
            self.set_status("Choose a start version on the Version tree first.", error=True)
            return
        handler = self._assign_handler
        if handler is not None:
            handler(self, juniors, description, anchor_sha, anchor_label)

    def _onUpdateTaskClicked(self) -> None:
        task = self.selected_task()
        if not task or not self._canUpdateSelected():
            self.set_status("Select one of your open tasks first.", error=True)
            return
        juniors = self.selected_juniors()
        if not juniors:
            self.set_status("Keep at least one junior on the task.", error=True)
            return
        description = self.task_description()
        if not description:
            self.set_status("Write a short description first.", error=True)
            return
        handler = self._update_handler
        if handler is not None:
            handler(self, task, juniors, description)

    def _onCancelTaskClicked(self) -> None:
        task = self.selected_task()
        if not task or not self._canCancelSelected():
            self.set_status("Select a task first.", error=True)
            return
        handler = self._cancel_handler
        if handler is not None:
            handler(self, task)


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
        self._pending_versions_behind_hint = False
        self._ontology_document = None
        self._ontology_preset_ids = [preset_id for preset_id, _label in preset_choices()]
        self._connected = False
        self._local_mode = False
        self._loaded_project_name = None
        self._local_project_path = None
        # MRML node IDs loaded for the open CV project (scene only — not project files).
        self._project_scene_node_ids = []
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
        self._local_project_people = []
        self._notifications = []
        self._notification_invites = []
        self._notification_activity = []
        self._notificationsTimer = None
        self._refreshing_notifications = False
        self._notificationsProcess = None
        self._notificationFetchQueue = []
        self._notificationFetchResults = []
        self._notificationFetchAnnounce = False
        self._notificationFetchKind = ""
        self._notificationFetchProject = ""
        self._invite_read_ids = set()
        self._reads_by_project = {}
        self._project_reads = {}
        self._messageSendActivity = []
        self._messageSendReads = {}
        self._messageSendPresence = {}
        self._project_presence = {}
        self._presence_last_publish_mono = 0.0
        self._people_dialog_open = False
        self._task_dialog_open = False
        self._open_task_dialog = None
        self._task_anchor_picking = False
        self._task_anchor_pick_done = False
        self._notifications_popup_open = False
        self._ontology_graph_pending = False
        self._messages = []
        self._project_tasks = []
        self._project_activity = []
        self._messagesTimer = None
        self._refreshing_messages = False
        self._sending_message = False
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
        self._messageSendTasks = []
        # Parked chat while combo is not on the open project (None / other).
        self._open_project_chat_stash = None

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
        self._local_mode = False
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
        self.notificationsBehindBadge = qt.QLabel(self.notificationsBell)
        self.notificationsBehindBadge.setAlignment(qt.Qt.AlignCenter)
        self.notificationsBehindBadge.setFixedSize(16, 16)
        self.notificationsBehindBadge.move(20, 16)
        self.notificationsBehindBadge.setText("⚠")
        self.notificationsBehindBadge.setToolTip(
            "Local project is not aligned with the remote copy"
        )
        self.notificationsBehindBadge.setStyleSheet(
            "QLabel { background: transparent; color: #f59e0b; font-size: 13px; border: none; }"
        )
        try:
            self.notificationsBehindBadge.setAttribute(
                qt.Qt.WA_TransparentForMouseEvents, True
            )
        except (AttributeError, TypeError, RuntimeError):
            pass
        self.notificationsBehindBadge.hide()
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
        ontologyRow = qt.QHBoxLayout(ontologyPanel)
        ontologyRow.setContentsMargins(0, 0, 0, 0)
        ontologyRow.setSpacing(4)

        self.ontologyPresetCombo = qt.QComboBox()
        self.ontologyPresetCombo.addItem(ONTOLOGY_COMBO_NONE_LABEL)
        for _preset_id, label in preset_choices():
            self.ontologyPresetCombo.addItem(label)
        self.ontologyPresetCombo.setStyleSheet(FIELD_STYLE)
        self._makeComboShrinkable(self.ontologyPresetCombo)
        self.ontologyPresetCombo.setCurrentIndex(ONTOLOGY_COMBO_NONE_INDEX)
        ontologyRow.addWidget(self.ontologyPresetCombo, 1)

        # One gear menu instead of four separate Help / Load / Edit / Export buttons.
        self.ontologyMenuButton = qt.QToolButton()
        self.ontologyMenuButton.setText("⚙")
        self.ontologyMenuButton.setToolTip("Ontology options")
        self.ontologyMenuButton.setPopupMode(qt.QToolButton.InstantPopup)
        self.ontologyMenuButton.setAutoRaise(True)
        self.ontologyMenuButton.setStyleSheet(
            "QToolButton { font-size: 14px; padding: 2px 6px; border: 1px solid palette(mid); "
            "border-radius: 4px; }"
            "QToolButton::menu-indicator { image: none; width: 0; }"
            "QToolButton:hover { border-color: %s; }" % (ACCENT_ICE or "#5b9fd4")
        )
        ontologyMenu = qt.QMenu(self.ontologyMenuButton)
        self.ontologyHelpAction = ontologyMenu.addAction("Help…")
        self.ontologyLoadAction = ontologyMenu.addAction("Load JSON…")
        self.ontologyEditAction = ontologyMenu.addAction("Edit…")
        self.ontologyExportAction = ontologyMenu.addAction("Export JSON…")
        self.ontologyMenuButton.setMenu(ontologyMenu)
        ontologyRow.addWidget(self.ontologyMenuButton, 0)

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
        self.saveVersionButton.setToolTip(
            "Save a version locally (on main or another branch)"
        )
        self.shareButton.setToolTip(
            "Publish the current branch to the shared project"
        )
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
        self.ontologyHelpAction.connect("triggered()", self.onOntologyJsonHelp)
        self.ontologyLoadAction.connect("triggered()", self.onLoadOntologyJson)
        self.ontologyEditAction.connect("triggered()", self.onEditOntology)
        self.ontologyExportAction.connect("triggered()", self.onExportOntologyJson)
        self.createButton.connect("clicked()", self.onCreateProject)
        self.openButton.connect("clicked()", self.onOpenProject)
        self.saveVersionButton.connect("clicked()", self.onSaveVersion)
        self.shareButton.connect("clicked()", self.onShare)
        self.peopleButton.connect("clicked()", self.onPeople)
        self.deleteButton.connect("clicked()", self.onDeleteProject)
        self.messagesSend.connect("clicked()", self._onSendMessage)
        self.messagesInput.connect("returnPressed()", self._onSendMessage)
        self.messagesTaskButton.connect("clicked()", self.onOpenTask)
        self.volumeSelector.connect("currentNodeChanged(vtkMRMLNode*)", self._onVolumeAssetChanged)
        self.segmentationSelector.connect("currentNodeChanged(vtkMRMLNode*)", self._onSegmentationAssetChanged)

    def _buildMessagesSection(self) -> None:
        self.messagesTaskButton = qt.QPushButton("Tasks")
        self.messagesTaskButton.setStyleSheet(BTN_SECONDARY)
        self.messagesTaskButton.setMinimumHeight(32)
        self.messagesTaskButton.setSizePolicy(qt.QSizePolicy.Expanding, qt.QSizePolicy.Fixed)
        self.messagesTaskButton.setEnabled(False)
        self.messagesTaskButton.setToolTip("Connect with GitHub first.")
        self.layout.addWidget(self.messagesTaskButton)
        self.taskBadge = qt.QLabel(self.messagesTaskButton)
        self.taskBadge.setAlignment(qt.Qt.AlignCenter)
        self.taskBadge.setFixedSize(16, 16)
        self.taskBadge.setStyleSheet(NOTIFICATIONS_BADGE_STYLE)
        try:
            self.taskBadge.setAttribute(qt.Qt.WA_TransparentForMouseEvents, True)
        except (AttributeError, TypeError, RuntimeError):
            pass
        self.taskBadge.hide()

        messagesButton = qt.QPushButton("Messages")
        messagesButton.setCheckable(True)
        messagesButton.setChecked(False)
        messagesButton.setAutoDefault(False)
        messagesButton.setDefault(False)
        try:
            messagesButton.setFocusPolicy(qt.Qt.NoFocus)
        except (AttributeError, TypeError, RuntimeError):
            pass
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

        self.messagesPresenceLabel = qt.QLabel("")
        self.messagesPresenceLabel.setWordWrap(True)
        self.messagesPresenceLabel.setStyleSheet(DIALOG_HINT_STYLE)
        self.messagesPresenceLabel.setVisible(False)

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

        messagesLayout.addWidget(self.messagesPresenceLabel)
        messagesLayout.addWidget(self.messagesView)
        messagesLayout.addWidget(compose)
        messagesBody.hide()
        self.layout.addWidget(messagesBody)

        self._renderMessagesView()
        self._setMessagesComposerEnabled(False)
        self._updateTaskButtonUi()
        messagesButton.connect("toggled(bool)", self._onMessagesToggled)
        qt.QTimer.singleShot(0, self._positionMessagesBadge)
        qt.QTimer.singleShot(0, self._positionTaskBadge)

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

    def _alignProjectAssetNodeNames(self, volume_node, segmentation_node, project_name: str) -> None:
        """Rename MRML nodes to match project file stems (scene only — never renames disk sources)."""
        stem = self._projectFileStem(project_name)
        volume_name = "%s_volume" % stem
        segmentation_name = "%s_segmentation" % stem
        try:
            if volume_node is not None and hasattr(volume_node, "SetName"):
                if str(volume_node.GetName() or "") != volume_name:
                    volume_node.SetName(volume_name)
            if segmentation_node is not None and hasattr(segmentation_node, "SetName"):
                if str(segmentation_node.GetName() or "") != segmentation_name:
                    segmentation_node.SetName(segmentation_name)
        except (AttributeError, RuntimeError, TypeError, ValueError):
            logging.exception("Could not align project asset node names")

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
        if not self._hasWorkspaceSession() or self._suppress_asset_ui_updates > 0:
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

    def _hideLoadedProjectAssetFields(self) -> None:
        """Clear asset selectors only — keep scene nodes + ontology stash for restore."""
        self._suppress_dirty += 1
        self._suppress_asset_ui_updates += 1
        self._blockProjectAssetSignals(True)
        try:
            if _qt_widget_is_valid(getattr(self, "volumeSelector", None)):
                self.volumeSelector.setCurrentNode(None)
            if _qt_widget_is_valid(getattr(self, "segmentationSelector", None)):
                self.segmentationSelector.setCurrentNode(None)
            # Working ontology for UI only; keep _project_ontology_* for the open project.
            self._ontology_document = None
            if self.logic and getattr(self.logic, "_dependencyCanvas", None):
                self.logic._dependencyCanvas.set_specs(
                    [],
                    graph_title="Ontology",
                    graph_description="Open the selected project to load assets.",
                    painted_ids=[],
                )
            # Drop the open-project ontology row from the combo so it cannot be
            # re-selected while browsing another project — stash path/doc stays.
            combo = getattr(self, "ontologyPresetCombo", None)
            idx = int(getattr(self, "_ontology_server_combo_index", -1) or -1)
            if _qt_widget_is_valid(combo) and idx >= 0:
                combo.blockSignals(True)
                try:
                    if idx < _qt_combo_count(combo):
                        combo.removeItem(idx)
                    self._ontology_server_combo_index = -1
                finally:
                    combo.blockSignals(False)
            self._setOntologyComboNone()
        finally:
            self._blockProjectAssetSignals(False)
            self._suppress_asset_ui_updates -= 1
            self._suppress_dirty -= 1

    def _restoreLoadedProjectAssetFields(self) -> None:
        """Put back volume / segmentation / ontology for the project still in the scene."""
        self._suppress_dirty += 1
        self._suppress_asset_ui_updates += 1
        self._blockProjectAssetSignals(True)
        try:
            scene = slicer.mrmlScene
            volume_node = None
            segmentation_node = None
            for node_id in list(getattr(self, "_project_scene_node_ids", None) or []):
                try:
                    node = scene.GetNodeByID(node_id) if node_id else None
                except (AttributeError, RuntimeError, TypeError, ValueError):
                    node = None
                if node is None:
                    continue
                try:
                    class_name = str(node.GetClassName() or "")
                except (AttributeError, RuntimeError, TypeError, ValueError):
                    class_name = ""
                if "Segmentation" in class_name or "LabelMap" in class_name:
                    segmentation_node = node
                else:
                    volume_node = node
            if _qt_widget_is_valid(getattr(self, "volumeSelector", None)):
                self.volumeSelector.setCurrentNode(volume_node)
            if _qt_widget_is_valid(getattr(self, "segmentationSelector", None)):
                self.segmentationSelector.setCurrentNode(segmentation_node)
            document = getattr(self, "_project_ontology_document", None)
            path = getattr(self, "_project_ontology_path", None)
            if document is None and path and os.path.isfile(path):
                try:
                    document = load_ontology_file(path)
                    self._project_ontology_document = document
                except (OSError, ValueError):
                    document = None
            if path and getattr(self, "_ontology_server_combo_index", -1) < 0:
                self._setOntologyComboLoadedFilename(
                    document=document, filename=path
                )
            elif getattr(self, "_ontology_server_combo_index", -1) >= 0:
                combo = getattr(self, "ontologyPresetCombo", None)
                if _qt_widget_is_valid(combo):
                    combo.blockSignals(True)
                    try:
                        combo.setCurrentIndex(self._ontology_server_combo_index)
                    finally:
                        combo.blockSignals(False)
            if document is not None:
                self._ontology_document = document
                self._applyOntologyGraph(document)
                self._updateRightDockAvailability()
            else:
                self._ontology_document = None
        finally:
            self._blockProjectAssetSignals(False)
            self._suppress_asset_ui_updates -= 1
            self._suppress_dirty -= 1

    def _parkOpenProjectChatUi(self) -> None:
        """Hide messages + project activity notifs so they are not mistaken for the selection."""
        open_name = str(getattr(self, "_loaded_project_name", None) or "").strip()
        if not open_name:
            return
        stash = getattr(self, "_open_project_chat_stash", None)
        if not isinstance(stash, dict) or str(stash.get("project") or "").lower() != open_name.lower():
            self._open_project_chat_stash = {
                "project": open_name,
                "messages": list(getattr(self, "_messages", None) or []),
                "tasks": list(getattr(self, "_project_tasks", None) or []),
                "activity": list(getattr(self, "_project_activity", None) or []),
                "reads": dict(getattr(self, "_project_reads", None) or {}),
                "presence": dict(getattr(self, "_project_presence", None) or {}),
                "messages_unread": int(getattr(self, "_messages_unread", 0) or 0),
                "messages_project": str(getattr(self, "_messages_project", "") or ""),
                "notification_activity": list(
                    getattr(self, "_notification_activity", None) or []
                ),
            }
        self._stopMessagesPolling()
        self._messages = []
        self._project_tasks = []
        self._project_activity = []
        self._project_reads = {}
        self._project_presence = {}
        self._messages_unread = 0
        self._messages_project = ""
        self._notification_activity = []
        self._rebuildNotificationsDisplay()
        self._renderMessagesView()
        self._updateMessagesPresenceBanner()
        self._updateMessagesBadge()
        self._updateTaskButtonUi()
        self._setMessagesComposerEnabled(False)

    def _restoreParkedOpenProjectChatUi(self) -> None:
        """Put back parked messages / project activity when the open project is selected again."""
        open_name = str(getattr(self, "_loaded_project_name", None) or "").strip()
        stash = getattr(self, "_open_project_chat_stash", None)
        if not open_name or not isinstance(stash, dict):
            return
        if str(stash.get("project") or "").lower() != open_name.lower():
            return
        self._messages = list(stash.get("messages") or [])
        self._project_tasks = list(stash.get("tasks") or [])
        self._project_activity = list(stash.get("activity") or [])
        self._project_reads = dict(stash.get("reads") or {})
        self._project_presence = dict(stash.get("presence") or {})
        self._messages_unread = int(stash.get("messages_unread") or 0)
        self._messages_project = str(stash.get("messages_project") or open_name)
        self._notification_activity = list(stash.get("notification_activity") or [])
        self._open_project_chat_stash = None
        self._rebuildNotificationsDisplay()
        self._renderMessagesView()
        self._updateMessagesPresenceBanner()
        self._updateMessagesBadge()
        self._updateTaskButtonUi()

    def _syncAssetFieldsToProjectSelection(self) -> None:
        """Selectors + chat follow the combo; restored only for the open project."""
        loaded = str(getattr(self, "_loaded_project_name", None) or "").strip()
        if not loaded:
            return
        selected = self._currentProjectName() if self._hasSelectedProject() else ""
        if selected and selected.lower() == loaded.lower():
            self._restoreLoadedProjectAssetFields()
            self._restoreParkedOpenProjectChatUi()
        else:
            self._hideLoadedProjectAssetFields()
            self._parkOpenProjectChatUi()

    def _rememberProjectSceneNodes(self, volume_node=None, segmentation_node=None) -> None:
        """Track which scene nodes belong to the open CV project (for later unload).

        Order is segmentation then volume so unload can drop the seg first.
        """
        ids = []
        seen = set()
        for node in (segmentation_node, volume_node):
            if node is None or not hasattr(node, "GetID"):
                continue
            try:
                node_id = str(node.GetID() or "").strip()
            except (AttributeError, RuntimeError, TypeError, ValueError):
                continue
            if not node_id or node_id in seen:
                continue
            seen.add(node_id)
            ids.append(node_id)
        self._project_scene_node_ids = ids

    def _projectSceneNodesToUnload(self) -> list:
        """MRML nodes from the open project only — never unrelated Slicer data.

        Segmentation is listed before volume.
        """
        scene = slicer.mrmlScene
        nodes = []
        seen = set()

        def _append(node) -> None:
            if node is None:
                return
            try:
                current_id = str(node.GetID() or "")
            except (AttributeError, RuntimeError, TypeError, ValueError):
                return
            if current_id and current_id not in seen:
                seen.add(current_id)
                nodes.append(node)

        for node_id in list(getattr(self, "_project_scene_node_ids", None) or []):
            try:
                node = scene.GetNodeByID(node_id) if node_id else None
            except (AttributeError, RuntimeError, TypeError, ValueError):
                node = None
            _append(node)
        # Fallback if IDs were not tracked (e.g. session started before this feature).
        if not nodes and (
            getattr(self, "_loaded_project_name", None)
            or getattr(self, "_local_project_path", None)
        ):
            for selector_name in ("segmentationSelector", "volumeSelector"):
                _append(self._selectorCurrentNode(selector_name))
        # Prefer segmentation before volume even if stored order was wrong.
        def _unload_rank(node) -> int:
            try:
                class_name = str(node.GetClassName() or "")
            except (AttributeError, RuntimeError, TypeError, ValueError):
                class_name = ""
            if "Segmentation" in class_name:
                return 0
            if "LabelMap" in class_name:
                return 1
            return 2

        nodes.sort(key=_unload_rank)
        return nodes

    def _unloadProjectSceneNodes(self) -> int:
        """Remove open-project data from the Slicer scene only (segmentation, then volume).

        Local/remote project files on disk or GitHub are left untouched.
        Returns how many nodes were removed.
        """
        nodes = self._projectSceneNodesToUnload()
        self._suppress_dirty += 1
        self._suppress_asset_ui_updates += 1
        self._blockProjectAssetSignals(True)
        removed = 0
        try:
            if _qt_widget_is_valid(getattr(self, "segmentationSelector", None)):
                self.segmentationSelector.setCurrentNode(None)
            if _qt_widget_is_valid(getattr(self, "volumeSelector", None)):
                self.volumeSelector.setCurrentNode(None)
            scene = slicer.mrmlScene
            for node in nodes:
                try:
                    scene.RemoveNode(node)
                    removed += 1
                    slicer.app.processEvents()
                except (AttributeError, RuntimeError, TypeError, ValueError):
                    logging.exception("Could not unload a project scene node")
            self._project_scene_node_ids = []
            self._clearOntologyDocument()
            self._removeServerOntologyComboEntry()
            self._setOntologyComboNone()
        finally:
            self._blockProjectAssetSignals(False)
            self._suppress_asset_ui_updates -= 1
            self._suppress_dirty -= 1
        return removed

    def _setProjectAssetFieldsEnabled(self, enabled: bool) -> None:
        self.volumeSelector.setEnabled(enabled)
        self.segmentationSelector.setEnabled(enabled)
        self.ontologyPresetCombo.setEnabled(enabled)
        menu_btn = getattr(self, "ontologyMenuButton", None)
        if menu_btn is not None:
            menu_btn.setEnabled(True)
        # Help stays available; Load / Edit / Export follow the project section.
        help_action = getattr(self, "ontologyHelpAction", None)
        if help_action is not None:
            help_action.setEnabled(True)
        for name in ("ontologyLoadAction", "ontologyEditAction", "ontologyExportAction"):
            action = getattr(self, name, None)
            if action is not None:
                action.setEnabled(bool(enabled))

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
        self.historyTableWidget.setColumnCount(4)
        self.historyTableWidget.setHorizontalHeaderLabels(["Version", "Date", "Author", "Message"])
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

    def _promptSwitchVersion(self, version_id: str) -> bool:
        box = qt.QMessageBox(slicer.util.mainWindow())
        box.setWindowTitle("Switch version")
        box.setText("Switch to %s?" % self._versionDisplayTag(version_id))
        info = "Click Save first if you want to keep your current work."
        if self._isVersionWriteLocked(version_id):
            info = (
                "You can view this version, but you can't Save or Share from here "
                "(🔒 view only).\n\n"
                "To work, switch to your task branch (nodes without a lock).\n\n"
                "Click Save first if you want to keep your current work."
            )
        box.setInformativeText(info)
        switch_btn = box.addButton("Switch version", qt.QMessageBox.AcceptRole)
        cancel_btn = box.addButton("Cancel", qt.QMessageBox.RejectRole)
        box.setDefaultButton(cancel_btn)
        box.exec_()
        return box.clickedButton() == switch_btn

    def _promptSaveDestination(
        self,
        from_older_main: bool = False,
        junior: bool = False,
    ) -> str:
        """When saving from main: Put on main / Create a branch / cancel.

        Juniors never get Put on main (they can only Share a branch).
        Older-main view: only Create a branch so later unshared main tips stay.
        """
        box = qt.QMessageBox(slicer.util.mainWindow())
        box.setWindowTitle("Save version")
        if junior or from_older_main:
            if junior and from_older_main:
                box.setText("Save from this older main version?")
                box.setInformativeText(
                    "As a junior you save on a branch (not on main).\n"
                    "Main still has later versions on this computer — "
                    "Create a branch from here; those later main versions stay."
                )
            elif junior:
                box.setText("Save on a branch?")
                box.setInformativeText(
                    "As a junior you save on a branch (not on main).\n"
                    "Create a branch to save this version."
                )
            else:
                box.setText("Save from this older main version?")
                box.setInformativeText(
                    "Main still has later versions on this computer.\n"
                    "Create a branch from here — those later main versions stay."
                )
            branch_btn = box.addButton("Create a branch", qt.QMessageBox.AcceptRole)
            box.addButton("Cancel", qt.QMessageBox.RejectRole)
            box.setDefaultButton(branch_btn)
            box.exec_()
            return "branch" if box.clickedButton() == branch_btn else "cancel"
        box.setText("Where should this version be saved?")
        box.setInformativeText(
            "Put on main — save on main.\n"
            "Create a branch — create a new branch and save your changes there."
        )
        main_btn = box.addButton("Put on main", qt.QMessageBox.AcceptRole)
        branch_btn = box.addButton("Create a branch", qt.QMessageBox.ActionRole)
        box.addButton("Cancel", qt.QMessageBox.RejectRole)
        box.setDefaultButton(main_btn)
        box.exec_()
        clicked = box.clickedButton()
        if clicked == main_btn:
            return "main"
        if clicked == branch_btn:
            return "branch"
        return "cancel"

    def _promptBranchName(self) -> str:
        """Ask for a branch name (Create a branch). Empty = cancelled."""
        name, ok = _qt_input_text(
            slicer.util.mainWindow(),
            "Branch name",
            "Name for this branch:",
            "",
        )
        if not ok:
            return ""
        slug = normalize_branch_slug(name)
        if not slug:
            self._appendFeed("Enter a valid branch name.", error=True)
            return ""
        return slug

    def _promptTaskBranchName(
        self,
        parent=None,
        start_label: str = "",
        default_name: str = "",
    ) -> str:
        """Ask the senior to name the shared task branch. Empty = cancelled."""
        host = parent if parent is not None else slicer.util.mainWindow()
        start = str(start_label or "").strip() or "the chosen start version"
        suggested = normalize_branch_slug(default_name) or ""
        name, ok = _qt_input_text(
            host,
            "Task branch name",
            "A shared branch will be created from %s so the assigned "
            "juniors can work on this task together.\n\n"
            "Choose a name for that branch:" % start,
            suggested,
        )
        if not ok:
            return ""
        slug = normalize_branch_slug(name)
        if not slug:
            self._showTaskWarning(
                "Enter a valid branch name (letters, numbers, dashes).",
                parent=host,
            )
            return ""
        return slug

    def _showTaskWarning(self, message: str, parent=None) -> None:
        """Blocking warning box (preferred over a feed line for task pick/assign)."""
        text = str(message or "").strip() or "Something went wrong."
        host = parent
        if host is None:
            logic = getattr(self, "logic", None)
            if logic is not None:
                host = getattr(logic, "historyDialog", None)
        if host is None:
            host = getattr(self, "_open_task_dialog", None)
        if host is None:
            host = slicer.util.mainWindow()
        try:
            slicer.util.warningDisplay(text, windowTitle="Tasks", parent=host)
            return
        except TypeError:
            pass
        box = qt.QMessageBox(host)
        box.setWindowTitle("Tasks")
        box.setIcon(qt.QMessageBox.Warning)
        box.setText(text)
        box.setStandardButtons(qt.QMessageBox.Ok)
        box.exec_()

    def _confirmShareCurrentLine(self, local_path: str) -> bool:
        """Explain exactly what Share will publish on the current branch."""
        on_branch = False
        slug = ""
        try:
            on_branch = work_is_on_review_branch(local_path)
            slug = current_review_branch_slug(local_path) if on_branch else ""
        except (GitHubAuthError, OSError, RuntimeError, ValueError):
            on_branch = False
            slug = ""
        branch = slug or "main"
        tip = str(getattr(self, "_currentVersionId", None) or "").strip() or "the current tip"
        box = qt.QMessageBox(slicer.util.mainWindow())
        box.setWindowTitle("Share")
        box.setIcon(qt.QMessageBox.Question)
        box.setText("Publish this branch to the shared project?")
        box.setInformativeText(
            "Branch: %s\n"
            "Up to: %s\n\n"
            "This shares all unshared versions on this branch up to that tip.\n"
            "Other local branches are not shared."
            % (branch, tip)
        )
        share_btn = box.addButton("Share", qt.QMessageBox.AcceptRole)
        box.addButton("Cancel", qt.QMessageBox.RejectRole)
        box.setDefaultButton(share_btn)
        box.exec_()
        return box.clickedButton() == share_btn

    def _githubLogin(self) -> str:
        session = getattr(self, "_github_session", None) or {}
        login = str(session.get("login") or "").strip()
        if login:
            return login
        # Avoid a fake identity in local mode (owner/senior checks use this).
        if getattr(self, "_local_mode", False) or not self._connected:
            return ""
        return "annotator"

    def _currentRemoteRepo(self) -> dict | None:
        if not self._hasSelectedProject():
            return None
        session = getattr(self, "_github_session", None) or {}
        name = self._currentProjectName()
        for repo in session.get("repos") or []:
            if repo.get("full_name") == name:
                return repo
        return None

    def _isCurrentProjectLocalOnly(self) -> bool:
        """True for Connected list entries marked (not shared) — local clone, not on GitHub."""
        repo = self._currentRemoteRepo()
        return bool(repo and (repo or {}).get("local_only"))

    def _projectUsesLocalInfoOnly(self) -> bool:
        """No remote project-info poll: offline local mode, or Connected (not shared) project."""
        if getattr(self, "_local_mode", False) and not self._connected:
            return True
        return self._isCurrentProjectLocalOnly()

    def _hasWorkspaceSession(self) -> bool:
        """Online Connected or offline local mode (identity known)."""
        return bool(self._connected or getattr(self, "_local_mode", False))

    def _populateProjectCombo(self) -> None:
        blocked = self.projectCombo.signalsBlocked()
        self.projectCombo.blockSignals(True)
        previous = self._currentProjectName()
        self.projectCombo.clear()
        self.projectCombo.addItem(PROJECT_NONE_LABEL)
        self.projectCombo.setItemData(0, "")
        session = getattr(self, "_github_session", None) or {}
        restore_index = 0
        if self._hasWorkspaceSession():
            for repo in session.get("repos") or []:
                full_name = str((repo or {}).get("full_name") or "").strip()
                if not full_name:
                    continue
                # Suffix only when online-connected and project exists only locally.
                if self._connected and bool((repo or {}).get("local_only")):
                    label = "%s%s" % (full_name, PROJECT_NOT_ON_GITHUB_SUFFIX)
                else:
                    label = full_name
                self.projectCombo.addItem(label)
                index = _qt_combo_count(self.projectCombo) - 1
                self.projectCombo.setItemData(index, full_name)
                if previous and full_name == previous:
                    restore_index = index
        self.projectCombo.setCurrentIndex(restore_index)
        self.projectCombo.blockSignals(blocked)

    def _hasSelectedProject(self) -> bool:
        name = self._currentProjectName()
        return bool(name) and name != PROJECT_NONE_LABEL

    def _currentProjectName(self) -> str:
        combo = getattr(self, "projectCombo", None)
        if not _qt_widget_is_valid(combo):
            return ""
        try:
            index = int(combo.currentIndex())
        except (AttributeError, RuntimeError, TypeError, ValueError):
            index = -1
        if index >= 0:
            try:
                data = combo.itemData(index)
            except (AttributeError, RuntimeError, TypeError, ValueError):
                data = None
            if data is not None:
                name = str(data).strip()
                if name:
                    return name
        name = _qt_combo_text(combo)
        if name == PROJECT_NONE_LABEL:
            return ""
        if name.endswith(PROJECT_NOT_ON_GITHUB_SUFFIX):
            return name[: -len(PROJECT_NOT_ON_GITHUB_SUFFIX)].strip()
        # Legacy label from older builds.
        if name.endswith(" (not shared)"):
            return name[: -len(" (not shared)")].strip()
        return name

    def _refreshUiState(self) -> None:
        if self._connected:
            self._setNotificationsEnabled(True)
            self._setRightDockLocked(False)
            self._setActiveProjectSectionEnabled(True)
            self._setMessagesSectionEnabled(True)
            self._syncMessagesPolling()
            self._updateCommitHistoryPanel()
            self._updateVersionActionButtons()
            # Keep Version tree / Anatomy buttons in sync when selection leaves the open project.
            self._updateRightDockAvailability()
            return
        if getattr(self, "_local_mode", False):
            self._applyLocalModeUi()
            return
        self._applyDisconnectedUi()

    def _applyLocalModeUi(self) -> None:
        """Unlock workspace UI without claiming a live GitHub online session."""
        self._stopNotificationsPolling()
        self._clearNotificationsDisplay()
        self._setNotificationsEnabled(False)
        self._stopMessagesPolling()
        self._setRightDockLocked(False)
        self._setActiveProjectSectionEnabled(True)
        # Messages / Tasks: show local snapshot; send / Assign stay blocked.
        self._setMessagesSectionEnabled(True)
        self._setMessagesComposerEnabled(False)
        self._updateCommitHistoryPanel()
        self._updateVersionActionButtons()
        self._updateRightDockAvailability()

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
            "ontologyMenuButton",
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
            # Gear stays clickable for Help; other ontology actions stay off.
            menu_btn = getattr(self, "ontologyMenuButton", None)
            if menu_btn is not None:
                menu_btn.setEnabled(True)
            self._setProjectAssetFieldsEnabled(False)
            return
        self._setProjectAssetFieldsEnabled(True)
        self._updateVersionActionButtons()

    def _setMessagesSectionEnabled(self, enabled: bool) -> None:
        button = getattr(self, "messagesButton", None)
        if button is not None:
            button.setEnabled(bool(enabled))
        task_button = getattr(self, "messagesTaskButton", None)
        if task_button is not None:
            # Same as other action buttons: clickable when connected, even with no project.
            task_button.setEnabled(bool(enabled))
        if not enabled:
            self._setMessagesComposerEnabled(False)
        self._updateTaskButtonUi()

    def _setMessagesComposerEnabled(self, enabled: bool) -> None:
        can_write = bool(
            enabled
            and self._connected
            and self._projectDataIsLoaded()
            and not self._projectUsesLocalInfoOnly()
        )
        for name in ("messagesInput", "messagesSend"):
            widget = getattr(self, name, None)
            if widget is not None:
                widget.setEnabled(can_write)
        self._updateTaskButtonUi()

    def _canOpenDependencyGraph(self) -> bool:
        if not self._hasWorkspaceSession():
            return False
        if not self._ontology_document:
            return False
        if self._hasSelectedProject():
            return self._server_pulled
        return True

    def _canOpenVersionTree(self) -> bool:
        if not self._hasWorkspaceSession():
            return False
        if not self._hasSelectedProject():
            return False
        return self._server_pulled

    def _updateRightDockAvailability(self) -> None:
        if not self._hasWorkspaceSession() or self._suppress_asset_ui_updates > 0:
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
        if not self._hasWorkspaceSession() or self._suppress_asset_ui_updates > 0:
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
            self._hasWorkspaceSession()
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
        return bool(
            self._hasWorkspaceSession()
            and self._hasSelectedProject()
            and not self._projectDataIsLoaded()
        )

    def _openDisabledReason(self) -> str:
        if not self._hasWorkspaceSession():
            return "Connect with GitHub first."
        if not self._hasSelectedProject():
            return "Select a project first."
        if self._projectDataIsLoaded():
            return "This project is already open."
        return ""

    def _canShare(self) -> bool:
        if not self._connected:
            return False
        if not self._projectDataIsLoaded():
            return False
        if self._isCurrentProjectLocalOnly():
            return False
        if self._isCurrentVersionWriteLocked():
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
        if self._isCurrentProjectLocalOnly():
            return "This project is not on GitHub."
        if self._isCurrentVersionWriteLocked():
            return self._writeLockBlockedReason("Share")
        repo = self._currentRemoteRepo()
        if repo and not repo.get("can_push"):
            return "This project is read-only for your account."
        if not self._unshared_version:
            return "Save a version first."
        return ""

    def _canSaveVersion(self) -> bool:
        if not self._projectDataIsLoaded():
            return False
        if self._isCurrentVersionWriteLocked():
            return False
        if not self._hasExplicitUnsavedEdits():
            return False
        return self._hasVolume() and self._ontologyReadyForCreate()

    def _saveVersionDisabledReason(self) -> str:
        if not self._hasWorkspaceSession():
            return "Connect with GitHub first."
        if not self._hasSelectedProject():
            return "Create or open a project first."
        if not self._projectDataIsLoaded():
            return "Open the project first."
        if self._isCurrentVersionWriteLocked():
            return self._writeLockBlockedReason("Save")
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
        if not self._hasWorkspaceSession() or self._suppress_asset_ui_updates > 0:
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
        else:
            self.shareButton.setToolTip(
                "Publish the current branch (main or another branch) to the shared project"
            )
        can_people = self._canOpenPeople()
        self.peopleButton.setStyleSheet(BTN_PEOPLE)
        self.peopleButton.setEnabled(True)
        self.peopleButton.setToolTip(
            "See who is on this project" if can_people else self._peopleDisabledReason()
        )
        can_delete = self._canDeleteProject()
        self.deleteButton.setStyleSheet(BTN_DELETE)
        self.deleteButton.setEnabled(True)
        if not can_delete:
            self.deleteButton.setToolTip(self._deleteDisabledReason())
        elif self._canDeleteRemoteProject():
            self.deleteButton.setToolTip(
                "Remove this project on this computer and/or on GitHub"
            )
        elif self._isCurrentProjectLocalOnly():
            self.deleteButton.setToolTip("Remove this project folder on this computer")
        else:
            self.deleteButton.setToolTip(
                "Remove the local copy on this computer (GitHub stays)"
            )

    def _isCurrentProjectOwner(self) -> bool:
        """Online owner (Delete / People Add). Local mode never counts as owner here."""
        repo = self._currentRemoteRepo()
        return bool(self._connected and repo and repo.get("role") == "owner")

    def _repoOwnerMatchesLogin(self) -> bool:
        """True when the project owner/ segment matches the session login (offline-safe)."""
        name = self._currentProjectName()
        login = (self._githubLogin() or "").strip()
        if not name or not login or "/" not in name:
            return False
        owner = name.split("/", 1)[0].strip()
        return bool(owner) and owner.lower() == login.lower()

    def _hasSeniorProjectAccess(self) -> bool:
        """Senior/owner rights for write-locks / Save rules (works from local snapshot)."""
        if self._isCurrentProjectOwner() or self._repoOwnerMatchesLogin():
            return True
        full_name = self._currentProjectName()
        if not full_name:
            return False
        cache = getattr(self, "_people_access_cache", {}) or {}
        return cache.get(full_name.lower()) == PEOPLE_ACCESS_SENIOR

    def _rememberPeopleAccess(self, full_name: str, access: str | None = None) -> str:
        name = (full_name or "").strip()
        if not name:
            return PEOPLE_ACCESS_JUNIOR
        if access is None:
            if self._isCurrentProjectOwner() or self._repoOwnerMatchesLogin():
                access = PEOPLE_ACCESS_SENIOR
            elif self._projectUsesLocalInfoOnly():
                # Offline / (not shared): never hit the API; default junior until snapshot.
                access = PEOPLE_ACCESS_JUNIOR
            else:
                access = people_access_for(name, self._githubLogin())
        cache = getattr(self, "_people_access_cache", None)
        if cache is None:
            self._people_access_cache = {}
            cache = self._people_access_cache
        cache[name.lower()] = access
        return access

    def _shareNeedsApproval(self) -> bool:
        if self._hasSeniorProjectAccess():
            return False
        full_name = self._currentProjectName()
        if not full_name:
            return False
        cache = getattr(self, "_people_access_cache", {}) or {}
        access = cache.get(full_name.lower())
        return access == PEOPLE_ACCESS_JUNIOR

    def _canOpenPeople(self) -> bool:
        # Same gate as Share / Delete: live GitHub session (not local mode).
        return bool(
            self._connected
            and self._hasSelectedProject()
            and self._projectDataIsLoaded()
        )

    def _peopleDisabledReason(self) -> str:
        if not self._connected:
            return "Connect with GitHub first."
        if not self._hasSelectedProject():
            return "Select a project first."
        if not self._projectDataIsLoaded():
            return "Open the project first."
        return ""

    def _canDeleteProject(self) -> bool:
        """Local folder can always be removed on this machine; remote needs owner."""
        return bool(self._hasWorkspaceSession() and self._hasSelectedProject())

    def _canDeleteRemoteProject(self) -> bool:
        """GitHub delete: Connected owner of a project that is on GitHub."""
        if not self._connected or not self._isCurrentProjectOwner():
            return False
        if self._isCurrentProjectLocalOnly():
            return False
        return True

    def _deleteDisabledReason(self) -> str:
        if not self._hasWorkspaceSession():
            return "Connect with GitHub first."
        if not self._hasSelectedProject():
            return "Select a project first."
        return ""

    def _clearProjectSelection(self) -> None:
        self.projectCombo.blockSignals(True)
        none_index = self.projectCombo.findText(PROJECT_NONE_LABEL)
        self.projectCombo.setCurrentIndex(none_index if none_index >= 0 else 0)
        self.projectCombo.blockSignals(False)

    def _applyProjectHistoryBundle(self, history: dict | None, follow_head: bool = False) -> str | None:
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
        head_id = bundle.get("head_id")
        if follow_head and head_id:
            self._currentVersionId = head_id
        elif previous_sha and previous_sha in id_by_sha:
            self._currentVersionId = id_by_sha[previous_sha]
        else:
            self._currentVersionId = head_id
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
        if not self._hasWorkspaceSession():
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
        if not self._hasWorkspaceSession():
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
        if self._hasSelectedProject() and not self._hasWorkspaceSession():
            self._showConnectRequired("Connect with GitHub to open a remote project.")
            self.projectCombo.blockSignals(True)
            self._clearProjectSelection()
            self.projectCombo.blockSignals(False)
            return

        if self._hasSelectedProject():
            name = self._currentProjectName()
            if name == getattr(self, "_loaded_project_name", None):
                # Same as returning from None: keep history/version bundle in memory.
                self._server_pulled = True
            else:
                # Hide history UI only — do not wipe the open project's bundle,
                # or returning here would show an empty Version tree / table.
                self._server_pulled = False
            # Assets + messages/project notifs follow selection (park while away).
            self._syncAssetFieldsToProjectSelection()
            self._refreshUiState()
            self._appendFeed("Project selected: %s" % name)
            return

        # None selected: same as another project — park chat/notifs activity.
        self._server_pulled = False
        self._syncAssetFieldsToProjectSelection()
        self._refreshUiState()
        self._appendFeed("No project selected — Create a new project or wait for an invitation.")

    def _versionDisplayTag(self, version_id: str) -> str:
        bundle = getattr(self, "_project_history_bundle", None) or {}
        tags = bundle.get("tags_by_id") or {}
        return str(tags.get(version_id, version_id))

    def getVersionTreePayload(self):
        if not self._hasWorkspaceSession():
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

        # Already in local mode: skip Continue/Switch — go straight to online check.
        if getattr(self, "_local_mode", False):
            login = str((self._github_session or {}).get("login") or "").strip()
            if not login:
                login = local_cli_login() or ""
            session = self._connectOnlineWithOfflineFallback(login)
            if session is None:
                return
            self.connectButton.setEnabled(True)
            self._applyGitHubSession(session)
            return

        # 1) Tools + local gh auth status only (works offline).
        # 2) If a CLI account exists → Continue / Switch / Cancel.
        # 3) Continue → gh api user + repo list (needs Internet).
        self._openProgress("GitHub", "Checking GitHub CLI…")
        try:
            self._updateProgress("Checking GitHub CLI…")
            ensure_tools()
            self._updateProgress("Reading local GitHub account…")
            existing_login = local_cli_login()
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
            session = self._connectOnlineWithOfflineFallback(existing_login)
            if session is None:
                return
            self.connectButton.setEnabled(True)
            self._applyGitHubSession(session)
            return

        # No local CLI account → full web sign-in (needs Internet).
        session = self._signInThenConnect()
        if session is None:
            return
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

    def _promptOfflineLocalMode(self, login: str) -> str:
        """Cannot reach GitHub after Continue — Try again / Local mode / Cancel."""
        box = qt.QMessageBox(slicer.util.mainWindow())
        box.setIcon(qt.QMessageBox.Warning)
        box.setWindowTitle("Cannot reach GitHub")
        box.setText(offline_message())
        if login:
            box.setInformativeText(
                "Or work offline in local mode as %s "
                "(open and save projects already on this computer)."
                % login
            )
        else:
            box.setInformativeText(
                "Or work offline in local mode "
                "(open and save projects already on this computer)."
            )
        try_btn = box.addButton("Try again", qt.QMessageBox.AcceptRole)
        local_btn = box.addButton("Local mode", qt.QMessageBox.ActionRole)
        box.addButton("Cancel", qt.QMessageBox.RejectRole)
        box.setDefaultButton(try_btn)
        box.exec_()
        clicked = box.clickedButton()
        if clicked == try_btn:
            return "try_again"
        if clicked == local_btn:
            return "local"
        return "cancel"

    def _connectOnlineWithOfflineFallback(
        self, login: str, *, allow_signin: bool = True
    ) -> dict | None:
        """Online connect_session; on offline → Try again / Local mode / Cancel."""
        while True:
            self._openProgress("GitHub", "Connecting…")
            try:
                self._updateProgress("Checking GitHub account online…")
                session = connect_session()
                self._updateProgress("Connected")
            except GitHubNotSignedInError:
                self._closeProgress()
                if not allow_signin:
                    self._connectFailed(
                        "GitHub sign-in was not completed. "
                        "Click Connect with GitHub to try again."
                    )
                    return None
                session = self._signInThenConnect()
                if session is None:
                    return None
                return session
            except GitHubAuthError as error:
                self._closeProgress()
                if is_offline_error(error) or isinstance(error, GitHubOfflineError):
                    choice = self._promptOfflineLocalMode(login)
                    if choice == "try_again":
                        self._appendFeed("Trying GitHub again…")
                        continue
                    if choice == "local":
                        if not login:
                            self._connectFailed(
                                "Connect with GitHub first — no local account found."
                            )
                            return None
                        self._enterLocalMode(login)
                        return None
                    # Cancel: restore previous local-mode UI or plain Not connected.
                    self.connectButton.setEnabled(True)
                    if getattr(self, "_local_mode", False) and login:
                        self.connectionStatusLabel.text = (
                            "Not connected — %s (local mode)" % login
                        )
                        self.connectionStatusLabel.setStyleSheet(STATUS_NEUTRAL)
                        self._appendFeed("Still in local mode as %s." % login)
                    else:
                        self.connectionStatusLabel.text = "Not connected"
                        self.connectionStatusLabel.setStyleSheet(STATUS_NEUTRAL)
                        self._appendFeed("Connection cancelled.")
                    return None
                self._connectFailed(error)
                return None
            self._closeProgress()
            return session

    def _enterLocalMode(self, login: str) -> None:
        """Offline workspace: identity known, button stays Connect, local clones only."""
        user = str(login or "").strip()
        if not user:
            self._connectFailed("Connect with GitHub first — no local account found.")
            return
        self._closeProgress()
        self._local_mode = True
        self._connected = False
        self._local_project_people = []
        self._clearNotificationsDisplay()
        repos = []
        for full_name in list_local_project_full_names(user):
            repos.append(
                {
                    "full_name": full_name,
                    "private": True,
                    "can_push": True,
                    "role": "local",
                    "local_only": True,
                }
            )
        self._github_session = {"login": user, "repos": repos}
        self.connectButton.setEnabled(True)
        self.connectButton.setText("Connect with GitHub")
        self.connectionStatusLabel.text = "Not connected — %s (local mode)" % user
        self.connectionStatusLabel.setStyleSheet(STATUS_NEUTRAL)
        self._populateProjectCombo()
        self._refreshUiState()
        self._appendFeed(
            "Local mode as %s — %d project(s) on this computer."
            % (user, len(repos))
        )

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
        if getattr(self, "_local_mode", False):
            login = str((self._github_session or {}).get("login") or "").strip()
            if login:
                self.connectionStatusLabel.text = (
                    "Not connected — %s (local mode)" % login
                )
                self.connectionStatusLabel.setStyleSheet(STATUS_NEUTRAL)
                self._showGithubError(error, box=True)
                return
        self.connectionStatusLabel.text = "Not connected"
        self.connectionStatusLabel.setStyleSheet(STATUS_NEUTRAL)
        self._showGithubError(error, box=True)

    def _showGithubError(self, error, *, box: bool = True) -> None:
        """Show a clinician-facing GitHub/Git error; unify offline / missing-project messages.

        User-triggered actions (Connect / Open / Share / …) always get feedback again on
        each click — no throttle. Background paths use ``box=False`` and may throttle feed.
        """
        text = user_facing_github_error(error)
        feed_line = text.split("\n")[0].strip() or "Something went wrong talking to GitHub."
        if is_offline_error(error) or isinstance(error, GitHubOfflineError):
            if box:
                slicer.util.warningDisplay(
                    offline_message(),
                    windowTitle="Cannot reach GitHub",
                )
            # force=True so a second Connect/Open/Share while offline still logs in the feed.
            self._appendFeed(feed_line, error=True, force=True)
            return
        if is_missing_project_error(error) or isinstance(error, GitHubMissingProjectError):
            if box:
                slicer.util.warningDisplay(
                    missing_project_message(),
                    windowTitle="Project unavailable",
                )
            self._appendFeed(feed_line, error=True, force=True)
            return
        if box:
            slicer.util.warningDisplay(text, windowTitle="GitHub")
        self._appendFeed(feed_line, error=True, force=True)

    def _showConnectRequired(self, message: str = "") -> None:
        """Button gated on live GitHub — box instead of feed (esp. local mode)."""
        text = str(message or "").strip() or "Connect with GitHub first."
        title = "Local mode" if getattr(self, "_local_mode", False) else "GitHub"
        try:
            slicer.util.warningDisplay(text, windowTitle=title)
        except TypeError:
            slicer.util.warningDisplay(text)

    def _showActionUnavailable(self, reason: str) -> None:
        """Disabled-button click: Connect → box; other reasons → feed."""
        text = str(reason or "").strip()
        if not text:
            return
        if text.startswith("Connect with GitHub"):
            self._showConnectRequired(text)
            return
        self._appendFeed(text, error=True)

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
        login_hint = ""
        try:
            login_hint = local_cli_login() or ""
        except GitHubAuthError:
            login_hint = ""
        # Same online path + offline Try again / Local mode / Cancel.
        # allow_signin=False avoids looping back into this dialog.
        return self._connectOnlineWithOfflineFallback(login_hint, allow_signin=False)

    def _replaceSessionReposMerged(
        self, remote_repos: list | None, login: str | None = None
    ) -> list:
        """Set session repos = remote ∪ local clones (not shared). Never drop known local-only."""
        user = str(
            login
            or (getattr(self, "_github_session", None) or {}).get("login")
            or self._githubLogin()
            or ""
        ).strip()
        merged = merge_remote_and_local_repos(user, remote_repos or [])
        seen = {
            str((repo or {}).get("full_name") or "").strip().lower()
            for repo in merged
            if str((repo or {}).get("full_name") or "").strip()
        }
        # Keep prior (not shared) entries still on disk if the folder scan missed them.
        for old in (getattr(self, "_github_session", None) or {}).get("repos") or []:
            if not (old or {}).get("local_only"):
                continue
            full_name = str((old or {}).get("full_name") or "").strip()
            key = full_name.lower()
            if not full_name or key in seen:
                continue
            try:
                dest = local_project_dir(full_name, user or None)
                still_there = os.path.isdir(os.path.join(dest, ".git"))
            except (GitHubAuthError, OSError, TypeError, ValueError):
                still_there = False
            if not still_there:
                continue
            entry = dict(old)
            entry["local_only"] = True
            merged.append(entry)
            seen.add(key)
        merged.sort(key=lambda item: str((item or {}).get("full_name") or "").lower())
        previous = getattr(self, "_github_session", None) or {}
        self._github_session = {
            "login": user or previous.get("login") or "unknown",
            "repos": merged,
        }
        return merged

    def _applyGitHubSession(self, session: dict) -> None:
        self._closeProgress()
        login = session.get("login") or "unknown"
        # Merge GitHub-accessible repos with local clones; local-only → (not shared).
        merged = self._replaceSessionReposMerged(session.get("repos") or [], login)
        self._connected = True
        self._local_mode = False
        repo_count = len(merged)
        local_only = sum(1 for repo in merged if (repo or {}).get("local_only"))
        self.connectionStatusLabel.text = "Connected — %s" % login
        self.connectionStatusLabel.setStyleSheet(STATUS_OK)
        self.connectButton.setText("Disconnect")
        self._populateProjectCombo()
        self._refreshUiState()
        if local_only:
            self._appendFeed(
                "Connected as %s — %d project(s) "
                "(%d only on this computer, not on GitHub)."
                % (login, repo_count, local_only)
            )
        else:
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
            # Scene only — project files stay on disk / GitHub.
            self._updateProgress("Unloading data from 3D Slicer…")
            self._unloadProjectSceneNodes()
            self._updateProgress("Signing out of GitHub…")
            logout_github_cli(login or None)
        except GitHubAuthError as error:
            self._closeProgress()
            self._showGithubError(error, box=True)
            return
        self._closeProgress()
        self._connected = False
        self._local_mode = False
        self._github_session = None
        self.connectButton.setText("Connect with GitHub")
        self.connectionStatusLabel.text = "Not connected"
        self.connectionStatusLabel.setStyleSheet(STATUS_NEUTRAL)
        self._clearProjectSelection()
        self._populateProjectCombo()
        self._loaded_project_name = None
        self._local_project_path = None
        self._project_scene_node_ids = []
        self._server_pulled = False
        self._people_access_cache = {}
        self._local_project_people = []
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
                self._showConnectRequired()
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
            self._showGithubError(error, box=True)
            return
        login = self._githubLogin()
        try:
            remote_repos = list_accessible_repos(login)
        except GitHubAuthError:
            remote_repos = [
                item
                for item in ((self._github_session or {}).get("repos") or [])
                if not (item or {}).get("local_only")
            ]
            if not any(item.get("full_name") == created["full_name"] for item in remote_repos):
                remote_repos.append(created)
        # Keep (not shared) locals — same merge as Connect / Accept invite.
        self._replaceSessionReposMerged(remote_repos, login)
        full_name = created["full_name"]
        local_path = created.get("local_path") or ""
        # Drop the previous project's Version tree — its clicks / timers must not
        # fire a Switch-version prompt against the new project.
        self._closeHistoryDialog()
        self.projectCombo.blockSignals(True)
        self._populateProjectCombo()
        restore = -1
        for index in range(_qt_combo_count(self.projectCombo)):
            try:
                data = self.projectCombo.itemData(index)
            except (AttributeError, RuntimeError, TypeError, ValueError):
                data = None
            if str(data or "").strip() == full_name:
                restore = index
                break
        if restore >= 0:
            self.projectCombo.setCurrentIndex(restore)
        self._loaded_project_name = full_name
        self._local_project_path = local_path
        self._server_pulled = True
        self.projectCombo.blockSignals(False)
        # Clear stale version id (e.g. main/2 of the source project) so history
        # table refresh does not try to checkout another tip with a Save prompt.
        self._suppress_history_selection_signal = True
        self._suppress_dirty += 1
        try:
            self._currentVersionId = None
            self._applyProjectHistoryBundle(history, follow_head=True)
            # Match Open-project naming in the scene; original files outside the project stay untouched.
            self._alignProjectAssetNodeNames(volume_node, segmentation_node, config["name"])
            self._rememberProjectSceneNodes(volume_node, segmentation_node)
            if ontology_path:
                self._setOntologyComboLoadedFilename(filename=ontology_path)
            self._clearChangeFlags()
            self._syncAssetDataObservers()
            self.createButton.setEnabled(True)
            self._closeProgress()
            self._refreshUiState()
        finally:
            self._suppress_dirty -= 1
            self._suppress_history_selection_signal = False
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
                self._showActionUnavailable(reason)
            return
        full_name = self._currentProjectName()
        self.peopleButton.setEnabled(False)
        # Local mode / (not shared): colleagues from Open snapshot (no API). Add stays off.
        if self._projectUsesLocalInfoOnly():
            people = list(getattr(self, "_local_project_people", None) or [])
            if not people and full_name and "/" in full_name:
                owner = full_name.split("/", 1)[0].strip()
                if owner:
                    people = [{"login": owner, "role": "owner"}]
            self._updateVersionActionButtons()
            qt.QTimer.singleShot(
                0,
                lambda n=full_name, p=people: self._showPeopleDialog(n, p, False),
            )
            return
        self._openProgress("People", "Reading who is on this project…")
        try:
            self._updateProgress("Reading who is on this project…")
            people = list_project_people(full_name)
        except (GitHubAuthError, OSError, RuntimeError, ValueError) as error:
            self._closeProgress()
            self._updateVersionActionButtons()
            self._showGithubError(error, box=True)
            return
        self._closeProgress()
        self._updateVersionActionButtons()
        can_add = self._isCurrentProjectOwner()
        qt.QTimer.singleShot(
            0,
            lambda n=full_name, p=people, a=can_add: self._showPeopleDialog(n, p, a),
        )

    def _showPeopleDialog(self, full_name: str, people, can_add: bool) -> None:
        current = list(people or [])
        # Presence comes from the Messages poll (same project-info document).
        self._maybeTouchPresence(force=False)
        while True:
            self._pending_people_action = None
            dialog = None
            try:
                local_view = self._projectUsesLocalInfoOnly()
                dialog = PeopleDialog(
                    slicer.util.mainWindow(),
                    current,
                    can_add=can_add,
                    # Snapshot-only projects: no live presence stamps.
                    presence=(
                        {}
                        if local_view
                        else (getattr(self, "_project_presence", {}) or {})
                    ),
                    me=self._githubLogin() or "",
                )
                if (
                    local_view
                    and not can_add
                    and getattr(dialog, "colleagueHint", None) is not None
                ):
                    # Prefer local-mode wording: enterLocalMode tags every repo
                    # local_only, so "not on GitHub" must not win that case.
                    if getattr(self, "_local_mode", False):
                        dialog.colleagueHint.setText(
                            "Local mode — viewing colleagues from this computer. "
                            "Add or remove requires Connect with GitHub."
                        )
                    elif self._isCurrentProjectLocalOnly():
                        dialog.colleagueHint.setText(
                            "This project is not on GitHub — "
                            "viewing colleagues from this computer. "
                            "Add or remove is unavailable."
                        )
                    else:
                        dialog.colleagueHint.setText(
                            "Local mode — viewing colleagues from this computer. "
                            "Add or remove requires Connect with GitHub."
                        )
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
                    self._flushMessagesUiAfterModal()
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
            access = str(payload.get("access") or PEOPLE_ACCESS_JUNIOR)
        else:
            username = str(payload or "").strip()
            access = PEOPLE_ACCESS_JUNIOR
        if access == PEOPLE_ACCESS_SENIOR:
            access_label = "Senior"
        else:
            access_label = "Junior"
        self._openProgress("People", "Adding colleague…")
        try:
            self._updateProgress("Adding colleague…")
            outcome = invite_project_colleague(full_name, username, access)
            self._updateProgress("Updating the people list…")
            people = list_project_people(full_name)
        except (GitHubAuthError, OSError, RuntimeError, ValueError) as error:
            self._closeProgress()
            self._showGithubError(error, box=True)
            return current
        self._closeProgress()
        if outcome == "already":
            message = "%s is already on this project." % username
        else:
            message = (
                "Invitation sent to %s (%s). They can join from 3D Slicer after they Connect."
                % (username, access_label)
            )
            me = self._githubLogin() or "Someone"
            self._recordActivity(
                full_name,
                "people_add",
                "%s invited %s (%s)." % (me, username, access_label),
            )
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
            self._showGithubError(error, box=True)
            return current
        self._closeProgress()
        login_key = login.lower()
        people = [
            item
            for item in (current or [])
            if str(item.get("login") or "").strip().lower() != login_key
            or item.get("role") == "owner"
        ]
        me = self._githubLogin() or "Someone"
        if role == "pending":
            message = "Cancelled the invitation for %s." % login
            self._recordActivity(
                full_name,
                "people_remove",
                "%s cancelled the invitation for %s." % (me, login),
            )
        else:
            message = "Removed %s from the project." % login
            self._recordActivity(
                full_name,
                "people_remove",
                "%s removed %s from the project." % (me, login),
            )
        self._appendFeed(message)
        return people

    def _joinIncomingInvitation(self, invitation: dict) -> None:
        full_name = invitation.get("full_name") or ""
        self._openProgress("Join project", "Joining %s…" % full_name)
        try:
            self._updateProgress("Joining %s…" % full_name)
            accept_project_invitation(invitation.get("id"))
            self._updateProgress("Refreshing project list…")
            session = connect_session()
            login = str(session.get("login") or self._githubLogin() or "").strip()
            # Same merge as Connect (+ keep prior not-shared still on disk).
            self._replaceSessionReposMerged(session.get("repos") or [], login)
            # Rebuild list; keep the currently selected project (do not auto-switch).
            self._populateProjectCombo()
            self._refreshUiState()
        except (GitHubAuthError, OSError, RuntimeError, ValueError) as error:
            self._closeProgress()
            self._appendFeed(str(error).split("\n")[0], error=True)
            return
        self._closeProgress()
        me = self._githubLogin() or "Someone"
        try:
            access = people_access_for(full_name, me)
        except (GitHubAuthError, OSError, RuntimeError, ValueError):
            access = PEOPLE_ACCESS_JUNIOR
        # Always refresh session cache (Senior→Junior re-invite must not keep old role).
        self._rememberPeopleAccess(full_name, access)
        role_label = "Senior" if access == PEOPLE_ACCESS_SENIOR else "Junior"
        self._recordActivity(
            full_name,
            "join",
            "%s joined the project as %s." % (me, role_label),
        )
        loaded = str(getattr(self, "_loaded_project_name", None) or "").strip()
        if full_name and loaded and full_name.lower() == loaded.lower():
            # Project already open: padlocks / Save / Share / Tasks follow the new role.
            self._refreshUiState()
            self._updateCommitHistoryPanel()
            self._updateVersionActionButtons()
            self._updateTaskButtonUi()
            self._appendFeed(
                "Joined %s as %s — role updated for the open project."
                % (full_name, role_label)
            )
        else:
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
        self._notificationFetchProject = ""
        self._refreshing_notifications = False
        if process is None:
            return
        try:
            if int(process.state()) != 0:
                process.kill()
            process.deleteLater()
        except (AttributeError, RuntimeError, TypeError, ValueError):
            pass

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
        # Invites only (global). Project activity comes from the Messages poll.
        queue = [{"kind": "invite", "args": incoming_invitations_fetch_args(), "full_name": ""}]
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
            self._notificationFetchProject = ""
            self._refreshing_notifications = False
            self._applyNotificationRequests(incoming, announce=announce)
            return
        job = queue.pop(0)
        self._notificationFetchQueue = queue
        self._notificationFetchKind = job.get("kind") or ""
        self._notificationFetchProject = job.get("full_name") or ""
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
        self._notificationFetchProject = ""
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
        items = []
        try:
            if kind == "invite":
                items = parse_incoming_invitations_output(stdout, stderr, code)
        except (GitHubAuthError, OSError, RuntimeError, ValueError):
            items = []
        results = getattr(self, "_notificationFetchResults", None)
        if results is None:
            results = []
            self._notificationFetchResults = results
        results.extend(items or [])
        self._startNextNotificationFetch()

    def _notificationKey(self, item: dict) -> str:
        kind = item.get("kind") or ""
        if kind == "invite":
            return "invite#%s" % item.get("id")
        return "activity#%s#%s" % (item.get("full_name") or "", item.get("id") or "")

    def _rebuildNotificationsDisplay(self) -> None:
        invites = list(getattr(self, "_notification_invites", []) or [])
        activity = list(getattr(self, "_notification_activity", []) or [])
        self._notifications = invites + activity
        self._updateNotificationsBadge()

    def _applyNotificationRequests(self, requests: list, announce: bool = False) -> None:
        """Apply invitation-only poll results; keep project activity from Messages."""
        invites = [
            item
            for item in (requests or [])
            if str(item.get("kind") or "") == "invite"
        ]
        previous_keys = {
            self._notificationKey(item)
            for item in getattr(self, "_notification_invites", []) or []
        }
        if announce:
            for item in invites:
                key = self._notificationKey(item)
                if key in previous_keys:
                    continue
                if not self._isNotificationUnread(item):
                    continue
                self._appendFeed(
                    "You were invited to %s." % (item.get("full_name") or "a project")
                )
        self._notification_invites = invites
        self._rebuildNotificationsDisplay()

    def _syncNotificationActivityFromProject(self, announce: bool = False) -> None:
        """Fill the bell with activity for the selected project (from Messages poll)."""
        # Local mode / (not shared): no project activity in the bell.
        if self._projectUsesLocalInfoOnly():
            self._notification_activity = []
            self._rebuildNotificationsDisplay()
            return
        project = self._currentProjectName() if self._hasSelectedProject() else ""
        me = (self._githubLogin() or "").lower()
        items = []
        if project:
            for event in getattr(self, "_project_activity", []) or []:
                author = str((event or {}).get("author") or "").strip()
                if author.lower() == me:
                    continue
                items.append(
                    {
                        "kind": "activity",
                        "activity_kind": str((event or {}).get("kind") or ""),
                        "id": str((event or {}).get("id") or ""),
                        "author": author,
                        "text": str((event or {}).get("text") or ""),
                        "at": str((event or {}).get("at") or ""),
                        "full_name": project,
                        "when": self._formatMessageTime((event or {}).get("at") or ""),
                    }
                )
        items.sort(key=lambda item: str(item.get("at") or ""), reverse=True)
        items = items[:40]
        previous_keys = {
            self._notificationKey(item)
            for item in getattr(self, "_notification_activity", []) or []
        }
        saw_new_assign = False
        if announce:
            for item in items:
                key = self._notificationKey(item)
                if key in previous_keys:
                    continue
                if not self._isNotificationUnread(item):
                    continue
                text = str(item.get("text") or "").strip()
                if text:
                    self._appendFeed(text)
                if str(item.get("activity_kind") or "").strip().lower() == "assign":
                    saw_new_assign = True
        self._notification_activity = items
        self._rebuildNotificationsDisplay()
        # Rare offline cache: refresh origin/project-info when a new Assign lands.
        if saw_new_assign:
            self._scheduleLocalProjectInfoFetch()
        if getattr(self, "_pending_versions_behind_hint", False):
            self._pending_versions_behind_hint = False
            if self._projectVersionsBehind():
                slicer.util.infoDisplay(
                    "Your local project is not aligned with the remote copy.\n\n"
                    "Open Notifications → Compare with shared to review differences "
                    "before updating.",
                    windowTitle="Local project",
                )

    def _clearNotificationsDisplay(self) -> None:
        self._notifications = []
        self._notification_invites = []
        self._notification_activity = []
        self._invite_read_ids = set()
        self._reads_by_project = {}
        self._updateNotificationsBadge()

    def _notificationsEmptyText(self) -> str:
        if not self._connected:
            return "Connect with GitHub to see notifications."
        return "No new notifications."

    def _projectReadEntry(self, full_name: str) -> dict:
        project = str(full_name or "").strip()
        if not project:
            return {}
        return dict((getattr(self, "_reads_by_project", {}) or {}).get(project) or {})

    def _isNotificationUnread(self, item: dict) -> bool:
        kind = str((item or {}).get("kind") or "")
        key = self._notificationKey(item or {})
        if kind == "invite":
            return bool(key) and key not in getattr(self, "_invite_read_ids", set())
        entry = self._projectReadEntry((item or {}).get("full_name") or "")
        aid = str((item or {}).get("id") or "").strip()
        ids = entry.get("activity_ids") or []
        if aid and isinstance(ids, list) and aid in ids:
            return False
        stamp = str((item or {}).get("at") or "")
        cursor = str(entry.get("activity_at") or "")
        if cursor and stamp and stamp <= cursor:
            return False
        return True

    def _unreadNotificationKeys(self) -> set:
        unread = set()
        for item in getattr(self, "_notifications", []) or []:
            key = self._notificationKey(item)
            if key and self._isNotificationUnread(item):
                unread.add(key)
        return unread

    def _unreadNotificationCount(self) -> int:
        return len(self._unreadNotificationKeys())

    def _bumpLocalReadCursor(
        self,
        full_name: str,
        activity_at: str = "",
        messages_at: str = "",
        versions_at: str = "",
        activity_ids=None,
    ) -> None:
        project = str(full_name or "").strip()
        if not project:
            return
        by_project = getattr(self, "_reads_by_project", None)
        if not isinstance(by_project, dict):
            by_project = {}
            self._reads_by_project = by_project
        entry = dict(by_project.get(project) or {})
        activity_stamp = str(activity_at or "").strip()
        messages_stamp = str(messages_at or "").strip()
        versions_stamp = str(versions_at or "").strip()
        if activity_stamp and activity_stamp > str(entry.get("activity_at") or ""):
            entry["activity_at"] = activity_stamp
        if messages_stamp and messages_stamp > str(entry.get("messages_at") or ""):
            entry["messages_at"] = messages_stamp
        if versions_stamp and versions_stamp > str(entry.get("versions_at") or ""):
            entry["versions_at"] = versions_stamp
        ids = list(entry.get("activity_ids") or []) if isinstance(entry.get("activity_ids"), list) else []
        seen = set(ids)
        for aid in activity_ids or []:
            text = str(aid or "").strip()
            if not text or text in seen:
                continue
            seen.add(text)
            ids.append(text)
        if ids:
            entry["activity_ids"] = ids[-200:]
        by_project[project] = entry
        current = self._currentProjectName() if self._hasSelectedProject() else ""
        if project == current:
            self._project_reads = dict(entry)

    def _persistReadCursor(
        self,
        full_name: str,
        activity_at: str = "",
        messages_at: str = "",
        versions_at: str = "",
        activity_ids=None,
    ) -> None:
        # Update local cursor immediately; push to GitHub async (same path as chat).
        self._bumpLocalReadCursor(
            full_name,
            activity_at=activity_at,
            messages_at=messages_at,
            versions_at=versions_at,
            activity_ids=activity_ids,
        )
        self._enqueueReadCursor(
            full_name,
            activity_at=activity_at,
            messages_at=messages_at,
            versions_at=versions_at,
            activity_ids=activity_ids,
        )

    def _enqueueReadCursor(
        self,
        full_name: str,
        activity_at: str = "",
        messages_at: str = "",
        versions_at: str = "",
        activity_ids=None,
    ) -> None:
        project = str(full_name or "").strip()
        activity_stamp = str(activity_at or "").strip()
        messages_stamp = str(messages_at or "").strip()
        versions_stamp = str(versions_at or "").strip()
        ids = [str(aid).strip() for aid in (activity_ids or []) if str(aid).strip()]
        if not project or (
            not activity_stamp and not messages_stamp and not versions_stamp and not ids
        ):
            return

        def _bump_payload(payload: dict) -> None:
            if activity_stamp and activity_stamp > str(payload.get("activity_at") or ""):
                payload["activity_at"] = activity_stamp
            if messages_stamp and messages_stamp > str(payload.get("messages_at") or ""):
                payload["messages_at"] = messages_stamp
            if versions_stamp and versions_stamp > str(payload.get("versions_at") or ""):
                payload["versions_at"] = versions_stamp
            existing = list(payload.get("activity_ids") or [])
            seen = set(existing)
            for aid in ids:
                if aid not in seen:
                    seen.add(aid)
                    existing.append(aid)
            if existing:
                payload["activity_ids"] = existing[-200:]

        current = getattr(self, "_messageSendCurrent", None) or {}
        if (
            getattr(self, "_sending_message", False)
            and str(current.get("kind") or "") == "reads"
            and str(current.get("full_name") or "") == project
        ):
            _bump_payload(current)
            return
        queue = list(getattr(self, "_messageSendQueue", []) or [])
        for item in queue:
            if str(item.get("kind") or "") == "reads" and str(item.get("full_name") or "") == project:
                _bump_payload(item)
                self._messageSendQueue = queue
                return
        payload = {
            "id": "reads-%s-%s" % (project, int(time.time() * 1000)),
            "kind": "reads",
            "full_name": project,
            "author": self._githubLogin() or "Someone",
            "text": "",
            "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "activity_at": activity_stamp,
            "messages_at": messages_stamp,
            "versions_at": versions_stamp,
            "activity_ids": list(ids),
        }
        queue.append(payload)
        self._messageSendQueue = queue
        if not getattr(self, "_sending_message", False):
            self._startNextQueuedSend()

    def _versionsSyncCursor(self, full_name: str = "") -> str:
        project = str(full_name or "").strip() or (
            self._currentProjectName() if self._hasSelectedProject() else ""
        )
        return str(self._projectReadEntry(project).get("versions_at") or "")

    def _isVersionsSyncRelevant(self, item: dict) -> bool:
        if str((item or {}).get("kind") or "") != "activity":
            return False
        return str((item or {}).get("activity_kind") or "").strip().lower() in (
            _VERSIONS_SYNC_ACTIVITY_KINDS
        )

    def _isNotificationLaggingVersions(self, item: dict) -> bool:
        if not self._isVersionsSyncRelevant(item):
            return False
        stamp = str((item or {}).get("at") or "").strip()
        if not stamp:
            return False
        cursor = self._versionsSyncCursor((item or {}).get("full_name") or "")
        return (not cursor) or stamp > cursor

    def _laggingVersionNotificationKeys(self) -> set:
        lagging = set()
        for item in getattr(self, "_notifications", []) or []:
            if not self._isNotificationLaggingVersions(item):
                continue
            key = self._notificationKey(item)
            if key:
                lagging.add(key)
        return lagging

    def _projectVersionsBehind(self) -> bool:
        return bool(self._laggingVersionNotificationKeys())

    def _newestVersionsSyncStamp(self) -> str:
        newest = ""
        for item in getattr(self, "_notification_activity", []) or []:
            if not self._isVersionsSyncRelevant(item):
                continue
            stamp = str(item.get("at") or "").strip()
            if stamp > newest:
                newest = stamp
        if newest:
            return newest
        for event in getattr(self, "_project_activity", []) or []:
            kind = str((event or {}).get("kind") or "").strip().lower()
            if kind not in _VERSIONS_SYNC_ACTIVITY_KINDS:
                continue
            stamp = str((event or {}).get("at") or "").strip()
            if stamp > newest:
                newest = stamp
        return newest

    def _markNotificationRead(self, item: dict) -> None:
        kind = str((item or {}).get("kind") or "")
        key = self._notificationKey(item or {})
        if kind == "invite":
            if key:
                invite_ids = getattr(self, "_invite_read_ids", set())
                invite_ids.add(key)
                self._invite_read_ids = invite_ids
            self._updateNotificationsBadge()
            return
        project = str((item or {}).get("full_name") or "").strip()
        aid = str((item or {}).get("id") or "").strip()
        if project and aid:
            self._persistReadCursor(project, activity_ids=[aid])
        self._updateNotificationsBadge()

    def _markAllNotificationsRead(self) -> None:
        newest_by_project = {}
        ids_by_project = {}
        invite_ids = getattr(self, "_invite_read_ids", set())
        for item in getattr(self, "_notifications", []) or []:
            if str(item.get("kind") or "") == "invite":
                key = self._notificationKey(item)
                if key:
                    invite_ids.add(key)
                continue
            project = str(item.get("full_name") or "").strip()
            stamp = str(item.get("at") or "").strip()
            aid = str(item.get("id") or "").strip()
            if not project:
                continue
            if stamp and stamp > str(newest_by_project.get(project) or ""):
                newest_by_project[project] = stamp
            if aid:
                ids_by_project.setdefault(project, []).append(aid)
        self._invite_read_ids = invite_ids
        projects = set(newest_by_project) | set(ids_by_project)
        for project in projects:
            self._persistReadCursor(
                project,
                activity_at=newest_by_project.get(project) or "",
                activity_ids=ids_by_project.get(project) or [],
            )
        self._updateNotificationsBadge()

    def _taskExcerptForJunior(self, junior: str) -> str:
        name = str(junior or "").strip().lower()
        if not name:
            return ""
        for task in getattr(self, "_project_tasks", []) or []:
            if name not in {login.lower() for login in _task_junior_logins(task)}:
                continue
            if str(task.get("status") or "") == "accepted":
                continue
            return _task_excerpt(
                task.get("submitted_description") or task.get("description") or ""
            )
        return ""

    def _updateNotificationsBadge(self) -> None:
        badge = getattr(self, "notificationsBadge", None)
        behind_badge = getattr(self, "notificationsBehindBadge", None)
        bell = getattr(self, "notificationsBell", None)
        count = self._unreadNotificationCount()
        behind = bool(
            self._projectDataIsLoaded()
            and not self._projectUsesLocalInfoOnly()
            and self._projectVersionsBehind()
        )
        if badge is not None:
            if count <= 0:
                badge.hide()
            else:
                badge.setText("9+" if count > 9 else str(count))
                badge.show()
                badge.raise_()
        if behind_badge is not None:
            if behind:
                behind_badge.show()
                behind_badge.raise_()
            else:
                behind_badge.hide()
        if bell is not None:
            tips = []
            if count == 1:
                tips.append("1 notification")
            elif count > 1:
                tips.append("%d notifications" % count)
            if behind:
                tips.append("Local project is not aligned with the remote copy")
            bell.setToolTip(" · ".join(tips) if tips else "Notifications")

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
            self._updateMessagesPresenceBanner()
            self._maybeTouchPresence(force=False)
        button = getattr(self, "messagesButton", None)
        if button is not None:
            try:
                button.clearFocus()
            except (AttributeError, RuntimeError, TypeError):
                pass
        self._positionMessagesBadge()

    def _resetMessagesState(self, project: str) -> None:
        self._stopMessageSend()
        self._open_project_chat_stash = None
        self._messages = []
        self._project_tasks = []
        self._project_activity = []
        self._project_reads = {}
        self._project_presence = {}
        self._presence_last_publish_mono = 0.0
        self._messages_unread = 0
        self._messages_project = project or ""
        self._notification_activity = []
        self._rebuildNotificationsDisplay()
        self._renderMessagesView()
        self._updateMessagesPresenceBanner()
        self._updateMessagesBadge()
        self._updateTaskButtonUi()

    def _messagesProjectActive(self) -> str:
        """Only after Open: Messages / project activity / versions sync are for the loaded copy."""
        if not self._connected or not self._projectDataIsLoaded():
            return ""
        # (not shared) local-only projects: no Connected project-info poll.
        if self._projectUsesLocalInfoOnly():
            return ""
        return self._currentProjectName()

    def _syncMessagesPolling(self) -> None:
        name = self._messagesProjectActive()
        seeded = str(getattr(self, "_messages_project", "") or "").strip()
        loaded = (
            self._projectDataIsLoaded()
            and seeded
            and seeded == self._currentProjectName()
        )
        # Local mode / (not shared): keep Open snapshot in memory; no poll.
        if not name and loaded and self._projectUsesLocalInfoOnly():
            self._stopMessagesPolling()
            self._setMessagesComposerEnabled(False)
            self._renderMessagesView()
            self._updateMessagesBadge()
            self._updateTaskButtonUi()
            return
        # Chat already parked by _parkOpenProjectChatUi while browsing away.
        if not name and getattr(self, "_open_project_chat_stash", None):
            self._stopMessagesPolling()
            self._setMessagesComposerEnabled(False)
            self._renderMessagesView()
            self._updateMessagesBadge()
            self._updateTaskButtonUi()
            return
        changed = name != seeded
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
        if self._projectUsesLocalInfoOnly():
            return
        progress = getattr(self, "_progressDialog", None)
        if progress is not None and _qt_widget_is_valid(progress):
            return
        if getattr(self, "_offering_invitations", False):
            return
        # People / Tasks / Notifications open: keep polling (and presence), but
        # _applyProjectMessages will skip UI refresh until those dialogs close.
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

    def _messagesUiRefreshBlocked(self) -> bool:
        """True while a modal project dialog should not have lists rewritten under it."""
        return bool(
            getattr(self, "_people_dialog_open", False)
            or getattr(self, "_task_dialog_open", False)
            or getattr(self, "_notifications_popup_open", False)
        )

    def _flushMessagesUiAfterModal(self) -> None:
        """Apply cached Messages/presence state to the UI after a blocking dialog closes."""
        if self._messagesUiRefreshBlocked():
            return
        if not self._connected or not self._projectDataIsLoaded():
            return
        self._applyProjectMessages(
            list(getattr(self, "_messages", []) or []),
            tasks=list(getattr(self, "_project_tasks", []) or []),
            activity=list(getattr(self, "_project_activity", []) or []),
            reads=None,
            presence=dict(getattr(self, "_project_presence", {}) or {}),
            refresh_ui=True,
            announce_activity=False,
        )
        self._maybeTouchPresence(force=False)

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
            incoming, _sha, tasks, activity, reads, presence = parse_project_messages_output(
                stdout, stderr, code
            )
        except (GitHubAuthError, OSError, RuntimeError, ValueError):
            return
        blocked = self._messagesUiRefreshBlocked()
        self._applyProjectMessages(
            incoming,
            tasks,
            activity,
            reads,
            presence,
            refresh_ui=not blocked,
            announce_activity=not blocked,
        )
        self._maybeTouchPresence(force=False)

    def _messagesCursor(self) -> str:
        return str((getattr(self, "_project_reads", {}) or {}).get("messages_at") or "")

    def _newestMessageStamp(self, messages=None) -> str:
        newest = ""
        for item in messages if messages is not None else (getattr(self, "_messages", []) or []):
            stamp = str((item or {}).get("at") or "")
            if stamp > newest:
                newest = stamp
        return newest

    def _applyProjectMessages(
        self,
        incoming: list,
        tasks=None,
        activity=None,
        reads=None,
        presence=None,
        refresh_ui: bool = True,
        announce_activity: bool = True,
    ) -> None:
        if tasks is not None:
            self._project_tasks = list(tasks or [])
        if activity is not None:
            self._project_activity = list(activity or [])
        if presence is not None:
            self._project_presence = dict(presence or {})
        messages = list(incoming or [])
        me = (self._githubLogin() or "").lower()
        project = self._currentProjectName() if self._hasSelectedProject() else ""
        if reads is not None and project:
            my_reads = (reads or {}).get(me) or {}
            previous = getattr(self, "_project_reads", {}) or {}
            ids = []
            seen_ids = set()
            for source in (previous.get("activity_ids"), my_reads.get("activity_ids")):
                if not isinstance(source, list):
                    continue
                for aid in source:
                    text = str(aid or "").strip()
                    if not text or text in seen_ids:
                        continue
                    seen_ids.add(text)
                    ids.append(text)
            merged = {
                "activity_at": max(
                    str(previous.get("activity_at") or ""),
                    str(my_reads.get("activity_at") or ""),
                ),
                "messages_at": max(
                    str(previous.get("messages_at") or ""),
                    str(my_reads.get("messages_at") or ""),
                ),
                "versions_at": max(
                    str(previous.get("versions_at") or ""),
                    str(my_reads.get("versions_at") or ""),
                ),
            }
            if ids:
                merged["activity_ids"] = ids[-200:]
            self._project_reads = {key: value for key, value in merged.items() if value}
            by_project = getattr(self, "_reads_by_project", None)
            if not isinstance(by_project, dict):
                by_project = {}
                self._reads_by_project = by_project
            by_project[project] = dict(self._project_reads)
        cursor = self._messagesCursor()
        # While a modal dialog is open, do not auto-mark the chat as read.
        panel_open = self._messagesPanelOpen() and refresh_ui
        if panel_open:
            newest = self._newestMessageStamp(messages)
            if project and newest and newest > cursor:
                self._persistReadCursor(project, messages_at=newest)
            self._messages_unread = 0
        else:
            unread = 0
            for item in messages:
                if str((item or {}).get("kind") or "") == "task":
                    continue
                author = str(item.get("author") or "").lower()
                stamp = str(item.get("at") or "")
                if not stamp or author == me:
                    continue
                if stamp > cursor:
                    unread += 1
            self._messages_unread = unread
        self._messages = self._mergePendingMessages(messages)
        if not refresh_ui:
            # Memory + presence heartbeat only; UI catches up when the dialog closes.
            return
        self._renderMessagesView()
        self._updateMessagesPresenceBanner()
        self._updateMessagesBadge()
        self._updateTaskButtonUi()
        # Task assign/cancel can change junior write-lock lanes (Save/Share).
        self._updateVersionActionButtons()
        self._syncNotificationActivityFromProject(announce=bool(announce_activity))

    def _onlinePresenceLogins(self, *, exclude_me: bool = False) -> list[str]:
        presence = getattr(self, "_project_presence", {}) or {}
        me = (self._githubLogin() or "").strip().lower()
        names = []
        for key, entry in sorted(presence.items(), key=lambda item: item[0]):
            login = str((entry or {}).get("login") or key or "").strip()
            stamp = str((entry or {}).get("at") or "").strip()
            if not login:
                continue
            if exclude_me and me and login.lower() == me:
                continue
            if presence_is_online(stamp) or (me and login.lower() == me):
                names.append(login)
        if me and not exclude_me:
            # Always count myself when the project is open locally.
            if not any(name.lower() == me for name in names):
                names.insert(0, self._githubLogin() or me)
        names.sort(key=lambda item: item.lower())
        return names

    def _updateMessagesPresenceBanner(self) -> None:
        label = getattr(self, "messagesPresenceLabel", None)
        if label is None or not _qt_widget_is_valid(label):
            return
        if not self._projectDataIsLoaded():
            label.setText("")
            label.setVisible(False)
            return
        # Local mode / (not shared): no live presence poll — hide the online banner.
        if not self._connected or self._projectUsesLocalInfoOnly():
            label.setText("")
            label.setVisible(False)
            return
        others = self._onlinePresenceLogins(exclude_me=True)
        if others:
            text = "🟢 Online: %s" % ", ".join(others)
        else:
            text = "🟢 Online: only you (nobody else in the last ~2–3 min)"
        label.setText(text)
        label.setVisible(True)

    def _maybeTouchPresence(self, force: bool = False) -> None:
        """Publish my last-seen stamp (throttled) while this project is open."""
        if not self._connected or not self._projectDataIsLoaded():
            return
        if self._projectUsesLocalInfoOnly():
            return
        project = self._currentProjectName()
        me = (self._githubLogin() or "").strip()
        if not project or not me:
            return
        now_mono = time.monotonic()
        last = float(getattr(self, "_presence_last_publish_mono", 0.0) or 0.0)
        if not force and last and (now_mono - last) < PRESENCE_PUBLISH_INTERVAL_SECONDS:
            return
        # Optimistic local mark so People/Messages update before the PUT returns.
        stamp = utc_now_stamp()
        presence = dict(getattr(self, "_project_presence", {}) or {})
        presence[me.lower()] = {"login": me, "at": stamp}
        self._project_presence = presence
        self._presence_last_publish_mono = now_mono
        self._updateMessagesPresenceBanner()
        self._enqueuePresenceTouch(project, stamp)

    def _enqueuePresenceTouch(self, full_name: str, stamp: str = "") -> None:
        project = str(full_name or "").strip()
        me = (self._githubLogin() or "").strip()
        at = str(stamp or "").strip() or utc_now_stamp()
        if not project or not me:
            return
        current = getattr(self, "_messageSendCurrent", None) or {}
        if (
            getattr(self, "_sending_message", False)
            and str(current.get("kind") or "") == "presence"
            and str(current.get("full_name") or "") == project
        ):
            current["at"] = at
            current["author"] = me
            return
        queue = list(getattr(self, "_messageSendQueue", []) or [])
        for item in queue:
            if (
                str(item.get("kind") or "") == "presence"
                and str(item.get("full_name") or "") == project
            ):
                item["at"] = at
                item["author"] = me
                self._messageSendQueue = queue
                return
        queue.append(
            {
                "id": "presence-%s-%s" % (project, int(time.time() * 1000)),
                "kind": "presence",
                "full_name": project,
                "author": me,
                "text": "",
                "at": at,
            }
        )
        self._messageSendQueue = queue
        if not getattr(self, "_sending_message", False):
            self._startNextQueuedSend()

    def _mergePresenceForPut(self, remote_presence, touch_stamp: str = "") -> dict:
        merged = dict(remote_presence or {})
        local = dict(getattr(self, "_project_presence", {}) or {})
        for key, entry in local.items():
            remote_entry = merged.get(key) or {}
            local_at = str((entry or {}).get("at") or "")
            remote_at = str((remote_entry or {}).get("at") or "")
            if local_at and local_at >= remote_at:
                merged[key] = {
                    "login": str((entry or {}).get("login") or key),
                    "at": local_at,
                }
        me = (self._githubLogin() or "").strip()
        stamp = str(touch_stamp or "").strip()
        if me and stamp:
            merged[me.lower()] = {"login": me, "at": stamp}
        return merged

    def _markMessagesRead(self) -> None:
        project = self._currentProjectName() if self._hasSelectedProject() else ""
        newest = self._newestMessageStamp()
        if project and newest:
            self._persistReadCursor(project, messages_at=newest)
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
        if not self._projectDataIsLoaded():
            return "Select a project and open it to access messages."
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

    def _isChatMessage(self, item: dict) -> bool:
        return str((item or {}).get("kind") or "") != "task"

    def _chatMessages(self):
        return [
            item
            for item in (getattr(self, "_messages", []) or [])
            if self._isChatMessage(item)
        ]

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

    def _messagesScrollMetrics(self):
        bar = self._messagesScrollBar()
        if bar is None:
            return None
        try:
            value = bar.value
            if callable(value):
                value = value()
            maximum = bar.maximum
            if callable(maximum):
                maximum = maximum()
            return int(value), int(maximum)
        except (AttributeError, RuntimeError, TypeError, ValueError):
            return None

    def _messagesViewAtBottom(self) -> bool:
        metrics = self._messagesScrollMetrics()
        if metrics is None:
            return True
        value, maximum = metrics
        return maximum - value <= 12

    def _renderMessagesView(self, force_bottom: bool = False) -> None:
        view = getattr(self, "messagesView", None)
        if view is None or not _qt_widget_is_valid(view):
            return
        messages = self._chatMessages()
        if not messages:
            markup = '<span style="color:%s">%s</span>' % (
                TEXT_MUTED,
                html.escape(self._messagesEmptyText()),
            )
        else:
            markup = "".join(self._formatMessageHtml(item) for item in messages)
        # Polling must not rewrite identical HTML: that resets the scrollbar slightly.
        if markup == getattr(self, "_messagesViewHtml", None) and not force_bottom:
            return
        stay_at_bottom = bool(force_bottom) or self._messagesViewAtBottom()
        from_bottom = 0
        if not stay_at_bottom:
            metrics = self._messagesScrollMetrics()
            if metrics is not None:
                value, maximum = metrics
                from_bottom = max(0, maximum - value)
        self._messagesViewHtml = markup
        try:
            view.setHtml(markup)
        except (RuntimeError, TypeError, ValueError):
            return
        self._messagesScrollRestore = "end" if stay_at_bottom else ("from_bottom", from_bottom)
        qt.QTimer.singleShot(0, self._applyMessagesScrollRestore)

    def _applyMessagesScrollRestore(self) -> None:
        payload = getattr(self, "_messagesScrollRestore", None)
        self._messagesScrollRestore = None
        if payload is None:
            return
        if payload == "end":
            self._scrollMessagesToEnd()
            return
        if not isinstance(payload, (tuple, list)) or len(payload) != 2:
            return
        kind, from_bottom = payload
        if kind != "from_bottom":
            return
        bar = self._messagesScrollBar()
        if bar is None:
            return
        try:
            maximum = bar.maximum
            if callable(maximum):
                maximum = maximum()
            bar.setValue(max(0, int(maximum) - int(from_bottom)))
        except (AttributeError, RuntimeError, TypeError, ValueError):
            pass

    def _scrollMessagesToEnd(self) -> None:
        view = getattr(self, "messagesView", None)
        if view is None or not _qt_widget_is_valid(view):
            return
        try:
            view.moveCursor(qt.QTextCursor.End)
            view.ensureCursorVisible()
        except (AttributeError, RuntimeError, TypeError, ValueError):
            pass
        bar = self._messagesScrollBar()
        if bar is None:
            return
        try:
            maximum = bar.maximum
            if callable(maximum):
                maximum = maximum()
            bar.setValue(int(maximum))
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
        self._messageSendTasks = []
        self._messageSendActivity = []
        self._messageSendReads = {}
        self._stopMessageSendProcess()

    def _storedMessage(self, message: dict) -> dict:
        stored = {
            "id": str(message.get("id") or ""),
            "author": str(message.get("author") or "Someone"),
            "text": str(message.get("text") or ""),
            "at": str(message.get("at") or ""),
        }
        kind = str(message.get("kind") or "").strip()
        if kind:
            stored["kind"] = kind
        return stored

    def _startNextQueuedSend(self) -> None:
        if getattr(self, "_sending_message", False):
            return
        queue = list(getattr(self, "_messageSendQueue", []) or [])
        if not queue:
            return
        message = queue.pop(0)
        self._messageSendQueue = queue
        self._messageSendCurrent = message
        kind = str(message.get("kind") or "")
        if kind in ("reads", "presence"):
            self._messageSendProject = str(message.get("full_name") or "").strip()
        else:
            self._messageSendProject = self._currentProjectName()
        self._messageSendAttempt = 0
        self._messageSendExisting = []
        self._messageSendTasks = list(getattr(self, "_project_tasks", []) or [])
        self._messageSendActivity = list(getattr(self, "_project_activity", []) or [])
        self._messageSendReads = {}
        self._messageSendPresence = dict(getattr(self, "_project_presence", {}) or {})
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
        if (
            str(current.get("kind") or "") not in ("reads", "presence")
            and project != self._currentProjectName()
        ):
            self._failPendingMessage(current, "Could not send the message.")
            return
        if phase == "get":
            try:
                existing, sha, tasks, activity, reads, presence = parse_project_messages_output(
                    stdout, stderr, code
                )
            except (GitHubAuthError, OSError, RuntimeError, ValueError) as error:
                self._failPendingMessage(current, str(error))
                return
            if str(current.get("kind") or "") == "presence":
                merged_presence = self._mergePresenceForPut(
                    presence, touch_stamp=str(current.get("at") or "")
                )
                self._messageSendExisting = existing
                self._messageSendTasks = tasks
                self._messageSendActivity = activity
                self._messageSendReads = reads
                self._messageSendPresence = merged_presence
                self._messageSendPhase = "put"
                self._startMessageSendProcess(
                    project_messages_put_args(
                        project,
                        existing,
                        sha,
                        tasks=tasks,
                        activity=activity,
                        reads=reads,
                        presence=merged_presence,
                    )
                )
                return
            if str(current.get("kind") or "") == "reads":
                me = (self._githubLogin() or "").strip().lower()
                merged_reads = dict(reads or {})
                entry = dict(merged_reads.get(me) or {})
                activity_stamp = str(current.get("activity_at") or "").strip()
                messages_stamp = str(current.get("messages_at") or "").strip()
                versions_stamp = str(current.get("versions_at") or "").strip()
                local = (getattr(self, "_reads_by_project", {}) or {}).get(project) or {}
                if str(local.get("activity_at") or "") > activity_stamp:
                    activity_stamp = str(local.get("activity_at") or "")
                if str(local.get("messages_at") or "") > messages_stamp:
                    messages_stamp = str(local.get("messages_at") or "")
                if str(local.get("versions_at") or "") > versions_stamp:
                    versions_stamp = str(local.get("versions_at") or "")
                if activity_stamp and activity_stamp > str(entry.get("activity_at") or ""):
                    entry["activity_at"] = activity_stamp
                if messages_stamp and messages_stamp > str(entry.get("messages_at") or ""):
                    entry["messages_at"] = messages_stamp
                if versions_stamp and versions_stamp > str(entry.get("versions_at") or ""):
                    entry["versions_at"] = versions_stamp
                ids = []
                seen_ids = set()
                for source in (
                    entry.get("activity_ids"),
                    current.get("activity_ids"),
                    local.get("activity_ids"),
                ):
                    if not isinstance(source, list):
                        continue
                    for aid in source:
                        text = str(aid or "").strip()
                        if not text or text in seen_ids:
                            continue
                        seen_ids.add(text)
                        ids.append(text)
                if ids:
                    entry["activity_ids"] = ids[-200:]
                if me and entry:
                    merged_reads[me] = entry
                merged_presence = self._mergePresenceForPut(presence)
                self._messageSendExisting = existing
                self._messageSendTasks = tasks
                self._messageSendActivity = activity
                self._messageSendReads = merged_reads
                self._messageSendPresence = merged_presence
                self._messageSendPhase = "put"
                self._startMessageSendProcess(
                    project_messages_put_args(
                        project,
                        existing,
                        sha,
                        tasks=tasks,
                        activity=activity,
                        reads=merged_reads,
                        presence=merged_presence,
                    )
                )
                return
            activity_only = str(current.get("kind") or "") == "activity"
            if activity_only:
                if any(item.get("id") == current.get("id") for item in (activity or [])):
                    self._messageSendTasks = tasks
                    self._messageSendActivity = activity
                    self._messageSendReads = reads
                    self._messageSendPresence = presence
                    self._confirmPendingMessage(current, existing)
                    return
            elif any(item.get("id") == current.get("id") for item in existing):
                self._messageSendTasks = tasks
                self._messageSendActivity = activity
                self._messageSendReads = reads
                self._messageSendPresence = presence
                self._confirmPendingMessage(current, existing)
                return
            try:
                if not activity_only:
                    tasks = self._tasksAfterMessageOp(current, tasks)
            except GitHubAuthError as error:
                self._failPendingMessage(current, str(error))
                return
            merged_activity = list(activity or [])
            extra = self._activityEventFromQueuedMessage(current)
            if extra and not any(
                str(item.get("id") or "") == extra.get("id") for item in merged_activity
            ):
                merged_activity.append(extra)
            merged_presence = self._mergePresenceForPut(presence)
            self._messageSendExisting = existing
            self._messageSendTasks = tasks
            self._messageSendActivity = merged_activity
            self._messageSendReads = reads
            self._messageSendPresence = merged_presence
            self._messageSendPhase = "put"
            if activity_only:
                payload = list(existing)
            else:
                payload = list(existing) + [self._storedMessage(current)]
            self._startMessageSendProcess(
                project_messages_put_args(
                    project,
                    payload,
                    sha,
                    tasks=tasks,
                    activity=merged_activity,
                    reads=reads,
                    presence=merged_presence,
                )
            )
            return
        if code == 0:
            existing = list(getattr(self, "_messageSendExisting", []) or [])
            kind = str(current.get("kind") or "")
            if kind not in ("activity", "reads", "presence"):
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

    def _activityEventFromQueuedMessage(self, message: dict):
        if not isinstance(message, dict):
            return None
        if str(message.get("kind") or "") == "activity":
            kind = str(message.get("activity_kind") or "").strip()
            text = str(message.get("text") or "").strip()
            if not kind or not text:
                return None
            try:
                event = build_project_activity(
                    str(message.get("author") or self._githubLogin() or "Someone"),
                    kind,
                    text,
                )
            except (GitHubAuthError, OSError, RuntimeError, ValueError):
                return None
            if message.get("id"):
                event["id"] = str(message.get("id"))
            if message.get("at"):
                event["at"] = str(message.get("at"))
            return event
        op = str(message.get("task_op") or "").strip()
        if op not in ("assign", "update", "cancel", "submit", "accept"):
            return None
        author = str(message.get("author") or self._githubLogin() or "Someone")
        juniors = _task_juniors_label(message)
        if juniors == "no juniors":
            juniors = "a junior"
        if op == "assign":
            excerpt = _task_excerpt(message.get("description") or "")
            start = str(message.get("anchor_label") or "").strip()
            branch = str(message.get("branch_slug") or "").strip()
            if start and excerpt:
                text = "%s assigned %s to a task from %s: %s" % (
                    author,
                    juniors,
                    start,
                    excerpt,
                )
            elif start:
                text = "%s assigned %s to a task from %s." % (author, juniors, start)
            elif excerpt:
                text = "%s assigned %s to a task: %s" % (author, juniors, excerpt)
            else:
                text = "%s assigned %s to a task." % (author, juniors)
            if branch:
                text = "%s Branch %s." % (text.rstrip("."), branch)
        elif op == "update":
            excerpt = _task_excerpt(message.get("description") or "")
            text = (
                "%s updated the task for %s: %s" % (author, juniors, excerpt)
                if excerpt
                else "%s updated the task for %s." % (author, juniors)
            )
        elif op == "cancel":
            text = "%s cancelled the task for %s." % (author, juniors)
        elif op == "submit":
            excerpt = _task_excerpt(message.get("description") or "")
            branch = str(message.get("branch_slug") or "").strip()
            if excerpt and branch:
                text = "%s requested a review for task on branch %s: %s" % (
                    author,
                    branch,
                    excerpt,
                )
            elif branch:
                text = "%s requested a review on branch %s." % (author, branch)
            elif excerpt:
                text = "%s requested a review for task: %s" % (author, excerpt)
            else:
                text = "%s requested a review on their line." % author
        else:
            excerpt = _task_excerpt(message.get("description") or "")
            text = (
                "%s accepted %s's line onto main for task: %s" % (author, juniors, excerpt)
                if excerpt
                else "%s accepted %s's line onto main." % (author, juniors)
            )
        try:
            return build_project_activity(author, op, text)
        except (GitHubAuthError, OSError, RuntimeError, ValueError):
            return None

    def _confirmPendingMessage(self, message: dict, existing: list) -> None:
        self._sending_message = False
        self._messageSendCurrent = None
        self._messageSendPhase = ""
        kind = str((message or {}).get("kind") or "")
        presence = getattr(self, "_messageSendPresence", None)
        if presence is not None:
            self._project_presence = dict(presence or {})
            self._updateMessagesPresenceBanner()
        if kind not in ("reads", "presence"):
            self._applyProjectMessages(
                existing,
                getattr(self, "_messageSendTasks", None),
                getattr(self, "_messageSendActivity", None),
                getattr(self, "_messageSendReads", None),
                presence,
            )
        # Assigner side: same rare fetch so local mode Tasks stay current.
        if str((message or {}).get("task_op") or "").strip() in ("assign", "update"):
            self._scheduleLocalProjectInfoFetch()
        self._startNextQueuedSend()

    def _scheduleLocalProjectInfoFetch(self) -> None:
        """Best-effort ``git fetch origin project-info`` (not on the 1s poll)."""
        if not self._connected or getattr(self, "_local_mode", False):
            return
        if self._isCurrentProjectLocalOnly():
            return
        path = str(getattr(self, "_local_project_path", None) or "").strip()
        if not path or not os.path.isdir(os.path.join(path, ".git")):
            return
        if getattr(self, "_project_info_fetch_pending", False):
            return
        self._project_info_fetch_pending = True
        qt.QTimer.singleShot(
            0, lambda p=path: self._runLocalProjectInfoFetch(p)
        )

    def _runLocalProjectInfoFetch(self, repo_dir: str) -> None:
        try:
            fetch_local_project_info(repo_dir)
        except (GitHubAuthError, OSError, RuntimeError, ValueError, TypeError):
            pass
        finally:
            self._project_info_fetch_pending = False

    def _failPendingMessage(self, message: dict, error_text: str) -> None:
        kind = str((message or {}).get("kind") or "")
        if kind in ("reads", "presence"):
            if kind == "presence":
                # Allow a retry on the next poll window.
                self._presence_last_publish_mono = 0.0
            self._sending_message = False
            self._messageSendCurrent = None
            self._messageSendPhase = ""
            self._startNextQueuedSend()
            return
        mid = (message or {}).get("id")
        if mid and kind != "activity":
            self._messages = [
                item for item in (getattr(self, "_messages", []) or []) if item.get("id") != mid
            ]
            self._renderMessagesView()
        text = str((message or {}).get("text") or "")
        if (
            text
            and kind not in ("task", "activity")
            and _qt_widget_is_valid(getattr(self, "messagesInput", None))
        ):
            if not _qt_line_text(self.messagesInput):
                self.messagesInput.setText(text)
        self._appendFeed(str(error_text or "Could not send the message.").split("\n")[0], error=True)
        self._sending_message = False
        self._messageSendCurrent = None
        self._messageSendPhase = ""
        self._startNextQueuedSend()

    def _recordActivity(
        self,
        full_name: str,
        kind: str = "",
        text: str = "",
        event: dict | None = None,
    ) -> None:
        name = str(full_name or "").strip()
        if not name:
            return
        try:
            publish_project_activity(name, kind, text, event=event)
        except (GitHubAuthError, OSError, RuntimeError, ValueError):
            # Activity is secondary: never block Share / People / Join / review.
            return

    def _buildActivityEvent(self, kind: str, text: str):
        """Freeze activity id/timestamp now (before any slow UI or network)."""
        try:
            return build_project_activity(self._githubLogin() or "Someone", kind, text)
        except (GitHubAuthError, OSError, RuntimeError, ValueError):
            return None

    def _canAssignTask(self) -> bool:
        """Assign needs a live GitHub session (writes project-info remotely)."""
        if not self._connected or not self._hasSelectedProject():
            return False
        if self._projectUsesLocalInfoOnly():
            return False
        return self._hasSeniorProjectAccess()

    def _tasksAfterMessageOp(self, message, tasks):
        current = list(tasks or [])
        op = str((message or {}).get("task_op") or "").strip()
        if not op:
            return current
        juniors = _task_junior_logins(message)
        senior = str((message or {}).get("senior") or "").strip()
        description = normalize_task_title((message or {}).get("description"))
        if op == "assign":
            if not juniors or not senior:
                raise GitHubAuthError("Select at least one junior.")
            if not description:
                raise GitHubAuthError("Write a short description first.")
            anchor_sha = str((message or {}).get("anchor_sha") or "").strip().lower()
            anchor_label = str((message or {}).get("anchor_label") or "").strip()
            if not anchor_sha or not anchor_label:
                raise GitHubAuthError("Choose a start version on the Version tree first.")
            entry = {
                "id": str(message.get("task_id") or message.get("id") or ""),
                "juniors": list(juniors),
                "junior": juniors[0],
                "senior": senior,
                "kind": "assigned",
                "description": description,
                "status": "",
                "anchor_sha": anchor_sha,
                "anchor_label": anchor_label,
            }
            branch_slug = normalize_branch_slug(
                (message or {}).get("branch_slug") or ""
            )
            if branch_slug:
                entry["branch_slug"] = branch_slug
            current.append(entry)
            return current
        if op == "update":
            if not juniors or not senior:
                raise GitHubAuthError("Keep at least one junior on the task.")
            if not description:
                raise GitHubAuthError("Write a short description first.")
            tid = str((message or {}).get("task_id") or "").strip()
            updated = []
            matched = False
            for task in current:
                if str(task.get("status") or "") == "accepted":
                    updated.append(task)
                    continue
                matches = bool(tid) and str(task.get("id") or "") == tid
                if matches and not matched:
                    task = dict(task)
                    task["juniors"] = list(juniors)
                    task["junior"] = juniors[0]
                    task["description"] = description
                    matched = True
                updated.append(task)
            if not matched:
                raise GitHubAuthError("That task is no longer active.")
            return updated
        if op in ("propose", "claim"):
            # Voluntary tasks removed — ignore legacy ops if they still appear.
            return current
        if op == "submit":
            return self._tasksWithStatus(
                current,
                message,
                "submitted",
                snapshot=description,
            )
        if op == "accept":
            return self._tasksWithStatus(current, message, "accepted")
        if op == "cancel":
            tid = str((message or {}).get("task_id") or "").strip()
            junior_keys = {name.lower() for name in juniors}
            kept = []
            removed = False
            for task in current:
                if str(task.get("status") or "") == "accepted":
                    kept.append(task)
                    continue
                matches = bool(tid) and str(task.get("id") or "") == tid
                if not matches and not tid and junior_keys:
                    task_keys = {name.lower() for name in _task_junior_logins(task)}
                    matches = bool(junior_keys & task_keys)
                if matches and not removed:
                    removed = True
                    continue
                kept.append(task)
            return kept
        return current

    def _tasksWithStatus(self, tasks, message, status: str, snapshot: str = ""):
        tid = str((message or {}).get("task_id") or "").strip()
        junior_keys = {name.lower() for name in _task_junior_logins(message)}
        updated = []
        matched = False
        for task in tasks or []:
            if str(task.get("status") or "") == "accepted":
                updated.append(task)
                continue
            matches = bool(tid) and str(task.get("id") or "") == tid
            if not matches and not tid and junior_keys:
                task_keys = {name.lower() for name in _task_junior_logins(task)}
                matches = bool(junior_keys & task_keys)
            if matches and not matched:
                task = dict(task)
                task["status"] = status
                if status == "submitted":
                    task["submitted_description"] = snapshot or str(task.get("description") or "")
                matched = True
            updated.append(task)
        if not matched:
            raise GitHubAuthError("That task is no longer active.")
        return updated

    def _enqueueTaskMessage(self, message: dict) -> None:
        try:
            self._project_tasks = self._tasksAfterMessageOp(
                message, getattr(self, "_project_tasks", []) or []
            )
        except GitHubAuthError as error:
            self._appendFeed(str(error).split("\n")[0], error=True)
            return
        message["pending"] = True
        current = list(getattr(self, "_messages", []) or [])
        current.append(message)
        self._messages = current
        stamp = str(message.get("at") or "")
        project = self._currentProjectName() if self._hasSelectedProject() else ""
        if project and stamp:
            self._bumpLocalReadCursor(project, messages_at=stamp)
        self._messages_unread = 0
        self._renderMessagesView(force_bottom=True)
        self._updateMessagesBadge()
        self._updateTaskButtonUi()
        queue = list(getattr(self, "_messageSendQueue", []) or [])
        queue.append(message)
        self._messageSendQueue = queue
        if not getattr(self, "_sending_message", False):
            self._startNextQueuedSend()

    def onOpenTask(self, draft=None) -> None:
        if not self._hasWorkspaceSession():
            self._showConnectRequired()
            return
        if not self._hasSelectedProject():
            self._appendFeed("Select a project first.", error=True)
            return
        if not self._projectDataIsLoaded():
            self._appendFeed("Open the project first.", error=True)
            return
        can_assign = self._canAssignTask()
        people = []
        button = getattr(self, "messagesTaskButton", None)
        if button is not None:
            button.setEnabled(False)
        if self._projectUsesLocalInfoOnly():
            # Browse tasks from the local Open snapshot; Assign stays hidden.
            people = list(getattr(self, "_local_project_people", None) or [])
        elif can_assign:
            self._openProgress("Tasks", "Reading who is on this project…")
            try:
                self._updateProgress("Reading who is on this project…")
                people = list_project_people(self._currentProjectName())
            except (GitHubAuthError, OSError, RuntimeError, ValueError) as error:
                self._closeProgress()
                if button is not None:
                    button.setEnabled(True)
                self._updateTaskButtonUi()
                self._appendFeed(str(error).split("\n")[0], error=True)
                return
            self._closeProgress()
        try:
            dialog = TaskDialog(
                slicer.util.mainWindow(),
                people=people,
                tasks=getattr(self, "_project_tasks", []) or [],
                me=self._githubLogin(),
                can_assign=can_assign,
                is_senior=self._hasSeniorProjectAccess(),
                draft=draft if can_assign else None,
            )
        except Exception as error:
            if button is not None:
                button.setEnabled(True)
            self._updateTaskButtonUi()
            self._appendFeed("Could not open tasks. %s" % str(error).split("\n")[0], error=True)
            return
        dialog.set_cancel_handler(self._onCancelTaskChosen)
        if can_assign:
            dialog.set_assign_handler(self._onAssignTaskChosen)
            dialog.set_update_handler(self._onUpdateTaskChosen)
            dialog.set_pick_start_handler(self._onPickStartFromTaskDialog)
        self._task_dialog_open = True
        self._open_task_dialog = dialog
        try:
            dialog.exec_()
        finally:
            self._task_dialog_open = False
            self._open_task_dialog = None
            if getattr(self, "_task_anchor_picking", False):
                self._task_anchor_picking = False
                self._closeHistoryDialog()
            if button is not None:
                button.setEnabled(True)
            self._flushMessagesUiAfterModal()
            self._updateTaskButtonUi()

    def _onPickStartFromTaskDialog(self, dialog) -> None:
        self._open_task_dialog = dialog
        self._beginTaskAnchorPick()

    def _beginTaskAnchorPick(self) -> None:
        dialog = getattr(self, "_open_task_dialog", None)
        if not self._projectDataIsLoaded():
            message = "Open the project first to choose a start version."
            self._appendFeed(message, error=True)
            if dialog is not None:
                dialog.set_status(message, error=True)
            return
        specs = list(
            (getattr(self, "_project_history_bundle", None) or {}).get("version_specs") or []
        )
        if not specs:
            message = "No versions yet to choose as a start."
            self._appendFeed(message, error=True)
            if dialog is not None:
                dialog.set_status(message, error=True)
            return
        self._task_anchor_picking = True
        self._task_anchor_pick_done = False
        self._appendFeed(
            "Click a shared start version in the Version tree "
            "(dashed nodes must be shared first)."
        )
        self.onOpenHistoryGraph(pick_mode=True, parent=dialog)

    def _versionIsUnshared(self, version_id: str) -> bool:
        vid = str(version_id or "").strip()
        if not vid:
            return True
        for row in (
            (getattr(self, "_project_history_bundle", None) or {}).get("commit_history")
            or []
        ):
            if not row or str(row[0] or "").strip() != vid:
                continue
            if len(row) > 4 and str(row[4] or "").strip().lower() == "local":
                return True
            return False
        return False

    def _finishTaskAnchorPick(self, version_id: str) -> None:
        if not getattr(self, "_task_anchor_picking", False):
            return
        dialog = getattr(self, "_open_task_dialog", None)
        logic = getattr(self, "logic", None)
        graph_parent = (
            getattr(logic, "historyDialog", None) if logic is not None else None
        )
        vid = str(version_id or "").strip()
        if self._versionIsUnshared(vid):
            message = "You have to share this version first."
            if dialog is not None:
                dialog.set_status(message, error=True)
            self._showTaskWarning(message, parent=graph_parent or dialog)
            return
        bundle = getattr(self, "_project_history_bundle", None) or {}
        sha = str((bundle.get("sha_by_id") or {}).get(vid) or "").strip().lower()
        label = self._versionDisplayTag(vid) if vid else ""
        if not sha or not label:
            message = "Could not use that version as a start."
            if dialog is not None:
                dialog.set_status(message, error=True)
            self._showTaskWarning(message, parent=graph_parent or dialog)
            return
        local_path = getattr(self, "_local_project_path", None) or ""
        if local_path and not sha_is_shared_on_remote(local_path, sha):
            message = "You have to share this version first."
            if dialog is not None:
                dialog.set_status(message, error=True)
            self._showTaskWarning(message, parent=graph_parent or dialog)
            return
        self._task_anchor_pick_done = True
        self._task_anchor_picking = False
        self._closeHistoryDialog()
        if dialog is not None:
            dialog.set_start_version(sha, label)
            dialog.set_status("Start version set to %s." % label)
        self._appendFeed("Start version set to %s." % label)

    def _cancelTaskAnchorPick(self) -> None:
        if not getattr(self, "_task_anchor_picking", False):
            return
        if getattr(self, "_task_anchor_pick_done", False):
            return
        self._task_anchor_picking = False
        dialog = getattr(self, "_open_task_dialog", None)
        self._appendFeed("Start version not chosen.")
        if dialog is not None:
            try:
                dialog.set_status("Start version not chosen.", error=True)
            except (AttributeError, RuntimeError, TypeError):
                pass

    def _closeHistoryDialog(self) -> None:
        logic = getattr(self, "logic", None)
        if logic is None:
            return
        dialog = getattr(logic, "historyDialog", None)
        logic.historyDialog = None
        logic._historyCanvas = None
        if dialog is None:
            return
        try:
            dialog.close()
        except (AttributeError, RuntimeError, TypeError):
            pass
        try:
            dialog.deleteLater()
        except (AttributeError, RuntimeError, TypeError):
            pass

    def _onAssignTaskChosen(
        self,
        dialog,
        juniors,
        description: str,
        anchor_sha: str = "",
        anchor_label: str = "",
    ) -> None:
        names = [str(name or "").strip() for name in (juniors or []) if str(name or "").strip()]
        if not names:
            dialog.set_status("Select at least one junior.", error=True)
            return
        sha = str(anchor_sha or "").strip().lower()
        start = str(anchor_label or "").strip()
        if not sha or not start:
            dialog.set_status("Choose a start version on the Version tree first.", error=True)
            return
        local_path = getattr(self, "_local_project_path", None) or ""
        if not local_path or not self._projectDataIsLoaded():
            dialog.set_status("Open the project first.", error=True)
            return
        if not sha_is_shared_on_remote(local_path, sha):
            message = "You have to share this version first."
            dialog.set_status(message, error=True)
            self._showTaskWarning(message, parent=dialog)
            return
        # Same alignment gate as Share: remote extras / tip divergence block Assign.
        dialog.set_status("Checking alignment with the shared project…")
        try:
            dialog.assignButton.setEnabled(False)
            dialog.pickStartButton.setEnabled(False)
        except (AttributeError, RuntimeError, TypeError):
            pass
        self._openProgress("Tasks", "Checking the shared project…")
        try:
            local_freeze = copy.deepcopy(
                getattr(self, "_project_history_bundle", None)
            )
            ensure_can_share_with_shared(
                local_path,
                local_history=local_freeze,
                action="assign",
            )
        except (GitHubAuthError, OSError, RuntimeError, ValueError) as error:
            self._closeProgress()
            try:
                dialog.assignButton.setEnabled(True)
                dialog.pickStartButton.setEnabled(True)
            except (AttributeError, RuntimeError, TypeError):
                pass
            dialog.set_status(str(error).split("\n")[0], error=True)
            self._showTaskWarning(str(error), parent=dialog)
            return
        self._closeProgress()
        try:
            dialog.assignButton.setEnabled(True)
            dialog.pickStartButton.setEnabled(True)
        except (AttributeError, RuntimeError, TypeError):
            pass
        branch_slug = self._promptTaskBranchName(
            parent=dialog,
            start_label=start,
            default_name=description,
        )
        if not branch_slug:
            dialog.set_status("Branch name required to assign the task.", error=True)
            return
        label = _task_juniors_label({"juniors": names})
        senior = self._githubLogin()
        try:
            message = build_project_message(
                senior,
                "assigned %s to this task from %s: %s"
                % (label, start, _task_excerpt(description)),
                kind="task",
            )
        except (GitHubAuthError, OSError, RuntimeError, ValueError) as error:
            dialog.set_status(str(error).split("\n")[0], error=True)
            return
        task_id = str(message.get("id") or "")
        dialog.set_status("Creating task branch %s…" % branch_slug)
        try:
            dialog.assignButton.setEnabled(False)
            dialog.pickStartButton.setEnabled(False)
        except (AttributeError, RuntimeError, TypeError):
            pass
        self._openProgress("Tasks", "Creating task branch…")
        try:
            self._updateProgress("Publishing task branch %s…" % branch_slug)
            branch_slug = create_and_publish_task_branch(
                local_path, sha, branch_slug
            )
            self._updateProgress("Updating version history…")
            history = read_project_history(local_path)
        except (GitHubAuthError, OSError, RuntimeError, ValueError) as error:
            self._closeProgress()
            try:
                dialog.assignButton.setEnabled(True)
                dialog.pickStartButton.setEnabled(True)
            except (AttributeError, RuntimeError, TypeError):
                pass
            err = str(error).split("\n")[0]
            dialog.set_status(err, error=True)
            self._showTaskWarning(str(error), parent=dialog)
            return
        self._applyProjectHistoryBundle(history)
        self._closeProgress()
        self._updateCommitHistoryPanel()
        self._updateVersionActionButtons()
        message["task_op"] = "assign"
        message["juniors"] = names
        message["junior"] = names[0]
        message["senior"] = senior
        message["description"] = normalize_task_title(description)
        message["task_id"] = task_id
        message["anchor_sha"] = sha
        message["anchor_label"] = start
        message["branch_slug"] = branch_slug
        dialog.accept()
        self._enqueueTaskMessage(message)
        self._appendFeed(
            "Assigned %s to this task (start %s, branch %s)."
            % (label, start, branch_slug)
        )
        # Show the new lane start on the Version tree (e.g. my-task/start).
        qt.QTimer.singleShot(0, lambda: self.onOpenHistoryGraph(pick_mode=False))

    def _onUpdateTaskChosen(self, dialog, task: dict, juniors, description: str) -> None:
        names = [str(name or "").strip() for name in (juniors or []) if str(name or "").strip()]
        if not names:
            dialog.set_status("Keep at least one junior on the task.", error=True)
            return
        title = normalize_task_title(description)
        if not title:
            dialog.set_status("Write a short description first.", error=True)
            return
        if not self._connected:
            dialog.set_status("Connect with GitHub first.", error=True)
            return
        tid = str((task or {}).get("id") or "").strip()
        if not tid:
            dialog.set_status("Could not update this task.", error=True)
            return
        old_juniors = _task_junior_logins(task)
        old_desc = normalize_task_title((task or {}).get("description") or "")
        if (
            {n.lower() for n in names} == {n.lower() for n in old_juniors}
            and title == old_desc
        ):
            dialog.set_status("No changes to save.")
            return
        senior = str((task or {}).get("senior") or self._githubLogin() or "").strip()
        label = _task_juniors_label({"juniors": names})
        try:
            message = build_project_message(
                self._githubLogin(),
                "updated the task for %s: %s" % (label, _task_excerpt(title)),
                kind="task",
            )
        except (GitHubAuthError, OSError, RuntimeError, ValueError) as error:
            dialog.set_status(str(error).split("\n")[0], error=True)
            return
        message["task_op"] = "update"
        message["task_id"] = tid
        message["juniors"] = names
        message["junior"] = names[0]
        message["senior"] = senior
        message["description"] = title
        # Keep start / branch on the stored task; update only juniors + description.
        for key in ("anchor_sha", "anchor_label", "branch_slug", "status"):
            if (task or {}).get(key):
                message[key] = task.get(key)
        self._enqueueTaskMessage(message)
        try:
            dialog.refresh_tasks(getattr(self, "_project_tasks", []) or [])
        except (AttributeError, RuntimeError, TypeError):
            pass
        dialog.set_status("Task updated for %s." % label)
        self._appendFeed("Updated the task for %s." % label)
        self._updateTaskButtonUi()
        self._updateVersionActionButtons()

    def _onCancelTaskChosen(self, dialog, task: dict) -> None:
        juniors = _task_junior_logins(task)
        label = _task_juniors_label(task)
        try:
            message = build_project_message(
                self._githubLogin(),
                "cancelled the task for %s." % label,
                kind="task",
            )
        except (GitHubAuthError, OSError, RuntimeError, ValueError) as error:
            dialog.set_status(str(error).split("\n")[0], error=True)
            return
        message["task_op"] = "cancel"
        message["task_id"] = str((task or {}).get("id") or "")
        message["juniors"] = list(juniors)
        if juniors:
            message["junior"] = juniors[0]
        message["senior"] = str((task or {}).get("senior") or "")
        dialog.accept()
        self._enqueueTaskMessage(message)
        self._appendFeed("Cancelled the task for %s." % label)

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
        stamp = str(message.get("at") or "")
        project = self._currentProjectName() if self._hasSelectedProject() else ""
        if project and stamp:
            self._bumpLocalReadCursor(project, messages_at=stamp)
        self._messages_unread = 0
        self._renderMessagesView(force_bottom=True)
        self._updateMessagesBadge()
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
        items = []
        for item in getattr(self, "_notifications", []) or []:
            row = dict(item)
            row["_key"] = self._notificationKey(item)
            items.append(row)
        project_open = bool(
            self._hasSelectedProject()
            and (getattr(self, "_local_project_path", None) or "")
            and getattr(self, "_server_pulled", False)
        )
        # (not shared) / offline snapshot: no "aligned with shared" — there is no remote.
        sync_eligible = bool(project_open and not self._projectUsesLocalInfoOnly())
        behind = bool(sync_eligible and self._projectVersionsBehind())
        if sync_eligible and behind:
            sync_status = "⚠  Local project is not aligned with the remote copy."
        elif sync_eligible:
            sync_status = "✅  Local project is aligned with the shared project."
        else:
            sync_status = ""
        dialog = NotificationsDialog(
            slicer.util.mainWindow(),
            items=items,
            empty_text=self._notificationsEmptyText(),
            unread_keys=self._unreadNotificationKeys(),
            lagging_keys=self._laggingVersionNotificationKeys() if sync_eligible else set(),
            sync_status_text=sync_status,
            show_sync_button=bool(sync_eligible and behind),
        )
        self._notifications_popup_open = True
        try:
            result = dialog.exec_()
        finally:
            self._notifications_popup_open = False
            self._flushMessagesUiAfterModal()
        if getattr(dialog, "compare_requested", False) or getattr(
            dialog, "sync_requested", False
        ):
            self._openCompareWithShared()
            return
        if getattr(dialog, "mark_all", False):
            self._markAllNotificationsRead()
            return
        chosen = getattr(dialog, "chosen", None)
        if not chosen or result != qt.QDialog.Accepted:
            return
        self._markNotificationRead(chosen)
        self._openNotificationDetail(chosen)

    def _openCompareWithShared(self) -> None:
        """Fetch for compare only — does not refresh the Version tree until Validate."""
        if not self._hasSelectedProject():
            self._appendFeed("Select a project first.", error=True)
            return
        if self._projectUsesLocalInfoOnly():
            if getattr(self, "_local_mode", False):
                self._showConnectRequired()
            else:
                self._showActionUnavailable(
                    "This project is not on GitHub — "
                    "Compare with shared is unavailable."
                )
            return
        local_path = getattr(self, "_local_project_path", None) or ""
        if not local_path or not getattr(self, "_server_pulled", False):
            self._appendFeed("Open the project first.", error=True)
            return
        # Freeze Version tree UI *and* use that exact state as Compare → Local.
        saved_bundle = copy.deepcopy(getattr(self, "_project_history_bundle", None))
        saved_version_id = getattr(self, "_currentVersionId", None)
        saved_unshared = bool(getattr(self, "_unshared_version", False))
        local_snapshot = saved_bundle
        peek_caps = None
        self._openProgress("Compare with shared", "Reading the shared project…")
        try:
            if not local_snapshot or not (
                local_snapshot.get("version_specs") or local_snapshot.get("sha_by_id")
            ):
                self._updateProgress("Snapshotting local versions…")
                local_snapshot = read_project_history(local_path)
            # Lock Version-tree remote tips to what is already displayed *before* peek-fetch,
            # so a later Open does not absorb Compare-only origin updates.
            peek_caps = derive_remote_sync_caps_from_history(local_path, local_snapshot)
            save_remote_sync_caps(local_path, peek_caps)
            self._updateProgress("Reading the shared project…")
            fetch_remote_updates(local_path)
            self._updateProgress("Building version graphs…")
            # Local = frozen Version tree; Remote = origin/* after fetch; diff = SHA Δ.
            compare = read_compare_project_histories(
                local_path, local_history=local_snapshot
            )
        except (GitHubAuthError, OSError, RuntimeError, ValueError) as error:
            self._closeProgress()
            self._showGithubError(error, box=True)
            return
        self._closeProgress()
        # Re-assert frozen UI (fetch must never rewrite the Version tree panel).
        self._project_history_bundle = saved_bundle
        self._currentVersionId = saved_version_id
        self._unshared_version = saved_unshared
        self._updateCommitHistoryPanel()
        self._updateVersionActionButtons()

        dialog = CompareWithSharedDialog(slicer.util.mainWindow(), compare)
        accepted = dialog.exec_() == qt.QDialog.Accepted
        action = str(getattr(dialog, "action", "") or "") if accepted else ""
        if action == CompareWithSharedDialog.ACTION_UPDATE:
            self._applySharedVersionsUpdate(local_path, fetched=True)
            return
        conflict_lanes = list(getattr(dialog, "_conflict_lanes", None) or [])
        if not conflict_lanes:
            conflict_lanes = list((compare or {}).get("conflict_lanes") or [])
        reset_lanes = list(getattr(dialog, "_reset_lanes", None) or [])
        if not reset_lanes:
            reset_lanes = list((compare or {}).get("reset_lanes") or conflict_lanes)
        if action == CompareWithSharedDialog.ACTION_RESET:
            self._resetToSharedVersions(local_path, reset_lanes or conflict_lanes)
            return
        if action == CompareWithSharedDialog.ACTION_LINEAR:
            self._integrateSharedLinear(local_path, conflict_lanes)
            return
        # Cancel / Keep / Merge-coming: keep frozen tree + keep peek caps (no new remote tips in UI).
        if peek_caps is not None:
            save_remote_sync_caps(local_path, peek_caps)
        self._project_history_bundle = saved_bundle
        self._currentVersionId = saved_version_id
        self._unshared_version = saved_unshared
        self._updateCommitHistoryPanel()
        self._updateVersionActionButtons()
        self._updateNotificationsBadge()
        if action == CompareWithSharedDialog.ACTION_KEEP:
            self._appendFeed(
                "Kept your local versions. Version tree unchanged until you update."
            )

    def _applySharedVersionsUpdate(self, local_path: str, fetched: bool = False) -> None:
        """Rebuild the version tree from origin refs; does not change open assets."""
        project = self._currentProjectName()
        self._openProgress("Update from shared", "Updating version history…")
        try:
            if not fetched:
                self._updateProgress("Reading the shared project…")
                fetch_remote_updates(local_path)
            # Acknowledge current origin tips so Open/Version tree may show them.
            save_remote_sync_caps(local_path, capture_remote_sync_caps(local_path))
            self._updateProgress("Updating version history…")
            history = read_project_history(local_path)
            self._applyProjectHistoryBundle(history, follow_head=False)
            stamp = self._newestVersionsSyncStamp() or time.strftime(
                "%Y-%m-%dT%H:%M:%SZ", time.gmtime()
            )
            if project and stamp:
                self._persistReadCursor(project, versions_at=stamp)
        except (GitHubAuthError, OSError, RuntimeError, ValueError) as error:
            self._closeProgress()
            self._showGithubError(error, box=True)
            return
        self._closeProgress()
        unshared = self._historyHasUnsharedVersion(history)
        self._unshared_version = unshared
        self._updateCommitHistoryPanel()
        self._updateVersionActionButtons()
        self._updateNotificationsBadge()
        self._appendFeed("Updated the version tree from the shared project.")

    def _resetToSharedVersions(self, local_path: str, conflict_lanes=None) -> None:
        """Adopt shared tips for conflicting lanes only (others stay local)."""
        lanes = [
            str(name).strip()
            for name in (conflict_lanes or ())
            if str(name).strip()
        ] or ["main"]
        lanes_label = ", ".join(lanes)
        box = qt.QMessageBox(slicer.util.mainWindow())
        box.setWindowTitle("Reset to shared")
        box.setIcon(qt.QMessageBox.Warning)
        includes_main = any(str(name).strip().lower() == "main" for name in lanes)
        warn_main = (
            "\n\nWarning: main is included — unshared versions on main leave the tree."
            if includes_main
            else ""
        )
        box.setText(
            "Reset these branches to the shared tips?\n\n"
            "Branches: %s\n"
            "Other local branches stay unchanged.\n\n"
            "Warning: saved versions on the reset branches leave those lines."
            "%s"
            % (lanes_label, warn_main)
        )
        box.setStandardButtons(qt.QMessageBox.Ok | qt.QMessageBox.Cancel)
        box.button(qt.QMessageBox.Ok).setText("Reset to shared")
        box.setDefaultButton(qt.QMessageBox.Cancel)
        if box.exec_() != qt.QMessageBox.Ok:
            return
        project = self._currentProjectName()
        self._openProgress("Reset to shared", "Moving conflicting branches to shared…")
        try:
            self._updateProgress("Moving conflicting branches to shared…")
            adopt_shared_lanes(local_path, lanes)
            save_remote_sync_caps(local_path, capture_remote_sync_caps(local_path))
            self._updateProgress("Updating version history…")
            history = read_project_history(local_path)
            version_id = self._applyProjectHistoryBundle(history, follow_head=True)
            stamp = self._newestVersionsSyncStamp() or time.strftime(
                "%Y-%m-%dT%H:%M:%SZ", time.gmtime()
            )
            if project and stamp:
                self._persistReadCursor(project, versions_at=stamp)
        except (GitHubAuthError, OSError, RuntimeError, ValueError) as error:
            self._closeProgress()
            self._showGithubError(error, box=True)
            return
        self._closeProgress()
        unshared = self._historyHasUnsharedVersion(history)
        self._unshared_version = unshared
        self._updateCommitHistoryPanel()
        self._updateVersionActionButtons()
        self._updateNotificationsBadge()
        if version_id:
            self._appendFeed(
                "Reset conflicting branches (%s). Tip: %s." % (lanes_label, version_id)
            )
        else:
            self._appendFeed("Reset conflicting branches (%s)." % lanes_label)

    def _integrateSharedLinear(self, local_path: str, conflict_lanes=None) -> None:
        """Linear-integrate conflicting lanes only onto their shared tips."""
        lanes = [
            str(name).strip()
            for name in (conflict_lanes or ())
            if str(name).strip()
        ] or ["main"]
        lanes_label = ", ".join(lanes)
        box = qt.QMessageBox(slicer.util.mainWindow())
        box.setWindowTitle("Add shared, then mine")
        box.setIcon(qt.QMessageBox.Warning)
        box.setText(
            "On conflicting branches, add shared versions then keep yours on top?\n\n"
            "Branches: %s\n"
            "Other local branches stay unchanged.\n\n"
            "Warning: on those branches, your versions will be placed after the shared versions."
            % lanes_label
        )
        box.setStandardButtons(qt.QMessageBox.Ok | qt.QMessageBox.Cancel)
        box.button(qt.QMessageBox.Ok).setText("Add shared, then mine")
        box.setDefaultButton(qt.QMessageBox.Cancel)
        if box.exec_() != qt.QMessageBox.Ok:
            return
        project = self._currentProjectName()
        self._openProgress("Add shared, then mine", "Adding shared, then your work…")
        try:
            self._updateProgress("Adding shared, then your work…")
            integrate_shared_lanes(local_path, lanes)
            save_remote_sync_caps(local_path, capture_remote_sync_caps(local_path))
            self._updateProgress("Updating version history…")
            history = read_project_history(local_path)
            version_id = self._applyProjectHistoryBundle(history, follow_head=True)
            stamp = self._newestVersionsSyncStamp() or time.strftime(
                "%Y-%m-%dT%H:%M:%SZ", time.gmtime()
            )
            if project and stamp:
                self._persistReadCursor(project, versions_at=stamp)
        except (GitHubAuthError, OSError, RuntimeError, ValueError) as error:
            self._closeProgress()
            if is_offline_error(error):
                self._showGithubError(error, box=True)
                return
            detail = str(error).strip()
            first = detail.split("\n")[0]
            self._appendFeed(first, error=True)
            # Second line often has the real git reason.
            rest = "\n".join(detail.split("\n")[1:]).strip()
            if rest and not looks_like_offline_error(rest):
                self._appendFeed(rest.split("\n")[0], error=True)
            return
        self._closeProgress()
        unshared = self._historyHasUnsharedVersion(history)
        self._unshared_version = unshared
        self._updateCommitHistoryPanel()
        self._updateVersionActionButtons()
        self._updateNotificationsBadge()
        if version_id:
            self._appendFeed(
                "Added shared, then yours on %s. Tip: %s." % (lanes_label, version_id)
            )
        else:
            self._appendFeed("Added shared, then yours on %s." % lanes_label)

    def _openNotificationDetail(self, item: dict) -> None:
        detail = NotificationDetailDialog(
            slicer.util.mainWindow(),
            item,
            guidance=self._notificationGuidance(item),
        )
        detail.exec_()
        if str((item or {}).get("kind") or "") != "invite":
            return
        choice = str(getattr(detail, "choice", "") or "")
        if choice == "join":
            self._offering_invitations = True
            try:
                self._joinIncomingInvitation(item)
            finally:
                self._offering_invitations = False
                if self._connected:
                    self._runNotificationChecks(announce=False)
        elif choice == "decline":
            self._offering_invitations = True
            try:
                self._declineIncomingInvitation(item)
            finally:
                self._offering_invitations = False
                if self._connected:
                    self._runNotificationChecks(announce=False)

    def _currentNamedBranchSlug(self) -> str:
        local_path = getattr(self, "_local_project_path", None) or ""
        if not local_path:
            return ""
        try:
            return current_review_branch_slug(local_path) or ""
        except (GitHubAuthError, OSError, RuntimeError, ValueError):
            return ""

    def _notificationGuidance(self, item: dict) -> str:
        """Extra help under the notif body (role-specific for review requests)."""
        if str((item or {}).get("kind") or "") != "activity":
            return ""
        if str((item or {}).get("activity_kind") or "").strip().lower() != "submit":
            return ""
        branch = self._branchSlugFromSubmitNotification(item)
        branch_bit = (" on branch %s" % branch) if branch else ""
        if self._canAssignTask():
            return (
                "Open the Version tree, find the node marked 🔵 (awaiting review)%s, "
                "double-click it, then Accept or Decline."
                % branch_bit
            )
        return (
            "A teammate already requested a review%s. "
            "Wait for a senior — no need to request again. "
            "The Version tree shows 🔵 on that branch."
            % branch_bit
        )

    def _branchSlugFromSubmitNotification(self, item: dict) -> str:
        text = str((item or {}).get("text") or "")
        found = re.search(r"\bbranch\s+([A-Za-z0-9._-]+)", text, flags=re.IGNORECASE)
        if found:
            return normalize_branch_slug(found.group(1)) or found.group(1)
        for task in getattr(self, "_project_tasks", []) or []:
            if str(task.get("status") or "") != "submitted":
                continue
            slug = normalize_branch_slug(task.get("branch_slug") or "")
            if slug:
                return slug
        return ""

    def _activeTaskForBranchSlug(self, lane: str):
        """Active (non-accepted) task whose unified lane is this branch slug."""
        lane_key = normalize_branch_slug(lane) or str(lane or "").strip().lower()
        if not lane_key or lane_key == "main":
            return None
        for task in getattr(self, "_project_tasks", []) or []:
            if str(task.get("status") or "") == "accepted":
                continue
            slug = normalize_branch_slug((task or {}).get("branch_slug") or "")
            if slug and slug.lower() == lane_key:
                return task
        return None

    def _reviewPendingVersionIds(self) -> set:
        """Tip version ids of submitted task lanes (show 🔵 on the Version tree)."""
        pending_slugs = set()
        for task in getattr(self, "_project_tasks", []) or []:
            if str(task.get("status") or "") != "submitted":
                continue
            slug = normalize_branch_slug((task or {}).get("branch_slug") or "")
            if slug:
                pending_slugs.add(slug.lower())
        if not pending_slugs:
            return set()
        marked = set()
        for slug in pending_slugs:
            tip_id = self._tipVersionIdForLane(slug)
            if tip_id:
                marked.add(tip_id)
        return marked

    def _tipVersionIdForLane(self, lane: str) -> str:
        """Highest …/N (or …/start) id for this branch in the current history bundle."""
        lane_key = normalize_branch_slug(lane) or str(lane or "").strip().lower()
        if not lane_key:
            return ""
        best_id = ""
        best_rank = -1
        for spec in (
            (getattr(self, "_project_history_bundle", None) or {}).get("version_specs")
            or []
        ):
            if str((spec or {}).get("branch") or "").strip().lower() != lane_key:
                continue
            vid = str((spec or {}).get("id") or "").strip()
            if not vid:
                continue
            suffix = vid.rsplit("/", 1)[-1]
            if suffix == "start":
                rank = 0
            else:
                try:
                    rank = int(suffix)
                except ValueError:
                    rank = 0
            if rank >= best_rank:
                best_rank = rank
                best_id = vid
        return best_id

    def _taskRoleForLane(self, lane: str, *, network: bool = True):
        """Return submit/review role for a lane.

        ``network=False`` uses only local task fields (fast — for Version details
        dialog). ``network=True`` may query GitHub for open review PRs.
        """
        lane_key = normalize_branch_slug(lane) or str(lane or "").strip().lower()
        if not lane_key or lane_key == "main":
            return None
        me = (self._githubLogin() or "").strip().lower()
        if not me:
            return None
        current_slug = self._currentNamedBranchSlug().lower()
        own = None
        review = None
        full_name = self._currentProjectName()
        for task in getattr(self, "_project_tasks", []) or []:
            if str(task.get("status") or "") == "accepted":
                continue
            juniors = _task_junior_logins(task)
            senior = str(task.get("senior") or "").strip()
            if not juniors:
                continue
            junior_keys = {name.lower() for name in juniors}
            task_slug = normalize_branch_slug(task.get("branch_slug") or "").lower()
            status = str(task.get("status") or "").strip().lower()
            lane_matches = (task_slug and task_slug == lane_key) or (
                current_slug and lane_key == current_slug
            )
            if me in junior_keys:
                # Already submitted: no second Request review (🔵 shows the state).
                if status == "submitted":
                    continue
                if lane_matches:
                    own = task
                continue
            if senior.lower() != me:
                continue
            if task_slug == lane_key and status == "submitted":
                review = task
                continue
            if not network:
                continue
            try:
                req = find_open_review_request_for_branch(full_name, lane_key)
            except (GitHubAuthError, OSError, RuntimeError, ValueError):
                req = None
            author_key = str((req or {}).get("author") or "").strip().lower()
            if req and author_key in junior_keys:
                review = task
                continue
            for junior in juniors:
                try:
                    req2 = find_open_review_request(full_name, junior)
                except (GitHubAuthError, OSError, RuntimeError, ValueError):
                    req2 = None
                if not req2:
                    continue
                head = str(req2.get("branch") or "").strip()
                head_slug = head.split("/")[-1].lower() if head else ""
                if head_slug == lane_key:
                    review = task
                    break
        if own:
            return ("submit", own)
        if review:
            return ("review", review)
        return None

    def _openReviewForTask(self, task: dict, lane: str = "") -> dict | None:
        """Find an open review from any junior on this task (prefers the lane)."""
        lane_key = str(lane or "").strip()
        if lane_key and lane_key.lower() != "main":
            try:
                by_lane = find_open_review_request_for_branch(
                    self._currentProjectName(), lane_key
                )
            except (GitHubAuthError, OSError, RuntimeError, ValueError):
                by_lane = None
            if by_lane:
                author = str(by_lane.get("author") or "").strip().lower()
                if author in {name.lower() for name in _task_junior_logins(task)}:
                    return by_lane
        for junior in _task_junior_logins(task):
            request = self._openReviewForJunior(junior, lane=lane)
            if request:
                return request
        return None

    def _openReviewForJunior(self, junior: str, lane: str = "") -> dict | None:
        name = str(junior or "").strip()
        if not name:
            return None
        full_name = self._currentProjectName()
        lane_key = str(lane or "").strip()
        if lane_key and lane_key.lower() != "main":
            try:
                by_lane = find_open_review_request_for_branch(full_name, lane_key)
            except (GitHubAuthError, OSError, RuntimeError, ValueError):
                by_lane = None
            if by_lane:
                return by_lane
        for item in getattr(self, "_notifications", []) or []:
            if str(item.get("kind") or "") != "review":
                continue
            if str(item.get("full_name") or "").lower() != full_name.lower():
                continue
            author = str(item.get("author") or "").strip().lower()
            item_branch = str(item.get("branch") or "").strip().lower()
            if author == name.lower() and item_branch.startswith("cv-review/"):
                if not lane_key or item_branch.endswith("/" + lane_key.lower()):
                    return item
        try:
            return find_open_review_request(full_name, name)
        except (GitHubAuthError, OSError, RuntimeError, ValueError):
            return None

    def _isOwnReviewLane(self, lane: str) -> bool:
        key = str(lane or "").strip().lower()
        if not key or key == "main":
            return False
        current = self._currentNamedBranchSlug().lower()
        return bool(current and current == key)

    def _versionHistoryStatus(self, version_id: str) -> str:
        vid = str(version_id or "").strip()
        if not vid:
            return ""
        for row in (
            (getattr(self, "_project_history_bundle", None) or {}).get("commit_history")
            or []
        ):
            if not row or str(row[0] or "").strip() != vid:
                continue
            if len(row) > 4:
                return str(row[4] or "").strip().lower()
            return ""
        return ""

    def _canDeleteLocalUnsharedVersion(self, spec) -> bool:
        """True for any local (not shared) version on a lane — not stubs / shared."""
        if not self._projectDataIsLoaded():
            return False
        if (spec or {}).get("lane_start"):
            return False
        version_id = str((spec or {}).get("id") or "").strip()
        if not version_id:
            return False
        if self._versionHistoryStatus(version_id) != "local":
            return False
        # Juniors may only delete on their writable task lanes.
        if self._isVersionWriteLocked(version_id):
            return False
        return True

    def _withDeleteAction(self, payload: dict, spec) -> dict:
        out = dict(payload or {})
        if self._canDeleteLocalUnsharedVersion(spec):
            out["delete"] = True
            out["delete_note"] = (
                "Delete removes this version only on this computer. "
                "It works for any saved local version that is not shared yet "
                "(dashed border). Shared versions cannot be deleted."
            )
        return out

    def _reviewActionsForVersion(self, spec, history) -> dict:
        """Build Version-details actions from local state only (no GitHub round-trip)."""
        lane = str((spec or {}).get("branch") or "")
        # Task lanes first — never show bare "Merge" instead of Accept/Decline.
        task = self._activeTaskForBranchSlug(lane)
        if task is not None:
            return self._withDeleteAction(self._reviewActionsForTaskLane(task, lane), spec)
        # Owner / senior: merge their own shared line onto main (no task).
        if self._canAssignTask() and self._isOwnReviewLane(lane):
            return self._withDeleteAction({"merge": True}, spec)
        # Local task fields only — PR lookup happens when Accept/Decline is clicked.
        role = self._taskRoleForLane(lane, network=False)
        if not role:
            return self._withDeleteAction({}, spec)
        kind, linked = role
        if kind == "review":
            text = str(
                linked.get("submitted_description") or linked.get("description") or ""
            ).strip()
        else:
            text = str(linked.get("description") or "").strip()
        payload = {
            "task_text": text,
            "task_senior": str(linked.get("senior") or "").strip(),
        }
        if kind == "submit":
            payload["submit"] = True
            return self._withDeleteAction(payload, spec)
        payload["accept"] = True
        payload["decline"] = True
        return self._withDeleteAction(payload, spec)

    def _reviewActionsForTaskLane(self, task: dict, lane: str) -> dict:
        """Actions for a unified task branch (1 task = 1 lane). Local-only (fast)."""
        status = str((task or {}).get("status") or "").strip().lower()
        me = (self._githubLogin() or "").strip().lower()
        senior = str((task or {}).get("senior") or "").strip().lower()
        juniors = {name.lower() for name in _task_junior_logins(task)}
        text = str(
            (task.get("submitted_description") if status == "submitted" else "")
            or task.get("description")
            or ""
        ).strip()
        payload = {
            "task_text": text,
            "task_senior": str(task.get("senior") or "").strip(),
        }
        if status == "submitted":
            if self._canAssignTask() and senior and senior == me:
                # Show Accept/Decline immediately; resolve the open PR on click.
                payload["accept"] = True
                payload["decline"] = True
            return payload
        if me in juniors and status != "accepted":
            payload["submit"] = True
        return payload

    def onVersionReviewAction(self, action: str, spec) -> None:
        lane = str((spec or {}).get("branch") or "")
        if action == "delete":
            self._deleteLocalUnsharedVersion(spec)
            return
        task = self._activeTaskForBranchSlug(lane)
        role = self._taskRoleForLane(lane)
        if action == "merge":
            if task is not None:
                # Task lanes use Accept; Merge here still closes the task after merge.
                if not self._canAssignTask():
                    self._appendFeed("Only a senior can merge a task branch.", error=True)
                    return
                self._mergeOwnReviewLine(lane)
                return
            if not self._canAssignTask() or not self._isOwnReviewLane(lane):
                self._appendFeed("You can merge only your own branch.", error=True)
                return
            self._mergeOwnReviewLine(lane)
            return
        if action == "submit":
            if task is not None:
                if str(task.get("status") or "") == "submitted":
                    self._appendFeed(
                        "A review is already requested for this task (🔵 on the Version tree).",
                        error=True,
                    )
                    return
                role = ("submit", task)
            if not role or role[0] != "submit":
                self._appendFeed("You can request a review only on your own branch.", error=True)
                return
            self._submitOwnReviewLine(lane)
            return
        if action not in ("accept", "decline"):
            return
        review_task = task if task is not None else (role[1] if role and role[0] == "review" else None)
        if review_task is None:
            self._appendFeed(
                "You can Accept / Decline only a task you assigned.",
                error=True,
            )
            return
        me = (self._githubLogin() or "").strip().lower()
        senior = str(review_task.get("senior") or "").strip().lower()
        if not self._canAssignTask() or (senior and senior != me):
            self._appendFeed(
                "You can Accept / Decline only a task you assigned.",
                error=True,
            )
            return
        try:
            request = self._openReviewForTask(review_task, lane=lane)
        except (GitHubAuthError, OSError, RuntimeError, ValueError) as error:
            self._appendFeed(str(error).split("\n")[0], error=True)
            return
        if not request:
            if action == "accept" and task is not None:
                # No open PR — still finish the task lane via Merge (same as before).
                self._mergeOwnReviewLine(lane)
                return
            self._appendFeed("Nothing is waiting for review on this branch.", error=True)
            return
        junior = str(request.get("author") or "").strip() or "this junior"
        if action == "accept":
            confirmed = slicer.util.confirmYesNoDisplay(
                "Accept %s's version onto main and publish it to the shared project?"
                % junior,
                windowTitle="Accept",
            )
            if not confirmed:
                return
            if self._acceptReviewedShareRequest(request):
                # 1 task = 1 branch: Accept closes the task for every assigned junior.
                self._markTaskAccepted(review_task)
        else:
            confirmed = slicer.util.confirmYesNoDisplay(
                "Decline %s's branch?\n\nThe versions stay in the version tree." % junior,
                windowTitle="Decline",
            )
            if not confirmed:
                return
            self._declineReviewedShareRequest(request)
        self._updateActiveVersionIndicators()
        self._updateTaskButtonUi()

    def _deleteLocalUnsharedVersion(self, spec) -> None:
        """Remove a local unsaved-to-shared version (this computer only)."""
        if not self._canDeleteLocalUnsharedVersion(spec):
            self._appendFeed(
                "Delete is only for local versions that are not shared yet.",
                error=True,
            )
            return
        version_id = str((spec or {}).get("id") or "").strip()
        lane = str((spec or {}).get("branch") or "main").strip() or "main"
        display = self._versionDisplayTag(version_id)
        tip_id = self._tipVersionIdForLane(lane)
        middle_note = ""
        if tip_id and tip_id != version_id:
            middle_note = (
                "\n\nNewer local versions on this branch will be kept "
                "(same content, new ids may appear on the tree)."
            )
        confirmed = slicer.util.confirmYesNoDisplay(
            "Delete %s from this computer?\n\n"
            "This only removes a saved local version that is not shared yet.\n"
            "Shared versions cannot be deleted. This cannot be undone."
            "%s" % (display, middle_note),
            windowTitle="Delete version",
        )
        if not confirmed:
            return
        local_path = getattr(self, "_local_project_path", None) or ""
        bundle = getattr(self, "_project_history_bundle", None) or {}
        sha = str((bundle.get("sha_by_id") or {}).get(version_id) or "").strip()
        if not local_path or not sha:
            self._appendFeed("Could not delete that version.", error=True)
            return
        self._openProgress("Delete version", "Removing %s…" % display)
        try:
            self._updateProgress("Updating the local branch…")
            delete_local_unshared_version(local_path, sha, lane)
            self._updateProgress("Reloading project files…")
            self._loadOpenedProjectAssets(local_path, volume_folder=local_path)
            self._rememberProjectSceneNodes(
                self._selectorCurrentNode("volumeSelector"),
                self._selectorCurrentNode("segmentationSelector"),
            )
            self._syncAssetDataObservers()
            self._clearDirtyAssets()
            self._updateProgress("Updating version history…")
            history = read_project_history(local_path)
            version_id_after = self._applyProjectHistoryBundle(history, follow_head=True)
            self._unshared_version = self._historyHasUnsharedVersion(history)
        except (GitHubAuthError, OSError, RuntimeError, ValueError) as error:
            self._closeProgress()
            self._updateVersionActionButtons()
            self._showGithubError(error, box=True)
            return
        self._closeProgress()
        self._updateCommitHistoryPanel()
        self._updateActiveVersionIndicators()
        self._updateVersionActionButtons()
        self._armLoadSettle()
        if version_id_after:
            self._appendFeed(
                "Deleted %s (local only). Now on %s."
                % (display, self._versionDisplayTag(version_id_after))
            )
        else:
            self._appendFeed("Deleted %s (local only)." % display)
        # Refresh an open Version tree so the node disappears immediately.
        logic = getattr(self, "logic", None)
        dialog = getattr(logic, "historyDialog", None) if logic is not None else None
        if dialog is not None and _qt_widget_is_valid(dialog):
            qt.QTimer.singleShot(0, lambda: self.onOpenHistoryGraph(pick_mode=False))

    def _mergeOwnReviewLine(self, lane: str = "") -> None:
        """Senior/owner: put a shared named branch onto main (same merge as Accept)."""
        me = (self._githubLogin() or "").strip()
        if not me or not self._canAssignTask():
            self._appendFeed("Only a senior can merge their branch onto main.", error=True)
            return
        slug = normalize_branch_slug(lane) or self._currentNamedBranchSlug()
        if not slug:
            self._appendFeed("Switch to your branch first.", error=True)
            return
        task = self._activeTaskForBranchSlug(slug)
        confirmed = slicer.util.confirmYesNoDisplay(
            "Merge branch %s onto main and publish it to the shared project?" % slug,
            windowTitle="Merge",
        )
        if not confirmed:
            return
        request = {
            "full_name": self._currentProjectName(),
            "branch": review_branch_for(slug),
            "number": None,
            "author": me,
        }
        if self._acceptReviewedShareRequest(request):
            if task is not None and str(task.get("status") or "") != "accepted":
                # Merging a task lane closes the task for everyone assigned.
                self._markTaskAccepted(task)
            else:
                self._recordActivity(
                    self._currentProjectName(),
                    "accept",
                    "%s merged branch %s onto main." % (me or "Someone", slug),
                )
            self._updateActiveVersionIndicators()
            self._updateTaskButtonUi()

    def _showShareBranchBeforeReviewHint(self) -> None:
        """Junior tried Request review before Share — box + feed."""
        text = (
            "Share your branch first.\n\n"
            "Request review is only available after this version has been shared."
        )
        slicer.util.warningDisplay(text, windowTitle="Request review")
        self._appendFeed("Share your branch first.", error=True)

    def _submitOwnReviewLine(self, lane: str = "") -> None:
        slug = normalize_branch_slug(lane) or self._currentNamedBranchSlug()
        if not slug:
            self._showShareBranchBeforeReviewHint()
            return
        role = self._taskRoleForLane(slug)
        if not role or role[0] != "submit":
            self._appendFeed("You can request a review only on your own branch.", error=True)
            return
        task = role[1]
        description = str(task.get("description") or "").strip()
        if self._openReviewForJunior(self._githubLogin(), lane=slug):
            slicer.util.infoDisplay(
                "A review is already requested for this branch.",
                windowTitle="Review already requested",
            )
            return
        full_name = self._currentProjectName()
        self._openProgress("Request review", "Asking for a review…")
        try:
            self._updateProgress("Asking for a review…")
            outcome = submit_review_line(full_name, slug)
        except (GitHubAuthError, OSError, RuntimeError, ValueError) as error:
            self._closeProgress()
            detail = str(error).split("\n")[0].strip().lower()
            if "share" in detail and "branch" in detail:
                self._showShareBranchBeforeReviewHint()
            else:
                self._showGithubError(error, box=True)
            return
        self._closeProgress()
        if outcome == "updated":
            if str(task.get("status") or "") != "submitted":
                self._markTaskSubmitted(task, description)
            slicer.util.infoDisplay(
                "A review is already requested for this branch.",
                windowTitle="Review already requested",
            )
            return
        self._markTaskSubmitted(task, description)
        self._appendFeed("Review requested. This branch is not on main yet.")

    def _markTaskSubmitted(self, task: dict, description: str) -> None:
        juniors = _task_junior_logins(task)
        excerpt = _task_excerpt(description)
        body = (
            "requested a review for this task: %s" % excerpt
            if excerpt
            else "requested a review for this task."
        )
        try:
            message = build_project_message(self._githubLogin(), body, kind="task")
        except (GitHubAuthError, OSError, RuntimeError, ValueError) as error:
            self._appendFeed(str(error).split("\n")[0], error=True)
            return
        message["task_op"] = "submit"
        message["task_id"] = str((task or {}).get("id") or "")
        message["juniors"] = list(juniors)
        if juniors:
            message["junior"] = juniors[0]
        message["senior"] = str((task or {}).get("senior") or "")
        message["description"] = normalize_task_title(description)
        branch_slug = normalize_branch_slug((task or {}).get("branch_slug") or "")
        if branch_slug:
            message["branch_slug"] = branch_slug
        self._enqueueTaskMessage(message)
        self._updateTaskButtonUi()

    def _markTaskAccepted(self, task: dict) -> None:
        juniors = _task_junior_logins(task)
        description = str(
            (task or {}).get("submitted_description")
            or (task or {}).get("description")
            or ""
        ).strip()
        excerpt = _task_excerpt(description)
        body = (
            "accepted this task: %s" % excerpt if excerpt else "accepted this task."
        )
        try:
            message = build_project_message(self._githubLogin(), body, kind="task")
        except (GitHubAuthError, OSError, RuntimeError, ValueError) as error:
            self._appendFeed(str(error).split("\n")[0], error=True)
            return
        message["task_op"] = "accept"
        message["task_id"] = str((task or {}).get("id") or "")
        message["juniors"] = list(juniors)
        if juniors:
            message["junior"] = juniors[0]
        message["senior"] = str((task or {}).get("senior") or "")
        message["description"] = normalize_task_title(description)
        branch_slug = normalize_branch_slug((task or {}).get("branch_slug") or "")
        if branch_slug:
            message["branch_slug"] = branch_slug
        self._enqueueTaskMessage(message)
        self._updateTaskButtonUi()

    def _acceptReviewedShareRequest(self, request: dict) -> None:
        full_name = request.get("full_name") or ""
        author = request.get("author") or "the colleague"
        self._openProgress("Review version", "Adding the version to the project…")
        try:
            self._updateProgress("Adding the version to the project…")
            local_path = accept_share_request(full_name, request.get("branch") or "", request.get("number"))
            save_remote_sync_caps(local_path, capture_remote_sync_caps(local_path))
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
        if full_name:
            self._persistReadCursor(
                full_name,
                versions_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            )
        self._appendFeed("Accepted the version from %s. It is now on the project." % author)
        self._runNotificationChecks(announce=False)
        return True

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
        me = self._githubLogin() or "Someone"
        excerpt = self._taskExcerptForJunior(author)
        decline_text = (
            "%s declined %s's line for task: %s" % (me, author, excerpt)
            if excerpt
            else "%s declined %s's line." % (me, author)
        )
        self._recordActivity(
            request.get("full_name") or self._currentProjectName(),
            "decline",
            decline_text,
        )
        self._appendFeed(
            "Declined the version from %s. Their versions stay in the version tree." % author
        )
        self._refreshUiState()
        self._runNotificationChecks(announce=False)

    def _promptDeleteProjectChoice(self, full_name: str) -> str:
        """Return ``local``, ``remote_and_local``, or ``cancel``."""
        can_remote = self._canDeleteRemoteProject()
        local_only = self._isCurrentProjectLocalOnly()
        box = qt.QMessageBox(slicer.util.mainWindow())
        box.setWindowTitle("Delete project")
        box.setIcon(qt.QMessageBox.Warning)
        box.setText("Delete project %s?" % full_name)
        if can_remote:
            box.setInformativeText(
                "Choose what to remove. This cannot be undone.\n\n"
                "• This computer only — keeps the GitHub project.\n"
                "• GitHub and this computer — removes it for everyone.\n\n"
                "Project data loaded in 3D Slicer will be unloaded."
            )
            local_btn = box.addButton(
                "This computer only", qt.QMessageBox.AcceptRole
            )
            remote_btn = box.addButton(
                "GitHub and this computer", qt.QMessageBox.DestructiveRole
            )
            cancel_btn = box.addButton("Cancel", qt.QMessageBox.RejectRole)
            box.setDefaultButton(cancel_btn)
            box.exec_()
            clicked = box.clickedButton()
            if clicked == local_btn:
                return "local"
            if clicked == remote_btn:
                return "remote_and_local"
            return "cancel"
        if getattr(self, "_local_mode", False):
            box.setInformativeText(
                "Local mode — this removes the folder on this computer only.\n"
                "Connect with GitHub to delete a project on GitHub.\n\n"
                "Project data loaded in 3D Slicer will be unloaded."
            )
        elif local_only:
            box.setInformativeText(
                "This project is not on GitHub.\n\n"
                "The folder on this computer will be removed.\n"
                "Project data loaded in 3D Slicer will be unloaded."
            )
        else:
            box.setInformativeText(
                "Only the owner can delete this project on GitHub.\n\n"
                "This removes the folder on this computer only.\n"
                "The GitHub project is not deleted.\n\n"
                "Project data loaded in 3D Slicer will be unloaded."
            )
        box.setStandardButtons(qt.QMessageBox.Yes | qt.QMessageBox.No)
        box.setDefaultButton(qt.QMessageBox.No)
        if box.exec_() != qt.QMessageBox.Yes:
            return "cancel"
        return "local"

    def _resolveDeleteLocalPath(self, full_name: str) -> str:
        """Folder for the *selected* project name — not whatever is currently open."""
        name = str(full_name or "").strip()
        if not name:
            return ""
        loaded = str(getattr(self, "_loaded_project_name", None) or "").strip()
        path = str(getattr(self, "_local_project_path", None) or "").strip()
        if (
            loaded
            and loaded.lower() == name.lower()
            and path
            and os.path.isdir(path)
        ):
            return path
        try:
            login = self._githubLogin() or None
            dest = local_project_dir(name, login)
        except (GitHubAuthError, OSError, TypeError, ValueError):
            return ""
        return dest if dest and os.path.isdir(dest) else ""

    def _deleteRemoteProjectWithPermission(self, full_name: str) -> bool:
        """Delete GitHub repo only. Returns False if cancelled or failed."""
        if has_delete_repo_scope() is False:
            if not self._authorizeDeletePermission():
                return False
        try:
            self._updateProgress("Deleting the GitHub project…")
            delete_remote_owned_repository(full_name)
            return True
        except GitHubMissingDeletePermissionError:
            self._closeProgress()
            if not self._authorizeDeletePermission():
                self._updateVersionActionButtons()
                return False
            self._openProgress("Delete project", "Deleting %s…" % full_name)
            try:
                self._updateProgress("Deleting the GitHub project…")
                delete_remote_owned_repository(full_name)
                return True
            except GitHubAuthError as error:
                self._closeProgress()
                self._updateVersionActionButtons()
                self._showGithubError(error, box=True)
                return False
        except GitHubAuthError as error:
            self._closeProgress()
            self._updateVersionActionButtons()
            self._showGithubError(error, box=True)
            return False

    def _clearUiAfterProjectRemoved(self, full_name: str, *, drop_list_entry: bool) -> None:
        name = str(full_name or "").strip()
        if drop_list_entry and self._github_session is not None and name:
            repos = list((self._github_session or {}).get("repos") or [])
            self._github_session["repos"] = [
                item for item in repos if item.get("full_name") != name
            ]
        loaded = str(getattr(self, "_loaded_project_name", None) or "").strip()
        deleting_open = bool(
            name and loaded and name.lower() == loaded.lower()
        )
        if deleting_open:
            self._currentVersionId = None
            self._server_pulled = False
            self._updateProgress("Unloading data from 3D Slicer…")
            self._unloadProjectSceneNodes()
            self._loaded_project_name = None
            self._local_project_path = None
            self._project_scene_node_ids = []
            self._clearChangeFlags()
            try:
                self.removeObservers(self._onAssetDataModified)
            except Exception:
                pass
        self._closeProgress()
        if not deleting_open and loaded:
            # Combo still shows the deleted name — point it at the open project
            # so _populateProjectCombo restores that selection.
            self.projectCombo.blockSignals(True)
            try:
                for index in range(_qt_combo_count(self.projectCombo)):
                    try:
                        data = str(self.projectCombo.itemData(index) or "").strip()
                    except (AttributeError, RuntimeError, TypeError, ValueError):
                        data = ""
                    if data.lower() == loaded.lower():
                        self.projectCombo.setCurrentIndex(index)
                        break
            finally:
                self.projectCombo.blockSignals(False)
            self._populateProjectCombo()
        else:
            self._populateProjectCombo()
            self._clearProjectSelection()
        self._refreshUiState()

    def onDeleteProject(self) -> None:
        if not self._canDeleteProject():
            reason = self._deleteDisabledReason()
            if reason:
                self._showActionUnavailable(reason)
            return
        full_name = self._currentProjectName()
        choice = self._promptDeleteProjectChoice(full_name)
        if choice == "cancel":
            return
        delete_remote = choice == "remote_and_local"
        drop_list_entry = delete_remote or self._isCurrentProjectLocalOnly()
        local_path = self._resolveDeleteLocalPath(full_name)
        if not delete_remote and not local_path:
            try:
                slicer.util.warningDisplay(
                    "No local folder found for this project on this computer.",
                    windowTitle="Delete project",
                )
            except TypeError:
                slicer.util.warningDisplay(
                    "No local folder found for this project on this computer."
                )
            return
        self.deleteButton.setEnabled(False)
        if delete_remote:
            self._appendFeed("Deleting project %s on GitHub and this computer…" % full_name)
        else:
            self._appendFeed("Removing local copy of %s…" % full_name)
        self._openProgress("Delete project", "Deleting %s…" % full_name)
        if delete_remote:
            if not self._deleteRemoteProjectWithPermission(full_name):
                return
        try:
            if local_path:
                self._updateProgress("Removing the local folder…")
                remove_local_project_dir(local_path)
        except (GitHubAuthError, OSError, RuntimeError, ValueError) as error:
            self._closeProgress()
            self._updateVersionActionButtons()
            self._showGithubError(error, box=True)
            if delete_remote:
                # Remote already gone — still clear UI so the list matches GitHub.
                self._clearUiAfterProjectRemoved(
                    full_name, drop_list_entry=True
                )
                self._appendFeed(
                    "GitHub project deleted, but the local folder could not be removed.",
                    error=True,
                )
            return
        self._clearUiAfterProjectRemoved(full_name, drop_list_entry=drop_list_entry)
        if delete_remote:
            self._appendFeed("Project deleted on GitHub and this computer: %s" % full_name)
        else:
            self._appendFeed("Local copy removed: %s" % full_name)

    def _authorizeDeletePermission(self) -> bool:
        try:
            open_delete_permission_window()
        except GitHubAuthError as error:
            self._showGithubError(error, box=True)
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
        if not self._hasWorkspaceSession():
            self._showConnectRequired()
            return
        if self._warnIfWriteLocked("Save"):
            return
        if not self._canSaveVersion():
            reason = self._saveVersionDisabledReason()
            if reason:
                self._showActionUnavailable(reason)
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
        on_branch = False
        from_older_main = False
        try:
            on_branch = work_is_on_review_branch(local_path)
            if not on_branch:
                from_older_main = is_viewing_older_than_branch_tip(local_path, "main")
        except (GitHubAuthError, OSError, RuntimeError, ValueError):
            on_branch = False
            from_older_main = False
        new_branch_slug = ""
        if not on_branch:
            # Junior: Create a branch only (cannot Share from main).
            destination = self._promptSaveDestination(
                from_older_main=from_older_main,
                junior=self._shareNeedsApproval(),
            )
            if destination == "cancel":
                self._appendFeed("Save cancelled.")
                return
            if destination == "branch":
                new_branch_slug = self._promptBranchName()
                if not new_branch_slug:
                    self._appendFeed("Save cancelled.")
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
            if new_branch_slug:
                self._updateProgress("Creating branch %s…" % new_branch_slug)
                start_local_review_branch(local_path, new_branch_slug)
            self._updateProgress("Saving the version…")
            commit_local_version(local_path, message)
            self._updateProgress("Updating version history…")
            history = read_project_history(local_path)
            version_id = self._applyProjectHistoryBundle(history, follow_head=True)
            self._clearDirtyAssets()
            self._unshared_version = True
            self._syncAssetDataObservers()
            self._closeProgress()
            self._refreshUiState()
        except (GitHubAuthError, OSError, RuntimeError, ValueError) as error:
            self._closeProgress()
            self._updateVersionActionButtons()
            self._showGithubError(error, box=True)
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
        if new_branch_slug:
            self._appendFeed(
                "Saved on branch %s (local only until you Share)." % new_branch_slug
            )

    def onShare(self) -> None:
        if not self._connected:
            self._showConnectRequired()
            return
        if self._warnIfWriteLocked("Share"):
            return
        if not self._canShare():
            reason = self._shareDisabledReason()
            if reason:
                self._showActionUnavailable(reason)
            return
        local_path = getattr(self, "_local_project_path", None) or ""
        if not local_path or not os.path.isdir(os.path.join(local_path, ".git")):
            self._appendFeed("Open the project first.", error=True)
            return
        on_branch = False
        try:
            on_branch = work_is_on_review_branch(local_path)
        except (GitHubAuthError, OSError, RuntimeError, ValueError):
            on_branch = False
        # Juniors publish a branch only (main stays for seniors / Merge-Accept).
        if self._shareNeedsApproval() and not on_branch:
            self._appendFeed(
                "Save on a branch first (Create a branch), then Share.",
                error=True,
            )
            self._updateVersionActionButtons()
            return
        if not self._confirmShareCurrentLine(local_path):
            self._appendFeed("Share cancelled.")
            self._updateVersionActionButtons()
            return
        self.shareButton.setEnabled(False)
        self._publishCurrentLine(local_path)

    def _publishCurrentLine(self, local_path: str) -> None:
        """Push only the current branch (main or another branch) to the shared project."""
        try:
            on_branch = work_is_on_review_branch(local_path)
            slug = current_review_branch_slug(local_path) if on_branch else ""
        except (GitHubAuthError, OSError, RuntimeError, ValueError):
            on_branch = False
            slug = ""
        branch = slug or "main"
        self._appendFeed("Sharing %s…" % branch)
        self._openProgress("Share", "Publishing %s…" % branch)
        history = {}
        published = branch
        try:
            # Strict: fetch + refuse if shared is ahead / tips diverged (Update first).
            local_freeze = copy.deepcopy(
                getattr(self, "_project_history_bundle", None)
            )
            self._updateProgress("Checking the shared project…")
            ensure_can_share_with_shared(local_path, local_history=local_freeze)
            self._updateProgress("Publishing %s…" % branch)
            published = publish_current_line(local_path)
            save_remote_sync_caps(local_path, capture_remote_sync_caps(local_path))
            self._updateProgress("Updating version history…")
            history = read_project_history(local_path)
        except (GitHubAuthError, OSError, RuntimeError, ValueError) as error:
            self._closeProgress()
            self._updateVersionActionButtons()
            self._showGithubError(error, box=True)
            return
        unshared = self._historyHasUnsharedVersion(history)
        self._applyProjectHistoryBundle(history, follow_head=True)
        self._unshared_version = unshared
        self._closeProgress()
        self._refreshUiState()
        self._unshared_version = unshared
        self._updateVersionActionButtons()
        me = self._githubLogin() or "Someone"
        if published == "main":
            self._appendFeed("Shared on main.")
            share_event = self._buildActivityEvent(
                "share", "%s shared versions on main." % me
            )
        else:
            label = published or branch
            self._appendFeed("Shared on branch %s." % label)
            share_event = self._buildActivityEvent(
                "share", "%s shared versions on branch %s." % (me, label)
            )
            slicer.util.infoDisplay(
                self._shareLineNextStepMessage(),
                windowTitle="Share",
            )
        if self._unsaved_changes:
            self._appendFeed(
                "Unsaved changes are still on this computer. Save a version if you want them shared later."
            )
        if share_event:
            self._recordActivity(self._currentProjectName(), event=share_event)

    def _activeTasksAsJunior(self) -> list:
        me = (self._githubLogin() or "").strip().lower()
        if not me:
            return []
        found = []
        for task in getattr(self, "_project_tasks", []) or []:
            if str(task.get("status") or "") == "accepted":
                continue
            if me in {login.lower() for login in _task_junior_logins(task)}:
                found.append(task)
        return found

    def _hasActiveTaskAsJunior(self) -> bool:
        return bool(self._activeTasksAsJunior())

    def _juniorWriteLockApplies(self) -> bool:
        """Seniors are unrestricted; everyone else follows task write-lock rules."""
        if not self._projectDataIsLoaded():
            return False
        # Use snapshot/online senior rights — not Assign (Assign needs Connected).
        if self._hasSeniorProjectAccess():
            return False
        return True

    def _writableTaskLaneSlugs(self):
        """None = no locks. Empty set = lock all writes. Else only those lane slugs."""
        if not self._juniorWriteLockApplies():
            return None
        slugs = set()
        for task in self._activeTasksAsJunior():
            slug = normalize_branch_slug((task or {}).get("branch_slug") or "")
            if slug:
                slugs.add(slug.lower())
        return slugs

    def _isVersionWriteLocked(self, version_id: str) -> bool:
        allowed = self._writableTaskLaneSlugs()
        if allowed is None:
            return False
        lane = (self._historyLaneForVersion(version_id) or "main").strip().lower()
        if not lane or lane == "main":
            return True
        return lane not in allowed

    def _isCurrentVersionWriteLocked(self) -> bool:
        return self._isVersionWriteLocked(
            str(getattr(self, "_currentVersionId", None) or "")
        )

    def _writeLockedVersionIds(self) -> set:
        allowed = self._writableTaskLaneSlugs()
        if allowed is None:
            return set()
        locked = set()
        for spec in (
            (getattr(self, "_project_history_bundle", None) or {}).get("version_specs")
            or []
        ):
            vid = str((spec or {}).get("id") or "").strip()
            if not vid:
                continue
            branch = str((spec or {}).get("branch") or "main").strip().lower() or "main"
            if branch == "main" or branch not in allowed:
                locked.add(vid)
        return locked

    def _writeLockBlockedReason(self, action: str = "Save") -> str:
        verb = str(action or "Save").strip() or "Save"
        if self._hasActiveTaskAsJunior():
            return (
                "%s is blocked here (🔒 view only). "
                "Switch to your task branch to %s."
                % (verb, verb.lower())
            )
        return (
            "%s is blocked (🔒 view only). "
            "Ask a senior to Assign you a task first."
            % verb
        )

    def _warnIfWriteLocked(self, action: str = "Save") -> bool:
        """If current version is write-locked, show a box and return True."""
        if not self._isCurrentVersionWriteLocked():
            return False
        message = self._writeLockBlockedReason(action)
        try:
            slicer.util.warningDisplay(message, windowTitle="View only")
        except TypeError:
            slicer.util.warningDisplay(message)
        self._appendFeed(message, error=True)
        return True

    def _shareLineNextStepMessage(self) -> str:
        if self._canAssignTask():
            return (
                "Shared on your branch. If you want to put it on main, open that "
                "branch in the version tree and Merge."
            )
        if self._hasActiveTaskAsJunior():
            return (
                "Shared on your branch. Next: open that branch in the version "
                "tree → Request review."
            )
        return (
            "Shared on your branch. To request a review, ask a senior to "
            "Assign you a task first."
        )

    def _positionTaskBadge(self) -> None:
        button = getattr(self, "messagesTaskButton", None)
        badge = getattr(self, "taskBadge", None)
        if button is None or badge is None or not _qt_widget_is_valid(button):
            return
        try:
            width = button.width
            if callable(width):
                width = width()
            badge.move(max(8, int(width) - 22), 8)
            badge.raise_()
        except (AttributeError, RuntimeError, TypeError, ValueError):
            pass

    def _taskButtonAccentStyle(self) -> str:
        accent = ACCENT_ICE or "#5b9fd4"
        on_accent = TEXT_ON_ICE or "#0f172a"
        return (
            "QPushButton {"
            " background-color: palette(button); color: palette(button-text);"
            " border: 2px solid %s; font-weight: 700;"
            " border-radius: 4px; padding: 6px 10px;"
            "}"
            "QPushButton:hover {"
            " background-color: %s; border-color: %s; color: %s;"
            "}"
            "QPushButton:pressed {"
            " background-color: %s; border-color: %s; color: %s;"
            "}"
            % (accent, accent, accent, on_accent, accent, accent, on_accent)
        )

    def _updateTaskButtonUi(self) -> None:
        button = getattr(self, "messagesTaskButton", None)
        badge = getattr(self, "taskBadge", None)
        if button is None:
            return
        if not self._hasWorkspaceSession():
            button.setText("Tasks")
            button.setStyleSheet(BTN_SECONDARY)
            button.setToolTip("Connect with GitHub first.")
            if badge is not None:
                badge.hide()
            return
        button.setStyleSheet(self._taskButtonAccentStyle())
        button.setText("Tasks")
        if not self._hasSelectedProject():
            button.setToolTip("Select a project first.")
            if badge is not None:
                badge.hide()
            return
        if not self._projectDataIsLoaded():
            button.setToolTip("Open the project first.")
            if badge is not None:
                badge.hide()
            return
        # Senior online can Assign; local mode / junior: browse tasks only.
        if self._canAssignTask():
            button.setToolTip("Tasks")
            if badge is not None:
                badge.hide()
            return
        if self._projectUsesLocalInfoOnly():
            # Same as People: local_mode overrides local_only tagging.
            if getattr(self, "_local_mode", False):
                tip = (
                    "Tasks (local mode) — Assign needs Connect with GitHub."
                    if self._hasSeniorProjectAccess()
                    else "Tasks (local mode) — view only."
                )
            elif self._isCurrentProjectLocalOnly():
                tip = (
                    "Tasks (not on GitHub) — Assign unavailable for this project."
                    if self._hasSeniorProjectAccess()
                    else "Tasks (not on GitHub) — view only."
                )
            elif self._hasSeniorProjectAccess():
                tip = "Tasks (local mode) — Assign needs Connect with GitHub."
            else:
                tip = "Tasks (local mode) — view only."
            button.setToolTip(tip)
            mine = self._activeTasksAsJunior()
            if badge is not None:
                if mine:
                    badge.setText(str(len(mine)))
                    badge.show()
                    badge.raise_()
                    self._positionTaskBadge()
                else:
                    badge.hide()
            return
        mine = self._activeTasksAsJunior()
        if not mine:
            button.setToolTip("No active task — wait for a senior to Assign you one.")
            if badge is not None:
                badge.hide()
            return
        if len(mine) == 1:
            task = mine[0]
            excerpt = _task_excerpt(
                task.get("submitted_description") or task.get("description") or ""
            )
            senior = str(task.get("senior") or "").strip()
            if excerpt and senior:
                tip = "%s (Assigned by %s)" % (excerpt, senior)
            elif excerpt:
                tip = excerpt
            elif senior:
                tip = "Assigned by %s" % senior
            else:
                tip = "You have an active task"
        else:
            tip = "You have %d active tasks — open Tasks to see them." % len(mine)
        button.setToolTip(tip)
        if badge is not None:
            badge.setText(str(len(mine)))
            badge.show()
            badge.raise_()
            self._positionTaskBadge()

    def onOpenProject(self) -> None:
        if not self._canOpenProject():
            reason = self._openDisabledReason()
            if reason:
                self._showActionUnavailable(reason)
            return
        full_name = self._currentProjectName()
        self.openButton.setEnabled(False)
        self._appendFeed("Opening project %s…" % full_name)
        # Show progress immediately — path/login checks below must not delay the box.
        self._openProgress("Open project", "Opening %s…" % full_name)
        try:
            # Already cloned → open local only (no silent fetch). Remote updates go via
            # notifications → Compare with shared. First time → clone.
            # Use session login (no network) + cheap .git check (no unpushed scan).
            login = str((self._github_session or {}).get("login") or "").strip()
            try:
                dest = local_project_dir(full_name, login or None)
                local_exists = os.path.isdir(os.path.join(dest, ".git"))
            except (GitHubAuthError, OSError, TypeError, ValueError):
                local_exists = False
            local_only = False
            for repo in (getattr(self, "_github_session", None) or {}).get("repos") or []:
                if (repo or {}).get("full_name") == full_name:
                    local_only = bool((repo or {}).get("local_only"))
                    break
            if (getattr(self, "_local_mode", False) or local_only) and not local_exists:
                self._closeProgress()
                self._updateVersionActionButtons()
                self._appendFeed(
                    "This project is not on this computer. "
                    "Connect with GitHub first to download it."
                    if not local_only
                    else "This project is not on GitHub and the local folder is missing.",
                    error=True,
                )
                return
            # (not shared) / offline local: open disk copy only — never clone/fetch.
            choice = "local" if (local_exists or local_only) else "update"
            if local_only:
                choice = "local"
            progress_label = (
                "Opening this computer's work…"
                if choice == "local"
                else "Opening %s…" % full_name
            )
            self._updateProgress(progress_label)
            # Drop previous project's scene nodes only (files stay on disk / GitHub).
            self._updateProgress("Unloading previous data from 3D Slicer…")
            self._unloadProjectSceneNodes()
            self._updateProgress(progress_label)
            local_path = open_or_update_local_project(full_name, mode=choice)
            loaded = self._loadOpenedProjectAssets(local_path)
            self._updateProgress("Reading version history…")
            history = read_project_history(local_path)
        except (GitHubAuthError, OSError, RuntimeError, ValueError) as error:
            self._closeProgress()
            self._updateVersionActionButtons()
            self._showGithubError(error, box=True)
            return
        unshared = self._historyHasUnsharedVersion(history)
        self._suppress_dirty += 1
        self._suppress_asset_ui_updates += 1
        try:
            self._loaded_project_name = full_name
            self._local_project_path = local_path
            self._server_pulled = True
            self._applyProjectHistoryBundle(history)
            self._rememberProjectSceneNodes(
                self._selectorCurrentNode("volumeSelector"),
                self._selectorCurrentNode("segmentationSelector"),
            )
            self._clearChangeFlags()
            self._unshared_version = unshared
            self._syncAssetDataObservers()
            # Always seed from local project-info first (same path as local mode /
            # not shared). Connected poll may refresh afterward if the network works.
            self._applyLocalProjectInfoSnapshot(
                local_path,
                full_name,
                disable_notifications=(
                    getattr(self, "_local_mode", False) and not self._connected
                ),
            )
            if self._connected and not local_only:
                try:
                    # Fresher role from GitHub only when people.json is readable.
                    # Missing/deleted remote → None → keep local snapshot (avoid fake Junior).
                    remote_access = remote_people_access_or_none(
                        full_name, self._githubLogin()
                    )
                    if remote_access is not None:
                        self._rememberPeopleAccess(full_name, remote_access)
                except (GitHubAuthError, OSError, RuntimeError, ValueError):
                    pass
        finally:
            self._suppress_asset_ui_updates -= 1
            self._suppress_dirty -= 1
        self._closeProgress()
        # Online Open of a real GitHub project: first Messages poll may show behind.
        if self._connected and not local_only:
            self._pending_versions_behind_hint = True
        self._refreshUiState()
        self._clearChangeFlags()
        self._unshared_version = unshared
        self._updateVersionActionButtons()
        self._armLoadSettle()
        # First clone fetched shared refs — mark versions sync current.
        if choice != "local" and full_name and self._connected and not local_only:
            self._persistReadCursor(
                full_name,
                versions_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            )
        self._appendFeed("Project opened: %s" % full_name)
        self._appendFeed("Opened this computer's copy.")
        if unshared:
            self._appendFeed("Some versions on this computer are not shared yet.")
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

    def _applyLocalProjectInfoSnapshot(
        self,
        local_path: str,
        full_name: str,
        *,
        disable_notifications: bool = True,
    ) -> None:
        """One-shot read of local project-info (messages, tasks, people). No API.

        Used for every Open. Sets ``_messages_project`` so a following Connected
        poll sync does not wipe this seed when the network fails.
        """
        login = str((self._github_session or {}).get("login") or self._githubLogin() or "").strip()
        try:
            info = read_local_project_info(local_path or "", full_name, login)
        except (GitHubAuthError, OSError, RuntimeError, ValueError, TypeError):
            info = {
                "ref": "",
                "messages": [],
                "tasks": [],
                "activity": [],
                "reads": {},
                "presence": {},
                "people": [],
                "my_access": PEOPLE_ACCESS_JUNIOR,
            }
        self._local_project_people = list(info.get("people") or [])
        access = str(info.get("my_access") or PEOPLE_ACCESS_JUNIOR)
        try:
            self._rememberPeopleAccess(full_name, access)
        except (GitHubAuthError, OSError, RuntimeError, ValueError):
            pass
        # Mark active before apply so _syncMessagesPolling won't reset this seed.
        self._messages_project = str(full_name or "").strip()
        self._applyProjectMessages(
            list(info.get("messages") or []),
            tasks=list(info.get("tasks") or []),
            activity=list(info.get("activity") or []),
            reads=info.get("reads") or {},
            presence=dict(info.get("presence") or {}),
            refresh_ui=True,
            announce_activity=False,
        )
        if disable_notifications:
            # Full offline local mode: bell off.
            self._notification_invites = []
            self._notification_activity = []
            self._clearNotificationsDisplay()
            self._setNotificationsEnabled(False)
        elif self._projectUsesLocalInfoOnly():
            # Connected (not shared): keep invite notifs; no project activity in bell.
            self._notification_activity = []
            self._rebuildNotificationsDisplay()
        if info.get("ref"):
            self._appendFeed(
                "Loaded project info from this computer "
                "(messages, tasks, people)."
            )
        else:
            self._appendFeed(
                "No local project-info snapshot yet — "
                "role defaults applied; Connect with GitHub to refresh."
            )

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
        # Same folder was already scanned — only look elsewhere if volume is missing there.
        if (
            not volume_path
            and volume_folder
            and os.path.normpath(volume_folder) != os.path.normpath(folder)
        ):
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
                    # Load directly from the project file (no cv_load_ temp copy).
                    segmentation_node = manager.load_segmentation(
                        segmentation_path,
                        isolate=False,
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

    def _historyLaneForVersion(self, version_id: str) -> str:
        bundle = getattr(self, "_project_history_bundle", None) or {}
        for spec in bundle.get("version_specs") or []:
            if str((spec or {}).get("id") or "") == str(version_id or ""):
                return str((spec or {}).get("branch") or "main") or "main"
        return "main"

    def _checkoutVersion(
        self,
        version_id: str,
        notify: bool = False,
        sync_table: bool = True,
        prompt: bool = True,
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
        if prompt and not self._promptSwitchVersion(version_id):
            self._appendFeed("Switch version cancelled.")
            return False
        bundle = getattr(self, "_project_history_bundle", None) or {}
        sha = (bundle.get("sha_by_id") or {}).get(version_id)
        local_path = getattr(self, "_local_project_path", None) or ""
        if not sha or not local_path:
            self._appendFeed(
                "Could not switch to %s." % self._versionDisplayTag(version_id),
                error=True,
            )
            return False
        lane = "main"
        for spec in bundle.get("version_specs") or []:
            if str((spec or {}).get("id") or "") == str(version_id):
                lane = str((spec or {}).get("branch") or "main")
                break
        display = self._versionDisplayTag(version_id)
        previous_id = self._currentVersionId
        self._suppress_history_selection_signal = True
        try:
            self._currentVersionId = version_id
            self._updateActiveVersionIndicators()
            self._selectHistoryRowForVersion(version_id)
            self._openProgress("Switch version", "Loading %s…" % display)
            try:
                checkout_local_version(local_path, sha, lane)
                # Load from the project folder (volume untouched; seg/ontology restored above).
                # volume_folder=local_path keeps soft reload: reuse volume + inject seg, no temp copy.
                # Ontology combo is set inside _loadOpenedProjectAssets — no second discover.
                self._loadOpenedProjectAssets(local_path, volume_folder=local_path)
                self._rememberProjectSceneNodes(
                    self._selectorCurrentNode("volumeSelector"),
                    self._selectorCurrentNode("segmentationSelector"),
                )
                self._syncAssetDataObservers()
                self._clearDirtyAssets()
            except (GitHubAuthError, OSError, RuntimeError, ValueError) as error:
                self._currentVersionId = previous_id
                self._updateActiveVersionIndicators()
                if previous_id:
                    self._selectHistoryRowForVersion(previous_id)
                try:
                    self._loadOpenedProjectAssets(local_path)
                    self._rememberProjectSceneNodes(
                        self._selectorCurrentNode("volumeSelector"),
                        self._selectorCurrentNode("segmentationSelector"),
                    )
                    self._syncAssetDataObservers()
                    self._clearDirtyAssets()
                except Exception:
                    pass
                self._showGithubError(error, box=True)
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
        self._armLoadSettle()
        return True

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
                bundle = getattr(self, "_project_history_bundle", None) or {}
                specs = list(bundle.get("version_specs") or [])
                if specs and hasattr(canvas, "version_specs"):
                    canvas.version_specs = specs
                    canvas._specs_by_id = {spec["id"]: spec for spec in specs}
                    canvas.commit_history_by_id = CollaborativeVersioningLib.GraphCanvas.commit_history_lookup(
                        bundle.get("commit_history", [])
                    )
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

    def onOpenHistoryGraph(self, pick_mode: bool = False, parent=None) -> None:
        if not self._canOpenVersionTree():
            payload = self.getVersionTreePayload()
            self._appendFeed(payload["description"], error=True)
            if pick_mode:
                self._task_anchor_picking = False
                dialog = getattr(self, "_open_task_dialog", None)
                if dialog is not None:
                    dialog.set_status(payload["description"], error=True)
            return
        self.logic.openVersionHistoryGraph(
            pick_mode=bool(pick_mode),
            parent=parent,
        )

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

    def _styleHistoryCell(self, item: qt.QTableWidgetItem, column: int, version_id: str = "") -> None:
        if column == 0:
            lane = self._historyLaneForVersion(
                version_id or self._historyVersionIdFromItem(item)
            )
            color = CollaborativeVersioningLib.GraphCanvas.branch_color(lane) or TEXT_MUTED
            item.setForeground(qt.QColor(color))
            font = item.font()
            font.setBold(True)
            item.setFont(font)
        elif column == 2:
            item.setForeground(qt.QColor(TEXT_SECONDARY))

    def _refreshHistoryTable(self) -> None:
        bundle = getattr(self, "_project_history_bundle", None) or {}
        commit_history = bundle.get("commit_history", [])
        # Same lane→color map as the Version tree (unique among displayed branches).
        CollaborativeVersioningLib.GraphCanvas.prepare_branch_colors(
            (spec or {}).get("branch", "main")
            for spec in (bundle.get("version_specs") or [])
        )
        self.historyTableWidget.setRowCount(len(commit_history))
        for row_index, row_values in enumerate(commit_history):
            version_id = row_values[0]
            # Table shows Version / Date / Author / Message only (status = dashed box on graph).
            for column_index, value in enumerate(row_values[:4]):
                if column_index == 0:
                    display = self._versionDisplayTag(version_id)
                    item = qt.QTableWidgetItem(display)
                    item.setData(qt.Qt.UserRole, version_id)
                else:
                    item = qt.QTableWidgetItem(str(value))
                self._styleHistoryCell(item, column_index, version_id=version_id)
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

    def _appendFeed(self, message: str, error: bool = False, *, force: bool = False) -> None:
        # Unify technical offline/DNS errors into one readable feed line.
        # Throttle only background spam (force=False); each user click uses force=True.
        if error and looks_like_offline_error(message):
            message = offline_message().split("\n")[0]
            if not force:
                now = time.time()
                last = float(getattr(self, "_last_offline_feed_at", 0.0) or 0.0)
                if (now - last) < 8.0:
                    return
                self._last_offline_feed_at = now
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
        if getattr(widget, "_task_anchor_picking", False):
            widget._finishTaskAnchorPick(version_id)
            return
        widget._checkoutVersion(version_id, notify=True, sync_table=True)

    def onVersionPickedForTask(self, version_id: str) -> None:
        widget = self.widget
        if not widget:
            return
        widget._finishTaskAnchorPick(version_id)

    def reviewActionsForVersion(self, spec, history) -> dict:
        widget = self.widget
        if not widget:
            return {}
        return widget._reviewActionsForVersion(spec, history)

    def onVersionReviewAction(self, action: str, spec) -> None:
        widget = self.widget
        if not widget:
            return
        widget.onVersionReviewAction(action, spec)

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

    def openVersionHistoryGraph(self, pick_mode: bool = False, parent=None) -> None:
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

        host = parent if parent is not None else slicer.util.mainWindow()
        self.historyDialog = qt.QDialog(host)
        if pick_mode:
            # Keep Tasks open behind; block only that dialog while picking.
            self.historyDialog.setWindowModality(qt.Qt.WindowModal)
            self.historyDialog.setWindowTitle("Choose start version")
        else:
            self.historyDialog.setWindowFlags(qt.Qt.Window)
            self.historyDialog.setWindowTitle("Version tree")
        self.historyDialog.resize(820, 620)

        layout = qt.QVBoxLayout(self.historyDialog)
        layout.setContentsMargins(12, 12, 12, 12)

        write_locked_ids = set()
        review_pending_ids = set()
        if pick_mode:
            hint_text = (
                "Click a shared version (solid border), e.g. main/3. "
                "Dashed / local versions must be shared first."
            )
        else:
            hint_text = graph_description or (
                "Version tree built from the project version history."
            )
            if widget is not None:
                try:
                    write_locked_ids = set(widget._writeLockedVersionIds() or ())
                except (AttributeError, TypeError, RuntimeError):
                    write_locked_ids = set()
                try:
                    review_pending_ids = set(widget._reviewPendingVersionIds() or ())
                except (AttributeError, TypeError, RuntimeError):
                    review_pending_ids = set()
            extra_bits = []
            if review_pending_ids:
                extra_bits.append(
                    "🔵 = awaiting senior review (double-click to Accept or Decline)"
                )
            if write_locked_ids:
                extra_bits.append(
                    "🔒 = view only — Switch OK, Save / Share blocked"
                )
            if extra_bits:
                hint_text = (hint_text + "\n" if hint_text else "") + "   ·   ".join(
                    extra_bits
                )
        hint = qt.QLabel(hint_text)
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
            pick_mode=bool(pick_mode),
            write_locked_ids=write_locked_ids,
            review_pending_ids=review_pending_ids,
        )
        self._historyCanvas = canvas
        layout.addWidget(canvas.create_toolbar())
        layout.addWidget(canvas, 1)

        if pick_mode and widget is not None:
            try:
                self.historyDialog.connect(
                    "finished(int)",
                    lambda *_args: widget._cancelTaskAnchorPick(),
                )
            except (AttributeError, TypeError, RuntimeError):
                pass

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
