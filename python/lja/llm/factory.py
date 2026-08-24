"""Reads LJA_LLM_PROVIDER and hands back the matching LLMClient. This is the
only place that should ever branch on the provider name -- everywhere else
just calls get_llm_client() and programs against LLMClient.
"""

from __future__ import annotations

from .. import config
from .anthropic_client import AnthropicClient
from .base import LLMClient
from .openai_compatible_client import OpenAICompatibleClient


def get_llm_client() -> LLMClient:
    if config.LLM_PROVIDER == "anthropic":
        if not config.ANTHROPIC_API_KEY:
            raise RuntimeError(
                "LJA_LLM_PROVIDER=anthropic but ANTHROPIC_API_KEY is not set. "
                "See python/.env.example."
            )
        return AnthropicClient(
            model=config.ANTHROPIC_MODEL,
            api_key=config.ANTHROPIC_API_KEY,
            effort=config.ANTHROPIC_EFFORT,
            thinking=config.ANTHROPIC_THINKING,
        )

    if config.LLM_PROVIDER == "openai_compatible":
        return OpenAICompatibleClient(
            base_url=config.OPENAI_BASE_URL,
            model=config.OPENAI_MODEL,
            api_key=config.OPENAI_API_KEY,
            max_tokens=config.OPENAI_MAX_TOKENS,
            temperature=config.OPENAI_TEMPERATURE,
        )

    raise ValueError(
        f"Unknown LJA_LLM_PROVIDER: {config.LLM_PROVIDER!r} "
        f"(expected 'anthropic' or 'openai_compatible')"
    )
