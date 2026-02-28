from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

DEFAULT_EXTENSIONS = [".txt", ".md", ".rst", ".pdf", ".docx", ".pptx", ".xlsx"]
DEFAULT_CONFIG_PATH = Path("~/.config/search-daemon/config.yaml")


@dataclass
class FolderConfig:
    path: Path
    extensions: list[str]


@dataclass
class Settings:
    model: str = "all-MiniLM-L6-v2"
    chunk_size: int = 1000
    chunk_overlap: int = 200
    batch_size: int = 32
    extensions: list[str] = field(default_factory=lambda: list(DEFAULT_EXTENSIONS))


@dataclass
class Config:
    folders: list[FolderConfig]
    settings: Settings


def load(config_path: Path | None = None) -> Config:
    path = (config_path or DEFAULT_CONFIG_PATH).expanduser().resolve()
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")

    with path.open() as f:
        raw: dict[str, Any] = yaml.safe_load(f) or {}

    settings_raw = raw.get("settings", {})
    settings = Settings(
        model=settings_raw.get("model", "all-MiniLM-L6-v2"),
        chunk_size=settings_raw.get("chunk_size", 1000),
        chunk_overlap=settings_raw.get("chunk_overlap", 200),
        batch_size=settings_raw.get("batch_size", 32),
        extensions=settings_raw.get("extensions", list(DEFAULT_EXTENSIONS)),
    )

    folders = []
    for entry in raw.get("folders", []):
        folder_path = Path(entry["path"]).expanduser().resolve()
        if not folder_path.is_dir():
            raise ValueError(f"Folder does not exist or is not a directory: {folder_path}")
        exts = entry.get("extensions", settings.extensions)
        folders.append(FolderConfig(path=folder_path, extensions=exts))

    if not folders:
        raise ValueError("No folders configured in config file")

    return Config(folders=folders, settings=settings)
