import importlib
import logging
import os
import sys
from datetime import datetime

import ctk
import qt
import slicer
from slicer.ScriptedLoadableModule import *
from slicer.i18n import tr as _
from slicer.i18n import translate
from slicer.util import VTKObservationMixin

import CollaborativeVersioningLib
import CollaborativeVersioningLib.GraphCanvas
import CollaborativeVersioningLib.UiStyles

# Change this string to verify that Reload picked up your edits.
_UI_BUILD_TAG = "2026-07-19-ui-workflow-v43-en"

_LIB_MODULE_NAMES = (
    "CollaborativeVersioningLib.UiStyles",
    "CollaborativeVersioningLib.DataManager",
    "CollaborativeVersioningLib.OntologyLoader",
    "CollaborativeVersioningLib.simulation.DemoData",
    "CollaborativeVersioningLib.GraphCanvas",
    "CollaborativeVersioningLib",
)


def _refreshLibModules() -> None:
    for module_name in _LIB_MODULE_NAMES:
        module = sys.modules.get(module_name)
        if module is not None:
            importlib.reload(module)


_refreshLibModules()

from CollaborativeVersioningLib.simulation.DemoData import (
    DEMO_SERVER_PROJECTS,
    apply_server_pull,
    format_version_display_plain,
    load_project_history_bundle,
)
from CollaborativeVersioningLib.GraphCanvas import GRAPH_BUILD_TAG
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
    ACCENT_INDIGO,
    ACCENT_MINT,
    BTN_CONNECT,
    BTN_CREATE,
    BTN_DEPENDENCY,
    BTN_HISTORY,
    BTN_PULL,
    BTN_PUSH,
    BTN_SECONDARY,
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
    PLACEHOLDER_LOCKED_STYLE,
    PLACEHOLDER_STYLE,
    SECTION_TITLE_LOCKED_STYLE,
    SECTION_TITLE_STYLE,
    SEPARATOR_STYLE,
    STATUS_NEUTRAL,
    STATUS_OK,
    STATUS_WARNING,
    TABLE_LOCKED_STYLE,
    TABLE_STYLE,
    TEXT_MUTED,
    TEXT_SECONDARY,
)

LOCAL_PROJECT_NAME = "Local — new project"
ONTOLOGY_COMBO_NONE_LABEL = "None"
ONTOLOGY_COMBO_NONE_INDEX = 0


def _qt_combo_text(combo) -> str:
    value = combo.currentText
    if callable(value):
        value = value()
    return str(value).strip()


def _qt_combo_count(combo) -> int:
    value = combo.count
    if callable(value):
        value = value()
    return int(value)


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
    """Configuration dialog shown when creating a new local project."""

    def __init__(self, parent=None) -> None:
        qt.QDialog.__init__(self, parent)
        self.setWindowTitle("New project configuration")
        self.setMinimumWidth(420)

        layout = qt.QFormLayout(self)
        layout.setSpacing(10)

        self.nameEdit = qt.QLineEdit()
        self.nameEdit.setPlaceholderText("My annotation project")
        self.nameEdit.setStyleSheet(FIELD_STYLE)
        layout.addRow("Project name:", self.nameEdit)

        self.descriptionEdit = qt.QLineEdit()
        self.descriptionEdit.setPlaceholderText("Optional short description")
        self.descriptionEdit.setStyleSheet(FIELD_STYLE)
        layout.addRow("Description:", self.descriptionEdit)

        self.messageEdit = qt.QLineEdit("Initial commit")
        self.messageEdit.setStyleSheet(FIELD_STYLE)
        layout.addRow("Initial commit message:", self.messageEdit)

        buttons = qt.QDialogButtonBox(qt.QDialogButtonBox.Ok | qt.QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

    def values(self) -> dict:
        return {
            "name": self.nameEdit.text.strip(),
            "description": self.descriptionEdit.text.strip(),
            "message": self.messageEdit.text.strip() or "Initial commit",
        }


class CollaborativeVersioning(ScriptedLoadableModule):
    def __init__(self, parent):
        ScriptedLoadableModule.__init__(self, parent)
        self.parent.title = _("Collaborative Versioning")
        self.parent.categories = [translate("qSlicerAbstractCoreModule", "Informatics")]
        self.parent.dependencies = []
        self.parent.contributors = ["Ahmed Ben Akouche (ISIR)", "Julien Gori (CNRS)"]
        self.parent.helpText = _(
            """
            Collaborative versioning for 3D image annotations — UI MVP (E2).<br><br>
            Server connection, local or remote project selection, VCS actions.<br>
            Right panel: graphs, history, and activity feed.<br><br>
            Back-end not connected at this project stage.
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
        self._server_files_loaded = False
        self._active_server_project = None
        self._ontology_server_combo_index = -1
        self._local_project_name = None
        self._local_project_description = None
        self._local_project_created = False
        self._suppress_asset_ui_updates = 0
        self._suppress_history_selection_signal = False
        self._project_history_bundle = None

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
        self._clearLayout()
        self.logic = CollaborativeVersioningLogic()
        self.logic.setWidget(self)
        self._buildLeftPanel()
        self._buildRightDock()
        self._setupDefaults()
        self._connected = False
        self.connectionStatusLabel.text = "Not connected"
        self.connectionStatusLabel.setStyleSheet(STATUS_NEUTRAL)
        self._applyDisconnectedUi()
        self.setupDeveloperSection()
        self._appendFeed(_("Collaborative Versioning module — UI MVP (E2)."))
        self._appendFeed(f"Build UI : {_UI_BUILD_TAG}")
        self._appendFeed(f"Graph build : {GRAPH_BUILD_TAG}")

    def _clearLayout(self) -> None:
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
        connexionLayout = qt.QFormLayout(connexionButton)
        connexionLayout.setSpacing(8)

        self.serverUrlEdit = qt.QLineEdit("https://anatovcs-server.icm-institute.org")
        self.serverUrlEdit.setPlaceholderText("https://anatovcs-server.icm-institute.org")
        self.serverUrlEdit.setStyleSheet(FIELD_STYLE)
        connexionLayout.addRow("Server URL:", self.serverUrlEdit)

        self.userIdEdit = qt.QLineEdit()
        self.userIdEdit.setPlaceholderText("user id")
        self.userIdEdit.setStyleSheet(FIELD_STYLE)
        connexionLayout.addRow("User ID:", self.userIdEdit)

        self.passwordEdit = qt.QLineEdit()
        self.passwordEdit.setEchoMode(qt.QLineEdit.Password)
        self.passwordEdit.setPlaceholderText("password")
        self.passwordEdit.setStyleSheet(FIELD_STYLE)
        connexionLayout.addRow("Password:", self.passwordEdit)

        connectRow = qt.QWidget()
        connectRowLayout = qt.QHBoxLayout(connectRow)
        connectRowLayout.setContentsMargins(0, 0, 0, 0)
        self.connectButton = qt.QPushButton("Connect")
        self.connectButton.setStyleSheet(BTN_CONNECT)
        self.connectionStatusLabel = qt.QLabel("Not connected")
        self.connectionStatusLabel.setStyleSheet(STATUS_NEUTRAL)
        connectRowLayout.addWidget(self.connectButton)
        connectRowLayout.addWidget(self.connectionStatusLabel, 1)
        connexionLayout.addRow(connectRow)

        projectButton = ctk.ctkCollapsibleButton()
        projectButton.text = "Active project"
        projectButton.collapsed = False
        self.projectButton = projectButton
        self.layout.addWidget(projectButton)
        projectLayout = qt.QVBoxLayout(projectButton)
        projectLayout.setSpacing(10)

        sourceForm = qt.QFormLayout()
        sourceForm.setSpacing(8)

        self.projectCombo = qt.QComboBox()
        self.projectCombo.setStyleSheet(FIELD_STYLE)
        self.projectCombo.addItem(LOCAL_PROJECT_NAME)
        sourceForm.addRow("Project:", self.projectCombo)
        projectLayout.addLayout(sourceForm)

        assetsForm = qt.QFormLayout()
        assetsForm.setSpacing(8)

        self.volumeSelector = slicer.qMRMLNodeComboBox()
        self._configureDataNodeSelector(self.volumeSelector, ["vtkMRMLScalarVolumeNode"], none_enabled=True)
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
        self.ontologyPresetCombo.setCurrentIndex(ONTOLOGY_COMBO_NONE_INDEX)
        ontologyPanelLayout.addWidget(self.ontologyPresetCombo)
        ontologyLocalActions = qt.QHBoxLayout()
        self.ontologyHelpButton = qt.QPushButton("Help")
        self.loadOntologyButton = qt.QPushButton("Load JSON…")
        self.editOntologyButton = qt.QPushButton("Edit")
        self.exportOntologyButton = qt.QPushButton("Export")
        for btn in (self.ontologyHelpButton, self.loadOntologyButton, self.editOntologyButton, self.exportOntologyButton):
            btn.setStyleSheet(BTN_SECONDARY + " font-size: 10px; padding: 3px 6px;")
            ontologyLocalActions.addWidget(btn)
        ontologyPanelLayout.addLayout(ontologyLocalActions)

        assetsForm.addRow("Ontology map (JSON):", ontologyPanel)
        projectLayout.addLayout(assetsForm)

        actionsRow = qt.QWidget()
        actionsLayout = qt.QHBoxLayout(actionsRow)
        actionsLayout.setContentsMargins(0, 0, 0, 0)
        self.createButton = qt.QPushButton("Create")
        self.pullButton = qt.QPushButton("Pull")
        self.pushButton = qt.QPushButton("Push")
        self.createButton.setStyleSheet(BTN_CREATE)
        self.pullButton.setStyleSheet(BTN_PULL)
        self.pushButton.setStyleSheet(BTN_PUSH)
        for btn in (self.createButton, self.pullButton, self.pushButton):
            actionsLayout.addWidget(btn)
        self.createButton.setEnabled(False)
        self.pullButton.setEnabled(False)
        self.pushButton.setEnabled(False)
        projectLayout.addWidget(actionsRow)

        self.layout.addStretch(1)

        self.connectButton.connect("clicked()", self.onConnect)
        self.projectCombo.connect("currentIndexChanged(int)", self.onProjectChanged)
        self.ontologyPresetCombo.connect("currentIndexChanged(int)", self.onOntologyPresetChanged)
        self.ontologyHelpButton.connect("clicked()", self.onOntologyJsonHelp)
        self.loadOntologyButton.connect("clicked()", self.onLoadOntologyJson)
        self.editOntologyButton.connect("clicked()", self.onEditOntology)
        self.exportOntologyButton.connect("clicked()", self.onExportOntologyJson)
        self.createButton.connect("clicked()", self.onCreateVersion)
        self.pushButton.connect("clicked()", self.onPush)
        self.pullButton.connect("clicked()", self.onPull)
        self.volumeSelector.connect("currentNodeChanged(vtkMRMLNode*)", self._onProjectAssetsChanged)
        self.segmentationSelector.connect("currentNodeChanged(vtkMRMLNode*)", self._onProjectAssetsChanged)

    def _configureDataNodeSelector(self, selector, node_types, none_enabled=False) -> None:
        """Existing scene nodes only (no create/delete entries)."""
        selector.setMRMLScene(slicer.mrmlScene)
        selector.nodeTypes = node_types
        selector.addEnabled = False
        selector.removeEnabled = False
        selector.editEnabled = False
        selector.renameEnabled = False
        selector.noneEnabled = none_enabled
        selector.setStyleSheet(FIELD_STYLE)

    def _serverAwaitingPull(self) -> bool:
        return self._isServerProjectMode() and not self._server_files_loaded

    def _clearOntologyDocument(self) -> None:
        self._ontology_document = None
        if self.logic and self.logic._dependencyCanvas:
            self.logic._dependencyCanvas.set_specs(
                [],
                graph_title="Ontology",
                graph_description="No ontology loaded.",
            )
        self._updateRightDockAvailability()
        self._updateVersionActionButtons()

    def _setOntologyComboNone(self) -> None:
        self.ontologyPresetCombo.blockSignals(True)
        self.ontologyPresetCombo.setCurrentIndex(ONTOLOGY_COMBO_NONE_INDEX)
        self.ontologyPresetCombo.blockSignals(False)

    def _removeServerOntologyComboEntry(self) -> None:
        combo = self.ontologyPresetCombo
        if self._ontology_server_combo_index < 0:
            return
        combo.blockSignals(True)
        if 0 <= self._ontology_server_combo_index < combo.count:
            combo.removeItem(self._ontology_server_combo_index)
        self._ontology_server_combo_index = -1
        combo.blockSignals(False)

    def _ontologyComboLabelFromPath(self, path: str) -> str:
        name = os.path.basename(path)
        if name.lower().endswith(".json"):
            return name[:-5]
        return os.path.splitext(name)[0]

    def _setOntologyComboLoadedFilename(self, document=None, filename=None) -> None:
        if filename:
            label = self._ontologyComboLabelFromPath(filename)
        elif document:
            label = self._ontologyComboLabelFromPath(document.get("source_path") or "ontology.json")
        else:
            return
        combo = self.ontologyPresetCombo
        self._removeServerOntologyComboEntry()
        combo.blockSignals(True)
        combo.addItem(label)
        self._ontology_server_combo_index = combo.count - 1
        combo.setCurrentIndex(self._ontology_server_combo_index)
        combo.blockSignals(False)

    def _beginBatchUiUpdate(self) -> None:
        self._suppress_asset_ui_updates += 1

    def _endBatchUiUpdate(self, refresh: bool = True) -> None:
        if self._suppress_asset_ui_updates > 0:
            self._suppress_asset_ui_updates -= 1
        if refresh and self._suppress_asset_ui_updates == 0:
            qt.QTimer.singleShot(0, self._refreshProjectAssetUi)

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
            try:
                selector.disconnect("currentNodeChanged(vtkMRMLNode*)", self._onProjectAssetsChanged)
            except (RuntimeError, ValueError, TypeError):
                pass
            setattr(self, name, None)

    def _refreshProjectAssetUi(self) -> None:
        if not self._connected or self._suppress_asset_ui_updates > 0:
            return
        if not _qt_widget_is_valid(getattr(self, "pullButton", None)):
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

        self.btnDependencyGraph = qt.QPushButton("View dependency graph")
        self.btnDependencyGraph.setStyleSheet(BTN_DEPENDENCY)
        layout.addWidget(self.btnDependencyGraph)

        self.btnHistoryGraph = qt.QPushButton("View version tree")
        self.btnHistoryGraph.setStyleSheet(BTN_HISTORY)
        layout.addWidget(self.btnHistoryGraph)

        self._dockHistoryTitle = qt.QLabel("COMMIT HISTORY")
        self._dockHistoryTitle.setStyleSheet(SECTION_TITLE_STYLE)
        layout.addWidget(self._dockHistoryTitle)

        self.checkedOutLabel = qt.QLabel("")
        self.checkedOutLabel.setWordWrap(True)
        self.checkedOutLabel.setStyleSheet(CHECKED_OUT_LABEL_STYLE)
        self.checkedOutLabel.setVisible(False)
        layout.addWidget(self.checkedOutLabel)

        self.historyPlaceholder = qt.QLabel(
            "Commit history is available for server projects after Pull."
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
        layout.addWidget(self._dockActivityTitle)

        self.feedTextEdit = qt.QTextEdit()
        self.feedTextEdit.setReadOnly(True)
        self.feedTextEdit.setStyleSheet(FEED_STYLE)
        layout.addWidget(self.feedTextEdit, 1)

        self._rightDock.setWidget(container)
        mainWin.addDockWidget(qt.Qt.RightDockWidgetArea, self._rightDock)

        self.btnDependencyGraph.connect("clicked()", self.onOpenDependencyGraph)
        self.btnHistoryGraph.connect("clicked()", self.onOpenHistoryGraph)
        self.historyTableWidget.connect("itemSelectionChanged()", self.onHistorySelectionChanged)
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
            button.setStyleSheet(active_style)
            button.setEnabled(enabled)
        except (RuntimeError, ValueError):
            pass

    def _setupDefaults(self) -> None:
        self.userIdEdit.text = os.environ.get("USER", os.environ.get("USERNAME", "annotator"))

    def _promptCommitMessage(self, title: str, label: str, default: str = "") -> str | None:
        message, ok = _qt_input_text(slicer.util.mainWindow(), title, label, default)
        if not ok or not message:
            return None
        return message

    def _populateProjectCombo(self) -> None:
        self.projectCombo.blockSignals(True)
        previous = _qt_combo_text(self.projectCombo) if _qt_combo_count(self.projectCombo) else LOCAL_PROJECT_NAME
        self.projectCombo.clear()
        self.projectCombo.addItem(LOCAL_PROJECT_NAME)
        if self._connected:
            for project_name in DEMO_SERVER_PROJECTS:
                self.projectCombo.addItem(project_name)
        if previous != LOCAL_PROJECT_NAME and (not self._connected or previous not in DEMO_SERVER_PROJECTS):
            previous = LOCAL_PROJECT_NAME
        restore_index = self.projectCombo.findText(previous)
        self.projectCombo.setCurrentIndex(restore_index if restore_index >= 0 else 0)
        self.projectCombo.blockSignals(False)

    def _isServerProjectMode(self) -> bool:
        project_name = _qt_combo_text(self.projectCombo)
        return project_name != LOCAL_PROJECT_NAME and project_name in DEMO_SERVER_PROJECTS

    def _currentProjectName(self) -> str:
        return _qt_combo_text(self.projectCombo) or LOCAL_PROJECT_NAME

    def _isLocalProjectMode(self) -> bool:
        return self._currentProjectName() == LOCAL_PROJECT_NAME

    def _refreshUiState(self) -> None:
        if not self._connected:
            self._applyDisconnectedUi()
            return
        self._setRightDockLocked(False)
        self._setActiveProjectSectionEnabled(True)
        self._updateProjectModeUi()
        self._updateRightDockAvailability()

    def _applyDisconnectedUi(self) -> None:
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
            if getattr(self, "historyTableWidget", None):
                self.historyTableWidget.setEnabled(False)
                self.historyTableWidget.setStyleSheet(TABLE_LOCKED_STYLE)
            return
        if getattr(self, "feedTextEdit", None):
            self.feedTextEdit.setStyleSheet(FEED_STYLE)
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
            "pullButton",
            "pushButton",
        ):
            widget = getattr(self, widget_name, None)
            if widget is not None:
                widget.setEnabled(enabled)
        if not enabled:
            return
        if self._isServerProjectMode() and not self._server_files_loaded:
            self._setProjectAssetFieldsEnabled(False)
        elif self._isServerProjectMode():
            self._setProjectAssetFieldsEnabled(True)
        else:
            self._setProjectAssetFieldsEnabled(True)
        self._updateVersionActionButtons()

    def _canOpenDependencyGraph(self) -> bool:
        if not self._connected:
            return False
        if not self._ontology_document:
            return False
        if self._isServerProjectMode():
            return self._server_pulled
        return self._isLocalProjectMode()

    def _canOpenVersionTree(self) -> bool:
        if not self._connected:
            return False
        if self._isLocalProjectMode():
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
        feed = getattr(self, "feedTextEdit", None)
        if _qt_widget_is_valid(feed):
            try:
                feed.setStyleSheet(FEED_STYLE)
            except (RuntimeError, ValueError):
                pass

    def _hasVolume(self) -> bool:
        if not getattr(self, "volumeSelector", None):
            return False
        node = self.volumeSelector.currentNode()
        if node is None:
            return False
        scene = slicer.mrmlScene
        return scene is not None and scene.GetNodeByID(node.GetID()) is not None

    def _hasSegmentation(self) -> bool:
        if not getattr(self, "segmentationSelector", None):
            return False
        node = self.segmentationSelector.currentNode()
        if node is None:
            return False
        scene = slicer.mrmlScene
        return scene is not None and scene.GetNodeByID(node.GetID()) is not None

    def _hasOntology(self) -> bool:
        return self._ontology_document is not None

    def _projectAssetsComplete(self) -> bool:
        return self._hasVolume() and self._hasSegmentation() and self._hasOntology()

    def _missingProjectAssets(self) -> list[str]:
        missing = []
        if not self._hasVolume():
            missing.append("3D Volume")
        if not self._hasSegmentation():
            missing.append("Segmentation")
        if not self._hasOntology():
            missing.append("Ontology map")
        return missing

    def _onProjectAssetsChanged(self, *_args) -> None:
        if not self._connected or self._suppress_asset_ui_updates > 0:
            return
        if not _qt_widget_is_valid(getattr(self, "pullButton", None)):
            return
        qt.QTimer.singleShot(0, self._refreshProjectAssetUi)

    def _canPush(self) -> bool:
        if not self._connected or not self._currentVersionId:
            return False
        if self._isLocalProjectMode():
            return self._projectAssetsComplete()
        return self._server_pulled

    def _pushDisabledReason(self) -> str:
        if not self._connected:
            return "Connect to the server first."
        if not self._currentVersionId:
            return "Create or select a version first."
        if self._isLocalProjectMode():
            missing = ", ".join(self._missingProjectAssets())
            if missing:
                return "Fill project data first: %s." % missing
            return ""
        if not self._server_pulled:
            return "Pull the server project first."
        return ""

    def _updateVersionActionButtons(self) -> None:
        if not self._connected or self._suppress_asset_ui_updates > 0:
            return
        if not _qt_widget_is_valid(getattr(self, "pushButton", None)):
            return
        self.createButton.setStyleSheet(BTN_CREATE)
        self.createButton.setEnabled(True)
        self.createButton.setToolTip("")
        push_ok = self._canPush()
        self.pushButton.setStyleSheet(BTN_PUSH)
        self.pushButton.setEnabled(push_ok)
        self.pushButton.setToolTip("" if push_ok else self._pushDisabledReason())
        if self._isLocalProjectMode():
            self.pullButton.setEnabled(False)
            return
        self.pullButton.setEnabled(True)

    def _selectLocalProject(self) -> None:
        local_index = self.projectCombo.findText(LOCAL_PROJECT_NAME)
        if local_index >= 0:
            self.projectCombo.setCurrentIndex(local_index)

    def _updateProjectModeUi(self) -> None:
        if not self._connected:
            return
        if self._isServerProjectMode():
            if self._active_server_project != self._currentProjectName():
                self._server_files_loaded = False
                self._server_pulled = False
                self._project_history_bundle = None
                self._active_server_project = self._currentProjectName()
            if not self._server_files_loaded:
                self._clearProjectAssetFields()
                self._setProjectAssetFieldsEnabled(False)
            else:
                self._setProjectAssetFieldsEnabled(True)
        else:
            self._server_files_loaded = False
            self._server_pulled = False
            self._project_history_bundle = None
            self._active_server_project = None
            self._local_project_created = False
            self._local_project_name = None
            self._local_project_description = None
            self._setProjectAssetFieldsEnabled(True)
        self._updateCommitHistoryPanel()
        if self._connected:
            self._updateVersionActionButtons()
        self._updateRightDockAvailability()

    def _shouldShowCommitHistory(self) -> bool:
        return self._isServerProjectMode() and self._server_pulled

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
            self.historyPlaceholder.setText("Connect to the server to begin.")
        elif self._isServerProjectMode():
            self.historyPlaceholder.setText("Pull to load commit history from the server.")
        else:
            self.historyPlaceholder.setText(
                "Commit history is available for server projects after Pull."
            )

    def _simulateServerPull(self, version_id=None) -> None:
        apply_server_pull(self, version_id)

    def _initOntologyFromPreset(self, preset_index: int) -> None:
        if preset_index < 0 or preset_index >= len(self._ontology_preset_ids):
            preset_index = 0
        preset_id = self._ontology_preset_ids[preset_index]
        try:
            document = load_preset(preset_id)
        except (OSError, ValueError) as error:
            self._appendFeed("Ontology preset error: %s" % error, error=True)
            return
        self._applyOntologyDocument(document)
        self.ontologyPresetCombo.blockSignals(True)
        self.ontologyPresetCombo.setCurrentIndex(preset_index + 1)
        self.ontologyPresetCombo.blockSignals(False)

    def _applyOntologyDocument(self, document) -> None:
        self._ontology_document = document
        if self.logic and self.logic._dependencyCanvas:
            self.logic._dependencyCanvas.set_specs(
                document_to_graph_specs(document),
                graph_title=document.get("name"),
            )
        self._updateRightDockAvailability()
        self._updateVersionActionButtons()

    def getOntologyGraphPayload(self):
        if not self._connected:
            return {
                "specs": [],
                "title": "Ontology",
                "description": "Connect to the server to begin.",
            }
        if self._isServerProjectMode() and not self._server_pulled:
            return {
                "specs": [],
                "title": "Ontology",
                "description": "Dependency graph is not available — Pull a server project first.",
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
        if self._isServerProjectMode() and not self._connected:
            self._appendFeed("Connect to the server to open a remote project.", error=True)
            self.projectCombo.blockSignals(True)
            self._selectLocalProject()
            self.projectCombo.blockSignals(False)
            return

        if self._isServerProjectMode():
            self._server_files_loaded = False
            self._server_pulled = False
            self._project_history_bundle = None
            self._local_project_created = False
            self._local_project_name = None
            self._refreshUiState()
            self._appendFeed("Server project selected: %s — Pull to load data" % self._currentProjectName())
            return

        self._local_project_created = False
        self._local_project_name = None
        self._local_project_description = None
        self._currentVersionId = None
        self._refreshUiState()
        self._appendFeed("Local — new project: use Create to configure and start.")

    def _versionDisplayTag(self, version_id: str) -> str:
        bundle = getattr(self, "_project_history_bundle", None) or {}
        return format_version_display_plain(version_id, bundle.get("tags_by_id"))

    def getVersionTreePayload(self):
        if not self._connected:
            return {
                "specs": [],
                "title": "Version tree",
                "description": "Connect to the server to begin.",
            }
        if self._isLocalProjectMode():
            return {
                "specs": [],
                "title": "Version tree",
                "description": "Version tree is not available — no server project selected.",
            }
        if not self._server_pulled:
            return {
                "specs": [],
                "title": "Version tree",
                "description": "Version tree is not available — Pull a server project first.",
            }
        return {
            "specs": list((getattr(self, "_project_history_bundle", None) or {}).get("version_specs", [])),
            "title": self._currentProjectName() or "Version tree",
            "description": "",
        }

    def onOntologyPresetChanged(self, index: int) -> None:
        if self._serverAwaitingPull():
            return
        if index == ONTOLOGY_COMBO_NONE_INDEX:
            self._clearOntologyDocument()
            self._removeServerOntologyComboEntry()
            self._updateRightDockAvailability()
            return
        if index == self._ontology_server_combo_index:
            return
        self._removeServerOntologyComboEntry()
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
        self._appendFeed("Ontology loaded: %s" % document.get("name"))

    def onOntologyJsonHelp(self) -> None:
        dialog = OntologyJsonHelpDialog(slicer.util.mainWindow())
        dialog.exec_()

    def onLoadOntologyJson(self) -> None:
        if self._serverAwaitingPull():
            self._appendFeed("Pull required before loading ontology from server project.", error=True)
            return
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
        if self._serverAwaitingPull():
            self._appendFeed("Pull required before editing ontology.", error=True)
            return
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

    def cleanup(self) -> None:
        self._closeLogicDialogs()
        self._disconnectProjectAssetSignals()
        self._teardownRightDock()
        if self._rightDock and slicer.util.mainWindow():
            slicer.util.mainWindow().removeDockWidget(self._rightDock)
            self._rightDock.deleteLater()
        self._rightDock = None
        self.removeObservers()

    def onConnect(self) -> None:
        server_url = self.serverUrlEdit.text.strip()
        user_id = self.userIdEdit.text.strip()
        password = self.passwordEdit.text

        if not server_url:
            self._appendFeed("Error: server URL is empty.", error=True)
            return
        if not user_id:
            self._appendFeed("Error: user ID is required.", error=True)
            return
        if not password:
            self._appendFeed("Error: password is required to connect.", error=True)
            return

        self._connected = True
        self.connectionStatusLabel.text = "Connected — %s" % user_id
        self.connectionStatusLabel.setStyleSheet(STATUS_OK)
        self._populateProjectCombo()
        self._refreshUiState()
        self._appendFeed("Simulated connection: %s@%s (E2)." % (user_id, server_url))

    def _promptNewProjectConfig(self) -> dict | None:
        dialog = ProjectConfigDialog(slicer.util.mainWindow())
        if dialog.exec_() != qt.QDialog.Accepted:
            return None
        values = dialog.values()
        if not values["name"]:
            self._appendFeed("Project name is required.", error=True)
            return None
        return values

    def _formatMainVersion(self, revision: int) -> str:
        return "main/%d" % revision

    def _parseMainRevision(self, version_id: str) -> int | None:
        if not version_id.startswith("main/"):
            return None
        try:
            return int(version_id.split("/", 1)[1])
        except ValueError:
            return None

    def _nextMainVersionId(self) -> str:
        max_revision = 0
        for row in range(_qt_table_row_count(self.historyTableWidget)):
            version_item = self.historyTableWidget.item(row, 0)
            if not version_item:
                continue
            revision = self._parseMainRevision(self._historyVersionIdFromItem(version_item))
            if revision is not None:
                max_revision = max(max_revision, revision)
        if max_revision == 0 and self._currentVersionId:
            revision = self._parseMainRevision(self._currentVersionId)
            if revision is not None:
                max_revision = revision
        return self._formatMainVersion(max_revision + 1)

    def onCreateVersion(self) -> None:
        if not self._connected:
            self._appendFeed("Connect to the server first.", error=True)
            return
        if not self._projectAssetsComplete():
            missing = ", ".join(self._missingProjectAssets())
            slicer.util.warningDisplay(
                "Cannot create a project yet.\n\n"
                "Fill in all project data first:\n"
                "• 3D Volume\n"
                "• Segmentation\n"
                "• Ontology map\n\n"
                "Missing: %s" % missing
            )
            self._appendFeed(
                "Create blocked — missing project data: %s." % missing,
                error=True,
            )
            return

        if self._isLocalProjectMode():
            if not self._local_project_created:
                config = self._promptNewProjectConfig()
                if config is None:
                    return
                self._local_project_name = config["name"]
                self._local_project_description = config["description"]
                self._local_project_created = True
                version_id = self._formatMainVersion(1)
                message = config["message"]
                self._currentVersionId = version_id
                self._appendFeed(
                    "Project created: « %s » — %s (%s)"
                    % (self._local_project_name, version_id, message)
                )
                if self._local_project_description:
                    self._appendFeed("Description: %s" % self._local_project_description)
                self._updateVersionActionButtons()
                self._updateRightDockAvailability()
                return

            message = self._promptCommitMessage(
                "New version",
                "Commit message:",
                "New version on main",
            )
            if message is None:
                return
            author = self.userIdEdit.text.strip() or "annotator"
            version_id = self._nextMainVersionId()
            self._currentVersionId = version_id
            self._appendFeed("Version created: %s — %s" % (version_id, message))
            self._updateVersionActionButtons()
            return

        default_message = "Initial commit" if not self._currentVersionId else "New version"
        message = self._promptCommitMessage(
            "Create version",
            "Commit message:",
            default_message,
        )
        if message is None:
            return

        author = self.userIdEdit.text.strip() or "annotator"
        version_id = self._nextMainVersionId()
        self._currentVersionId = version_id

        if self._shouldShowCommitHistory():
            self._prependHistoryRow(
                version_id,
                datetime.now().strftime("%Y-%m-%d %H:%M"),
                author,
                message,
                "local",
            )
        self._appendFeed("Create simulated: %s — %s" % (version_id, message))
        self._updateVersionActionButtons()

    def onPush(self) -> None:
        if not self._connected:
            self._appendFeed("Connect to the server first.", error=True)
            return
        if not self._canPush():
            reason = self._pushDisabledReason()
            if reason:
                self._appendFeed(reason, error=True)
            return
        if not self._currentVersionId:
            self._appendFeed("Create or select a version first.", error=True)
            return

        message = self._promptCommitMessage(
            "Push",
            "Commit message:",
            "Push changes",
        )
        if message is None:
            return

        if self._isServerProjectMode():
            meta = DEMO_SERVER_PROJECTS.get(self._currentProjectName(), {})
            self._appendFeed(
                "Push simulated to server: %s — %s (vol=%s, seg=%s, ont=%s)"
                % (
                    self._currentVersionId,
                    message,
                    meta.get("volume", "—"),
                    meta.get("segmentation", "—"),
                    meta.get("ontology", "—"),
                )
            )
        else:
            volume_name = self.volumeSelector.currentNode().GetName() if self.volumeSelector.currentNode() else "—"
            seg_name = self.segmentationSelector.currentNode().GetName() if self.segmentationSelector.currentNode() else "—"
            ont_name = self._ontology_document.get("name", "—") if self._ontology_document else "—"
            self._appendFeed(
                "Push simulated (local): %s — %s (vol=%s, seg=%s, ont=%s)"
                % (self._currentVersionId, message, volume_name, seg_name, ont_name)
            )
        self._updateHistoryStatus(self._currentVersionId, "pushed")
        self._updateHistoryMessage(self._currentVersionId, message)

    def onPull(self) -> None:
        if self._isServerProjectMode():
            if not self._connected:
                self._appendFeed("Connect to the server first.", error=True)
                return
            bundle = getattr(self, "_project_history_bundle", None) or {}
            commit_order = self._selectedVersionId() or bundle.get("head_version")
            self._simulateServerPull(commit_order)
            return

        self._appendFeed(
            "Local project: commit history is shown for server projects after Pull (E2).",
            error=True,
        )

    def onHistorySelectionChanged(self) -> None:
        if getattr(self, "_suppress_history_selection_signal", False):
            return
        selected_version_id = self._selectedVersionId()
        if selected_version_id:
            self._setCheckedOutVersion(selected_version_id, notify=True, sync_table=False)

    def _setCheckedOutVersion(
        self,
        version_id: str,
        notify: bool = False,
        sync_table: bool = True,
    ) -> None:
        if not version_id:
            return
        changed = version_id != self._currentVersionId
        self._currentVersionId = version_id
        self._updateActiveVersionIndicators()
        if sync_table:
            self._selectHistoryRowForVersion(version_id)
        if notify and changed:
            self._appendFeed(
                "Checked out %s (simulation — assets unchanged)."
                % self._versionDisplayTag(version_id)
            )
        self._updateVersionActionButtons()

    def _selectHistoryRowForVersion(self, version_id: str) -> None:
        table = self.historyTableWidget
        if not _qt_widget_is_valid(table):
            return
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
            self._suppress_history_selection_signal = False

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
        if canvas and _qt_widget_is_valid(canvas) and hasattr(canvas, "set_active_version_id"):
            canvas.set_active_version_id(active)

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
            return str(version_id)
        return id_item.text() if id_item else None

    def _historyVersionIdFromItem(self, item: qt.QTableWidgetItem) -> str:
        version_id = item.data(qt.Qt.UserRole)
        return str(version_id) if version_id else item.text()

    def _styleHistoryCell(self, item: qt.QTableWidgetItem, column: int, status: str = "", version_id: str = "") -> None:
        if column == 0:
            branch = (version_id or item.data(qt.Qt.UserRole) or item.text() or "").split("/", 1)[0]
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

    def _prependHistoryRow(self, version_id, date_display, author, message, status) -> None:
        self.historyTableWidget.insertRow(0)
        row_values = [version_id, date_display, author, message, status]
        for column_index, value in enumerate(row_values):
            if column_index == 0:
                item = qt.QTableWidgetItem(self._versionDisplayTag(version_id))
                item.setData(qt.Qt.UserRole, version_id)
            else:
                item = qt.QTableWidgetItem(str(value))
            self._styleHistoryCell(item, column_index, status, version_id=version_id)
            self.historyTableWidget.setItem(0, column_index, item)
        self.historyTableWidget.resizeColumnsToContents()

    def _updateHistoryStatus(self, version_id, status) -> None:
        for row in range(_qt_table_row_count(self.historyTableWidget)):
            id_item = self.historyTableWidget.item(row, 0)
            if id_item and self._historyVersionIdFromItem(id_item) == version_id:
                status_item = qt.QTableWidgetItem(status)
                self._styleHistoryCell(status_item, 4, status, version_id=version_id)
                self.historyTableWidget.setItem(row, 4, status_item)
                break

    def _updateHistoryMessage(self, version_id, message) -> None:
        for row in range(_qt_table_row_count(self.historyTableWidget)):
            id_item = self.historyTableWidget.item(row, 0)
            if id_item and self._historyVersionIdFromItem(id_item) == version_id:
                self.historyTableWidget.setItem(row, 3, qt.QTableWidgetItem(message))
                break

    def _appendFeed(self, message: str, error: bool = False) -> None:
        timestamp = datetime.now().strftime("%H:%M")
        prefix = "[ERROR]" if error else "[INFO]"
        line = f"[{timestamp}] {prefix} {message}"
        logging.info(line)
        if getattr(self, "feedTextEdit", None):
            color = FEED_COLOR_ERROR if error else FEED_COLOR_INFO
            self.feedTextEdit.append(f'<span style="color:{color}">{line}</span>')


class CollaborativeVersioningLogic(ScriptedLoadableModuleLogic):
    """E2 UI MVP — graph rendering only (back-end to be wired later)."""

    def __init__(self) -> None:
        ScriptedLoadableModuleLogic.__init__(self)
        self.widget = None
        self.dependencyDialog = None
        self.historyDialog = None
        self._dependencyCanvas = None
        self._historyCanvas = None
        self._pending_import_project = None

    def setWidget(self, widget) -> None:
        self.widget = widget

    def onVersionCheckedOut(self, version_id: str) -> None:
        widget = self.widget
        if not widget or self._pending_import_project:
            return
        widget._setCheckedOutVersion(version_id, notify=True, sync_table=True)

    def onVersionNodeSelected(self, version_id: str) -> None:
        if not self._pending_import_project:
            return

        project_name = self._pending_import_project
        widget = self.widget
        if not widget:
            return

        confirm = qt.QMessageBox.question(
            slicer.util.mainWindow(),
            "Import version",
            "Import version %s\n(project: %s) ?\n\n(UI only — simulated Pull on server)"
            % (format_version_display_plain(version_id, (getattr(widget, "_project_history_bundle", None) or {}).get("tags_by_id")), project_name),
            qt.QMessageBox.Yes | qt.QMessageBox.No,
            qt.QMessageBox.Yes,
        )
        if confirm != qt.QMessageBox.Yes:
            return

        if widget._isServerProjectMode():
            widget._simulateServerPull(version_id)
        widget._currentVersionId = version_id
        widget._appendFeed(
            "Import / Pull simulated: %s for « %s »."
            % (version_id, project_name)
        )

        self._pending_import_project = None
        if self.historyDialog and self.historyDialog.isVisible():
            self.historyDialog.close()

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
        self.dependencyDialog.setWindowFlags(qt.Qt.Window | qt.Qt.WindowStaysOnTopHint)
        self.dependencyDialog.setWindowTitle(
            "Dependency graph — %s" % graph_module.GRAPH_BUILD_TAG
        )
        self.dependencyDialog.resize(980, 640)

        layout = qt.QVBoxLayout(self.dependencyDialog)
        layout.setContentsMargins(12, 12, 12, 12)

        payload = widget.getOntologyGraphPayload() if widget else {
            "specs": [],
            "title": "Ontology",
            "description": "No ontology loaded.",
        }

        hint = qt.QLabel(
            payload["description"] or "Dependency graph built from the project ontology map."
        )
        hint.setStyleSheet(DIALOG_HINT_STYLE)
        hint.setWordWrap(True)
        layout.addWidget(hint)

        self._dependencyCanvas = graph_module.DependencyGraphCanvas(
            self,
            dependency_specs=payload["specs"],
            graph_title=payload["title"],
            graph_description=payload["description"],
        )
        layout.addWidget(self._dependencyCanvas.create_toolbar())
        layout.addWidget(self._dependencyCanvas, 1)

        self.dependencyDialog.show()
        self.dependencyDialog.raise_()
        self.dependencyDialog.activateWindow()
        qt.QTimer.singleShot(50, self._dependencyCanvas.reset_view)

    def openVersionHistoryGraph(self, for_import: bool = False, project_name: str | None = None) -> None:
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
        if widget and not for_import:
            payload = widget.getVersionTreePayload()
            version_specs = payload["specs"]
            graph_title = payload["title"]
            graph_description = payload["description"]
            commit_history_by_id = graph_module.commit_history_lookup(
                (getattr(widget, "_project_history_bundle", None) or {}).get("commit_history", [])
            )
        elif widget and for_import:
            try:
                bundle = load_project_history_bundle(project_name or widget._currentProjectName())
                version_specs = bundle["version_specs"]
                graph_title = project_name or widget._currentProjectName() or "Version tree"
                commit_history_by_id = graph_module.commit_history_lookup(bundle.get("commit_history", []))
            except (OSError, ValueError):
                version_specs = []
        self._pending_import_project = project_name if for_import else None

        self.historyDialog = qt.QDialog(slicer.util.mainWindow())
        self.historyDialog.setWindowFlags(qt.Qt.Window | qt.Qt.WindowStaysOnTopHint)
        dialog_title = "Choose a version" if for_import else "Version tree"
        self.historyDialog.setWindowTitle("%s — %s" % (dialog_title, graph_module.GRAPH_BUILD_TAG))
        self.historyDialog.resize(820, 620)

        layout = qt.QVBoxLayout(self.historyDialog)
        layout.setContentsMargins(12, 12, 12, 12)

        if for_import:
            hint_text = "Project: %s — click a node (simulated Pull in server mode)" % (project_name or "—")
        else:
            hint_text = graph_description or "Version tree built from the project commit history."
        hint = qt.QLabel(hint_text)
        hint.setStyleSheet(DIALOG_HINT_STYLE)
        hint.setWordWrap(True)
        layout.addWidget(hint)

        canvas = graph_module.VersionHistoryCanvas(
            self,
            version_specs=version_specs,
            selection_mode=for_import,
            graph_title=graph_title,
            graph_description=graph_description,
            active_version_id=getattr(widget, "_currentVersionId", None) if widget and not for_import else None,
            commit_history_by_id=commit_history_by_id,
        )
        self._historyCanvas = canvas
        layout.addWidget(canvas.create_toolbar())
        layout.addWidget(canvas, 1)

        def _clear_import_mode(*_args):
            self._pending_import_project = None

        self.historyDialog.connect("finished(int)", _clear_import_mode)

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
        self.assertTrue(_UI_BUILD_TAG.startswith("2026-07-"))
        self.delayDisplay("CollaborativeVersioning UI layout tests passed")
