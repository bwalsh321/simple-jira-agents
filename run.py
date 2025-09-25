#!/usr/bin/env python3
"""Simple runner for Jira AI Agents"""
import uvicorn
from config import Config

if __name__ == "__main__":  # FIXED: was **name**, should be __name__
    # Load config to validate environment variables
    config = Config()
    
    print("🚀 Starting Jira Simple Agents...")
    uvicorn.run(
        "main:app",  # FIXED: import string format to avoid warning
        host="127.0.0.1", 
        port=8000,
        reload=True,  # Auto-reload on file changes
        log_level="info"
    )