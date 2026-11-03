"""Side-by-side Merge Compare layout + control bar (inspired by CrossSegmentationExplorer)."""
from __future__ import annotations

import html

import qt
import slicer
import vtk

from CollaborativeVersioningLib import SegmentationCubes
from CollaborativeVersioningLib.UiStyles import (
    ACCENT_ICE,
    ACCENT_ICE_HOVER,
    ACCENT_INDIGO,
    ACCENT_INDIGO_HOVER,
    ACCENT_MINT,
    ACCENT_RED,
    BTN_CREATE,
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
# Cube-diff rectangle overlay (display RGB 0..1).
CUBE_DIFF_COLOR = (1.0, 0.85, 0.15)
CUBE_DIFF_SELECTED_COLOR = (0.15, 0.95, 1.0)  # cyan = selected cube
CUBE_DIFF_LINE_WIDTH = 2.0
CUBE_DIFF_SELECTED_LINE_WIDTH = 4.0
CUBE_DIFF_MODEL_NAME = "CVCompare_CubeDiffs"
CUBE_DIFF_SELECTED_MODEL_NAME = "CVCompare_CubeDiffSelected"


def _geometry_ijk_to_ras_matrix(geometry: dict | None) -> vtk.vtkMatrix4x4:
    """Build IJK→RAS from manifest/volume geometry (origin, spacing, directions)."""
    geo = dict(geometry or {})
    origin = [float(v) for v in (geo.get("origin") or [0.0, 0.0, 0.0])][:3]
    while len(origin) < 3:
        origin.append(0.0)
    spacing = [float(v) for v in (geo.get("spacing") or [1.0, 1.0, 1.0])][:3]
    while len(spacing) < 3:
        spacing.append(1.0)
    directions = list(geo.get("directions") or [1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0])
    if len(directions) != 9:
        directions = [1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0]
    matrix = vtk.vtkMatrix4x4()
    matrix.Identity()
    for col in range(3):
        for row in range(3):
            matrix.SetElement(
                row, col, float(directions[row * 3 + col]) * float(spacing[col])
            )
    for row in range(3):
        matrix.SetElement(row, 3, float(origin[row]))
    return matrix


def _ijk_to_ras(matrix: vtk.vtkMatrix4x4, i: float, j: float, k: float) -> tuple[float, float, float]:
    point = [float(i), float(j), float(k), 1.0]
    out = [0.0, 0.0, 0.0, 0.0]
    matrix.MultiplyPoint(point, out)
    return float(out[0]), float(out[1]), float(out[2])


def changed_cube_bounds(
    target_manifest: dict | None,
    source_manifest: dict | None,
) -> list[dict]:
    """IJK AABBs for cubes whose manifest hash differs (no voxel load)."""
    if not isinstance(target_manifest, dict) or not isinstance(source_manifest, dict):
        return []
    left = target_manifest.get("chunks") or {}
    right = source_manifest.get("chunks") or {}
    if not isinstance(left, dict) or not isinstance(right, dict):
        return []
    shape_t, chunk_t = SegmentationCubes._manifest_shape_chunk(target_manifest)
    shape_s, chunk_s = SegmentationCubes._manifest_shape_chunk(source_manifest)
    keys = set(left) | set(right)
    cubes: list[dict] = []
    for key in keys:
        if str(left.get(key) or "").strip().lower() == str(right.get(key) or "").strip().lower():
            continue
        if key in right and shape_s is not None:
            shape, chunk = shape_s, chunk_s
        elif key in left and shape_t is not None:
            shape, chunk = shape_t, chunk_t
        elif shape_s is not None:
            shape, chunk = shape_s, chunk_s
        elif shape_t is not None:
            shape, chunk = shape_t, chunk_t
        else:
            continue
        try:
            zsl, ysl, xsl = SegmentationCubes.cube_slices(shape, key, chunk)
        except ValueError:
            continue
        cubes.append(
            {
                "key": str(key),
                "i0": int(xsl.start),
                "i1": int(xsl.stop),
                "j0": int(ysl.start),
                "j1": int(ysl.stop),
                "k0": int(zsl.start),
                "k1": int(zsl.stop),
            }
        )
    return cubes


def manifest_geometry(manifest: dict | None, volume_node=None) -> dict:
    """Prefer manifest geometry; fall back to the background volume."""
    if isinstance(manifest, dict):
        geo = {
            "origin": list(manifest.get("origin") or [0.0, 0.0, 0.0]),
            "spacing": list(manifest.get("spacing") or [1.0, 1.0, 1.0]),
            "directions": list(
                manifest.get("directions")
                or [1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0]
            ),
        }
        if geo["directions"] and len(geo["directions"]) == 9:
            return geo
    if volume_node is not None:
        return SegmentationCubes.geometry_from_volume(volume_node)
    return {
        "origin": [0.0, 0.0, 0.0],
        "spacing": [1.0, 1.0, 1.0],
        "directions": [1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0],
    }


def build_merged_manifest(
    target_manifest: dict | None,
    source_manifest: dict | None,
    choices: dict[str, str],
) -> dict | None:
    """Compose a new manifest: unchanged hashes + chosen upper/lower for diffs."""
    if not isinstance(target_manifest, dict) or not isinstance(source_manifest, dict):
        return None
    base = dict(target_manifest)
    left = dict(target_manifest.get("chunks") or {})
    right = dict(source_manifest.get("chunks") or {})
    chunks = dict(left)
    for key in set(left) | set(right):
        lh = str(left.get(key) or "").strip().lower()
        rh = str(right.get(key) or "").strip().lower()
        if lh == rh:
            if key in left:
                chunks[key] = left[key]
            elif key in right:
                chunks[key] = right[key]
            continue
        side = str((choices or {}).get(str(key)) or "").strip().lower()
        if side == "upper":
            chunks[key] = left.get(key) if key in left else right.get(key)
        elif side == "lower":
            chunks[key] = right.get(key) if key in right else left.get(key)
        else:
            return None  # unresolved
    base["chunks"] = chunks
    return base


class CubeDiffOverlay:
    """Outline changed cubes via light wireframe models (2D slice intersections)."""

    def __init__(self) -> None:
        self._cubes: list[dict] = []
        self._cube_by_key: dict[str, dict] = {}
        self._ijk_to_ras: vtk.vtkMatrix4x4 | None = None
        self._ras_to_ijk: vtk.vtkMatrix4x4 | None = None
        self._enabled = True
        self._model_node_id = ""
        self._chosen_model_id = ""
        self._chosen_keys: set[str] = set()
        self._click_observers: list[tuple] = []
        self._click_callback = None

    @property
    def cube_count(self) -> int:
        return len(self._cubes)

    @property
    def cubes(self) -> list[dict]:
        return list(self._cubes)

    def configure(
        self,
        target_manifest: dict | None,
        source_manifest: dict | None,
        volume_node=None,
    ) -> int:
        self._cubes = changed_cube_bounds(target_manifest, source_manifest)
        self._cube_by_key = {str(c.get("key") or ""): c for c in self._cubes}
        matrix = vtk.vtkMatrix4x4()
        if volume_node is not None:
            try:
                volume_node.GetIJKToRASMatrix(matrix)
            except Exception:
                geo = manifest_geometry(source_manifest or target_manifest, volume_node)
                matrix = _geometry_ijk_to_ras_matrix(geo)
        else:
            geo = manifest_geometry(source_manifest or target_manifest, None)
            matrix = _geometry_ijk_to_ras_matrix(geo)
        self._ijk_to_ras = matrix
        self._ras_to_ijk = vtk.vtkMatrix4x4()
        vtk.vtkMatrix4x4.Invert(matrix, self._ras_to_ijk)
        return len(self._cubes)

    def start(self, *, enabled: bool = True, click_callback=None) -> None:
        self.stop()
        self._enabled = bool(enabled)
        self._click_callback = click_callback
        if not self._cubes or self._ijk_to_ras is None:
            return
        poly = self._build_wireframe_polydata(self._cubes)
        if poly is None or int(poly.GetNumberOfPoints()) <= 0:
            return
        self._model_node_id = self._add_model(
            CUBE_DIFF_MODEL_NAME,
            poly,
            CUBE_DIFF_COLOR,
            CUBE_DIFF_LINE_WIDTH,
        )
        self._install_click_observers()
        self._apply_visibility()
        self.set_chosen_keys(self._chosen_keys)

    def stop(self) -> None:
        self._remove_click_observers()
        for node_id in (self._model_node_id, self._chosen_model_id):
            if not node_id:
                continue
            node = slicer.mrmlScene.GetNodeByID(str(node_id))
            if node is not None:
                try:
                    slicer.mrmlScene.RemoveNode(node)
                except Exception:
                    pass
        self._model_node_id = ""
        self._chosen_model_id = ""
        self._remove_named_models()

    def set_enabled(self, enabled: bool) -> None:
        self._enabled = bool(enabled)
        if not self._model_node_id and enabled and self._cubes:
            self.start(enabled=True, click_callback=self._click_callback)
            return
        self._apply_visibility()
        if not self._enabled:
            self._clear_chosen_model()
        else:
            self.set_chosen_keys(self._chosen_keys)

    def set_chosen_keys(self, keys) -> None:
        """Cyan outline for cubes already chosen (will be taken on Apply)."""
        self._chosen_keys = {str(k) for k in (keys or []) if str(k or "").strip()}
        self._clear_chosen_model()
        if not self._enabled or not self._chosen_keys:
            return
        cubes = [
            self._cube_by_key[k]
            for k in self._chosen_keys
            if k in self._cube_by_key
        ]
        if not cubes:
            return
        poly = self._build_wireframe_polydata(cubes)
        if poly is None or int(poly.GetNumberOfPoints()) <= 0:
            return
        self._chosen_model_id = self._add_model(
            CUBE_DIFF_SELECTED_MODEL_NAME,
            poly,
            CUBE_DIFF_SELECTED_COLOR,
            CUBE_DIFF_SELECTED_LINE_WIDTH,
        )

    def pick_key_at_ras(self, ras) -> str:
        """Return changed-cube key containing this RAS point, else ''."""
        if self._ras_to_ijk is None or not ras:
            return ""
        out = [0.0, 0.0, 0.0, 1.0]
        self._ras_to_ijk.MultiplyPoint(
            [float(ras[0]), float(ras[1]), float(ras[2]), 1.0], out
        )
        i, j, k = float(out[0]), float(out[1]), float(out[2])
        for cube in self._cubes:
            if (
                float(cube["i0"]) <= i < float(cube["i1"])
                and float(cube["j0"]) <= j < float(cube["j1"])
                and float(cube["k0"]) <= k < float(cube["k1"])
            ):
                return str(cube.get("key") or "")
        return ""

    def _install_click_observers(self) -> None:
        layout = slicer.app.layoutManager()
        for tag in TARGET_SLICE_TAGS:
            self._observe_slice_tag(layout, tag, "upper")
        for tag in SOURCE_SLICE_TAGS:
            self._observe_slice_tag(layout, tag, "lower")

    def _observe_slice_tag(self, layout, tag: str, side: str) -> None:
        widget = layout.sliceWidget(tag)
        if widget is None:
            return
        try:
            interactor = widget.sliceView().interactor()
        except Exception:
            return
        if interactor is None:
            return

        def _handler(caller=None, event=None, w=widget, s=side):
            self._on_slice_click(w, s, caller)

        try:
            oid = interactor.AddObserver(
                vtk.vtkCommand.LeftButtonReleaseEvent, _handler
            )
            self._click_observers.append((interactor, oid))
        except Exception:
            pass

    def _remove_click_observers(self) -> None:
        for interactor, oid in self._click_observers:
            try:
                interactor.RemoveObserver(oid)
            except Exception:
                pass
        self._click_observers = []

    def _on_slice_click(self, slice_widget, side: str, caller) -> None:
        if not self._enabled or not callable(self._click_callback):
            return
        try:
            if caller is not None and hasattr(caller, "GetControlKey") and caller.GetControlKey():
                return
            if caller is not None and hasattr(caller, "GetShiftKey") and caller.GetShiftKey():
                return
        except Exception:
            pass
        ras = _ras_from_slice_interactor(slice_widget, caller)
        if ras is None:
            return
        key = self.pick_key_at_ras(ras)
        if not key:
            return
        try:
            self._click_callback(key, side)
        except Exception:
            pass

    def _apply_visibility(self) -> None:
        for node_id in (self._model_node_id, self._chosen_model_id):
            node = slicer.mrmlScene.GetNodeByID(str(node_id or ""))
            if node is None:
                continue
            display = node.GetDisplayNode()
            if display is None:
                continue
            try:
                display.SetVisibility(bool(self._enabled))
                display.SetVisibility2D(bool(self._enabled))
            except Exception:
                pass

    def _clear_chosen_model(self) -> None:
        node_id = str(self._chosen_model_id or "")
        self._chosen_model_id = ""
        if not node_id:
            return
        node = slicer.mrmlScene.GetNodeByID(node_id)
        if node is not None:
            try:
                slicer.mrmlScene.RemoveNode(node)
            except Exception:
                pass

    def _add_model(self, name: str, poly, color, thickness) -> str:
        model = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLModelNode", name)
        model.SetName(name)
        model.SetAndObservePolyData(poly)
        model.CreateDefaultDisplayNodes()
        display = model.GetDisplayNode()
        if display is not None:
            try:
                display.SetVisibility(bool(self._enabled))
                display.SetVisibility2D(True)
                display.SetVisibility3D(False)
                display.SetColor(*color)
                display.SetOpacity(0.0)
                try:
                    display.SetSliceIntersectionVisibility(True)
                except Exception:
                    pass
                try:
                    display.SetSliceIntersectionOpacity(0.95)
                except Exception:
                    pass
                try:
                    display.SetSliceIntersectionThickness(int(max(2, int(thickness))))
                except Exception:
                    pass
                try:
                    display.SetLineWidth(float(thickness))
                except Exception:
                    pass
                display.RemoveAllViewNodeIDs()
                layout = slicer.app.layoutManager()
                for tag in TARGET_SLICE_TAGS + SOURCE_SLICE_TAGS:
                    widget = layout.sliceWidget(tag)
                    if widget is None:
                        continue
                    try:
                        display.AddViewNodeID(widget.mrmlSliceNode().GetID())
                    except Exception:
                        continue
            except Exception:
                pass
        return model.GetID()

    def _build_wireframe_polydata(self, cubes: list[dict]) -> vtk.vtkPolyData | None:
        """Closed box faces — slice cut = rectangle on 2D views."""
        matrix = self._ijk_to_ras
        if matrix is None or not cubes:
            return None
        points = vtk.vtkPoints()
        polys = vtk.vtkCellArray()
        faces = (
            (0, 1, 3, 2),
            (4, 5, 7, 6),
            (0, 1, 5, 4),
            (2, 3, 7, 6),
            (0, 2, 6, 4),
            (1, 3, 7, 5),
        )
        for cube in cubes:
            i0, i1 = float(cube["i0"]), float(cube["i1"])
            j0, j1 = float(cube["j0"]), float(cube["j1"])
            k0, k1 = float(cube["k0"]), float(cube["k1"])
            if abs(i1 - i0) < 1e-6:
                i1 = i0 + 1.0
            if abs(j1 - j0) < 1e-6:
                j1 = j0 + 1.0
            if abs(k1 - k0) < 1e-6:
                k1 = k0 + 1.0
            corners_ijk = (
                (i0, j0, k0),
                (i1, j0, k0),
                (i0, j1, k0),
                (i1, j1, k0),
                (i0, j0, k1),
                (i1, j0, k1),
                (i0, j1, k1),
                (i1, j1, k1),
            )
            ids = []
            for i, j, k in corners_ijk:
                ras = _ijk_to_ras(matrix, i, j, k)
                ids.append(points.InsertNextPoint(ras[0], ras[1], ras[2]))
            for a, b, c, d in faces:
                polys.InsertNextCell(4)
                polys.InsertCellPoint(ids[a])
                polys.InsertCellPoint(ids[b])
                polys.InsertCellPoint(ids[c])
                polys.InsertCellPoint(ids[d])
        poly = vtk.vtkPolyData()
        poly.SetPoints(points)
        poly.SetPolys(polys)
        return poly

    @staticmethod
    def _remove_named_models() -> None:
        scene = slicer.mrmlScene
        names = {CUBE_DIFF_MODEL_NAME, CUBE_DIFF_SELECTED_MODEL_NAME}
        for index in range(scene.GetNumberOfNodesByClass("vtkMRMLModelNode") - 1, -1, -1):
            node = scene.GetNthNodeByClass(index, "vtkMRMLModelNode")
            if node is None:
                continue
            if str(node.GetName() or "") in names:
                try:
                    scene.RemoveNode(node)
                except Exception:
                    pass


def _ras_from_slice_interactor(slice_widget, interactor) -> tuple[float, float, float] | None:
    """Map a slice-view click to RAS."""
    if slice_widget is None or interactor is None:
        return None
    try:
        x, y = interactor.GetEventPosition()
    except Exception:
        return None
    try:
        slice_node = slice_widget.mrmlSliceNode()
        slice_view = slice_widget.sliceView()
    except Exception:
        return None
    if slice_node is None:
        return None
    xyz = [float(x), float(y), 0.0]
    try:
        # Preferred: display → XYZ in the slice canvas.
        tmp = [0.0, 0.0, 0.0]
        slice_view.convertDisplayToXYZ(int(x), int(y), tmp)
        xyz = [float(tmp[0]), float(tmp[1]), float(tmp[2])]
    except Exception:
        pass
    xy_to_ras = vtk.vtkMatrix4x4()
    try:
        slice_node.GetXYToRAS(xy_to_ras)
    except Exception:
        return None
    ras = [0.0, 0.0, 0.0, 1.0]
    xy_to_ras.MultiplyPoint([xyz[0], xyz[1], xyz[2], 1.0], ras)
    return float(ras[0]), float(ras[1]), float(ras[2])


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

        self.showCubeDiffsCheck = qt.QCheckBox("Show cube diffs")
        self.showCubeDiffsCheck.setChecked(True)
        self.showCubeDiffsCheck.setToolTip(
            "Outline changed cubes on 2D views. "
            "Click a cube on upper views = keep upper; lower views = keep lower."
        )
        layout.addWidget(self.showCubeDiffsCheck)

        self.cubeDiffsBox = qt.QWidget()
        cube_box = qt.QVBoxLayout(self.cubeDiffsBox)
        cube_box.setContentsMargins(0, 4, 0, 0)
        cube_box.setSpacing(6)
        self.cubeGuideLabel = qt.QLabel(
            "Click the cube you want to keep on the 2D views "
            "(upper = keep upper, lower = keep lower). "
            "Chosen cubes turn cyan — those are the ones taken on Apply merge."
        )
        self.cubeGuideLabel.setWordWrap(True)
        self.cubeGuideLabel.setStyleSheet("color: %s; font-size: 11px;" % muted)
        cube_box.addWidget(self.cubeGuideLabel)
        self.applyMergeButton = qt.QPushButton("Apply merge")
        self.applyMergeButton.setToolTip(
            "Build the merged tip from the cyan (chosen) cubes."
        )
        self.applyMergeButton.setStyleSheet(BTN_CREATE or "")
        self.applyMergeButton.setMinimumHeight(32)
        cube_box.addWidget(self.applyMergeButton)
        layout.addWidget(self.cubeDiffsBox)

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
        self.set_cube_diffs_visible(True)

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

    def set_cube_diffs_visible(self, visible: bool) -> None:
        visible = bool(visible)
        self.cubeDiffsBox.setVisible(visible)
        # Apply merge is only active while Show cube diffs is on.
        self.applyMergeButton.setEnabled(visible)

    def reset_controls(self) -> None:
        self.showAllCheck.blockSignals(True)
        self.showCubeDiffsCheck.blockSignals(True)
        self.show3dCheck.blockSignals(True)
        try:
            self.showAllCheck.setChecked(False)
            self.show3dCheck.setChecked(False)
            self.showCubeDiffsCheck.setChecked(True)
        finally:
            self.showAllCheck.blockSignals(False)
            self.showCubeDiffsCheck.blockSignals(False)
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
        self.set_cube_diffs_visible(True)
