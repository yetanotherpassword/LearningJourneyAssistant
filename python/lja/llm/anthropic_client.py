"""Claude backend for LLMClient. The API enforces the schema server-side via
output_config.format, so there is no JSON-parsing fallback path to write
here (contrast with openai_compatible_client.py, which cannot make that
assumption).

Deliberately builds the request with client.messages.create() rather than
the .parse() convenience helper: .parse() takes its own output_format=
parameter and it's not documented whether passing output_config directly
alongside it (for effort) merges cleanly or one silently wins. Building
output_config as a single dict -- format and effort as sibling keys, per
the documented shape -- and parsing the response text ourselves removes
that ambiguity entirely, at the cost of one extra line (schema validation)
that .parse() would otherwise do for us.
"""

from __future__ import annotations

import time
from typing import Any, TypeVar

import anthropic
from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)

# USD per million tokens, (input, output) -- from platform.claude.com/docs/en/pricing.
# Keyed by exact model ID; update when the pricing page changes or config.py's
# ANTHROPIC_MODEL default moves to a new model.
_PRICING_PER_MTOK: dict[str, tuple[float, float]] = {
    "claude-opus-4-8": (5.00, 25.00),
    "claude-opus-5": (5.00, 25.00),
    "claude-sonnet-5": (3.00, 15.00),
    "claude-haiku-4-5": (1.00, 5.00),
    "claude-fable-5": (10.00, 50.00),
}


class AnthropicClient:
    def __init__(
        self,
        *,
        model: str,
        api_key: str | None = None,
        effort: str = "",
        thinking: bool = False,
    ) -> None:
        # api_key=None lets the SDK fall back to ANTHROPIC_API_KEY / an
        # `ant auth login` profile -- see the claude-api skill's auth notes.
        self._client = anthropic.Anthropic(api_key=api_key or None)
        self._model = model
        # temperature/top_p/top_k are REJECTED (400) on this model family --
        # effort + thinking are the actual "how hard should it think" dials.
        # See python/README.md's LLM-tuning section before changing either.
        self._effort = effort
        self._thinking = thinking
        # Cumulative across every complete_structured() call on this
        # instance -- see usage_summary()'s docstring in base.py for why
        # cumulative, not last-call-only.
        self._call_count = 0
        self._total_elapsed_s = 0.0
        self._total_input_tokens = 0
        self._total_output_tokens = 0

    def complete_structured(self, *, system: str, user: str, schema: type[T]) -> T:
        output_config: dict[str, Any] = {
            "format": {
                "type": "json_schema",
                "schema": schema.model_json_schema(),
            }
        }
        if self._effort:
            output_config["effort"] = self._effort

        kwargs: dict[str, Any] = {
            "model": self._model,
            "max_tokens": 16000,
            "system": system,
            "messages": [{"role": "user", "content": user}],
            "output_config": output_config,
        }
        if self._thinking:
            kwargs["thinking"] = {"type": "adaptive"}

        start = time.perf_counter()
        response = self._client.messages.create(**kwargs)
        self._total_elapsed_s += time.perf_counter() - start

        self._call_count += 1
        self._total_input_tokens += response.usage.input_tokens
        self._total_output_tokens += response.usage.output_tokens

        text = next(block.text for block in response.content if block.type == "text")
        return schema.model_validate_json(text)

    def describe(self) -> str:
        return (
            f"provider=anthropic model={self._model} "
            f"effort={self._effort or 'default(high)'} thinking={self._thinking} "
            f"temperature=n/a (rejected by this model family)"
        )

    def usage_summary(self) -> str:
        base = (
            f"{self._call_count} call(s), {self._total_elapsed_s:.1f}s total, "
            f"tokens in={self._total_input_tokens} out={self._total_output_tokens}"
        )
        pricing = _PRICING_PER_MTOK.get(self._model)
        if pricing is None:
            return f"{base}, cost=unknown (no pricing entry for model {self._model!r})"
        input_price, output_price = pricing
        cost = (
            self._total_input_tokens / 1_000_000 * input_price
            + self._total_output_tokens / 1_000_000 * output_price
        )
        return f"{base}, cost=${cost:.4f}"
