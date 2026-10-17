from types import SimpleNamespace

import httpx
import pytest
import groq

from feedback import ModelUnavailable, propose


def fake_client(monkeypatch, create):
    monkeypatch.setenv("GROQ_API_KEY", "test-only-not-a-key")

    class Client:
        def __init__(self, **kwargs):
            assert kwargs["max_retries"] == 0
            self.chat = SimpleNamespace(
                completions=SimpleNamespace(with_raw_response=SimpleNamespace(create=create))
            )

        def __enter__(self):
            return self

        def __exit__(self, *_):
            pass

    monkeypatch.setattr(groq, "Groq", Client)


def test_strict_response_and_usage(monkeypatch):
    def create(**kwargs):
        assert kwargs["model"] == "openai/gpt-oss-120b"
        assert kwargs["reasoning_effort"] == "medium"
        assert kwargs["max_completion_tokens"] == 2048
        assert not kwargs["stream"]
        assert kwargs["response_format"]["json_schema"]["strict"]
        result = SimpleNamespace(
            choices=[
                SimpleNamespace(
                    finish_reason="stop",
                    message=SimpleNamespace(content='{"explanation":"No justified change","edits":[]}'),
                )
            ],
            usage=SimpleNamespace(model_dump=lambda: {"total_tokens": 123}),
        )
        return SimpleNamespace(
            parse=lambda: result, headers={"x-ratelimit-remaining-tokens": "7000", "unrelated": "ignored"}
        )

    fake_client(monkeypatch, create)
    proposal = propose({"sources": {}})
    assert proposal._metadata["usage"]["total_tokens"] == 123
    assert "unrelated" not in proposal._metadata["rate_limits"]


def test_rate_limit_stops_without_hidden_retry(monkeypatch):
    calls = []

    def create(**_):
        calls.append(1)
        response = httpx.Response(
            429, request=httpx.Request("POST", "https://api.groq.com"), headers={"retry-after": "45"}
        )
        raise groq.RateLimitError("limited", response=response, body={})

    fake_client(monkeypatch, create)
    with pytest.raises(ModelUnavailable, match="45 seconds"):
        propose({})
    assert len(calls) == 1


def test_truncated_output_never_applied(monkeypatch):
    fake_client(
        monkeypatch,
        lambda **_: SimpleNamespace(
            parse=lambda: SimpleNamespace(choices=[SimpleNamespace(finish_reason="length")]), headers={}
        ),
    )
    with pytest.raises(ValueError, match="completion budget"):
        propose({})
