"""
DuplicateCustomFieldsRule
-------------------------
Flags duplicate *custom field definitions* in Jira (same or very similar names).

Uses your existing JiraAPI.get_all_custom_fields() helper.
No issue-level JQL; purely metadata hygiene.

Outputs:
- duplicates: list of grouped duplicates with field ids/names/types
- count: number of duplicate groups
- note: short admin action note
- duplicates_html: pre-rendered HTML table for emails
- duplicates_markdown: pre-rendered Markdown table for comments
"""

from typing import Any, Dict, List, Optional, Tuple
from rules.base_rule import BaseRule
from core.logging import logger

# Soft import JiraAPI and Config
try:
    from core.config import Config
    from tools.jira_api import JiraAPI as _JiraAPI
    _HAS_JIRA = True
except Exception:
    _HAS_JIRA = False
    _JiraAPI = None
    Config = None  # type: ignore


def _norm(s: str) -> str:
    """Normalize field names for comparison."""
    return " ".join((s or "").strip().lower().split())


class DuplicateCustomFieldsRule(BaseRule):
    """Detects duplicate custom field definitions (same normalized name)."""

    def __init__(
        self,
        enabled: bool = True,
        case_insensitive: bool = True,
        require_same_type: bool = True,
        ignore_names: Optional[List[str]] = None,
    ):
        super().__init__(name="DuplicateCustomFieldsRule", enabled=enabled)
        self.case_insensitive = case_insensitive
        self.require_same_type = require_same_type
        self.ignore_names = set((ignore_names or []))

        self.jira = None
        if _HAS_JIRA:
            try:
                cfg = Config()
                if cfg.jira_base_url and cfg.jira_api_token:
                    self.jira = _JiraAPI(cfg)
            except Exception as e:
                logger.warning(f"DuplicateCustomFieldsRule init failed: {e}")
                self.jira = None

    # ----------------- rule contract -----------------

    def should_run(self, data: Dict[str, Any]) -> bool:
        if not self.enabled:
            return False
        event = (data or {}).get("eventType", "").lower()
        return event in {"scheduled_sweep", "manual_report"}

    def execute(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Run duplicate field detection."""
        if not self.enabled:
            res = {"rule": self.name, "status": "skipped", "reason": "disabled"}
            self.log_result(res)
            return res

        # dry run if no Jira connection
        if self.jira is None:
            res = {
                "rule": self.name,
                "status": "dry_run",
                "duplicates": [],
                "count": 0,
                "note": "Jira not configured; no metadata fetched.",
                "duplicates_html": "<p>No duplicate custom field names detected.</p>",
                "duplicates_markdown": "_No duplicate custom field names detected._",
            }
            self.log_result(res)
            return res

        try:
            fields = self._fetch_fields()
            dups = self._find_duplicates(fields)

            res = {
                "rule": self.name,
                "status": "ok",
                "duplicates": dups,
                "count": len(dups),
                "note": (
                    "Duplicate custom field names found. Consider consolidating redundant fields for cleaner admin."
                    if dups else "No duplicate custom field names detected."
                ),
                "duplicates_text": self._render_duplicates_text(dups),
            }
            self.log_result(res)
            return res
        except Exception as e:
            res = {"rule": self.name, "status": "error", "error": str(e)}
            self.log_result(res)
            return res

    # ---------------- internals ----------------

    def _fetch_fields(self) -> List[Dict[str, Any]]:
        """Use JiraAPI.get_all_custom_fields() (already implemented)."""
        if not hasattr(self.jira, "get_all_custom_fields"):
            raise RuntimeError("JiraAPI missing get_all_custom_fields()")

        resp = self.jira.get_all_custom_fields()  # type: ignore
        if isinstance(resp, dict):
            if resp.get("success") and "fields" in resp:
                return resp["fields"]
            if "error" in resp:
                raise RuntimeError(resp["error"])
        raise RuntimeError("Unexpected response from get_all_custom_fields()")

    def _find_duplicates(self, fields: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Return groups like:
        {
          "normalized_name": "team",
          "by_type": "com.atlassian.jira.plugin.system.customfieldtypes:select",
          "fields": [
             {"id":"customfield_12345","name":"Team","type":"..."},
             {"id":"customfield_67890","name":"team","type":"..."}
          ],
          "count": 2
        }
        """
        buckets: Dict[Tuple[str, Optional[str]], List[Dict[str, Any]]] = {}

        for f in fields:
            name = str(f.get("name", "")).strip()
            if not name:
                continue
            if name in self.ignore_names:
                continue

            norm = _norm(name) if self.case_insensitive else name
            ftype = (
                f.get("schema", {}).get("custom")
                or f.get("type")
                or "unknown"
            )
            key = (norm, ftype if self.require_same_type else None)
            buckets.setdefault(key, []).append({
                "id": f.get("id"),
                "name": name,
                "type": ftype,
            })

        out: List[Dict[str, Any]] = []
        for (norm, by_type), group in buckets.items():
            if len(group) > 1:
                out.append({
                    "normalized_name": norm,
                    "by_type": by_type,
                    "fields": group,
                    "count": len(group),
                    "suggestion": "Merge or remove redundant fields with same name/type.",
                })

        out.sort(key=lambda g: g["count"], reverse=True)
        return out

    def _render_duplicates_html(self, groups: List[Dict[str, Any]], *, max_rows: int = 25) -> str:
        if not groups:
            return "<p>No duplicate custom field names detected.</p>"
        rows: List[str] = []
        for g in groups[:max_rows]:
            field_ids = ", ".join(f.get("id", "") for f in g.get("fields", []))
            rows.append(
                "<tr>"
                f"<td>{g.get('normalized_name','')}</td>"
                f"<td>{g.get('by_type','')}</td>"
                f"<td>{g.get('count',0)}</td>"
                f"<td>{field_ids}</td>"
                "</tr>"
            )
        return (
            '<table border="1" cellspacing="0" cellpadding="6" style="border-collapse:collapse; font-size:13px;">'
            "<thead><tr style='background:#f3f4f6;'>"
            "<th align='left'>Duplicate Field Name</th>"
            "<th align='left'>Type</th>"
            "<th align='left'>Count</th>"
            "<th align='left'>Field IDs</th>"
            "</tr></thead><tbody>"
            + "".join(rows) +
            "</tbody></table>"
        )

    def _render_duplicates_markdown(self, groups: List[Dict[str, Any]], *, max_rows: int = 25) -> str:
        if not groups:
            return "_No duplicate custom field names detected._"
        lines = ["| Field name | Type | Count | Field IDs |", "|---|---:|---:|---|"]
        for g in groups[:max_rows]:
            field_ids = ", ".join(f.get("id", "") for f in g.get("fields", []))
            lines.append(
                f"| {g.get('normalized_name','')} | {g.get('by_type','')} | {g.get('count',0)} | {field_ids} |"
            )
        return "\n".join(lines)
    
    def _render_duplicates_text(self, groups: List[Dict[str, Any]], *, max_rows: int = 25) -> str:
        """
        Pretty, email-safe text rendering (no HTML, no loops in template).
        Shows duplicate group name/type/count and the actual field names.
        """
        if not groups:
            return "No duplicate custom field names detected."

        lines: List[str] = []
        header = "Duplicate field name  |  Type  |  Count  |  Fields"
        underline = "-" * len(header)
        lines.append(header)
        lines.append(underline)

        for g in groups[:max_rows]:
            # Build a comma-separated list of field *names* (and id suffix if you want)
            names_list = []
            for f in g.get("fields", []):
                fname = f.get("name", "")
                fid = f.get("id", "")
                # choose ONE of the next two lines:
                names_list.append(fname)                 # names only
                # names_list.append(f"{fname} ({fid})")  # names with id

            names_joined = ", ".join(names_list)
            lines.append(
                f"• {g.get('normalized_name','')}  |  {g.get('by_type','')}  |  {g.get('count',0)}  |  {names_joined}"
            )

        return "\n".join(lines)