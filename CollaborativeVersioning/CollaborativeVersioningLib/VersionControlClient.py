"""
E2 - Client de versioning collaboratif (MVP).

Interface REST prévue pour le serveur (E5/E9). En l'absence de serveur,
un stockage local permet de tester Push/Pull/Create et l'historique.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any
from urllib import error, request


@dataclass
class VersionRecord:
    version_id: str
    created_at: str
    author: str
    message: str
    status: str
    parent_id: str | None = None
    files: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> VersionRecord:
        return cls(
            version_id=data["version_id"],
            created_at=data["created_at"],
            author=data.get("author", "unknown"),
            message=data.get("message", ""),
            status=data.get("status", "local"),
            parent_id=data.get("parent_id"),
            files=list(data.get("files", [])),
        )


class VersionControlClient:
    """Client Push/Pull/Create pour le versioning collaboratif."""

    DEFAULT_SERVER_URL = "https://anatovcs-server.icm-institute.org"

    def __init__(self, server_url: str | None = None, local_store_dir: str | None = None):
        self.server_url = (server_url or self.DEFAULT_SERVER_URL).rstrip("/")
        self.connected = False
        self.remote_mode = False
        self.last_error = ""

        default_store = os.path.join(os.path.expanduser("~"), ".CollaborativeVersioning", "local_repo")
        self.local_store_dir = local_store_dir or default_store
        self.versions_dir = os.path.join(self.local_store_dir, "versions")
        self.metadata_file = os.path.join(self.local_store_dir, "versions.json")
        os.makedirs(self.versions_dir, exist_ok=True)
        self._ensure_metadata_file()

    def _ensure_metadata_file(self) -> None:
        if not os.path.exists(self.metadata_file):
            self._write_versions([])

    def _read_versions(self) -> list[VersionRecord]:
        with open(self.metadata_file, encoding="utf-8") as metadata_file:
            payload = json.load(metadata_file)
        return [VersionRecord.from_dict(item) for item in payload.get("versions", [])]

    def _write_versions(self, versions: list[VersionRecord]) -> None:
        payload = {"versions": [asdict(version) for version in versions]}
        with open(self.metadata_file, "w", encoding="utf-8") as metadata_file:
            json.dump(payload, metadata_file, indent=2)

    def connect(self, timeout_seconds: float = 3.0) -> tuple[bool, str]:
        self.last_error = ""
        health_url = f"{self.server_url}/health"
        try:
            with request.urlopen(health_url, timeout=timeout_seconds) as response:
                if response.status == 200:
                    self.connected = True
                    self.remote_mode = True
                    return True, f"Connecté au serveur distant ({self.server_url})"
        except (error.URLError, TimeoutError, ValueError) as exc:
            self.last_error = str(exc)
            logging.warning("Remote server unavailable: %s", exc)

        self.connected = True
        self.remote_mode = False
        return True, f"Mode local activé (serveur indisponible: {self.server_url})"

    def list_versions(self) -> list[VersionRecord]:
        if self.remote_mode:
            remote_versions = self._remote_get("/versions")
            if remote_versions is not None:
                return [VersionRecord.from_dict(item) for item in remote_versions]

        versions = self._read_versions()
        versions.sort(key=lambda item: item.created_at, reverse=True)
        return versions

    def create_version(self, author: str, message: str, parent_id: str | None = None) -> VersionRecord:
        version = VersionRecord(
            version_id=str(uuid.uuid4())[:8],
            created_at=datetime.now(timezone.utc).isoformat(),
            author=author,
            message=message or "Nouvelle version",
            status="created",
            parent_id=parent_id,
            files=[],
        )

        if self.remote_mode:
            remote_version = self._remote_post("/versions", asdict(version))
            if remote_version:
                return VersionRecord.from_dict(remote_version)

        versions = self._read_versions()
        versions.append(version)
        self._write_versions(versions)
        version_dir = os.path.join(self.versions_dir, version.version_id)
        os.makedirs(version_dir, exist_ok=True)
        return version

    def push(self, version_id: str, file_paths: list[str]) -> VersionRecord:
        if not file_paths:
            raise ValueError("Aucun fichier à envoyer.")

        if self.remote_mode:
            payload = {"version_id": version_id, "files": file_paths}
            remote_result = self._remote_post(f"/versions/{version_id}/push", payload)
            if remote_result:
                return VersionRecord.from_dict(remote_result)

        versions = self._read_versions()
        version = self._find_version(versions, version_id)
        version_dir = os.path.join(self.versions_dir, version_id)
        os.makedirs(version_dir, exist_ok=True)

        stored_files: list[str] = []
        for file_path in file_paths:
            if not os.path.exists(file_path):
                raise FileNotFoundError(file_path)
            destination = os.path.join(version_dir, os.path.basename(file_path))
            shutil.copy2(file_path, destination)
            stored_files.append(destination)

        version.files = stored_files
        version.status = "pushed"
        self._write_versions(versions)
        return version

    def pull(self, version_id: str, target_dir: str) -> list[str]:
        os.makedirs(target_dir, exist_ok=True)

        if self.remote_mode:
            payload = {"version_id": version_id, "target_dir": target_dir}
            remote_files = self._remote_post(f"/versions/{version_id}/pull", payload)
            if remote_files:
                return list(remote_files)

        versions = self._read_versions()
        version = self._find_version(versions, version_id)
        if not version.files:
            raise RuntimeError(f"La version {version_id} ne contient aucun fichier.")

        pulled_files: list[str] = []
        for source_path in version.files:
            if not os.path.exists(source_path):
                raise FileNotFoundError(source_path)
            destination = os.path.join(target_dir, os.path.basename(source_path))
            shutil.copy2(source_path, destination)
            pulled_files.append(destination)

        version.status = "pulled"
        self._write_versions(versions)
        return pulled_files

    def _find_version(self, versions: list[VersionRecord], version_id: str) -> VersionRecord:
        for version in versions:
            if version.version_id == version_id:
                return version
        raise KeyError(f"Version introuvable: {version_id}")

    def _remote_get(self, endpoint: str) -> Any | None:
        url = f"{self.server_url}{endpoint}"
        try:
            with request.urlopen(url, timeout=5) as response:
                return json.loads(response.read().decode("utf-8"))
        except (error.URLError, TimeoutError, json.JSONDecodeError, ValueError) as exc:
            logging.warning("Remote GET failed (%s): %s", url, exc)
            self.last_error = str(exc)
            return None

    def _remote_post(self, endpoint: str, payload: dict[str, Any]) -> Any | None:
        url = f"{self.server_url}{endpoint}"
        body = json.dumps(payload).encode("utf-8")
        http_request = request.Request(
            url,
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with request.urlopen(http_request, timeout=10) as response:
                return json.loads(response.read().decode("utf-8"))
        except (error.URLError, TimeoutError, json.JSONDecodeError, ValueError) as exc:
            logging.warning("Remote POST failed (%s): %s", url, exc)
            self.last_error = str(exc)
            return None
