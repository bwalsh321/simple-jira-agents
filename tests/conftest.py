import pytest
from core.config import Config

@pytest.fixture(scope="session")
def config():
    return Config()

# tests/unit-local/conftest.py
import os, sys
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)