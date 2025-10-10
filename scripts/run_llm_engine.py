#!/usr/bin/env python3
"""
Standalone LLM engine runner.
Useful if a client only uses the AI layer.
"""
from core.config import Config
from workflows.llm_engine import LLMEngine

if __name__ == "__main__":
    cfg = Config()
    llm = LLMEngine(cfg)
    result = llm.process()
    print("🤖 LLM engine output:")
    print(result)