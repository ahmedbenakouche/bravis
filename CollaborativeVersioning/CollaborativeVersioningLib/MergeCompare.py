"""Side-by-side Merge Compare layout + control bar (inspired by CrossSegmentationExplorer)."""
from __future__ import annotations

import html

import qt
import slicer

from CollaborativeVersioningLib.UiStyles import (
    BTN_SECONDARY,
    BTN_SAVE_VERSION,
    TEXT_MUTED,
)

# Layout: both 3D views on top; each version's Axial|Sagittal|Coronal below.
TARGET_3D_TAG = "CVCmpT"
SOURCE_3D_TAG = "CVCmpS"
TARGET_SLICE_TAGS = ("R CVCmpT", "G CVCmpT", "Y CVCmpT")
SOURCE_SLICE_TAGS = ("R CVCmpS", "G CVCmpS", "Y CVCmpS")
_ORIENT = ("Axial", "Sagittal", "Coronal")
_COLORS = ("#F34A33", "#4AF333", "#F3E833")


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
    seen: set[str] = set()
    ordered: list[str] = []
    for name in segment_names(target_node) + segment_names(source_node):
        key = name.lower()
        if key in seen:
            continue
        seen.add(key)
        ordered.append(name)

    def sort_key(value: str):
        text = str(value or "").strip()
        try:
            return (0, int(text))
        except ValueError:
            return (1, text.lower())

    ordered.sort(key=sort_key)
    return ordered


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


def focus_segment_name(
    segmentation_node,
    name: str,
    *,
    show_3d: bool = False,
) -> bool:
    """Show only ``name`` on this node; 3D only if show_3d. Returns True if found."""
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
    if not found_id:
        return False
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


def show_all_segments(segmentation_node) -> None:
    if segmentation_node is None:
        return
    display = segmentation_node.GetDisplayNode()
    if display is None:
        return
    display.SetAllSegmentsVisibility(True)


class MergeComparePanel(qt.QWidget):
    """Embedded left-panel controls: Prev/Next, Show 3D, Quit Compare."""

    def __init__(self, parent=None) -> None:
        qt.QWidget.__init__(self, parent)
        layout = qt.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        self.headerLabel = qt.QLabel("Compare")
        self.headerLabel.setTextFormat(qt.Qt.RichText)
        self.headerLabel.setWordWrap(True)
        self.headerLabel.setStyleSheet("color: %s;" % (TEXT_MUTED or "#888888"))
        layout.addWidget(self.headerLabel)

        hint = qt.QLabel("Finish Compare before saving or switching versions.")
        hint.setWordWrap(True)
        hint.setStyleSheet("color: %s; font-size: 10px;" % (TEXT_MUTED or "#888888"))
        layout.addWidget(hint)

        row = qt.QHBoxLayout()
        self.segmentLabel = qt.QLabel("Segment: —")
        self.segmentLabel.setStyleSheet("color: palette(window-text);")
        row.addWidget(self.segmentLabel, 1)
        self.prevButton = qt.QPushButton("◀ Prev")
        self.nextButton = qt.QPushButton("Next ▶")
        self.prevButton.setStyleSheet(BTN_SECONDARY)
        self.nextButton.setStyleSheet(BTN_SECONDARY)
        row.addWidget(self.prevButton)
        row.addWidget(self.nextButton)
        layout.addLayout(row)

        self.show3dCheck = qt.QCheckBox("Show 3D")
        self.show3dCheck.setChecked(False)
        self.show3dCheck.setToolTip(
            "Build and show closed-surface 3D for the current segment "
            "(off by default — faster)."
        )
        layout.addWidget(self.show3dCheck)

        self.quitButton = qt.QPushButton("Quit Compare")
        self.quitButton.setStyleSheet(BTN_SAVE_VERSION)
        layout.addWidget(self.quitButton)

    def set_version_labels(self, target_label: str, source_label: str) -> None:
        self.headerLabel.setText(
            "Target: <b>%s</b> (left 3D, upper 2D)<br>"
            "Source: <b>%s</b> (right 3D, lower 2D)"
            % (
                html.escape(str(target_label or "")),
                html.escape(str(source_label or "")),
            )
        )

    def set_segment_label(self, name: str, index: int, total: int) -> None:
        if total <= 0:
            self.segmentLabel.setText("Segment: (none)")
            return
        self.segmentLabel.setText(
            "Segment: %s  (%d / %d)" % (name or "—", index + 1, total)
        )

    def reset_controls(self) -> None:
        self.show3dCheck.blockSignals(True)
        try:
            self.show3dCheck.setChecked(False)
        finally:
            self.show3dCheck.blockSignals(False)
        self.set_segment_label("", 0, 0)
