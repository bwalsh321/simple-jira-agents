#!/usr/bin/env python3
"""
Run all active engines once per day.
Intended for cron / scheduled automation.
"""
from core.config import Config
from workflows.orchestrator import Orchestrator

if __name__ == "__main__":
    cfg = Config()
    orch = Orchestrator(cfg)
    result = orch.run()
    print("✅ Daily sweep complete:")
    print(result)