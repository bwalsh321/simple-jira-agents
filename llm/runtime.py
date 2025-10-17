# llm/runtime.py
from __future__ import annotations
import os, json, re
from typing import Any, Dict
import yaml
from core.logging import logger

PROMPTS_DIR = os.path.join(os.path.dirname(__file__), "prompts")
_VAR = re.compile(r"{{\s*([a-zA-Z0-9_\.]+)\s*}}")

def load_prompt(name: str) -> Dict[str, Any]:
    """
    Load a prompt YAML by name from llm/prompts/<name>.yml
    """
    path = os.path.join(PROMPTS_DIR, f"{name}.yml")
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    logger.info(f"Loaded prompt: {name}")
    return data

def render(template: str, ctx: Dict[str, Any]) -> str:
    """
    Replace {{ var }} with values from ctx; supports dotted keys.
    Dicts/lists are JSON-stringified.
    """
    def _lookup(path: str, data: Dict[str, Any]) -> Any:
        cur: Any = data
        for part in path.split("."):
            if isinstance(cur, dict):
                cur = cur.get(part)
            else:
                cur = getattr(cur, part, None)
        if isinstance(cur, (dict, list)):
            return json.dumps(cur)
        return "" if cur is None else str(cur)

    return _VAR.sub(lambda m: _lookup(m.group(1), ctx), template or "")