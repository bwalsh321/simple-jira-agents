# app/run.py
#!/usr/bin/env python3
"""Simple runner for Jira AI Agents"""
from __future__ import annotations

import uvicorn
from core.config import Config
from core.logging import logger

if __name__ == "__main__":
    # Validate env early (will raise if required vars are missing)
    _ = Config()
    logger.info("🚀 Starting Jira Simple Agents...")
    uvicorn.run(
        "app.main:app",   # import path to the FastAPI instance
        host="127.0.0.1",
        port=8000,
        reload=True,
        log_level="info",
    )