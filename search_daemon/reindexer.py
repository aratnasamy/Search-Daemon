from __future__ import annotations

import json
import logging
import os
from pathlib import Path

REQUESTS_PATH = Path("~/.cache/search-mcp/reindex-requests.json")

logger = logging.getLogger(__name__)


def request_reindex(folder: Path) -> None:
    """Write a reindex request for folder. Called by the menu bar process."""
    path = REQUESTS_PATH.expanduser().resolve()
    path.parent.mkdir(parents=True, exist_ok=True)

    abs_str = str(folder.resolve())
    existing: list[str] = []
    if path.exists():
        try:
            existing = json.loads(path.read_text())
        except (json.JSONDecodeError, OSError):
            existing = []

    if abs_str not in existing:
        existing.append(abs_str)

    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(existing))
    os.replace(tmp, path)
    logger.debug("Reindex requested for %s", abs_str)


def pop_requests() -> list[str]:
    """Read and atomically clear the request file. Called by the daemon."""
    path = REQUESTS_PATH.expanduser().resolve()
    if not path.exists():
        return []
    try:
        folders = json.loads(path.read_text())
        path.unlink(missing_ok=True)
        return folders if isinstance(folders, list) else []
    except (json.JSONDecodeError, OSError):
        return []
