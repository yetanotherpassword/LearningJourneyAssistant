"""Text embeddings through the OpenAI-compatible endpoint (Ollama, LM Studio).

Used by lja.data.competency_tagger to group hundreds of SILOs into
competencies without an LLM call per SILO -- a 30B chat model already fails
the single-call clustering at 52 SILOs (python/README.md), and embeddings
are the tool for "which of these 400 sentences are about the same thing".

Anthropic's API has no embeddings endpoint, so this always goes to
LJA_OPENAI_BASE_URL regardless of LJA_LLM_PROVIDER. Ollama ships
`nomic-embed-text` and `mxbai-embed-large`; pull one and set LJA_EMBED_MODEL.
"""

from __future__ import annotations

import time

from openai import OpenAI

from .. import config


class EmbeddingClient:
    def __init__(self, *, base_url: str | None = None, model: str | None = None, api_key: str | None = None) -> None:
        self.base_url = base_url or config.OPENAI_BASE_URL
        self.model = model or config.EMBED_MODEL
        self._client = OpenAI(base_url=self.base_url, api_key=api_key or config.OPENAI_API_KEY)
        self.calls = 0
        self.seconds = 0.0

    def describe(self) -> str:
        return f"embeddings model={self.model} base_url={self.base_url}"

    def embed(self, texts: list[str], *, batch_size: int = 64) -> list[list[float]]:
        out: list[list[float]] = []
        for i in range(0, len(texts), batch_size):
            batch = texts[i : i + batch_size]
            t0 = time.perf_counter()
            resp = self._client.embeddings.create(model=self.model, input=batch)
            self.seconds += time.perf_counter() - t0
            self.calls += 1
            # The API may return items out of order; sort by index to be safe.
            out.extend(item.embedding for item in sorted(resp.data, key=lambda d: d.index))
        return out

    def usage_summary(self) -> str:
        return f"{self.calls} embedding call(s), {self.seconds:.1f}s total"
