"""Module logic (split from CollaborativeVersioning.py). Behavior unchanged."""
from __future__ import annotations

import importlib

import qt
import slicer
from slicer.ScriptedLoadableModule import *

from CollaborativeVersioningLib.UiStyles import DIALOG_HINT_STYLE


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
                    "🔵 = that exact version awaits review "
                    "(double-click the 🔵 node to Accept or Decline)"
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


