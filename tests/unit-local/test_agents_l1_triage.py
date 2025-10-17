import pytest
from llm.agents.l1_triage_bot import process_ticket as triage

class FakeJira:
    def __init__(self, issues=None, fail_comment=False):
        self.issues = issues or []
        self.fail_comment = fail_comment
        self.comments = []
    def search_issues(self, jql, max_results=10):
        return {"issues": self.issues, "total": len(self.issues)}
    def add_comment(self, key, body):
        if self.fail_comment:
            return {"error": "permission denied"}
        self.comments.append((key, body))
        return {"ok": True}

class FakeLLM:
    def __init__(self, cfg): pass
    def chat(self, prompt, system_prompt=None):
        return "Step 1: Try rebooting\nStep 2: Check cables"

class FakeConfig: pass

@pytest.fixture(autouse=True)
def patch_deps(monkeypatch):
    import llm.agents.l1_triage_bot as l1
    monkeypatch.setattr(l1, "JiraAPI", lambda cfg: FakeJira(
        issues=[
            {"key":"ABC-2","fields":{"summary":"WiFi drops frequently"}},
            {"key":"ABC-3","fields":{"summary":"Email not syncing"}},
        ]
    ))
    monkeypatch.setattr(l1, "LLMProvider", lambda cfg: FakeLLM(cfg))
    yield

def test_triage_posts_comment_and_returns_success():
    issue = {"fields": {"summary": "WiFi not working", "description": "User cannot connect"}}
    out = triage("ABC-1", issue, FakeConfig())
    assert out["success"] is True
    assert out["response_length"] > 0

def test_triage_handles_comment_failure(monkeypatch):
    import llm.agents.l1_triage_bot as l1
    monkeypatch.setattr(l1, "JiraAPI", lambda cfg: FakeJira(fail_comment=True))
    issue = {"fields": {"summary": "VPN fails", "description": "timeout"}}
    out = triage("ABC-9", issue, FakeConfig())
    assert out["success"] is False