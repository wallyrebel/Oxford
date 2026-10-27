"""Bounded replacement requests and managed legacy overrides, without network writes."""
from unittest.mock import Mock

import pytest

from rss_to_wp.rewriter.openai_client import OpenAIRewriter
from rss_to_wp.rewriter.model_options import chat_model_params, resolve_retired_model


@pytest.mark.parametrize("legacy", ["gpt-4.1-nano", "gpt-4.1-nano-2025-04-14"])
def test_managed_retired_model_override_is_mapped(legacy):
    assert resolve_retired_model(legacy) == "gpt-6-luna"
    assert OpenAIRewriter(api_key="offline-test", model=legacy).model == "gpt-6-luna"


@pytest.mark.parametrize("token_name", ["max_tokens", "max_completion_tokens"])
def test_nano_request_keeps_budget_and_json_contract(token_name):
    original = {"model": "gpt-4.1-nano", token_name: 2000, "temperature": 0.7,
                "messages": [{"role": "user", "content": "Write JSON"}],
                "response_format": {"type": "json_object"}}
    result = chat_model_params(original)
    assert result["model"] == "gpt-6-luna"
    assert result["max_completion_tokens"] == 2000
    assert result["reasoning_effort"] == "none"
    assert "temperature" not in result and "max_tokens" not in result
    assert result["messages"] == original["messages"]
    assert result["response_format"] == original["response_format"]
    assert original["model"] == "gpt-4.1-nano"  # No inherited fallback mutation.


def test_other_model_and_disabled_fallback_are_preserved():
    params = {"model": "gpt-5.4-mini", "temperature": 0.7, "max_completion_tokens": 3200}
    assert chat_model_params(params) == params
    assert resolve_retired_model(None) is None
    assert resolve_retired_model("") == ""


def test_actual_rewriter_request_uses_compatible_nano_parameters(monkeypatch):
    editor = OpenAIRewriter(api_key="offline-test", model="gpt-4.1-nano")
    if hasattr(editor, "fallback_model"):
        editor.fallback_model = None
    monkeypatch.setattr(editor, "_rate_limit", lambda: None, raising=False)
    request = Mock(side_effect=RuntimeError("intentional offline request capture"))
    monkeypatch.setattr(editor.client.chat.completions, "create", request)
    try:
        if hasattr(editor, "extraction_model"):
            editor.extraction_model = "gpt-6-luna"
        editor.rewrite("County officials reopened Main Street after crews completed bridge repairs. The road is open to traffic.", "Main Street reopens")
    except RuntimeError:
        pass
    assert request.called
    kwargs = request.call_args_list[0].kwargs
    assert kwargs["model"] == "gpt-6-luna"
    assert kwargs["reasoning_effort"] == "none"
    assert kwargs["max_completion_tokens"] == editor.max_tokens
    assert "temperature" not in kwargs and "max_tokens" not in kwargs
