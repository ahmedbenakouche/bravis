"""Chargement, validation et edition d'ontologies (graphe de dependances)."""

import json
import os
import uuid

import qt

# Ontology JSON — nested atlas tree format (see ontology_json_help_text).
ONTOLOGY_JSON_FILE_FILTER = "Ontology JSON (*.json)"
SCHEMA_VERSION = "1.0"
ATLAS_FORMAT = "atlas_tree"
DEFAULT_NODE_COLOR = "#0078d4"
# One distinct border color per depth level (blue → orange → green first, then 9 more hues).
# Allen Mouse has 11 levels (depth 0–10): no color repeats within that range.
_DEPTH_COLORS = (
    "#0078d4",  # 0 blue
    "#e67e22",  # 1 orange
    "#16a085",  # 2 green
    "#8e44ad",  # 3 purple
    "#c0392b",  # 4 red
    "#0891b2",  # 5 cyan
    "#ca8a04",  # 6 gold
    "#db2777",  # 7 pink
    "#4f46e5",  # 8 indigo
    "#0d9488",  # 9 teal
    "#9333ea",  # 10 violet
    "#b45309",  # 11 amber
)
ONTOLOGIES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ontologies")

PRESET_ONTOLOGIES = {
    "allen_mouse_brain_atlas": {
        "label": "Allen Mouse Brain Atlas",
        "filename": "Allen_Mouse_Brain_Atlas.json",
    },
    "allen_human_brain_atlas": {
        "label": "Allen Human Brain Atlas",
        "filename": "Allen_Human_Brain_Atlas.json",
    },
}


def ontology_json_help_text():
    return """Ontology JSON — atlas tree format

Root object:
  atlas_name  (string, required) — ontology title
  tree        (object, required)  — hierarchical root node

Each node in tree (recursive):
  id        (string, required) — unique structure id
  symbol    (string, required) — short code / abbreviation
  name      (string, required) — display name
  children  (array, required)  — child nodes ([] if leaf)

Example:
{
  "atlas_name": "My brain atlas",
  "tree": {
    "id": "997",
    "symbol": "root",
    "name": "root",
    "children": [
      {
        "id": "8",
        "symbol": "CTX",
        "name": "Cerebral cortex",
        "children": []
      }
    ]
  }
}

Load and Export in this module use this format.
Presets (Allen Mouse / Human) follow the same structure.
"""


def ontology_format_error_message():
    return (
        "Unsupported ontology JSON. Expected atlas_name + tree. "
        "Open Help in the Ontology panel for the specification."
    )


class OntologyJsonHelpDialog(qt.QDialog):
    """Quick reference for the ontology JSON atlas tree format."""

    def __init__(self, parent=None) -> None:
        qt.QDialog.__init__(self, parent)
        self.setWindowTitle("Ontology JSON — format reference")
        self.setMinimumSize(560, 480)
        layout = qt.QVBoxLayout(self)
        body = qt.QTextEdit()
        body.setReadOnly(True)
        body.setPlainText(ontology_json_help_text())
        body.setStyleSheet("font-family: Consolas, monospace; font-size: 11px;")
        layout.addWidget(body, 1)
        close_btn = qt.QPushButton("Close")
        close_btn.connect("clicked()", self.accept)
        row = qt.QHBoxLayout()
        row.addStretch(1)
        row.addWidget(close_btn)
        layout.addLayout(row)


def preset_choices():
    return [(key, meta["label"]) for key, meta in PRESET_ONTOLOGIES.items()]


def load_preset(preset_id):
    meta = PRESET_ONTOLOGIES.get(preset_id)
    if not meta:
        raise ValueError("Preset inconnu : %s" % preset_id)
    path = os.path.join(ONTOLOGIES_DIR, meta["filename"])
    document = load_ontology_file(path)
    document["source"] = "preset:%s" % preset_id
    document["source_path"] = path
    return document


def load_ontology_file(path):
    with open(path, encoding="utf-8") as handle:
        payload = json.load(handle)
    document = normalize_document(payload)
    document["source"] = "file"
    document["source_path"] = os.path.abspath(path)
    return document


def _is_atlas_payload(payload):
    return isinstance(payload, dict) and isinstance(payload.get("tree"), dict)


def _color_for_depth(depth):
    return _DEPTH_COLORS[depth % len(_DEPTH_COLORS)]


def _flatten_atlas_tree(tree_node, parent_id=None, depth=0, nodes=None):
    if nodes is None:
        nodes = []
    if not isinstance(tree_node, dict):
        raise ValueError("Invalid atlas node.")
    node_id = str(tree_node.get("id", "")).strip()
    if not node_id:
        raise ValueError("Atlas node missing 'id'.")
    name = str(tree_node.get("name", "")).strip()
    symbol = str(tree_node.get("symbol", "")).strip()
    label = name or symbol or node_id
    node = {
        "id": node_id,
        "label": label,
        "parent": parent_id,
        "color": _color_for_depth(depth),
    }
    if symbol:
        node["symbol"] = symbol
    nodes.append(node)
    children = tree_node.get("children")
    if children is None:
        children = []
    if not isinstance(children, list):
        raise ValueError("Field 'children' must be a list for node '%s'." % node_id)
    for child in children:
        _flatten_atlas_tree(child, node_id, depth + 1, nodes)
    return nodes


def normalize_atlas_document(payload):
    tree = payload.get("tree")
    if not isinstance(tree, dict):
        raise ValueError("Field 'tree' must be a root object.")

    nodes = _flatten_atlas_tree(tree)
    if not nodes:
        raise ValueError("Atlas ontology is empty.")

    seen_ids = set()
    for node in nodes:
        if node["id"] in seen_ids:
            raise ValueError("Duplicate id: %s" % node["id"])
        seen_ids.add(node["id"])

    for node in nodes:
        parent_id = node["parent"]
        if parent_id is not None and parent_id not in seen_ids:
            raise ValueError("Unknown parent '%s' for node '%s'." % (parent_id, node["id"]))

    atlas_name = str(payload.get("atlas_name", "")).strip()
    return {
        "schema_version": SCHEMA_VERSION,
        "format": ATLAS_FORMAT,
        "name": atlas_name or "Atlas ontology",
        "nodes": nodes,
    }


def normalize_document(payload):
    if not _is_atlas_payload(payload):
        raise ValueError(ontology_format_error_message())
    return normalize_atlas_document(payload)


def _assert_acyclic(nodes):
    children_map = {}
    for node in nodes:
        parent_id = node["parent"]
        if parent_id is not None:
            children_map.setdefault(parent_id, []).append(node["id"])

    visiting = set()
    visited = set()

    def visit(node_id):
        if node_id in visiting:
            raise ValueError("Cycle detected around node '%s'." % node_id)
        if node_id in visited:
            return
        visiting.add(node_id)
        for child_id in children_map.get(node_id, []):
            visit(child_id)
        visiting.remove(node_id)
        visited.add(node_id)

    for node in nodes:
        if node["parent"] is None:
            visit(node["id"])


def _validate_nodes_list(nodes):
    if not isinstance(nodes, list) or not nodes:
        raise ValueError("The ontology must contain at least one node.")

    normalized_nodes = []
    seen_ids = set()
    for index, raw_node in enumerate(nodes):
        if not isinstance(raw_node, dict):
            raise ValueError("Invalid node #%d." % index)
        node_id = str(raw_node.get("id", "")).strip()
        label = str(raw_node.get("label", raw_node.get("name", ""))).strip()
        if not node_id:
            raise ValueError("Node #%d: 'id' is required." % index)
        if not label:
            raise ValueError("Node '%s': 'label' or 'name' is required." % node_id)
        if node_id in seen_ids:
            raise ValueError("Duplicate id: %s" % node_id)
        seen_ids.add(node_id)

        parent = raw_node.get("parent")
        if parent is not None:
            parent = str(parent).strip() or None

        node = {
            "id": node_id,
            "label": label,
            "parent": parent,
            "color": str(raw_node.get("color", DEFAULT_NODE_COLOR)),
        }
        symbol = raw_node.get("symbol")
        if symbol:
            node["symbol"] = str(symbol).strip()
        xref = raw_node.get("xref")
        if isinstance(xref, dict) and xref:
            node["xref"] = {str(k): str(v) for k, v in xref.items()}
        normalized_nodes.append(node)

    for node in normalized_nodes:
        parent_id = node["parent"]
        if parent_id is not None and parent_id not in seen_ids:
            raise ValueError("Unknown parent '%s' for node '%s'." % (parent_id, node["id"]))
        if parent_id == node["id"]:
            raise ValueError("A node cannot be its own parent: %s" % node["id"])

    roots = [node for node in normalized_nodes if node["parent"] is None]
    if not roots:
        raise ValueError("At least one root node (parent null) is required.")

    _assert_acyclic(normalized_nodes)
    return normalized_nodes


def normalize_edited_document(name, nodes):
    return {
        "schema_version": SCHEMA_VERSION,
        "format": ATLAS_FORMAT,
        "name": str(name or "Ontology").strip() or "Ontology",
        "nodes": _validate_nodes_list(nodes),
    }


def _default_symbol(label, node_id):
    compact = "".join(ch for ch in label if ch.isalnum())
    if compact:
        return compact[:12]
    return str(node_id)


def _build_atlas_tree_node(node_id, nodes_by_id, nodes):
    node = nodes_by_id[node_id]
    label = node["label"]
    symbol = node.get("symbol") or _default_symbol(label, node_id)
    child_ids = [item["id"] for item in nodes if item["parent"] == node_id]
    return {
        "id": str(node_id),
        "symbol": symbol,
        "name": label,
        "children": [_build_atlas_tree_node(child_id, nodes_by_id, nodes) for child_id in child_ids],
    }


def document_to_atlas_payload(document):
    nodes = _validate_nodes_list(document["nodes"])
    nodes_by_id = {node["id"]: node for node in nodes}
    roots = [node for node in nodes if node["parent"] is None]
    if len(roots) == 1:
        tree = _build_atlas_tree_node(roots[0]["id"], nodes_by_id, nodes)
    else:
        tree = {
            "id": "root",
            "symbol": "root",
            "name": "root",
            "children": [_build_atlas_tree_node(root["id"], nodes_by_id, nodes) for root in roots],
        }
    return {
        "atlas_name": document.get("name", "Ontology"),
        "tree": tree,
    }


def document_to_graph_specs(document):
    """Build graph node specs with colors recomputed from tree depth."""
    nodes = document["nodes"]
    _level_count, _max_depth, depths_by_id, _node_count = compute_hierarchy_stats(nodes)
    specs = []
    for node in nodes:
        spec = dict(node)
        depth = depths_by_id.get(node["id"], 0)
        spec["color"] = _color_for_depth(depth)
        specs.append(spec)
    return specs


def document_to_json(document, indent=2):
    payload = document_to_atlas_payload(document)
    return json.dumps(payload, indent=indent, ensure_ascii=False)


def save_ontology_file(document, path):
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(document_to_json(document))
    document["source"] = "file"
    document["source_path"] = os.path.abspath(path)


def compute_hierarchy_stats(nodes):
    """Return (level_count, max_depth, depths_by_id, node_count) for a flat node list."""
    if not nodes:
        return 0, 0, {}, 0

    nodes_by_id = {node["id"]: node for node in nodes}
    depths = {}

    def depth_of(node_id, visiting=None):
        if node_id in depths:
            return depths[node_id]
        node = nodes_by_id.get(node_id)
        if node is None:
            return 0
        parent_id = node.get("parent")
        if parent_id is None:
            depths[node_id] = 0
            return 0
        if visiting is None:
            visiting = set()
        if node_id in visiting:
            return 0
        visiting.add(node_id)
        value = depth_of(parent_id, visiting) + 1
        depths[node_id] = value
        return value

    for node in nodes:
        depth_of(node["id"])

    max_depth = max(depths.values()) if depths else 0
    return max_depth + 1, max_depth, depths, len(nodes)


def _slug_id(label):
    base = "".join(ch.lower() if ch.isalnum() else "_" for ch in label).strip("_")
    return base or ("node_%s" % uuid.uuid4().hex[:6])


def _qt_spin_value(spin):
    """Read QSpinBox value (PythonQt exposes `value` as a property, not value())."""
    value = spin.value if hasattr(spin, "value") and not callable(spin.value) else spin.value()
    if callable(value):
        value = value()
    return int(value)


def _qt_line_edit_text(edit):
    text = edit.text if hasattr(edit, "text") and not callable(edit.text) else edit.text()
    if callable(text):
        text = text()
    return str(text).strip()


def _qt_tree_current_item(tree):
    item = tree.currentItem if hasattr(tree, "currentItem") and not callable(tree.currentItem) else tree.currentItem()
    if callable(item):
        item = item()
    return item


def _qt_input_text(parent, title, label, default=""):
    """Prompt for a string; returns (text, accepted) using PythonQt.BoolResult."""
    import PythonQt

    ok = PythonQt.BoolResult()
    text = qt.QInputDialog.getText(
        parent,
        title,
        label,
        qt.QLineEdit.Normal,
        default,
        ok,
    )
    if not ok:
        return "", False
    return str(text).strip(), True


def _tree_item_text(item, column):
    text = item.text(column) if callable(getattr(item, "text", None)) else item.text
    if callable(text):
        text = text(column)
    return str(text)


def _tree_item_node_id(item):
    node_id = item.data(0, qt.Qt.UserRole)
    if node_id is not None and str(node_id).strip():
        return str(node_id)
    fallback = _tree_item_text(item, 1).strip()
    return fallback or None


class _OntologyNodeEditDialog(qt.QDialog):
    """Edit a structure name and id."""

    def __init__(self, parent, title, label, node_id):
        qt.QDialog.__init__(self, parent)
        self.setWindowTitle(title)
        self.setMinimumWidth(360)
        layout = qt.QVBoxLayout(self)

        form = qt.QFormLayout()
        self.nameEdit = qt.QLineEdit(label)
        self.idEdit = qt.QLineEdit(node_id)
        form.addRow("Name:", self.nameEdit)
        form.addRow("Id:", self.idEdit)
        layout.addLayout(form)

        footer = qt.QHBoxLayout()
        footer.addStretch(1)
        btnCancel = qt.QPushButton("Cancel")
        btnOk = qt.QPushButton("OK")
        footer.addWidget(btnCancel)
        footer.addWidget(btnOk)
        layout.addLayout(footer)

        btnCancel.connect("clicked()", self.reject)
        btnOk.connect("clicked()", self._on_ok)

    def _on_ok(self):
        if not _qt_line_edit_text(self.nameEdit):
            qt.QMessageBox.warning(self, "Rename", "Name is required.")
            return
        if not _qt_line_edit_text(self.idEdit):
            qt.QMessageBox.warning(self, "Rename", "Id is required.")
            return
        self.accept()

    def values(self):
        return _qt_line_edit_text(self.nameEdit), _qt_line_edit_text(self.idEdit)


class OntologyEditorDialog(qt.QDialog):
    """Editeur arbre simple — modifie le document JSON en memoire."""

    def __init__(self, document, parent=None):
        qt.QDialog.__init__(self, parent)
        self.setWindowTitle("Ontology editor")
        self.resize(560, 560)
        self._document = {
            "schema_version": document.get("schema_version", SCHEMA_VERSION),
            "format": document.get("format", ATLAS_FORMAT),
            "name": document.get("name", "Ontology"),
            "nodes": [dict(node) for node in document["nodes"]],
            "source": document.get("source"),
            "source_path": document.get("source_path"),
        }
        self._depths_by_id = {}
        self._level_count = 1

        layout = qt.QVBoxLayout(self)

        form = qt.QFormLayout()
        self.nameEdit = qt.QLineEdit(self._document["name"])
        form.addRow("Atlas name:", self.nameEdit)
        layout.addLayout(form)

        self.hierarchyInfoLabel = qt.QLabel("")
        from CollaborativeVersioningLib.UiStyles import TEXT_MUTED

        self.hierarchyInfoLabel.setStyleSheet("color: %s; font-size: 10px;" % TEXT_MUTED)
        layout.addWidget(self.hierarchyInfoLabel)

        depthRow = qt.QHBoxLayout()
        depthRow.addWidget(qt.QLabel("Levels shown:"))
        self.levelsShownSpin = qt.QSpinBox()
        self.levelsShownSpin.setMinimum(1)
        self.levelsShownSpin.setToolTip(
            "Limit how many hierarchy levels are displayed in the tree (1 = root only)."
        )
        depthRow.addWidget(self.levelsShownSpin)
        depthRow.addStretch(1)
        layout.addLayout(depthRow)

        self.tree = qt.QTreeWidget()
        self.tree.setHeaderLabels(["Structure", "Id"])
        self.tree.setColumnWidth(0, 280)
        layout.addWidget(self.tree, 1)

        buttons = qt.QHBoxLayout()
        self.btnAddRoot = qt.QPushButton("Add root")
        self.btnAddChild = qt.QPushButton("Add child")
        self.btnRename = qt.QPushButton("Rename")
        self.btnRemove = qt.QPushButton("Remove")
        for btn in (self.btnAddRoot, self.btnAddChild, self.btnRename, self.btnRemove):
            buttons.addWidget(btn)
        layout.addLayout(buttons)

        footer = qt.QHBoxLayout()
        footer.addStretch(1)
        self.btnCancel = qt.QPushButton("Cancel")
        self.btnApply = qt.QPushButton("Apply")
        footer.addWidget(self.btnCancel)
        footer.addWidget(self.btnApply)
        layout.addLayout(footer)

        self.btnAddRoot.connect("clicked()", self._on_add_root)
        self.btnAddChild.connect("clicked()", self._on_add_child)
        self.btnRename.connect("clicked()", self._on_rename)
        self.btnRemove.connect("clicked()", self._on_remove)
        self.btnCancel.connect("clicked()", self.reject)
        self.btnApply.connect("clicked()", self._on_apply)
        self.levelsShownSpin.connect("valueChanged(int)", self._on_levels_shown_changed)

        self._refresh_hierarchy_info(initial=True)
        self._populate_tree()

    def result_document(self):
        return self._document

    def _default_levels_shown(self, level_count, node_count):
        if level_count <= 4:
            return level_count
        if node_count > 200:
            return 3
        return min(4, level_count)

    def _refresh_hierarchy_info(self, initial=False):
        level_count, _max_depth, self._depths_by_id, node_count = compute_hierarchy_stats(
            self._document["nodes"]
        )
        self._level_count = max(1, level_count)
        self.hierarchyInfoLabel.setText(
            "Hierarchy: %d level(s) · %d structure(s)" % (self._level_count, node_count)
        )
        previous = _qt_spin_value(self.levelsShownSpin) if not initial else 0
        self.levelsShownSpin.blockSignals(True)
        self.levelsShownSpin.setMaximum(self._level_count)
        self.levelsShownSpin.setMinimum(1)
        if initial:
            self.levelsShownSpin.setValue(self._default_levels_shown(self._level_count, node_count))
        elif previous > self._level_count:
            self.levelsShownSpin.setValue(self._level_count)
        elif previous >= 1:
            self.levelsShownSpin.setValue(previous)
        self.levelsShownSpin.blockSignals(False)

    def _on_levels_shown_changed(self, _value):
        self._populate_tree()

    def _max_depth_shown(self):
        return _qt_spin_value(self.levelsShownSpin) - 1

    def _populate_tree(self):
        self.tree.clear()
        nodes_by_id = {node["id"]: node for node in self._document["nodes"]}
        children_map = {}
        for node in self._document["nodes"]:
            parent_id = node["parent"]
            if parent_id is not None:
                children_map.setdefault(parent_id, []).append(node["id"])
        max_depth = self._max_depth_shown()

        def add_node(node_id, parent_item=None):
            depth = self._depths_by_id.get(node_id, 0)
            if depth > max_depth:
                return
            node = nodes_by_id[node_id]
            item = qt.QTreeWidgetItem([node["label"], node["id"]])
            item.setData(0, qt.Qt.UserRole, node["id"])
            if parent_item is None:
                self.tree.addTopLevelItem(item)
            else:
                parent_item.addChild(item)
            if depth >= max_depth:
                return
            for child_id in children_map.get(node_id, []):
                add_node(child_id, item)

        for node in self._document["nodes"]:
            if node["parent"] is None:
                add_node(node["id"])
        self.tree.expandAll()

    def _selected_node_id(self):
        item = _qt_tree_current_item(self.tree)
        return _tree_item_node_id(item) if item else None

    def _on_add_root(self):
        label, ok = _qt_input_text(self, "New root", "Structure name:")
        if not ok or not label:
            return
        node_id = self._unique_id(_slug_id(label))
        self._document["nodes"].append({
            "id": node_id,
            "label": label,
            "parent": None,
            "color": DEFAULT_NODE_COLOR,
        })
        self._refresh_hierarchy_info()
        self._populate_tree()

    def _on_add_child(self):
        parent_id = self._selected_node_id()
        if not parent_id:
            qt.QMessageBox.information(self, "Ontology", "Select a parent node first.")
            return
        label, ok = _qt_input_text(self, "New child", "Structure name:")
        if not ok or not label:
            return
        node_id = self._unique_id(_slug_id(label))
        self._document["nodes"].append({
            "id": node_id,
            "label": label,
            "parent": parent_id,
            "color": DEFAULT_NODE_COLOR,
        })
        self._refresh_hierarchy_info()
        self._populate_tree()

    def _on_rename(self):
        node_id = self._selected_node_id()
        if not node_id:
            return
        node = next(node for node in self._document["nodes"] if node["id"] == node_id)
        dialog = _OntologyNodeEditDialog(self, "Rename structure", node["label"], node["id"])
        if dialog.exec_() != qt.QDialog.Accepted:
            return
        label, new_id = dialog.values()
        if new_id != node_id:
            existing = {item["id"] for item in self._document["nodes"]}
            if new_id in existing:
                qt.QMessageBox.warning(self, "Rename", "Id already used: %s" % new_id)
                return
            for item in self._document["nodes"]:
                if item["parent"] == node_id:
                    item["parent"] = new_id
            node["id"] = new_id
        node["label"] = label
        self._refresh_hierarchy_info()
        self._populate_tree()

    def _on_remove(self):
        node_id = self._selected_node_id()
        if not node_id:
            return
        to_remove = {node_id}
        changed = True
        while changed:
            changed = False
            for node in self._document["nodes"]:
                if node["parent"] in to_remove and node["id"] not in to_remove:
                    to_remove.add(node["id"])
                    changed = True
        self._document["nodes"] = [node for node in self._document["nodes"] if node["id"] not in to_remove]
        if not self._document["nodes"]:
            self._document["nodes"].append({
                "id": "root",
                "label": "Root",
                "parent": None,
                "color": DEFAULT_NODE_COLOR,
            })
        self._refresh_hierarchy_info()
        self._populate_tree()

    def _unique_id(self, base):
        existing = {node["id"] for node in self._document["nodes"]}
        if base not in existing:
            return base
        index = 2
        while "%s_%d" % (base, index) in existing:
            index += 1
        return "%s_%d" % (base, index)

    def _on_apply(self):
        try:
            self._document = normalize_edited_document(
                _qt_line_edit_text(self.nameEdit),
                self._document["nodes"],
            )
            self._document["source"] = "edited"
            self._document["source_path"] = None
        except ValueError as error:
            qt.QMessageBox.warning(self, "Invalid ontology", str(error))
            return
        self.accept()
