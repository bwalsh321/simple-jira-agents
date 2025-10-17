"""
Combined test for HygieneEngine
- Quick smoke check (does it run?)
- Integration check (rules execute correctly)
Run with:
    pytest -v tests/test_hygiene.py
    or python -m tests.test_hygiene
"""

from workflows.hygiene_engine import HygieneEngine
from core.config import Config


def test_hygiene_engine_smoke():
    """Simple smoke test to confirm the HygieneEngine runs end-to-end."""
    engine = HygieneEngine(
        projects=["TEST"],
        enable_stale=True,
        enable_missing_fields=True,
        enable_workflow_validator=True,
        enable_duplicate_check=False,
    )
    payload = {"eventType": "scheduled_sweep"}
    result = engine.process(payload)

    assert isinstance(result, dict)
    assert "rules" in result
    assert all(isinstance(v, dict) for v in result["rules"].values())


def test_hygiene_engine_integration():
    """Integration-style test to ensure all rules execute cleanly."""
    config = Config()
    engine = HygieneEngine(
        projects=["SBX"],
        enable_stale=True,
        enable_missing_fields=True,
        enable_workflow_validator=True,
        enable_duplicate_check=True,
        config=config,
    )

    payload = {"eventType": "scheduled_sweep"}
    result = engine.process(payload)

    # Verify structure and expected keys
    assert "rules" in result
    assert "StaleTicketRule" in result["rules"]
    assert "MissingFieldsRule" in result["rules"]
    assert "WorkflowValidatorRule" in result["rules"]

    # Optional: check no rule returns an unhandled error
    for name, details in result["rules"].items():
        assert details["status"] in ["ok", "skipped", "error"]