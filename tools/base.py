# tools/base.py
from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Dict, Optional, Callable
import time
from core.config import Config
from core.logging import logger

@dataclass
class ToolResult:
    success: bool
    data: Any | None = None
    error: str | None = None
    meta: Dict[str, Any] | None = None

class Tool:
    """
    Very small base for shared behavior (config access + logging).
    """
    def __init__(self, config: Optional[Config] = None) -> None:
        self.config = config or Config()
        self.logger = logger

def retry(
    fn: Callable[[], Any],
    *,
    attempts: int = 3,
    delay_sec: float = 0.5,
    backoff: float = 2.0,
    swallow: bool = True,
) -> Any:
    """
    Tiny retry helper for flaky I/O. Use only around safe idempotent GETs.
    """
    tries = attempts
    wait = max(0.0, delay_sec)
    last_err: Exception | None = None
    while tries > 0:
        try:
            return fn()
        except Exception as e:
            last_err = e
            logger.warning(f"retry: error={e} tries_left={tries-1}")
            time.sleep(wait)
            wait *= max(1.0, backoff)
            tries -= 1
    if swallow:
        return None
    raise last_err or RuntimeError("retry failed")