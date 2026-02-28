from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timezone
from pathlib import Path

from . import chunker, embedder, parser
from .config import Config, FolderConfig
from .status import StatusTracker
from .store import ChromaStore

logger = logging.getLogger(__name__)


def _chunk_id(file_path: Path, chunk_index: int) -> str:
    raw = f"{file_path}:{chunk_index}"
    return hashlib.sha256(raw.encode()).hexdigest()[:32]


class Indexer:
    def __init__(self, config: Config, store: ChromaStore, status: StatusTracker | None = None):
        self._config = config
        self._store = store
        self._status = status

    def index_file(
        self,
        folder: FolderConfig,
        file_path: Path,
        *,
        _scan_indexed: int | None = None,
        _scan_total: int | None = None,
    ) -> None:
        if file_path.suffix.lower() not in folder.extensions:
            return
        if not file_path.is_file():
            return

        collection = self._store.get_or_create_collection(folder.path)
        current_mtime = file_path.stat().st_mtime

        # Check if already indexed with same mtime
        indexed = self._store.get_indexed_files(collection)
        if indexed.get(str(file_path)) == current_mtime:
            logger.debug("Skipping unchanged file %s", file_path)
            return

        text = parser.parse_file(file_path)
        if not text or not text.strip():
            logger.debug("No text extracted from %s", file_path)
            return

        s = self._config.settings
        chunks = chunker.chunk_text(text, s.chunk_size, s.chunk_overlap)
        if not chunks:
            return

        if self._status:
            i = _scan_indexed if _scan_indexed is not None else len(indexed)
            t = _scan_total if _scan_total is not None else max(len(indexed) + 1, i + 1)
            self._status.set_indexing(folder.path, indexed=i, total=t, current_file=file_path.name)

        # Remove stale chunks before upserting new ones
        self._store.delete_by_path(collection, file_path)

        embeddings = embedder.embed(chunks, model_name=s.model, batch_size=s.batch_size)
        for i, (chunk, embedding) in enumerate(zip(chunks, embeddings)):
            doc_id = _chunk_id(file_path, i)
            self._store.upsert(
                collection=collection,
                doc_id=doc_id,
                embedding=embedding,
                document=chunk,
                metadata={
                    "file_path": str(file_path),
                    "file_name": file_path.name,
                    "mtime": current_mtime,
                    "chunk_index": i,
                    "folder": str(folder.path),
                },
            )
        logger.info("Indexed %s (%d chunks)", file_path, len(chunks))

        # After a live (non-scan) event, restore watching state
        if self._status and _scan_indexed is None:
            updated = self._store.get_indexed_files(collection)
            self._status.set_watching(folder.path, total=len(updated))

    def remove_file(self, folder: FolderConfig, file_path: Path) -> None:
        collection = self._store.get_or_create_collection(folder.path)
        self._store.delete_by_path(collection, file_path)
        logger.info("Removed %s from index", file_path)
        if self._status:
            updated = self._store.get_indexed_files(collection)
            self._status.set_watching(folder.path, total=len(updated))

    def initial_scan(self, folder: FolderConfig) -> None:
        logger.info("Starting initial scan of %s", folder.path)
        collection = self._store.get_or_create_collection(folder.path)
        prev_indexed = self._store.get_indexed_files(collection)

        # Collect eligible files first so we know the total
        eligible: list[Path] = [
            p for p in folder.path.rglob("*")
            if p.is_file() and p.suffix.lower() in folder.extensions
        ]
        on_disk = {str(p) for p in eligible}

        if self._status:
            self._status.set_scanning(folder.path, total=len(eligible))

        for i, file_path in enumerate(eligible):
            self.index_file(folder, file_path, _scan_indexed=i, _scan_total=len(eligible))

        # Remove entries for files no longer on disk
        for path_str in prev_indexed:
            if path_str not in on_disk:
                self._store.delete_by_path(collection, Path(path_str))
                logger.info("Pruned deleted file %s", path_str)

        if self._status:
            self._status.set_watching(
                folder.path,
                total=len(eligible),
                last_full_index=datetime.now(timezone.utc).isoformat(timespec="seconds"),
            )

        logger.info("Initial scan of %s complete (%d files)", folder.path, len(eligible))
