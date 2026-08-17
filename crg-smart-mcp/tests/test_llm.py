"""Tests for crg_smart_mcp.llm."""
from __future__ import annotations

import json
from unittest import mock

import pytest

from crg_smart_mcp.llm import summarize_with_llm


def _fake_response(content: str, status: int = 200):
    resp = mock.Mock()
    resp.status = status
    resp.read.return_value = json.dumps({
        "choices": [{"message": {"content": content}}]
    }).encode()
    resp.__enter__ = mock.Mock(return_value=resp)
    resp.__exit__ = mock.Mock(return_value=False)
    return resp


def test_summarize_happy(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CRG_SMART_LLM_KEY", "k")
    with mock.patch("urllib.request.urlopen", return_value=_fake_response("OK")):
        result = summarize_with_llm("user prompt", system="sys")
    assert result == "OK"


def test_summarize_missing_key_returns_none(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CRG_SMART_LLM_KEY", raising=False)
    assert summarize_with_llm("user", system="sys") is None


def test_summarize_http_error_returns_none(monkeypatch: pytest.MonkeyPatch) -> None:
    import urllib.error
    monkeypatch.setenv("CRG_SMART_LLM_KEY", "k")
    def raise_err(*a, **k):
        raise urllib.error.HTTPError(url="", code=500, msg="err", hdrs=None, fp=None)
    with mock.patch("urllib.request.urlopen", side_effect=raise_err):
        assert summarize_with_llm("user", system="sys") is None


def test_summarize_url_error_returns_none(monkeypatch: pytest.MonkeyPatch) -> None:
    import urllib.error
    monkeypatch.setenv("CRG_SMART_LLM_KEY", "k")
    def raise_url(*a, **k):
        raise urllib.error.URLError("connection refused")
    with mock.patch("urllib.request.urlopen", side_effect=raise_url):
        assert summarize_with_llm("user", system="sys") is None