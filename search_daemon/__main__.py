from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="search-daemon",
        description="Index documents into ChromaDB using all-MiniLM-L6-v2 embeddings.",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=None,
        help="Path to config YAML (default: ~/.config/search-daemon/config.yaml)",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging verbosity (default: INFO)",
    )
    args = parser.parse_args()

    log_dir = Path("~/.cache/search-mcp").expanduser()
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "daemon.log"

    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
        handlers=[
            logging.FileHandler(log_file),
            logging.StreamHandler(sys.stdout),
        ],
    )

    # Suppress chatty third-party loggers
    for noisy in ("httpx", "httpcore", "huggingface_hub", "sentence_transformers"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    from . import config as cfg
    from .watcher import run_daemon

    try:
        configuration = cfg.load(args.config)
    except (FileNotFoundError, ValueError) as e:
        logging.critical("Config error: %s", e)
        sys.exit(1)

    run_daemon(configuration)


if __name__ == "__main__":
    main()
