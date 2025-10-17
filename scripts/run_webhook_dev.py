#!/usr/bin/env python3
"""
Run a lightweight local FastAPI server that logs all incoming webhooks.

Useful for:
- Testing Jira → local development via ngrok or cloudflared tunnel
- Validating headers and payload structure before wiring to real handlers

Example:
    uvicorn scripts.run_webhook_dev:app --reload --port 9000
"""
import json
import logging
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("webhook-dev")

app = FastAPI(title="Webhook Dev Server", version="0.1")

@app.post("/webhook")
async def receive_webhook(request: Request):
    """Catch-all endpoint for any POSTed JSON webhook payload."""
    headers = dict(request.headers)
    try:
        body = await request.json()
    except Exception:
        body = await request.body()
        try:
            body = body.decode()
        except Exception:
            pass

    logger.info("=" * 60)
    logger.info("📩 Webhook received")
    logger.info(f"Headers: {json.dumps(headers, indent=2)}")
    logger.info(f"Body: {json.dumps(body, indent=2) if isinstance(body, (dict, list)) else body}")
    logger.info("=" * 60)

    return JSONResponse({"ok": True, "message": "Received", "type": type(body).__name__})

@app.get("/")
async def root():
    return {"status": "running", "usage": "POST /webhook with JSON payload"}

if __name__ == "__main__":
    import uvicorn
    print("🚀 Starting local webhook dev server on http://127.0.0.1:9000/webhook")
    uvicorn.run("scripts.run_webhook_dev:app", host="127.0.0.1", port=9000, reload=True)