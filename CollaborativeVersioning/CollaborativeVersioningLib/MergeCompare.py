"""Side-by-side Merge Compare layout + control bar (inspired by CrossSegmentationExplorer)."""
from __future__ import annotations

import html

import qt
import slicer

from CollaborativeVersioningLib.UiStyles import (
    ACCENT_ICE,
    ACCENT_ICE_HOVER,
    ACCENT_INDIGO,
    ACCENT_INDIGO_HOVER,
    ACCENT_MINT,
    ACCENT_RED,
    BTN_DELETE,
    TEXT_MUTED,
    TEXT_ON_ICE,
)

# Layout: both 3D views on top; each version's Axial|Sagittal|Coronal below.
TARGET_3D_TAG = "CVCmpT"
SOURCE_3D_TAG = "CVCmpS"
TARGET_SLICE_TAGS = ("R CVCmpT", "G CVCmpT", "Y CVCmpT")
SOURCE_SLICE_TAGS = ("R CVCmpS", "G CVCmpS", "Y CVCmpS")
_ORIENT = ("Axial", "Sagittal", "Coronal")
_COLORS = ("#F34A33", "#4AF333", "#F3E833")

# Forced Compare review colors (one segment at a time). RGB 0..1.
COMPARE_COLOR_TARGET = (0.20, 0.85, 0.35)  # green = target / upper
COMPARE_COLOR_SOURCE = (0.95, 0.22, 0.18)  # red = source / lower


def _slice_views_xml(slice_tags: tuple[str, ...], prefix: str) -> list[str]:
    parts = ['    <layout type="horizontal" split="true">']
    for tag, orient, color in zip(slice_tags, _ORIENT, _COLORS):
        short = {"Axial": "Ax", "Sagittal": "Sg", "Coronal": "Co"}[orient]
        label = "%s %s" % (prefix, short)
        parts.append(
            "      <item><view class=\"vtkMRMLSliceNode\" singletontag=\"%s\">\n"
            "        <property name=\"orientation\" action=\"default\">%s</property>\n"
            "        <property name=\"viewlabel\" action=\"default\">%s</property>\n"
            "        <property name=\"viewcolor\" action=\"default\">%s</property>\n"
            "      </view></item>"
            % (tag, orient, label, color)
        )
    parts.append("    </layout>")
    return parts


def layout_xml(target_label: str, source_label: str) -> str:
    """Top: target 3D | source 3D. Then target 2Ds, then source 2Ds (stacked)."""
    top = str(target_label or "target").strip() or "target"
    bottom = str(source_label or "source").strip() or "source"
    parts = ['<layout type="vertical" split="true">']
    # 1) Both 3D views side by side.
    parts.append("  <item>")
    parts.append('    <layout type="horizontal" split="true">')
    parts.append(
        "      <item><view class=\"vtkMRMLViewNode\" singletontag=\"%s\">\n"
        "        <property name=\"viewlabel\" action=\"default\">%s 3D</property>\n"
        "      </view></item>"
        % (TARGET_3D_TAG, top)
    )
    parts.append(
        "      <item><view class=\"vtkMRMLViewNode\" singletontag=\"%s\">\n"
        "        <property name=\"viewlabel\" action=\"default\">%s 3D</property>\n"
        "      </view></item>"
        % (SOURCE_3D_TAG, bottom)
    )
    parts.append("    </layout>")
    parts.append("  </item>")
    # 2) Target orthogonal slices.
    parts.append("  <item>")
    parts.extend(_slice_views_xml(TARGET_SLICE_TAGS, top))
    parts.append("  </item>")
    # 3) Source orthogonal slices (below target).
    parts.append("  <item>")
    parts.extend(_slice_views_xml(SOURCE_SLICE_TAGS, bottom))
    parts.append("  </item>")
    parts.append("</layout>")
    return "\n".join(parts)


def apply_compare_layout(target_label: str, source_label: str) -> int:
    """Install compare layout; return previous view arrangement id."""
    layout_node = slicer.app.layoutManager().layoutLogic().GetLayoutNode()
    previous = int(layout_node.GetViewArrangement())
    xml_code = layout_xml(target_label, source_label)
    user_view = layout_node.SlicerLayoutUserView
    if layout_node.IsLayoutDescription(user_view):
        layout_node.SetLayoutDescription(user_view, xml_code)
    else:
        layout_node.AddLayoutDescription(user_view, xml_code)
    layout_node.SetViewArrangement(user_view)
    return previous


def restore_layout(previous_arrangement: int | None) -> None:
    if previous_arrangement is None:
        return
    try:
        layout_node = slicer.app.layoutManager().layoutLogic().GetLayoutNode()
        layout_node.SetViewArrangement(int(previous_arrangement))
    except Exception:
        pass


def _nodes_by_class(class_name: str):
    """``getNodesByClass`` returns a dict in Slicer — iterate values, not keys."""
    nodes = slicer.util.getNodesByClass(class_name)
    if isinstance(nodes, dict):
        return list(nodes.values())
    if isinstance(nodes, (list, tuple)):
        return list(nodes)
    return []


def set_linked_2d(enabled: bool) -> None:
    for composite in _nodes_by_class("vtkMRMLSliceCompositeNode"):
        try:
            composite.SetLinkedControl(bool(enabled))
        except Exception:
            pass


def set_linked_3d(enabled: bool) -> None:
    layout = slicer.app.layoutManager()
    for index in range(int(layout.threeDViewCount)):
        try:
            layout.threeDWidget(index).threeDView().mrmlViewNode().SetLinkedControl(
                bool(enabled)
            )
        except Exception:
            pass


def _three_d_view_node(tag: str):
    """Find a 3D view node by singleton tag / name."""
    want = str(tag or "").strip()
    if not want:
        return None
    layout = slicer.app.layoutManager()
    try:
        widget = layout.threeDWidget(want)
        if widget is not None:
            return widget.threeDView().mrmlViewNode()
    except Exception:
        pass
    for index in range(int(layout.threeDViewCount)):
        try:
            view_node = layout.threeDWidget(index).threeDView().mrmlViewNode()
        except Exception:
            continue
        if view_node is None:
            continue
        name = str(view_node.GetName() or "")
        singleton = ""
        getter = getattr(view_node, "GetSingletonTag", None)
        if callable(getter):
            try:
                singleton = str(getter() or "")
            except Exception:
                singleton = ""
        if name == want or singleton == want:
            return view_node
    return None


def _clear_segmentation_views(segmentation_node) -> None:
    if segmentation_node is None or not hasattr(segmentation_node, "GetDisplayNode"):
        return
    try:
        segmentation_node.CreateDefaultDisplayNodes()
    except Exception:
        pass
    display = segmentation_node.GetDisplayNode()
    if display is None:
        return
    try:
        display.RemoveAllViewNodeIDs()
    except Exception:
        pass
    # Empty ViewNodeIDs = show in ALL views — force off.
    try:
        display.SetVisibility(False)
    except Exception:
        pass
    try:
        display.SetVisibility2D(False)
    except Exception:
        pass
    try:
        display.SetVisibility3D(False)
    except Exception:
        pass


def hide_all_scene_segmentations() -> None:
    """Hide every segmentation overlay (volume-only compare start)."""
    for node in _nodes_by_class("vtkMRMLSegmentationNode"):
        _clear_segmentation_views(node)


def _set_compare_background_volume(volume_node, *, clear_overlays: bool = False) -> None:
    """Set the shared volume on all compare slice views."""
    layout = slicer.app.layoutManager()
    volume_id = volume_node.GetID() if volume_node is not None else ""
    for tag in TARGET_SLICE_TAGS + SOURCE_SLICE_TAGS:
        widget = layout.sliceWidget(tag)
        if widget is None:
            continue
        try:
            composite = widget.sliceLogic().GetSliceCompositeNode()
            if volume_id:
                composite.SetBackgroundVolumeID(volume_id)
            if clear_overlays:
                try:
                    composite.SetLabelVolumeID("")
                except Exception:
                    pass
                try:
                    composite.SetForegroundVolumeID("")
                except Exception:
                    pass
            widget.sliceController().fitSliceToBackground()
        except Exception:
            pass


def reset_compare_slice_views() -> None:
    """Clear backgrounds/overlays on compare slice singletons (they survive layout changes)."""
    layout = slicer.app.layoutManager()
    for tag in TARGET_SLICE_TAGS + SOURCE_SLICE_TAGS:
        widget = layout.sliceWidget(tag)
        if widget is None:
            continue
        try:
            composite = widget.sliceLogic().GetSliceCompositeNode()
            composite.SetBackgroundVolumeID("")
            try:
                composite.SetForegroundVolumeID("")
            except Exception:
                pass
            try:
                composite.SetLabelVolumeID("")
            except Exception:
                pass
        except Exception:
            continue


def assign_volume_only(volume_node) -> None:
    """Compare views: background volume only, no segmentation overlays."""
    _set_compare_background_volume(volume_node, clear_overlays=True)
    hide_all_scene_segmentations()
    set_linked_2d(True)
    set_linked_3d(True)


def _assign_segmentation_to_row(
    segmentation_node,
    slice_tags: tuple[str, ...],
    threed_tag: str,
    *,
    show_3d: bool = False,
    reveal: bool = False,
) -> None:
    """Bind this seg to its 2D (+ 3D) views; keep hidden until Prev/Next focus unless reveal."""
    if segmentation_node is None:
        return
    try:
        segmentation_node.CreateDefaultDisplayNodes()
    except Exception:
        pass
    display = segmentation_node.GetDisplayNode()
    if display is None:
        return
    layout = slicer.app.layoutManager()
    view_ids = []
    for tag in slice_tags:
        widget = layout.sliceWidget(tag)
        if widget is None:
            continue
        view_node = widget.mrmlSliceNode()
        if view_node is not None:
            view_ids.append(view_node.GetID())
    threed = _three_d_view_node(threed_tag)
    if threed is not None:
        view_ids.append(threed.GetID())
    try:
        display.RemoveAllViewNodeIDs()
    except Exception:
        pass
    for view_id in view_ids:
        display.AddViewNodeID(view_id)
    # Never flash the full labelmap: start with every segment off.
    try:
        display.SetAllSegmentsVisibility(False)
    except Exception:
        pass
    display.SetVisibility2DFill(True)
    display.SetVisibility2DOutline(True)
    display.SetOpacity2DFill(0.5)
    display.SetOpacity2DOutline(0.5)
    try:
        display.SetVisibility2D(True)
    except Exception:
        pass
    try:
        display.SetVisibility3D(bool(show_3d) if reveal else False)
    except Exception:
        pass
    if show_3d and reveal:
        try:
            segmentation_node.CreateClosedSurfaceRepresentation()
        except Exception:
            pass
    display.SetVisibility(bool(reveal))


def assign_volume_and_segmentations(
    volume_node,
    target_segmentation,
    source_segmentation,
    *,
    show_3d: bool = False,
    reveal: bool = False,
) -> None:
    """Bind volume + segs to compare views. reveal=False avoids a full-seg flash."""
    try:
        slicer.app.processEvents()
    except Exception:
        pass
    _set_compare_background_volume(volume_node, clear_overlays=False)
    _assign_segmentation_to_row(
        target_segmentation,
        TARGET_SLICE_TAGS,
        TARGET_3D_TAG,
        show_3d=show_3d,
        reveal=reveal,
    )
    _assign_segmentation_to_row(
        source_segmentation,
        SOURCE_SLICE_TAGS,
        SOURCE_3D_TAG,
        show_3d=show_3d,
        reveal=reveal,
    )
    set_linked_2d(True)
    set_linked_3d(True)


def set_segmentations_show_3d(target_segmentation, source_segmentation, enabled: bool) -> None:
    """Toggle 3D segment render (closed surface only when enabling)."""
    enabled = bool(enabled)
    for node in (target_segmentation, source_segmentation):
        if node is None:
            continue
        try:
            node.CreateDefaultDisplayNodes()
        except Exception:
            pass
        display = node.GetDisplayNode()
        if display is None:
            continue
        if enabled:
            try:
                node.CreateClosedSurfaceRepresentation()
            except Exception:
                pass
        try:
            display.SetVisibility3D(enabled)
        except Exception:
            pass


def segment_names(segmentation_node) -> list[str]:
    names: list[str] = []
    if segmentation_node is None:
        return names
    segmentation = segmentation_node.GetSegmentation()
    if segmentation is None:
        return names
    for index in range(int(segmentation.GetNumberOfSegments())):
        segment_id = segmentation.GetNthSegmentID(index)
        segment = segmentation.GetSegment(segment_id)
        if segment is None:
            continue
        name = (segment.GetName() or "").strip()
        if name:
            names.append(name)
    return names


def union_segment_names(target_node, source_node) -> list[str]:
    return [
        row["name"]
        for row in segment_presence_rows(target_node, source_node, "", "")
    ]


def segment_presence_rows(
    target_node,
    source_node,
    target_label: str,
    source_label: str,
) -> list[dict]:
    """Union of segment names with presence status for the Compare list."""
    target_set = {n.lower(): n for n in segment_names(target_node)}
    source_set = {n.lower(): n for n in segment_names(source_node)}

    def _sort_key(key: str):
        name = str(target_set.get(key) or source_set.get(key) or key).strip()
        if name.isdigit():
            return (0, int(name))
        return (1, name.lower())

    keys = sorted(set(target_set) | set(source_set), key=_sort_key)
    top = str(target_label or "target").strip() or "target"
    bottom = str(source_label or "source").strip() or "source"
    rows: list[dict] = []
    for key in keys:
        in_target = key in target_set
        in_source = key in source_set
        name = target_set.get(key) or source_set.get(key) or key
        if in_target and in_source:
            status = "both"
        elif in_target:
            status = "%s only" % top
        else:
            status = "%s only" % bottom
        rows.append(
            {
                "name": name,
                "status": status,
                "in_target": in_target,
                "in_source": in_source,
            }
        )
    return rows


def _find_segment_id_by_name(segmentation_node, name: str) -> str:
    want = str(name or "").strip().lower()
    if not want or segmentation_node is None:
        return ""
    segmentation = segmentation_node.GetSegmentation()
    if segmentation is None:
        return ""
    for index in range(int(segmentation.GetNumberOfSegments())):
        segment_id = segmentation.GetNthSegmentID(index)
        segment = segmentation.GetSegment(segment_id)
        if segment is None:
            continue
        if (segment.GetName() or "").strip().lower() == want:
            return segment_id
    return ""


def _center_cameras_on_segment(segmentation_node, segment_id: str) -> None:
    """Point compare 3D cameras at the segment center (Prev/Next navigation)."""
    if segmentation_node is None or not segment_id:
        return
    try:
        center = segmentation_node.GetSegmentCenterRAS(segment_id)
    except Exception:
        return
    if center is None:
        return
    layout = slicer.app.layoutManager()
    for index in range(int(layout.threeDViewCount)):
        try:
            view_node = layout.threeDWidget(index).threeDView().mrmlViewNode()
            camera = slicer.modules.cameras.logic().GetViewActiveCameraNode(view_node)
            if camera is not None:
                camera.SetFocalPoint(center)
        except Exception:
            continue


def clear_segment_color_overrides(segmentation_node) -> None:
    """Drop display-node color overrides (needed when work seg is reused in Compare)."""
    if segmentation_node is None:
        return
    display = segmentation_node.GetDisplayNode()
    if display is None:
        return
    unset = getattr(display, "UnsetSegmentOverrideColor", None)
    if not callable(unset):
        return
    segmentation = segmentation_node.GetSegmentation()
    if segmentation is None:
        return
    for index in range(int(segmentation.GetNumberOfSegments())):
        segment_id = segmentation.GetNthSegmentID(index)
        if not segment_id:
            continue
        try:
            unset(segment_id)
        except Exception:
            continue


def _paint_segment_compare_color(segmentation_node, segment_id: str, rgb: tuple) -> None:
    """Force segment tint for Compare. Prefer display override (non-destructive)."""
    if segmentation_node is None or not segment_id or not rgb:
        return
    r, g, b = float(rgb[0]), float(rgb[1]), float(rgb[2])
    display = segmentation_node.GetDisplayNode()
    if display is not None:
        setter = getattr(display, "SetSegmentOverrideColor", None)
        if callable(setter):
            try:
                setter(segment_id, r, g, b)
                return
            except Exception:
                pass
    # Fallback: mutate segment color (temp CVCompare_* nodes only in practice).
    try:
        segmentation = segmentation_node.GetSegmentation()
        segment = segmentation.GetSegment(segment_id) if segmentation is not None else None
        if segment is not None:
            segment.SetColor(r, g, b)
    except Exception:
        pass


def focus_segment_name(
    segmentation_node,
    name: str,
    *,
    show_3d: bool = False,
    override_color: tuple | None = None,
) -> bool:
    """Show only ``name`` on this node; 3D only if show_3d. Returns True if found.

    ``override_color`` is RGB 0..1 (e.g. COMPARE_COLOR_TARGET / COMPARE_COLOR_SOURCE).
    """
    if segmentation_node is None:
        return False
    try:
        segmentation_node.CreateDefaultDisplayNodes()
    except Exception:
        pass
    display = segmentation_node.GetDisplayNode()
    if display is None:
        return False
    try:
        display.SetVisibility(True)
        display.SetVisibility2D(True)
        display.SetVisibility3D(bool(show_3d))
    except Exception:
        pass
    found_id = _find_segment_id_by_name(segmentation_node, name)
    display.SetAllSegmentsVisibility(False)
    if override_color is not None:
        clear_segment_color_overrides(segmentation_node)
    if not found_id:
        return False
    if override_color is not None:
        _paint_segment_compare_color(segmentation_node, found_id, override_color)
    display.SetSegmentVisibility(found_id, True)
    display.SetSegmentOpacity(found_id, 1.0)
    try:
        display.SetSegmentOpacity2DFill(found_id, 1.0)
        display.SetSegmentVisibility2DFill(found_id, True)
        display.SetSegmentVisibility2DOutline(found_id, True)
        display.SetSegmentVisibility3D(found_id, bool(show_3d))
    except Exception:
        pass
    if show_3d:
        _center_cameras_on_segment(segmentation_node, found_id)
    return True


def show_all_segments(
    segmentation_node,
    *,
    show_3d: bool = False,
) -> None:
    """Show every segment with node colors (no green/red override)."""
    if segmentation_node is None:
        return
    try:
        segmentation_node.CreateDefaultDisplayNodes()
    except Exception:
        pass
    clear_segment_color_overrides(segmentation_node)
    display = segmentation_node.GetDisplayNode()
    if display is None:
        return
    try:
        display.SetVisibility(True)
        display.SetVisibility2D(True)
        display.SetVisibility3D(bool(show_3d))
    except Exception:
        pass
    display.SetAllSegmentsVisibility(True)
    try:
        display.SetVisibility2DFill(True)
        display.SetVisibility2DOutline(True)
    except Exception:
        pass
    if show_3d:
        try:
            segmentation_node.CreateClosedSurfaceRepresentation()
        except Exception:
            pass
        segmentation = segmentation_node.GetSegmentation()
        if segmentation is not None:
            for index in range(int(segmentation.GetNumberOfSegments())):
                segment_id = segmentation.GetNthSegmentID(index)
                if not segment_id:
                    continue
                try:
                    display.SetSegmentVisibility3D(segment_id, True)
                except Exception:
                    continue


def show_all_segments_both(
    target_segmentation,
    source_segmentation,
    *,
    show_3d: bool = False,
) -> None:
    show_all_segments(target_segmentation, show_3d=show_3d)
    show_all_segments(source_segmentation, show_3d=show_3d)


def _nav_button_style(color: str, hover: str) -> str:
    on_ice = TEXT_ON_ICE or "#0f172a"
    return (
        "QPushButton {"
        "  background-color: palette(button);"
        "  color: %s;"
        "  border: 1px solid %s;"
        "  font-weight: 700;"
        "  border-radius: 4px;"
        "  padding: 8px;"
        "}"
        "QPushButton:hover {"
        "  background-color: %s;"
        "  color: %s;"
        "}"
        % (color, color, hover, on_ice)
    )


class MergeComparePanel(qt.QWidget):
    """Embedded left-panel: version names, segment list + status, Prev/Next, Quit."""

    def __init__(self, parent=None) -> None:
        qt.QWidget.__init__(self, parent)
        muted = TEXT_MUTED or "#888888"
        accent = ACCENT_ICE or "#5b9fd4"
        ice = ACCENT_ICE or "#5b9fd4"
        ice_hover = ACCENT_ICE_HOVER or ice
        indigo = ACCENT_INDIGO or "#818cf8"
        indigo_hover = ACCENT_INDIGO_HOVER or indigo
        mint = ACCENT_MINT or "#6ee7b7"
        red = ACCENT_RED or "#f87171"
        self._rows: list[dict] = []
        self._suppress_list = False

        layout = qt.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        versions = qt.QFrame()
        versions.setObjectName("cvCompareVersions")
        versions.setStyleSheet(
            "#cvCompareVersions {"
            "  background-color: palette(button);"
            "  border: 1px solid palette(mid);"
            "  border-left: 3px solid %s;"
            "  border-radius: 6px;"
            "}" % accent
        )
        versions_layout = qt.QVBoxLayout(versions)
        versions_layout.setContentsMargins(10, 8, 10, 8)
        versions_layout.setSpacing(6)
        self.upperVersionLabel = qt.QLabel("—")
        self.lowerVersionLabel = qt.QLabel("—")
        for label in (self.upperVersionLabel, self.lowerVersionLabel):
            label.setTextFormat(qt.Qt.RichText)
            label.setWordWrap(True)
            label.setStyleSheet(
                "color: palette(window-text); font-size: 12px; font-weight: 600;"
            )
            versions_layout.addWidget(label)
        layout.addWidget(versions)

        header = qt.QHBoxLayout()
        seg_title = qt.QLabel("SEGMENTS")
        seg_title.setStyleSheet(
            "color: %s; font-size: 10px; font-weight: 600; letter-spacing: 1px;" % accent
        )
        header.addWidget(seg_title, 1)
        self.segmentCountLabel = qt.QLabel("")
        self.segmentCountLabel.setStyleSheet("color: %s; font-size: 10px;" % muted)
        header.addWidget(self.segmentCountLabel, 0)
        layout.addLayout(header)

        self.segmentList = qt.QListWidget()
        self.segmentList.setMinimumHeight(140)
        self.segmentList.setMaximumHeight(220)
        self.segmentList.setStyleSheet(
            "QListWidget {"
            "  background-color: palette(base);"
            "  border: 1px solid palette(mid);"
            "  border-radius: 4px;"
            "  outline: none;"
            "}"
            "QListWidget::item { padding: 6px 8px; }"
            "QListWidget::item:selected {"
            "  background-color: %s;"
            "  color: %s;"
            "}" % (ice, TEXT_ON_ICE or "#0f172a")
        )
        layout.addWidget(self.segmentList)

        nav = qt.QHBoxLayout()
        nav.setSpacing(6)
        self.prevButton = qt.QPushButton("◀ Prev")
        self.nextButton = qt.QPushButton("Next ▶")
        self.prevButton.setStyleSheet(_nav_button_style(ice, ice_hover))
        self.nextButton.setStyleSheet(_nav_button_style(indigo, indigo_hover))
        for btn in (self.prevButton, self.nextButton):
            btn.setMinimumHeight(30)
            btn.setSizePolicy(qt.QSizePolicy.Expanding, qt.QSizePolicy.Fixed)
            nav.addWidget(btn)
        layout.addLayout(nav)

        self.statusLabel = qt.QLabel("")
        self.statusLabel.setWordWrap(True)
        self.statusLabel.setStyleSheet("color: %s; font-size: 11px;" % muted)
        layout.addWidget(self.statusLabel)

        self.showAllCheck = qt.QCheckBox("Show all segments")
        self.showAllCheck.setChecked(False)
        self.showAllCheck.setToolTip(
            "Show every segment with its real colors. "
            "Off = one segment at a time (green target / red source)."
        )
        layout.addWidget(self.showAllCheck)

        self.show3dCheck = qt.QCheckBox("Show 3D")
        self.show3dCheck.setChecked(False)
        self.show3dCheck.setToolTip(
            "Build and show closed-surface 3D "
            "(off by default — faster)."
        )
        layout.addWidget(self.show3dCheck)

        self.quitButton = qt.QPushButton("Quit")
        self.quitButton.setToolTip("Leave Compare and restore the normal layout")
        self.quitButton.setStyleSheet(BTN_DELETE)
        self.quitButton.setMinimumHeight(32)
        layout.addWidget(self.quitButton)

        # Keep color refs used only for status text styling helpers.
        self._status_colors = {
            "both": mint,
            "only": red,
            "muted": muted,
        }

    def set_version_labels(self, target_label: str, source_label: str) -> None:
        muted = self._status_colors["muted"]
        self.upperVersionLabel.setText(
            "%s<br><span style='color:%s;font-size:10px;font-weight:500;'>"
            "left 3D · upper 2D</span>"
            % (html.escape(str(target_label or "—")), muted)
        )
        self.lowerVersionLabel.setText(
            "%s<br><span style='color:%s;font-size:10px;font-weight:500;'>"
            "right 3D · lower 2D</span>"
            % (html.escape(str(source_label or "—")), muted)
        )

    def set_segments(self, rows: list[dict]) -> None:
        self._rows = list(rows or [])
        self._suppress_list = True
        try:
            self.segmentList.clear()
            for row in self._rows:
                name = str(row.get("name") or "")
                status = str(row.get("status") or "")
                item = qt.QListWidgetItem("%s    %s" % (name, status))
                item.setData(qt.Qt.UserRole, name)
                # Soft emphasis when not in both versions.
                if status != "both":
                    item.setForeground(qt.QColor(self._status_colors["only"]))
                else:
                    item.setForeground(qt.QColor(self._status_colors["both"]))
                self.segmentList.addItem(item)
            total = len(self._rows)
            self.segmentCountLabel.setText("" if total <= 0 else "%d" % total)
            if total <= 0:
                self.statusLabel.setText("No segments to compare.")
            else:
                self.statusLabel.setText("")
        finally:
            self._suppress_list = False

    def set_current_index(self, index: int) -> None:
        total = len(self._rows)
        if total <= 0:
            self.statusLabel.setText("No segments to compare.")
            return
        index = max(0, min(int(index), total - 1))
        self._suppress_list = True
        try:
            self.segmentList.setCurrentRow(index)
            item = self.segmentList.item(index)
            if item is not None:
                self.segmentList.scrollToItem(item)
        finally:
            self._suppress_list = False
        row = self._rows[index]
        status = str(row.get("status") or "")
        name = str(row.get("name") or "")
        if status == "both":
            self.statusLabel.setText("Present in both · %d / %d" % (index + 1, total))
            self.statusLabel.setStyleSheet(
                "color: %s; font-size: 11px;" % self._status_colors["both"]
            )
        else:
            self.statusLabel.setText(
                "%s · %s · %d / %d" % (name, status, index + 1, total)
            )
            self.statusLabel.setStyleSheet(
                "color: %s; font-size: 11px;" % self._status_colors["only"]
            )

    def reset_controls(self) -> None:
        self.showAllCheck.blockSignals(True)
        self.show3dCheck.blockSignals(True)
        try:
            self.showAllCheck.setChecked(False)
            self.show3dCheck.setChecked(False)
        finally:
            self.showAllCheck.blockSignals(False)
            self.show3dCheck.blockSignals(False)
        self._rows = []
        self._suppress_list = True
        try:
            self.segmentList.clear()
        finally:
            self._suppress_list = False
        self.segmentCountLabel.setText("")
        self.statusLabel.setText("")
        self.upperVersionLabel.setText("—")
        self.lowerVersionLabel.setText("—")
