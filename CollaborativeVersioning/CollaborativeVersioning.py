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
_UI_BUILD_TAG = "2026-07-17-ui-theme-ice-clinic-v18-en"

_LIB_MODULE_NAMES = (
    "CollaborativeVersioningLib.UiStyles",
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

from CollaborativeVersioningLib.GraphCanvas import GRAPH_BUILD_TAG
from CollaborativeVersioningLib.OntologyLoader import (
    OntologyEditorDialog,
    document_to_graph_specs,
    load_ontology_file,
    load_preset,
    preset_choices,
    save_ontology_file,
)
from CollaborativeVersioningLib.UiStyles import (
    BTN_CONNECT,
    BTN_CREATE,
    BTN_DEPENDENCY,
    BTN_HISTORY,
    BTN_PULL,
    BTN_PUSH,
    BTN_SECONDARY,
    COMMIT_STATUS_COLORS,
    DIALOG_HEADER_STYLE,
    DIALOG_HINT_STYLE,
    DOCK_STYLE,
    FEED_COLOR_ERROR,
    FEED_COLOR_INFO,
    FEED_STYLE,
    FIELD_STYLE,
    PLACEHOLDER_STYLE,
    SECTION_TITLE_STYLE,
    SEPARATOR_STYLE,
    STATUS_NEUTRAL,
    STATUS_OK,
    STATUS_WARNING,
    TABLE_STYLE,
    TEXT_MUTED,
    TEXT_SECONDARY,
)

LOCAL_PROJECT_NAME = "Local"
ONTOLOGY_COMBO_NONE_LABEL = "None"
ONTOLOGY_COMBO_NONE_INDEX = 0


def _qt_get_text(widget) -> str:
    value = widget.text if hasattr(widget, "text") and not callable(widget.text) else widget.text()
    if callable(value):
        value = value()
    return str(value).strip()


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


DEMO_SERVER_PROJECTS = {
    "Server — Project 1 — Allen mouse": {
        "volume": "brain_ccf_v3.nrrd",
        "segmentation": "annotations_main_v16.seg.nrrd",
        "ontology": "allen_mouse_brain_ccf_v3.json",
        "main_version": "6",
    },
    "Server — Project 2 — Human striatum": {
        "volume": "mri_striatum_t1.nii.gz",
        "segmentation": "striatum_labels_v8.seg.nrrd",
        "ontology": "minimal_brain_regions.json",
        "main_version": "6",
    },
    "Server — Project 3 — Collaborative demo": {
        "volume": "demo_volume.nrrd",
        "segmentation": "demo_seg.seg.nrrd",
        "ontology": "minimal_brain_regions.json",
        "main_version": "6",
    },
}

# Simulated server commit log — column 1 is chronological order (1 = oldest).
DEMO_COMMIT_HISTORY = [
    ("6", "2026-07-10 14:30", "Camille Bernard", "Release v4.0 — Allen CCF v3 alignment", "pushed"),
    ("5", "2026-07-09 11:05", "Dr. Elena Vasquez", "Expert review: striatum boundaries", "pushed"),
    ("4", "2026-07-08 09:40", "Lucas Petit", "Merge branch 'feature/mesencephalon'", "merged"),
    ("3", "2026-07-05 16:20", "Marie Dubois", "Refine hippocampus labels on coronal slices", "pushed"),
    ("2", "2026-07-03 10:15", "Thomas Laurent", "Merge feature/striatum into main", "merged"),
    ("1", "2026-06-28 08:00", "Sophie Martin", "Initial import from Allen Brain Atlas", "pushed"),
]


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
        self._server_pulled = False
        self._ontology_document = None
        self._ontology_preset_ids = [preset_id for preset_id, _label in preset_choices()]
        self._connected = False
        self._server_files_loaded = False
        self._active_server_project = None

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
        self._updateProjectModeUi()
        self._ensureLocalDefaultOntology()
        self.setupDeveloperSection()
        self._appendFeed(_("Collaborative Versioning module — UI MVP (E2)."))
        self._appendFeed(f"Build UI : {_UI_BUILD_TAG}")
        self._appendFeed(f"Graph build : {GRAPH_BUILD_TAG}")

    def _clearLayout(self) -> None:
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

        self.serverUrlEdit = qt.QLineEdit("http://localhost:8000")
        self.serverUrlEdit.setPlaceholderText("http://localhost:8000")
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
        self.loadOntologyButton = qt.QPushButton("Load JSON…")
        self.editOntologyButton = qt.QPushButton("Edit")
        self.exportOntologyButton = qt.QPushButton("Export")
        for btn in (self.loadOntologyButton, self.editOntologyButton, self.exportOntologyButton):
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
        projectLayout.addWidget(actionsRow)

        self.layout.addStretch(1)

        self.connectButton.connect("clicked()", self.onConnect)
        self.projectCombo.connect("currentIndexChanged(int)", self.onProjectChanged)
        self.ontologyPresetCombo.connect("currentIndexChanged(int)", self.onOntologyPresetChanged)
        self.loadOntologyButton.connect("clicked()", self.onLoadOntologyJson)
        self.editOntologyButton.connect("clicked()", self.onEditOntology)
        self.exportOntologyButton.connect("clicked()", self.onExportOntologyJson)
        self.createButton.connect("clicked()", self.onCreateVersion)
        self.pushButton.connect("clicked()", self.onPush)
        self.pullButton.connect("clicked()", self.onPull)

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

    def _setOntologyComboNone(self) -> None:
        self.ontologyPresetCombo.blockSignals(True)
        self.ontologyPresetCombo.setCurrentIndex(ONTOLOGY_COMBO_NONE_INDEX)
        self.ontologyPresetCombo.blockSignals(False)

    def _clearProjectAssetFields(self) -> None:
        self.volumeSelector.setCurrentNode(None)
        self.segmentationSelector.setCurrentNode(None)
        self._clearOntologyDocument()
        self._setOntologyComboNone()

    def _setProjectAssetFieldsEnabled(self, enabled: bool) -> None:
        self.volumeSelector.setEnabled(enabled)
        self.segmentationSelector.setEnabled(enabled)
        self.ontologyPresetCombo.setEnabled(enabled)
        self.loadOntologyButton.setEnabled(enabled)
        self.editOntologyButton.setEnabled(enabled)
        self.exportOntologyButton.setEnabled(enabled)

    def _buildRightDock(self) -> None:
        mainWin = slicer.util.mainWindow()
        for oldDock in mainWin.findChildren(qt.QDockWidget, "CollaborativeVersioning_RightDock"):
            mainWin.removeDockWidget(oldDock)
            oldDock.deleteLater()

        self._rightDock = qt.QDockWidget("Collaborative Versioning — Collaborative mode", mainWin)
        self._rightDock.setObjectName("CollaborativeVersioning_RightDock")
        self._rightDock.setAllowedAreas(qt.Qt.RightDockWidgetArea)

        container = qt.QWidget()
        container.setStyleSheet(DOCK_STYLE)
        layout = qt.QVBoxLayout(container)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(12)

        graphsTitle = qt.QLabel("VISUAL EXPLORATION")
        graphsTitle.setStyleSheet(SECTION_TITLE_STYLE)
        layout.addWidget(graphsTitle)

        self.btnDependencyGraph = qt.QPushButton("View dependency graph")
        self.btnDependencyGraph.setStyleSheet(BTN_DEPENDENCY)
        layout.addWidget(self.btnDependencyGraph)

        self.btnHistoryGraph = qt.QPushButton("View version tree")
        self.btnHistoryGraph.setStyleSheet(BTN_HISTORY)
        layout.addWidget(self.btnHistoryGraph)

        historyTitle = qt.QLabel("COMMIT HISTORY")
        historyTitle.setStyleSheet(SECTION_TITLE_STYLE)
        layout.addWidget(historyTitle)

        self.historyPlaceholder = qt.QLabel(
            "Commit history is available for server projects after Pull."
        )
        self.historyPlaceholder.setWordWrap(True)
        self.historyPlaceholder.setStyleSheet(PLACEHOLDER_STYLE)
        layout.addWidget(self.historyPlaceholder)

        self.historyTableWidget = qt.QTableWidget()
        self.historyTableWidget.setColumnCount(5)
        self.historyTableWidget.setHorizontalHeaderLabels(["#", "Date", "Author", "Message", "Status"])
        self.historyTableWidget.setAlternatingRowColors(True)
        self.historyTableWidget.setSelectionBehavior(qt.QAbstractItemView.SelectRows)
        self.historyTableWidget.setSelectionMode(qt.QAbstractItemView.SingleSelection)
        self.historyTableWidget.setEditTriggers(qt.QAbstractItemView.NoEditTriggers)
        self.historyTableWidget.setStyleSheet(TABLE_STYLE)
        self.historyTableWidget.horizontalHeader().setStretchLastSection(True)
        self.historyTableWidget.setMinimumHeight(130)
        self.historyTableWidget.setMaximumHeight(180)
        self.historyTableWidget.setVisible(False)
        layout.addWidget(self.historyTableWidget)

        self.refreshHistoryButton = qt.QPushButton("Refresh commits")
        self.refreshHistoryButton.setStyleSheet(BTN_SECONDARY + " font-size: 10px; padding: 4px 8px;")
        self.refreshHistoryButton.setVisible(False)
        layout.addWidget(self.refreshHistoryButton)

        separator = qt.QFrame()
        separator.setFrameShape(qt.QFrame.HLine)
        separator.setFrameShadow(qt.QFrame.Plain)
        separator.setStyleSheet(SEPARATOR_STYLE)
        layout.addWidget(separator)

        activityTitle = qt.QLabel("LIVE ACTIVITY FEED")
        activityTitle.setStyleSheet(SECTION_TITLE_STYLE)
        layout.addWidget(activityTitle)

        self.feedTextEdit = qt.QTextEdit()
        self.feedTextEdit.setReadOnly(True)
        self.feedTextEdit.setStyleSheet(FEED_STYLE)
        layout.addWidget(self.feedTextEdit, 1)

        self._rightDock.setWidget(container)
        mainWin.addDockWidget(qt.Qt.RightDockWidgetArea, self._rightDock)

        self.btnDependencyGraph.connect("clicked()", self.onOpenDependencyGraph)
        self.btnHistoryGraph.connect("clicked()", self.onOpenHistoryGraph)
        self.refreshHistoryButton.connect("clicked()", self._refreshHistoryTable)
        self.historyTableWidget.connect("itemSelectionChanged()", self.onHistorySelectionChanged)

    def _setupDefaults(self) -> None:
        self.userIdEdit.text = os.environ.get("USER", os.environ.get("USERNAME", "annotator"))

    def _promptCommitMessage(self, title: str, label: str, default: str = "") -> str | None:
        message, ok = qt.QInputDialog.getText(
            slicer.util.mainWindow(),
            title,
            label,
            text=default,
        )
        if not ok or not message.strip():
            return None
        return message.strip()

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

    def _selectLocalProject(self) -> None:
        local_index = self.projectCombo.findText(LOCAL_PROJECT_NAME)
        if local_index >= 0:
            self.projectCombo.setCurrentIndex(local_index)

    def _ensureLocalDefaultOntology(self) -> None:
        if self._isServerProjectMode():
            return
        if self._ontology_document is None:
            self._initOntologyFromPreset(0)

    def _updateProjectModeUi(self) -> None:
        if self._isServerProjectMode():
            if self._active_server_project != self._currentProjectName():
                self._server_files_loaded = False
                self._server_pulled = False
                self._active_server_project = self._currentProjectName()
            if not self._server_files_loaded:
                self._clearProjectAssetFields()
                self._setProjectAssetFieldsEnabled(False)
            else:
                self._setProjectAssetFieldsEnabled(True)
        else:
            self._server_files_loaded = False
            self._server_pulled = False
            self._active_server_project = None
            self._setProjectAssetFieldsEnabled(True)
        self._updateCommitHistoryPanel()

    def _shouldShowCommitHistory(self) -> bool:
        return self._isServerProjectMode() and self._server_pulled

    def _updateCommitHistoryPanel(self) -> None:
        if not getattr(self, "historyTableWidget", None):
            return
        if self._shouldShowCommitHistory():
            self.historyPlaceholder.setVisible(False)
            self.historyTableWidget.setVisible(True)
            self.refreshHistoryButton.setVisible(True)
            self._refreshHistoryTable()
            return

        self.historyPlaceholder.setVisible(True)
        self.historyTableWidget.setVisible(False)
        self.refreshHistoryButton.setVisible(False)
        self.historyTableWidget.setRowCount(0)
        if self._isServerProjectMode():
            self.historyPlaceholder.setText("Pull to load commit history from the server.")
        else:
            self.historyPlaceholder.setText(
                "Commit history is available for server projects after Pull."
            )

    def _simulateServerPull(self, version_id=None) -> None:
        project_name = self._currentProjectName()
        meta = DEMO_SERVER_PROJECTS.get(project_name)
        if not meta:
            return

        version_id = version_id or meta["main_version"]
        self._currentVersionId = version_id
        self._server_pulled = True
        # E2: back-end not wired — Pull does not load assets yet.
        self._server_files_loaded = False
        self._clearProjectAssetFields()
        self._setProjectAssetFieldsEnabled(False)
        self._updateCommitHistoryPanel()

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
                graph_description=document.get("description"),
            )

    def getOntologyGraphPayload(self):
        if not self._ontology_document:
            return {
                "specs": [],
                "title": "Ontology",
                "description": "No ontology loaded.",
            }
        document = self._ontology_document
        return {
            "specs": document_to_graph_specs(document),
            "title": document.get("name", "Ontology"),
            "description": document.get("description", ""),
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
            self._updateProjectModeUi()
            self._appendFeed("Server project selected: %s — Pull to load data" % self._currentProjectName())
        else:
            self._updateProjectModeUi()
            self._ensureLocalDefaultOntology()
            self._appendFeed("Local project — using current 3D Slicer scene.")

    def onOntologyPresetChanged(self, index: int) -> None:
        if self._serverAwaitingPull():
            return
        if index == ONTOLOGY_COMBO_NONE_INDEX:
            self._clearOntologyDocument()
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
        self._appendFeed("Ontology loaded: %s" % document.get("name"))

    def onLoadOntologyJson(self) -> None:
        if self._serverAwaitingPull():
            self._appendFeed("Pull required before loading ontology from server project.", error=True)
            return
        path = qt.QFileDialog.getOpenFileName(
            None,
            "Load ontology JSON",
            os.path.expanduser("~"),
            "JSON (*.json)",
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
        self._appendFeed("Ontology imported: %s (%d node(s))" % (document["name"], len(document["nodes"])))

    def onEditOntology(self) -> None:
        if self._serverAwaitingPull():
            self._appendFeed("Pull required before editing ontology.", error=True)
            return
        if not self._ontology_document:
            self._initOntologyFromPreset(0)
        dialog = OntologyEditorDialog(self._ontology_document, slicer.util.mainWindow())
        if dialog.exec_() != qt.QDialog.Accepted:
            return
        self._applyOntologyDocument(dialog.result_document())
        self._appendFeed("Ontology edited: %s (UI)" % self._ontology_document["name"])

    def onExportOntologyJson(self) -> None:
        if not self._ontology_document:
            self._appendFeed("No ontology to export.", error=True)
            return
        default_name = (self._ontology_document.get("name") or "ontology").replace(" ", "_") + ".json"
        path = qt.QFileDialog.getSaveFileName(
            None,
            "Export ontology JSON",
            os.path.join(os.path.expanduser("~"), default_name),
            "JSON (*.json)",
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
        self._updateProjectModeUi()
        self._appendFeed("Simulated connection: %s@%s (E2)." % (user_id, server_url))

    def _nextCommitOrder(self) -> str:
        max_order = 0
        for row in range(self.historyTableWidget.rowCount):
            order_item = self.historyTableWidget.item(row, 0)
            if not order_item:
                continue
            try:
                max_order = max(max_order, int(order_item.text()))
            except ValueError:
                continue
        return str(max_order + 1)

    def onCreateVersion(self) -> None:
        if self._isServerProjectMode() and not self._connected:
            self._appendFeed("Connect to the server first.", error=True)
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
        commit_order = self._nextCommitOrder()
        self._currentVersionId = commit_order

        if self._shouldShowCommitHistory():
            self._prependHistoryRow(
                commit_order,
                datetime.now().strftime("%Y-%m-%d %H:%M"),
                author,
                message,
                "local",
            )
        self._appendFeed("Create simulated: #%s — %s" % (commit_order, message))

    def onPush(self) -> None:
        if self._isServerProjectMode() and not self._connected:
            self._appendFeed("Connect to the server first.", error=True)
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
            commit_order = self._selectedVersionId() or DEMO_SERVER_PROJECTS.get(
                self._currentProjectName(), {}
            ).get("main_version")
            self._simulateServerPull(commit_order)
            self._appendFeed(
                "Pull simulated (server): #%s — commit history loaded; assets not wired yet (E2)."
                % (commit_order or "latest")
            )
            return

        self._appendFeed(
            "Local project: commit history is shown for server projects after Pull (E2).",
            error=True,
        )

    def onHistorySelectionChanged(self) -> None:
        selected_version_id = self._selectedVersionId()
        if selected_version_id:
            self._currentVersionId = selected_version_id

    def onOpenDependencyGraph(self) -> None:
        self.logic.openDependencyGraph()

    def onOpenHistoryGraph(self) -> None:
        self.logic.openVersionHistoryGraph()

    def _selectedVersionId(self) -> str | None:
        selected_items = self.historyTableWidget.selectedItems()
        if not selected_items:
            return None
        row = selected_items[0].row()
        id_item = self.historyTableWidget.item(row, 0)
        return id_item.text() if id_item else None

    def _styleHistoryCell(self, item: qt.QTableWidgetItem, column: int, status: str = "") -> None:
        if column == 0:
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
        self.historyTableWidget.setRowCount(len(DEMO_COMMIT_HISTORY))
        for row_index, row_values in enumerate(DEMO_COMMIT_HISTORY):
            status = row_values[4] if len(row_values) > 4 else ""
            for column_index, value in enumerate(row_values):
                item = qt.QTableWidgetItem(str(value))
                self._styleHistoryCell(item, column_index, status)
                self.historyTableWidget.setItem(row_index, column_index, item)
        self.historyTableWidget.resizeColumnsToContents()

    def _prependHistoryRow(self, version_id, date_display, author, message, status) -> None:
        self.historyTableWidget.insertRow(0)
        for column_index, value in enumerate([version_id, date_display, author, message, status]):
            item = qt.QTableWidgetItem(str(value))
            self._styleHistoryCell(item, column_index, status)
            self.historyTableWidget.setItem(0, column_index, item)
        self.historyTableWidget.resizeColumnsToContents()

    def _updateHistoryStatus(self, version_id, status) -> None:
        for row in range(self.historyTableWidget.rowCount):
            id_item = self.historyTableWidget.item(row, 0)
            if id_item and id_item.text() == version_id:
                status_item = qt.QTableWidgetItem(status)
                self._styleHistoryCell(status_item, 4, status)
                self.historyTableWidget.setItem(row, 4, status_item)
                break

    def _updateHistoryMessage(self, version_id, message) -> None:
        for row in range(self.historyTableWidget.rowCount):
            id_item = self.historyTableWidget.item(row, 0)
            if id_item and id_item.text() == version_id:
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
            % (version_id, project_name),
            qt.QMessageBox.Yes | qt.QMessageBox.No,
            qt.QMessageBox.Yes,
        )
        if confirm != qt.QMessageBox.Yes:
            return

        if widget._isServerProjectMode():
            widget._simulateServerPull(version_id)
        widget._currentVersionId = version_id
        widget._appendFeed(
            "Import / Pull simulated: %s for « %s » — no data loaded (E2)."
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
            "specs": graph_module.MOUSE_BRAIN_SPECS,
            "title": "Ontology",
            "description": "",
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

        version_specs = graph_module.VERSION_SPECS
        self._pending_import_project = project_name if for_import else None

        self.historyDialog = qt.QDialog(slicer.util.mainWindow())
        self.historyDialog.setWindowFlags(qt.Qt.Window | qt.Qt.WindowStaysOnTopHint)
        dialog_title = "Choose a version" if for_import else "Version tree"
        self.historyDialog.setWindowTitle("%s — %s" % (dialog_title, graph_module.GRAPH_BUILD_TAG))
        self.historyDialog.resize(820, 620)

        layout = qt.QVBoxLayout(self.historyDialog)
        layout.setContentsMargins(12, 12, 12, 12)

        if for_import:
            header_text = "Project: %s — click a node (simulated Pull in server mode)" % (project_name or "—")
        else:
            header_text = "Version tree — main branch centered + feature branches (UI demo)"
        header = qt.QLabel(header_text)
        header.setStyleSheet(DIALOG_HEADER_STYLE)
        header.setWordWrap(True)
        layout.addWidget(header)

        canvas = graph_module.VersionHistoryCanvas(
            self,
            version_specs=version_specs,
            selection_mode=for_import,
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
        self.assertTrue(_UI_BUILD_TAG.startswith("2026-07-17-ui-layout"))
        self.delayDisplay("CollaborativeVersioning UI layout tests passed")
