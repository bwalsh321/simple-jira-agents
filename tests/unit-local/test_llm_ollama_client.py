import json
import types
import pytest

from core.config import Config
from llm.ollama_client import call_ollama, _clean_response_text, _get_structured_fallback

# ---- helpers ----

class FakeResp:
    def __init__(self, status=200, payload=None):
        self.status_code = status
        self._payload = payload or {"response": ""}
    def raise_for_status(self):
        if self.status_code >= 400:
            raise Exception(f"HTTP {self.status_code}")
    def json(self):
        return self._payload

class _FakeReq:
    def __init__(self):
        self.calls = []
        self.to_raise = None
        self.response = FakeResp(200, {"response": '{"approved": true, "auto_create": true, "reason":"ok"}'})
    def post(self, url, json=None, timeout=None):
        self.calls.append({"url": url, "json": json, "timeout": timeout})
        if self.to_raise:
            raise self.to_raise
        return self.response

@pytest.fixture
def fake_requests(monkeypatch):
    fr = _FakeReq()
    import llm.ollama_client as oc
    import requests as real_requests
    fr.exceptions = real_requests.exceptions 
    monkeypatch.setattr(oc, "requests", fr) 
    return fr

@pytest.fixture
def cfg():
    c = Config()
    # keep these deterministic for tests
    c.ollama_url = "http://localhost:11434/api/generate"
    c.model = "llama3.1:8b"
    return c

# ---- unit tests for cleaners ----

def test_clean_response_variants():
    # code fences
    t1 = "```json\n{\"a\":1,\"b\":2}\n```"
    assert json.loads(_clean_response_text(t1)) == {"a": 1, "b": 2}

    # prefixed text with JSON later
    t2 = "Here is the JSON:\nSome blah\n{ \"x\": 10 } extra"
    assert json.loads(_clean_response_text(t2)) == {"x": 10}

    # nested braces cut at balance
    t3 = '{"a":{"b":2},"c":3} trailing junk } }'
    assert json.loads(_clean_response_text(t3)) == {"a": {"b": 2}, "c": 3}

# ---- happy path ----

def test_call_ollama_returns_parsed_json(fake_requests, cfg):
    out = call_ollama(prompt="Admin field check", system_prompt="SYS", config=cfg)
    assert isinstance(out, dict)
    assert out["approved"] is True
    assert out["auto_create"] is True
    # confirms we sent fields to the right url with timeout
    assert fake_requests.calls and fake_requests.calls[0]["url"] == cfg.ollama_url
    assert fake_requests.calls[0]["timeout"] == 60

# ---- short/empty response fallback ----

def test_call_ollama_empty_response_triggers_fallback(fake_requests, cfg):
    fake_requests.response = FakeResp(200, {"response": ""})
    out = call_ollama(prompt="admin new field", system_prompt="", config=cfg)
    # structured admin fallback (no 'error' key, has fallback_reason)
    assert isinstance(out, dict)
    assert out.get("fallback_reason") == "empty_response"

# ---- invalid json fallback ----

def test_call_ollama_invalid_json_fallback(fake_requests, cfg):
    fake_requests.response = FakeResp(200, {"response": "Not JSON at all"})
    out = call_ollama(prompt="field create please", system_prompt="", config=cfg)
    assert out.get("fallback_reason") == "invalid_json"

# ---- HTTP error ----

def test_call_ollama_http_error(fake_requests, cfg):
    fake_requests.response = FakeResp(500, {"response": ""})
    out = call_ollama(prompt="governance", system_prompt="", config=cfg)
    assert out.get("fallback_reason") == "error"

# ---- connection/timeout ----

def test_call_ollama_timeout(fake_requests, cfg):
    import requests
    fake_requests.to_raise = requests.exceptions.Timeout()
    out = call_ollama(prompt="admin", system_prompt="", config=cfg)
    assert out.get("fallback_reason") == "timeout"

def test_call_ollama_conn_error(fake_requests, cfg):
    import requests
    fake_requests.to_raise = requests.exceptions.ConnectionError()
    out = call_ollama(prompt="enhance meeting notes", system_prompt="", config=cfg)
    assert out.get("fallback_reason") == "connection_error"

# ---- admin/governance/enhance routing in fallback ----

@pytest.mark.parametrize("kw, expected_marker", [
    ("custom field", "ai-fallback"),
    ("governance", "governance-bot-fallback"),
    ("enhance story", "pm-ai-fallback"),
])
def test_fallback_buckets_by_prompt(kw, expected_marker):
    fb = _get_structured_fallback(kw, "timeout")
    assert expected_marker in fb.get("marker", "") or isinstance(fb.get("plan"), list)