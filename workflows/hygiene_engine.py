from __future__ import annotations

"""
HygieneEngine
-------------
Zero-AI rule runner for Jira hygiene checks.

Goals
- Additive: lives alongside the existing FastAPI app (no breaking changes)
- Clear: register rule objects and run them in order
- Testable: deterministic inputs/outputs; no globals
- Extensible: add rules via flags or at runtime with `add_rule()`

Rules included:
  ✓ StaleTicketRule
  ✓ MissingFieldsRule
  ✓ WorkflowValidatorRule
  ✓ DuplicateCustomFieldsRule
"""

from typing import Any, Dict, List, Optional
from core.logging import logger
from core.config import Config

# direct imports so we can toggle per-rule easily
from rules.missing_fields import MissingFieldsRule
from rules.stale_tickets import StaleTicketRule
from rules.workflow_validator import WorkflowValidatorRule
from rules.base_rule import BaseRule
from rules.duplicate_custom_fields import DuplicateCustomFieldsRule


def _build_rules(
    *,
    projects: Optional[List[str]],
    enable_stale: bool,
    enable_missing_fields: bool,
    enable_workflow_validator: bool,
    enable_duplicate_check: bool,
    stale_add_comment: bool,
    missing_fields_add_comment: bool,
    workflow_add_comment: bool,
) -> List[BaseRule]:
    """Build the list of rule instances based on which ones are enabled."""
    rules: List[BaseRule] = []

    if enable_stale:
        rules.append(
            StaleTicketRule(
                days=7,
                projects=projects,
                add_comment=stale_add_comment,
            )
        )

    if enable_missing_fields:
        rules.append(
            MissingFieldsRule(
                required=["Assignee"],  # adjust default list as needed
                projects=projects,
                add_comment=missing_fields_add_comment,
            )
        )

    if enable_workflow_validator:
        rules.append(
            WorkflowValidatorRule(
                statuses=["In Progress", "Ready for Dev"],
                projects=projects,
                require_assignee=True,
                add_comment=workflow_add_comment,
            )
        )

    if enable_duplicate_check:
        rules.append(
            DuplicateCustomFieldsRule(
                enabled=True,
                require_same_type=True,
                ignore_names=[],
            )
        )

    return rules


class HygieneEngine:
    """
    Backward-compatible class wrapper so existing code in app/main.py works:
      engine = HygieneEngine(...); engine.process(payload)
    """

    def __init__(
        self,
        *,
        projects: Optional[List[str]] = None,
        enable_stale: bool = True,
        enable_missing_fields: bool = True,
        enable_workflow_validator: bool = True,
        enable_duplicate_check: bool = True,
        stale_add_comment: bool = False,
        missing_fields_add_comment: bool = False,
        workflow_add_comment: bool = False,
        config: Optional[Config] = None,
    ):
        self.config = config or Config()

        # Keep a copy for meta + JQL construction in rules
        self.projects: List[str] = list(projects or [])

        self.rules = _build_rules(
            projects=self.projects,
            enable_stale=enable_stale,
            enable_missing_fields=enable_missing_fields,
            enable_workflow_validator=enable_workflow_validator,
            enable_duplicate_check=enable_duplicate_check,
            stale_add_comment=stale_add_comment,
            missing_fields_add_comment=missing_fields_add_comment,
            workflow_add_comment=workflow_add_comment,
        )
        logger.info(f"HygieneEngine initialized with {len(self.rules)} rules.")

    def process(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Runs enabled rules that want to handle this event.
        Returns a structured dict:
        {
          "rules": { <rule_name>: <result_dict>, ... },
          "meta": { ... }
        }
        """
        event = (payload or {}).get("eventType") or "unknown"
        logger.info(f"HygieneEngine.process event={event}")

        # initialize structured response
        out: Dict[str, Any] = {
            "rules": {},
            "meta": {
                "projects": self.projects,
                "projects_csv": ", ".join(self.projects) if self.projects else "",
                "event_type": event,
            },
        }

        for rule in self.rules:
            try:
                if rule.should_run(payload):
                    result = rule.execute(payload)
                else:
                    result = {
                        "rule": rule.name,
                        "status": "skipped",
                        "reason": "should_run=false",
                    }
            except Exception as e:
                result = {"rule": rule.name, "status": "error", "error": str(e)}

            out["rules"][rule.name] = result

        return out