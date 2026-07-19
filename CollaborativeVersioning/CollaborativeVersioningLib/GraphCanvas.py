"""2D canvas for dependency and version history graphs."""

import qt
from collections import defaultdict

from CollaborativeVersioningLib.simulation.DemoData import (
    VERSION_BRANCH_COLORS,
    VERSION_LANE_CENTERS,
)

GRAPH_BUILD_TAG = "2026-07-19-graph-version-v48-en"

CHECKOUT_POINTER_COLOR = "#5b9fd4"

MAIN_COLOR = "#818cf8"
GRAPH_BG = "#2a2a2a"
VERSION_NODE_W = 155
VERSION_ROW_H = 82
VERSION_Y0 = 52
VERSION_ROW_GAP = 14


H_GAP = 18
V_GAP = 52
DEPENDENCY_H_GAP = 28
DEPENDENCY_V_GAP = 78
MARGIN = 24

NODE_H = 34
NODE_FONT_SIZE = 7
NODE_PADDING_X = 16
NODE_PADDING_Y = 10
GRAPH_NAME_MAX_LEN = 22


def _node_font(font_size=NODE_FONT_SIZE):
    font = qt.QFont("Arial", font_size)
    font.setBold(True)
    return font


def _font_metrics(font_size=NODE_FONT_SIZE):
    return qt.QFontMetrics(_node_font(font_size))


def _measure_text_width(text, font_size=NODE_FONT_SIZE):
    metrics = _font_metrics(font_size)
    if hasattr(metrics, "horizontalAdvance"):
        advance = metrics.horizontalAdvance(text)
        if not callable(metrics.horizontalAdvance):
            return float(advance)
    width_fn = metrics.width
    return float(width_fn(text) if callable(width_fn) else width_fn)


def _measure_text_height(font_size=NODE_FONT_SIZE):
    metrics = _font_metrics(font_size)
    height = metrics.height if hasattr(metrics, "height") and not callable(metrics.height) else metrics.height()
    if callable(height):
        height = height()
    return float(height)


def _measure_node_size(caption, font_size=NODE_FONT_SIZE):
    text_width = _measure_text_width(caption, font_size)
    text_height = _measure_text_height(font_size)
    width = max(56, text_width + NODE_PADDING_X)
    height = max(NODE_H, text_height + NODE_PADDING_Y)
    return width, height


def _fit_caption_to_width(caption, max_inner_width, font_size=NODE_FONT_SIZE):
    if _measure_text_width(caption, font_size) <= max_inner_width:
        return caption
    metrics = _font_metrics(font_size)
    if hasattr(metrics, "elidedText"):
        elided = metrics.elidedText(caption, qt.Qt.ElideRight, int(max_inner_width))
        return str(elided)
    while caption and _measure_text_width(caption + "…", font_size) > max_inner_width:
        caption = caption[:-1]
    return (caption + "…") if caption else "…"


def _graph_display_label(spec):
    """Show full name when short enough; otherwise truncate with ellipsis."""
    name = str(spec.get("label", "")).strip()
    node_id = str(spec.get("id", "")).strip()
    if not name:
        return node_id or "?"
    if len(name) <= GRAPH_NAME_MAX_LEN:
        return name
    return name[: GRAPH_NAME_MAX_LEN - 3] + "..."


def _build_children_map(specs):
    children_map = defaultdict(list)
    for spec in specs:
        parent_id = spec.get("parent")
        if parent_id is not None:
            children_map[parent_id].append(spec["id"])
    return children_map


def _root_ids(specs):
    return [spec["id"] for spec in specs if spec.get("parent") is None]


def _default_expanded_ids(specs):
    """Start with root expanded → root and its direct children are visible."""
    return set(_root_ids(specs))


def _descendant_count(node_id, children_map):
    total = 0
    for child_id in children_map.get(node_id, []):
        total += 1 + _descendant_count(child_id, children_map)
    return total


def _visible_specs_from_expansion(specs, expanded_ids):
    specs_by_id = {spec["id"]: spec for spec in specs}
    children_map = _build_children_map(specs)
    visible = []

    def walk(node_id):
        spec = specs_by_id.get(node_id)
        if spec is None:
            return
        visible.append(spec)
        if node_id in expanded_ids:
            for child_id in children_map.get(node_id, []):
                walk(child_id)

    for root_id in _root_ids(specs):
        walk(root_id)
    return visible, children_map


def _collapsible_node_caption(spec, expanded_ids, children_map):
    label = _graph_display_label(spec)
    node_id = spec["id"]
    child_ids = children_map.get(node_id, [])
    if not child_ids:
        return label, False, False, 0

    expanded = node_id in expanded_ids
    hidden = 0 if expanded else _descendant_count(node_id, children_map)
    marker = "▼ " if expanded else "▶ "
    caption = marker + label
    if hidden:
        caption += " (+%d)" % hidden
    return caption, True, expanded, hidden


def _layout_hierarchy(specs, expanded_ids=None, full_children_map=None, h_gap=H_GAP, v_gap=V_GAP):
    """Compute x/y positions for a hierarchical tree."""
    specs_by_id = {spec["id"]: dict(spec) for spec in specs}
    children_map = _build_children_map(specs)
    if full_children_map is None:
        full_children_map = children_map
    if expanded_ids is None:
        expanded_ids = set(specs_by_id.keys())
    roots = _root_ids(specs)

    def subtree_width(node_id):
        children = children_map.get(node_id, [])
        if not children:
            caption, _, _, _ = _collapsible_node_caption(
                specs_by_id[node_id], expanded_ids, full_children_map
            )
            return _measure_node_size(caption)[0] + h_gap
        return sum(subtree_width(child_id) for child_id in children)

    positions = {}

    def assign(node_id, x_left, depth):
        spec = specs_by_id[node_id]
        caption, has_children, expanded, hidden_children = _collapsible_node_caption(
            spec, expanded_ids, full_children_map
        )
        width, height = _measure_node_size(caption)
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
            "label": caption,
            "color": spec["color"],
            "x": x,
            "y": MARGIN + depth * (NODE_H + v_gap),
            "w": width,
            "h": height,
            "has_children": has_children,
            "expanded": expanded,
            "hidden_children": hidden_children,
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


def _draw_box_node(scene, node, font_size=NODE_FONT_SIZE):
    x, y, w, h = node["x"], node["y"], node["w"], node["h"]
    color = node["color"]
    scene.addRect(
        x, y, w, h,
        qt.QPen(qt.QColor(color), 2),
        qt.QBrush(qt.QColor("#252525")),
    )
    inner_w = max(8, w - NODE_PADDING_X)
    text = _fit_caption_to_width(node["label"], inner_w, font_size)
    label = scene.addText(text)
    label.setFont(_node_font(font_size))
    label.setDefaultTextColor(qt.QColor("#eeeeee"))
    bounds = label.boundingRect()
    label.setPos(x + (w - bounds.width()) / 2.0, y + (h - bounds.height()) / 2.0)


def _draw_tree_edge(scene, parent, child, color="#555555", width=2, dashed=False):
    px, _ = _node_center(parent)
    cx, _ = _node_center(child)
    mid_y = parent["y"] + parent["h"] + (child["y"] - parent["y"] - parent["h"]) / 2.0
    pen = qt.QPen(qt.QColor(color), width)
    if dashed:
        pen.setStyle(qt.Qt.DashLine)
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


def _version_graph_edges(specs):
    specs_by_id = {spec["id"]: spec for spec in specs}
    edges = []
    merge_edge_pairs = set()
    for spec in specs:
        node_id = spec["id"]
        if spec.get("parent"):
            edges.append((spec["parent"], node_id, spec.get("branch", "main")))
        if spec.get("merge"):
            merge_target = spec.get("merge_into") or spec.get("parent")
            for merge_id in spec.get("merge_from", []):
                if not merge_target:
                    continue
                branch = specs_by_id.get(merge_id, {}).get("branch", "main")
                edges.append((merge_id, merge_target, branch))
                merge_edge_pairs.add((merge_id, merge_target))
    return edges, merge_edge_pairs


def _layout_version_graph(specs):
    """Layout : colonnes fixes par branche, lignes sans chevauchement."""
    specs_by_id = {spec["id"]: dict(spec) for spec in specs}
    rows = _compute_version_rows(specs)

    positions = {}
    for node_id, spec in specs_by_id.items():
        branch = spec.get("branch", "main")
        label = spec.get("tag") or spec["id"]
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

    edges, merge_edge_pairs = _version_graph_edges(specs)
    return positions, edges, merge_edge_pairs


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


def _draw_checkout_pointer(scene, node):
    x, y, h = node["x"], node["y"], node["h"]
    tip_x = x - 6
    mid_y = y + h / 2.0
    points = [
        qt.QPointF(tip_x, mid_y),
        qt.QPointF(tip_x - 10, mid_y - 7),
        qt.QPointF(tip_x - 10, mid_y + 7),
    ]
    scene.addPolygon(
        qt.QPolygonF(points),
        qt.QPen(qt.QColor(CHECKOUT_POINTER_COLOR), 1),
        qt.QBrush(qt.QColor(CHECKOUT_POINTER_COLOR)),
    )


def _wheel_delta(event):
    if hasattr(event, "angleDelta"):
        return event.angleDelta().y()
    return event.delta()


class InteractiveGraphView(qt.QGraphicsView):
    """Graphics view with mouse-wheel zoom, drag-to-pan, and a small toolbar."""

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

    def create_toolbar(self, leading_widgets=None):
        bar = qt.QWidget()
        layout = qt.QHBoxLayout(bar)
        layout.setContentsMargins(0, 0, 0, 4)
        layout.setSpacing(6)

        if leading_widgets:
            for widget in leading_widgets:
                layout.addWidget(widget)
        layout.addStretch(1)

        btn_style_hover = (
            "QPushButton {"
            "  background-color: #383838; color: #eef2f7; border: 1px solid #505050;"
            "  padding: 5px 12px; border-radius: 4px; font-size: 11px; font-weight: 600;"
            "}"
            "QPushButton:hover {"
            "  background-color: #5b9fd4; color: #161920; border-color: #5b9fd4;"
            "}"
        )
        btn_zoom_in = qt.QPushButton("Zoom in")
        btn_zoom_out = qt.QPushButton("Zoom out")
        btn_reset = qt.QPushButton("Reset view")
        for btn in (btn_zoom_in, btn_zoom_out, btn_reset):
            btn.setStyleSheet(btn_style_hover)

        btn_zoom_in.connect("clicked()", self.zoom_in)
        btn_zoom_out.connect("clicked()", self.zoom_out)
        btn_reset.connect("clicked()", self.reset_view)
        layout.addWidget(btn_zoom_in)
        layout.addWidget(btn_zoom_out)
        layout.addWidget(btn_reset)
        return bar


def commit_history_lookup(commit_history):
    lookup = {}
    for row in commit_history or []:
        if not row:
            continue
        version_id = str(row[0])
        lookup[version_id] = {
            "date": str(row[1]) if len(row) > 1 else "",
            "author": str(row[2]) if len(row) > 2 else "",
            "message": str(row[3]) if len(row) > 3 else "",
            "status": str(row[4]) if len(row) > 4 else "",
        }
    return lookup


class VersionHistoryCanvas(InteractiveGraphView):
    """Graphe de versions — noeuds cliquables en mode import."""

    def __init__(
        self,
        logic,
        version_specs=None,
        selection_mode=False,
        graph_title=None,
        graph_description=None,
        active_version_id=None,
        commit_history_by_id=None,
        parent=None,
    ):
        InteractiveGraphView.__init__(self, parent)
        self.logic = logic
        self.version_specs = version_specs if version_specs is not None else []
        self.selection_mode = selection_mode
        self.graph_title = graph_title or "Version tree"
        self.graph_description = graph_description or ""
        self.active_version_id = active_version_id
        self.commit_history_by_id = dict(commit_history_by_id or {})
        self._specs_by_id = {spec["id"]: spec for spec in self.version_specs}
        self._nodes_by_id = {}
        self._pending_node_id = None
        self._click_timer = qt.QTimer(self)
        self._click_timer.setSingleShot(True)
        self._click_timer.setInterval(220)
        self._click_timer.connect("timeout()", self._on_single_click_timeout)
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

    def set_active_version_id(self, version_id):
        if version_id == self.active_version_id:
            return
        self.active_version_id = version_id
        self.draw()
        self._pad_scene_rect()

    def create_toolbar(self):
        if self.selection_mode:
            hint = qt.QLabel("Click a node to import · Double-click for details")
        else:
            hint = qt.QLabel(
                "Click a node to check out (simulation) · Double-click for details"
            )
        hint.setStyleSheet("color: #6b7789; font-size: 10px;")
        return InteractiveGraphView.create_toolbar(self, leading_widgets=[hint])

    def _show_version_info(self, node_id):
        spec = self._specs_by_id.get(node_id)
        if not spec:
            return
        history = self.commit_history_by_id.get(node_id, {})
        checked_out = node_id == self.active_version_id
        dialog = _VersionInfoDialog(self, spec, history, checked_out=checked_out)
        dialog.exec_()

    def _on_single_click_timeout(self):
        node_id = self._pending_node_id
        self._pending_node_id = None
        if not node_id:
            return
        if self.selection_mode and hasattr(self.logic, "onVersionNodeSelected"):
            self.logic.onVersionNodeSelected(node_id)
        elif not self.selection_mode and hasattr(self.logic, "onVersionCheckedOut"):
            self.logic.onVersionCheckedOut(node_id)

    def showEvent(self, event):
        qt.QGraphicsView.showEvent(self, event)
        self.reset_view()

    def _node_at_scene_pos(self, scene_pos):
        return _node_id_at_scene_pos(self._nodes_by_id, scene_pos)

    def mousePressEvent(self, event):
        if event.button() == qt.Qt.LeftButton:
            scene_pos = self.mapToScene(_qt_event_pos(event))
            node_id = self._node_at_scene_pos(scene_pos)
            if node_id:
                self._pending_node_id = node_id
                self._click_timer.start()
                event.accept()
                return
        qt.QGraphicsView.mousePressEvent(self, event)

    def mouseDoubleClickEvent(self, event):
        self._click_timer.stop()
        self._pending_node_id = None
        if event.button() == qt.Qt.LeftButton:
            scene_pos = self.mapToScene(_qt_event_pos(event))
            node_id = self._node_at_scene_pos(scene_pos)
            if node_id:
                self._show_version_info(node_id)
                event.accept()
                return
        qt.QGraphicsView.mouseDoubleClickEvent(self, event)

    def draw(self):
        self._graphe_scene.clear()
        if not self.version_specs:
            hint = self._graphe_scene.addText("No versions to display.")
            hint.setDefaultTextColor(qt.QColor("#888888"))
            hint.setPos(MARGIN, MARGIN)
            self._graphe_scene.setSceneRect(0, 0, 400, 200)
            self._nodes_by_id = {}
            return

        positions, edges, _ = _layout_version_graph(self.version_specs)
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
                width=2,
                dashed=False,
            )

        for node in nodes_by_id.values():
            _draw_version_box_node(self._graphe_scene, node, font_size=7)
            if self.active_version_id and node["id"] == self.active_version_id:
                _draw_checkout_pointer(self._graphe_scene, node)

        max_y = max(node["y"] for node in nodes_by_id.values())
        scene_w = 940
        scene_h = max_y + NODE_H + 40
        self._graphe_scene.setSceneRect(0, 0, scene_w, scene_h + 28)

        if self.selection_mode:
            title_text = "Click a node to import that version"
        else:
            title_text = "%s — %d version(s) · main branch centered" % (
                self.graph_title,
                len(nodes_by_id),
            )
            if self.active_version_id:
                active_label = self.active_version_id
                for spec in self.version_specs:
                    if spec.get("id") == self.active_version_id:
                        active_label = spec.get("tag") or active_label
                        break
                title_text += " · checked out: %s" % active_label
            if self.graph_description:
                title_text += " — " + self.graph_description
        title = self._graphe_scene.addText(title_text)
        title.setFont(qt.QFont("Arial", 8))
        title.setDefaultTextColor(qt.QColor("#777777"))
        title.setPos(MARGIN, scene_h + 4)


def _compute_scene_bounds(nodes, padding=30):
    max_x = max(node["x"] + node["w"] for node in nodes) + padding
    max_y = max(node["y"] + node["h"] for node in nodes) + padding
    return max(640, max_x), max(320, max_y)


def _qt_event_pos(event):
    pos = event.pos if hasattr(event, "pos") and not callable(event.pos) else event.pos()
    if callable(pos):
        pos = pos()
    return pos


def _node_id_at_scene_pos(nodes_by_id, scene_pos):
    for node_id, node in nodes_by_id.items():
        if (
            node["x"] <= scene_pos.x() <= node["x"] + node["w"]
            and node["y"] <= scene_pos.y() <= node["y"] + node["h"]
        ):
            return node_id
    return None


class _VersionInfoDialog(qt.QDialog):
    """Read-only details for a version graph node."""

    def __init__(self, parent, spec, history=None, checked_out=False):
        qt.QDialog.__init__(self, parent)
        self.setWindowTitle("Version details")
        self.setMinimumWidth(440)
        layout = qt.QVBoxLayout(self)
        form = qt.QFormLayout()

        def add_row(title, value):
            label = qt.QLabel(value or "—")
            label.setWordWrap(True)
            label.setTextInteractionFlags(qt.Qt.TextSelectableByMouse)
            form.addRow(title, label)

        history = history or {}
        message = history.get("message") or spec.get("label", "")
        roles = []
        if spec.get("head"):
            roles.append("HEAD")
        if checked_out:
            roles.append("Checked out")
        if spec.get("merge"):
            roles.append("Merge commit")

        add_row("Version:", str(spec.get("tag", "")))
        add_row("Internal id:", str(spec.get("id", "")))
        add_row("Branch:", str(spec.get("branch", "")))
        add_row("Title:", str(spec.get("label", "")))
        add_row("Message:", message)
        add_row("Date:", history.get("date", ""))
        add_row("Author:", history.get("author", ""))
        add_row("Status:", history.get("status", ""))
        add_row("Parent:", str(spec.get("parent") or "—"))
        if spec.get("merge"):
            merge_from = spec.get("merge_from") or []
            add_row("Merge from:", ", ".join(merge_from) if merge_from else "—")
            merge_into = spec.get("merge_into") or spec.get("parent") or "—"
            add_row("Merge into:", str(merge_into))
        add_row("Role:", ", ".join(roles) if roles else "—")

        layout.addLayout(form)

        footer = qt.QHBoxLayout()
        footer.addStretch(1)
        close_btn = qt.QPushButton("Close")
        close_btn.connect("clicked()", self.accept)
        footer.addWidget(close_btn)
        layout.addLayout(footer)


class _StructureInfoDialog(qt.QDialog):
    """Read-only details for a dependency graph node."""

    def __init__(self, parent, spec):
        qt.QDialog.__init__(self, parent)
        self.setWindowTitle("Structure details")
        self.setMinimumWidth(420)
        layout = qt.QVBoxLayout(self)
        form = qt.QFormLayout()

        def add_row(title, value):
            label = qt.QLabel(value or "—")
            label.setWordWrap(True)
            label.setTextInteractionFlags(qt.Qt.TextSelectableByMouse)
            form.addRow(title, label)

        add_row("Id:", str(spec.get("id", "")))
        add_row("Name:", str(spec.get("label", "")))
        acronym = str(spec.get("symbol", "")).strip()
        add_row("Acronym:", acronym if acronym else "—")
        layout.addLayout(form)

        footer = qt.QHBoxLayout()
        footer.addStretch(1)
        close_btn = qt.QPushButton("Close")
        close_btn.connect("clicked()", self.accept)
        footer.addWidget(close_btn)
        layout.addLayout(footer)


class DependencyGraphCanvas(InteractiveGraphView):
    """Anatomical dependency graph with expand/collapse navigation."""

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
        self._all_specs = list(dependency_specs or [])
        self.dependency_specs = self._all_specs
        self.graph_title = graph_title or "Project ontology"
        self.graph_description = graph_description or ""
        self._full_children_map = _build_children_map(self._all_specs)
        self._expanded_ids = _default_expanded_ids(self._all_specs)
        self._nodes_by_id = {}
        self._specs_by_id = {}
        self._pending_node_id = None
        self._click_timer = qt.QTimer(self)
        self._click_timer.setSingleShot(True)
        self._click_timer.setInterval(220)
        self._click_timer.connect("timeout()", self._on_single_click_timeout)
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
        self._all_specs = list(dependency_specs or [])
        self.dependency_specs = self._all_specs
        self._full_children_map = _build_children_map(self._all_specs)
        self._expanded_ids = _default_expanded_ids(self._all_specs)
        if graph_title is not None:
            self.graph_title = graph_title
        if graph_description is not None:
            self.graph_description = graph_description
        self.draw()
        self._pad_scene_rect()
        self.reset_view()

    def create_toolbar(self):
        hint = qt.QLabel("Click parent to expand/collapse · Double-click for details")
        hint.setStyleSheet("color: #6b7789; font-size: 10px;")
        btn_collapse = qt.QPushButton("Collapse all")
        btn_collapse.setToolTip("Show only the root level again.")
        btn_collapse.connect("clicked()", self._collapse_all)
        return InteractiveGraphView.create_toolbar(
            self,
            leading_widgets=[hint, btn_collapse],
        )

    def _collapse_all(self):
        self._expanded_ids = _default_expanded_ids(self._all_specs)
        self.draw()
        self._pad_scene_rect()
        self.reset_view()

    def _has_children(self, node_id):
        return bool(self._full_children_map.get(node_id))

    def _toggle_node_expanded(self, node_id):
        if not self._has_children(node_id):
            return False
        if node_id in self._expanded_ids:
            self._expanded_ids.discard(node_id)
        else:
            self._expanded_ids.add(node_id)
        self.draw()
        self._pad_scene_rect()
        self.reset_view()
        return True

    def showEvent(self, event):
        qt.QGraphicsView.showEvent(self, event)
        self.reset_view()

    def _node_at_scene_pos(self, scene_pos):
        return _node_id_at_scene_pos(self._nodes_by_id, scene_pos)

    def _show_structure_info(self, node_id):
        spec = next((item for item in self._all_specs if item["id"] == node_id), None)
        if not spec:
            return
        dialog = _StructureInfoDialog(self, spec)
        dialog.exec_()

    def _on_single_click_timeout(self):
        node_id = self._pending_node_id
        self._pending_node_id = None
        if node_id:
            self._toggle_node_expanded(node_id)

    def mousePressEvent(self, event):
        if event.button() == qt.Qt.LeftButton:
            scene_pos = self.mapToScene(_qt_event_pos(event))
            node_id = self._node_at_scene_pos(scene_pos)
            if node_id and self._has_children(node_id):
                self._pending_node_id = node_id
                self._click_timer.start()
                event.accept()
                return
        qt.QGraphicsView.mousePressEvent(self, event)

    def mouseDoubleClickEvent(self, event):
        self._click_timer.stop()
        self._pending_node_id = None
        if event.button() == qt.Qt.LeftButton:
            scene_pos = self.mapToScene(_qt_event_pos(event))
            node_id = self._node_at_scene_pos(scene_pos)
            if node_id:
                self._show_structure_info(node_id)
                event.accept()
                return
        qt.QGraphicsView.mouseDoubleClickEvent(self, event)

    def draw(self):
        self._graphe_scene.clear()
        if not self._all_specs:
            hint = self._graphe_scene.addText("No ontology loaded.")
            hint.setDefaultTextColor(qt.QColor("#888888"))
            hint.setPos(MARGIN, MARGIN)
            self._graphe_scene.setSceneRect(0, 0, 400, 200)
            self._nodes_by_id = {}
            self._specs_by_id = {}
            return

        visible_specs, _children_map = _visible_specs_from_expansion(
            self._all_specs,
            self._expanded_ids,
        )
        self.dependency_specs = visible_specs
        if not visible_specs:
            hint = self._graphe_scene.addText("No structures to display.")
            hint.setDefaultTextColor(qt.QColor("#888888"))
            hint.setPos(MARGIN, MARGIN)
            self._graphe_scene.setSceneRect(0, 0, 400, 200)
            return

        positions, edges = _layout_hierarchy(
            visible_specs,
            expanded_ids=self._expanded_ids,
            full_children_map=self._full_children_map,
            h_gap=DEPENDENCY_H_GAP,
            v_gap=DEPENDENCY_V_GAP,
        )
        nodes_by_id = positions
        self._nodes_by_id = nodes_by_id
        self._specs_by_id = {spec["id"]: spec for spec in visible_specs}

        for parent_id, child_id in edges:
            if parent_id in nodes_by_id and child_id in nodes_by_id:
                _draw_tree_edge(self._graphe_scene, nodes_by_id[parent_id], nodes_by_id[child_id])

        for node in nodes_by_id.values():
            _draw_box_node(self._graphe_scene, node)

        scene_w, scene_h = _compute_scene_bounds(list(nodes_by_id.values()), padding=40)
        self._graphe_scene.setSceneRect(0, 0, scene_w, scene_h + 28)

        expanded_count = len(self._expanded_ids)
        title_text = "%s — showing %d of %d structure(s) · %d branch(es) expanded" % (
            self.graph_title,
            len(nodes_by_id),
            len(self._all_specs),
            expanded_count,
        )
        if self.graph_description:
            title_text += " — " + self.graph_description
        title = self._graphe_scene.addText(title_text)
        title.setFont(qt.QFont("Arial", 8))
        title.setDefaultTextColor(qt.QColor("#777777"))
        title.setPos(MARGIN, scene_h + 4)
