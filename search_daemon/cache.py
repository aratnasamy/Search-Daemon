from __future__ import annotations

import json
import os
import threading
from pathlib import Path

CACHE_PATH = Path("~/.cache/search-mcp/file-index.json")

# Per-folder cache schema:
# {
#   "/abs/folder/path": {
#     "doc_count": 142,            # ChromaDB collection.count() at last write
#     "files": {"/abs/file": mtime_float, ...}
#   },
#   ...
# }


class FileIndexCache:
    def __init__(self, cache_path: Path = CACHE_PATH):
        self._path = cache_path.expanduser().resolve()
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._data: dict[str, dict] = {}
        self._load()

    # ------------------------------------------------------------------
    # Read helpers
    # ------------------------------------------------------------------

    def get_files(self, folder: Path) -> dict[str, float]:
        """Return {path_str: mtime} cached for this folder."""
        key = _key(folder)
        with self._lock:
            return dict(self._data.get(key, {}).get("files", {}))

    def get_doc_count(self, folder: Path) -> int | None:
        """Return the ChromaDB doc count stored at last write, or None if missing."""
        key = _key(folder)
        with self._lock:
            entry = self._data.get(key)
            return int(entry["doc_count"]) if entry and "doc_count" in entry else None

    # ------------------------------------------------------------------
    # Write helpers (each does an atomic flush to disk)
    # ------------------------------------------------------------------

    def set_file(self, folder: Path, file_path: Path, mtime: float, doc_count: int) -> None:
        """Record that file_path was successfully indexed at mtime."""
        key = _key(folder)
        with self._lock:
            entry = self._data.setdefault(key, {"doc_count": 0, "files": {}})
            entry["files"][str(file_path)] = mtime
            entry["doc_count"] = doc_count
        self._write()

    def remove_file(self, folder: Path, file_path: Path, doc_count: int) -> None:
        """Remove file_path from the cache (e.g. after deletion)."""
        key = _key(folder)
        with self._lock:
            entry = self._data.get(key)
            if entry:
                entry["files"].pop(str(file_path), None)
                entry["doc_count"] = doc_count
        self._write()

    def invalidate(self, folder: Path) -> None:
        """Drop all cached data for a folder (forces full re-index)."""
        key = _key(folder)
        with self._lock:
            self._data.pop(key, None)
        self._write()

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _load(self) -> None:
        if self._path.exists():
            try:
                self._data = json.loads(self._path.read_text())
            except (json.JSONDecodeError, OSError):
                self._data = {}

    def _write(self) -> None:
        tmp = self._path.with_suffix(".tmp")
        with self._lock:
            payload = json.dumps(self._data, indent=2)
        tmp.write_text(payload)
        os.replace(tmp, self._path)


def _key(folder: Path) -> str:
    return str(folder.resolve())
