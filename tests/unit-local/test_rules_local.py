# tests/unit-local/test_rules_local.py
import pytest

from rules.duplicate_work_item_check import DuplicateCheckRule
from rules.missing_fields import MissingFieldsRule
from rules.stale_tickets import StaleTicketRule
from rules.workflow_validator import WorkflowValidatorRule


# ----------------------------
# Helpers
# ----------------------------

def ev_issue_created(issue_key="ABC-123", summary="Sample summary"):
    return {
        "eventType": "issue_created",
        "issue": {
            "key": issue_key,
            "fields": {"summary": summary},
        },
    }


def ev_issue_updated(issue_key="ABC-123", summary="Sample summary"):
    return {
        "eventType": "issue_updated",
        "issue": {
            "key": issue_key,
            "fields": {"summary": summary},
        },
    }


def ev_sweep():
    return {"eventType": "scheduled_sweep"}


def norm_ws(s: str) -> str:
    """Normalize whitespace for stable JQL comparisons."""
    return " ".join((s or "").split())


# ----------------------------
# DuplicateCheckRule
# ----------------------------

def test_duplicate_should_run_only_on_create_update():
    r = DuplicateCheckRule(projects=["ABC"], lookback_days=14, enabled=True)
    r.jira = None  # force dry run

    assert r.should_run(ev_issue_created())
    assert r.should_run(ev_issue_updated())
    assert not r.should_run(ev_sweep())


def test_duplicate_execute_dry_run_jql_and_payload_simple():
    r = DuplicateCheckRule(projects=["ABC"], lookback_days=14, enabled=True, max_results=5)
    r.jira = None

    data = ev_issue_created("ABC-7", "Printer not working")
    res = r.execute(data)

    assert res["rule"] == "DuplicateCheckRule"
    assert res["status"] == "dry_run"
    assert res["issue_key"] == "ABC-7"
    assert isinstance(res["duplicates"], list) and res["duplicates"] == []
    assert res["actions"] == {"comments": 0}
    # JQL shape
    expect = (
        'project in (ABC) AND text ~ "Printer not working" '
        "AND key != ABC-7 AND created >= -14d ORDER BY created DESC"
    )
    assert norm_ws(res["jql"]) == norm_ws(expect)


def test_duplicate_execute_escapes_quotes_in_summary():
    r = DuplicateCheckRule(projects=["ABC"], lookback_days=3, enabled=True)
    r.jira = None

    data = ev_issue_updated("ABC-9", 'User says: "cannot login"')
    res = r.execute(data)

    assert res["status"] == "dry_run"
    # Expect the inner quote to be escaped for JQL
    assert '\\"cannot login\\"' in res["jql"]


def test_duplicate_skips_when_no_issue_context():
    r = DuplicateCheckRule(enabled=True)
    r.jira = None

    res = r.execute({"eventType": "issue_created"})  # missing issue
    assert res["status"] == "skipped"
    assert res["reason"] == "no_issue_context"


# ----------------------------
# MissingFieldsRule
# ----------------------------

def test_missing_fields_should_run_on_create_update_and_sweep():
    r = MissingFieldsRule(required=["Story Points", "labels"], projects=["ABC"], enabled=True)
    r.jira = None

    assert r.should_run(ev_issue_created())
    assert r.should_run(ev_issue_updated())
    assert r.should_run(ev_sweep())


def test_missing_fields_execute_dry_run_and_jql_building():
    r = MissingFieldsRule(
        required=["Story Points", "labels"],
        projects=["ABC"],
        statuses=["In Progress", "Ready for Dev"],
        exclude_statuses=["On Hold"],
        enabled=True,
        max_results=100,
        batch_size=50,
    )
    r.jira = None

    res = r.execute(ev_sweep())
    assert res["rule"] == "MissingFieldsRule"
    assert res["status"] == "dry_run"
    assert res["issues_flagged"] == 0
    assert res["issue_keys"] == []
    assert res["actions"] == {"comments": 0, "labels": 0}
    assert res["checked_fields"] == ["Story Points", "labels"]

    jql = norm_ws(res["jql"])
    assert "project in (ABC)" in jql
    assert "statusCategory != Done" in jql
    assert 'status in ("In Progress","Ready for Dev")' in jql.replace(", ", "")
    assert 'status not in ("On Hold")' in jql
    assert '("Story Points" is EMPTY OR labels is EMPTY)' in jql.replace("  ", " ")


def test_missing_fields_raises_when_required_is_empty():
    with pytest.raises(ValueError):
        MissingFieldsRule(required=[], projects=["ABC"])


# ----------------------------
# StaleTicketRule
# ----------------------------

def test_stale_should_run_on_update_and_sweep_only():
    r = StaleTicketRule(days=7, projects=["ABC"], enabled=True)
    r.jira = None

    assert not r.should_run(ev_issue_created())
    assert r.should_run(ev_issue_updated())
    assert r.should_run(ev_sweep())


@pytest.mark.parametrize(
    "days, expect_fragment",
    [
        (7, "updated < -7d AND statusCategory != Done"),
        (0, "statusCategory != Done"),               # match all open
        (-5, "statusCategory != Done"),              # non positive coerces to open
    ],
)
def test_stale_execute_dry_run_jql(days, expect_fragment):
    r = StaleTicketRule(days=days, projects=["ABC"], enabled=True, exclude_statuses=["Blocked"], exclude_labels=["stale"])
    r.jira = None

    res = r.execute(ev_sweep())
    assert res["status"] == "dry_run"
    jql = norm_ws(res["jql"])
    assert "project in (ABC)" in jql
    assert expect_fragment in jql
    assert 'status not in ("Blocked")' in jql
    assert 'labels not in ("stale")' in jql


# ----------------------------
# WorkflowValidatorRule
# ----------------------------

def test_workflow_validator_requires_statuses():
    with pytest.raises(ValueError):
        WorkflowValidatorRule(statuses=[], projects=["ABC"])


def test_workflow_validator_should_run_on_create_update_and_sweep():
    r = WorkflowValidatorRule(statuses=["In Progress", "QA"], projects=["ABC"], enabled=True)
    r.jira = None

    assert r.should_run(ev_issue_created())
    assert r.should_run(ev_issue_updated())
    assert r.should_run(ev_sweep())


def test_workflow_validator_execute_dry_run_and_jql():
    r = WorkflowValidatorRule(
        statuses=["In Progress", "QA"],
        projects=["ABC"],
        require_assignee=True,
        require_fields=["Story Points"],
        enabled=True,
    )
    r.jira = None

    res = r.execute(ev_sweep())
    assert res["rule"] == "WorkflowValidatorRule"
    assert res["status"] == "dry_run"
    assert res["issue_keys"] == []
    assert res["violations"] == {}
    assert res["actions"] == {"comments": 0, "labels": 0}

    jql = norm_ws(res["jql"])
    assert "project in (ABC)" in jql
    assert "statusCategory != Done" in jql
    assert 'status in ("In Progress","QA")' in jql.replace(", ", "")


# ----------------------------
# Comment-builder micro-tests
# ----------------------------

def test_duplicate_comment_builder_formats_list_cleanly():
    r = DuplicateCheckRule(add_comment=True, comment_prefix="🔎 Dups:")
    # call private helper intentionally to validate string shape
    msg = r._build_comment([
        {"key": "ABC-1", "summary": "First"},
        {"key": "ABC-2", "summary": "Second issue"},
    ])
    # First line should be prefix + blank line, then bullet list
    assert msg.splitlines()[0] == "🔎 Dups:"
    assert "- ABC-1: First" in msg
    assert "- ABC-2: Second issue" in msg


def test_workflow_validator_comment_builder_handles_empty_and_populated():
    r = WorkflowValidatorRule(statuses=["In Progress"], add_comment=True)

    empty_msg = r._build_comment([])
    assert empty_msg.startswith("⚠️ Workflow validation:")

    populated_msg = r._build_comment(["Missing assignee", "Missing field: Story Points"])
    # Should include both violations in a single line after the base text
    assert "⚠️ Workflow validation: Missing assignee; Missing field: Story Points" == populated_msg