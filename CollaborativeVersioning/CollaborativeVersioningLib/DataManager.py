"""
E3 - Gestionnaire de données pour formats 3D (NIfTI, NRRD, DICOM).

Encapsule les API Slicer pour charger/exporter volumes et segmentations
utilisés dans le workflow de versioning collaboratif.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from enum import Enum
from typing import Any

import slicer


class DataFormat(Enum):
    NIFTI = "nifti"
    NRRD = "nrrd"
    DICOM = "dicom"
    SEGMENTATION = "segmentation"
    UNKNOWN = "unknown"


@dataclass
class FormatInfo:
    format: DataFormat
    extension: str
    description: str


SUPPORTED_FORMATS = {
    DataFormat.NIFTI: FormatInfo(DataFormat.NIFTI, ".nii.gz", "NIfTI volume"),
    DataFormat.NRRD: FormatInfo(DataFormat.NRRD, ".nrrd", "NRRD volume"),
    DataFormat.DICOM: FormatInfo(DataFormat.DICOM, "", "DICOM directory"),
    DataFormat.SEGMENTATION: FormatInfo(DataFormat.SEGMENTATION, ".seg.nrrd", "Segmentation labelmap"),
}


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

    def get_supported_formats(self) -> list[dict[str, str]]:
        return [
            {
                "id": fmt.value,
                "extension": info.extension,
                "description": info.description,
            }
            for fmt, info in SUPPORTED_FORMATS.items()
            if fmt != DataFormat.UNKNOWN
        ]

    @staticmethod
    def _basename_without_extension(path: str) -> str:
        name = os.path.basename(path)
        for extension in (".nii.gz", ".seg.nrrd", ".seg.nhdr", ".nii", ".nrrd", ".nhdr"):
            if name.lower().endswith(extension):
                return name[: -len(extension)]
        return os.path.splitext(name)[0]

    def load_volume(self, path: str, properties: dict[str, Any] | None = None) -> Any:
        data_format = self.detect_format(path)
        if data_format == DataFormat.DICOM:
            return self.load_dicom(path)
        if data_format not in (DataFormat.NIFTI, DataFormat.NRRD):
            raise ValueError(f"Unsupported volume format for: {path}")

        load_properties = dict(properties or {})
        node = slicer.util.loadVolume(path, load_properties)
        if not node:
            raise RuntimeError(f"Failed to load volume: {path}")
        node.SetName(self._basename_without_extension(path))
        logging.info("Loaded volume %s from %s", node.GetName(), path)
        return node

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

    def load_segmentation(self, path: str) -> Any:
        data_format = self.detect_format(path)
        if data_format not in (DataFormat.SEGMENTATION, DataFormat.NIFTI, DataFormat.NRRD):
            raise ValueError(f"Unsupported segmentation format for: {path}")

        segmentation_name = self._basename_without_extension(path)
        node = slicer.util.loadSegmentation(
            path,
            {"name": segmentation_name, "singleFile": True},
        )
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

        success = slicer.util.saveNode(node, path)
        if not success:
            raise RuntimeError(f"Failed to save volume to: {path}")
        logging.info("Saved volume %s to %s", node.GetName(), path)
        return path

    def save_segmentation(self, node: Any, path: str) -> str:
        lower_path = path.lower()
        if not lower_path.endswith((".nrrd", ".nhdr", ".nii", ".nii.gz")):
            path = f"{path}.seg.nrrd"

        success = slicer.util.saveNode(node, path)
        if not success:
            raise RuntimeError(f"Failed to save segmentation to: {path}")
        logging.info("Saved segmentation %s to %s", node.GetName(), path)
        return path

    def export_node(self, node: Any, path: str) -> str:
        node_class = node.GetClassName() if node else ""
        if "Segmentation" in node_class or "LabelMap" in node_class:
            return self.save_segmentation(node, path)
        return self.save_volume(node, path)

    def get_scene_export_candidates(self) -> dict[str, list[Any]]:
        scene = slicer.mrmlScene
        return {
            "volumes": list(scene.GetNodesByClass("vtkMRMLScalarVolumeNode")),
            "segmentations": list(scene.GetNodesByClass("vtkMRMLSegmentationNode")),
        }

    def build_export_path(self, output_dir: str, node_name: str, data_format: DataFormat) -> str:
        safe_name = "".join(c if c.isalnum() or c in "-_" else "_" for c in node_name)
        if data_format == DataFormat.NIFTI:
            return os.path.join(output_dir, f"{safe_name}.nii.gz")
        if data_format == DataFormat.SEGMENTATION:
            return os.path.join(output_dir, f"{safe_name}.seg.nrrd")
        return os.path.join(output_dir, f"{safe_name}.nrrd")
