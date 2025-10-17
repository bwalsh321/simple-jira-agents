#!/usr/bin/env python3
"""
Standalone hygiene runner for manual testing or debugging.
"""
from core.config import Config
from workflows.hygiene_engine import HygieneEngine

if __name__ == "__main__":
    cfg = Config()
    engine = HygieneEngine(
        projects=["SBX"],
        enable_stale=True,
        enable_missing_fields=True,
        enable_workflow_validator=True,
        stale_add_comment=True,
        missing_fields_add_comment=True,
        workflow_add_comment=True,
    )
    res = engine.process({"eventType": "scheduled_sweep"})
    print(res)