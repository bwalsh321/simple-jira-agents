# rules/__init__.py
from .base_rule import BaseRule
from .missing_fields import MissingFieldsRule
from .stale_tickets import StaleTicketRule
from .workflow_validator import WorkflowValidatorRule
from .duplicate_check import DuplicateCheckRule

__all__ = [
    "BaseRule",
    "MissingFieldsRule",
    "StaleTicketRule",
    "WorkflowValidatorRule",
    "DuplicateCheckRule",
]

def default_hygiene_rules() -> list[BaseRule]:
    """
    Convenience factory: create your default hygiene ruleset.
    Tweak parameters here as your defaults evolve.
    """
    rules: list[BaseRule] = [
        StaleTicketRule(days=7, add_comment=False),
        MissingFieldsRule(
            required=["Assignee"],
            add_comment=False,
        ),
        WorkflowValidatorRule(
            statuses=["In Progress", "Ready for Dev"],
            require_assignee=True,
            add_comment=False,
        ),
        DuplicateCheckRule(lookback_days=14, add_comment=False),
    ]
    return rules