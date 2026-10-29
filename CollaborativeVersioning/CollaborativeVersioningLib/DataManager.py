"""Load and export 3D volumes and segmentations (NIfTI, NRRD, DICOM) for collaborative versioning."""

from __future__ import annotations

import logging
import os
import re
import shutil
import tempfile
import time
from enum import Enum
from typing import Any

import slicer

_SEGMENT_ID_NAME = re.compile(r"(?i)^segment_(\d+)$")


class _SlicerProgressPopupGuard:
    """Hide Slicer's own I/O progress popup while we show ours."""

    def __init__(self) -> None:
        self._filter = None

    def __enter__(self):
        import qt

        class _Filter(qt.QObject):
            def eventFilter(self, obj, event):
                try:
                    if int(event.type()) != int(qt.QEvent.Show):
                        return False
                    name = ""
                    try:
                        name = str(obj.metaObject().className())
                    except Exception:
                        name = type(obj).__name__
                    if name == "QProgressDialog" or name.endswith("ProgressDialog"):
                        try:
                            obj.hide()
                        except Exception:
                            pass
                        return True
                except Exception:
                    return False
                return False

        app = qt.QApplication.instance()
        if app is None:
            return self
        self._filter = _Filter()
        try:
            app.installEventFilter(self._filter)
        except Exception:
            self._filter = None
        return self

    def __exit__(self, *_args) -> None:
        import qt

        app = qt.QApplication.instance()
        filt = self._filter
        self._filter = None
        if app is None or filt is None:
            return
        try:
            app.removeEventFilter(filt)
        except Exception:
            pass


class DataFormat(Enum):
    NIFTI = "nifti"
    NRRD = "nrrd"
    DICOM = "dicom"
    SEGMENTATION = "segmentation"
    UNKNOWN = "unknown"


class DataManager:
    """Charge et exporte des données 3D via les lecteurs Slicer."""

    NIFTI_EXTENSIONS = (".nii", ".nii.gz")
    NRRD_EXTENSIONS = (".nrrd", ".nhdr")
    SEGMENTATION_EXTENSIONS = (".seg.nrrd", ".seg.nhdr")

    def detect_format(self, path: str) -> DataFormat:
        if not path:
            return DataFormat.UNKNOWN

        if os.path.isdir(path):
            return DataFormat.DICOM

        lower_path = path.lower()
        if lower_path.endswith(self.SEGMENTATION_EXTENSIONS):
            return DataFormat.SEGMENTATION
        if lower_path.endswith(self.NIFTI_EXTENSIONS):
            return DataFormat.NIFTI
        if lower_path.endswith(self.NRRD_EXTENSIONS):
            return DataFormat.NRRD
        if lower_path.endswith(".dcm"):
            return DataFormat.DICOM

        return DataFormat.UNKNOWN

    @staticmethod
    def _basename_without_extension(path: str) -> str:
        name = os.path.basename(path)
        for extension in (".nii.gz", ".seg.nrrd", ".seg.nhdr", ".nii", ".nrrd", ".nhdr"):
            if name.lower().endswith(extension):
                return name[: -len(extension)]
        return os.path.splitext(name)[0]

    def load_volume(self, path: str, properties: dict[str, Any] | None = None, isolate: bool = False) -> Any:
        data_format = self.detect_format(path)
        if data_format == DataFormat.DICOM:
            return self.load_dicom(path)
        if data_format not in (DataFormat.NIFTI, DataFormat.NRRD):
            raise ValueError(f"Unsupported volume format for: {path}")

        load_properties = dict(properties or {})
        load_properties.setdefault("singleFile", True)
        load_properties.setdefault("show", True)
        load_properties["labelmap"] = False
        dest, tmp = self._load_source_path(path, isolate)
        try:
            node = self._load_volume_quietly(
                dest,
                labelmap=bool(load_properties.get("labelmap")),
                show=bool(load_properties.get("show", True)),
                single_file=bool(load_properties.get("singleFile", True)),
            )
        finally:
            self._defer_remove(tmp)
        if not node:
            raise RuntimeError(f"Failed to load volume: {path}")
        if not load_properties.get("labelmap"):
            node = self._as_scalar_volume(node)
        node.SetName(self._basename_without_extension(path))
        logging.info("Loaded volume %s from %s", node.GetName(), path)
        return node

    def _load_volume_quietly(
        self,
        path: str,
        labelmap: bool = False,
        show: bool = True,
        single_file: bool = True,
    ) -> Any:
        class_name = "vtkMRMLLabelMapVolumeNode" if labelmap else "vtkMRMLScalarVolumeNode"
        node = slicer.mrmlScene.AddNewNodeByClass(class_name)
        with _SlicerProgressPopupGuard():
            ok = self._read_with_storage(
                node,
                "vtkMRMLVolumeArchetypeStorageNode",
                path,
                single_file=single_file,
            )
        if not ok:
            slicer.mrmlScene.RemoveNode(node)
            return None
        try:
            node.CreateDefaultDisplayNodes()
        except Exception:
            pass
        if show and not labelmap:
            self.present_in_slice_views(node)
        return node

    def _read_with_storage(self, node: Any, storage_class: str, path: str, single_file: bool = True) -> bool:
        storage = slicer.mrmlScene.AddNewNodeByClass(storage_class)
        try:
            storage.SetFileName(path)
            if hasattr(storage, "SetSingleFile"):
                storage.SetSingleFile(1 if single_file else 0)
            if hasattr(storage, "SetUseCompression"):
                storage.SetUseCompression(1)
            return bool(storage.ReadData(node))
        except Exception:
            return False
        finally:
            slicer.mrmlScene.RemoveNode(storage)

    def _write_with_storage(self, node: Any, storage_class: str, path: str) -> bool:
        storage = slicer.mrmlScene.AddNewNodeByClass(storage_class)
        try:
            storage.SetFileName(path)
            if hasattr(storage, "SetUseCompression"):
                storage.SetUseCompression(1)
            return bool(storage.WriteData(node))
        except Exception:
            return False
        finally:
            slicer.mrmlScene.RemoveNode(storage)

    def present_in_slice_views(self, volume_node: Any, segmentation_node: Any = None) -> None:
        """Show the volume (and segmentation overlay) in the slice views, as Add Data does."""
        if volume_node is not None:
            try:
                volume_node.CreateDefaultDisplayNodes()
            except Exception:
                pass
            display = volume_node.GetDisplayNode() if hasattr(volume_node, "GetDisplayNode") else None
            if display is not None and hasattr(display, "SetAutoWindowLevel"):
                try:
                    display.SetAutoWindowLevel(1)
                except Exception:
                    pass
            self._set_background_volume(volume_node)
            self._fit_slices_to_volume(volume_node)
        if segmentation_node is not None:
            self._prepare_segmentation_display(segmentation_node)
            if volume_node is not None:
                setter = getattr(segmentation_node, "SetReferenceImageGeometryParameterFromVolumeNode", None)
                if callable(setter):
                    try:
                        setter(volume_node)
                    except Exception:
                        pass

    def _set_background_volume(self, node: Any) -> None:
        try:
            slicer.util.setSliceViewerLayers(background=node, fit=True)
            return
        except TypeError:
            try:
                slicer.util.setSliceViewerLayers(background=node)
            except Exception:
                pass
        except Exception:
            pass
        try:
            app_logic = slicer.app.applicationLogic()
            selection = app_logic.GetSelectionNode()
            selection.SetActiveVolumeID(node.GetID())
            app_logic.PropagateVolumeSelection(1)
        except Exception:
            pass

    def _fit_slices_to_volume(self, node: Any) -> None:
        if node is None:
            return
        try:
            layout = slicer.app.layoutManager()
            node_id = node.GetID()
            for view_name in layout.sliceViewNames():
                logic = layout.sliceWidget(view_name).sliceLogic()
                logic.GetSliceCompositeNode().SetBackgroundVolumeID(node_id)
                logic.FitSliceToAll()
        except Exception:
            pass

    def _prepare_segmentation_display(self, node: Any) -> None:
        if node is None:
            return
        try:
            node.CreateDefaultDisplayNodes()
        except Exception:
            pass
        display = node.GetDisplayNode() if hasattr(node, "GetDisplayNode") else None
        if display is None:
            return
        for name, value in (
            ("SetVisibility", True),
            ("SetVisibility2D", True),
            ("SetVisibility2DFill", True),
            ("SetVisibility2DOutline", True),
            ("SetVisibility3D", True),
        ):
            setter = getattr(display, name, None)
            if callable(setter):
                try:
                    setter(value)
                except Exception:
                    pass

    def _isolated_copy(self, path: str) -> tuple[str, str]:
        tmp = tempfile.mkdtemp(prefix="cv_load_")
        dest = os.path.join(tmp, os.path.basename(path))
        self._copy_keeping_ui_alive(path, dest)
        return dest, tmp

    def _load_source_path(self, path: str, isolate: bool) -> tuple[str, str | None]:
        if not isolate:
            return path, None
        dest, tmp = self._isolated_copy(path)
        return dest, tmp

    def _copy_keeping_ui_alive(self, src: str, dest: str, chunk_size: int = 8 * 1024 * 1024) -> None:
        with open(src, "rb") as incoming, open(dest, "wb") as outgoing:
            while True:
                block = incoming.read(chunk_size)
                if not block:
                    break
                outgoing.write(block)
                slicer.app.processEvents()
        try:
            shutil.copystat(src, dest)
        except OSError:
            pass

    def _defer_remove(self, path: str) -> None:
        if not path:
            return
        try:
            import qt
            qt.QTimer.singleShot(2500, lambda p=path: shutil.rmtree(p, ignore_errors=True))
        except Exception:
            shutil.rmtree(path, ignore_errors=True)

    def _as_scalar_volume(self, node: Any) -> Any:
        """Keep anatomical data as a scalar volume so it appears in 3D Volume."""
        if node is None or not node.IsA("vtkMRMLLabelMapVolumeNode"):
            return node
        import vtk

        scalar = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLScalarVolumeNode", node.GetName())
        scalar.CopyOrientation(node)
        if node.GetImageData() is not None:
            copied = vtk.vtkImageData()
            copied.DeepCopy(node.GetImageData())
            scalar.SetAndObserveImageData(copied)
        slicer.mrmlScene.RemoveNode(node)
        return scalar

    def _as_segmentation_node(self, node: Any, name: str) -> Any:
        """Turn a labelmap/volume into a real segmentation node (not a 3D volume)."""
        if node is None:
            return None
        if node.IsA("vtkMRMLSegmentationNode"):
            node.SetName(name)
            self._ensure_segment_id_names(node)
            self._prepare_segmentation_display(node)
            return node
        seg = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLSegmentationNode", name)
        try:
            seg.CreateDefaultDisplayNodes()
        except Exception:
            pass
        slicer.modules.segmentations.logic().ImportLabelmapToSegmentationNode(node, seg)
        slicer.mrmlScene.RemoveNode(node)
        self._ensure_segment_id_names(seg)
        self._prepare_segmentation_display(seg)
        return seg

    def inject_segmentation_from_file(self, segmentation_node: Any, path: str, isolate: bool = False) -> bool:
        """Read a version file into an existing segmentation node (same node, one Slicer read)."""
        if segmentation_node is None or not segmentation_node.IsA("vtkMRMLSegmentationNode"):
            return False
        dest, tmp = self._load_source_path(path, isolate)
        try:
            kept_colors = self._segment_colors_by_label(segmentation_node)
            display = segmentation_node.GetDisplayNode() if hasattr(segmentation_node, "GetDisplayNode") else None
            if display is None:
                try:
                    segmentation_node.CreateDefaultDisplayNodes()
                except Exception:
                    pass
            segmentation = segmentation_node.GetSegmentation()
            if segmentation is None:
                return False
            segmentation.RemoveAllSegments()
            with _SlicerProgressPopupGuard():
                ok = self._read_with_storage(
                    segmentation_node,
                    "vtkMRMLSegmentationStorageNode",
                    dest,
                    single_file=True,
                )
            if not ok:
                return False
            self._ensure_segment_id_names(segmentation_node)
            self._apply_kept_segment_colors(segmentation_node, kept_colors)
            return True
        except Exception:
            logging.exception("Could not inject segmentation from %s", path)
            return False
        finally:
            if tmp:
                self._defer_remove(tmp)

    def _segment_colors_by_label(self, segmentation_node: Any) -> dict[int, tuple[float, float, float]]:
        colors: dict[int, tuple[float, float, float]] = {}
        segmentation = segmentation_node.GetSegmentation()
        if segmentation is None:
            return colors
        for index in range(int(segmentation.GetNumberOfSegments())):
            segment_id = segmentation.GetNthSegmentID(index)
            segment = segmentation.GetSegment(segment_id)
            if segment is None:
                continue
            name = (segment.GetName() or "").strip()
            value = 0
            match = _SEGMENT_ID_NAME.match(name)
            if match:
                value = int(match.group(1))
            if value <= 0:
                value = self._segment_label_value(segmentation_node, segment, segment_id)
            if value <= 0:
                continue
            try:
                color = segment.GetColor()
                colors[value] = (float(color[0]), float(color[1]), float(color[2]))
            except Exception:
                continue
        return colors

    def _apply_kept_segment_colors(
        self,
        segmentation_node: Any,
        kept_colors: dict[int, tuple[float, float, float]],
    ) -> None:
        segmentation = segmentation_node.GetSegmentation()
        if segmentation is None:
            return
        display = segmentation_node.GetDisplayNode() if hasattr(segmentation_node, "GetDisplayNode") else None
        for index in range(int(segmentation.GetNumberOfSegments())):
            segment_id = segmentation.GetNthSegmentID(index)
            segment = segmentation.GetSegment(segment_id)
            if segment is None:
                continue
            name = (segment.GetName() or "").strip()
            value = 0
            match = _SEGMENT_ID_NAME.match(name)
            if match:
                value = int(match.group(1))
            if value <= 0:
                value = self._segment_label_value(segmentation_node, segment, segment_id)
            if value > 0 and value in kept_colors:
                red, green, blue = kept_colors[value]
                segment.SetColor(red, green, blue)
                continue
            generator = getattr(display, "GenerateSegmentColor", None) if display is not None else None
            if not callable(generator):
                continue
            rgb = [0.5, 0.5, 0.5]
            try:
                generator(rgb)
                segment.SetColor(float(rgb[0]), float(rgb[1]), float(rgb[2]))
            except Exception:
                continue

    def _ensure_segment_id_names(self, seg_node: Any) -> None:
        segmentation = seg_node.GetSegmentation() if seg_node is not None else None
        if segmentation is None:
            return
        for index in range(int(segmentation.GetNumberOfSegments())):
            segment_id = segmentation.GetNthSegmentID(index)
            segment = segmentation.GetSegment(segment_id)
            if segment is None:
                continue
            name = (segment.GetName() or "").strip()
            if _SEGMENT_ID_NAME.match(name):
                continue
            value = self._segment_label_value(seg_node, segment, segment_id)
            if value <= 0:
                match = re.search(r"(\d+)$", name)
                if match:
                    value = int(match.group(1))
            if value > 0:
                segment.SetName("Segment_%d" % value)
                setter = getattr(segment, "SetLabelValue", None)
                if callable(setter):
                    try:
                        setter(value)
                    except Exception:
                        pass

    def _segment_label_value(self, seg_node: Any, segment: Any, segment_id: str) -> int:
        getter = getattr(segment, "GetLabelValue", None)
        if callable(getter):
            try:
                value = int(getter() or 0)
                if value > 0:
                    return value
            except Exception:
                pass
        try:
            import vtk

            image = slicer.vtkOrientedImageData()
            reader = getattr(seg_node, "GetBinaryLabelmapRepresentation", None)
            if not callable(reader) or not reader(segment_id, image):
                return 0
            acc = vtk.vtkImageAccumulate()
            acc.SetInputData(image)
            acc.IgnoreZeroOn()
            acc.Update()
            lo = acc.GetMin()
            value = int(lo[0] if lo is not None and hasattr(lo, "__getitem__") else 0)
            return value if value > 0 else 0
        except Exception:
            return 0

    def discover_project_files(self, folder: str) -> dict[str, Any]:
        empty = {
            "volume": None,
            "segmentation": None,
            "segmentation_store": False,
            "ontologies": [],
        }
        if not folder or not os.path.isdir(folder):
            return empty
        volumes = []
        segmentations = []
        unlabeled = []
        ontologies = []
        for name in sorted(os.listdir(folder)):
            if name.startswith("."):
                continue
            path = os.path.join(folder, name)
            if not os.path.isfile(path):
                continue
            lower = name.lower()
            if lower.endswith(".json"):
                ontologies.append(path)
                continue
            if lower.endswith(self.SEGMENTATION_EXTENSIONS):
                segmentations.append(path)
                continue
            if lower.endswith(self.NIFTI_EXTENSIONS) or lower.endswith(self.NRRD_EXTENSIONS):
                if self._filename_is_segmentation(lower):
                    segmentations.append(path)
                elif self._filename_is_volume(lower):
                    volumes.append(path)
                else:
                    unlabeled.append(path)
        if unlabeled:
            extra_volume, extra_segmentation = self._split_unlabeled_nifti(unlabeled, bool(volumes), bool(segmentations))
            if extra_volume:
                volumes.append(extra_volume)
            if extra_segmentation:
                segmentations.append(extra_segmentation)
        from CollaborativeVersioningLib import SegmentationCubes

        has_store = SegmentationCubes.store_exists(folder)
        return {
            "volume": volumes[0] if volumes else None,
            "segmentation": segmentations[0] if segmentations else None,
            "segmentation_store": has_store,
            "ontologies": ontologies,
        }

    def save_segmentation_cubes(self, folder: str, labelmap_node: Any, stem: str) -> dict[str, Any]:
        """Write ``.cv_seg`` blocks + manifest from a labelmap; drop legacy root NIfTI."""
        from CollaborativeVersioningLib import SegmentationCubes

        if labelmap_node is None:
            raise ValueError("Segmentation labelmap is missing.")
        grid = slicer.util.arrayFromVolume(labelmap_node)
        geometry = SegmentationCubes.geometry_from_volume(labelmap_node)
        stats = SegmentationCubes.write_store(folder, grid, geometry)
        SegmentationCubes.remove_legacy_segmentation_file(folder, stem)
        logging.info(
            "Saved segmentation cubes in %s (written=%s reused=%s empty=%s)",
            folder,
            stats.get("written"),
            stats.get("reused"),
            stats.get("skipped_empty"),
        )
        return stats

    def _labelmap_from_cube_store(
        self,
        folder: str,
        name: str,
        timings: dict[str, float] | None = None,
    ) -> Any:
        """Rebuild cube store into a temporary labelmap node (RAM only, no cache file)."""
        from CollaborativeVersioningLib import SegmentationCubes

        t0 = time.perf_counter()
        grid, geometry = SegmentationCubes.read_store(folder)
        if timings is not None:
            timings["read_store_ms"] = (time.perf_counter() - t0) * 1000.0
        labelmap = slicer.mrmlScene.AddNewNodeByClass(
            "vtkMRMLLabelMapVolumeNode",
            name or "segmentation",
        )
        try:
            t1 = time.perf_counter()
            slicer.util.updateVolumeFromArray(labelmap, grid)
            SegmentationCubes.apply_geometry(labelmap, geometry)
            if timings is not None:
                timings["labelmap_fill_ms"] = (time.perf_counter() - t1) * 1000.0
        except Exception:
            slicer.mrmlScene.RemoveNode(labelmap)
            raise
        return labelmap

    def _find_segment_id_for_label(self, segmentation_node: Any, label: int) -> str | None:
        """Return existing segment ID for ontology label, or None if absent."""
        segmentation = segmentation_node.GetSegmentation()
        if segmentation is None or int(label) <= 0:
            return None
        want = "Segment_%d" % int(label)
        if segmentation.GetSegment(want) is not None:
            return want
        by_name = getattr(segmentation, "GetSegmentIdBySegmentName", None)
        if callable(by_name):
            try:
                found = str(by_name(want) or "").strip()
                if found and segmentation.GetSegment(found) is not None:
                    return found
            except Exception:
                pass
        for index in range(int(segmentation.GetNumberOfSegments())):
            segment_id = segmentation.GetNthSegmentID(index)
            segment = segmentation.GetSegment(segment_id)
            if segment is None:
                continue
            name = (segment.GetName() or "").strip()
            match = _SEGMENT_ID_NAME.match(name)
            if match and int(match.group(1)) == int(label):
                return str(segment_id)
            value = self._segment_label_value(segmentation_node, segment, segment_id)
            if value == int(label):
                return str(segment_id)
        return None

    def _prepare_updated_segment_import(
        self,
        labelmap: Any,
        segmentation_node: Any,
    ) -> tuple[Any, list[int]]:
        """Remap ontology voxels → 1..N and build updatedSegmentIDs for Import update.

        Returns ``(vtkStringArray ids, ontology_labels ordered)``.
        """
        import numpy as np
        import vtk

        grid = slicer.util.arrayFromVolume(labelmap)
        labels = sorted({int(v) for v in np.unique(grid) if int(v) > 0})
        ids = vtk.vtkStringArray()
        if not labels:
            return ids, []
        max_lab = int(labels[-1])
        lut = np.zeros(max_lab + 1, dtype=grid.dtype)
        for index, label in enumerate(labels):
            lut[int(label)] = index + 1
            existing = self._find_segment_id_for_label(segmentation_node, int(label))
            ids.InsertNextValue(existing if existing else ("Segment_%d" % int(label)))
        slicer.util.updateVolumeFromArray(labelmap, lut[grid])
        return ids, labels

    def _restore_ontology_segment_labels(
        self,
        segmentation_node: Any,
        segment_ids: Any,
        ontology_labels: list[int],
    ) -> None:
        """After update-Import, voxels are 1..N and LabelValue is 1..N.

        Remap the shared binary labelmap back to ontology IDs, then set each
        segment LabelValue/name to the ontology id. Without the voxel remap,
        LabelValue (e.g. 896) no longer matches image values (1..N) and the
        2D display collapses to a single wrong color (often all red).
        """
        import numpy as np

        segmentation = segmentation_node.GetSegmentation()
        if segmentation is None:
            return
        count = min(int(segment_ids.GetNumberOfValues()), len(ontology_labels))
        if count <= 0:
            return

        rep_name = slicer.vtkSegmentationConverter.GetSegmentationBinaryLabelmapRepresentationName()
        shared_image = None
        for index in range(count):
            segment = segmentation.GetSegment(str(segment_ids.GetValue(index)))
            if segment is None:
                continue
            rep = segment.GetRepresentation(rep_name)
            shared_image = slicer.vtkOrientedImageData.SafeDownCast(rep)
            if shared_image is not None:
                break

        if shared_image is not None and shared_image.GetPointData() is not None:
            scalars = shared_image.GetPointData().GetScalars()
            if scalars is not None:
                from vtk.util import numpy_support

                max_ontology = max(int(v) for v in ontology_labels)
                try:
                    slicer.vtkOrientedImageDataResample.CastImageForValue(
                        shared_image,
                        max_ontology,
                    )
                except Exception:
                    logging.exception("Could not cast shared labelmap for ontology ids")
                # Slicer 5.10 has no slicer.util.arrayFromImage — use VTK numpy bridge.
                scalars = shared_image.GetPointData().GetScalars()
                if scalars is None:
                    raise RuntimeError("Shared labelmap has no scalars after cast.")
                arr = numpy_support.vtk_to_numpy(scalars)
                flat_max = int(arr.max()) if arr.size else 0
                lut = np.zeros(max(flat_max, count) + 1, dtype=np.uint16)
                for index, label in enumerate(ontology_labels[:count]):
                    if index + 1 < len(lut):
                        lut[index + 1] = int(label)
                idx = np.clip(arr.astype(np.int64, copy=False), 0, len(lut) - 1)
                remapped = lut[idx].astype(arr.dtype, copy=False)
                arr[:] = remapped
                scalars.Modified()
                shared_image.Modified()

        for index in range(count):
            segment_id = str(segment_ids.GetValue(index))
            label = int(ontology_labels[index])
            segment = segmentation.GetSegment(segment_id)
            if segment is None:
                continue
            try:
                segment.SetName("Segment_%d" % label)
            except Exception:
                pass
            setter = getattr(segment, "SetLabelValue", None)
            if callable(setter):
                try:
                    setter(label)
                except Exception:
                    pass
        try:
            segmentation.Modified()
        except Exception:
            pass
        try:
            segmentation_node.Modified()
        except Exception:
            pass

    def _remove_segments_absent_from_labels(
        self,
        segmentation_node: Any,
        keep_labels: set[int],
    ) -> int:
        """Remove segments whose ontology id is not in keep_labels. Returns remove count."""
        segmentation = segmentation_node.GetSegmentation()
        if segmentation is None:
            return 0
        to_remove: list[str] = []
        for index in range(int(segmentation.GetNumberOfSegments())):
            segment_id = segmentation.GetNthSegmentID(index)
            segment = segmentation.GetSegment(segment_id)
            if segment is None:
                continue
            name = (segment.GetName() or "").strip()
            match = _SEGMENT_ID_NAME.match(name)
            if match:
                value = int(match.group(1))
            else:
                value = self._segment_label_value(segmentation_node, segment, segment_id)
            if value <= 0 or value not in keep_labels:
                to_remove.append(str(segment_id))
        for segment_id in to_remove:
            try:
                segmentation.RemoveSegment(segment_id)
            except Exception:
                logging.exception("Could not remove obsolete segment %s", segment_id)
        return len(to_remove)

    def inject_segmentation_from_cubes(
        self,
        segmentation_node: Any,
        folder: str,
    ) -> tuple[bool, dict[str, float]]:
        """Load ``.cv_seg`` into an existing segmentation node (RAM only).

        Prefers Import + ``updatedSegmentIDs`` (update/create in place, no RemoveAll).
        Falls back to RemoveAll + Import add if the update path fails.

        Returns ``(ok, timings_ms)`` with per-step durations for Switch profiling.
        """
        timings: dict[str, float] = {}
        total_t0 = time.perf_counter()
        if segmentation_node is None or not segmentation_node.IsA("vtkMRMLSegmentationNode"):
            return False, timings
        labelmap = None
        render_paused = False
        try:
            t0 = time.perf_counter()
            kept_colors = self._segment_colors_by_label(segmentation_node)
            try:
                segmentation_node.CreateDefaultDisplayNodes()
            except Exception:
                pass
            segmentation = segmentation_node.GetSegmentation()
            if segmentation is None:
                return False, timings
            timings["prepare_ms"] = (time.perf_counter() - t0) * 1000.0
            labelmap = self._labelmap_from_cube_store(
                folder,
                "%s_labelmap" % (segmentation_node.GetName() or "segmentation"),
                timings=timings,
            )

            t_remap = time.perf_counter()
            updated_ids, ontology_labels = self._prepare_updated_segment_import(
                labelmap,
                segmentation_node,
            )
            timings["RemapLabels_ms"] = (time.perf_counter() - t_remap) * 1000.0
            keep_labels = set(ontology_labels)

            # Batch MRML / segment events and pause slice redraws (2D overlays too).
            try:
                slicer.app.pauseRender()
                render_paused = True
            except Exception:
                render_paused = False
            modify = segmentation_node.StartModify()
            was_segment_modified = True
            ok = False
            used_update = False
            setter = getattr(segmentation, "SetSegmentModifiedEnabled", None)
            if callable(setter):
                try:
                    was_segment_modified = bool(setter(False))
                except Exception:
                    was_segment_modified = True
            try:
                if ontology_labels:
                    t2 = time.perf_counter()
                    with _SlicerProgressPopupGuard():
                        try:
                            ok = bool(
                                slicer.vtkSlicerSegmentationsModuleLogic.ImportLabelmapToSegmentationNode(
                                    labelmap,
                                    segmentation_node,
                                    updated_ids,
                                )
                            )
                        except TypeError:
                            ok = bool(
                                slicer.modules.segmentations.logic().ImportLabelmapToSegmentationNode(
                                    labelmap,
                                    segmentation_node,
                                    updated_ids,
                                )
                            )
                    timings["ImportLabelmap_ms"] = (time.perf_counter() - t2) * 1000.0
                    if ok:
                        try:
                            self._restore_ontology_segment_labels(
                                segmentation_node,
                                updated_ids,
                                ontology_labels,
                            )
                            t_rm = time.perf_counter()
                            removed = self._remove_segments_absent_from_labels(
                                segmentation_node,
                                keep_labels,
                            )
                            timings["RemoveObsolete_ms"] = (time.perf_counter() - t_rm) * 1000.0
                            timings["RemoveObsolete_count"] = float(removed)
                            used_update = True
                        except Exception as restore_exc:
                            # Keep same node: fall through to RemoveAll+Import below.
                            ok = False
                            used_update = False
                            timings["_inject_error"] = "restore/obsolete: %s" % restore_exc
                            logging.exception(
                                "Ontology restore after update-import failed (%s)",
                                folder,
                            )
                else:
                    t1 = time.perf_counter()
                    segmentation.RemoveAllSegments()
                    timings["RemoveAllSegments_ms"] = (time.perf_counter() - t1) * 1000.0
                    ok = True

                if not ok:
                    # Fallback on the SAME node (do not create a second segmentation).
                    logging.warning(
                        "Segment update import failed; falling back to RemoveAll+Import (%s)",
                        folder,
                    )
                    if "_inject_error" not in timings:
                        timings["_inject_error"] = "update ImportLabelmap returned false"
                    try:
                        slicer.mrmlScene.RemoveNode(labelmap)
                    except Exception:
                        pass
                    labelmap = self._labelmap_from_cube_store(
                        folder,
                        "%s_labelmap" % (segmentation_node.GetName() or "segmentation"),
                        timings=None,
                    )
                    t1 = time.perf_counter()
                    segmentation.RemoveAllSegments()
                    timings["RemoveAllSegments_ms"] = (time.perf_counter() - t1) * 1000.0
                    t2 = time.perf_counter()
                    with _SlicerProgressPopupGuard():
                        ok = bool(
                            slicer.modules.segmentations.logic().ImportLabelmapToSegmentationNode(
                                labelmap,
                                segmentation_node,
                            )
                        )
                    timings["ImportLabelmap_ms"] = (time.perf_counter() - t2) * 1000.0
                    used_update = False
            finally:
                if callable(setter):
                    try:
                        setter(was_segment_modified)
                    except Exception:
                        pass
                try:
                    segmentation_node.EndModify(modify)
                except Exception:
                    pass
            if not ok:
                return False, timings
            t3 = time.perf_counter()
            self._ensure_segment_id_names(segmentation_node)
            self._apply_kept_segment_colors(segmentation_node, kept_colors)
            self._prepare_segmentation_display(segmentation_node)
            timings["finalize_ms"] = (time.perf_counter() - t3) * 1000.0
            timings["inject_update"] = 1.0 if used_update else 0.0
            return True, timings
        except Exception:
            logging.exception("Could not inject segmentation cubes from %s", folder)
            return False, timings
        finally:
            # Include slice redraw in TOTAL (pauseRender defers it until here).
            if render_paused:
                t_resume = time.perf_counter()
                try:
                    slicer.app.resumeRender()
                    slicer.app.processEvents()
                except Exception:
                    pass
                timings["resumeRender_ms"] = (time.perf_counter() - t_resume) * 1000.0
            if labelmap is not None:
                try:
                    t4 = time.perf_counter()
                    slicer.mrmlScene.RemoveNode(labelmap)
                    timings["cleanup_labelmap_ms"] = (time.perf_counter() - t4) * 1000.0
                except Exception:
                    pass
            timings["total_ms"] = (time.perf_counter() - total_t0) * 1000.0

    def load_segmentation_from_cubes(
        self,
        folder: str,
        stem: str = "project",
    ) -> tuple[Any, dict[str, float]]:
        """Create a segmentation node from ``.cv_seg`` in memory (no cache NIfTI)."""
        timings: dict[str, float] = {}
        total_t0 = time.perf_counter()
        name = "%s_segmentation" % ((stem or "project").strip() or "project")
        labelmap = self._labelmap_from_cube_store(folder, name, timings=timings)
        t0 = time.perf_counter()
        node = self._as_segmentation_node(labelmap, name)
        timings["ImportLabelmap_ms"] = (time.perf_counter() - t0) * 1000.0
        timings["total_ms"] = (time.perf_counter() - total_t0) * 1000.0
        return node, timings

    @staticmethod
    def _filename_is_segmentation(lower_name: str) -> bool:
        return (
            "_segmentation" in lower_name
            or "segmentation" in lower_name
            or "_labelmap" in lower_name
            or "labelmap" in lower_name
            or lower_name.endswith("_seg.nii")
            or lower_name.endswith("_seg.nii.gz")
        )

    @staticmethod
    def _filename_is_volume(lower_name: str) -> bool:
        return "_volume" in lower_name or "_reference" in lower_name

    def _split_unlabeled_nifti(
        self,
        unlabeled: list[str],
        has_volume: bool,
        has_segmentation: bool,
    ) -> tuple[str | None, str | None]:
        if has_volume and has_segmentation:
            return None, None
        if len(unlabeled) == 1:
            if has_volume:
                return None, unlabeled[0]
            return unlabeled[0], None
        bases = [(self._basename_without_extension(path).lower(), path) for path in unlabeled]
        for volume_name, volume_path in bases:
            for seg_name, seg_path in bases:
                if volume_path != seg_path and seg_name.startswith(volume_name) and seg_name != volume_name:
                    extra_volume = None if has_volume else volume_path
                    extra_segmentation = None if has_segmentation else seg_path
                    return extra_volume, extra_segmentation
        if has_volume:
            return None, unlabeled[0]
        if has_segmentation:
            return unlabeled[0], None
        likely_seg = max(unlabeled, key=self._labelmap_likelihood)
        volume_path = next((path for path in unlabeled if path != likely_seg), unlabeled[0])
        return volume_path, likely_seg

    def _labelmap_likelihood(self, path: str) -> float:
        """Cheap guess without reading voxels (name hints + smaller file ≈ labelmap)."""
        score = 0.0
        lower = os.path.basename(path).lower()
        for hint in ("seg", "label", "mask", "annot"):
            if hint in lower:
                score += 10.0
        try:
            # Volumes are usually much larger than labelmaps / segmentations.
            size_mib = float(os.path.getsize(path)) / (1024.0 * 1024.0)
            score += 1.0 / (1.0 + size_mib)
        except OSError:
            pass
        return score

    def load_dicom(self, dicom_path: str) -> list[Any]:
        from DICOMLib import DICOMUtils

        if os.path.isfile(dicom_path):
            dicom_dir = os.path.dirname(dicom_path)
        else:
            dicom_dir = dicom_path

        loaded_nodes: list[Any] = []
        with DICOMUtils.TemporaryDICOMDatabase() as db:
            DICOMUtils.importDicom(dicom_dir, db)

            for patient_uid in db.patients():
                patient_nodes = DICOMUtils.loadPatientByUID(patient_uid)
                if patient_nodes:
                    loaded_nodes.extend(patient_nodes)

        if not loaded_nodes:
            raise RuntimeError(f"No DICOM volume loaded from: {dicom_path}")

        logging.info("Loaded %d node(s) from DICOM path %s", len(loaded_nodes), dicom_path)
        return loaded_nodes

    def load_segmentation(self, path: str, isolate: bool = False) -> Any:
        data_format = self.detect_format(path)
        if data_format not in (DataFormat.SEGMENTATION, DataFormat.NIFTI, DataFormat.NRRD):
            raise ValueError(f"Unsupported segmentation format for: {path}")

        segmentation_name = self._basename_without_extension(path)
        dest, tmp = self._load_source_path(path, isolate)
        try:
            node = None
            with _SlicerProgressPopupGuard():
                logic = slicer.modules.segmentations.logic()
                try:
                    node = logic.LoadSegmentationFromFile(dest, True, segmentation_name)
                except TypeError:
                    node = logic.LoadSegmentationFromFile(dest)
            if not node:
                labelmap = self._load_volume_quietly(
                    dest, labelmap=True, show=False, single_file=True
                )
                node = self._as_segmentation_node(labelmap, segmentation_name)
            else:
                self._ensure_segment_id_names(node)
                self._prepare_segmentation_display(node)
        finally:
            self._defer_remove(tmp)
        if not node:
            raise RuntimeError(f"Failed to load segmentation: {path}")
        node.SetName(segmentation_name)
        logging.info("Loaded segmentation %s from %s", node.GetName(), path)
        return node

    def remove_scene_nodes_by_names(self, names: set[str]) -> None:
        if not names:
            return
        scene = slicer.mrmlScene
        for class_name in (
            "vtkMRMLScalarVolumeNode",
            "vtkMRMLLabelMapVolumeNode",
            "vtkMRMLSegmentationNode",
        ):
            for index in range(scene.GetNumberOfNodesByClass(class_name) - 1, -1, -1):
                node = scene.GetNthNodeByClass(index, class_name)
                if node and node.GetName() in names:
                    scene.RemoveNode(node)

    def save_volume(self, node: Any, path: str) -> str:
        data_format = self.detect_format(path)
        if data_format not in (DataFormat.NIFTI, DataFormat.NRRD):
            raise ValueError(f"Unsupported export format for volume: {path}")

        with _SlicerProgressPopupGuard():
            success = self._write_with_storage(node, "vtkMRMLVolumeArchetypeStorageNode", path)
        if not success:
            raise RuntimeError(f"Failed to save volume to: {path}")
        logging.info("Saved volume %s to %s", node.GetName(), path)
        return path
