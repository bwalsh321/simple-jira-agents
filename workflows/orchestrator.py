# workflows/orchestrator.py
from __future__ import annotations
from typing import Any, Dict, Optional

from core.config import Config
from core.logging import logger

from workflows.hygiene_engine import HygieneEngine
from workflows.llm_engine import LLMEngine


def run_full(
    payload: Dict[str, Any],
    *,
    mode: str = "both",          # "rules" | "llm" | "both"
    llm_agent: str = "l1_triage",# or "admin_validator"
    config: Optional[Config] = None,

    # hygiene toggles (forwarded into HygieneEngine)
    projects: Optional[list[str]] = None,
    enable_stale: bool = True,
    enable_missing_fields: bool = True,
    enable_workflow_validator: bool = True,
    enable_duplicate_check: bool = True,
    stale_add_comment: bool = False,
    missing_fields_add_comment: bool = False,
    workflow_add_comment: bool = False,
) -> Dict[str, Any]:
    """
    One entry point to orchestrate engines:
      - mode="rules": only hygiene/rule engine
      - mode="llm":   only llm agent
      - mode="both":  run hygiene then llm
    """
    cfg = config or Config()
    mode = (mode or "both").lower()
    out: Dict[str, Any] = {"mode": mode}

    logger.info(f"orchestrator.run_full mode={mode}")

    if mode in {"rules", "both"}:
        hygiene = HygieneEngine(
            projects=projects,
            enable_stale=enable_stale,
            enable_missing_fields=enable_missing_fields,
            enable_workflow_validator=enable_workflow_validator,
            enable_duplicate_check=enable_duplicate_check,
            stale_add_comment=stale_add_comment,
            missing_fields_add_comment=missing_fields_add_comment,
            workflow_add_comment=workflow_add_comment,
            config=cfg,
        )
        out["rules"] = hygiene.process(payload)

    if mode in {"llm", "both"}:
        llm = LLMEngine(agent=llm_agent, config=cfg)
        out["llm"] = llm.process(payload)

    return out