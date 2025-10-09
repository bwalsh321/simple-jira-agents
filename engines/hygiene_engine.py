# engines/hygiene_engine.py
"""
HygieneEngine
-------------
Zero-AI rule runner for Jira hygiene checks.

Goals
- Additive: lives alongside the existing FastAPI app (no breaking changes)
- Clear: register rule objects and run them in order
- Testable: deterministic inputs/outputs; no globals
- Extensible: add rules via flags or at runtime with `add_rule()`

Rule contract (see rules/base_rule.py):
  - should_run(webhook_data: dict) -> bool
  - execute(webhook_data: dict) -> dict

Rules included:
  ✓ StaleTicketRule
  ✓ MissingFieldsRule
  ✓ WorkflowValidatorRule
"""

from typing import Any, Dict, List, Optional

# ---- tolerant imports so you can run this file before all rules exist ----
from rules.stale_tickets import StaleTicketRule  # implemented

try:
    from rules.missing_fields import MissingFieldsRule  # implemented
except Exception:
    MissingFieldsRule = None  # type: ignore

try:
    from rules.workflow_validator import WorkflowValidatorRule  # implemented
except Exception:
    WorkflowValidatorRule = None  # type: ignore


class HygieneEngine:
    """
    Orchestrates hygiene rules.

    Usage:
        engine = HygieneEngine(
            projects=["TEST"],
            stale_days=7,
            enable_stale=True,
            enable_missing_fields=True,
            enable_workflow_validator=True,
            # Optional per-rule settings:
            missing_fields_required=["labels", "storyPoints"],
            missing_fields_statuses=["In Progress", "Ready for Dev"],
            workflow_statuses=["In Progress", "Ready for Dev"],
            workflow_require_assignee=True,
            workflow_require_fields=[],        # e.g., ["Story Points"]
        )
        result = engine.process({"eventType": "scheduled_sweep"})
    """

    def __init__(
        self,
        *,
        # Global-ish knobs
        projects: Optional[List[str]] = None,

        # Enable/disable individual rules
        enable_stale: bool = True,
        enable_missing_fields: bool = False,
        enable_workflow_validator: bool = False,

        # ---- StaleTicketRule settings ----
        stale_days: int = 7,
        stale_add_comment: bool = False,
        stale_comment_text: Optional[str] = None,
        stale_add_label: Optional[str] = None,
        stale_exclude_statuses: Optional[List[str]] = None,
        stale_exclude_labels: Optional[List[str]] = None,
        stale_max_results: int = 1000,
        stale_batch_size: int = 100,

        # ---- MissingFieldsRule settings ----
        missing_fields_required: Optional[List[str]] = None,
        missing_fields_statuses: Optional[List[str]] = None,
        missing_fields_add_comment: bool = False,
        missing_fields_comment_text: Optional[str] = None,
        missing_fields_add_label: Optional[str] = None,
        missing_fields_max_results: int = 1000,
        missing_fields_batch_size: int = 100,

        # ---- WorkflowValidatorRule settings ----
        workflow_statuses: Optional[List[str]] = None,
        workflow_require_assignee: bool = True,
        workflow_require_fields: Optional[List[str]] = None,
        workflow_add_comment: bool = False,
        workflow_comment_text: Optional[str] = None,
        workflow_add_label: Optional[str] = None,
        workflow_max_results: int = 1000,
        workflow_batch_size: int = 100,
    ) -> None:
        self.projects = projects or []

        # Registry of rule instances
        self.rules: List[Any] = []
        self._register_default_rules(
            # enables
            enable_stale=enable_stale,
            enable_missing_fields=enable_missing_fields,
            enable_workflow_validator=enable_workflow_validator,
            # stale args
            stale_days=stale_days,
            stale_add_comment=stale_add_comment,
            stale_comment_text=stale_comment_text,
            stale_add_label=stale_add_label,
            stale_exclude_statuses=stale_exclude_statuses,
            stale_exclude_labels=stale_exclude_labels,
            stale_max_results=stale_max_results,
            stale_batch_size=stale_batch_size,
            # missing fields args
            missing_fields_required=missing_fields_required,
            missing_fields_statuses=missing_fields_statuses,
            missing_fields_add_comment=missing_fields_add_comment,
            missing_fields_comment_text=missing_fields_comment_text,
            missing_fields_add_label=missing_fields_add_label,
            missing_fields_max_results=missing_fields_max_results,
            missing_fields_batch_size=missing_fields_batch_size,
            # workflow args
            workflow_statuses=workflow_statuses,
            workflow_require_assignee=workflow_require_assignee,
            workflow_require_fields=workflow_require_fields,
            workflow_add_comment=workflow_add_comment,
            workflow_comment_text=workflow_comment_text,
            workflow_add_label=workflow_add_label,
            workflow_max_results=workflow_max_results,
            workflow_batch_size=workflow_batch_size,
        )

    # ----------------- public api -----------------

    def add_rule(self, rule_obj: Any) -> None:
        """Append a rule instance that follows the BaseRule contract."""
        if rule_obj is not None:
            self.rules.append(rule_obj)

    def list_rules(self) -> List[str]:
        """All registered rules (enabled/disabled)."""
        names = []
        for r in self.rules:
            name = getattr(r, "name", r.__class__.__name__)
            enabled = getattr(r, "enabled", True)
            names.append(f"{name} ({'on' if enabled else 'off'})")
        return names

    def get_active_rules(self) -> List[str]:
        """Rule names that are currently enabled."""
        return [
            getattr(r, "name", r.__class__.__name__)
            for r in self.rules
            if getattr(r, "enabled", True)
        ]

    def process(self, webhook_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute each registered rule (if its should_run() returns True).
        Returns a stable JSON-like dict for easy API/CLI use.
        """
        results: List[Dict[str, Any]] = []

        for rule in self.rules:
            try:
                should = True
                if hasattr(rule, "should_run"):
                    should = bool(rule.should_run(webhook_data))
                if not should:
                    continue

                if hasattr(rule, "execute"):
                    res = rule.execute(webhook_data)
                else:
                    res = {
                        "rule": getattr(rule, "name", rule.__class__.__name__),
                        "status": "error",
                        "error": "Rule missing execute()",
                    }
                results.append(res)
            except Exception as e:
                results.append(
                    {
                        "rule": getattr(rule, "name", rule.__class__.__name__),
                        "status": "error",
                        "error": str(e),
                    }
                )

        return {
            "engine": "HygieneEngine",
            "processed": len(results),
            "results": results,
        }

    # ----------------- internal wiring -----------------

    def _register_default_rules(
        self,
        *,
        enable_stale: bool,
        enable_missing_fields: bool,
        enable_workflow_validator: bool,
        # stale args
        stale_days: int,
        stale_add_comment: bool,
        stale_comment_text: Optional[str],
        stale_add_label: Optional[str],
        stale_exclude_statuses: Optional[List[str]],
        stale_exclude_labels: Optional[List[str]],
        stale_max_results: int,
        stale_batch_size: int,
        # missing fields args
        missing_fields_required: Optional[List[str]],
        missing_fields_statuses: Optional[List[str]],
        missing_fields_add_comment: bool,
        missing_fields_comment_text: Optional[str],
        missing_fields_add_label: Optional[str],
        missing_fields_max_results: int,
        missing_fields_batch_size: int,
        # workflow args
        workflow_statuses: Optional[List[str]],
        workflow_require_assignee: bool,
        workflow_require_fields: Optional[List[str]],
        workflow_add_comment: bool,
        workflow_comment_text: Optional[str],
        workflow_add_label: Optional[str],
        workflow_max_results: int,
        workflow_batch_size: int,
    ) -> None:
        """Create and register the default rules based on flags."""

        # --- Stale tickets ---
        if enable_stale:
            self.add_rule(
                StaleTicketRule(
                    days=stale_days,
                    projects=self.projects,
                    enabled=True,
                    add_comment=stale_add_comment,
                    comment_text=stale_comment_text,
                    add_label=stale_add_label,
                    exclude_statuses=stale_exclude_statuses,
                    exclude_labels=stale_exclude_labels,
                    max_results=stale_max_results,
                    batch_size=stale_batch_size,
                )
            )

        # --- Missing fields ---
        if enable_missing_fields and MissingFieldsRule is not None:
            required = missing_fields_required or ["labels", "storyPoints"]
            self.add_rule(
                MissingFieldsRule(  # type: ignore
                    required=required,
                    projects=self.projects,
                    statuses=missing_fields_statuses,  # e.g., ["In Progress","Ready for Dev"]
                    enabled=True,
                    add_comment=missing_fields_add_comment,
                    comment_text=missing_fields_comment_text,
                    add_label=missing_fields_add_label,
                    max_results=missing_fields_max_results,
                    batch_size=missing_fields_batch_size,
                )
            )

        # --- Workflow validator ---
        if enable_workflow_validator and WorkflowValidatorRule is not None:
            statuses = workflow_statuses or ["In Progress", "Ready for Dev"]
            self.add_rule(
                WorkflowValidatorRule(  # type: ignore
                    statuses=statuses,
                    projects=self.projects,
                    enabled=True,
                    require_assignee=workflow_require_assignee,
                    require_fields=(workflow_require_fields or []),
                    add_comment=workflow_add_comment,
                    comment_text=workflow_comment_text,
                    add_label=workflow_add_label,
                    max_results=workflow_max_results,
                    batch_size=workflow_batch_size,
                )
            )

