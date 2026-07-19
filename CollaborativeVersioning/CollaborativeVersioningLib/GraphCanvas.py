"""Canvas 2D pour graphes de dépendances et d'historique de versions."""

import qt
from collections import defaultdict

GRAPH_BUILD_TAG = "2026-07-17-ice-clinic-v18"

MAIN_COLOR = "#818cf8"
VERSION_BRANCH_COLORS = {
    "main": MAIN_COLOR,
    "feature/mesencephale": "#5b9fd4",
    "feature/striatum": "#fbbf24",
    "feature/cervelet": "#fb923c",
    "feature/forebrain": "#6ee7b7",
}
HEAD_COLOR = "#6ee7b7"
GRAPH_BG = "#161920"
VERSION_LANE_CENTERS = {
    "feature/striatum": 95,
    "feature/forebrain": 265,
    "main": 435,
    "feature/mesencephale": 615,
    "feature/cervelet": 795,
}
VERSION_NODE_W = 155
VERSION_ROW_H = 82
VERSION_Y0 = 52
VERSION_ROW_GAP = 14

VERSION_SPECS = [
    {"id": "v1", "label": "v1.0 Import IRM Allen", "parent": None, "branch": "main"},
    {"id": "v2", "label": "v1.1 Masque cerebral", "parent": "v1", "branch": "main"},
    {"id": "v3", "label": "v1.2 Tronc cerebral", "parent": "v2", "branch": "main"},
    {"id": "v4", "label": "v1.2.1 Noyau rouge", "parent": "v3", "branch": "main"},
    {"id": "v5", "label": "v1.2.2 Substance noire", "parent": "v4", "branch": "main"},
    {"id": "v6", "label": "v1.2.f1 Colliculus sup.", "parent": "v3", "branch": "feature/mesencephale"},
    {"id": "v7", "label": "v1.2.f2 Colliculus inf.", "parent": "v6", "branch": "feature/mesencephale"},
    {"id": "v8", "label": "v2.0 Merge mesencephale", "parent": "v5", "branch": "main", "merge": True, "merge_from": ["v7"]},
    {"id": "v9", "label": "v1.3.f1 Striatum", "parent": "v2", "branch": "feature/striatum"},
    {"id": "v10", "label": "v1.3.f2 Affinage striatum", "parent": "v9", "branch": "feature/striatum"},
    {"id": "v11", "label": "v1.4.f1 Cervelet vermis", "parent": "v2", "branch": "feature/cervelet"},
    {"id": "v12", "label": "v1.4.f2 Hemispheres CB", "parent": "v11", "branch": "feature/cervelet"},
    {"id": "v13", "label": "v2.5.f1 Hippocampe CA1", "parent": "v2", "branch": "feature/forebrain"},
    {"id": "v14", "label": "v3.0 Merge global", "parent": "v8", "branch": "main", "merge": True, "merge_from": ["v10", "v12"]},
    {"id": "v15", "label": "v3.1 Review expert", "parent": "v14", "branch": "main"},
    {"id": "v16", "label": "v4.0 HEAD Release", "parent": "v15", "branch": "main", "head": True},
]


def version_specs_from_records(versions):
    """Construit le graphe a partir des versions reelles (depot / serveur)."""
    if not versions:
        return []

    sorted_versions = sorted(versions, key=lambda item: item.created_at)
    known_ids = {version.version_id for version in sorted_versions}
    branch_names = [
        "main",
        "feature/mesencephale",
        "feature/striatum",
        "feature/cervelet",
        "feature/forebrain",
    ]
    children_map = defaultdict(list)

    for version in sorted_versions:
        parent_id = version.parent_id if version.parent_id in known_ids else None
        if parent_id:
            children_map[parent_id].append(version.version_id)

    node_branch = {}
    for version in sorted_versions:
        if not version.parent_id or version.parent_id not in known_ids:
            node_branch.setdefault(version.version_id, "main")

    for parent_id, child_ids in children_map.items():
        for index, child_id in enumerate(child_ids):
            node_branch[child_id] = branch_names[min(index, len(branch_names) - 1)]

    newest_id = max(sorted_versions, key=lambda item: item.created_at).version_id
    specs = []
    previous_id = None

    for version in sorted_versions:
        parent_id = version.parent_id if version.parent_id in known_ids else previous_id
        message = (version.message or "sans message").strip()
        if len(message) > 18:
            message = message[:15] + "..."
        specs.append({
            "id": version.version_id,
            "label": "%s %s" % (version.version_id[:8], message),
            "parent": parent_id,
            "branch": node_branch.get(version.version_id, "main"),
            "head": version.version_id == newest_id,
        })
        previous_id = version.version_id

    if specs:
        specs[0]["parent"] = None

    return specs


H_GAP = 18
V_GAP = 52
MARGIN = 24

# Atlas Allen CCF v3 — hiérarchie d'annotation cerveau souris C57BL/6
MOUSE_BRAIN_SPECS = [
    {"id": "vol", "label": "Volume IRM Allen CCF v3", "parent": None, "color": "#0078d4"},
    {"id": "mask", "label": "Masque cerebral global", "parent": "vol", "color": "#1a8cff"},
    {"id": "brainstem", "label": "Tronc cerebral", "parent": "mask", "color": "#6f42c1"},
    {"id": "cerebellum", "label": "Cervelet", "parent": "mask", "color": "#e67e22"},
    {"id": "dienceph", "label": "Diencephale", "parent": "mask", "color": "#9b59b6"},
    {"id": "telenceph", "label": "Telencephale", "parent": "mask", "color": "#16a085"},
    {"id": "mesen", "label": "Mesencephale", "parent": "brainstem", "color": "#8e44ad"},
    {"id": "myel", "label": "Myelencephale", "parent": "brainstem", "color": "#7d3c98"},
    {"id": "col_sup", "label": "Colliculus superieur", "parent": "mesen", "color": "#00ff88"},
    {"id": "col_inf", "label": "Colliculus inferieur", "parent": "mesen", "color": "#00cc6a"},
    {"id": "sn", "label": "Substance noire (SNc)", "parent": "mesen", "color": "#ffcd38"},
    {"id": "rn", "label": "Noyau rouge", "parent": "mesen", "color": "#ff6b6b"},
    {"id": "rf", "label": "Formation reticulee", "parent": "myel", "color": "#c0392b"},
    {"id": "nv", "label": "Noyau n. vague", "parent": "myel", "color": "#e74c3c"},
    {"id": "vermis", "label": "Vermis cerebelleux", "parent": "cerebellum", "color": "#d35400"},
    {"id": "hemi", "label": "Hemispheres cerebelleux", "parent": "cerebellum", "color": "#f39c12"},
    {"id": "thal", "label": "Thalamus", "parent": "dienceph", "color": "#bb8fce"},
    {"id": "hypo", "label": "Hypothalamus", "parent": "dienceph", "color": "#a569bd"},
    {"id": "cortex_m1", "label": "Cortex moteur (M1)", "parent": "telenceph", "color": "#1abc9c"},
    {"id": "hippo", "label": "Hippocampe CA1", "parent": "telenceph", "color": "#48c9b0"},
    {"id": "striatum", "label": "Striatum", "parent": "telenceph", "color": "#76d7c4"},
]

NODE_H = 34


def _estimate_node_width(label):
    return max(108, min(155, len(label) * 6 + 24))


def _layout_hierarchy(specs):
    """Calcule les positions x/y d'un arbre hierarchique."""
    specs_by_id = {spec["id"]: dict(spec) for spec in specs}
    children_map = defaultdict(list)
    roots = []
    for spec in specs:
        parent = spec.get("parent")
        if parent is None:
            roots.append(spec["id"])
        else:
            children_map[parent].append(spec["id"])

    def subtree_width(node_id):
        children = children_map.get(node_id, [])
        if not children:
            return _estimate_node_width(specs_by_id[node_id]["label"]) + H_GAP
        return sum(subtree_width(child_id) for child_id in children)

    positions = {}

    def assign(node_id, x_left, depth):
        spec = specs_by_id[node_id]
        label = spec["label"]
        width = _estimate_node_width(label)
        height = NODE_H
        children = children_map.get(node_id, [])

        if not children:
            x = x_left + (subtree_width(node_id) - width) / 2.0
        else:
            child_x = x_left
            child_centers = []
            for child_id in children:
                child_width = subtree_width(child_id)
                assign(child_id, child_x, depth + 1)
                child_centers.append(positions[child_id]["x"] + positions[child_id]["w"] / 2.0)
                child_x += child_width
            x = (min(child_centers) + max(child_centers)) / 2.0 - width / 2.0

        positions[node_id] = {
            "id": node_id,
            "label": label,
            "color": spec["color"],
            "x": x,
            "y": MARGIN + depth * (NODE_H + V_GAP),
            "w": width,
            "h": height,
        }

    x_cursor = MARGIN
    for root_id in roots:
        assign(root_id, x_cursor, 0)
        x_cursor += subtree_width(root_id)

    edges = []
    for spec in specs:
        parent = spec.get("parent")
        if parent is not None:
            edges.append((parent, spec["id"]))

    return positions, edges


def _node_center(node):
    return node["x"] + node["w"] / 2.0, node["y"] + node["h"] / 2.0


def _draw_box_node(scene, node, font_size=7):
    x, y, w, h = node["x"], node["y"], node["w"], node["h"]
    color = node["color"]
    scene.addRect(
        x, y, w, h,
        qt.QPen(qt.QColor(color), 2),
        qt.QBrush(qt.QColor("#252525")),
    )
    label = scene.addText(node["label"])
    label.setFont(qt.QFont("Arial", font_size, qt.QFont.Bold))
    label.setDefaultTextColor(qt.QColor("#eeeeee"))
    bounds = label.boundingRect()
    label.setPos(x + (w - bounds.width()) / 2.0, y + (h - bounds.height()) / 2.0)


def _draw_tree_edge(scene, parent, child, color="#555555", width=2):
    px, _ = _node_center(parent)
    cx, _ = _node_center(child)
    mid_y = parent["y"] + parent["h"] + (child["y"] - parent["y"] - parent["h"]) / 2.0
    pen = qt.QPen(qt.QColor(color), width)
    scene.addLine(px, parent["y"] + parent["h"], px, mid_y, pen)
    scene.addLine(px, mid_y, cx, mid_y, pen)
    scene.addLine(cx, mid_y, cx, child["y"], pen)


def _version_lane_x(branch):
    center = VERSION_LANE_CENTERS.get(branch, VERSION_LANE_CENTERS["main"])
    return center - VERSION_NODE_W / 2.0


def _compute_version_rows(specs):
    specs_by_id = {spec["id"]: spec for spec in specs}
    rows = {}

    def row_for(node_id):
        if node_id in rows:
            return rows[node_id]
        spec = specs_by_id[node_id]
        predecessors = []
        if spec.get("parent"):
            predecessors.append(spec["parent"])
        predecessors.extend(spec.get("merge_from", []))
        if not predecessors:
            rows[node_id] = 0
        else:
            rows[node_id] = max(row_for(predecessor_id) for predecessor_id in predecessors) + 1
        return rows[node_id]

    for node_id in specs_by_id:
        row_for(node_id)
    return rows


def _rects_overlap(first, second, padding=10):
    return not (
        first["x"] + first["w"] + padding <= second["x"]
        or second["x"] + second["w"] + padding <= first["x"]
        or first["y"] + first["h"] + padding <= second["y"]
        or second["y"] + second["h"] + padding <= first["y"]
    )


def _resolve_vertical_overlaps(positions):
    nodes = list(positions.values())
    changed = True
    while changed:
        changed = False
        nodes.sort(key=lambda node: (node["y"], node["x"]))
        for index in range(len(nodes)):
            for other_index in range(index + 1, len(nodes)):
                upper = nodes[index]
                lower = nodes[other_index]
                if _rects_overlap(upper, lower):
                    lower["y"] = upper["y"] + upper["h"] + VERSION_ROW_GAP
                    changed = True
    return positions


def _layout_version_graph(specs):
    """Layout : colonnes fixes par branche, lignes sans chevauchement."""
    specs_by_id = {spec["id"]: dict(spec) for spec in specs}
    rows = _compute_version_rows(specs)

    positions = {}
    for node_id, spec in specs_by_id.items():
        branch = spec.get("branch", "main")
        label = spec["label"]
        y = VERSION_Y0 + rows[node_id] * VERSION_ROW_H
        x = _version_lane_x(branch)
        color = VERSION_BRANCH_COLORS.get(branch, MAIN_COLOR)

        positions[node_id] = {
            "id": node_id,
            "label": label,
            "x": x,
            "y": y,
            "w": VERSION_NODE_W,
            "h": NODE_H,
            "color": color,
            "branch": branch,
            "merge": spec.get("merge", False),
            "head": spec.get("head", False),
        }

    _resolve_vertical_overlaps(positions)

    edges = []
    for spec in specs:
        node_id = spec["id"]
        if spec.get("parent"):
            edges.append((spec["parent"], node_id, spec.get("branch", "main")))
        for merge_id in spec.get("merge_from", []):
            edges.append((merge_id, node_id, specs_by_id[merge_id].get("branch", "main")))

    return positions, edges


def _main_trunk_order(specs):
    if not specs:
        return []
    specs_by_id = {spec["id"]: spec for spec in specs}
    roots = [
        spec["id"] for spec in specs
        if spec.get("parent") is None and spec.get("branch", "main") == "main"
    ]
    if not roots:
        roots = [spec["id"] for spec in specs if spec.get("parent") is None]
    if not roots:
        return [specs[0]["id"]]

    order = []
    current = roots[0]
    visited = set()
    while current and current not in visited:
        visited.add(current)
        order.append(current)
        next_main = None
        for node_id, spec in specs_by_id.items():
            if spec.get("parent") == current and spec.get("branch", "main") == "main":
                next_main = node_id
                break
        current = next_main
    return order


def _draw_main_trunk(scene, positions, trunk_order):
    pen = qt.QPen(qt.QColor(MAIN_COLOR), 4)
    for index in range(len(trunk_order) - 1):
        upper = positions[trunk_order[index + 1]]
        lower = positions[trunk_order[index]]
        ux, uy = _node_center(upper)
        lx, ly = _node_center(lower)
        scene.addLine(lx, ly + lower["h"] / 2.0, ux, uy - upper["h"] / 2.0, pen)


def _draw_version_box_node(scene, node, font_size=7):
    x, y, w, h = node["x"], node["y"], node["w"], node["h"]
    if node.get("head"):
        color = HEAD_COLOR
        border = 3
    else:
        color = node["color"]
        border = 3 if node.get("merge") else 2
    scene.addRect(
        x, y, w, h,
        qt.QPen(qt.QColor(color), border),
        qt.QBrush(qt.QColor("#252525")),
    )
    text = node["label"]
    if len(text) > 22:
        text = text[:19] + "..."
    label = scene.addText(text)
    label.setFont(qt.QFont("Arial", font_size, qt.QFont.Bold))
    label.setDefaultTextColor(qt.QColor("#eeeeee"))
    bounds = label.boundingRect()
    label.setPos(x + (w - bounds.width()) / 2.0, y + (h - bounds.height()) / 2.0)


def _wheel_delta(event):
    if hasattr(event, "angleDelta"):
        return event.angleDelta().y()
    return event.delta()


class InteractiveGraphView(qt.QGraphicsView):
    """Vue graphique avec zoom (molette), pan (glisser) et barre d'outils."""

    ZOOM_MIN = 0.2
    ZOOM_MAX = 6.0
    ZOOM_STEP = 1.18

    def _setup_interaction(self):
        self.setDragMode(qt.QGraphicsView.ScrollHandDrag)
        self.setTransformationAnchor(qt.QGraphicsView.AnchorUnderMouse)
        self.setResizeAnchor(qt.QGraphicsView.AnchorViewCenter)
        self.setHorizontalScrollBarPolicy(qt.Qt.ScrollBarAsNeeded)
        self.setVerticalScrollBarPolicy(qt.Qt.ScrollBarAsNeeded)
        self._zoom_level = 1.0

    def _pad_scene_rect(self, margin=100):
        rect = self._graphe_scene.sceneRect
        self._graphe_scene.setSceneRect(
            rect.x() - margin,
            rect.y() - margin,
            rect.width() + 2 * margin,
            rect.height() + 2 * margin,
        )

    def reset_view(self):
        self.resetTransform()
        self._zoom_level = 1.0
        rect = self._graphe_scene.sceneRect
        if rect.width() <= 0 or rect.height() <= 0:
            return
        vp = self.viewport()
        if vp.width <= 0 or vp.height <= 0:
            return
        self.fitInView(rect, qt.Qt.KeepAspectRatio)

    def zoom_in(self):
        self._apply_zoom(self.ZOOM_STEP)

    def zoom_out(self):
        self._apply_zoom(1.0 / self.ZOOM_STEP)

    def _apply_zoom(self, factor):
        new_level = self._zoom_level * factor
        if new_level < self.ZOOM_MIN or new_level > self.ZOOM_MAX:
            return
        self._zoom_level = new_level
        self.setTransformationAnchor(qt.QGraphicsView.AnchorUnderMouse)
        self.scale(factor, factor)

    def wheelEvent(self, event):
        delta = _wheel_delta(event)
        if delta > 0:
            self.zoom_in()
        elif delta < 0:
            self.zoom_out()
        event.accept()

    def create_toolbar(self):
        bar = qt.QWidget()
        layout = qt.QHBoxLayout(bar)
        layout.setContentsMargins(0, 0, 0, 4)
        layout.setSpacing(6)

        nav_hint = qt.QLabel("Molette = zoom  |  Clic gauche + glisser = deplacer")
        nav_hint.setStyleSheet("color: #6b7789; font-size: 10px;")
        layout.addWidget(nav_hint)
        layout.addStretch(1)

        btn_style_hover = (
            "QPushButton {"
            "  background-color: #242933; color: #eef2f7; border: 1px solid #353d4d;"
            "  padding: 5px 12px; border-radius: 4px; font-size: 11px; font-weight: 600;"
            "}"
            "QPushButton:hover {"
            "  background-color: #5b9fd4; color: #161920; border-color: #5b9fd4;"
            "}"
        )
        btn_zoom_in = qt.QPushButton("Zoom +")
        btn_zoom_out = qt.QPushButton("Zoom -")
        btn_reset = qt.QPushButton("Reinitialiser")
        for btn in (btn_zoom_in, btn_zoom_out, btn_reset):
            btn.setStyleSheet(btn_style_hover)

        btn_zoom_in.connect("clicked()", self.zoom_in)
        btn_zoom_out.connect("clicked()", self.zoom_out)
        btn_reset.connect("clicked()", self.reset_view)
        layout.addWidget(btn_zoom_in)
        layout.addWidget(btn_zoom_out)
        layout.addWidget(btn_reset)
        return bar


class VersionHistoryCanvas(InteractiveGraphView):
    """Graphe de versions — noeuds cliquables en mode import."""

    def __init__(self, logic, version_specs=None, selection_mode=False, parent=None):
        InteractiveGraphView.__init__(self, parent)
        self.logic = logic
        self.version_specs = version_specs if version_specs is not None else VERSION_SPECS
        self.selection_mode = selection_mode
        self._nodes_by_id = {}
        graphe_scene = qt.QGraphicsScene()
        self.setScene(graphe_scene)
        self._graphe_scene = graphe_scene
        self.setRenderHints(qt.QPainter.Antialiasing | qt.QPainter.TextAntialiasing)
        self.setStyleSheet(f"background-color: {GRAPH_BG}; border: none;")
        self.setMinimumHeight(480)
        self._setup_interaction()
        if self.selection_mode:
            self.setDragMode(qt.QGraphicsView.NoDrag)
            self.setCursor(qt.QCursor(qt.Qt.PointingHandCursor))
        self.draw()
        self._pad_scene_rect()
        self.reset_view()

    def showEvent(self, event):
        qt.QGraphicsView.showEvent(self, event)
        self.reset_view()

    def _node_at_scene_pos(self, scene_pos):
        for node_id, node in self._nodes_by_id.items():
            if (
                node["x"] <= scene_pos.x() <= node["x"] + node["w"]
                and node["y"] <= scene_pos.y() <= node["y"] + node["h"]
            ):
                return node_id
        return None

    def mousePressEvent(self, event):
        if self.selection_mode and event.button() == qt.Qt.LeftButton:
            scene_pos = self.mapToScene(event.pos())
            node_id = self._node_at_scene_pos(scene_pos)
            if node_id and hasattr(self.logic, "onVersionNodeSelected"):
                self.logic.onVersionNodeSelected(node_id)
                event.accept()
                return
        qt.QGraphicsView.mousePressEvent(self, event)

    def draw(self):
        self._graphe_scene.clear()
        if not self.version_specs:
            hint = self._graphe_scene.addText("Aucune version a afficher")
            hint.setDefaultTextColor(qt.QColor("#888888"))
            hint.setPos(MARGIN, MARGIN)
            self._graphe_scene.setSceneRect(0, 0, 400, 200)
            self._nodes_by_id = {}
            return

        positions, edges = _layout_version_graph(self.version_specs)
        self._nodes_by_id = positions
        nodes_by_id = positions
        trunk_order = _main_trunk_order(self.version_specs)

        if len(trunk_order) > 1:
            _draw_main_trunk(self._graphe_scene, nodes_by_id, trunk_order)
        trunk_pairs = set(zip(trunk_order[:-1], trunk_order[1:])) if len(trunk_order) > 1 else set()

        for parent_id, child_id, branch in edges:
            if parent_id not in nodes_by_id or child_id not in nodes_by_id:
                continue
            if (parent_id, child_id) in trunk_pairs:
                continue
            edge_color = VERSION_BRANCH_COLORS.get(branch, "#555555")
            _draw_tree_edge(
                self._graphe_scene,
                nodes_by_id[parent_id],
                nodes_by_id[child_id],
                color=edge_color,
            )

        for node in nodes_by_id.values():
            _draw_version_box_node(self._graphe_scene, node, font_size=7)

        max_y = max(node["y"] for node in nodes_by_id.values())
        scene_w = 940
        scene_h = max_y + NODE_H + 60
        self._graphe_scene.setSceneRect(0, 0, scene_w, scene_h)

        if self.selection_mode:
            title_text = "Cliquez sur un noeud pour importer cette version"
        else:
            title_text = "%d versions — branche main centree (demo ou depot)" % len(nodes_by_id)
        title = self._graphe_scene.addText(title_text)
        title.setFont(qt.QFont("Arial", 8))
        title.setDefaultTextColor(qt.QColor(MAIN_COLOR))
        title.setPos(MARGIN, scene_h - 22)

        if not self.selection_mode:
            legend_y = 8
            for text, color in [
                ("main (centre)", MAIN_COLOR),
                ("feature/mesencephale", VERSION_BRANCH_COLORS["feature/mesencephale"]),
                ("feature/striatum (gauche)", VERSION_BRANCH_COLORS["feature/striatum"]),
                ("feature/cervelet (droite)", VERSION_BRANCH_COLORS["feature/cervelet"]),
                ("feature/forebrain (ouvert)", VERSION_BRANCH_COLORS["feature/forebrain"]),
                ("HEAD", HEAD_COLOR),
            ]:
                self._graphe_scene.addRect(
                    MARGIN, legend_y, 10, 10,
                    qt.QPen(qt.QColor(color)), qt.QBrush(qt.QColor(color)),
                )
                lbl = self._graphe_scene.addText(text)
                lbl.setFont(qt.QFont("Arial", 7))
                lbl.setDefaultTextColor(qt.QColor("#888888"))
                lbl.setPos(MARGIN + 14, legend_y - 2)
                legend_y += 14


def _compute_scene_bounds(nodes, padding=30):
    max_x = max(node["x"] + node["w"] for node in nodes) + padding
    max_y = max(node["y"] + node["h"] for node in nodes) + padding
    return max(640, max_x), max(320, max_y)


class DependencyGraphCanvas(InteractiveGraphView):
    """Graphe de dependances anatomiques — charge depuis JSON / preset."""

    def __init__(
        self,
        logic,
        dependency_specs=None,
        graph_title=None,
        graph_description=None,
        parent=None,
    ):
        InteractiveGraphView.__init__(self, parent)
        self.logic = logic
        self.dependency_specs = dependency_specs if dependency_specs is not None else MOUSE_BRAIN_SPECS
        self.graph_title = graph_title or "Ontologie du projet"
        self.graph_description = graph_description or ""
        graphe_scene = qt.QGraphicsScene()
        self.setScene(graphe_scene)
        self._graphe_scene = graphe_scene
        self.setRenderHints(qt.QPainter.Antialiasing | qt.QPainter.TextAntialiasing)
        self.setStyleSheet(f"background-color: {GRAPH_BG}; border: none;")
        self.setMinimumHeight(480)
        self._setup_interaction()
        self.draw()
        self._pad_scene_rect()
        self.reset_view()

    def set_specs(self, dependency_specs, graph_title=None, graph_description=None):
        self.dependency_specs = dependency_specs
        if graph_title is not None:
            self.graph_title = graph_title
        if graph_description is not None:
            self.graph_description = graph_description
        self.draw()
        self._pad_scene_rect()
        self.reset_view()

    def showEvent(self, event):
        qt.QGraphicsView.showEvent(self, event)
        self.reset_view()

    def draw(self):
        self._graphe_scene.clear()
        if not self.dependency_specs:
            hint = self._graphe_scene.addText("Aucune ontologie chargee")
            hint.setDefaultTextColor(qt.QColor("#888888"))
            hint.setPos(MARGIN, MARGIN)
            self._graphe_scene.setSceneRect(0, 0, 400, 200)
            return

        positions, edges = _layout_hierarchy(self.dependency_specs)
        nodes_by_id = positions

        for parent_id, child_id in edges:
            if parent_id in nodes_by_id and child_id in nodes_by_id:
                _draw_tree_edge(self._graphe_scene, nodes_by_id[parent_id], nodes_by_id[child_id])

        for node in nodes_by_id.values():
            _draw_box_node(self._graphe_scene, node)

        scene_w, scene_h = _compute_scene_bounds(list(nodes_by_id.values()), padding=40)
        self._graphe_scene.setSceneRect(0, 0, scene_w, scene_h + 20)

        title_text = "%s — %d structure(s)" % (self.graph_title, len(nodes_by_id))
        if self.graph_description:
            title_text += " — " + self.graph_description
        title = self._graphe_scene.addText(title_text)
        title.setFont(qt.QFont("Arial", 8))
        title.setDefaultTextColor(qt.QColor("#777777"))
        title.setPos(MARGIN, scene_h - 6)

        legend_y = 8
        seen_colors = []
        for node in self.dependency_specs:
            color = node.get("color", "#0078d4")
            if color not in seen_colors:
                seen_colors.append(color)
        for color in seen_colors[:6]:
            self._graphe_scene.addRect(
                MARGIN, legend_y, 10, 10,
                qt.QPen(qt.QColor(color)), qt.QBrush(qt.QColor(color)),
            )
            lbl = self._graphe_scene.addText(color)
            lbl.setFont(qt.QFont("Arial", 7))
            lbl.setDefaultTextColor(qt.QColor("#888888"))
            lbl.setPos(MARGIN + 14, legend_y - 2)
            legend_y += 14

