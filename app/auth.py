# app/auth.py
from __future__ import annotations
from fastapi import Request
import hmac
import hashlib

from core.config import Config

_cfg = Config()

def verify_header_secret(request: Request) -> bool:
    """
    Simple shared check. Compares the X header to your configured secret.
    """
    sent = request.headers.get("x-webhook-secret", "") or ""
    expected = _cfg.webhook_secret or ""
    return hmac.compare_digest(sent, expected)

def verify_hmac_body(raw_body: bytes, signature_header: str | None) -> bool:
    """
    Optional: verify a body HMAC signature if you ever add it.
    Expected header format: 'sha256=<hex>'
    """
    if not signature_header:
        return False
    provided = signature_header.replace("sha256=", "")
    secret = (_cfg.webhook_secret or "").encode()
    digest = hashlib.sha256(secret + (raw_body or b"")).hexdigest()
    return hmac.compare_digest(provided, digest)