from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import rumps

from .reindexer import request_reindex

STATUS_PATH = Path("~/.cache/search-mcp/status.json").expanduser()
STALE_SECONDS = 12


def _display_path(abs_path: str) -> str:
    home = str(Path.home())
    if abs_path.startswith(home):
        return "~" + abs_path[len(home):]
    return abs_path


def _format_dt(iso: str | None) -> str:
    if not iso:
        return "never"
    try:
        dt = datetime.fromisoformat(iso).astimezone()
        return dt.strftime("%-m/%-d %-I:%M %p")
    except ValueError:
        return iso


def _make_reindex_callback(abs_path: str):
    def _callback(_sender) -> None:
        request_reindex(Path(abs_path))
    return _callback


def _folder_status_text(folder: dict) -> str:
    state = folder.get("state", "")
    total = folder.get("total_files", 0)
    indexed = folder.get("indexed_files", 0)
    current = folder.get("current_file")
    last = folder.get("last_full_index")

    if state == "watching":
        return f"✅ Fully indexed · {total} files · {_format_dt(last)}"
    elif state == "indexing":
        line = f"⏳ Indexing {indexed}/{total} files…"
        if current:
            line += f"\n      {current}"
        return line
    elif state == "scanning":
        return f"🔍 Scanning… ({total} files found)"
    return "❓ Unknown"


class SearchDaemonApp(rumps.App):
    def __init__(self):
        super().__init__("🔍", quit_button=None)
        self._timer = rumps.Timer(self._refresh, 2)
        self._timer.start()
        self._refresh(None)

    def _refresh(self, _sender) -> None:
        items = []

        title_item = rumps.MenuItem("Search Daemon")
        title_item.set_callback(None)
        items.append(title_item)
        items.append(rumps.separator)

        status = _load_status()

        if status is None:
            items.append(rumps.MenuItem("⚠️ Daemon not running"))
        else:
            folders: dict = status.get("folders", {})
            if not folders:
                items.append(rumps.MenuItem("No folders configured"))
            else:
                for abs_path, folder in folders.items():
                    display = _display_path(abs_path)
                    folder_item = rumps.MenuItem(display)
                    folder_item.set_callback(None)
                    status_text = _folder_status_text(folder)
                    for line in status_text.split("\n"):
                        sub = rumps.MenuItem(line)
                        sub.set_callback(None)
                        folder_item.add(sub)
                    folder_item.add(rumps.separator)
                    reindex_item = rumps.MenuItem(
                        "Force Reindex",
                        callback=_make_reindex_callback(abs_path),
                    )
                    folder_item.add(reindex_item)
                    items.append(folder_item)

        items.append(rumps.separator)
        items.append(rumps.MenuItem("Quit", callback=rumps.quit_application))

        self.menu.clear()
        self.menu = items


def _load_status() -> dict | None:
    if not STATUS_PATH.exists():
        return None
    try:
        data = json.loads(STATUS_PATH.read_text())
    except (json.JSONDecodeError, OSError):
        return None

    updated_at = data.get("updated_at", "")
    try:
        dt = datetime.fromisoformat(updated_at)
        age = (datetime.now(timezone.utc) - dt).total_seconds()
        if age > STALE_SECONDS:
            return None
    except (ValueError, TypeError):
        return None

    return data


def main() -> None:
    SearchDaemonApp().run()


if __name__ == "__main__":
    main()
