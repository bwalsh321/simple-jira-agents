# app/webhook_handlers.py
from __future__ import annotations
from core.logging import logger
from core.config import Config

# existing agent flows you already have
from llm.agents.l1_triage_bot import process_ticket as process_l1_triage
from llm.agents.admin_validator import process_admin_request

# your hygiene engine (class-based) you already call today
from workflows.hygiene_engine import HygieneEngine


def handle_l1_triage(payload: dict, cfg: Config) -> dict:
    """
    Thin wrapper around your existing L1 triage function.
    """
    issue = payload.get("issue") or {}
    issue_key = issue.get("key")
    logger.info(f"handler:l1_triage key={issue_key}")
    return process_l1_triage(issue_key, issue, cfg)


def handle_admin_validator(payload: dict, cfg: Config) -> dict:
    """
    Thin wrapper around your existing admin validator function.
    """
    issue = payload.get("issue") or {}
    issue_key = issue.get("key")
    logger.info(f"handler:admin_validator key={issue_key}")
    return process_admin_request(issue_key, issue, cfg)


def handle_hygiene(payload: dict, cfg: Config) -> dict:
    evt = (payload or {}).get("eventType") or "scheduled_sweep"

    raw = (payload or {}).get("projects")
    if isinstance(raw, list) and raw:
        projects = [str(p).strip() for p in raw if str(p).strip()]
    elif isinstance(raw, str) and raw.strip():
        projects = [p.strip() for p in raw.split(",") if p.strip()]
    else:
        projects = cfg.HYGIENE_DEFAULT_PROJECTS
    
    logger.info(f"hygiene: evt={evt} projects={projects}")
    print('Hi')
    
    engine = HygieneEngine(
        projects=projects,
        enable_stale=True,
        enable_missing_fields=True,
        enable_workflow_validator=True,
        enable_duplicate_check=True,
        stale_add_comment=True,
        missing_fields_add_comment=True,
        workflow_add_comment=True,
    )

    return engine.process({"eventType": evt})