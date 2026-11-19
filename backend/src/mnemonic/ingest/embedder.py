"""Local embeddings via fastembed (ONNX, no PyTorch) — see ADR 0001."""

from collections.abc import Iterable
from functools import lru_cache

import numpy as np
from fastembed import TextEmbedding
from tokenizers import Tokenizer

MODEL_NAME = "BAAI/bge-small-en-v1.5"
DIMENSIONS = 384


@lru_cache
def _model() -> TextEmbedding:
    return TextEmbedding(MODEL_NAME)


def get_tokenizer() -> Tokenizer:
    """The model's own tokenizer, so chunk sizes are measured in the units the model sees."""
    return _model().model.tokenizer


def embed_documents(texts: Iterable[str]) -> list[np.ndarray]:
    return list(_model().embed(texts))


def embed_query(text: str) -> np.ndarray:
    # bge expects a query instruction prefix; fastembed adds it in query_embed.
    return next(iter(_model().query_embed(text)))
