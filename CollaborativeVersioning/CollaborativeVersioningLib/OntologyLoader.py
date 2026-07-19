"""Chargement, validation et edition d'ontologies (graphe de dependances) au format JSON."""

import json
import os
import uuid

import qt

SCHEMA_VERSION = "1.0"
DEFAULT_NODE_COLOR = "#0078d4"
ONTOLOGIES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ontologies")

PRESET_ONTOLOGIES = {
    "allen_mouse_brain_ccf_v3": {
        "label": "Allen CCF v3 — Mouse brain (default)",
        "filename": "allen_mouse_brain_ccf_v3.json",
    },
    "minimal_brain_regions": {
        "label": "Minimal example — 6 regions",
        "filename": "minimal_brain_regions.json",
    },
}


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


def normalize_document(payload):
    if not isinstance(payload, dict):
        raise ValueError("Le JSON doit etre un objet racine.")

    nodes = payload.get("nodes")
    if not isinstance(nodes, list) or not nodes:
        raise ValueError("Le champ 'nodes' doit etre une liste non vide.")

    normalized_nodes = []
    seen_ids = set()
    for index, raw_node in enumerate(nodes):
        if not isinstance(raw_node, dict):
            raise ValueError("Noeud #%d invalide." % index)
        node_id = str(raw_node.get("id", "")).strip()
        label = str(raw_node.get("label", "")).strip()
        if not node_id:
            raise ValueError("Noeud #%d : 'id' obligatoire." % index)
        if not label:
            raise ValueError("Noeud '%s' : 'label' obligatoire." % node_id)
        if node_id in seen_ids:
            raise ValueError("Id duplique : %s" % node_id)
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
        xref = raw_node.get("xref")
        if isinstance(xref, dict) and xref:
            node["xref"] = {str(k): str(v) for k, v in xref.items()}
        normalized_nodes.append(node)

    for node in normalized_nodes:
        parent_id = node["parent"]
        if parent_id is not None and parent_id not in seen_ids:
            raise ValueError("Parent inconnu '%s' pour le noeud '%s'." % (parent_id, node["id"]))
        if parent_id == node["id"]:
            raise ValueError("Un noeud ne peut pas etre son propre parent : %s" % node["id"])

    roots = [node for node in normalized_nodes if node["parent"] is None]
    if not roots:
        raise ValueError("Au moins un noeud racine (parent null) est requis.")

    _assert_acyclic(normalized_nodes)

    return {
        "schema_version": str(payload.get("schema_version", SCHEMA_VERSION)),
        "name": str(payload.get("name", "Ontologie sans titre")).strip() or "Ontologie sans titre",
        "description": str(payload.get("description", "")).strip(),
        "nodes": normalized_nodes,
    }


def _assert_acyclic(nodes):
    children_map = {}
    for node in nodes:
        parent_id = node["parent"]
        if parent_id is not None:
            children_map.setdefault(parent_id, []).append(node["id"])

    visiting = set()
    visited = set()
    nodes_by_id = {node["id"]: node for node in nodes}

    def visit(node_id):
        if node_id in visiting:
            raise ValueError("Cycle detecte autour du noeud '%s'." % node_id)
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


def document_to_graph_specs(document):
    return [dict(node) for node in document["nodes"]]


def document_to_json(document, indent=2):
    payload = {
        "schema_version": document.get("schema_version", SCHEMA_VERSION),
        "name": document.get("name", "Ontologie"),
        "description": document.get("description", ""),
        "nodes": [
            {
                "id": node["id"],
                "label": node["label"],
                "parent": node["parent"],
                "color": node.get("color", DEFAULT_NODE_COLOR),
                **({"xref": node["xref"]} if node.get("xref") else {}),
            }
            for node in document["nodes"]
        ],
    }
    return json.dumps(payload, indent=indent, ensure_ascii=False)


def save_ontology_file(document, path):
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(document_to_json(document))
    document["source"] = "file"
    document["source_path"] = os.path.abspath(path)


def default_document():
    return load_preset("allen_mouse_brain_ccf_v3")


def _slug_id(label):
    base = "".join(ch.lower() if ch.isalnum() else "_" for ch in label).strip("_")
    return base or ("node_%s" % uuid.uuid4().hex[:6])


class OntologyEditorDialog(qt.QDialog):
    """Editeur arbre simple — modifie le document JSON en memoire."""

    def __init__(self, document, parent=None):
        qt.QDialog.__init__(self, parent)
        self.setWindowTitle("Ontology editor (JSON)")
        self.resize(520, 520)
        self._document = {
            "schema_version": document.get("schema_version", SCHEMA_VERSION),
            "name": document.get("name", "Ontologie"),
            "description": document.get("description", ""),
            "nodes": [dict(node) for node in document["nodes"]],
            "source": document.get("source"),
            "source_path": document.get("source_path"),
        }

        layout = qt.QVBoxLayout(self)

        form = qt.QFormLayout()
        self.nameEdit = qt.QLineEdit(self._document["name"])
        self.descriptionEdit = qt.QLineEdit(self._document["description"])
        form.addRow("Name:", self.nameEdit)
        form.addRow("Description:", self.descriptionEdit)
        layout.addLayout(form)

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

        self._populate_tree()

    def result_document(self):
        return self._document

    def _populate_tree(self):
        self.tree.clear()
        nodes_by_id = {node["id"]: node for node in self._document["nodes"]}
        item_by_id = {}

        def add_node(node_id, parent_item=None):
            node = nodes_by_id[node_id]
            item = qt.QTreeWidgetItem([node["label"], node["id"]])
            if parent_item is None:
                self.tree.addTopLevelItem(item)
            else:
                parent_item.addChild(item)
            item_by_id[node_id] = item
            for child in self._document["nodes"]:
                if child["parent"] == node_id:
                    add_node(child["id"], item)

        for node in self._document["nodes"]:
            if node["parent"] is None:
                add_node(node["id"])
        self.tree.expandAll()

    def _selected_node_id(self):
        item = self.tree.currentItem()
        return item.text(1) if item else None

    def _on_add_root(self):
        label, ok = qt.QInputDialog.getText(self, "New root", "Structure name:")
        if not ok or not label.strip():
            return
        label = label.strip()
        node_id = self._unique_id(_slug_id(label))
        self._document["nodes"].append({
            "id": node_id,
            "label": label,
            "parent": None,
            "color": DEFAULT_NODE_COLOR,
        })
        self._populate_tree()

    def _on_add_child(self):
        parent_id = self._selected_node_id()
        if not parent_id:
            qt.QMessageBox.information(self, "Ontology", "Select a parent node first.")
            return
        label, ok = qt.QInputDialog.getText(self, "New child", "Structure name:")
        if not ok or not label.strip():
            return
        label = label.strip()
        node_id = self._unique_id(_slug_id(label))
        self._document["nodes"].append({
            "id": node_id,
            "label": label,
            "parent": parent_id,
            "color": DEFAULT_NODE_COLOR,
        })
        self._populate_tree()

    def _on_rename(self):
        node_id = self._selected_node_id()
        if not node_id:
            return
        node = next(node for node in self._document["nodes"] if node["id"] == node_id)
        label, ok = qt.QInputDialog.getText(self, "Rename", "New name:", text=node["label"])
        if ok and label.strip():
            node["label"] = label.strip()
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
        self._document["name"] = self.nameEdit.text.strip() or "Ontologie"
        self._document["description"] = self.descriptionEdit.text.strip()
        try:
            self._document = normalize_document(self._document)
            self._document["source"] = "edited"
            self._document["source_path"] = None
        except ValueError as error:
            qt.QMessageBox.warning(self, "Invalid ontology", str(error))
            return
        self.accept()
