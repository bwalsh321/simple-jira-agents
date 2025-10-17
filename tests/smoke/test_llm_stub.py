"""
Smoke test for LLMEngine (offline)
Ensures it initializes and returns a structured dict without hitting Jira/LLM.
"""

from workflows.llm_engine import LLMEngine
from core.config import Config


def test_llm_engine_basic():
    cfg = Config()
    # Use an unknown agent to avoid real Jira/LLM calls
    llm = LLMEngine(agent="noop", config=cfg)
    out = llm.process(payload={})

    assert isinstance(out, dict)
    # Unknown agent should gracefully return a failure shape
    assert out.get("success") is False
    assert "unknown agent" in out.get("error", "")