"""
BaseRule - shared parent class for all hygiene rules.
Each rule defines:
  - should_run(webhook_data): bool
  - execute(webhook_data): dict
"""

from abc import ABC, abstractmethod
from typing import Any, Dict


class BaseRule(ABC):
    """Abstract base class that all hygiene rules inherit from."""

    def __init__(self, name: str, enabled: bool = True):
        self.name = name
        self.enabled = enabled

    @abstractmethod
    def should_run(self, webhook_data: Dict[str, Any]) -> bool:
        """Return True if the rule should run for this webhook or scheduled event."""
        raise NotImplementedError

    @abstractmethod
    def execute(self, webhook_data: Dict[str, Any]) -> Dict[str, Any]:
        """Run the rule logic. Must return a dictionary of results."""
        raise NotImplementedError

    def log_result(self, result: Dict[str, Any]) -> None:
        """Basic logging helper for consistent rule output."""
        print(f"[{self.name}] → {result.get('status', 'completed')} | details: {result}")

    def __repr__(self) -> str:
        return f"<Rule name={self.name} enabled={self.enabled}>"