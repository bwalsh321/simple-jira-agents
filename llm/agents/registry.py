# agents/registry.py
from __future__ import annotations
from typing import Dict, Type
from agents.base import Agent

_REGISTRY: Dict[str, Type[Agent]] = {}

def register(name: str):
    def _wrap(cls: Type[Agent]):
        _REGISTRY[name] = cls
        return cls
    return _wrap

def get(name: str) -> Type[Agent]:
    return _REGISTRY[name]