# tests/unit-local/test_rules_with_fake_jira.py
import pytest

from rules.stale_tickets import StaleTicketRule
from rules.missing_fields import MissingFieldsRule
from rules.workflow_validator import WorkflowValidatorRule
from rules.duplicate_work_item_check import DuplicateCheckRule


class FakeJira:
    """Minimal stub for JiraAPI used by rule tests."""
    def __init__(self, issues=None):
        # issues is a list of dicts shaped like Jira search payloads expects
        self._issues = issues or []
        self._comments = []
        self._labels_added = []

    # ---- search API (supports pagination) ----
    def search_issues(self, jql, start_at=0, max_results=50, fields=None):
        # Simulate Jira's 'issues' window and a 'total' count
        window = self._issues[start_at : start_at + max_results]
        return {
            "issues": window,
            "total": len(self._issues),
        }

    # ---- writes ----
    def add_comment(self, key, body):
        self._comments.append((key, body))
        return {"ok": True}

    def add_label(self, key, label):
        self._labels_added.append((key, label))
        return {"ok": True}


# ---------- DuplicateCheckRule ok path ----------

def test_duplicate_check_ok_path_adds_comment_when_dupes_found():
    # Fake search returns two "other" issues (exclude current via rule logic)
    fake = FakeJira(issues=[
        {"key": "ABC-2", "fields": {"summary": "Printer not working"}},
        {"key": "ABC-3", "fields": {"summary": "Printer jams"}},
    ])
    r = DuplicateCheckRule(projects=["ABC"], lookback_days=14, add_comment=True)
    r.jira = fake  # use stub

    data = {"eventType": "issue_created",
            "issue": {"key": "ABC-1", "fields": {"summary": "Printer not working"}}}

    res = r.execute(data)
    assert res["status"] == "ok"
    assert len(res["duplicates"]) == 2
    # 1 comment written to the current key
    assert fake._comments and fake._comments[0][0] == "ABC-1"
    assert "Possible duplicates" in fake._comments[0][1]


# ---------- StaleTicketRule ok path ----------

def test_stale_tickets_ok_path_paginates_and_writes():
    # 3 stale issues; batch size will force pagination
    issues = [{"key": f"ABC-{i}"} for i in range(1, 4)]
    fake = FakeJira(issues=issues)

    r = StaleTicketRule(
        days=7,
        projects=["ABC"],
        add_comment=True,
        add_label="stale",
        batch_size=2,  # force 2 + 1 pagination
        enabled=True,
    )
    r.jira = fake

    res = r.execute({"eventType": "scheduled_sweep"})
    assert res["status"] == "ok"
    assert set(res["issue_keys"]) == {"ABC-1", "ABC-2", "ABC-3"}
    # side effects counted
    assert res["actions"]["comments"] == 3
    assert res["actions"]["labels"] == 3
    # stub recorded writes
    assert len(fake._comments) == 3
    assert len(fake._labels_added) == 3


# ---------- MissingFieldsRule ok path ----------

def test_missing_fields_ok_path_flags_and_comments():
    # search_issues returns issues (keys only is fine for our rule)
    fake = FakeJira(issues=[{"key": "SBX-10"}, {"key": "SBX-11"}])

    r = MissingFieldsRule(
        required=["Story Points", "labels"],
        projects=["SBX"],
        add_comment=True,
        comment_text="Missing fields — please update.",
        add_label="missing-required-fields",
        enabled=True,
        batch_size=50,
    )
    r.jira = fake

    res = r.execute({"eventType": "scheduled_sweep"})
    assert res["status"] == "ok"
    assert res["issues_flagged"] == 2
    assert set(res["issue_keys"]) == {"SBX-10", "SBX-11"}
    assert res["actions"]["comments"] == 2
    assert res["actions"]["labels"] == 2
    assert fake._comments[0][1].startswith("Missing fields")


# ---------- WorkflowValidatorRule ok path ----------

def test_workflow_validator_ok_path_builds_per_issue_violations_and_writes():
    # Provide fields the validator inspects: assignee + required fields
    fake = FakeJira(issues=[
        {"key": "WFK-1", "fields": {"assignee": None, "Story Points": None}},
        {"key": "WFK-2", "fields": {"assignee": {"displayName": "Tori"}, "Story Points": 3}},
        {"key": "WFK-3", "fields": {"assignee": None, "Story Points": 5}},
    ])

    r = WorkflowValidatorRule(
        statuses=["In Progress", "QA"],
        projects=["WFK"],
        require_assignee=True,
        require_fields=["Story Points"],
        add_comment=True,
        add_label="workflow-violation",
        enabled=True,
        batch_size=10,
    )
    r.jira = fake

    res = r.execute({"eventType": "scheduled_sweep"})
    assert res["status"] == "ok"
    # WFK-1 and WFK-3 violate (missing assignee); WFK-1 also missing Story Points
    assert set(res["issue_keys"]) == {"WFK-1", "WFK-3"}
    vios = res["violations"]
    assert vios["WFK-1"] == ["Missing assignee", "Missing field: Story Points"]
    assert vios["WFK-3"] == ["Missing assignee"]

    # Comments and labels written only for flagged issues
    assert res["actions"]["comments"] == 2
    assert res["actions"]["labels"] == 2
    keys_commented = [k for k, _ in fake._comments]
    assert set(keys_commented) == {"WFK-1", "WFK-3"}