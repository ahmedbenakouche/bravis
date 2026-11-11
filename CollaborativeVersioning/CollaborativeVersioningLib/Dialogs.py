"""UI dialogs (split from CollaborativeVersioning.py). Behavior unchanged."""
from __future__ import annotations

import time

import qt

import CollaborativeVersioningLib.GraphCanvas as graph_module
from CollaborativeVersioningLib.GitHubAuth import (
    GitHubAuthError,
    build_scoped_reset_preview,
    normalize_task_title,
    set_wait_callback,
    suggest_github_usernames,
    PEOPLE_ACCESS_SENIOR,
    PEOPLE_ACCESS_JUNIOR,
    presence_is_online,
    format_presence_ago,
)

from CollaborativeVersioningLib.UiStyles import (
    ACCENT_ICE,
    ACCENT_MINT,
    BG_ELEVATED,
    BORDER,
    BTN_CREATE,
    BTN_DELETE,
    BTN_HISTORY,
    BTN_SAVE_VERSION,
    BTN_SECONDARY,
    DIALOG_HINT_STYLE,
    FEED_COLOR_ERROR,
    FIELD_STYLE,
    TEXT_MUTED,
    TEXT_SECONDARY,
)

from CollaborativeVersioningLib.Helpers import (
    _notification_detail_title,
    _notification_list_label,
    _notification_text,
    _task_excerpt,
    _task_junior_logins,
    _task_juniors_label,
    _task_status_label,
    _task_status_mark,
)

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


class ResolveConflictLanesDialog(qt.QDialog):
    """Per-lane plan: Reset to shared or Compare and merge (tip-conflict lanes only)."""

    CHOICE_RESET = "reset"
    CHOICE_MERGE = "merge"

    def __init__(
        self,
        parent,
        conflict_lanes,
        shared_ahead_lanes=None,
        initial_plan=None,
    ) -> None:
        qt.QDialog.__init__(self, parent)
        self.setWindowTitle("Resolve conflicting branches")
        self.setModal(True)
        self.lane_plan = {}
        lanes = [
            str(name).strip()
            for name in (conflict_lanes or ())
            if str(name).strip()
        ]
        ahead = [
            str(name).strip()
            for name in (shared_ahead_lanes or ())
            if str(name).strip()
        ]
        initial = dict(initial_plan or {})

        layout = qt.QVBoxLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(14, 12, 14, 12)

        intro = qt.QLabel(
            "For each conflicting branch, choose one option:"
        )
        intro.setWordWrap(True)
        intro.setStyleSheet(DIALOG_HINT_STYLE)
        layout.addWidget(intro)

        grid = qt.QGridLayout()
        grid.setHorizontalSpacing(16)
        grid.setVerticalSpacing(8)
        grid.setContentsMargins(4, 4, 4, 4)
        header_branch = qt.QLabel("Branch")
        header_reset = qt.QLabel("Reset to shared")
        header_merge = qt.QLabel("Compare and merge")
        for header in (header_branch, header_reset, header_merge):
            header.setStyleSheet("font-weight: 700;")
        grid.addWidget(header_branch, 0, 0)
        grid.addWidget(header_reset, 0, 1, 1, 1, qt.Qt.AlignHCenter)
        grid.addWidget(header_merge, 0, 2, 1, 1, qt.Qt.AlignHCenter)

        self._row_radios = {}
        for row, lane in enumerate(lanes, start=1):
            name_lbl = qt.QLabel(lane)
            name_lbl.setStyleSheet("font-weight: 600;")
            reset_radio = qt.QRadioButton("")
            merge_radio = qt.QRadioButton("")
            reset_radio.setToolTip(
                "Move this branch tip to the shared tip. "
                "Conflicting local versions leave this line."
            )
            merge_radio.setToolTip(
                "After Validate, open Compare and merge for this branch "
                "(local tip with shared tip)."
            )
            group = qt.QButtonGroup(self)
            group.setExclusive(True)
            group.addButton(reset_radio)
            group.addButton(merge_radio)
            choice = str(initial.get(lane) or "").strip().lower()
            if choice == self.CHOICE_RESET:
                reset_radio.setChecked(True)
            else:
                # Default: Compare and merge
                merge_radio.setChecked(True)
            grid.addWidget(name_lbl, row, 0)
            grid.addWidget(reset_radio, row, 1, 1, 1, qt.Qt.AlignHCenter)
            grid.addWidget(merge_radio, row, 2, 1, 1, qt.Qt.AlignHCenter)
            self._row_radios[lane] = (reset_radio, merge_radio)

        layout.addLayout(grid)

        if ahead:
            ahead_hint = qt.QLabel(
                "Shared-ahead branches (%s) are not listed here — "
                "they are caught up automatically on Validate "
                "(with Reset all or when the plan is applied)."
                % _lanes_label_simple(ahead)
            )
            ahead_hint.setWordWrap(True)
            ahead_hint.setStyleSheet(DIALOG_HINT_STYLE)
            layout.addWidget(ahead_hint)

        if not lanes:
            empty = qt.QLabel("No conflicting branches to plan.")
            empty.setStyleSheet(DIALOG_HINT_STYLE)
            layout.addWidget(empty)

        buttons = qt.QHBoxLayout()
        buttons.addStretch(1)
        cancel_btn = qt.QPushButton("Cancel")
        cancel_btn.setStyleSheet(BTN_SECONDARY)
        cancel_btn.connect("clicked()", self.reject)
        ok_btn = qt.QPushButton("OK")
        ok_btn.setStyleSheet(BTN_CREATE)
        ok_btn.setEnabled(bool(lanes))
        ok_btn.connect("clicked()", self._onOk)
        buttons.addWidget(cancel_btn)
        buttons.addWidget(ok_btn)
        layout.addLayout(buttons)

        try:
            self.resize(520, min(420, 140 + 36 * max(1, len(lanes))))
        except (AttributeError, TypeError, RuntimeError):
            pass

    def _onOk(self) -> None:
        plan = {}
        for lane, radios in self._row_radios.items():
            reset_radio, merge_radio = radios
            if reset_radio.isChecked():
                plan[lane] = self.CHOICE_RESET
            else:
                plan[lane] = self.CHOICE_MERGE
        self.lane_plan = plan
        self.accept()


def _lanes_label_simple(lanes) -> str:
    names = [str(name).strip() for name in (lanes or ()) if str(name).strip()]
    if not names:
        return "the same branch"
    if len(names) == 1:
        return names[0]
    if len(names) == 2:
        return "%s and %s" % (names[0], names[1])
    return "%s, and %s" % (", ".join(names[:-1]), names[-1])


class CompareWithSharedDialog(qt.QDialog):
    """Compare local vs shared graphs, preview a choice, then Validate to apply."""

    ACTION_NONE = ""
    ACTION_UPDATE = "update"
    ACTION_KEEP = "keep"
    ACTION_RESET = "reset"
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
        # Per-lane plan from ResolveConflictLanesDialog: lane -> "reset"|"merge"
        self.lane_plan = {}
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
        self._shared_ahead_lanes = [
            str(name).strip()
            for name in (self._compare.get("shared_ahead_lanes") or ())
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

        # One palette for Local + Shared + all Result previews (avoid same-rank collisions).
        compare_branch_names = []
        for model in (
            local_model,
            remote_model,
            self._compare.get("result"),
            self._compare.get("reset"),
        ):
            for spec in (model or {}).get("version_specs") or []:
                name = str((spec or {}).get("branch") or "").strip()
                if name:
                    compare_branch_names.append(name)
        graph_module.prepare_branch_colors(compare_branch_names)

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
            refresh_branch_colors=False,
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
            refresh_branch_colors=False,
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
        self._reset_btn = qt.QPushButton("Reset all to shared")
        self._reset_btn.setStyleSheet(BTN_SECONDARY)
        self._reset_btn.setToolTip(
            "Reset every conflicting branch to its shared tip. "
            "Other local branches stay. Conflicting local versions leave those lines."
        )
        self._reset_btn.connect(
            "clicked()", lambda: self._selectChoice(self.ACTION_RESET)
        )
        self._merge_btn = qt.QPushButton("Compare and merge")
        self._merge_btn.setStyleSheet(BTN_SECONDARY)
        self._merge_btn.setToolTip(
            "Choose Reset or Compare and merge per conflicting branch."
        )
        self._merge_btn.connect("clicked()", self._onMergePlanClicked)
        choice_row.addWidget(self._update_choice_btn)
        choice_row.addWidget(self._keep_btn)
        choice_row.addWidget(self._reset_btn)
        choice_row.addWidget(self._merge_btn)
        choice_row.addStretch(1)
        conflicts_layout.addLayout(choice_row)

        self._conflict_options_help = qt.QLabel("")
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
            "Green dashes: From shared, Yours on top, or Compare after Validate."
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
            refresh_branch_colors=False,
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
        self._merge_btn.setStyleSheet(
            self._choiceButtonStyle(self._pending == self.ACTION_MERGE)
        )

    def _hideAllChoiceButtons(self) -> None:
        self._update_choice_btn.hide()
        self._keep_btn.hide()
        self._reset_btn.hide()
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

    def _tipConflictLaneCount(self) -> int:
        return len(
            [
                str(name).strip()
                for name in (self._conflict_lanes or ())
                if str(name).strip()
            ]
        )

    def _tipConflictMergeButtonLabel(self) -> str:
        """Label for the per-lane plan button."""
        if self._tipConflictLaneCount() <= 1:
            return "Compare and merge"
        return "Reset or Compare and merge"

    def _applyTipConflictActionLabels(self) -> None:
        """Tip-conflict only: Reset all + merge label from conflict lane count."""
        merge_label = self._tipConflictMergeButtonLabel()
        self._reset_btn.setText("Reset all to shared")
        self._reset_btn.setToolTip(
            "Reset every conflicting branch to its shared tip. "
            "Other local branches stay. Conflicting local versions leave those lines."
        )
        self._merge_btn.setText(merge_label)
        if self._tipConflictLaneCount() <= 1:
            self._merge_btn.setToolTip(
                "Compare and merge your local tip with the shared tip on this branch "
                "(use Reset all to shared if you want a full reset instead)."
            )
            help_text = (
                "• Reset all to shared — every conflicting branch matches shared; "
                "other local branches stay. "
                "Warning: conflicting saved versions leave those branch lines.\n"
                "• Compare and merge — merge your local tip with the shared tip "
                "on this branch (no plan window — only one conflicting branch)."
            )
        else:
            self._merge_btn.setToolTip(
                "Choose Reset or Compare and merge per conflicting branch."
            )
            help_text = (
                "• Reset all to shared — every conflicting branch matches shared; "
                "other local branches stay. "
                "Warning: conflicting saved versions leave those branch lines.\n"
                "• Reset or Compare and merge — pick Reset or Compare and merge "
                "for each conflicting branch."
            )
        help_lbl = getattr(self, "_conflict_options_help", None)
        if help_lbl is not None:
            help_lbl.setText(help_text)

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
            self._applyTipConflictActionLabels()
            ahead_line = ""
            if self._shared_ahead_lanes:
                ahead_line = (
                    "\nShared-ahead branches (%s) are caught up automatically "
                    "on Validate with Reset all / plan (not listed in the plan grid)."
                    % self._lanesLabel(self._shared_ahead_lanes)
                )
            self._setConflictsMessage(
                "Local and shared have diverged on: %s.\n"
                "Reset all to shared resets every conflicting branch; "
                "other local versions stay.%s\n"
                "Choose how to integrate, then Validate."
                % (self._conflictLanesLabel(), ahead_line)
            )
            self._update_choice_btn.hide()
            self._keep_btn.hide()
            self._reset_btn.show()
            self._merge_btn.show()
            self._conflict_options_help.show()
            self._result_panel.hide()
            self._validate_btn.setEnabled(False)
            return

        if self._obsolete_merged:
            # Obsolete path: single Reset action (not the tip-conflict "Reset all" plan).
            self._reset_btn.setText("Reset to shared")
            self._reset_btn.setToolTip(
                "Move obsolete merged branch tips (and main when listed) to shared."
            )
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
                    "Click Validate to update."
                    if many
                    else "Branch %s was already merged onto main on the shared project.\n"
                    "Your local versions on that branch are obsolete.\n"
                    "Reset moves these tips to shared: %s "
                    "(main included — unshared main versions leave the tree).\n"
                    "Click Validate to update."
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
                        "Click Validate to update."
                        % lanes
                    )
                else:
                    self._setConflictsMessage(
                        "No tip conflict — the shared project has newer versions, "
                        "and you also have local versions not shared yet.\n"
                        "Preview: Update version tree (your local unshared versions stay). "
                        "Click Validate to update."
                    )
            elif self._has_new_remote_lanes and not self._has_remote:
                self._setConflictsMessage(
                    "No conflicts — the shared project has new branches (%s). "
                    "Preview below shows the result after integrating them into your local folder. "
                    "Click Validate to update."
                    % lanes
                )
            else:
                self._setConflictsMessage(
                    "No conflicts — the shared project has newer versions. "
                    "Preview below shows the result after integrating them into your local folder. "
                    "Click Validate to update."
                )
            self._selectChoice(self.ACTION_UPDATE, silent=True)
            return

        # Local unshared only (e.g. DIY) — shared not ahead / no tip fork.
        if self._has_local:
            self._setConflictsMessage(
                "No tip conflict — you have local versions not shared yet, "
                "and the shared project is not ahead.\n"
                "Preview: Keep mine. Click Validate to update "
                "(or Close to leave the Version tree unchanged)."
            )
            self._keep_btn.show()
            self._selectChoice(self.ACTION_KEEP, silent=True)
            return

        if self._aligned:
            self._setConflictsMessage(
                "No conflicts — this computer matches the shared project."
            )
            self._result_panel.hide()
            self._validate_btn.setEnabled(False)
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
            # Green: tips taken from shared + local-only versions that stay
            # (non-reset / local-ahead lanes still present in the scoped reset model).
            mark_shas = set(only_remote)
            if not mark_shas:
                remote_model = self._compare.get("remote") or {}
                remote_sha_by_id = remote_model.get("sha_by_id") or {}
                for vid in set(self._compare.get("conflict_ids_remote") or ()):
                    sha = remote_sha_by_id.get(vid)
                    if sha:
                        mark_shas.add(sha)
            for vid in self._idsForShas(model, mark_shas):
                roles[vid] = "shared"
            for vid in self._idsForShas(model, only_local):
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
        reset_model = self._compare.get("reset") or remote_model

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
            if self._conflict and self._shared_ahead_lanes:
                detail += (
                    "; shared-ahead (%s) caught up"
                    % self._lanesLabel(self._shared_ahead_lanes)
                )
            if includes_main:
                detail += " — unshared main versions leave the tree"
            reset_title = (
                "Result — Reset all to shared"
                if self._conflict
                else "Result — Reset to shared"
            )
            return (
                reset_model,
                reset_title,
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
        if choice == self.ACTION_MERGE:
            return self._modelForLanePlan()
        return (
            {},
            "Result — Compare and merge",
            "Coming soon",
        )

    def _planResetNames(self) -> list:
        return [
            name
            for name, choice in (self.lane_plan or {}).items()
            if choice == ResolveConflictLanesDialog.CHOICE_RESET
        ]

    def _planMergeNames(self) -> list:
        return [
            name
            for name, choice in (self.lane_plan or {}).items()
            if choice == ResolveConflictLanesDialog.CHOICE_MERGE
        ]

    def _planPreviewSharedTipLanes(self) -> list:
        """Lanes whose Result tip is shared: plan Reset + plan Merge + shared-ahead."""
        ordered = []
        seen = set()
        for name in (
            list(self._planResetNames())
            + list(self._planMergeNames())
            + list(self._shared_ahead_lanes or ())
        ):
            key = str(name).strip().lower()
            label = str(name).strip()
            if not label or key in seen:
                continue
            ordered.append(label)
            seen.add(key)
        return ordered

    def _tipIdsForLanes(self, model: dict, lanes) -> set:
        """Tip version ids for the given lanes in a history model (excludes phantoms)."""
        wanted = {
            str(name).strip().lower()
            for name in (lanes or ())
            if str(name).strip()
        }
        if not wanted:
            return set()
        ids_on_lane = set()
        parent_on_lane = set()
        for spec in (model or {}).get("version_specs") or []:
            if not isinstance(spec, dict):
                continue
            if spec.get("plan_merge_phantom"):
                continue
            branch = str(spec.get("branch") or "").strip().lower()
            vid = str(spec.get("id") or "").strip()
            if not vid or branch not in wanted:
                continue
            ids_on_lane.add(vid)
            parent = str(spec.get("parent") or "").strip()
            if parent:
                parent_on_lane.add(parent)
        return {vid for vid in ids_on_lane if vid not in parent_on_lane}

    def _preferLaneTipId(self, tip_ids) -> str:
        ids = [str(vid).strip() for vid in (tip_ids or ()) if str(vid).strip()]
        if not ids:
            return ""
        real = [vid for vid in ids if not vid.lower().endswith("/start")]
        return sorted(real or ids, key=str)[0]

    def _withPlanMergePhantoms(self, model: dict) -> dict:
        """After shared tips: one phantom child per Compare-and-merge lane."""
        out = {
            "version_specs": [
                dict(spec) for spec in ((model or {}).get("version_specs") or [])
                if isinstance(spec, dict)
            ],
            "sha_by_id": dict((model or {}).get("sha_by_id") or {}),
            "tags_by_id": dict((model or {}).get("tags_by_id") or {}),
            "commit_history": [
                list(row) for row in ((model or {}).get("commit_history") or [])
                if row
            ],
            "head_id": (model or {}).get("head_id"),
        }
        existing = {
            str(spec.get("id") or "").strip()
            for spec in out["version_specs"]
            if str(spec.get("id") or "").strip()
        }
        for lane in self._planMergeNames():
            tip_id = self._preferLaneTipId(self._tipIdsForLanes(out, [lane]))
            if not tip_id:
                continue
            phantom_id = "%s/compare-preview" % lane
            if phantom_id in existing:
                continue
            out["version_specs"].append(
                {
                    "id": phantom_id,
                    "parent": tip_id,
                    "branch": lane,
                    "tag": "○",
                    "merge": False,
                    "plan_merge_phantom": True,
                }
            )
            out["sha_by_id"][phantom_id] = ""
            out["tags_by_id"][phantom_id] = "○"
            out["commit_history"].append(
                [
                    phantom_id,
                    "",
                    "",
                    "Merge result after Compare (preview only)",
                    "local",
                ]
            )
            existing.add(phantom_id)
        return out

    def _modelForLanePlan(self) -> tuple:
        """Result: shared tips on plan lanes; phantom merge node on Compare-and-merge lanes."""
        local_model = self._compare.get("local") or {}
        remote_model = self._compare.get("remote") or {}
        reset_names = self._planResetNames()
        merge_names = self._planMergeNames()
        shared_tip_lanes = self._planPreviewSharedTipLanes()
        if shared_tip_lanes:
            model = build_scoped_reset_preview(
                local_model, remote_model, shared_tip_lanes
            )
        else:
            model = dict(local_model or {})
        if merge_names:
            model = self._withPlanMergePhantoms(model)
        detail_bits = []
        if reset_names:
            detail_bits.append("Reset: %s → shared tip" % self._lanesLabel(reset_names))
        if merge_names:
            detail_bits.append(
                "Compare and merge: %s → shared tip + merge preview"
                % self._lanesLabel(merge_names)
            )
        if self._shared_ahead_lanes:
            detail_bits.append(
                "shared-ahead caught up: %s"
                % self._lanesLabel(self._shared_ahead_lanes)
            )
        detail = "; ".join(detail_bits) if detail_bits else "Plan preview"
        return (
            model,
            "Result — plan (Reset / Compare and merge)",
            detail,
        )

    def _resultMarksForLanePlan(self, model: dict) -> tuple:
        """Green marks: From shared on real tips; Compare after Validate on phantoms."""
        only_remote = set(self._compare.get("only_remote_shas") or ())
        only_local = set(self._compare.get("only_local_shas") or ())
        roles = {}
        phantom_ids = set()
        for spec in (model or {}).get("version_specs") or []:
            if not isinstance(spec, dict) or not spec.get("plan_merge_phantom"):
                continue
            vid = str(spec.get("id") or "").strip()
            if vid:
                phantom_ids.add(vid)
                roles[vid] = "merge"
        # Real tips adopted from shared (reset + merge lanes + shared-ahead).
        for vid in self._tipIdsForLanes(model, self._planPreviewSharedTipLanes()):
            roles[vid] = "shared"
        for vid in self._idsForShas(model, only_remote):
            if vid not in phantom_ids:
                roles.setdefault(vid, "shared")
        # Local-only versions that stay on other lanes.
        for vid in self._idsForShas(model, only_local):
            if vid in phantom_ids:
                continue
            roles.setdefault(vid, "local")
        return set(roles.keys()), roles

    def _showResultPreview(
        self, choice: str, model: dict, title: str, description: str, silent: bool
    ) -> None:
        """Paint Result canvas for a choice / plan and refresh Validate state."""
        if choice == self.ACTION_MERGE:
            result_ids, result_roles = self._resultMarksForLanePlan(model)
        else:
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

    def _applyLanePlanSelection(self, plan: dict) -> None:
        """Store plan after Compare and merge / plan OK; show Result (étape 3)."""
        self.lane_plan = dict(plan or {})
        reset_names = self._planResetNames()
        merge_names = self._planMergeNames()
        # All Reset in the plan ≡ Reset all (Validate applies now).
        if reset_names and not merge_names:
            self._selectChoice(self.ACTION_RESET, silent=False)
            if self._shared_ahead_lanes:
                self._setConflictsMessage(
                    "Preview: Reset all to shared (plan = reset on every conflicting "
                    "branch; shared-ahead %s caught up).\n"
                    "Click Validate to apply, or pick another option."
                    % self._lanesLabel(self._shared_ahead_lanes)
                )
            else:
                self._setConflictsMessage(
                    "Preview: Reset all to shared (plan = reset on every conflicting "
                    "branch).\n"
                    "Click Validate to apply, or pick another option."
                )
            return

        self._pending = self.ACTION_MERGE
        self._refreshChoiceStyles()
        model, title, description = self._modelForLanePlan()
        self._showResultPreview(self.ACTION_MERGE, model, title, description, False)
        # Étape 3: Result shown; Validate for merge queue = étape 4+.
        self._validate_btn.setEnabled(False)
        self._validate_btn.setToolTip(
            "Compare and merge after Validate comes next — "
            "not applied yet for lanes marked Compare after Validate."
        )
        parts = ["Preview: plan ready."]
        if reset_names:
            parts.append(
                "Reset to shared (on Validate): %s." % self._lanesLabel(reset_names)
            )
        if merge_names:
            parts.append(
                "Compare and merge: %s → shared tip + ○ preview "
                "(Validate for merges comes next)."
                % self._lanesLabel(merge_names)
            )
        if self._shared_ahead_lanes:
            parts.append(
                "Shared-ahead (%s) caught up on Validate."
                % self._lanesLabel(self._shared_ahead_lanes)
            )
        if self._tipConflictLaneCount() > 1:
            parts.append("Reopen the plan to change choices, or use Reset all.")
        else:
            parts.append("Use Reset all to shared if you want a full reset instead.")
        self._setConflictsMessage("\n".join(parts))

    def _onMergePlanClicked(self) -> None:
        """Étape 2: 1 lane → merge implicite; ≥2 → grille Reset|Compare and merge."""
        lanes = [
            str(name).strip()
            for name in (self._conflict_lanes or ())
            if str(name).strip()
        ]
        if not lanes:
            return
        # One conflict lane: Reset all vs Compare and merge already cover the choice.
        if len(lanes) == 1:
            self._applyLanePlanSelection(
                {lanes[0]: ResolveConflictLanesDialog.CHOICE_MERGE}
            )
            return
        plan_dlg = ResolveConflictLanesDialog(
            self,
            lanes,
            shared_ahead_lanes=self._shared_ahead_lanes,
            initial_plan=self.lane_plan,
        )
        if plan_dlg.exec_() != qt.QDialog.Accepted:
            return
        self._applyLanePlanSelection(dict(plan_dlg.lane_plan or {}))

    def _selectChoice(self, choice: str, silent: bool = False) -> None:
        self._pending = choice
        self._refreshChoiceStyles()
        if choice == self.ACTION_MERGE:
            # Plan path owns Result; keep a safe fallback if called without a plan.
            if self.lane_plan:
                model, title, description = self._modelForLanePlan()
                self._showResultPreview(
                    self.ACTION_MERGE, model, title, description, silent
                )
                has_merge = bool(self._planMergeNames())
                self._validate_btn.setEnabled(not has_merge)
                if has_merge:
                    self._validate_btn.setToolTip(
                        "Compare and merge after Validate comes next."
                    )
                else:
                    self._validate_btn.setToolTip("Apply this choice to this computer.")
                return
            self._result_panel.hide()
            legend = getattr(self, "_result_legend", None)
            if legend is not None:
                legend.hide()
            self._validate_btn.setEnabled(False)
            self._validate_btn.setToolTip(
                "Open the per-branch plan, then preview the Result."
            )
            if not silent:
                if self._tipConflictLaneCount() <= 1:
                    self._setConflictsMessage(
                        "Compare and merge selects this branch for merge after Validate "
                        "(or use Reset all to shared)."
                    )
                else:
                    self._setConflictsMessage(
                        "Open %s to choose Reset or Compare and merge per branch."
                        % self._tipConflictMergeButtonLabel()
                    )
            return

        model, title, description = self._modelForChoice(choice)
        self._showResultPreview(choice, model, title, description, silent)
        self._validate_btn.setEnabled(True)
        self._validate_btn.setToolTip("Apply this choice to this computer.")
        if not silent:
            labels = {
                self.ACTION_KEEP: "Keep mine",
                self.ACTION_RESET: (
                    "Reset all to shared" if self._conflict else "Reset to shared"
                ),
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
            "and Accept and Merge / Decline a junior's review request.\n"
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


