from datetime import UTC, date, datetime, timedelta
from uuid import uuid4
from zoneinfo import ZoneInfo

from fsrs import Card, State

from app.database import SessionLocal
from app.models import CardState
from app.reviews import EXAM_WINDOW_DAYS

NOW = datetime(2030, 1, 1, 4, tzinfo=UTC)  # 12:00 in Asia/Shanghai
ZONE = ZoneInfo("Asia/Shanghai")


def set_clock(monkeypatch, now=NOW):
    monkeypatch.setattr("app.reviews.utcnow", lambda: now)
    monkeypatch.setattr("app.stats.utcnow", lambda: now)


def set_exam(client, exam):
    prefs = client.get("/api/v1/auth/me").json()["preferences"]
    prefs["exam_date"] = exam.isoformat() if exam else None
    response = client.put("/api/v1/preferences", json=prefs)
    assert response.status_code == 200, response.text


def mature(item_id, due):
    """Give a card a long-term state whose next review sits at `due`."""
    with SessionLocal() as db:
        state = db.get(CardState, item_id)
        card = Card.from_dict(state.data)
        card.state, card.stability, card.difficulty = State.Review, 200.0, 3.0
        card.last_review, card.due, card.step = NOW - timedelta(days=60), due, None
        state.data, state.due, state.last_review = card.to_dict(), card.due, card.last_review
        state.stability, state.difficulty, state.state, state.version = 200.0, 3.0, 2, 1
        db.commit()


def window(exam):
    first = exam - timedelta(days=EXAM_WINDOW_DAYS)
    lo = datetime.combine(first, datetime.min.time(), ZONE).astimezone(UTC)
    hi = datetime.combine(exam, datetime.min.time(), ZONE).astimezone(UTC)
    return lo, hi


def test_long_intervals_are_pulled_before_the_exam(account, item, monkeypatch):
    set_clock(monkeypatch)
    exam = date(2030, 3, 11)  # 70 days away
    mature(item["id"], NOW)
    set_exam(account, None)
    free = account.get(f"/api/v1/items/{item['id']}/preview").json()["ratings"]["easy"]
    assert datetime.fromisoformat(free["due"]) > window(exam)[1]
    set_exam(account, exam)
    lo, hi = window(exam)
    ratings = account.get(f"/api/v1/items/{item['id']}/preview").json()["ratings"]
    for name in ("good", "easy"):
        due = datetime.fromisoformat(ratings[name]["due"])
        assert lo <= due < hi, name
    response = account.post(f"/api/v1/items/{item['id']}/reviews", json={
        "request_id": str(uuid4()), "rating": "easy", "expected_version": 1})
    assert response.status_code == 201, response.text
    assert lo <= datetime.fromisoformat(response.json()["review"]["due"]) < hi


def test_short_intervals_are_untouched(account, item, monkeypatch):
    set_clock(monkeypatch)
    set_exam(account, date(2030, 3, 11))
    preview = account.get(f"/api/v1/items/{item['id']}/preview").json()["ratings"]["good"]
    assert preview["interval_seconds"] == 600


def test_existing_cards_after_exam_are_rebalanced(account, item, monkeypatch):
    set_clock(monkeypatch)
    exam = date(2030, 3, 11)
    mature(item["id"], NOW + timedelta(days=120))
    set_exam(account, exam)
    lo, hi = window(exam)
    with SessionLocal() as db:
        state = db.get(CardState, item["id"])
        assert lo <= state.due < hi
        assert Card.from_dict(state.data).due == state.due
        assert state.version == 2
    assert account.get("/api/v1/reviews/due").status_code == 200


def test_past_exam_date_changes_nothing(account, item, monkeypatch):
    set_clock(monkeypatch)
    later = NOW + timedelta(days=120)
    mature(item["id"], later)
    set_exam(account, date(2029, 12, 1))
    account.get("/api/v1/reviews/due")
    with SessionLocal() as db:
        assert db.get(CardState, item["id"]).due == later
