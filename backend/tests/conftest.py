import os
import pytest
from fastapi.testclient import TestClient

TEST_DB_FILE = os.path.abspath("test_app.db")
if os.path.exists(TEST_DB_FILE):
    try:
        os.remove(TEST_DB_FILE)
    except Exception:
        pass

# Configure environment for tests before importing app
os.environ["DATABASE_URL"] = f"sqlite:///{TEST_DB_FILE}"
os.environ["LLM_API_KEYS"] = "mock_key_1,mock_key_2"
os.environ["ENABLE_FAILURE_SIMULATION"] = "true"
os.environ["DEFAULT_MODEL"] = "gemini/gemini-2.0-flash"
os.environ["MOCK_LLM"] = "true"

from app.config import settings
settings.DATABASE_URL = f"sqlite:///{TEST_DB_FILE}"
settings.LLM_API_KEYS = "mock_key_1,mock_key_2"
settings.ENABLE_FAILURE_SIMULATION = True
settings.MOCK_LLM = True

from app.main import app
from app.database import init_db


@pytest.fixture(autouse=True)
def setup_test_db():
    init_db(settings.DATABASE_URL)
    yield
    if os.path.exists(TEST_DB_FILE):
        try:
            os.remove(TEST_DB_FILE)
        except Exception:
            pass


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c
