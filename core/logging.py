# core/logging.py
import logging
import sys

# Create a single global logger
logger = logging.getLogger("simple_jira_bot")

# Avoid duplicate handlers if file reloads
if not logger.handlers:
    handler = logging.StreamHandler(sys.stdout)
    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    handler.setFormatter(formatter)
    logger.addHandler(handler)

# Default log level (can override in .env later)
logger.setLevel(logging.INFO)