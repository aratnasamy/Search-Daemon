from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timezone
from pathlib import Path

from . import chunker, embedder, parser
from .cache import FileIndexCache
from .config import Config, FolderConfig
from .status import StatusTracker
from .store import ChromaStore

logger = logging.getLogger(__name__)


def _chunk_id(file_path: Path, chunk_index: int) -> str:
    raw = f"{file_path}:{chunk_index}"
    return hashlib.sha256(raw.encode()).hexdigest()[:32]


class Indexer:
    def __init__(
        self,
        config: Config,
        store: ChromaStore,
        status: StatusTracker | None = None,
        cache: FileIndexCache | None = None,
    ):
        self._config = config
        self._store = store
        self._status = status
        self._cache = cache

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

        s = self._config.settings
        text = parser.parse_file(file_path)
        if not text or not text.strip():
            logger.debug("No text extracted from %s", file_path)
            return

        chunks = chunker.chunk_text(text, s.chunk_size, s.chunk_overlap)
        if not chunks:
            return

        if self._status:
            i = _scan_indexed if _scan_indexed is not None else 0
            t = _scan_total if _scan_total is not None else 1
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

        if self._cache:
            self._cache.set_file(folder.path, file_path, current_mtime, collection.count())

        # After a live (non-scan) event, restore watching state
        if self._status and _scan_indexed is None:
            total = len(self._cache.get_files(folder.path)) if self._cache else 0
            self._status.set_watching(folder.path, total=total)

    def remove_file(self, folder: FolderConfig, file_path: Path) -> None:
        collection = self._store.get_or_create_collection(folder.path)
        self._store.delete_by_path(collection, file_path)
        logger.info("Removed %s from index", file_path)
        if self._cache:
            self._cache.remove_file(folder.path, file_path, collection.count())
        if self._status:
            total = len(self._cache.get_files(folder.path)) if self._cache else 0
            self._status.set_watching(folder.path, total=total)

    def initial_scan(self, folder: FolderConfig) -> None:
        logger.info("Starting initial scan of %s", folder.path)
        collection = self._store.get_or_create_collection(folder.path)

        # Collect eligible files first so we know the total
        eligible: list[Path] = [
            p for p in folder.path.rglob("*")
            if p.is_file() and p.suffix.lower() in folder.extensions
        ]
        on_disk = {str(p) for p in eligible}

        if self._status:
            self._status.set_scanning(folder.path, total=len(eligible))

        # Load cache and validate against ChromaDB chunk count (O(1) query).
        # If they differ the DB was cleared/modified externally — discard the cache.
        cached_files: dict[str, float] = {}
        if self._cache:
            cached_doc_count = self._cache.get_doc_count(folder.path)
            db_doc_count = collection.count()
            if cached_doc_count is not None and cached_doc_count == db_doc_count:
                cached_files = self._cache.get_files(folder.path)
                logger.debug(
                    "Cache valid for %s (%d chunks, %d files cached)",
                    folder.path, db_doc_count, len(cached_files),
                )
            else:
                logger.info(
                    "Cache invalid for %s (cached=%s, db=%d) — full re-index",
                    folder.path, cached_doc_count, db_doc_count,
                )
                self._cache.invalidate(folder.path)

        for i, file_path in enumerate(eligible):
            current_mtime = file_path.stat().st_mtime
            if cached_files.get(str(file_path)) == current_mtime:
                logger.debug("Skipping unchanged file %s", file_path)
                continue
            self.index_file(folder, file_path, _scan_indexed=i, _scan_total=len(eligible))

        # Prune files that were indexed but are no longer on disk.
        # Use cache if valid, otherwise fall back to a ChromaDB metadata query.
        indexed_paths = set(cached_files) if cached_files else set(
            self._store.get_indexed_files(collection)
        )
        for path_str in indexed_paths:
            if path_str not in on_disk:
                self._store.delete_by_path(collection, Path(path_str))
                if self._cache:
                    self._cache.remove_file(folder.path, Path(path_str), collection.count())
                logger.info("Pruned deleted file %s", path_str)

        if self._status:
            self._status.set_watching(
                folder.path,
                total=len(eligible),
                last_full_index=datetime.now(timezone.utc).isoformat(timespec="seconds"),
            )

        logger.info("Initial scan of %s complete (%d files)", folder.path, len(eligible))
