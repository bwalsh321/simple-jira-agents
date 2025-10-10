# agents/base.py
from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional
from core.config import Config
from llm.provider import LLMProvider

class Agent(ABC):
    def __init__(self, config: Optional[Config] = None, llm: Optional[LLMProvider] = None):
        self.config = config or Config()
        self.llm = llm or LLMProvider(self.config)

    @abstractmethod
    def run(self, event: Dict[str, Any]) -> Dict[str, Any]:
        ...