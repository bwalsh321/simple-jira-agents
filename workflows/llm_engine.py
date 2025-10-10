# workflows/llm_engine.py
from __future__ import annotations
from typing import Any, Dict, Optional

from core.config import Config
from core.logging import logger

# reuse your existing agent flows so nothing else needs to change
from llm.agents.l1_triage_bot import process_ticket as _process_l1
from llm.agents.admin_validator import process_admin_request as _process_admin


class LLMEngine:
    """
    Thin coordinator for LLM-powered flows.
    You can run one of your existing agent paths by name without touching routes.
    """

    def __init__(self, *, agent: str = "l1_triage", config: Optional[Config] = None):
        self.agent = agent
        self.config = config or Config()
        logger.info(f"LLMEngine initialized agent={self.agent}")

    def process(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Dispatch to the chosen agent using the existing functions.
        Expecting payloads that contain issue context similar to your webhooks.
        """
        issue = (payload or {}).get("issue") or {}
        key = issue.get("key", "UNKNOWN")
        logger.info(f"LLMEngine.process agent={self.agent} key={key}")

        if self.agent == "l1_triage":
            return _process_l1(key, issue, self.config)
        elif self.agent == "admin_validator":
            return _process_admin(key, issue, self.config)
        else:
            return {"success": False, "error": f"unknown agent '{self.agent}'"}


# Convenience function
def run_llm(payload: Dict[str, Any], *, agent: str = "l1_triage", config: Optional[Config] = None) -> Dict[str, Any]:
    return LLMEngine(agent=agent, config=config).process(payload)