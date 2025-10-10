#!/usr/bin/env python3
"""
Run both Hygiene + LLM engines, like production would.
"""
from core.config import Config
from workflows.orchestrator import Orchestrator

if __name__ == "__main__":
    cfg = Config()
    orch = Orchestrator(cfg)
    summary = orch.run()
    print("🏁 Orchestrator run summary:")
    print(summary)