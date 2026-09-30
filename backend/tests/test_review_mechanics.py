import hashlib
import io
import json
import zipfile
from datetime import UTC, datetime, timedelta
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest
from fsrs import Card, Rating, State

from app.database import SessionLocal
from app.models import CardState, Review, User
from app.reviews import scheduler_for, state_values


def rate(client, item, rating="again", version=0, **fields):
    return client.post(f"/api/v1/items/{item['id']}/reviews", json={
        "request_id": str(uuid4()), "rating": rating, "expected_version": version, **fields})


def problem(client, **fields):
    response = client.post("/api/v1/items", json={
        "title": "Cache 综合题", "subject": "408", "kind": "problem",
        "question": "计算组数与地址位数", "answer": "先统一单位，再计算组数", **fields})
    assert response.status_code == 201, response.text
    return response.json()


def set_clock(monkeypatch, now):
    monkeypatch.setattr("app.reviews.utcnow", lambda: now)
    monkeypatch.setattr("app.stats.utcnow", lambda: now)


@pytest.mark.parametrize("zone,now", [
    ("Asia/Shanghai", datetime(2030, 1, 1, 10, tzinfo=UTC)),
    ("America/New_York", datetime(2030, 3, 10, 5, 30, tzinfo=UTC)),
    ("Asia/Shanghai", datetime(2030, 1, 1, 15, 59, 50, tzinfo=UTC)),
])
@pytest.mark.parametrize("rating", ["again", "hard"])
def test_short_failed_or_hard_review_waits_until_next_local_day(account, item, monkeypatch, zone, now, rating):
    prefs = account.get("/api/v1/auth/me").json()["preferences"]
    prefs["timezone"] = zone
    assert account.put("/api/v1/preferences", json=prefs).status_code == 200
    set_clock(monkeypatch, now)
    local = now.astimezone(ZoneInfo(zone))
    tomorrow = (local + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0).astimezone(UTC)
    preview = account.get(f"/api/v1/items/{item['id']}/preview").json()["ratings"][rating]
    assert datetime.fromisoformat(preview["due"]) == tomorrow
    assert preview["next_day"] is True
    response = rate(account, item, rating)
    assert response.status_code == 201, response.text
    review = response.json()["review"]
    assert datetime.fromisoformat(review["due"]) == tomorrow
    assert account.get("/api/v1/reviews/due").json()["due_count"] == 0
    assert account.post(f"/api/v1/reviews/{review['id']}/undo").status_code == 200
    assert account.get(f"/api/v1/items/{item['id']}").json()["schedule"]["state"] == "new"


def test_good_still_uses_original_learning_step(account, item, monkeypatch):
    now = datetime(2030, 1, 1, 10, tzinfo=UTC)
    set_clock(monkeypatch, now)
    preview = account.get(f"/api/v1/items/{item['id']}/preview").json()["ratings"]["good"]
    assert preview["interval_seconds"] == 600
    assert preview["next_day"] is False
    response = rate(account, item, "good")
    assert datetime.fromisoformat(response.json()["review"]["due"]) == now + timedelta(minutes=10)


def test_relearning_is_deferred_without_changing_fsrs_memory(account, item, monkeypatch):
    now = datetime(2030, 1, 1, 10, tzinfo=UTC)
    set_clock(monkeypatch, now)
    before = Card(state=State.Review, step=None, stability=30, difficulty=5,
                  due=now, last_review=now - timedelta(days=30))
    with SessionLocal() as db:
        state = db.get(CardState, item["id"])
        for key, value in state_values(before).items():
            setattr(state, key, value)
        db.commit()
        scheduler, _ = scheduler_for(db.query(User).first(), "408")
    expected, _ = scheduler.review_card(before, Rating.Again, review_datetime=now)
    response = rate(account, item)
    assert response.status_code == 201, response.text
    result = account.get(f"/api/v1/items/{item['id']}").json()["schedule"]
    assert result["stability"] == expected.stability
    assert result["difficulty"] == expected.difficulty
    assert result["state"] == "relearning"
    assert datetime.fromisoformat(result["due"]) == datetime(2030, 1, 1, 16, tzinfo=UTC)


def test_long_hard_interval_is_not_shortened_to_tomorrow(account, item, monkeypatch):
    now = datetime(2030, 1, 1, 10, tzinfo=UTC)
    set_clock(monkeypatch, now)
    with SessionLocal() as db:
        state = db.get(CardState, item["id"])
        card = Card(state=State.Review, step=None, stability=100, difficulty=5,
                    due=now, last_review=now - timedelta(days=100))
        for key, value in state_values(card).items():
            setattr(state, key, value)
        db.commit()
    preview = account.get(f"/api/v1/items/{item['id']}/preview").json()["ratings"]["hard"]
    assert preview["interval_seconds"] >= 86400
    assert preview["next_day"] is False
    assert datetime.fromisoformat(rate(account, item, "hard").json()["review"]["due"]) >= now + timedelta(days=1)


def test_problem_feedback_is_stored_and_retry_is_idempotent(account):
    item = problem(account)
    payload = {"request_id": "problem-feedback", "rating": "again", "expected_version": 0,
               "expected_item_version": item["version"], "independent_completed": False, "blocker": "不会计算组数"}
    response = account.post(f"/api/v1/items/{item['id']}/reviews", json=payload)
    assert response.status_code == 201, response.text
    saved = response.json()["review"]
    assert saved["independent_completed"] is False
    assert saved["blocker"] == "不会计算组数"
    assert account.post(f"/api/v1/items/{item['id']}/reviews", json=payload).json()["already_recorded"] is True
    history = account.get(f"/api/v1/items/{item['id']}/reviews").json()
    assert history["total"] == 1
    assert history["items"][0]["blocker"] == "不会计算组数"


@pytest.mark.parametrize("rating,completed,blocker", [
    ("again", False, ""), ("good", False, "组数"), ("again", True, ""),
])
def test_contradictory_or_incomplete_problem_feedback_is_rejected(account, rating, completed, blocker):
    item = problem(account)
    assert rate(account, item, rating, independent_completed=completed, blocker=blocker).status_code == 422
    assert account.get(f"/api/v1/items/{item['id']}/reviews").json()["total"] == 0


def test_feedback_on_non_problem_and_stale_content_is_rejected(account, item):
    assert rate(account, item, "good", independent_completed=True).status_code == 422
    old_version = item["version"]
    assert account.patch(f"/api/v1/items/{item['id']}", json={"question": "新的问题"}).status_code == 200
    assert rate(account, item, "good", expected_item_version=old_version).status_code == 409


def test_retry_from_before_upgrade_keeps_legacy_payload_hash(account, item):
    payload = {"request_id": "before-upgrade", "rating": "good", "expected_version": 0,
               "duration_ms": 0, "answer_text": "", "answer_media": []}
    response = account.post(f"/api/v1/items/{item['id']}/reviews", json=payload)
    assert response.status_code == 201
    old_hash = hashlib.sha256(json.dumps({**payload, "item_id": item["id"]},
                                        sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    with SessionLocal() as db:
        db.get(Review, response.json()["review"]["id"]).payload_hash = old_hash
        db.commit()
    retry = account.post(f"/api/v1/items/{item['id']}/reviews", json=payload)
    assert retry.status_code == 201, retry.text
    assert retry.json()["already_recorded"] is True


def test_small_task_has_own_memory_and_traceable_source(account):
    original = problem(account)
    response = account.post("/api/v1/items", json={
        "title": "组数如何计算？", "subject": "408", "question": "组数如何计算？", "answer": "容量除以每组容量",
        "source_item_id": original["id"]})
    assert response.status_code == 201, response.text
    task = response.json()
    assert task["source_item_id"] == original["id"]
    assert task["schedule"]["state"] == "new"
    assert rate(account, original, "good", independent_completed=True).status_code == 201
    assert account.get(f"/api/v1/items/{task['id']}").json()["schedule"]["state"] == "new"
    related = account.get("/api/v1/items", params={"source_item_id": original["id"]}).json()
    assert [i["id"] for i in related["items"]] == [task["id"]]
    assert account.patch(f"/api/v1/items/{task['id']}", json={"source_item_id": task["id"]}).status_code == 422


def test_empty_source_id_is_rejected_before_database_write(account):
    response = account.post("/api/v1/items", json={"title": "小任务", "subject": "408", "question": "Q",
                                                   "answer": "A", "source_item_id": ""})
    assert response.status_code == 422


def test_source_task_cannot_reference_foreign_or_wrong_subject_item(account):
    original = problem(account)
    fields = {"title": "小任务", "subject": "math", "question": "Q", "answer": "A", "source_item_id": original["id"]}
    assert account.post("/api/v1/items", json=fields).status_code == 422
    account.post("/api/v1/auth/logout")
    assert account.post("/api/v1/auth/register", json={"username": "other-learner", "password": "test-password-456"}).status_code == 201
    fields["subject"] = "408"
    assert account.post("/api/v1/items", json=fields).status_code == 422


def test_delayed_recall_excludes_new_cards_and_same_day_repetitions(account, monkeypatch):
    record = problem(account)
    now = datetime(2030, 1, 1, 10, tzinfo=UTC)
    set_clock(monkeypatch, now)
    assert rate(account, record, "good", independent_completed=True).status_code == 201
    set_clock(monkeypatch, now + timedelta(days=2))
    failed = rate(account, record, "again", version=1, independent_completed=False, blocker="分不清组与块").json()["review"]
    set_clock(monkeypatch, now + timedelta(days=2, minutes=10))
    recovered = rate(account, record, "good", version=2, independent_completed=True).json()["review"]
    data = account.get("/api/v1/stats").json()
    assert data["today"]["unique_items"] == 1
    assert data["today"]["reviews"] == 2
    assert data["learning"]["delayed_reviews"] == 1
    assert data["learning"]["delayed_retention"] == 0
    assert data["learning"]["delayed_failures"][0]["blocker"] == failed["blocker"]
    assert data["learning"]["problem_results"][0]["independent_completed"] is True
    assert account.post(f"/api/v1/reviews/{recovered['id']}/undo").status_code == 200
    assert account.get("/api/v1/stats").json()["learning"]["problem_results"][0]["independent_completed"] is False


def test_delayed_recall_uses_learning_date_not_24_hours(account, item, monkeypatch):
    now = datetime(2030, 1, 1, 15, 55, tzinfo=UTC)
    set_clock(monkeypatch, now)
    assert rate(account, item, "good").status_code == 201
    set_clock(monkeypatch, now + timedelta(minutes=10))
    assert rate(account, item, "good", version=1).status_code == 201
    data = account.get("/api/v1/stats").json()
    assert data["learning"]["delayed_reviews"] == 1
    assert data["learning"]["delayed_retention"] == 1
    assert data["learning"]["problem_results"] == []


def test_backup_preserves_feedback_and_remaps_task_source(account):
    original = problem(account)
    response = account.post("/api/v1/items", json={"title": "组数小任务", "subject": "408", "question": "组数？",
        "answer": "容量 / 每组容量", "source_item_id": original["id"]})
    assert response.status_code == 201, response.text
    original_task_id = response.json()["id"]
    assert rate(account, original, independent_completed=False, blocker="单位换算").status_code == 201
    blob = account.get("/api/v1/export").content
    response = account.post("/api/v1/import", files={"file": ("backup.zip", blob, "application/zip")})
    assert response.status_code == 200, response.text
    entries = account.get("/api/v1/items").json()["items"]
    imported_original = next(i for i in entries if i["kind"] == "problem" and i["id"] != original["id"])
    imported_task = next(i for i in entries if i["source_item_id"] == imported_original["id"])
    assert imported_task["id"] != original_task_id
    history = account.get(f"/api/v1/items/{imported_original['id']}/reviews").json()["items"]
    assert history[0]["independent_completed"] is False
    assert history[0]["blocker"] == "单位换算"
    with zipfile.ZipFile(io.BytesIO(blob)) as archive:
        manifest = json.loads(archive.read("manifest.json"))
    for entry in manifest["items"]:
        entry.pop("source_item_id", None)
    for review in manifest["reviews"]:
        review.pop("independent_completed", None)
        review.pop("blocker", None)
    old = io.BytesIO()
    with zipfile.ZipFile(old, "w") as archive:
        archive.writestr("manifest.json", json.dumps(manifest))
    response = account.post("/api/v1/import", files={"file": ("old.zip", old.getvalue(), "application/zip")})
    assert response.status_code == 200, response.text
