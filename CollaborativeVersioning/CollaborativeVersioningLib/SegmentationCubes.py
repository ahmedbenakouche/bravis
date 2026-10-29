"""Chunked segmentation store: 64^3 cubes named by xxHash64 content.

Layout (versioned in Git):
  .cv_seg/
    manifest.json          # shape, geometry, chunk size, hash per cube key
    blocks/ab/abcdef...    # immutable zlib-compressed cube bytes (no extension)

Open/Switch rebuilds a labelmap in RAM and imports it into the segmentation node
(no gitignored NIfTI cache).

xxHash is always over the uncompressed uint16 cube bytes.
Legacy ``*_segmentation.nii.gz`` at the project root is no longer written on Save.
Open/Switch still loads it when no cube store exists (old commits).
"""

from __future__ import annotations

import json
import logging
import os
import zlib
from typing import Any

import numpy as np

try:
    import xxhash
except ImportError as exc:  # pragma: no cover - installed in Slicer; optional for host Python
    xxhash = None  # type: ignore[assignment]
    _XXHASH_IMPORT_ERROR = exc
else:
    _XXHASH_IMPORT_ERROR = None

STORE_DIRNAME = ".cv_seg"
BLOCKS_DIRNAME = "blocks"
MANIFEST_NAME = "manifest.json"
CHUNK_SIZE = 64
FORMAT_VERSION = 2
BLOCK_ENCODING = "zlib"
ZLIB_LEVEL = 6
GRID_DTYPE = np.dtype("<u2")  # little-endian uint16
_ZERO_HASH_CACHE: dict[tuple[int, int, int], str] = {}


def _require_xxhash() -> None:
    if xxhash is None:
        raise RuntimeError(
            "The xxhash package is required for cube segmentation storage. "
            "Install it in 3D Slicer's Python (import xxhash must work)."
        ) from _XXHASH_IMPORT_ERROR


def store_dir(folder: str) -> str:
    return os.path.join(folder, STORE_DIRNAME)


def manifest_path(folder: str) -> str:
    return os.path.join(store_dir(folder), MANIFEST_NAME)


def blocks_dir(folder: str) -> str:
    return os.path.join(store_dir(folder), BLOCKS_DIRNAME)


def block_file_path(folder: str, digest: str) -> str:
    digest = str(digest or "").strip().lower()
    if len(digest) < 2:
        raise ValueError("Invalid block hash.")
    return os.path.join(blocks_dir(folder), digest[:2], digest)


def store_exists(folder: str) -> bool:
    return bool(folder) and os.path.isfile(manifest_path(folder))


def make_key(cz: int, cy: int, cx: int) -> str:
    return "%d.%d.%d" % (int(cz), int(cy), int(cx))


def parse_key(key: str) -> tuple[int, int, int]:
    text = str(key or "").strip()
    parts = text.split(".")
    if len(parts) != 3:
        raise ValueError("Invalid cube key: %s" % key)
    try:
        return int(parts[0]), int(parts[1]), int(parts[2])
    except ValueError as exc:
        raise ValueError("Invalid cube key: %s" % key) from exc


def chunk_counts(shape: tuple[int, ...], chunk: int = CHUNK_SIZE) -> tuple[int, int, int]:
    z, y, x = (int(shape[0]), int(shape[1]), int(shape[2]))
    c = max(1, int(chunk))
    return (
        (z + c - 1) // c,
        (y + c - 1) // c,
        (x + c - 1) // c,
    )


def cube_slices(
    shape: tuple[int, ...],
    key: str | tuple[int, int, int],
    chunk: int = CHUNK_SIZE,
) -> tuple[slice, slice, slice]:
    cz, cy, cx = parse_key(key) if isinstance(key, str) else key
    c = max(1, int(chunk))
    z, y, x = (int(shape[0]), int(shape[1]), int(shape[2]))
    z0, y0, x0 = cz * c, cy * c, cx * c
    return (
        slice(z0, min(z0 + c, z)),
        slice(y0, min(y0 + c, y)),
        slice(x0, min(x0 + c, x)),
    )


def cube_shape(
    shape: tuple[int, ...],
    key: str | tuple[int, int, int],
    chunk: int = CHUNK_SIZE,
) -> tuple[int, int, int]:
    zsl, ysl, xsl = cube_slices(shape, key, chunk)
    return (zsl.stop - zsl.start, ysl.stop - ysl.start, xsl.stop - xsl.start)


def all_keys(shape: tuple[int, ...], chunk: int = CHUNK_SIZE) -> list[str]:
    nz, ny, nx = chunk_counts(shape, chunk)
    return [make_key(cz, cy, cx) for cz in range(nz) for cy in range(ny) for cx in range(nx)]


def hash_cube(block: np.ndarray) -> str:
    """xxHash64 hex digest of the cube's little-endian bytes (C-order)."""
    _require_xxhash()
    arr = np.ascontiguousarray(block, dtype=GRID_DTYPE)
    return xxhash.xxh64(arr.tobytes()).hexdigest()


def zero_hash(shape: tuple[int, int, int]) -> str:
    key = (int(shape[0]), int(shape[1]), int(shape[2]))
    cached = _ZERO_HASH_CACHE.get(key)
    if cached is not None:
        return cached
    digest = hash_cube(np.zeros(key, dtype=GRID_DTYPE))
    _ZERO_HASH_CACHE[key] = digest
    return digest


def as_grid(array: Any) -> np.ndarray:
    if array is None:
        raise ValueError("Segmentation grid is missing.")
    grid = np.asarray(array)
    if grid.ndim != 3:
        raise ValueError("Segmentation grid must be 3D.")
    if grid.size and int(grid.min()) < 0:
        raise ValueError("Segmentation labels cannot be negative.")
    max_u16 = int(np.iinfo(np.uint16).max)
    if grid.size and int(grid.max()) > max_u16:
        raise ValueError("A segment ID is too large to store.")
    return np.ascontiguousarray(grid, dtype=GRID_DTYPE)


def geometry_from_volume(volume_node: Any) -> dict[str, Any]:
    """Capture origin / spacing / IJK→RAS directions from a Slicer volume node."""
    geometry: dict[str, Any] = {
        "origin": [0.0, 0.0, 0.0],
        "spacing": [1.0, 1.0, 1.0],
        "directions": [1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0],
    }
    if volume_node is None:
        return geometry
    try:
        origin = volume_node.GetOrigin()
        geometry["origin"] = [float(origin[0]), float(origin[1]), float(origin[2])]
    except Exception:
        pass
    try:
        spacing = volume_node.GetSpacing()
        geometry["spacing"] = [float(spacing[0]), float(spacing[1]), float(spacing[2])]
    except Exception:
        pass
    try:
        import vtk

        matrix = vtk.vtkMatrix4x4()
        volume_node.GetIJKToRASDirectionMatrix(matrix)
        directions = []
        for row in range(3):
            for col in range(3):
                directions.append(float(matrix.GetElement(row, col)))
        geometry["directions"] = directions
    except Exception:
        logging.exception("Could not read segmentation IJKToRAS directions")
    return geometry


def apply_geometry(volume_node: Any, geometry: dict[str, Any] | None) -> None:
    if volume_node is None:
        return
    geo = dict(geometry or {})
    try:
        origin = geo.get("origin") or [0.0, 0.0, 0.0]
        volume_node.SetOrigin(float(origin[0]), float(origin[1]), float(origin[2]))
    except Exception:
        pass
    try:
        spacing = geo.get("spacing") or [1.0, 1.0, 1.0]
        volume_node.SetSpacing(float(spacing[0]), float(spacing[1]), float(spacing[2]))
    except Exception:
        pass
    directions = geo.get("directions")
    if not directions or len(directions) != 9:
        return
    try:
        import vtk

        matrix = vtk.vtkMatrix4x4()
        matrix.Identity()
        for row in range(3):
            for col in range(3):
                matrix.SetElement(row, col, float(directions[row * 3 + col]))
        volume_node.SetIJKToRASDirectionMatrix(matrix)
    except Exception:
        logging.exception("Could not apply segmentation geometry")


def _keep_ui_alive() -> None:
    try:
        import slicer

        slicer.app.processEvents()
    except Exception:
        pass


def build_manifest(grid: np.ndarray, geometry: dict[str, Any] | None = None) -> dict[str, Any]:
    shape = tuple(int(v) for v in grid.shape)
    return {
        "format": FORMAT_VERSION,
        "chunk": CHUNK_SIZE,
        "shape": list(shape),
        "dtype": "uint16",
        "block_encoding": BLOCK_ENCODING,
        "origin": list((geometry or {}).get("origin") or [0.0, 0.0, 0.0]),
        "spacing": list((geometry or {}).get("spacing") or [1.0, 1.0, 1.0]),
        "directions": list(
            (geometry or {}).get("directions")
            or [1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0]
        ),
        "chunks": {},
    }


def load_manifest(folder: str) -> dict[str, Any]:
    path = manifest_path(folder)
    if not os.path.isfile(path):
        raise RuntimeError("This project has no segmentation to open.")
    try:
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError, TypeError) as exc:
        raise RuntimeError("Invalid segmentation manifest.") from exc
    if not isinstance(data, dict) or not data.get("shape") or not data.get("chunks"):
        # Empty volume still has chunks dict (possibly empty) — allow empty chunks if shape ok
        if not isinstance(data, dict) or not data.get("shape"):
            raise RuntimeError("Invalid segmentation manifest.")
        data.setdefault("chunks", {})
    data.setdefault("chunk", CHUNK_SIZE)
    data.setdefault("dtype", "uint16")
    return data


def try_load_manifest(folder: str) -> dict[str, Any] | None:
    """Return the cube manifest if present and valid; otherwise None."""
    if not store_exists(folder):
        return None
    try:
        return load_manifest(folder)
    except RuntimeError:
        return None


def _manifest_shape_chunk(manifest: dict[str, Any]) -> tuple[tuple[int, int, int] | None, int]:
    raw = manifest.get("shape") or []
    try:
        shape = (int(raw[0]), int(raw[1]), int(raw[2]))
    except (TypeError, ValueError, IndexError):
        return None, CHUNK_SIZE
    if shape[0] <= 0 or shape[1] <= 0 or shape[2] <= 0:
        return None, CHUNK_SIZE
    try:
        chunk = int(manifest.get("chunk") or CHUNK_SIZE)
    except (TypeError, ValueError):
        chunk = CHUNK_SIZE
    return shape, max(1, chunk)


def _merge_inclusive_intervals(intervals: list[tuple[int, int]]) -> list[tuple[int, int]]:
    if not intervals:
        return []
    ordered = sorted((int(lo), int(hi)) for lo, hi in intervals)
    merged: list[list[int]] = [[ordered[0][0], ordered[0][1]]]
    for lo, hi in ordered[1:]:
        if lo <= merged[-1][1] + 1:
            merged[-1][1] = max(merged[-1][1], hi)
        else:
            merged.append([lo, hi])
    return [(a, b) for a, b in merged]


def format_voxel_intervals(intervals: list[tuple[int, int]]) -> str:
    """Human-readable inclusive ranges: ``[25, 70] puis [75, 96]``."""
    if not intervals:
        return "—"
    return " puis ".join("[%d, %d]" % (lo, hi) for lo, hi in intervals)


def diff_manifest_chunks(
    before: dict[str, Any] | None,
    after: dict[str, Any] | None,
) -> dict[str, Any] | None:
    """Compare two manifests: changed count + merged voxel intervals on X/Y/Z.

    Returns ``None`` if either manifest is missing, else::

        {
          "changed": int,
          "total": int,
          "x": [(lo, hi), ...],  # inclusive voxel indices
          "y": [...],
          "z": [...],
        }
    """
    if not isinstance(before, dict) or not isinstance(after, dict):
        return None
    left = before.get("chunks") or {}
    right = after.get("chunks") or {}
    if not isinstance(left, dict) or not isinstance(right, dict):
        return None
    shape_before, chunk_before = _manifest_shape_chunk(before)
    shape_after, chunk_after = _manifest_shape_chunk(after)
    keys = set(left) | set(right)
    if not keys:
        return {"changed": 0, "total": 0, "x": [], "y": [], "z": []}
    changed_keys: list[str] = []
    for key in keys:
        if str(left.get(key) or "").strip().lower() != str(right.get(key) or "").strip().lower():
            changed_keys.append(key)
    x_intervals: list[tuple[int, int]] = []
    y_intervals: list[tuple[int, int]] = []
    z_intervals: list[tuple[int, int]] = []
    for key in changed_keys:
        # Prefer the destination layout; fall back to the source if needed.
        if key in right and shape_after is not None:
            shape, chunk = shape_after, chunk_after
        elif key in left and shape_before is not None:
            shape, chunk = shape_before, chunk_before
        elif shape_after is not None:
            shape, chunk = shape_after, chunk_after
        elif shape_before is not None:
            shape, chunk = shape_before, chunk_before
        else:
            continue
        try:
            zsl, ysl, xsl = cube_slices(shape, key, chunk)
        except ValueError:
            continue
        if zsl.stop > zsl.start:
            z_intervals.append((zsl.start, zsl.stop - 1))
        if ysl.stop > ysl.start:
            y_intervals.append((ysl.start, ysl.stop - 1))
        if xsl.stop > xsl.start:
            x_intervals.append((xsl.start, xsl.stop - 1))
    return {
        "changed": len(changed_keys),
        "total": len(keys),
        "x": _merge_inclusive_intervals(x_intervals),
        "y": _merge_inclusive_intervals(y_intervals),
        "z": _merge_inclusive_intervals(z_intervals),
    }


def save_manifest(folder: str, manifest: dict[str, Any]) -> str:
    path = manifest_path(folder)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(manifest, handle, indent=2, sort_keys=True)
        handle.write("\n")
    return path


def _compress_block_bytes(raw: bytes) -> bytes:
    return zlib.compress(raw, ZLIB_LEVEL)


def _decompress_block_bytes(payload: bytes) -> bytes:
    try:
        return zlib.decompress(payload)
    except zlib.error as exc:
        raise RuntimeError("Could not decompress segmentation cube (expected zlib).") from exc


def _write_block_file(folder: str, digest: str, block: np.ndarray) -> bool:
    """Write zlib-compressed block bytes if absent. Returns True when a new file was created."""
    path = block_file_path(folder, digest)
    if os.path.isfile(path):
        return False
    os.makedirs(os.path.dirname(path), exist_ok=True)
    arr = np.ascontiguousarray(block, dtype=GRID_DTYPE)
    raw = arr.tobytes()
    compressed = _compress_block_bytes(raw)
    tmp = path + ".tmp"
    with open(tmp, "wb") as handle:
        handle.write(compressed)
    os.replace(tmp, path)
    return True


def write_store(
    folder: str,
    grid: Any,
    geometry: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Split ``grid`` into cubes, hash, write missing blocks + manifest.

    All-zero cubes are recorded in the manifest but do not create a block file
    (the zero hash for that shape is enough to reconstruct).
    """
    _require_xxhash()
    array = as_grid(grid)
    shape = tuple(int(v) for v in array.shape)
    manifest = build_manifest(array, geometry)
    chunks: dict[str, str] = {}
    written = 0
    reused = 0
    skipped_empty = 0
    keys = all_keys(shape, CHUNK_SIZE)
    for index, key in enumerate(keys):
        zsl, ysl, xsl = cube_slices(shape, key, CHUNK_SIZE)
        block = array[zsl, ysl, xsl]
        digest = hash_cube(block)
        chunks[key] = digest
        if digest == zero_hash(tuple(int(v) for v in block.shape)):
            skipped_empty += 1
        elif _write_block_file(folder, digest, block):
            written += 1
        else:
            reused += 1
        if index % 32 == 0:
            _keep_ui_alive()
    manifest["chunks"] = chunks
    save_manifest(folder, manifest)
    return {
        "shape": list(shape),
        "chunks": len(chunks),
        "written": written,
        "reused": reused,
        "skipped_empty": skipped_empty,
        "manifest": manifest_path(folder),
    }


def _decode_cube(raw: bytes, expected_shape: tuple[int, int, int]) -> np.ndarray:
    expected = int(expected_shape[0] * expected_shape[1] * expected_shape[2] * GRID_DTYPE.itemsize)
    if len(raw) != expected:
        raise RuntimeError(
            "Cube payload has the wrong size (got %d bytes, expected %d)."
            % (len(raw), expected)
        )
    return np.frombuffer(raw, dtype=GRID_DTYPE).reshape(expected_shape).copy()


def read_store(folder: str, manifest: dict[str, Any] | None = None) -> tuple[np.ndarray, dict[str, Any]]:
    """Rebuild a full uint16 grid from manifest + zlib block files."""
    _require_xxhash()
    data = manifest if manifest is not None else load_manifest(folder)
    shape = tuple(int(v) for v in data["shape"])
    if len(shape) != 3:
        raise RuntimeError("Invalid segmentation manifest.")
    chunk = int(data.get("chunk") or CHUNK_SIZE)
    chunks = data.get("chunks") or {}
    grid = np.zeros(shape, dtype=GRID_DTYPE)
    for index, key in enumerate(all_keys(shape, chunk)):
        digest = str(chunks.get(key) or "").strip().lower()
        if not digest:
            raise RuntimeError("Missing segmentation cube %s." % key)
        expected = cube_shape(shape, key, chunk)
        if digest == zero_hash(expected):
            # Already zeros in the grid.
            pass
        else:
            path = block_file_path(folder, digest)
            if not os.path.isfile(path):
                raise RuntimeError("Missing segmentation cube %s." % key)
            with open(path, "rb") as handle:
                compressed = handle.read()
            raw = _decompress_block_bytes(compressed)
            block = _decode_cube(raw, expected)
            zsl, ysl, xsl = cube_slices(shape, key, chunk)
            grid[zsl, ysl, xsl] = block
        if index % 32 == 0:
            _keep_ui_alive()
    geometry = {
        "origin": list(data.get("origin") or [0.0, 0.0, 0.0]),
        "spacing": list(data.get("spacing") or [1.0, 1.0, 1.0]),
        "directions": list(
            data.get("directions") or [1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0]
        ),
    }
    return grid, geometry


def legacy_segmentation_path(folder: str, stem: str) -> str:
    return os.path.join(folder, "%s_segmentation.nii.gz" % ((stem or "project").strip() or "project"))


def remove_legacy_segmentation_file(folder: str, stem: str) -> bool:
    """Delete root ``*_segmentation.nii.gz`` so it is not re-committed. Returns True if removed."""
    path = legacy_segmentation_path(folder, stem)
    if not os.path.isfile(path):
        return False
    try:
        os.remove(path)
        return True
    except OSError:
        logging.exception("Could not remove legacy segmentation file %s", path)
        return False
