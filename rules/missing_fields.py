# rules/missing_fields.py
"""
MissingFieldsRule
-----------------
Flags issues that are in specific statuses (or any open status) but are missing one
or more required fields.

Features:
- Dry-run if Jira isn't configured (no crashes during local dev)
- Project scoping
- Optional status scoping (e.g., only run for "In Progress", "Ready for Dev")
- Pagination (batches of 100)
- Optional side effects: add a comment and/or a label
- Clear, stable result payload

Notes:
- JQL uses field *names* (e.g., Story Points, Labels). Jira accepts custom field
  names in JQL when they’re unambiguous. If a name is ambiguous in your site,
  consider switching to IDs later.
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


class MissingFieldsRule(BaseRule):
    def __init__(
        self,
        required: List[str],
        projects: Optional[List[str]] = None,
        statuses: Optional[List[str]] = None,
        enabled: bool = True,
        add_comment: bool = False,
        comment_text: Optional[str] = None,
        add_label: Optional[str] = None,
        exclude_statuses: Optional[List[str]] = None,
        max_results: int = 1000,
        batch_size: int = 100,
        write_delay_sec: float = 0.2,
    ):
        super().__init__(name="MissingFieldsRule", enabled=enabled)
        if not required:
            raise ValueError("MissingFieldsRule requires a non-empty `required` list.")

        self.required = [s.strip() for s in required if s and s.strip()]
        self.projects = projects or []
        self.statuses = [s.strip() for s in statuses or []]
        self.exclude_statuses = set((exclude_statuses or []))

        self.add_comment = bool(add_comment)
        self.comment_text = comment_text or (
            f"⚠️ This issue is missing required fields: {', '.join(self.required)}"
        )
        self.add_label = add_label  # e.g., "missing-required-fields"

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
        """Run on create/update events or scheduled sweeps."""
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

        # Dry run: no Jira client initialised
        if self.jira is None:
            res = {
                "rule": self.name,
                "status": "dry_run",
                "jql": jql,
                "issues_flagged": 0,
                "issue_keys": [],
                "checked_fields": self.required,
                "actions": {"comments": 0, "labels": 0},
                "note": "Jira not configured; no side effects performed.",
            }
            self.log_result(res)
            return res

        # Real mode
        try:
            items = self._search_all(jql)
            keys = [i["key"] for i in items]
            actions = self._maybe_write_actions(keys)

            res = {
                "rule": self.name,
                "status": "ok",
                "jql": jql,
                "issues_flagged": len(keys),
                "issue_keys": keys,
                "checked_fields": self.required,
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
        clause = ""
        if self.statuses:
            statuses = ",".join(f'"{s}"' for s in self.statuses)
            clause += f" AND status in ({statuses})"
        if self.exclude_statuses:
            ex = ",".join(f'"{s}"' for s in sorted(self.exclude_statuses))
            clause += f" AND status not in ({ex})"
        return clause

    def _missing_fields_clause(self) -> str:
        # Build (FieldA is EMPTY OR FieldB is EMPTY ...)
        parts = [f'"{name}" is EMPTY' if " " in name else f"{name} is EMPTY" for name in self.required]
        return " AND (" + " OR ".join(parts) + ")"

    def _build_jql(self) -> str:
        # Default to excluding Done category; if you want it configurable, add a flag later
        base = (
            f"{self._project_clause()}"
            f"statusCategory != Done"
            f"{self._status_clause()}"
            f"{self._missing_fields_clause()}"
        )
        return base

    def _search_all(self, jql: str) -> List[Dict[str, Any]]:
        """Paginate through Jira search results using JiraAPI.search_issues."""
        results: List[Dict[str, Any]] = []
        start_at = 0
        remaining = self.max_results

        while remaining > 0:
            limit = min(self.batch_size, remaining)
            resp = self.jira.search_issues(  # type: ignore
                jql, start_at=start_at, max_results=limit, fields=["key"]
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
                if key:
                    results.append({"key": key})

            got = len(issues)
            start_at += got
            remaining -= got

            total = resp.get("total")
            if isinstance(total, int) and start_at >= total:
                break

        return results

    def _maybe_write_actions(self, keys: List[str]) -> Dict[str, int]:
        """Optionally add a comment and/or label; return counts written."""
        written_comments = 0
        written_labels = 0
        if self.jira is None or not keys:
            return {"comments": 0, "labels": 0}

        for k in keys:
            if self.add_comment:
                try:
                    self.jira.add_comment(k, self.comment_text)  # type: ignore
                    written_comments += 1
                    if self.write_delay_sec:
                        sleep(self.write_delay_sec)
                except Exception:
                    pass

            if self.add_label:
                try:
                    # Implement add_label in your JiraAPI if you want this live.
                    self.jira.add_label(k, self.add_label)  # type: ignore
                    written_labels += 1
                    if self.write_delay_sec:
                        sleep(self.write_delay_sec)
                except Exception:
                    pass

        return {"comments": written_comments, "labels": written_labels}