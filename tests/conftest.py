import pytest
from core.config import Config

@pytest.fixture(scope="session")
def config():
    return Config()