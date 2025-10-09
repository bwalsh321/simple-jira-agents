# rules/workflow_validator.py
"""
WorkflowValidatorRule
---------------------
Enforces workflow invariants, e.g.:
- Issues in certain statuses must have an assignee
- Optionally: required fields for those statuses

Features:
- Dry-run if Jira isn't configured (safe local testing)
- Project scoping
- Status scoping (e.g., "In Progress", "Ready for Dev")
- Pagination (batches of 100)
- Optional side effects: add a comment and/or a label
- Clear, structured results (per issue keys flagged)

Notes:
- Uses JQL + fields selector to minimize payload.
- For additional invariants later, extend `_violations_for_issue()`.
"""

from typing import Any, Dict, List, Optional
from time import sleep
from rules.base_rule import BaseRule

# Soft imports to keep dev smooth without creds
try:
    from config import Config
    try:
        from api import JiraAPI as _JiraAPI
    except Exception:
        from api import JiraAPI as _JiraAPI  # fallback
    _HAS_JIRA = True
except Exception:
    _HAS_JIRA = False
    _JiraAPI = None
    Config = None  # type: ignore


class WorkflowValidatorRule(BaseRule):
    def __init__(
        self,
        statuses: List[str],                     # statuses where invariants apply
        projects: Optional[List[str]] = None,    # optional project filter
        enabled: bool = True,

        # Invariants (enable/disable as needed)
        require_assignee: bool = True,
        require_fields: Optional[List[str]] = None,  # e.g., ["Story Points"]

        # Side effects
        add_comment: bool = False,
        comment_text: Optional[str] = None,
        add_label: Optional[str] = None,

        # Paging + timing
        max_results: int = 1000,
        batch_size: int = 100,
        write_delay_sec: float = 0.2,
    ):
        super().__init__(name="WorkflowValidatorRule", enabled=enabled)

        if not statuses:
            raise ValueError("WorkflowValidatorRule requires a non-empty `statuses` list.")

        self.projects = projects or []
        self.statuses = [s.strip() for s in statuses if s and s.strip()]

        self.require_assignee = bool(require_assignee)
        self.require_fields = [f.strip() for f in (require_fields or []) if f and f.strip()]

        self.add_comment = bool(add_comment)
        default_comment = "⚠️ Workflow check: please assign this issue and complete required fields."
        self.comment_text = comment_text or default_comment
        self.add_label = add_label  # e.g., "workflow-violation"

        self.max_results = max(1, max_results)
        self.batch_size = max(1, min(batch_size, 100))
        self.write_delay_sec = max(0.0, write_delay_sec)

        # Initialize Jira client (real mode) if possible
        self.jira = None
        if _HAS_JIRA:
            try:
                self.cfg = Config()
                if self.cfg.jira_base_url and self.cfg.jira_api_token:
                    self.jira = _JiraAPI(self.cfg)
            except Exception:
                self.jira = None  # stay in dry-run

    # ----------------- rule contract -----------------

    def should_run(self, data: Dict[str, Any]) -> bool:
        if not self.enabled:
            return False
        event = (data or {}).get("eventType", "").lower()
        return event in {"issue_created", "issue_updated", "scheduled_sweep"}

    def execute(self, data: Dict[str, Any]) -> Dict[str, Any]:
        if not self.enabled:
            res = {"rule": self.name, "status": "skipped", "reason": "disabled"}
            self.log_result(res)
            return res

        jql = self._build_jql()

        # Dry run
        if self.jira is None:
            res = {
                "rule": self.name,
                "status": "dry_run",
                "jql": jql,
                "issues_flagged": 0,
                "issue_keys": [],
                "violations": {},          # key → list of strings describing violations
                "actions": {"comments": 0, "labels": 0},
                "note": "Jira not configured; no side effects performed.",
            }
            self.log_result(res)
            return res

        # Real mode
        try:
            items = self._search_all(jql)
            # Build per-issue violation report
            per_issue_violations: Dict[str, List[str]] = {}
            for it in items:
                key = it["key"]
                fields = it.get("fields", {})
                vios = self._violations_for_issue(fields)
                if vios:
                    per_issue_violations[key] = vios

            keys = list(per_issue_violations.keys())
            actions = self._maybe_write_actions(keys, per_issue_violations)

            res = {
                "rule": self.name,
                "status": "ok",
                "jql": jql,
                "issues_flagged": len(keys),
                "issue_keys": keys,
                "violations": per_issue_violations,
                "actions": actions,
            }
            self.log_result(res)
            return res

        except Exception as e:
            res = {"rule": self.name, "status": "error", "jql": jql, "error": str(e)}
            self.log_result(res)
            return res

    # ----------------- internals -----------------

    def _project_clause(self) -> str:
        if not self.projects:
            return ""
        csv_vals = ",".join(p.strip() for p in self.projects if p and p.strip())
        return f"project in ({csv_vals}) AND "

    def _status_clause(self) -> str:
        statuses = ",".join(f'"{s}"' for s in self.statuses)
        return f" AND status in ({statuses})"

    def _build_jql(self) -> str:
        # Only the necessary fields to evaluate invariants
        # Assignee is stored in "assignee"; custom names may need quotes
        base = (
            f"{self._project_clause()}"
            f"statusCategory != Done"
            f"{self._status_clause()}"
        )
        return base

    def _search_all(self, jql: str) -> List[Dict[str, Any]]:
        """Paginate using JiraAPI.search_issues; fetch required fields."""
        results: List[Dict[str, Any]] = []
        start_at = 0
        remaining = self.max_results

        # Always include 'key' and 'assignee'; include required fields if specified.
        fields = ["key", "assignee"]
        # For required_fields, if they contain spaces, Jira accepts quoted names in JQL,
        # but field retrieval usually needs IDs; many sites still return by name via 'fields' selector.
        # Keep names for now; you can switch to IDs later if needed.
        fields.extend(self.require_fields)

        while remaining > 0:
            limit = min(self.batch_size, remaining)
            resp = self.jira.search_issues(  # type: ignore
                jql, start_at=start_at, max_results=limit, fields=fields
            )

            if isinstance(resp, dict) and "error" in resp:
                raise RuntimeError(resp["error"])
            if not isinstance(resp, dict) or "issues" not in resp:
                raise RuntimeError("Unexpected JiraAPI.search_issues() response shape")

            issues = resp.get("issues", []) or []
            if not issues:
                break

            for item in issues:
                key = item.get("key")
                f = item.get("fields", {}) or {}
                if key:
                    results.append({"key": key, "fields": f})

            got = len(issues)
            start_at += got
            remaining -= got

            total = resp.get("total")
            if isinstance(total, int) and start_at >= total:
                break

        return results

    def _violations_for_issue(self, fields: Dict[str, Any]) -> List[str]:
        """Return a list of violation messages for a single issue."""
        violations: List[str] = []

        # Assignee check
        if self.require_assignee:
            assignee = fields.get("assignee")
            # On Cloud, assignee is an object or None
            if not assignee:
                violations.append("Missing assignee")

        # Required fields check (by *name*; may need IDs later)
        for name in self.require_fields:
            # Jira field dict keys are field IDs; for common names like "labels", "Story Points", Cloud maps to:
            # - labels: fields['labels'] (list)
            # - Story Points: often 'customfield_xxxxx'; some sites alias by name in search results
            val = fields.get(name)
            if val in (None, "", [], {}):
                violations.append(f"Missing field: {name}")

        return violations

    def _maybe_write_actions(self, keys: List[str], per_issue: Dict[str, List[str]]) -> Dict[str, int]:
        """Optionally add comment and/or label; return counts written."""
        written_comments = 0
        written_labels = 0
        if self.jira is None or not keys:
            return {"comments": 0, "labels": 0}

        for k in keys:
            if self.add_comment:
                try:
                    msg = self._build_comment(per_issue.get(k, []))
                    self.jira.add_comment(k, msg)  # type: ignore
                    written_comments += 1
                    if self.write_delay_sec:
                        sleep(self.write_delay_sec)
                except Exception:
                    pass

            if self.add_label:
                try:
                    # Implement add_label in JiraAPI if you want this live.
                    self.jira.add_label(k, self.add_label)  # type: ignore
                    written_labels += 1
                    if self.write_delay_sec:
                        sleep(self.write_delay_sec)
                except Exception:
                    pass

        return {"comments": written_comments, "labels": written_labels}

    def _build_comment(self, violations: List[str]) -> str:
        base = "⚠️ Workflow validation:"
        if not violations:
            return base
        return base + " " + "; ".join(violations)