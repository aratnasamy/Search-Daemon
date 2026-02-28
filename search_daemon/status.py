from __future__ import annotations

import json
import os
import threading
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

STATUS_PATH = Path("~/.cache/search-mcp/status.json")


@dataclass
class FolderStatus:
    state: str              # "scanning" | "indexing" | "watching"
    total_files: int
    indexed_files: int
    current_file: str | None
    last_full_index: str | None  # ISO datetime string
    collection: str


class StatusTracker:
    def __init__(self, status_path: Path = STATUS_PATH):
        self._path = status_path.expanduser().resolve()
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._folders: dict[str, FolderStatus] = {}
        self._daemon_started = _now_iso()

    def _folder_key(self, folder: Path) -> str:
        return str(folder.resolve())

    def set_scanning(self, folder: Path, total: int) -> None:
        from .store import collection_name
        key = self._folder_key(folder)
        with self._lock:
            existing = self._folders.get(key)
            self._folders[key] = FolderStatus(
                state="scanning",
                total_files=total,
                indexed_files=0,
                current_file=None,
                last_full_index=existing.last_full_index if existing else None,
                collection=collection_name(folder),
            )
        self._write()

    def set_indexing(
        self,
        folder: Path,
        indexed: int,
        total: int,
        current_file: str,
    ) -> None:
        key = self._folder_key(folder)
        with self._lock:
            existing = self._folders.get(key)
            if existing:
                existing.state = "indexing"
                existing.indexed_files = indexed
                existing.total_files = total
                existing.current_file = current_file
        self._write()

    def set_watching(
        self,
        folder: Path,
        total: int,
        last_full_index: str | None = None,
    ) -> None:
        key = self._folder_key(folder)
        with self._lock:
            existing = self._folders.get(key)
            lfi = last_full_index or (existing.last_full_index if existing else None)
            if existing:
                existing.state = "watching"
                existing.total_files = total
                existing.indexed_files = total
                existing.current_file = None
                existing.last_full_index = lfi
            else:
                from .store import collection_name
                self._folders[key] = FolderStatus(
                    state="watching",
                    total_files=total,
                    indexed_files=total,
                    current_file=None,
                    last_full_index=lfi,
                    collection=collection_name(folder),
                )
        self._write()

    def start_heartbeat(self, interval: float = 5.0) -> None:
        """Repeatedly touch updated_at so the menu bar knows the daemon is alive."""
        def _beat() -> None:
            self._write()
            t = threading.Timer(interval, _beat)
            t.daemon = True
            t.start()

        t = threading.Timer(interval, _beat)
        t.daemon = True
        t.start()

    def _write(self) -> None:
        payload = {
            "daemon_pid": os.getpid(),
            "daemon_started": self._daemon_started,
            "updated_at": _now_iso(),
            "folders": {k: asdict(v) for k, v in self._folders.items()},
        }
        tmp = self._path.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, indent=2))
        os.replace(tmp, self._path)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")
