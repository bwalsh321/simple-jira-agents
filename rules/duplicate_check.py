# rules/duplicate_check.py
from __future__ import annotations
from typing import Any, Dict, List, Optional
from time import sleep

from rules.base_rule import BaseRule

# Soft imports so local dev works without Jira creds
try:
    from core.config import Config
    from tools.jira_api import JiraAPI as _JiraAPI
    _HAS_JIRA = True
except Exception:
    _HAS_JIRA = False
    _JiraAPI = None  # type: ignore
    Config = None    # type: ignore


class DuplicateCheckRule(BaseRule):
    """
    Checks for likely duplicate issues by searching recent issues with similar text.
    Triggered on issue_created / issue_updated (or can be called in a sweep with issue context).
    """

    def __init__(
        self,
        lookback_days: int = 14,
        projects: Optional[List[str]] = None,
        enabled: bool = True,
        add_comment: bool = False,
        comment_prefix: str = "🔍 Possible duplicates found:",
        max_results: int = 10,
        write_delay_sec: float = 0.2,
    ):
        super().__init__(name="DuplicateCheckRule", enabled=enabled)
        self.lookback_days = max(1, lookback_days)
        self.projects = projects or []
        self.add_comment = bool(add_comment)
        self.comment_prefix = comment_prefix
        self.max_results = max(1, max_results)
        self.write_delay_sec = max(0.0, write_delay_sec)

        self.jira = None
        if _HAS_JIRA:
            try:
                cfg = Config()
                if cfg.jira_base_url and cfg.jira_api_token:
                    self.jira = _JiraAPI(cfg)
            except Exception:
                self.jira = None

    # ------------ rule contract ------------

    def should_run(self, data: Dict[str, Any]) -> bool:
        if not self.enabled:
            return False
        event = (data or {}).get("eventType", "").lower()
        return event in {"issue_created", "issue_updated"}

    def execute(self, data: Dict[str, Any]) -> Dict[str, Any]:
        if not self.enabled:
            res = {"rule": self.name, "status": "skipped", "reason": "disabled"}
            self.log_result(res)
            return res

        issue = (data or {}).get("issue") or {}
        key = issue.get("key")
        fields = issue.get("fields") or {}
        summary = (fields.get("summary") or "").strip()

        if not key or not summary:
            # Only meaningful on concrete issue events
            res = {"rule": self.name, "status": "skipped", "reason": "no_issue_context"}
            self.log_result(res)
            return res

        jql = self._build_jql(summary, key)

        # Dry-run
        if self.jira is None:
            res = {
                "rule": self.name,
                "status": "dry_run",
                "issue_key": key,
                "jql": jql,
                "duplicates": [],
                "actions": {"comments": 0},
                "note": "Jira not configured; no side effects performed.",
            }
            self.log_result(res)
            return res

        # Real mode
        try:
            resp = self.jira.search_issues(jql, max_results=self.max_results, fields=["summary"])  # type: ignore
            issues = resp.get("issues", []) if isinstance(resp, dict) else []
            dupes = [
                {"key": it.get("key"), "summary": (it.get("fields") or {}).get("summary", "")}
                for it in issues if it.get("key")
            ]

            actions = {"comments": 0}
            if self.add_comment and dupes:
                comment = self._build_comment(dupes)
                try:
                    self.jira.add_comment(key, comment)  # type: ignore
                    actions["comments"] = 1
                    if self.write_delay_sec:
                        sleep(self.write_delay_sec)
                except Exception:
                    pass

            res = {
                "rule": self.name,
                "status": "ok",
                "issue_key": key,
                "jql": jql,
                "duplicates": dupes,
                "actions": actions,
            }
            self.log_result(res)
            return res

        except Exception as e:
            res = {"rule": self.name, "status": "error", "issue_key": key, "jql": jql, "error": str(e)}
            self.log_result(res)
            return res

    # ------------ internals ------------

    def _project_clause(self) -> str:
        if not self.projects:
            return ""
        csv_vals = ",".join(p.strip() for p in self.projects if p and p.strip())
        return f"project in ({csv_vals}) AND "

    def _build_jql(self, summary: str, current_key: str) -> str:
        """
        Simple text match on the summary over recent issues, excluding the current one.
        You can swap to 'text ~ ""' if you want description matching too.
        """
        # Escape quotes in summary for JQL
        safe_summary = summary.replace('"', '\\"')
        base = (
            f"{self._project_clause()}"
            f'text ~ "{safe_summary}" '
            f"AND key != {current_key} "
            f"AND created >= -{self.lookback_days}d "
            f"ORDER BY created DESC"
        )
        return base

    def _build_comment(self, dupes: List[Dict[str, str]]) -> str:
        lines = [self.comment_prefix, ""]
        for d in dupes:
            lines.append(f"- {d['key']}: {d['summary']}")
        return "\n".join(lines)