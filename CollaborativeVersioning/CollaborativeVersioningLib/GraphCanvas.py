"""2D canvas for dependency and version history graphs."""

import qt
from collections import defaultdict

from CollaborativeVersioningLib import UiStyles as _ui

MAIN_COLOR = _ui.ACCENT_INDIGO
MAIN_LANE_X = 435
VERSION_NODE_W = 155
VERSION_ROW_H = 82
VERSION_Y0 = 52
VERSION_ROW_GAP = 14


DEPENDENCY_H_GAP = 28
DEPENDENCY_V_GAP = 78
MARGIN = 24

NODE_H = 34
NODE_FONT_SIZE = 7
NODE_PADDING_X = 16
NODE_PADDING_Y = 10
GRAPH_NAME_MAX_LEN = 22
COVERAGE_BADGE_RADIUS = 4.5
COVERAGE_BADGE_INSET = 9
COVERAGE_BADGE_RESERVE = 18


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


def _ontology_id_key(value):
    text = str(value).strip()
    if text.isdigit():
        return str(int(text))
    return text


def _coverage_self_color(added):
    return _ui.ACCENT_MINT if added else _ui.TEXT_MUTED


def _coverage_children_color(status):
    if status == "all":
        return _ui.ACCENT_INDIGO
    if status == "some":
        return _ui.ACCENT_AMBER
    return _ui.TEXT_MUTED


def _coverage_self_label(added):
    return "Has an annotation" if added else "No annotation"


def _coverage_children_label(status):
    if status == "all":
        return "All children have an annotation"
    if status == "some":
        return "Some children have an annotation"
    if status == "none":
        return "No children have an annotation"
    return "—"


def _coverage_by_id(specs, painted_ids):
    """Per node: this structure added (bool) and children coverage (all/some/none/None)."""
    painted = {_ontology_id_key(item) for item in (painted_ids or [])}
    children_map = _build_children_map(specs)
    self_added = {
        spec["id"]: _ontology_id_key(spec["id"]) in painted for spec in specs
    }
    coverage = {}
    leaf_cache = {}

    def leaf_counts(node_id):
        cached = leaf_cache.get(node_id)
        if cached is not None:
            return cached
        child_ids = children_map.get(node_id, [])
        if not child_ids:
            result = (1 if self_added.get(node_id) else 0, 1)
            leaf_cache[node_id] = result
            return result
        added = 0
        total = 0
        for child_id in child_ids:
            child_added, child_total = leaf_counts(child_id)
            added += child_added
            total += child_total
        result = (added, total)
        leaf_cache[node_id] = result
        return result

    for spec in specs:
        node_id = spec["id"]
        child_ids = children_map.get(node_id, [])
        if not child_ids:
            coverage[node_id] = {"self": bool(self_added.get(node_id)), "children": None}
            continue
        added, total = leaf_counts(node_id)
        if total <= 0 or added <= 0:
            children_status = "none"
        elif added >= total:
            children_status = "all"
        else:
            children_status = "some"
        coverage[node_id] = {
            "self": bool(self_added.get(node_id)),
            "children": children_status,
        }
    return coverage


def _leaf_annotation_counts(specs, coverage_map):
    children_map = _build_children_map(specs)
    leaves = [spec["id"] for spec in specs if not children_map.get(spec["id"])]
    added = sum(
        1 for node_id in leaves if (coverage_map.get(node_id) or {}).get("self")
    )
    return added, len(leaves)


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


def _layout_hierarchy(specs, expanded_ids=None, full_children_map=None, h_gap=DEPENDENCY_H_GAP, v_gap=DEPENDENCY_V_GAP):
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
            return _measure_node_size(caption)[0] + 2 * COVERAGE_BADGE_RESERVE + h_gap
        return sum(subtree_width(child_id) for child_id in children)

    positions = {}

    def assign(node_id, x_left, depth):
        spec = specs_by_id[node_id]
        caption, has_children, expanded, hidden_children = _collapsible_node_caption(
            spec, expanded_ids, full_children_map
        )
        width, height = _measure_node_size(caption)
        width += 2 * COVERAGE_BADGE_RESERVE
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


def _draw_box_node(scene, node, font_size=NODE_FONT_SIZE, coverage=None):
    x, y, w, h = node["x"], node["y"], node["w"], node["h"]
    color = node["color"]
    scene.addRect(
        x, y, w, h,
        qt.QPen(qt.QColor(color), 2),
        qt.QBrush(qt.QColor(_ui.GRAPH_NODE_FILL)),
    )
    inner_w = max(8, w - NODE_PADDING_X - 2 * COVERAGE_BADGE_RESERVE)
    text = _fit_caption_to_width(node["label"], inner_w, font_size)
    label = scene.addText(text)
    label.setFont(_node_font(font_size))
    label.setDefaultTextColor(qt.QColor(_ui.GRAPH_NODE_TEXT))
    bounds = label.boundingRect()
    label.setPos(x + (w - bounds.width()) / 2.0, y + (h - bounds.height()) / 2.0)
    if coverage is not None:
        _draw_coverage_badges(scene, x, y, w, coverage)


def _draw_coverage_dot(scene, cx, cy, radius, filled, color_hex):
    color = qt.QColor(color_hex)
    if filled:
        scene.addEllipse(
            cx - radius,
            cy - radius,
            radius * 2,
            radius * 2,
            qt.QPen(color, 1),
            qt.QBrush(color),
        )
        return
    scene.addEllipse(
        cx - radius,
        cy - radius,
        radius * 2,
        radius * 2,
        qt.QPen(color, 1.4),
        qt.QBrush(qt.QColor(_ui.GRAPH_NODE_FILL)),
    )


def _draw_coverage_badges(scene, x, y, w, coverage):
    radius = COVERAGE_BADGE_RADIUS
    cy = y + COVERAGE_BADGE_INSET
    self_added = bool(coverage.get("self"))
    children_status = coverage.get("children")
    _draw_coverage_dot(
        scene,
        x + COVERAGE_BADGE_INSET,
        cy,
        radius,
        self_added,
        _coverage_self_color(self_added),
    )
    if children_status is None:
        return
    _draw_coverage_dot(
        scene,
        x + w - COVERAGE_BADGE_INSET,
        cy,
        radius,
        children_status != "none",
        _coverage_children_color(children_status),
    )


def _draw_ontology_edge(scene, parent, child, color=None, width=2):
    """Orthogonal tree: leave the bottom-center of the parent, then drop to the child."""
    if color is None:
        color = _ui.GRAPH_EDGE
    px = parent["x"] + parent["w"] / 2.0
    cx = child["x"] + child["w"] / 2.0
    start_y = parent["y"] + parent["h"]
    end_y = child["y"]
    pen = qt.QPen(qt.QColor(color), width)
    if abs(px - cx) < 1:
        scene.addLine(px, start_y, cx, end_y, pen)
        return
    mid_y = start_y + (end_y - start_y) / 2.0
    scene.addLine(px, start_y, px, mid_y, pen)
    scene.addLine(px, mid_y, cx, mid_y, pen)
    scene.addLine(cx, mid_y, cx, end_y, pen)


def _draw_tree_edge(scene, parent, child, color=None, width=2):
    if color is None:
        color = _ui.GRAPH_EDGE
    px, py = _node_center(parent)
    cx, cy = _node_center(child)
    pen = qt.QPen(qt.QColor(color), width)
    parent_branch = parent.get("branch") or "main"
    child_branch = child.get("branch") or "main"
    if abs(px - cx) < 1:
        scene.addLine(px, parent["y"] + parent["h"], cx, child["y"], pen)
        return
    merge_in = child.get("merge") or (
        child_branch == "main" and parent_branch != "main"
    )
    if merge_in:
        # Branch → main (Accept): arrive a bit above center on main.
        start_y = parent["y"] + parent["h"] if py <= cy else parent["y"]
        shift = min(10.0, max(6.0, child["h"] * 0.22))
        end_y = cy - shift
        end_x = child["x"] + child["w"] if px > cx else child["x"]
        scene.addLine(px, start_y, px, end_y, pen)
        scene.addLine(px, end_y, end_x, end_y, pen)
        return
    start_x = parent["x"] + parent["w"] if cx > px else parent["x"]
    # Main → branch (fork): leave a bit below center on main.
    if parent_branch == "main" and child_branch != "main":
        shift = min(10.0, max(6.0, parent["h"] * 0.22))
        start_y = py + shift
        scene.addLine(start_x, start_y, cx, start_y, pen)
        scene.addLine(cx, start_y, cx, child["y"], pen)
        return
    scene.addLine(start_x, py, cx, py, pen)
    scene.addLine(cx, py, cx, child["y"], pen)


# Reserved for compare-dialog outlines (not used as normal node/branch colors).
COMPARE_DIFF_COLOR = "#dc2626"  # red — Local / Shared diffs
COMPARE_RESULT_COLOR = "#16a34a"  # green — Result preview (what this choice applies)


# Assignment for side-branch colors in the current graph / history (not main).
_branch_color_by_lane: dict[str, str] = {}


def _side_branch_palette():
    """Strong hues for side branches — not main indigo, not compare red/green."""
    if getattr(_ui, "IS_DARK", True):
        return [
            "#f59e0b",  # amber
            "#22d3ee",  # cyan
            "#f472b6",  # pink
            "#a3e635",  # lime
            "#fb923c",  # orange
            "#e879f9",  # magenta
            "#2dd4bf",  # teal
            "#fcd34d",  # gold
            "#38bdf8",  # sky
            "#c084fc",  # violet (lighter than main indigo)
            "#fdba74",  # peach
            "#67e8f9",  # ice cyan
            "#f9a8d4",  # rose
            "#bef264",  # yellow-green
            "#fbbf24",  # warm gold
            "#d946ef",  # fuchsia
        ]
    return [
        "#d97706",  # amber
        "#0891b2",  # cyan
        "#db2777",  # pink
        "#65a30d",  # lime
        "#ea580c",  # orange
        "#a21caf",  # magenta
        "#0f766e",  # teal
        "#ca8a04",  # yellow
        "#0284c7",  # sky
        "#7c3aed",  # violet
        "#c2410c",  # burnt orange
        "#0e7490",  # deep cyan
        "#be185d",  # rose
        "#4d7c0f",  # olive
        "#b45309",  # brown-gold
        "#86198f",  # deep fuchsia
    ]


def prepare_branch_colors(branches) -> None:
    """Assign unique palette colors to displayed side branches (stable order).

    ``main`` stays on the theme indigo. Side lanes are sorted and take distinct
    palette entries until the palette is exhausted (then colors reuse).
    Call before painting the Version tree or styling Version history so both match.
    """
    global _branch_color_by_lane
    names = sorted(
        {
            str(name).strip()
            for name in (branches or ())
            if str(name).strip() and str(name).strip().lower() != "main"
        },
        key=lambda text: text.lower(),
    )
    palette = _side_branch_palette()
    if not palette:
        _branch_color_by_lane = {}
        return
    assigned: dict[str, str] = {}
    for index, name in enumerate(names):
        assigned[name] = palette[index % len(palette)]
    _branch_color_by_lane = assigned


def _branch_color(branch):
    """Color for a version-tree lane (main + side branches). Shared with Version history."""
    name = str(branch or "").strip() or "main"
    if name.lower() == "main":
        # Read theme live (MAIN_COLOR is only an import-time fallback).
        return _ui.ACCENT_INDIGO or MAIN_COLOR or "#818cf8"
    mapped = _branch_color_by_lane.get(name)
    if mapped:
        return mapped
    # Fallback if prepare_branch_colors was not called (isolated lookup).
    palette = _side_branch_palette()
    if not palette:
        return _ui.ACCENT_INDIGO or MAIN_COLOR or "#818cf8"
    acc = 0
    for char in name:
        acc = (acc * 33 + ord(char)) % 2147483647
    return palette[(acc * 7) % len(palette)]


def branch_color(branch):
    """Public alias used by Version history (must match Version tree boxes/edges)."""
    return _branch_color(branch)


def _ranges_overlap(first, second):
    return not (first[1] < second[0] or second[1] < first[0])


def _side_branch_spans(specs, rows):
    specs_by_id = {spec["id"]: spec for spec in specs or []}
    spans = {}
    for spec in specs or []:
        branch = spec.get("branch") or "main"
        if branch == "main":
            continue
        row = rows.get(spec["id"], 0)
        current = spans.get(branch)
        if current is None:
            spans[branch] = (row, row)
        else:
            spans[branch] = (min(current[0], row), max(current[1], row))
    for spec in specs or []:
        if not spec.get("merge"):
            continue
        merge_row = rows.get(spec["id"], 0)
        for source_id in spec.get("merge_from") or []:
            source = specs_by_id.get(source_id) or {}
            branch = source.get("branch") or "main"
            if branch == "main" or branch not in spans:
                continue
            lo, hi = spans[branch]
            spans[branch] = (lo, max(hi, merge_row))
    return spans


def _assign_side_lanes(specs, rows):
    """Closest free column: right of main, then left, then further out. Reuse when ranges do not overlap."""
    assigned = {"main": 0}
    occupied = defaultdict(list)
    spans = _side_branch_spans(specs, rows)
    for branch in sorted(spans, key=lambda name: (spans[name][0], name)):
        span = spans[branch]
        chosen = None
        for offset in range(1, 24):
            for lane in (offset, -offset):
                if all(not _ranges_overlap(span, other) for other in occupied[lane]):
                    chosen = lane
                    break
            if chosen is not None:
                break
        if chosen is None:
            chosen = max(assigned.values(), default=0) + 1
        assigned[branch] = chosen
        occupied[chosen].append(span)
    return assigned


def _lane_centers_for(specs, rows=None):
    if rows is None:
        rows = _compute_version_rows(specs or [])
    assigned = _assign_side_lanes(specs, rows)
    spacing = 200
    centers = {"main": MAIN_LANE_X}
    for branch, lane in assigned.items():
        centers[branch] = MAIN_LANE_X + lane * spacing
    return centers


def _version_lane_x(branch, centers=None):
    if not centers:
        centers = {"main": MAIN_LANE_X}
    center = centers.get(branch, centers.get("main", MAIN_LANE_X))
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
    for spec in specs:
        node_id = spec["id"]
        if spec.get("parent"):
            edges.append((spec["parent"], node_id, spec.get("branch", "main")))
        if spec.get("merge"):
            merge_target = spec.get("id")
            for merge_id in spec.get("merge_from", []):
                if merge_id == merge_target:
                    continue
                branch = specs_by_id.get(merge_id, {}).get("branch", "main")
                edges.append((merge_id, merge_target, branch))
    return edges


def _layout_version_graph(specs):
    """Layout : colonnes par ligne de versions, lignes sans chevauchement."""
    specs_by_id = {spec["id"]: dict(spec) for spec in specs}
    prepare_branch_colors(spec.get("branch", "main") for spec in specs)
    rows = _compute_version_rows(specs)
    centers = _lane_centers_for(specs, rows)

    positions = {}
    for node_id, spec in specs_by_id.items():
        branch = spec.get("branch", "main")
        label = spec.get("tag") or spec["id"]
        y = VERSION_Y0 + rows[node_id] * VERSION_ROW_H
        x = _version_lane_x(branch, centers)
        color = _branch_color(branch)

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
        }

    _resolve_vertical_overlaps(positions)
    if positions:
        min_x = min(node["x"] for node in positions.values())
        if min_x < MARGIN:
            shift = MARGIN - min_x
            for node in positions.values():
                node["x"] += shift

    return positions, _version_graph_edges(specs)


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
    pen = qt.QPen(qt.QColor(_ui.ACCENT_INDIGO), 4)
    for index in range(len(trunk_order) - 1):
        upper = positions[trunk_order[index + 1]]
        lower = positions[trunk_order[index]]
        ux, uy = _node_center(upper)
        lx, ly = _node_center(lower)
        scene.addLine(lx, ly + lower["h"] / 2.0, ux, uy - upper["h"] / 2.0, pen)


def _node_is_unshared(node_id, commit_history_by_id):
    """True when Status is local (saved here, not shared yet)."""
    info = (commit_history_by_id or {}).get(node_id) or {}
    return str(info.get("status") or "").strip().lower() == "local"


def _draw_version_box_node(scene, node, font_size=7):
    x, y, w, h = node["x"], node["y"], node["w"], node["h"]
    color = node["color"]
    border = 3 if node.get("merge") else 2
    # Dashed border = saved on this computer, not shared yet (Status: local).
    style = qt.Qt.DashLine if node.get("unshared") else qt.Qt.SolidLine
    scene.addRect(
        x, y, w, h,
        qt.QPen(qt.QColor(color), border, style),
        qt.QBrush(qt.QColor(_ui.GRAPH_NODE_FILL)),
    )
    text = node["label"]
    if len(text) > 22:
        text = text[:19] + "..."
    label = scene.addText(text)
    label.setFont(qt.QFont("Arial", font_size, qt.QFont.Bold))
    label.setDefaultTextColor(qt.QColor(_ui.GRAPH_NODE_TEXT))
    bounds = label.boundingRect()
    label.setPos(x + (w - bounds.width()) / 2.0, y + (h - bounds.height()) / 2.0)


def _draw_share_status_legend(scene, x, y):
    """Tiny legend: solid = shared, dashed = not shared yet.

    Returns scene QRectF covering the legend text.
    """
    text = scene.addText(
        "Solid box = shared    ·    Dashed box = saved here · not shared yet"
    )
    text.setFont(qt.QFont("Arial", 8))
    text.setDefaultTextColor(qt.QColor(_ui.GRAPH_HINT or _ui.GRAPH_TITLE or "#888888"))
    text.setPos(x, y)
    bounds = text.boundingRect()
    return qt.QRectF(float(x), float(y), float(bounds.width()), float(bounds.height()))


def _draw_checkout_pointer(scene, node, color=None):
    x, y, h = node["x"], node["y"], node["h"]
    tip_x = x - 6
    mid_y = y + h / 2.0
    points = [
        qt.QPointF(tip_x, mid_y),
        qt.QPointF(tip_x - 10, mid_y - 7),
        qt.QPointF(tip_x - 10, mid_y + 7),
    ]
    # Checkout "cursor": mint green (same family as former HEAD_COLOR #6ee7b7).
    pointer = color or _ui.ACCENT_MINT or "#6ee7b7"
    scene.addPolygon(
        qt.QPolygonF(points),
        qt.QPen(qt.QColor(pointer), 1),
        qt.QBrush(qt.QColor(pointer)),
    )


def _build_one_diff_caption(node_id, commit_history_by_id, side):
    """Short label for a single diff node: when / who (shared only)."""
    info = (commit_history_by_id or {}).get(node_id) or {}
    author = str(info.get("author") or "").strip() or "a colleague"
    when = str(info.get("date") or "").strip() or "recently"
    side = str(side or "").strip().lower()
    if side == "local":
        return "Saved · not shared yet\n%s" % when
    return "Shared by %s\n%s" % (author, when)


def _build_one_result_caption(node_id, commit_history_by_id, role):
    """Short label for a Result green mark: from shared vs yours on top."""
    info = (commit_history_by_id or {}).get(node_id) or {}
    when = str(info.get("date") or "").strip() or "recently"
    role = str(role or "").strip().lower()
    if role == "local":
        return "Yours on top\n%s" % when
    return "From shared\n%s" % when


def _measure_caption_size(text, font_size=8):
    font = qt.QFont("Arial", font_size)
    metrics = qt.QFontMetrics(font)
    lines = [line for line in str(text or "").split("\n") if line] or [""]
    widths = []
    for line in lines:
        if hasattr(metrics, "horizontalAdvance"):
            advance = metrics.horizontalAdvance(line)
            widths.append(float(advance() if callable(advance) else advance))
        else:
            widths.append(float(metrics.width(line)))
    line_h = metrics.lineSpacing()
    if callable(line_h):
        line_h = line_h()
    return max(widths) if widths else 0.0, float(line_h) * len(lines)


def _rect_overlap_area(a, b):
    x0 = max(a.left(), b.left())
    y0 = max(a.top(), b.top())
    x1 = min(a.right(), b.right())
    y1 = min(a.bottom(), b.bottom())
    if x1 <= x0 or y1 <= y0:
        return 0.0
    return float(x1 - x0) * float(y1 - y0)


def _annotation_collision_score(rects, obstacles):
    score = 0.0
    for rect in rects:
        for obs in obstacles:
            score += _rect_overlap_area(rect, obs)
    return score


def _diff_annotation_layout(box, text_w, text_h, side):
    """Return (pointer_poly_points, pointer_bounds, label_pos, label_bounds) for left/right."""
    mid_y = box.center().y()
    if side == "right":
        tip_x = box.right() + 4
        outer_x = tip_x + 12
        points = [
            qt.QPointF(tip_x, mid_y),
            qt.QPointF(outer_x, mid_y - 8),
            qt.QPointF(outer_x, mid_y + 8),
        ]
        pointer_bounds = qt.QRectF(tip_x, mid_y - 8, outer_x - tip_x, 16)
        label_x = outer_x + 8
        label_y = mid_y - text_h / 2.0
    else:
        tip_x = box.left() - 4
        outer_x = tip_x - 12
        points = [
            qt.QPointF(tip_x, mid_y),
            qt.QPointF(outer_x, mid_y - 8),
            qt.QPointF(outer_x, mid_y + 8),
        ]
        pointer_bounds = qt.QRectF(outer_x, mid_y - 8, tip_x - outer_x, 16)
        label_x = outer_x - text_w - 8
        label_y = mid_y - text_h / 2.0
    label_bounds = qt.QRectF(label_x, label_y, text_w, text_h)
    return points, pointer_bounds, (label_x, label_y), label_bounds


def _pick_diff_annotation_side(box, text_w, text_h, obstacles):
    """Prefer the side where pointer + caption do not cover other nodes."""
    best = None
    for side in ("left", "right"):
        points, pointer_bounds, label_pos, label_bounds = _diff_annotation_layout(
            box, text_w, text_h, side
        )
        score = _annotation_collision_score(
            (pointer_bounds, label_bounds), obstacles
        )
        # Slight preference for left when both are clear (stable reading).
        tie = 0.0 if side == "left" else 0.01
        candidate = (score + tie, side, points, pointer_bounds, label_pos, label_bounds)
        if best is None or candidate[0] < best[0]:
            best = candidate
    return best[1:]


def _draw_diff_region(
    scene,
    positions,
    diff_ids,
    commit_history_by_id=None,
    diff_side="",
    color=None,
    caption_mode="diff",
    result_roles=None,
):
    """Dashed box + pointer + caption per marked node (red diff or green result).

    One box per node. Each has its own arrow and text, placed on the
    left or right so they avoid overlapping other version nodes (and each other).

    Returns a QRectF covering boxes + pointers + captions (for fitInView), or None.
    """
    diff_id_list = [
        node_id for node_id in (diff_ids or ()) if node_id in positions
    ]
    if not diff_id_list:
        return None
    pad = 10
    mark = str(color or COMPARE_DIFF_COLOR)
    pen = qt.QPen(qt.QColor(mark), 2, qt.Qt.DashLine)
    roles = dict(result_roles or {})
    node_obstacles = {}
    for nid, node in positions.items():
        node_obstacles[nid] = qt.QRectF(
            float(node["x"]) - 4,
            float(node["y"]) - 4,
            float(node["w"]) + 8,
            float(node["h"]) + 8,
        )
    placed_annotations = []

    fit = None
    # Top-to-bottom so stacked marks pick free sides consistently.
    ordered = sorted(
        diff_id_list,
        key=lambda nid: (
            float(positions[nid]["y"]),
            float(positions[nid]["x"]),
            str(nid),
        ),
    )
    for node_id in ordered:
        node = positions[node_id]
        x0 = float(node["x"]) - pad
        y0 = float(node["y"]) - pad
        x1 = float(node["x"]) + float(node["w"]) + pad
        y1 = float(node["y"]) + float(node["h"]) + pad
        box = qt.QRectF(x0, y0, x1 - x0, y1 - y0)
        scene.addRect(box, pen, qt.QBrush(qt.Qt.NoBrush))
        fit = box if fit is None else fit.united(box)

        if str(caption_mode or "").strip().lower() == "result":
            role = roles.get(node_id) or diff_side or "shared"
            text = _build_one_result_caption(node_id, commit_history_by_id, role)
        else:
            text = _build_one_diff_caption(node_id, commit_history_by_id, diff_side)
        text_w, text_h = _measure_caption_size(text, font_size=8)
        blockers = [
            rect for nid, rect in node_obstacles.items() if nid != node_id
        ]
        blockers.extend(placed_annotations)
        _side, points, pointer_bounds, label_pos, label_bounds = (
            _pick_diff_annotation_side(box, text_w, text_h, blockers)
        )
        scene.addPolygon(
            qt.QPolygonF(points),
            qt.QPen(qt.QColor(mark), 1),
            qt.QBrush(qt.QColor(mark)),
        )
        fit = fit.united(pointer_bounds)
        if text:
            label = scene.addText(text)
            label.setFont(qt.QFont("Arial", 8))
            label.setDefaultTextColor(qt.QColor(_ui.GRAPH_NODE_TEXT or "#eeeeee"))
            label.setPos(label_pos[0], label_pos[1])
            fit = fit.united(label_bounds)
            placed_annotations.append(pointer_bounds)
            placed_annotations.append(label_bounds.adjusted(-4, -2, 4, 2))
    return fit


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
        self._sync_scene_background()

    def _sync_scene_background(self):
        scene = getattr(self, "_graphe_scene", None)
        if scene is None:
            return
        try:
            role = getattr(qt.QPalette, "Base", None) or getattr(qt.QPalette, "Window", None)
            color = self.palette().color(role)
            scene.setBackgroundBrush(qt.QBrush(color))
        except Exception:
            scene.setBackgroundBrush(qt.QBrush(qt.QColor(_ui.GRAPH_BG)))

    def _pad_scene_rect(self, margin=100):
        rect = self._graphe_scene.sceneRect
        self._graphe_scene.setSceneRect(
            rect.x() - margin,
            rect.y() - margin,
            rect.width() + 2 * margin,
            rect.height() + 2 * margin,
        )

    def reset_view(self):
        # Guard against fitInView ↔ scrollbar ↔ resize feedback loops.
        if getattr(self, "_fitting", False):
            return
        self._fitting = True
        try:
            self.resetTransform()
            self._zoom_level = 1.0
            vp = self.viewport()
            if vp.width <= 0 or vp.height <= 0:
                return
            # Compare-with-shared only: tight fit on nodes (+ pointer caption).
            # Normal Version tree: classic fit on full sceneRect (unchanged).
            if getattr(self, "fit_tight", False):
                rect = getattr(self, "_content_fit_rect", None)
                if rect is None or rect.width() <= 0 or rect.height() <= 0:
                    rect = self._graphe_scene.sceneRect
                if rect.width() <= 0 or rect.height() <= 0:
                    return
                try:
                    rect = rect.adjusted(-28, -28, 28, 28)
                except (AttributeError, TypeError, RuntimeError):
                    pass
                self.fitInView(rect, qt.Qt.KeepAspectRatio)
                return
            rect = self._graphe_scene.sceneRect
            if rect.width() <= 0 or rect.height() <= 0:
                return
            self.fitInView(rect, qt.Qt.KeepAspectRatio)
        finally:
            self._fitting = False

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

        btn_style_hover = _ui.BTN_SECONDARY
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
    """Graphe de versions — clic pour check-out, double-clic pour les details."""

    def __init__(
        self,
        logic,
        version_specs=None,
        graph_title=None,
        graph_description=None,
        active_version_id=None,
        commit_history_by_id=None,
        parent=None,
        read_only=False,
        conflict_ids=None,
        diff_side=None,
        minimum_height=480,
        fit_tight=False,
        pick_mode=False,
    ):
        InteractiveGraphView.__init__(self, parent)
        self.logic = logic
        self.version_specs = version_specs if version_specs is not None else []
        self.graph_title = graph_title or "Version tree"
        self.graph_description = graph_description or ""
        self.active_version_id = active_version_id
        self.commit_history_by_id = dict(commit_history_by_id or {})
        self.read_only = bool(read_only)
        self.pick_mode = bool(pick_mode)
        self.conflict_ids = set(conflict_ids or ())
        # "local" | "shared" — caption wording next to the red diff pointer
        self.diff_side = str(diff_side or "").strip().lower()
        # Result preview: green dashed marks (id -> "shared" | "local")
        self.result_ids = set()
        self.result_roles = {}
        self.fit_tight = bool(fit_tight)
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
        self.setStyleSheet("background-color: palette(base); border: none;")
        self.setMinimumHeight(int(minimum_height) if minimum_height else 480)
        try:
            self.setSizePolicy(qt.QSizePolicy.Expanding, qt.QSizePolicy.Expanding)
        except (AttributeError, TypeError, RuntimeError):
            pass
        self._setup_interaction()
        self.draw()
        # Compare views: less empty pad so fitInView can zoom in more.
        self._pad_scene_rect(margin=36 if self.fit_tight else 100)
        self.reset_view()

    def sizeHint(self):
        # Compare dialogs: do not advertise scene size (huge graphs blow the window off-screen).
        if getattr(self, "fit_tight", False):
            min_h = max(int(self.minimumHeight() or 0), 200)
            min_w = max(int(self.minimumWidth() or 0), 320)
            return qt.QSize(min_w, min_h)
        try:
            return InteractiveGraphView.sizeHint(self)
        except (AttributeError, TypeError, RuntimeError):
            return qt.QSize(640, 480)

    def minimumSizeHint(self):
        if getattr(self, "fit_tight", False):
            min_h = max(int(self.minimumHeight() or 0), 160)
            min_w = max(int(self.minimumWidth() or 0), 240)
            return qt.QSize(min_w, min_h)
        try:
            return InteractiveGraphView.minimumSizeHint(self)
        except (AttributeError, TypeError, RuntimeError):
            return qt.QSize(240, 160)

    def set_active_version_id(self, version_id):
        if version_id == self.active_version_id:
            return
        self.active_version_id = version_id
        self.draw()
        self._pad_scene_rect()

    def set_compare_content(
        self,
        version_specs=None,
        graph_title=None,
        graph_description=None,
        active_version_id=None,
        commit_history_by_id=None,
        conflict_ids=None,
        diff_side=None,
        result_ids=None,
        result_roles=None,
    ):
        """Replace graph contents (used by the compare result preview)."""
        if version_specs is not None:
            self.version_specs = list(version_specs)
            self._specs_by_id = {spec["id"]: spec for spec in self.version_specs}
        if graph_title is not None:
            self.graph_title = graph_title
        if graph_description is not None:
            self.graph_description = graph_description
        if active_version_id is not None:
            self.active_version_id = active_version_id
        if commit_history_by_id is not None:
            self.commit_history_by_id = dict(commit_history_by_id)
        if conflict_ids is not None:
            self.conflict_ids = set(conflict_ids)
        if diff_side is not None:
            self.diff_side = str(diff_side or "").strip().lower()
        if result_ids is not None:
            self.result_ids = set(result_ids or ())
        if result_roles is not None:
            self.result_roles = dict(result_roles or {})
        self.draw()
        self._pad_scene_rect()
        self.reset_view()

    def create_toolbar(self):
        if self.pick_mode:
            hint = qt.QLabel("Click a node to set the task start version")
        elif self.read_only:
            hint = qt.QLabel("Read-only · Double-click for details")
        else:
            hint = qt.QLabel("Click a node to check out · Double-click for details")
        hint.setStyleSheet("color: %s; font-size: 10px;" % _ui.GRAPH_HINT)
        return InteractiveGraphView.create_toolbar(self, leading_widgets=[hint])

    def _show_version_info(self, node_id):
        spec = self._specs_by_id.get(node_id)
        if not spec:
            return
        history = self.commit_history_by_id.get(node_id, {})
        actions = {} if self.read_only else self._review_actions(spec, history)
        dialog = _VersionInfoDialog(
            self,
            spec,
            history,
            actions=actions,
        )
        if dialog.exec_() != qt.QDialog.Accepted or not dialog.chosen:
            return
        if self.read_only:
            return
        if hasattr(self.logic, "onVersionReviewAction"):
            self.logic.onVersionReviewAction(dialog.chosen, spec)

    def _review_actions(self, spec, history):
        if not hasattr(self.logic, "reviewActionsForVersion"):
            return {}
        try:
            actions = self.logic.reviewActionsForVersion(spec, history or {})
        except Exception:
            return {}
        return actions if isinstance(actions, dict) else {}

    def _on_single_click_timeout(self):
        node_id = self._pending_node_id
        self._pending_node_id = None
        if not node_id:
            return
        if self.pick_mode:
            if hasattr(self.logic, "onVersionPickedForTask"):
                self.logic.onVersionPickedForTask(node_id)
            return
        if self.read_only:
            return
        if hasattr(self.logic, "onVersionCheckedOut"):
            self.logic.onVersionCheckedOut(node_id)

    def showEvent(self, event):
        qt.QGraphicsView.showEvent(self, event)
        if getattr(self, "fit_tight", False):
            # Compare dialog: one deferred fit after layout.
            try:
                qt.QTimer.singleShot(0, self.reset_view)
            except (AttributeError, TypeError, RuntimeError):
                self.reset_view()
            return
        self.reset_view()

    def _node_at_scene_pos(self, scene_pos):
        return _node_id_at_scene_pos(self._nodes_by_id, scene_pos)

    def mousePressEvent(self, event):
        if event.button() == qt.Qt.LeftButton:
            scene_pos = self.mapToScene(_qt_event_pos(event))
            node_id = self._node_at_scene_pos(scene_pos)
            if node_id:
                if self.read_only and not self.pick_mode:
                    event.accept()
                    return
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
                if self.pick_mode:
                    # In pick mode a double-click also selects the start version.
                    if hasattr(self.logic, "onVersionPickedForTask"):
                        self.logic.onVersionPickedForTask(node_id)
                    event.accept()
                    return
                self._show_version_info(node_id)
                event.accept()
                return
        qt.QGraphicsView.mouseDoubleClickEvent(self, event)

    def draw(self):
        self._sync_scene_background()
        self._graphe_scene.clear()
        if not self.version_specs:
            hint = self._graphe_scene.addText("No versions to display.")
            hint.setDefaultTextColor(qt.QColor(_ui.GRAPH_HINT))
            hint.setPos(MARGIN, MARGIN)
            self._graphe_scene.setSceneRect(0, 0, 400, 200)
            self._nodes_by_id = {}
            self._content_fit_rect = None
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
            edge_color = _branch_color(branch)
            _draw_tree_edge(
                self._graphe_scene,
                nodes_by_id[parent_id],
                nodes_by_id[child_id],
                color=edge_color,
                width=2,
            )

        any_unshared = False
        for node in nodes_by_id.values():
            unshared = _node_is_unshared(node["id"], self.commit_history_by_id)
            node["unshared"] = unshared
            if unshared:
                any_unshared = True
            _draw_version_box_node(self._graphe_scene, node, font_size=7)

        if self.fit_tight:
            # Compare-with-shared: center nodes; include pointer caption via symmetric pad.
            max_x = max(node["x"] + node["w"] for node in nodes_by_id.values())
            max_y = max(node["y"] + node["h"] for node in nodes_by_id.values())
            min_x = min(node["x"] for node in nodes_by_id.values())
            min_y = min(node["y"] for node in nodes_by_id.values())
            node_rect = qt.QRectF(min_x, min_y, max_x - min_x, max_y - min_y)
            self._content_fit_rect = qt.QRectF(node_rect)
            # Compare dialog: dashed boxes stay; share-status legend only on Version tree.

            diff_bounds = None
            if self.result_ids:
                diff_bounds = _draw_diff_region(
                    self._graphe_scene,
                    nodes_by_id,
                    self.result_ids,
                    commit_history_by_id=self.commit_history_by_id,
                    diff_side="shared",
                    color=COMPARE_RESULT_COLOR,
                    caption_mode="result",
                    result_roles=self.result_roles,
                )
            elif self.conflict_ids:
                diff_bounds = _draw_diff_region(
                    self._graphe_scene,
                    nodes_by_id,
                    self.conflict_ids,
                    commit_history_by_id=self.commit_history_by_id,
                    diff_side=self.diff_side,
                )
            elif self.active_version_id and self.active_version_id in nodes_by_id:
                _draw_checkout_pointer(
                    self._graphe_scene, nodes_by_id[self.active_version_id]
                )

            if diff_bounds is not None:
                left_extra = max(0.0, node_rect.left() - diff_bounds.left())
                right_extra = max(0.0, diff_bounds.right() - node_rect.right())
                top_extra = max(0.0, node_rect.top() - diff_bounds.top())
                bottom_extra = max(0.0, diff_bounds.bottom() - node_rect.bottom())
                h_pad = max(left_extra, right_extra)
                v_pad = max(top_extra, bottom_extra)
                self._content_fit_rect = node_rect.adjusted(
                    -h_pad, -v_pad, h_pad, v_pad
                )

            fit = self._content_fit_rect
            scene_left = min(0.0, fit.left() - 20)
            scene_top = min(0.0, fit.top() - 20)
            scene_right = max(940.0, max_x + MARGIN + 40.0, fit.right() + 20)
            scene_bottom = max(max_y + 40.0, fit.bottom() + 20)
            self._graphe_scene.setSceneRect(
                scene_left,
                scene_top,
                scene_right - scene_left,
                scene_bottom - scene_top,
            )
            return

        # Normal Version tree — classic layout (no auto enlarge / special centering).
        self._content_fit_rect = None
        if self.result_ids:
            _draw_diff_region(
                self._graphe_scene,
                nodes_by_id,
                self.result_ids,
                commit_history_by_id=self.commit_history_by_id,
                diff_side="shared",
                color=COMPARE_RESULT_COLOR,
                caption_mode="result",
                result_roles=self.result_roles,
            )
        elif self.conflict_ids:
            _draw_diff_region(
                self._graphe_scene,
                nodes_by_id,
                self.conflict_ids,
                commit_history_by_id=self.commit_history_by_id,
                diff_side=self.diff_side,
            )
        elif self.active_version_id and self.active_version_id in nodes_by_id:
            _draw_checkout_pointer(
                self._graphe_scene, nodes_by_id[self.active_version_id]
            )

        max_x = max(node["x"] + node["w"] for node in nodes_by_id.values())
        max_y = max(node["y"] for node in nodes_by_id.values())
        scene_w = max(940, max_x + MARGIN + 40)
        scene_h = max_y + NODE_H + 40
        footer_h = 28
        if any_unshared:
            footer_h = 48
        self._graphe_scene.setSceneRect(0, 0, scene_w, scene_h + footer_h)

        title_text = "%s — %d version(s)" % (
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
        title.setDefaultTextColor(qt.QColor(_ui.GRAPH_TITLE))
        title.setPos(MARGIN, scene_h + 4)
        if any_unshared:
            _draw_share_status_legend(self._graphe_scene, MARGIN, scene_h + 22)


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

    def __init__(self, parent, spec, history=None, actions=None):
        qt.QDialog.__init__(self, parent)
        self.setWindowTitle("Version details")
        self.setMinimumWidth(440)
        self.chosen = ""
        layout = qt.QVBoxLayout(self)
        form = qt.QFormLayout()

        def add_row(title, value):
            label = qt.QLabel(value or "—")
            label.setWordWrap(True)
            label.setTextInteractionFlags(qt.Qt.TextSelectableByMouse)
            form.addRow(title, label)

        history = history or {}
        message = history.get("message") or spec.get("label", "")

        add_row("Version:", str(spec.get("tag", "")))
        line = spec.get("branch") or ""
        add_row("Branch:", "main" if line == "main" else str(line))
        add_row("Message:", message)
        add_row("Date:", history.get("date", ""))
        add_row("Author:", history.get("author", ""))
        add_row("Status:", history.get("status", ""))
        add_row("Parent:", str(spec.get("parent") or "—"))
        if spec.get("merge"):
            merge_from = spec.get("merge_from") or []
            add_row("Merge from:", ", ".join(merge_from) if merge_from else "—")
            add_row("Merge into:", str(spec.get("parent") or "—"))
        task_text = str((actions or {}).get("task_text") or "").strip()
        task_senior = str((actions or {}).get("task_senior") or "").strip()
        if task_text:
            shown = ("%s: %s" % (task_senior, task_text)) if task_senior else task_text
            task_label = qt.QLabel(shown)
            task_label.setWordWrap(True)
            task_label.setFixedWidth(300)
            task_label.setTextInteractionFlags(qt.Qt.TextSelectableByMouse)
            form.addRow("Task:", task_label)

        layout.addLayout(form)

        allowed = actions or {}
        has_action = bool(
            allowed.get("submit")
            or allowed.get("merge")
            or allowed.get("accept")
            or allowed.get("decline")
        )
        if has_action:
            actions_row = qt.QHBoxLayout()
            actions_row.setSpacing(16)
            actions_row.addStretch(1)

            def add_action(label, handler, style):
                button = qt.QPushButton(label)
                button.setMinimumWidth(120)
                button.setMinimumHeight(32)
                if style:
                    button.setStyleSheet(style)
                button.connect("clicked()", handler)
                actions_row.addWidget(button)

            if allowed.get("submit"):
                add_action("Request review", self._chooseSubmit, _ui.BTN_CREATE)
            if allowed.get("merge"):
                add_action("Merge", self._chooseMerge, _ui.BTN_CREATE)
            if allowed.get("accept"):
                add_action("Accept", self._chooseAccept, _ui.BTN_CREATE)
            if allowed.get("decline"):
                add_action("Decline", self._chooseDecline, _ui.BTN_DELETE)
            layout.addSpacing(14)
            layout.addLayout(actions_row)

        layout.addSpacing(10)
        close_row = qt.QHBoxLayout()
        close_row.addStretch(1)
        close_btn = qt.QPushButton("Close")
        close_btn.setMinimumWidth(120)
        close_btn.setMinimumHeight(32)
        close_btn.setStyleSheet(_ui.BTN_SECONDARY)
        close_btn.connect("clicked()", self.reject)
        close_row.addWidget(close_btn)
        layout.addLayout(close_row)

    def _chooseSubmit(self):
        self._choose("submit")

    def _chooseMerge(self):
        self._choose("merge")

    def _chooseAccept(self):
        self._choose("accept")

    def _chooseDecline(self):
        self._choose("decline")

    def _choose(self, name):
        self.chosen = name
        self.accept()


COVERAGE_HELP_TEXT = """Left mark (top-left corner)
A filled mint circle means this structure has an annotation in Slicer (a region named Segment_ID, for example Segment_64).
The annotation may still be empty: the region exists, but nothing may have been painted yet.
An empty circle means this structure has no annotation.

Right mark (top-right corner)
Shown on parent structures only. Lowest-level structures have no right mark.
• Indigo, filled: every lowest-level structure under this one has an annotation.
• Amber, filled: some, but not all, of those structures have an annotation.
• Empty circle: none of the structures under this one have an annotation.

The two marks are independent. A parent can have an annotation of its own (left filled) while only some children do (right amber).
"""


class _CoverageHelpDialog(qt.QDialog):
    """Explains the left/right coverage marks on the anatomy tree."""

    def __init__(self, parent=None):
        qt.QDialog.__init__(self, parent)
        self.setWindowTitle("Anatomy tree marks")
        self.setMinimumSize(520, 380)
        layout = qt.QVBoxLayout(self)
        body = qt.QTextEdit()
        body.setReadOnly(True)
        body.setPlainText(COVERAGE_HELP_TEXT.strip())
        body.setStyleSheet("font-size: 12px;")
        layout.addWidget(body, 1)
        close_btn = qt.QPushButton("Close")
        close_btn.connect("clicked()", self.accept)
        row = qt.QHBoxLayout()
        row.addStretch(1)
        row.addWidget(close_btn)
        layout.addLayout(row)


class _StructureInfoDialog(qt.QDialog):
    """Read-only details for a dependency graph node."""

    def __init__(self, parent, spec, coverage=None):
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
        coverage = coverage or {}
        add_row("Left mark:", _coverage_self_label(bool(coverage.get("self"))) if coverage else "—")
        add_row("Right mark:", _coverage_children_label(coverage.get("children")) if coverage else "—")
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
        painted_ids=None,
        parent=None,
    ):
        InteractiveGraphView.__init__(self, parent)
        self.logic = logic
        self._all_specs = list(dependency_specs or [])
        self.dependency_specs = self._all_specs
        self.graph_title = graph_title or "Project ontology"
        self.graph_description = graph_description or ""
        self._painted_ids = {_ontology_id_key(item) for item in (painted_ids or [])}
        self._coverage_ready = painted_ids is not None
        self._coverage_map = {}
        self._coverageLegendLeft = None
        self._coverageLegendRight = None
        self._coverageCount = None
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
        self.setStyleSheet("background-color: palette(base); border: none;")
        self.setMinimumHeight(480)
        self._setup_interaction()
        self.draw()
        self._pad_scene_rect()
        self.reset_view()

    def set_specs(self, dependency_specs, graph_title=None, graph_description=None, painted_ids=None, preserve_expansion=False):
        previous_expanded = set(getattr(self, "_expanded_ids", set()) or set())
        self._all_specs = list(dependency_specs or [])
        self.dependency_specs = self._all_specs
        self._full_children_map = _build_children_map(self._all_specs)
        if preserve_expansion and previous_expanded:
            valid_ids = {spec["id"] for spec in self._all_specs}
            kept = previous_expanded.intersection(valid_ids)
            self._expanded_ids = kept or _default_expanded_ids(self._all_specs)
        else:
            self._expanded_ids = _default_expanded_ids(self._all_specs)
        if graph_title is not None:
            self.graph_title = graph_title
        if graph_description is not None:
            self.graph_description = graph_description
        if painted_ids is not None:
            self._painted_ids = {_ontology_id_key(item) for item in painted_ids}
            self._coverage_ready = True
        self.draw()
        self._pad_scene_rect()
        if not preserve_expansion:
            self.reset_view()

    def set_painted_ids(self, painted_ids):
        normalized = {_ontology_id_key(item) for item in (painted_ids or [])}
        if self._coverage_ready and normalized == self._painted_ids:
            return
        self._painted_ids = normalized
        self._coverage_ready = True
        self.draw()
        self._pad_scene_rect()

    def create_toolbar(self):
        hint = qt.QLabel("Click parent to expand/collapse · Double-click for details")
        hint.setStyleSheet("color: %s; font-size: 10px;" % _ui.GRAPH_HINT)
        btn_collapse = qt.QPushButton("Collapse all")
        btn_collapse.setToolTip("Show only the root level again.")
        btn_collapse.connect("clicked()", self._collapse_all)
        return InteractiveGraphView.create_toolbar(
            self,
            leading_widgets=[hint, btn_collapse],
        )

    def create_legend_bar(self):
        self._coverageLegendLeft = qt.QLabel()
        self._coverageLegendLeft.setTextFormat(qt.Qt.RichText)
        self._coverageLegendLeft.setWordWrap(True)
        self._coverageLegendLeft.setStyleSheet("font-size: 10px;")
        self._coverageLegendRight = qt.QLabel()
        self._coverageLegendRight.setTextFormat(qt.Qt.RichText)
        self._coverageLegendRight.setWordWrap(True)
        self._coverageLegendRight.setStyleSheet("font-size: 10px;")
        self._coverageCount = qt.QLabel()
        self._coverageCount.setStyleSheet("color: %s; font-size: 10px;" % _ui.GRAPH_HINT)
        self._coverageCount.setAlignment(qt.Qt.AlignRight | qt.Qt.AlignVCenter)
        help_btn = qt.QPushButton("?")
        help_btn.setToolTip("What the left and right marks mean")
        help_btn.setStyleSheet(_ui.BTN_SECONDARY)
        help_btn.setFixedSize(24, 24)
        help_btn.connect("clicked()", self._show_coverage_help)
        legend_row = qt.QWidget()
        legend_layout = qt.QHBoxLayout(legend_row)
        legend_layout.setContentsMargins(0, 8, 0, 0)
        legend_layout.setSpacing(16)
        legend_layout.addWidget(self._coverageLegendLeft, 1)
        legend_layout.addWidget(self._coverageLegendRight, 1)
        legend_layout.addWidget(help_btn, 0, qt.Qt.AlignTop)
        legend_layout.addWidget(self._coverageCount, 0, qt.Qt.AlignTop)
        self._refresh_coverage_legend()
        return legend_row

    def _show_coverage_help(self):
        dialog = _CoverageHelpDialog(self)
        dialog.exec_()

    def _coverage_legend_html(self):
        mint = _ui.ACCENT_MINT
        indigo = _ui.ACCENT_INDIGO
        amber = _ui.ACCENT_AMBER
        muted = _ui.TEXT_MUTED
        left = (
            "<b>Left mark</b><br>"
            '<span style="color:%s">●</span> Has an annotation&nbsp;&nbsp;'
            '<span style="color:%s">○</span> No annotation'
        ) % (mint, muted)
        right = (
            "<b>Right mark</b><br>"
            '<span style="color:%s">●</span> All have an annotation&nbsp;&nbsp;'
            '<span style="color:%s">●</span> Some have an annotation&nbsp;&nbsp;'
            '<span style="color:%s">○</span> None have an annotation'
        ) % (indigo, amber, muted)
        return left, right

    def _refresh_coverage_legend(self):
        left_label = getattr(self, "_coverageLegendLeft", None)
        right_label = getattr(self, "_coverageLegendRight", None)
        count_label = getattr(self, "_coverageCount", None)
        left_html, right_html = self._coverage_legend_html()
        if left_label is not None:
            try:
                left_label.setText(left_html)
            except (RuntimeError, ValueError):
                pass
        if right_label is not None:
            try:
                right_label.setText(right_html)
            except (RuntimeError, ValueError):
                pass
        if count_label is None:
            return
        try:
            if not self._coverage_ready:
                count_label.setText("Reading annotation…")
                return
            annotated, total = _leaf_annotation_counts(self._all_specs, self._coverage_map)
            if total:
                count_label.setText(
                    "Lowest-level structures: %d / %d with an annotation" % (annotated, total)
                )
            else:
                count_label.setText("")
        except (RuntimeError, ValueError):
            pass

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
        dialog = _StructureInfoDialog(
            self,
            spec,
            coverage=(
                self._coverage_map.get(node_id) if getattr(self, "_coverage_ready", False) else None
            ),
        )
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
        self._sync_scene_background()
        self._graphe_scene.clear()
        if not self._all_specs:
            hint = self._graphe_scene.addText("No ontology loaded.")
            hint.setDefaultTextColor(qt.QColor(_ui.GRAPH_HINT))
            hint.setPos(MARGIN, MARGIN)
            self._graphe_scene.setSceneRect(0, 0, 400, 200)
            self._nodes_by_id = {}
            self._specs_by_id = {}
            self._coverage_map = {}
            self._refresh_coverage_legend()
            return

        visible_specs, _children_map = _visible_specs_from_expansion(
            self._all_specs,
            self._expanded_ids,
        )
        self.dependency_specs = visible_specs
        if not visible_specs:
            hint = self._graphe_scene.addText("No structures to display.")
            hint.setDefaultTextColor(qt.QColor(_ui.GRAPH_HINT))
            hint.setPos(MARGIN, MARGIN)
            self._graphe_scene.setSceneRect(0, 0, 400, 200)
            self._coverage_map = _coverage_by_id(self._all_specs, self._painted_ids)
            self._refresh_coverage_legend()
            return

        positions, edges = _layout_hierarchy(
            visible_specs,
            expanded_ids=self._expanded_ids,
            full_children_map=self._full_children_map,
            h_gap=DEPENDENCY_H_GAP,
            v_gap=DEPENDENCY_V_GAP,
        )
        self._coverage_map = _coverage_by_id(self._all_specs, self._painted_ids)
        nodes_by_id = positions
        self._nodes_by_id = nodes_by_id
        self._specs_by_id = {spec["id"]: spec for spec in visible_specs}

        for parent_id, child_id in edges:
            if parent_id in nodes_by_id and child_id in nodes_by_id:
                _draw_ontology_edge(self._graphe_scene, nodes_by_id[parent_id], nodes_by_id[child_id])

        for node in nodes_by_id.values():
            coverage = None
            if self._coverage_ready:
                coverage = self._coverage_map.get(node["id"])
            _draw_box_node(self._graphe_scene, node, coverage=coverage)

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
        title.setDefaultTextColor(qt.QColor(_ui.GRAPH_TITLE))
        title.setPos(MARGIN, scene_h + 4)
        self._refresh_coverage_legend()
