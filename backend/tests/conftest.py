import os
import tempfile
from pathlib import Path

import pytest

TEST_DIRECTORY = tempfile.TemporaryDirectory(prefix="shiyi-tests-")
os.environ["SHIYI_DATA_DIR"] = TEST_DIRECTORY.name
os.environ["SHIYI_DATABASE_URL"] = "sqlite:///" + (Path(TEST_DIRECTORY.name) / "test.db").as_posix()
os.environ["SHIYI_ALLOW_REGISTRATION"] = "true"

from fastapi.testclient import TestClient

from app.database import Base, engine
from app.main import app
from app.security import attempts


@pytest.fixture(scope="session", autouse=True)
def close_database_after_tests():
    yield
    engine.dispose()
    TEST_DIRECTORY.cleanup()


@pytest.fixture
def client():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    attempts.clear()
    with TestClient(app) as client:
        yield client


@pytest.fixture
def account(client):
    response = client.post("/api/v1/auth/register", json={"username": "learner", "password": "test-password-123", "display_name": "小林"})
    assert response.status_code == 201, response.text
    return client


@pytest.fixture
def item(account):
    response = account.post("/api/v1/items", json={"title": "Cache 组数", "subject": "408", "question": "组数怎么计算？", "answer": "容量 /（块大小 × 路数）", "is_mistake": True})
    assert response.status_code == 201, response.text
    return response.json()
