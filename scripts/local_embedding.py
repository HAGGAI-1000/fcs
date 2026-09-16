#!/usr/bin/env python3
"""LlamaIndex embedding adapter for the current FastEmbed runtime."""

from __future__ import annotations

import warnings
from typing import Any

from fastembed import TextEmbedding
from llama_index.core.base.embeddings.base import BaseEmbedding
from pydantic import PrivateAttr


class FastEmbedAdapter(BaseEmbedding):
    """Expose FastEmbed 0.8 models through the LlamaIndex BaseEmbedding API."""

    _model: Any = PrivateAttr()

    def __init__(self, model_name: str, cache_dir: str, batch_size: int = 128) -> None:
        super().__init__(model_name=model_name, embed_batch_size=batch_size)
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", message=r"The model .* now uses mean pooling.*")
            self._model = TextEmbedding(model_name=model_name, cache_dir=cache_dir, lazy_load=True)

    def _get_query_embedding(self, query: str) -> list[float]:
        return next(iter(self._model.query_embed(query))).tolist()

    async def _aget_query_embedding(self, query: str) -> list[float]:
        return self._get_query_embedding(query)

    def _get_text_embedding(self, text: str) -> list[float]:
        return next(iter(self._model.embed(text))).tolist()

    def _get_text_embeddings(self, texts: list[str]) -> list[list[float]]:
        return [value.tolist() for value in self._model.embed(texts, batch_size=self.embed_batch_size)]
