from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

_model = None
_model_name: str | None = None


def _get_model(model_name: str):
    global _model, _model_name
    if _model is None or _model_name != model_name:
        logger.info("Loading embedding model %s...", model_name)
        from sentence_transformers import SentenceTransformer

        _model = SentenceTransformer(model_name)
        _model_name = model_name
        logger.info("Embedding model loaded.")
    return _model


def embed(texts: list[str], model_name: str = "all-MiniLM-L6-v2", batch_size: int = 32) -> list[list[float]]:
    model = _get_model(model_name)
    vectors = model.encode(texts, batch_size=batch_size, show_progress_bar=False)
    return [v.tolist() for v in vectors]
