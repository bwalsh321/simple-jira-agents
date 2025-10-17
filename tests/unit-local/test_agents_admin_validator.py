# tests/unit-local/test_agents_admin_validator.py
import pytest
from llm.agents.admin_validator import process_admin_request  # correct path


class FakeJira:
    def __init__(self, dup=0, sim=0, create_ok=True):
        self.comments = []
        self._dup = dup
        self._sim = sim
        self._create_ok = create_ok

    def add_comment(self, key, body):
        self.comments.append((key, body))
        return {"ok": True}

    def check_duplicate_field(self, name):
        return {
            "duplicates": list(range(self._dup)),
            "similar": list(range(self._sim)),
            "total_checked": 10,
        }

    def create_custom_field(self, field_name, field_type, description, options):
        if not self._create_ok:
            return {"error": "nope"}
        return {"field": {"id": "cf_123", "name": field_name}}


class FakeConfig:
    pass


@pytest.fixture(autouse=True)
def patch_jira_and_llm(monkeypatch):
    import llm.agents.admin_validator as av

    # Default Jira fake (can be overridden per test)
    monkeypatch.setattr(av, "JiraAPI", lambda cfg: FakeJira())

    # Default LLM that approves (can be overridden per test)
    class FLLM:
        def __init__(self, cfg): ...
        def chat(self, prompt, system_prompt=None):
            return {"approved": True, "reason": "no duplicates", "auto_create": True}

    monkeypatch.setattr(av, "LLMProvider", lambda cfg: FLLM(cfg))
    yield


def test_admin_validator_happy_path_creates_field(monkeypatch):
    import llm.agents.admin_validator as av

    # Ensure a non-empty field name so we don't hit the needs_info early return
    monkeypatch.setattr(
        av, "extract_field_details",
        lambda summary, description: {
            "field_name": "Foo",
            "field_type": "text",
            "field_options": [],
        },
    )
    # Zero duplicates, allow creation
    monkeypatch.setattr(av, "JiraAPI", lambda cfg: FakeJira(dup=0, sim=1, create_ok=True))

    issue = {"fields": {"summary": "Create custom field Foo", "description": "text field"}}
    out = process_admin_request("ABC-1", issue, FakeConfig())

    assert out["success"] is True
    assert out["status"] == "approved"
    assert out["field_created"] is True
    assert out["duplicates_found"] == 0


def test_admin_validator_dup_found_blocks_create(monkeypatch):
    import llm.agents.admin_validator as av

    monkeypatch.setattr(
        av, "extract_field_details",
        lambda summary, description: {
            "field_name": "Foo",
            "field_type": "text",
            "field_options": [],
        },
    )
    # Duplicates present → should not create
    monkeypatch.setattr(av, "JiraAPI", lambda cfg: FakeJira(dup=2, sim=3, create_ok=True))

    issue = {"fields": {"summary": "Create custom field Foo", "description": "text field"}}
    out = process_admin_request("ABC-2", issue, FakeConfig())

    assert out["success"] is True
    # Could be approved/rejected by LLM; key behavior is: no creation if duplicates > 0
    assert out["field_created"] is False


def test_admin_validator_handles_llm_failure(monkeypatch):
    import llm.agents.admin_validator as av

    monkeypatch.setattr(
        av, "extract_field_details",
        lambda summary, description: {
            "field_name": "Bar",
            "field_type": "select",
            "field_options": [],
        },
    )

    # Make LLM return an error shape
    class FLLM:
        def __init__(self, cfg): ...
        def chat(self, prompt, system_prompt=None):
            return {"error": "down"}

    monkeypatch.setattr(av, "LLMProvider", lambda cfg: FLLM(cfg))
    monkeypatch.setattr(av, "JiraAPI", lambda cfg: FakeJira(dup=0, sim=0))

    issue = {"fields": {"summary": "Create field Bar", "description": "picklist"}}
    out = process_admin_request("ABC-3", issue, FakeConfig())

    assert out["success"] is True
    # With LLM failure we should NOT auto-create
    assert out["field_created"] is False
    assert out["status"] in ("rejected", "approved") or "duplicates_found" in out  # structure sanity


def test_admin_validator_needs_info_when_no_field_name(monkeypatch):
    """Explicitly cover the early return when field_name is empty."""
    import llm.agents.admin_validator as av

    monkeypatch.setattr(
        av, "extract_field_details",
        lambda summary, description: {
            "field_name": "",
            "field_type": "text",
            "field_options": [],
        },
    )
    issue = {"fields": {"summary": "Create some field", "description": "no clear name"}}
    out = process_admin_request("ABC-4", issue, FakeConfig())

    assert out["success"] is True
    assert out["status"] == "needs_info"
    # early return doesn't include field_created — that's expected