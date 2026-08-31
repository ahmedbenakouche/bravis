"""E2 simulation — fake server projects and Pull using files in simulation/data/."""

from __future__ import annotations

import json
import os
from typing import Any

from CollaborativeVersioningLib.DataManager import DataManager
from CollaborativeVersioningLib.OntologyLoader import load_ontology_file

SIMULATION_DIR = os.path.dirname(os.path.abspath(__file__))
SIMULATION_DATA_DIR = os.path.join(SIMULATION_DIR, "data")

HISTORY_SCHEMA_VERSION = 1

# Display names → files expected under simulation/data/
_SERVER_PROJECT_DEFS = (
    (
        "Mouse Brain",
        {
            "volume": "mouse_brain_reference.nii",
            "segmentation": "mouse_brain_annotation.nii",
            "ontology": "mouse_brain_atlas.json",
            "history": "mouse_brain_history.json",
        },
    ),
    (
        "Human Brain",
        {
            "volume": "human_brain_reference.nii",
            "segmentation": "human_brain_annotation.nii",
            "ontology": "human_brain_atlas.json",
            "history": "human_brain_history.json",
        },
    ),
    (
        "Human Striatum",
        {
            "volume": "human_striatum_reference.nii",
            "segmentation": "human_striatum_annotation.nii",
            "ontology": "human_striatum_atlas.json",
            "history": "human_striatum_history.json",
        },
    ),
)


def _server_project_label(index, display_name):
    return "Server — Project %d — %s" % (index, display_name)


def simulation_file_path(filename):
    return os.path.join(SIMULATION_DATA_DIR, filename)


DEMO_SERVER_PROJECTS = {
    _server_project_label(index, display_name): dict(meta)
    for index, (display_name, meta) in enumerate(_SERVER_PROJECT_DEFS, start=1)
}

VERSION_BRANCH_COLORS = {
    "main": "#818cf8",
    "mid": "#5b9fd4",
    "limb": "#fbbf24",
    "cb": "#fb923c",
    "fore": "#6ee7b7",
}

VERSION_LANE_CENTERS = {
    "limb": 95,
    "fore": 265,
    "main": 435,
    "mid": 615,
    "cb": 795,
}

_EMPTY_HISTORY_BUNDLE: dict[str, Any] = {
    "head_version": None,
    "commit_history": [],
    "version_specs": [],
    "tags_by_id": {},
}


def _normalize_graph_node(raw_node: dict[str, Any]) -> dict[str, Any]:
    node = {
        "id": str(raw_node["id"]),
        "tag": str(raw_node.get("tag", raw_node["id"])),
        "label": str(raw_node.get("label", raw_node["id"])),
        "branch": str(raw_node.get("branch", "main")),
        "parent": raw_node.get("parent"),
    }
    if raw_node.get("merge"):
        node["merge"] = True
        node["merge_from"] = list(raw_node.get("merge_from") or [])
        merge_into = raw_node.get("merge_into") or node["parent"]
        if merge_into:
            node["merge_into"] = str(merge_into)
    if raw_node.get("head"):
        node["head"] = True
    return node


def _history_row_from_entry(entry: dict[str, Any]) -> tuple[str, str, str, str, str]:
    return (
        str(entry["id"]),
        str(entry.get("date", "")),
        str(entry.get("author", "")),
        str(entry.get("message", "")),
        str(entry.get("status", "")),
    )


def _parse_history_payload(payload: dict[str, Any]) -> dict[str, Any]:
    if payload.get("schema_version") != HISTORY_SCHEMA_VERSION:
        raise ValueError("Unsupported history schema_version: %s" % payload.get("schema_version"))

    graph_nodes = payload.get("graph", {}).get("nodes")
    if not isinstance(graph_nodes, list) or not graph_nodes:
        raise ValueError("History JSON must contain graph.nodes")

    version_specs = [_normalize_graph_node(node) for node in graph_nodes]
    tags_by_id = {spec["id"]: spec["tag"] for spec in version_specs if spec.get("tag")}

    history_entries = payload.get("history")
    if not isinstance(history_entries, list):
        raise ValueError("History JSON must contain a history array")

    commit_history = [_history_row_from_entry(entry) for entry in history_entries]
    head_version = payload.get("head_version")
    if not head_version and version_specs:
        head_nodes = [spec for spec in version_specs if spec.get("head")]
        if head_nodes:
            head_version = head_nodes[0]["id"]
        else:
            head_version = version_specs[-1]["id"]

    return {
        "head_version": str(head_version) if head_version else None,
        "commit_history": commit_history,
        "version_specs": version_specs,
        "tags_by_id": tags_by_id,
    }


def load_project_history_bundle(project_name: str) -> dict[str, Any]:
    """Load commit history + version graph for a server project from simulation/data/."""
    meta = DEMO_SERVER_PROJECTS.get(project_name)
    if not meta:
        return dict(_EMPTY_HISTORY_BUNDLE)

    history_file = meta.get("history")
    if not history_file:
        return dict(_EMPTY_HISTORY_BUNDLE)

    history_path = simulation_file_path(history_file)
    if not os.path.isfile(history_path):
        raise FileNotFoundError("Missing history file: %s" % history_path)

    with open(history_path, encoding="utf-8") as handle:
        payload = json.load(handle)

    if not isinstance(payload, dict):
        raise ValueError("History JSON root must be an object: %s" % history_path)

    return _parse_history_payload(payload)


def format_version_display_plain(version_id, tags_by_id=None) -> str:
    tag_map = tags_by_id or {}
    return str(tag_map.get(version_id, version_id))


def _project_node_names(meta):
    return {
        DataManager._basename_without_extension(simulation_file_path(meta["volume"])),
        DataManager._basename_without_extension(simulation_file_path(meta["segmentation"])),
    }


def apply_server_pull(widget, version_id=None) -> None:
    """Simulate Pull: load volume, segmentation and ontology from simulation/data/."""
    project_name = widget._currentProjectName()
    meta = DEMO_SERVER_PROJECTS.get(project_name)
    if not meta:
        return

    try:
        widget._project_history_bundle = load_project_history_bundle(project_name)
    except (OSError, ValueError) as error:
        widget._project_history_bundle = dict(_EMPTY_HISTORY_BUNDLE)
        widget._appendFeed("Pull: history load failed: %s" % error, error=True)

    head_version = widget._project_history_bundle.get("head_version")
    widget._currentVersionId = version_id or head_version or "main/1"
    widget._server_pulled = True
    widget._server_files_loaded = False

    widget._beginBatchUiUpdate()
    widget._clearProjectAssetFields()

    data_manager = DataManager()
    data_manager.remove_scene_nodes_by_names(_project_node_names(meta))
    errors = []

    widget._blockProjectAssetSignals(True)
    try:
        ontology_path = simulation_file_path(meta["ontology"])
        if not os.path.isfile(ontology_path):
            errors.append("Missing ontology file: %s" % ontology_path)
        else:
            try:
                document = load_ontology_file(ontology_path)
                document["source"] = "server:%s" % project_name
                document["source_path"] = ontology_path
                widget._applyOntologyDocument(document)
                widget._setOntologyComboLoadedFilename(filename=meta["ontology"])
            except (OSError, ValueError) as error:
                errors.append("Ontology load failed: %s" % error)

        volume_path = simulation_file_path(meta["volume"])
        if not os.path.isfile(volume_path):
            errors.append("Missing volume file: %s" % volume_path)
        else:
            try:
                volume_node = data_manager.load_volume(volume_path)
                widget.volumeSelector.setCurrentNode(volume_node)
            except (OSError, ValueError, RuntimeError) as error:
                errors.append("Volume load failed: %s" % error)

        segmentation_path = simulation_file_path(meta["segmentation"])
        if not os.path.isfile(segmentation_path):
            errors.append("Missing segmentation file: %s" % segmentation_path)
        else:
            try:
                segmentation_node = data_manager.load_segmentation(segmentation_path)
                widget.segmentationSelector.setCurrentNode(segmentation_node)
            except (OSError, ValueError, RuntimeError) as error:
                errors.append("Segmentation load failed: %s" % error)
    finally:
        widget._blockProjectAssetSignals(False)

    widget._server_files_loaded = widget._projectAssetsComplete()
    widget._setProjectAssetFieldsEnabled(widget._server_files_loaded)

    if errors:
        for message in errors:
            widget._appendFeed("Pull: %s" % message, error=True)
    if widget._server_files_loaded:
        widget._appendFeed(
            "Pull loaded simulation assets for « %s » (volume, segmentation, ontology)."
            % project_name.split(" — ")[-1]
        )
        widget._appendFeed(
            "Checked out %s."
            % widget._versionDisplayTag(widget._currentVersionId)
        )
    else:
        widget._appendFeed(
            "Pull incomplete — add the missing files under: %s" % SIMULATION_DATA_DIR,
            error=True,
        )

    widget._updateCommitHistoryPanel()
    widget._endBatchUiUpdate(refresh=True)
