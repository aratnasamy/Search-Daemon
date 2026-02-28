from __future__ import annotations

import logging
import signal
import threading
from pathlib import Path

from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer, ObserverType

from .config import Config, FolderConfig
from .indexer import Indexer
from .status import StatusTracker
from .store import ChromaStore

logger = logging.getLogger(__name__)


class FileEventHandler(FileSystemEventHandler):
    def __init__(self, indexer: Indexer, folder: FolderConfig):
        super().__init__()
        self._indexer = indexer
        self._folder = folder
        self._exts = set(folder.extensions)

    def _relevant(self, path: str) -> bool:
        return Path(path).suffix.lower() in self._exts

    def on_created(self, event: FileSystemEvent) -> None:
        if not event.is_directory and self._relevant(event.src_path):
            self._indexer.index_file(self._folder, Path(event.src_path))

    def on_modified(self, event: FileSystemEvent) -> None:
        if not event.is_directory and self._relevant(event.src_path):
            self._indexer.index_file(self._folder, Path(event.src_path))

    def on_deleted(self, event: FileSystemEvent) -> None:
        if not event.is_directory and self._relevant(event.src_path):
            self._indexer.remove_file(self._folder, Path(event.src_path))

    def on_moved(self, event: FileSystemEvent) -> None:
        if event.is_directory:
            return
        if self._relevant(event.src_path):
            self._indexer.remove_file(self._folder, Path(event.src_path))
        if self._relevant(event.dest_path):
            self._indexer.index_file(self._folder, Path(event.dest_path))


def run_daemon(config: Config) -> None:
    store = ChromaStore()
    status = StatusTracker()
    status.start_heartbeat(interval=5.0)
    indexer = Indexer(config, store, status=status)

    observers: list[ObserverType] = []
    stop_event = threading.Event()

    def shutdown(signum, frame):
        logger.info("Shutting down daemon...")
        stop_event.set()
        for obs in observers:
            obs.stop()

    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)

    for folder in config.folders:
        indexer.initial_scan(folder)
        handler = FileEventHandler(indexer, folder)
        obs = Observer()
        obs.schedule(handler, str(folder.path), recursive=True)
        obs.start()
        observers.append(obs)
        logger.info("Watching %s", folder.path)

    logger.info("Daemon running. Press Ctrl+C to stop.")
    stop_event.wait()

    for obs in observers:
        obs.join()
    logger.info("Daemon stopped.")
