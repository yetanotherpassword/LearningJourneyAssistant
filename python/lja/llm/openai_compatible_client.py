"""Backend for any server that speaks OpenAI's /v1/chat/completions shape --
LM Studio, Ollama (via its /v1 endpoint), llama.cpp's server, or OpenAI
itself. This is what makes local, zero-cost development possible; see
python/README.md's LLM layer section.

Two real, confirmed-live server disagreements shape this file, not
hypothetical ones:

1. response_format support varies. Ollama's /v1 endpoint accepts
   `{"type": "json_object"}`; a real LM Studio instance rejected that exact
   request with `400 'response_format.type' must be 'json_schema' or
   'text'`. So this client tries progressively looser strategies rather
   than retrying the same request twice.
2. Hybrid-reasoning models (Qwen3.5 and similar) stream their chain of
   thought into a separate `reasoning_content` field and leave `content`
   empty until they finish thinking. With no explicit max_tokens, a live
   test against exactly such a model spent its *entire* budget on
   reasoning and returned `finish_reason: "length"` with empty content --
   confirmed by inspecting the raw response, not assumed. Hence the large
   default max_tokens below: cutting it short doesn't save time, it just
   means the answer never arrives.

Feature code never sees either of these; it just gets a validated object
back or a clear final error.
"""

from __future__ import annotations

import json
import time
from typing import Any, TypeVar

from openai import OpenAI
from pydantic import BaseModel, ValidationError

T = TypeVar("T", bound=BaseModel)

# Generous on purpose -- see point 2 in the module docstring. A reasoning
# model can spend thousands of tokens thinking before it ever starts the
# JSON answer; a tight budget produces a confidently empty response, not a
# faster one.
DEFAULT_MAX_TOKENS = 16000


class OpenAICompatibleClient:
    def __init__(
        self,
        *,
        base_url: str,
        model: str,
        api_key: str = "not-needed",
        max_tokens: int = DEFAULT_MAX_TOKENS,
        temperature: float | None = 0.2,
    ) -> None:
        self._client = OpenAI(base_url=base_url, api_key=api_key)
        self._model = model
        self._max_tokens = max_tokens
        # None omits the field and relies on the server's own default.
        # Kept low by default -- this is a classification/judgement task,
        # not a creative-writing one; see config.py's OPENAI_TEMPERATURE.
        self._temperature = temperature
        # Cumulative across every complete_structured() call (and every
        # response_format retry within a call) on this instance -- see
        # usage_summary()'s docstring in base.py.
        self._call_count = 0
        self._total_elapsed_s = 0.0
        self._total_input_tokens = 0
        self._total_output_tokens = 0

    def complete_structured(self, *, system: str, user: str, schema: type[T]) -> T:
        schema_json = json.dumps(schema.model_json_schema(), indent=2)
        full_system = (
            f"{system}\n\nRespond with a single JSON object only -- no markdown "
            f"code fences, no commentary before or after -- matching exactly this "
            f"JSON Schema:\n{schema_json}"
        )

        # Progressively looser response_format strategies. Ordered from most
        # to least constrained: if the server honours json_schema, that's the
        # strongest guarantee (closest to the Anthropic path); json_object is
        # the older, more widely-supported mode; omitting response_format
        # entirely relies purely on the prompt instructions above plus
        # _strip_code_fences() -- the universal fallback, since every
        # OpenAI-compatible server accepts a plain chat completion.
        response_formats: list[dict[str, Any] | None] = [
            {
                "type": "json_schema",
                "json_schema": {
                    "name": schema.__name__,
                    "schema": schema.model_json_schema(),
                },
            },
            {"type": "json_object"},
            None,
        ]

        last_error: Exception | None = None
        last_raw: str | None = None
        last_finish_reason: str | None = None
        for attempt, response_format in enumerate(response_formats):
            user_prompt = user
            if attempt > 0:
                user_prompt = (
                    f"{user}\n\nYour previous reply was not valid JSON matching the "
                    f"schema. Reply with ONLY the JSON object this time, no other text."
                )
            kwargs: dict[str, Any] = {
                "model": self._model,
                "max_tokens": self._max_tokens,
                "messages": [
                    {"role": "system", "content": full_system},
                    {"role": "user", "content": user_prompt},
                ],
            }
            if response_format is not None:
                kwargs["response_format"] = response_format
            if self._temperature is not None:
                kwargs["temperature"] = self._temperature
            try:
                start = time.perf_counter()
                response = self._client.chat.completions.create(**kwargs)
                self._total_elapsed_s += time.perf_counter() - start
                self._call_count += 1
                # Not every OpenAI-compatible server populates usage (some
                # local builds omit the attribute entirely, not just set it
                # to None) -- getattr so a missing field undercounts for
                # this attempt rather than raising and masquerading as a
                # failed response_format strategy.
                usage = getattr(response, "usage", None)
                if usage is not None:
                    self._total_input_tokens += getattr(usage, "prompt_tokens", 0) or 0
                    self._total_output_tokens += getattr(usage, "completion_tokens", 0) or 0

                choice = response.choices[0]
                raw = choice.message.content or ""
                last_raw = raw
                last_finish_reason = choice.finish_reason
                if not raw and choice.finish_reason == "length":
                    # The model ran out of budget before emitting any answer
                    # content -- almost certainly a reasoning model that spent
                    # everything on chain-of-thought (see module docstring).
                    # Retrying with the *same* max_tokens would just repeat
                    # this, so treat it as a hard failure for this attempt
                    # rather than trying to parse an empty string.
                    raise ValueError(
                        f"empty content, finish_reason=length -- likely ran out of "
                        f"max_tokens={self._max_tokens} while reasoning, before any "
                        f"answer content was emitted"
                    )
                return schema.model_validate(_strip_code_fences(raw))
            except (json.JSONDecodeError, ValidationError, ValueError) as exc:
                last_error = exc
                continue
            except Exception as exc:  # noqa: BLE001 -- local server failure modes
                # are not standardized (unsupported response_format value,
                # connection resets, etc); we want to fall through to the
                # next strategy either way, and a clear final error if all
                # of them fail.
                last_error = exc
                continue

        raise RuntimeError(
            f"{self._model} at {self._client.base_url} never returned valid "
            f"{schema.__name__} JSON after trying {len(response_formats)} "
            f"response_format strategies (max_tokens={self._max_tokens}, last "
            f"finish_reason={last_finish_reason!r}). Last raw reply: {last_raw!r}"
        ) from last_error

    def describe(self) -> str:
        return (
            f"provider=openai_compatible model={self._model} "
            f"base_url={self._client.base_url} temperature={self._temperature} "
            f"max_tokens={self._max_tokens}"
        )

    def usage_summary(self) -> str:
        return (
            f"{self._call_count} call(s), {self._total_elapsed_s:.1f}s total, "
            f"tokens in={self._total_input_tokens} out={self._total_output_tokens} "
            f"(0 tokens may mean the server doesn't report usage, not that none was used)"
        )


def _strip_code_fences(raw: str) -> dict:
    text = raw.strip()
    if text.startswith("```"):
        # Drop the opening fence (and an optional "json" language tag) and
        # the closing fence.
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[len("json"):]
    return json.loads(text.strip())
