# rules/stale_tickets.py
"""
StaleTicketRule - flags issues not updated in N days (not Done).
Features:
- Dry-run without Jira config
- Project scoping
- Pagination (batches of 100)
- Optional side effects: add comment and/or label
- Exclusions for statuses/labels
- Config defaults with param overrides
"""

from typing import Any, Dict, List, Optional
from time import sleep
from rules.base_rule import BaseRule

# Soft imports to keep dev smooth without creds
try:
    from core.config import Config
    try:
        # Support either jira_api.py or api.py naming
        from tools.jira_api import JiraAPI as _JiraAPI
    except Exception:
        from tools.jira_api import JiraAPI as _JiraAPI  # fallback
    _HAS_JIRA = True
except Exception:
    _HAS_JIRA = False
    _JiraAPI = None
    Config = None  # type: ignore


class StaleTicketRule(BaseRule):
    def __init__(
        self,
        days: Optional[int] = None,
        projects: Optional[List[str]] = None,
        enabled: bool = True,
        add_comment: bool = False,
        comment_text: Optional[str] = None,
        add_label: Optional[str] = None,
        exclude_statuses: Optional[List[str]] = None,
        exclude_labels: Optional[List[str]] = None,
        max_results: int = 1000,
        batch_size: int = 100,
        write_delay_sec: float = 0.2,
        max_days: int = 365,
    ):
        super().__init__(name="StaleTicketRule", enabled=enabled)

        # Defaults from Config when available, else fallbacks
        cfg_days = 7
        cfg_projects: List[str] = []
        if _HAS_JIRA:
            try:
                _cfg = Config()
                # if you later add YAML keys for rules, read them here
                # e.g., cfg_days = _cfg.hygiene.stale_tickets.days
            except Exception:
                pass

        self.days = int(days or cfg_days)
        self.projects = projects or cfg_projects
        self.add_comment = bool(add_comment)
        self.comment_text = comment_text or f"⏰ No updates in {self.days} days. Please update or close."
        self.add_label = add_label  # e.g., "stale"
        self.exclude_statuses = set((exclude_statuses or []))
        self.exclude_labels = set((exclude_labels or []))
        self.max_results = max(1, max_results)
        self.batch_size = max(1, min(batch_size, 100))
        self.write_delay_sec = max(0.0, write_delay_sec)
        self.max_days = max(1, max_days)

        # Initialize Jira client (real mode) if possible
        self.jira = None
        if _HAS_JIRA:
            try:
                self.cfg = Config()
                if self.cfg.jira_base_url and self.cfg.jira_api_token:
                    self.jira = _JiraAPI(self.cfg)
            except Exception:
                self.jira = None  # stay in dry-run

    def should_run(self, data: Dict[str, Any]) -> bool:
        """Run on updates or scheduled sweeps."""
        if not self.enabled:
            return False
        event = (data or {}).get("eventType", "").lower()
        return event in {"issue_updated", "scheduled_sweep"}

    # -------- internals --------

    def _project_clause(self) -> str:
        if not self.projects:
            return ""
        csv_vals = ",".join(p.strip() for p in self.projects if p and p.strip())
        return f"project in ({csv_vals}) AND "

    def _exclude_status_clause(self) -> str:
        if not self.exclude_statuses:
            return ""
        statuses = ",".join(f'"{s}"' for s in sorted(self.exclude_statuses))
        return f" AND status not in ({statuses})"

    def _exclude_labels_clause(self) -> str:
        if not self.exclude_labels:
            return ""
        labels = ",".join(f'"{l}"' for l in sorted(self.exclude_labels))
        return f" AND labels not in ({labels})"

    def _build_jql(self) -> str:
        """
        Build JQL for test or prod:
        - When self.days <= 0 → match all open issues
        - Otherwise: use 'updated < -Nd' logic
        """
        if self.days <= 0:
            base = f"{self._project_clause()}statusCategory != Done"
        else:
            days = min(self.days, self.max_days)
            base = f"{self._project_clause()}updated < -{days}d AND statusCategory != Done"

        base += self._exclude_status_clause()
        base += self._exclude_labels_clause()
        return base

    def _search_all(self, jql: str) -> list[dict]:
        """Paginate through Jira search results using JiraAPI.search_issues."""
        results: list[dict] = []
        start_at = 0
        remaining = self.max_results

        while remaining > 0:
            limit = min(self.batch_size, remaining)

            # Ask Jira only for "key" to keep payloads small
            resp = self.jira.search_issues(jql, start_at=start_at, max_results=limit, fields=["key"])  # type: ignore

            if not isinstance(resp, dict) or "issues" not in resp:
                break  # error or unexpected shape

            issues = resp.get("issues", []) or []
            if not issues:
                break

            # Normalize to {"key": "..."}
            for item in issues:
                # Cloud returns dicts with "key"
                key = item.get("key")
                if key:
                    results.append({"key": key})

            got = len(issues)
            start_at += got
            remaining -= got

            # If Jira says total is smaller than start_at, we're done
            total = resp.get("total")
            if isinstance(total, int) and start_at >= total:
                break

        return results

    def _maybe_write_actions(self, keys: List[str]) -> Dict[str, int]:
        """Optionally add a comment and/or label; return counts written."""
        written_comments = 0
        written_labels = 0
        if not keys:
            return {"comments": 0, "labels": 0}

        for k in keys:
            if self.add_comment:
                try:
                    self.jira.add_comment(k, self.comment_text)  # type: ignore
                    written_comments += 1
                    if self.write_delay_sec:
                        sleep(self.write_delay_sec)
                except Exception:
                    pass  # keep going; report totals later

            if self.add_label:
                try:
                    # You can implement a helper like jira.add_label(k, self.add_label)
                    # For now, many clients use edit issue with labels union
                    self.jira.add_label(k, self.add_label)  # type: ignore
                    written_labels += 1
                    if self.write_delay_sec:
                        sleep(self.write_delay_sec)
                except Exception:
                    pass

        return {"comments": written_comments, "labels": written_labels}

    # -------- public API required by BaseRule --------

    def execute(self, data: Dict[str, Any]) -> Dict[str, Any]:
        if not self.enabled:
            result = {"rule": self.name, "status": "skipped", "reason": "disabled"}
            self.log_result(result)
            return result

        jql = self._build_jql()

        # Dry run: no Jira client initialised
        if self.jira is None:
            result = {
                "rule": self.name,
                "status": "dry_run",
                "jql": jql,
                "issues_flagged": 0,
                "issue_keys": [],
                "actions": {"comments": 0, "labels": 0},
                "note": "Jira not configured; no side effects performed.",
            }
            self.log_result(result)
            return result

        # Real mode
        try:
            items = self._search_all(jql)
            keys = [i["key"] for i in items]
            actions = self._maybe_write_actions(keys)

            result = {
                "rule": self.name,
                "status": "ok",
                "jql": jql,
                "issues_flagged": len(keys),
                "issue_keys": keys,
                "actions": actions,
            }
            self.log_result(result)
            return result
        except Exception as e:
            result = {"rule": self.name, "status": "error", "jql": jql, "error": str(e)}
            self.log_result(result)
            return result