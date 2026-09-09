"""The one interface every feature module is allowed to depend on.

Nothing outside this package should import `anthropic` or `openai` directly --
that is the whole point of the abstraction (see python/README.md's LLM layer
section). Add a method here only when a real feature needs it; this file
should stay small.
"""

from __future__ import annotations

from typing import Protocol, TypeVar

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


class LLMClient(Protocol):
    """A model that can turn a prompt into a validated Pydantic object.

    Every feature that needs the LLM to classify, extract, or judge
    something defines its own Pydantic schema and calls this -- never a
    free-text completion that then gets regex-parsed downstream.
    """

    def complete_structured(self, *, system: str, user: str, schema: type[T]) -> T:
        """Return `schema.model_validate(...)` of the model's response.

        Implementations must raise rather than return a value that failed
        validation -- callers should never have to re-check the shape.
        """
        ...

    def describe(self) -> str:
        """One-line, human-readable summary of provider/model/sampling
        settings actually in effect -- e.g. for a startup preamble so it's
        obvious which backend and knobs produced a given clustering, without
        callers needing to know each backend's field names.
        """
        ...

    def usage_summary(self) -> str:
        """One-line summary of time and tokens spent across every
        complete_structured() call made so far on this client instance.
        Cumulative rather than last-call-only on purpose: a caller like
        cluster_silos() can retry a failed attempt, and those retries still
        cost real time and tokens that a "last call" figure would hide.
        """
        ...
