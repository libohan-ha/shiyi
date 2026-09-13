import io
import json
import zipfile
from datetime import timedelta

from fsrs import Card, Rating
from PIL import Image

from app.config import settings
from app.database import SessionLocal, utcnow
from app.models import CardState, User
from app.reviews import scheduler_for


def image_bytes():
    output = io.BytesIO()
    Image.new("RGB", (320, 180), "white").save(output, format="PNG")
    return output.getvalue()


def rate(client, item, request_id="attempt-1", rating="good", version=0):
    return client.post(f"/api/v1/items/{item['id']}/reviews", json={
        "request_id": request_id, "rating": rating, "expected_version": version, "duration_ms": 60000})


def test_setup_login_and_private_registration(client):
    assert client.get("/api/v1/auth/status").json()["initialized"] is False
    settings.allow_registration = False
    try:
        assert client.post("/api/v1/auth/register", json={"username": "owner", "password": "strong-password"}).status_code == 201
        assert client.post("/api/v1/auth/register", json={"username": "owner2", "password": "strong-password"}).status_code == 403
        assert client.get("/api/v1/auth/me").json()["username"] == "owner"
        assert client.post("/api/v1/auth/logout").status_code == 204
        assert client.get("/api/v1/auth/me").status_code == 401
        assert client.post("/api/v1/auth/login", json={"username": "owner", "password": "strong-password"}).status_code == 200
    finally:
        settings.allow_registration = True


def test_item_lifecycle_keeps_memory_and_hides_answers(account, item):
    queue = account.get("/api/v1/reviews/due").json()
    assert queue["new_available"] == 1
    assert "answer" not in queue["items"][0]
    first = rate(account, item)
    assert first.status_code == 201, first.text
    edited = account.patch(f"/api/v1/items/{item['id']}", json={"answer": "补充：统一容量单位", "expected_version": 1}).json()
    assert edited["schedule"]["version"] == 1
    assert edited["schedule"]["last_review"] is not None
    assert account.patch(f"/api/v1/items/{item['id']}", json={"title": "旧窗口", "expected_version": 1}).status_code == 409
    account.delete(f"/api/v1/items/{item['id']}")
    assert account.get("/api/v1/items").json()["total"] == 0
    assert account.get("/api/v1/items?status=deleted").json()["total"] == 1
    restored = account.post(f"/api/v1/items/{item['id']}/restore").json()
    assert restored["schedule"]["last_review"] == edited["schedule"]["last_review"]


def test_real_fsrs_retry_conflict_and_undo(account, item):
    with SessionLocal() as db:
        state = db.get(CardState, item["id"])
        before = state.data.copy()
        user = db.query(User).first()
        scheduler, _ = scheduler_for(user, item["subject"])
    response = rate(account, item)
    assert response.status_code == 201, response.text
    data = response.json()
    from datetime import datetime
    expected, _ = scheduler.review_card(Card.from_dict(before), Rating.Good,
                                        review_datetime=datetime.fromisoformat(data["review"]["reviewed_at"]), review_duration=60000)
    assert data["review"]["due"] == expected.to_dict()["due"]
    duplicate = rate(account, item).json()
    assert duplicate["already_recorded"] is True
    assert account.get(f"/api/v1/items/{item['id']}/reviews").json()["total"] == 1
    assert rate(account, item, rating="hard").status_code == 409
    assert rate(account, item, request_id="new-attempt-stale").status_code == 409
    assert account.post(f"/api/v1/reviews/{data['review']['id']}/undo").status_code == 200
    restored = account.get(f"/api/v1/items/{item['id']}").json()
    assert restored["schedule"]["state"] == "new"
    assert restored["schedule"]["version"] == 2
    assert account.get("/api/v1/stats").json()["today"]["reviews"] == 0
    assert rate(account, item, request_id="attempt-after-undo", version=2).status_code == 201


def test_hard_is_success_and_daily_limit(account, item):
    assert rate(account, item, rating="hard").status_code == 201
    stats = account.get("/api/v1/stats").json()
    assert stats["totals"]["retention"] == 1
    assert stats["today"]["minutes"] == 1
    prefs = account.get("/api/v1/auth/me").json()["preferences"]
    prefs["daily_new_limit"] = 0
    assert account.put("/api/v1/preferences", json=prefs).status_code == 200
    account.post("/api/v1/items", json={"title": "新单词", "subject": "english", "question": "recall", "answer": "回忆"})
    queue = account.get("/api/v1/reviews/due").json()
    assert queue["new_count"] == 1 and queue["new_available"] == 0
    with SessionLocal() as db:
        state = db.get(CardState, item["id"])
        state.due = utcnow() - timedelta(hours=1)
        db.commit()
    assert account.get("/api/v1/reviews/due").json()["due_count"] == 1


def test_images_cross_account_and_scoped_api(account, item):
    upload = account.post("/api/v1/media", files={"file": ("题目.png", image_bytes(), "image/png")})
    assert upload.status_code == 201, upload.text
    media = upload.json()
    assert account.get(media["url"]).status_code == 200
    assert account.post("/api/v1/media", files={"file": ("fake.png", b"not-an-image", "image/png")}).status_code == 422
    key = account.post("/api/v1/keys", json={"name": "读取", "scopes": ["read"]}).json()
    headers = {"Authorization": "Bearer " + key["token"]}
    assert account.get("/api/v1/items", headers=headers).status_code == 200
    assert account.delete(f"/api/v1/items/{item['id']}", headers=headers).status_code == 403
    assert account.get("/api/v1/keys", headers=headers).status_code == 403
    account.post("/api/v1/auth/logout")
    assert account.get(media["url"]).status_code == 401
    account.post("/api/v1/auth/register", json={"username": "another", "password": "test-password-456"})
    assert account.get(f"/api/v1/items/{item['id']}").status_code == 404
    assert account.get(media["url"]).status_code == 404
    assert account.post("/api/v1/items", json={"title": "越权附件", "subject": "math", "question_media": [media["id"]], "answer": "答案"}).status_code == 422


def test_archive_roundtrip_and_malicious_archive(account, item):
    media = account.post("/api/v1/media", files={"file": ("题图.png", image_bytes(), "image/png")}).json()
    account.patch(f"/api/v1/items/{item['id']}", json={"question_media": [media["id"]]})
    assert rate(account, item).status_code == 201
    exported = account.get("/api/v1/export")
    assert exported.status_code == 200
    files = {"file": ("backup.zip", exported.content, "application/zip")}
    imported = account.post("/api/v1/import", files=files)
    assert imported.status_code == 200, imported.text
    assert imported.json()["imported"] == 1
    assert account.get("/api/v1/items").json()["total"] == 2
    assert account.post("/api/v1/import", files=files).json()["already_imported"] is True
    assert account.get("/api/v1/items").json()["total"] == 2
    forged = io.BytesIO()
    with zipfile.ZipFile(forged, "w") as archive:
        archive.writestr("manifest.json", json.dumps({"format": "shiyi", "version": 1, "chapters": [], "items": [], "reviews": [],
                                                       "media": [{"id": "evil", "filename": "x", "path": "../../x"}]}))
    assert account.post("/api/v1/import", files={"file": ("bad.zip", forged.getvalue())}).status_code == 422


def test_csrf_unknown_fields_and_chapter_validation(account, item):
    assert account.delete(f"/api/v1/items/{item['id']}", headers={"Origin": "https://evil.example"}).status_code == 403
    assert account.patch(f"/api/v1/items/{item['id']}", json={"schedule": {"due": "2099-01-01"}}).status_code == 422
    chapters = account.get("/api/v1/chapters").json()
    other = next(c for c in chapters if c["subject"] == "math")
    assert account.patch(f"/api/v1/items/{item['id']}", json={"chapter_id": other["id"]}).status_code == 422
    assert account.post("/api/v1/items", json={"title": "空题", "subject": "math"}).status_code == 422
    assert account.post("/api/v1/items", json={"title": "稍后补充", "subject": "math", "status": "draft"}).status_code == 201
