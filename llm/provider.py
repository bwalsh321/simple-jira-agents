# llm/provider.py
from __future__ import annotations
from typing import Any, Optional
from core.config import Config
from core.logging import logger

# IMPORT PROVIDER CLIENT
from llm.ollama_client import call_ollama

class LLMProvider:
    """
    Thin adapter so agents don't import a specific backend.
    Default backend is Ollama via llm.ollama_client.call_ollama.
    """
    def __init__(self, config: Optional[Config] = None, backend: str = "ollama"):
        self.config = config or Config()
        self.backend = backend

    def chat(self, prompt: str, *, system_prompt: str | None = None, **kwargs: Any) -> Any:
        logger.info(f"LLMProvider(chat) backend={self.backend}")
        if self.backend == "ollama":
            return call_ollama(prompt, system_prompt or "", self.config)
        raise NotImplementedError(f"Unknown backend: {self.backend}")