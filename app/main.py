# app/main.py
"""FastAPI server with specialized webhook endpoints"""
from __future__ import annotations

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse

from core.config import Config
from core.logging import logger
from app.auth import verify_header_secret
from app.webhook_handlers import (
    handle_l1_triage,
    handle_admin_validator,
    handle_jira_architect,
    handle_hygiene,
)

# health deps
from tools.jira_api import JiraAPI
from llm.ollama_client import test_ollama_connection

app = FastAPI(title="Jira Simple Agents", version="1.0.0")
config = Config()


@app.post("/api/v1/l1-triage-bot")
async def l1_triage_webhook(request: Request):
    """
    L1 Triage Bot - Incident support
    """
    # read raw early so HMAC/hardening is possible later
    _ = await request.body()

    if not verify_header_secret(request):
        raise HTTPException(status_code=401, detail="Invalid webhook secret")

    try:
        data = await request.json()
        issue = data.get("issue", {})
        issue_key = issue.get("key")
        if not issue_key:
            raise HTTPException(status_code=400, detail="No issue key provided")

        logger.info(f"L1 Triage webhook received for {issue_key}")
        result = handle_l1_triage(data, config)

        return {
            "received": True,
            "issue_key": issue_key,
            "result": result,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"L1 triage webhook error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/v1/admin-validator")
async def admin_validator_webhook(request: Request):
    """
    Admin Validator - Field requests
    """
    _ = await request.body()

    if not verify_header_secret(request):
        raise HTTPException(status_code=401, detail="Invalid webhook secret")

    try:
        data = await request.json()
        issue = data.get("issue", {})
        issue_key = issue.get("key")
        if not issue_key:
            raise HTTPException(status_code=400, detail="No issue key provided")

        logger.info(f"Admin validator webhook received for {issue_key}")
        result = handle_admin_validator(data, config)

        return {
            "received": True,
            "issue_key": issue_key,
            "result": result,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Admin validator webhook error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/v1/jira-architect")
async def jira_architect_webhook(request: Request):
    """
    Jira Architect - Admin/architecture guidance
    """
    _ = await request.body()

    if not verify_header_secret(request):
        raise HTTPException(status_code=401, detail="Invalid webhook secret")

    try:
        data = await request.json()
        issue = data.get("issue", {})
        issue_key = issue.get("key")
        if not issue_key:
            raise HTTPException(status_code=400, detail="No issue key provided")

        logger.info(f"Jira architect webhook received for {issue_key}")
        result = handle_jira_architect(data, config)

        return {
            "received": True,
            "issue_key": issue_key,
            "result": result,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Jira architect webhook error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/v1/hygiene")
async def hygiene_webhook(request: Request):
    """
    Hygiene sweep endpoint (scheduled or event-driven).
    """
    if not verify_header_secret(request):
        raise HTTPException(status_code=401, detail="Invalid webhook secret")

    try:
        body = await request.json()
    except Exception:
        body = {}

    try:
        result = handle_hygiene(body, config)
        return JSONResponse(content=result, status_code=200)
    except Exception as e:
        logger.error(f"Hygiene webhook error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/health")
async def health_check():
    """
    Health check endpoint – validates LLM and Jira connectivity.
    """
    # LLM
    ollama_status = test_ollama_connection(config)

    # Jira
    jira = JiraAPI(config)
    jira_status = jira.test_connection()

    status = "healthy" if jira_status.get("success") and ollama_status.get("status") == "success" else "degraded"
    return {
        "status": status,
        "jira": jira_status,
        "ollama": ollama_status,
        "config": {
            "jira_url": config.jira_base_url,
            "ollama_url": config.ollama_url,
            "model": config.model,
        },
    }


# Optional: allow direct `python -m app.main` run
if __name__ == "__main__":
    import uvicorn
    logger.info("Starting dev server from app.main __main__")
    uvicorn.run(app, host="0.0.0.0", port=8000)
