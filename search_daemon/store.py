from __future__ import annotations

import hashlib
import logging
from pathlib import Path

import chromadb

logger = logging.getLogger(__name__)

DB_PATH = Path("~/.cache/search-mcp/chroma")


def collection_name(folder_path: Path) -> str:
    digest = hashlib.sha256(str(folder_path.resolve()).encode()).hexdigest()[:16]
    return f"search-{digest}"


class ChromaStore:
    def __init__(self, db_path: Path = DB_PATH):
        resolved = db_path.expanduser().resolve()
        resolved.mkdir(parents=True, exist_ok=True)
        self._client = chromadb.PersistentClient(path=str(resolved))
        self._collections: dict[str, chromadb.Collection] = {}

    def get_or_create_collection(self, folder_path: Path) -> chromadb.Collection:
        name = collection_name(folder_path)
        if name not in self._collections:
            self._collections[name] = self._client.get_or_create_collection(
                name=name,
                metadata={"folder": str(folder_path)},
            )
            logger.info("Using collection %s for %s", name, folder_path)
        return self._collections[name]

    def upsert(
        self,
        collection: chromadb.Collection,
        doc_id: str,
        embedding: list[float],
        document: str,
        metadata: dict,
    ) -> None:
        collection.upsert(
            ids=[doc_id],
            embeddings=[embedding],
            documents=[document],
            metadatas=[metadata],
        )

    def delete_by_path(self, collection: chromadb.Collection, file_path: Path) -> None:
        path_str = str(file_path)
        results = collection.get(where={"file_path": path_str}, include=[])
        ids = results.get("ids", [])
        if ids:
            collection.delete(ids=ids)
            logger.debug("Deleted %d chunks for %s", len(ids), file_path)

    def get_indexed_files(self, collection: chromadb.Collection) -> dict[str, float]:
        """Return {path_str: mtime} for all indexed documents. Fallback for cache miss."""
        results = collection.get(include=["metadatas"])
        seen: dict[str, float] = {}
        for meta in results.get("metadatas") or []:
            if meta and "file_path" in meta and "mtime" in meta:
                seen[meta["file_path"]] = float(meta["mtime"])
        return seen
