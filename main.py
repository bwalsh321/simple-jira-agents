"""FastAPI server with specialized webhook endpoints"""

from fastapi import FastAPI, Request, HTTPException
import hmac
import hashlib
import logging
from config import Config
from agents.l1_triage_bot import process_ticket as process_l1_triage
from agents.admin_validator import process_admin_request

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Jira Simple Agents", version="1.0.0")
config = Config()

def verify_webhook_secret(request: Request, body: bytes) -> bool:
    """Verify webhook secret"""
    provided_secret = request.headers.get("x-webhook-secret", "")
    return hmac.compare_digest(provided_secret, config.webhook_secret)

@app.post("/api/v1/l1-triage-bot")
async def l1_triage_webhook(request: Request):
    """L1 Triage Bot - Incident support"""
    body = await request.body()
    
    if not verify_webhook_secret(request, body):
        raise HTTPException(status_code=401, detail="Invalid webhook secret")
    
    try:
        data = await request.json()
        issue = data.get("issue", {})
        issue_key = issue.get("key")
        
        if not issue_key:
            raise HTTPException(status_code=400, detail="No issue key provided")
        
        logger.info(f"L1 Triage webhook received for {issue_key}")
        
        # Process in background (for now, synchronous)
        result = process_l1_triage(issue_key, issue, config)
        
        return {
            "received": True,
            "issue_key": issue_key,
            "result": result
        }
        
    except Exception as e:
        logger.error(f"L1 triage webhook error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/v1/admin-validator")
async def admin_validator_webhook(request: Request):
    """Admin Validator - Field requests"""
    body = await request.body()
    
    if not verify_webhook_secret(request, body):
        raise HTTPException(status_code=401, detail="Invalid webhook secret")
    
    try:
        data = await request.json()
        issue = data.get("issue", {})
        issue_key = issue.get("key")
        
        if not issue_key:
            raise HTTPException(status_code=400, detail="No issue key provided")
        
        logger.info(f"Admin validator webhook received for {issue_key}")
        
        result = process_admin_request(issue_key, issue, config)
        
        return {
            "received": True,
            "issue_key": issue_key,
            "result": result
        }
        
    except Exception as e:
        logger.error(f"Admin validator webhook error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    from ollama_client import test_ollama_connection
    from api import JiraAPI
    
    # Test Ollama
    ollama_status = test_ollama_connection(config)
    
    # Test Jira
    jira = JiraAPI(config)
    jira_status = jira.test_connection()
    
    return {
        "status": "healthy" if jira_status.get("success") and ollama_status.get("status") == "success" else "degraded",
        "jira": jira_status,
        "ollama": ollama_status,
        "config": {
            "jira_url": config.jira_base_url,
            "ollama_url": config.ollama_url,
            "model": config.model
        }
    }


from engines.hygiene_engine import HygieneEngine

@app.post("/api/v1/hygiene")
async def hygiene_webhook(request: Request):
    # shared-secret check
    if request.headers.get("x-webhook-secret") != config.webhook_secret:
        raise HTTPException(status_code=401, detail="Invalid webhook secret")

    # accept either Jira payload or a simple body
    try:
        body = await request.json()
    except Exception:
        body = {}

    # default to a sweep if no event provided
    evt = (body or {}).get("eventType") or "scheduled_sweep"

    engine = HygieneEngine(
        projects=["SBX"],               # your sandbox project key
        stale_days=7,
        enable_stale=True,
        enable_missing_fields=True,
        enable_workflow_validator=True,
        # keep side-effects OFF while testing:
        stale_add_comment=True,
        missing_fields_add_comment=False,
        workflow_add_comment=False,
    )
    return engine.process({"eventType": evt})



if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)