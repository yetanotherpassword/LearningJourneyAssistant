"""Regression tests for two real bugs found by running against a live
LM Studio endpoint (see openai_compatible_client.py's module docstring):

1. A server that rejects response_format: json_object outright -- the
   client must try a different strategy, not repeat the identical request.
2. A reasoning model that spends its whole max_tokens budget on
   chain-of-thought and returns empty `content` with finish_reason="length"
   -- this must fail clearly, not be parsed as if it were valid JSON.

Both are exercised here against a fake stand-in for the openai SDK client,
not a live server -- deterministic and offline, like the rest of the suite.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from pydantic import BaseModel

from lja.llm.openai_compatible_client import OpenAICompatibleClient


class _Schema(BaseModel):
    ok: bool


def _completion(*, content: str, finish_reason: str = "stop"):
    message = SimpleNamespace(content=content)
    choice = SimpleNamespace(message=message, finish_reason=finish_reason)
    return SimpleNamespace(choices=[choice])


class _FakeChatCompletions:
    """Queues canned responses (or exceptions) and records the
    response_format each call was made with, so tests can assert on the
    fallback order without a real server.
    """

    def __init__(self, responses: list) -> None:
        self._responses = list(responses)
        self.calls: list[dict] = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        next_response = self._responses.pop(0)
        if isinstance(next_response, Exception):
            raise next_response
        return next_response


def _client_with(responses: list) -> tuple[OpenAICompatibleClient, _FakeChatCompletions]:
    client = OpenAICompatibleClient(base_url="http://fake/v1", model="fake-model")
    fake_completions = _FakeChatCompletions(responses)
    client._client = SimpleNamespace(
        base_url="http://fake/v1",
        chat=SimpleNamespace(completions=fake_completions),
    )
    return client, fake_completions


def test_valid_json_on_first_attempt() -> None:
    client, fake = _client_with([_completion(content='{"ok": true}')])
    result = client.complete_structured(system="sys", user="usr", schema=_Schema)
    assert result == _Schema(ok=True)
    assert len(fake.calls) == 1
    assert fake.calls[0]["response_format"]["type"] == "json_schema"


def test_json_schema_rejected_falls_back_to_json_object() -> None:
    """The exact real failure: a server 400s on response_format entirely,
    or (as observed live) specifically rejects one variant. The second
    attempt must use a DIFFERENT response_format, not repeat the first.
    """
    client, fake = _client_with(
        [
            RuntimeError("400 'response_format.type' must be 'json_schema' or 'text'"),
            _completion(content='{"ok": true}'),
        ]
    )
    result = client.complete_structured(system="sys", user="usr", schema=_Schema)
    assert result == _Schema(ok=True)
    assert len(fake.calls) == 2
    assert fake.calls[0]["response_format"]["type"] == "json_schema"
    assert fake.calls[1]["response_format"]["type"] == "json_object"


def test_empty_content_with_length_finish_reason_is_treated_as_failure() -> None:
    """The bug found live against qwen3.5-35b-a3b: a reasoning model burns
    its whole max_tokens budget on chain-of-thought (visible only in
    reasoning_content, which this client does not read) and returns empty
    `content` with finish_reason="length". That must not be silently
    parsed as empty-but-valid; it must fail loudly enough to point at
    max_tokens as the cause.
    """
    client, fake = _client_with(
        [
            _completion(content="", finish_reason="length"),
            _completion(content="", finish_reason="length"),
            _completion(content="", finish_reason="length"),
        ]
    )
    with pytest.raises(RuntimeError, match="finish_reason='length'"):
        client.complete_structured(system="sys", user="usr", schema=_Schema)
    assert len(fake.calls) == 3


def test_max_tokens_is_sent_on_every_request() -> None:
    client = OpenAICompatibleClient(base_url="http://fake/v1", model="fake-model", max_tokens=1234)
    fake = _FakeChatCompletions([_completion(content='{"ok": true}')])
    client._client = SimpleNamespace(base_url="http://fake/v1", chat=SimpleNamespace(completions=fake))
    client.complete_structured(system="sys", user="usr", schema=_Schema)
    assert fake.calls[0]["max_tokens"] == 1234


def test_temperature_is_sent_when_set() -> None:
    client = OpenAICompatibleClient(base_url="http://fake/v1", model="fake-model", temperature=0.4)
    fake = _FakeChatCompletions([_completion(content='{"ok": true}')])
    client._client = SimpleNamespace(base_url="http://fake/v1", chat=SimpleNamespace(completions=fake))
    client.complete_structured(system="sys", user="usr", schema=_Schema)
    assert fake.calls[0]["temperature"] == 0.4


def test_temperature_omitted_when_none() -> None:
    """None means: don't send the field at all, rely on the server's own
    default -- distinct from sending an explicit 0.0.
    """
    client = OpenAICompatibleClient(base_url="http://fake/v1", model="fake-model", temperature=None)
    fake = _FakeChatCompletions([_completion(content='{"ok": true}')])
    client._client = SimpleNamespace(base_url="http://fake/v1", chat=SimpleNamespace(completions=fake))
    client.complete_structured(system="sys", user="usr", schema=_Schema)
    assert "temperature" not in fake.calls[0]
