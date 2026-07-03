import logging
from typing import Optional

logger = logging.getLogger(__name__)

_CROSS_ENCODER = None


def _get_model():
    global _CROSS_ENCODER
    if _CROSS_ENCODER is not None:
        return _CROSS_ENCODER
    try:
        from sentence_transformers import CrossEncoder
        _CROSS_ENCODER = CrossEncoder("cross-encoder/ms-marco-MiniLM-L-6-v2")
        logger.info("Cross-encoder loaded")
    except Exception as e:
        logger.warning(f"Cross-encoder not available: {e}")
        _CROSS_ENCODER = False
    return _CROSS_ENCODER


def rerank(query: str, documents: list[tuple[str, str]]) -> Optional[list[float]]:
    model = _get_model()
    if not model:
        return None
    pairs = [(query, doc[1]) for doc in documents]
    try:
        scores = model.predict(pairs)
        return scores.tolist() if hasattr(scores, "tolist") else list(scores)
    except Exception as e:
        logger.error(f"Rerank error: {e}")
        return None
