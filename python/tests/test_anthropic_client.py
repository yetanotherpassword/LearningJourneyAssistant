"""Unit tests for lja.llm.anthropic_client. Exercised against a fake stand-in
for the anthropic SDK client -- there is no Anthropic API key configured in
this dev environment (the team runs the OpenAI-compatible/local path day to
day; see python/README.md), so these check request construction only, not a
live round-trip. In particular: that output_config.format and effort are
built as sibling keys of ONE dict (not two separate request params), since
that's the whole point of not using client.messages.parse() here -- see the
module docstring in anthropic_client.py.
"""

from __future__ import annotations

import anthropic

from types import SimpleNamespace

from pydantic import BaseModel

from lja.llm.anthropic_client import AnthropicClient


class _Schema(BaseModel):
    ok: bool


def _text_response(text: str):
    block = SimpleNamespace(type="text", text=text)
    usage = SimpleNamespace(input_tokens=10, output_tokens=5)
    return SimpleNamespace(content=[block], usage=usage)


class _FakeMessages:
    def __init__(self, response) -> None:
        self._response = response
        self.calls: list[dict] = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return self._response


def _client_with(response, **client_kwargs) -> tuple[AnthropicClient, _FakeMessages]:
    client = AnthropicClient(model="fake-model", api_key="not-needed", **client_kwargs)
    fake_messages = _FakeMessages(response)
    client._client = SimpleNamespace(messages=fake_messages)
    return client, fake_messages


def test_returns_validated_schema_from_text_block() -> None:
    client, fake = _client_with(_text_response('{"ok": true}'))
    result = client.complete_structured(system="sys", user="usr", schema=_Schema)
    assert result == _Schema(ok=True)
    assert len(fake.calls) == 1


def test_output_config_format_carries_the_json_schema() -> None:
    client, fake = _client_with(_text_response('{"ok": true}'))
    client.complete_structured(system="sys", user="usr", schema=_Schema)
    output_config = fake.calls[0]["output_config"]
    assert output_config["format"]["type"] == "json_schema"
    assert output_config["format"]["schema"] == anthropic.transform_schema(
        _Schema.model_json_schema()
    )

def test_effort_and_format_are_sibling_keys_of_one_output_config() -> None:
    """The reason this client doesn't use .parse(): effort must land next
    to format inside the SAME output_config dict, not as a second request
    parameter that might silently override or be overridden by the one
    .parse() would build from output_format=.
    """
    client, fake = _client_with(_text_response('{"ok": true}'), effort="high")
    client.complete_structured(system="sys", user="usr", schema=_Schema)
    output_config = fake.calls[0]["output_config"]
    assert output_config["effort"] == "high"
    assert output_config["format"]["type"] == "json_schema"


def test_effort_omitted_by_default() -> None:
    client, fake = _client_with(_text_response('{"ok": true}'))
    client.complete_structured(system="sys", user="usr", schema=_Schema)
    assert "effort" not in fake.calls[0]["output_config"]


def test_thinking_omitted_by_default() -> None:
    client, fake = _client_with(_text_response('{"ok": true}'))
    client.complete_structured(system="sys", user="usr", schema=_Schema)
    assert "thinking" not in fake.calls[0]


def test_thinking_enabled_sends_adaptive() -> None:
    client, fake = _client_with(_text_response('{"ok": true}'), thinking=True)
    client.complete_structured(system="sys", user="usr", schema=_Schema)
    assert fake.calls[0]["thinking"] == {"type": "adaptive"}


def test_finds_text_block_even_when_it_is_not_first() -> None:
    """Guards against assuming content[0] is always the answer -- with
    thinking enabled, a thinking block can precede the text block.
    """
    thinking_block = SimpleNamespace(type="thinking", text=None)
    text_block = SimpleNamespace(type="text", text='{"ok": true}')
    usage = SimpleNamespace(input_tokens=10, output_tokens=5)
    response = SimpleNamespace(content=[thinking_block, text_block], usage=usage)
    client, fake = _client_with(response, thinking=True)
    result = client.complete_structured(system="sys", user="usr", schema=_Schema)
    assert result == _Schema(ok=True)
