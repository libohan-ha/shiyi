import io
import json
import zipfile
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from PIL import Image

from app.config import settings
from app.database import SessionLocal, utcnow
from app.models import Item, Review
from app.static import SPAFiles


def test_dashboard_new_quota_matches_review_queue(account, item):
    for subject in ("math", "english"):
        account.post("/api/v1/items", json={"subject": subject, "title": subject, "question": "Q", "answer": "A"})
    preferences = account.get("/api/v1/auth/me").json()["preferences"]
    preferences["daily_new_limit"] = 1
    account.put("/api/v1/preferences", json=preferences)
    plan = account.get("/api/v1/stats").json()
    queue = account.get("/api/v1/reviews/due").json()
    assert plan["today"]["new_available"] == queue["new_available"] == 1
    assert plan["today"]["due"] == 0
    assert plan["today"]["estimated_minutes"] == 2
    assert not plan["today"]["estimate_from_history"]
    assert sum(subject["new"] for subject in plan["subjects"]) == 3
    preferences["daily_new_limit"] = 0
    account.put("/api/v1/preferences", json=preferences)
    plan = account.get("/api/v1/stats").json()
    assert plan["today"]["new_available"] == plan["today"]["estimated_minutes"] == 0


def test_dashboard_estimate_uses_subject_history_and_includes_overdue(account):
    records = []
    for index, duration in enumerate((30_000, 60_000, 18_000_000)):
        record = account.post("/api/v1/items", json={"subject": "math", "title": f"Math {index}", "question": "Q", "answer": "A"}).json()
        response = account.post(f"/api/v1/items/{record['id']}/reviews", json={"rating": "good", "duration_ms": duration, "expected_version": 0})
        assert response.status_code == 201, response.text
        records.append(record)
    with SessionLocal() as db:
        for record in records:
            card = db.get(Item, record["id"]).card
            card.due = utcnow() - timedelta(days=2)
            card.data = {**card.data, "due": card.due.isoformat()}
        db.commit()
    def schedules():
        return [{key: value for key, value in account.get(f"/api/v1/items/{record['id']}").json()["schedule"].items()
                 if key != "retrievability"} for record in records]

    before = schedules()
    plan = account.get("/api/v1/stats").json()
    assert plan["today"]["due"] == plan["today"]["overdue"] == 3
    assert plan["today"]["estimated_minutes"] == 3
    assert plan["today"]["estimate_from_history"]
    assert next(subject for subject in plan["subjects"] if subject["subject"] == "math")["overdue"] == 3
    assert before == schedules()


def test_extra_browser_origins_require_an_exact_match(account, item, monkeypatch):
    monkeypatch.setattr(settings, "allowed_origins", " http://192.168.1.10:8765/, http://localhost:8766 ")
    path = f"/api/v1/items/{item['id']}"
    for origin in ("http://192.168.1.10:8765", "http://localhost:8766", settings.public_url):
        response = account.patch(path, headers={"Origin": origin}, json={"difficulty": "hard"})
        assert response.status_code == 200, response.text
    for origin in ("http://192.168.1.10:8766", "https://192.168.1.10:8765", "http://192.168.1.11:8765",
                   "http://192.168.1.10.evil.example:8765", "null"):
        assert account.patch(path, headers={"Origin": origin}, json={"difficulty": "basic"}).status_code == 403
    assert account.patch(path, headers={"Sec-Fetch-Site": "cross-site"}, json={"difficulty": "basic"}).status_code == 403
    assert account.get(path).json()["difficulty"] == "hard"
    assert account.get("/api/health", headers={"Host": "untrusted.example"}).status_code == 400


def test_bearer_crud_external_ids_and_documentation(account):
    key = account.post("/api/v1/keys", json={"name": "外部助手", "scopes": ["read", "write", "review"]}).json()
    headers = {"Authorization": "Bearer " + key["token"]}
    account.cookies.clear()
    created = account.post("/api/v1/items", headers=headers, json={
        "title": "幂等导入标识", "subject": "math", "question": "导数的定义？", "answer": "差商的极限",
        "external_id": "notes:math:001", "tags": ["微积分"],
    })
    assert created.status_code == 201, created.text
    item = created.json()
    found = account.get("/api/v1/items", headers=headers, params={"external_id": "notes:math:001"}).json()
    assert found["total"] == 1 and found["items"][0]["id"] == item["id"]
    updated = account.patch(f"/api/v1/items/{item['id']}", headers=headers,
                            json={"difficulty": "hard", "expected_version": item["version"]})
    assert updated.status_code == 200
    assert updated.json()["difficulty"] == "hard"
    assert account.delete(f"/api/v1/items/{item['id']}", headers=headers).status_code == 204
    restored = account.post(f"/api/v1/items/{item['id']}/restore", headers=headers)
    assert restored.status_code == 200 and restored.json()["status"] == "active"
    assert account.get("/api/v1/items", headers={"Authorization": "Basic invalid"}).status_code == 401
    assert account.get("/api/v1/keys", headers=headers).status_code == 403
    schema = account.get("/api/openapi.json").json()
    assert schema["components"]["securitySchemes"]["APIKey"]["scheme"] == "bearer"
    assert {"APIKey": []} in schema["paths"]["/api/v1/items"]["post"]["security"]


def test_unicode_and_literal_search(account):
    for title, tags in [("矩阵的秩", ['线性代数', '100%_掌握', 'a"b']), ("微分", ['100AB掌握'])]:
        assert account.post("/api/v1/items", json={
            "title": title, "subject": "math", "question": title, "answer": "判定标准", "tags": tags,
        }).status_code == 201
    for params in ({"q": "线性代数"}, {"q": "%_"}, {"tag": 'a"b'}):
        result = account.get("/api/v1/items", params=params)
        assert result.status_code == 200
        assert result.json()["total"] == 1
        assert result.json()["items"][0]["title"] == "矩阵的秩"
    assert account.get("/api/v1/items", params={"subject": "english"}).json()["total"] == 0


def test_image_only_questions_and_answers(account):
    stream = io.BytesIO()
    Image.new("RGB", (300, 200), "white").save(stream, "PNG")
    media = account.post("/api/v1/media", files={"file": ("截图.png", stream.getvalue(), "image/png")}).json()
    response = account.post("/api/v1/items", json={
        "title": "图片错题", "subject": "math", "kind": "problem", "is_mistake": True,
        "question_media": [media["id"]], "answer_media": [media["id"]],
    })
    assert response.status_code == 201, response.text
    item = response.json()
    assert item["question"] == "" and item["question_media"][0]["width"] == 300
    queue = account.get("/api/v1/reviews/due").json()
    assert "answer_media" not in queue["items"][0]
    assert account.get(media["url"]).headers["content-type"] == "image/webp"
    assert account.patch(f"/api/v1/items/{item['id']}", json={"question_media": []}).status_code == 422


@pytest.mark.parametrize("same_request", [True, False])
def test_concurrent_review_submissions(account, item, same_request):
    def submit(index):
        return account.post(f"/api/v1/items/{item['id']}/reviews", json={
            "request_id": "concurrent" if same_request else f"concurrent-{index}",
            "rating": "good", "expected_version": 0,
        })

    with ThreadPoolExecutor(max_workers=2) as workers:
        responses = list(workers.map(submit, range(2)))
    assert sorted(r.status_code for r in responses) == ([201, 201] if same_request else [201, 409])
    assert account.get(f"/api/v1/items/{item['id']}/reviews").json()["total"] == 1
    if same_request:
        assert sorted(r.json()["already_recorded"] for r in responses) == [False, True]


def test_daily_new_limit_uses_selected_timezone(account, item, monkeypatch):
    instant = datetime(2026, 9, 12, 16, 10, tzinfo=UTC)
    monkeypatch.setattr("app.reviews.utcnow", lambda: instant)
    rated = account.post(f"/api/v1/items/{item['id']}/reviews", json={"rating": "good", "expected_version": 0}).json()
    with SessionLocal() as db:
        review = db.get(Review, rated["review"]["id"])
        review.reviewed_at = datetime(2026, 9, 12, 15, 50, tzinfo=UTC)
        db.commit()
    account.post("/api/v1/items", json={"title": "recall", "subject": "english", "question": "recall", "answer": "回忆"})
    preferences = account.get("/api/v1/auth/me").json()["preferences"]
    preferences.update(daily_new_limit=1, timezone="Asia/Shanghai")
    account.put("/api/v1/preferences", json=preferences)
    assert account.get("/api/v1/reviews/due?subject=english").json()["new_available"] == 1
    preferences["timezone"] = "UTC"
    account.put("/api/v1/preferences", json=preferences)
    assert account.get("/api/v1/reviews/due?subject=english").json()["new_available"] == 0


@pytest.mark.parametrize("field,value", [("state", 999), ("stability", 0), ("stability", float("nan")),
                                         ("difficulty", 100), ("due", "2026-09-12T10:00:00")])
def test_malformed_backup_is_atomic(account, item, field, value):
    original = account.get("/api/v1/export").content
    with zipfile.ZipFile(io.BytesIO(original)) as archive:
        manifest = json.loads(archive.read("manifest.json"))
    manifest["items"][0]["card_data"][field] = value
    corrupted = io.BytesIO()
    with zipfile.ZipFile(corrupted, "w") as archive:
        archive.writestr("manifest.json", json.dumps(manifest))
    response = account.post("/api/v1/import", files={"file": ("bad.zip", corrupted.getvalue(), "application/zip")})
    assert response.status_code == 422
    assert account.get("/api/v1/items").json()["total"] == 1
    assert account.get(f"/api/v1/items/{item['id']}").json()["schedule"]["version"] == 0


def test_spa_routes_and_missing_assets(tmp_path):
    (tmp_path / "index.html").write_text("<main>Shiyi</main>", encoding="utf-8")
    (tmp_path / "assets").mkdir()
    (tmp_path / "assets" / "app.js").write_text("console.log('app')", encoding="utf-8")
    application = FastAPI()
    application.mount("/", SPAFiles(directory=tmp_path, html=True))
    with TestClient(application) as client:
        for path in ("/", "/library", "/items/example", "/settings?tab=api"):
            assert client.get(path).text == "<main>Shiyi</main>"
        assert client.get("/assets/app.js").status_code == 200
        for path in ("/assets/missing.js", "/api/missing", "/.env"):
            assert client.get(path).status_code == 404
