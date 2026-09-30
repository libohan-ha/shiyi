import json
import sys
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import event, select

from app.database import Base, SessionLocal, engine
from app.models import APIKey, Item, Review, User
from app.schemas import Preferences

AGENT = "/api/v1/agent"
NOW = datetime(2030, 11, 4, 12, tzinfo=UTC)


@pytest.fixture
def clock(monkeypatch):
    def freeze(now):
        monkeypatch.setattr("app.stats.utcnow", lambda: now)
        monkeypatch.setattr("app.reviews.utcnow", lambda: now)
        if "app.agent" in sys.modules:
            monkeypatch.setattr(sys.modules["app.agent"], "utcnow", lambda: now)
    freeze(NOW)
    return freeze


def api_key(account, scopes):
    response = account.post("/api/v1/keys", json={"name": "test-only-key", "scopes": scopes})
    assert response.status_code == 201, response.text
    return {"Authorization": "Bearer " + response.json()["token"]}


def make_item(account, **fields):
    response = account.post("/api/v1/items", json={
        "title": "Test item", "subject": "408", "question": "QUESTION_SECRET",
        "answer": "ANSWER_SECRET", **fields})
    assert response.status_code == 201, response.text
    return response.json()


def add_review(item, at=NOW, **fields):
    with SessionLocal() as db:
        record = db.get(Item, item["id"])
        values = {"id": str(uuid4()), "user_id": record.user_id, "item_id": record.id,
                  "request_id": str(uuid4()), "payload_hash": "TEST_PAYLOAD_SECRET", "rating": 1,
                  "reviewed_at": at, "duration_ms": 60_000, "answer_text": "RESPONSE_SECRET",
                  "answer_media": ["TEST_ANSWER_MEDIA_SECRET"], "blocker": "unit conversion",
                  "independent_completed": False, "before": {"last_review": (at - timedelta(days=2)).isoformat()},
                  "after": {"due": (at + timedelta(days=1)).isoformat()}, "fsrs_log": {},
                  "was_new": False, "undone": False, "card_version": 1, **fields}
        db.add(Review(**values))
        db.commit()
        return values["id"]


def set_preferences(**fields):
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.username == "learner"))
        user.preferences = {**user.preferences, **fields}
        db.commit()


def database_snapshot():
    with engine.connect() as connection:
        return {table.name: connection.execute(select(table).order_by(*table.primary_key.columns)).mappings().all()
                for table in Base.metadata.sorted_tables}


def get_ok(account, endpoint, **kwargs):
    response = account.get(f"{AGENT}/{endpoint}", **kwargs)
    assert response.status_code == 200, response.text
    return response.json()


@pytest.mark.parametrize("endpoint", ["context", "reviews", "weaknesses"])
@pytest.mark.parametrize("scopes", [
    ["read"], ["write"], ["review"], ["write", "review"],
    ["read", "write"], ["read", "review"], ["review", "write", "read"],
])
def test_agent_requires_read_and_reports_only_actual_scopes(account, clock, scopes, endpoint):
    headers = api_key(account, scopes)
    # Keep the full-permission browser cookie: bearer scopes must take precedence.
    response = account.get(f"{AGENT}/{endpoint}", headers=headers)
    assert response.status_code == (200 if "read" in scopes else 403), response.text
    if "read" in scopes and endpoint == "context":
        assert response.json()["permissions"] == [s for s in ("read", "write", "review") if s in scopes]


@pytest.mark.parametrize("endpoint", ["context", "reviews", "weaknesses"])
def test_agent_requires_authentication(client, endpoint):
    assert client.get(f"{AGENT}/{endpoint}").status_code == 401


def test_context_is_allowlisted_stats_without_bodies_or_secrets(account, clock):
    original = make_item(account, kind="problem")
    task = make_item(account, source_item_id=original["id"])
    add_review(original)
    add_review(task, independent_completed=None, blocker="")
    headers = api_key(account, ["read"])
    set_preferences(api_token="PREFERENCE_SECRET", password="PREFERENCE_PASSWORD_SECRET")
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.username == "learner"))
        user.password_hash = "PASSWORD_HASH_SECRET"
        db.scalar(select(APIKey).where(APIKey.user_id == user.id)).name = "KEY_NAME_SECRET"
        db.commit()
    stats = account.get("/api/v1/stats").json()
    assert all(stats["learning"][key] for key in ("delayed_failures", "covered_weak_points", "problem_results"))
    result = get_ok(account, "context", headers=headers)
    assert set(result) == {"agent_api_version", "permissions", "profile", "summary", "study_date", "server_time"}
    assert result["agent_api_version"] == 1
    assert set(result["profile"]) == {"display_name", "preferences"}
    assert result["profile"]["display_name"] == "小林"
    assert set(result["profile"]["preferences"]) == set(Preferences.model_fields) - {"display_name"}
    assert result["profile"]["preferences"]["daily_goal"] == 30
    assert set(result["summary"]) == {"today", "totals", "subjects", "learning", "forecast"}
    for key in ("today", "totals", "subjects", "forecast"):
        assert result["summary"][key] == stats[key]
    assert result["summary"]["learning"] == {
        k: v for k, v in stats["learning"].items() if not isinstance(v, list)}
    assert datetime.fromisoformat(result["server_time"]) == NOW
    text = json.dumps(result)
    for secret in ("QUESTION_SECRET", "ANSWER_SECRET", "RESPONSE_SECRET", "TEST_ANSWER_MEDIA_SECRET",
                   "TEST_PAYLOAD_SECRET", "PREFERENCE_SECRET", "PREFERENCE_PASSWORD_SECRET",
                   "PASSWORD_HASH_SECRET", "KEY_NAME_SECRET", headers["Authorization"][7:]):
        assert secret not in text
    for field in ("question", "answer", "answer_text", "answer_media", "question_media", "password_hash",
                  "api_keys", "token_hash", "recent_items", "weak_items", "delayed_failures",
                  "covered_weak_points", "problem_results"):
        assert f'"{field}"' not in text


@pytest.mark.parametrize("zone,instant,expected", [
    ("Asia/Shanghai", datetime(2030, 1, 1, 16, tzinfo=UTC), "2030-01-02"),
    ("America/New_York", datetime(2030, 11, 4, 2, tzinfo=UTC), "2030-11-03"),
])
def test_context_study_date_uses_user_timezone(account, clock, zone, instant, expected):
    set_preferences(timezone=zone)
    clock(instant)
    result = get_ok(account, "context")
    assert result["study_date"] == result["summary"]["forecast"][0]["date"] == expected


def test_context_is_tenant_scoped(account, clock):
    make_item(account)
    headers = api_key(account, ["read"])
    account.cookies.clear()
    assert account.post("/api/v1/auth/register", json={
        "username": "second-user", "password": "test-password-456", "display_name": "Other user"}).status_code == 201
    add_review(make_item(account, title="FOREIGN_TITLE"))
    result = get_ok(account, "context", headers=headers)
    assert result["profile"]["display_name"] == "小林"
    assert result["summary"]["totals"]["items"] == 1
    assert result["summary"]["totals"]["reviews"] == 0
    assert "FOREIGN_TITLE" not in json.dumps(result)


@pytest.mark.parametrize("endpoint", ["context", "reviews", "weaknesses"])
def test_agent_get_never_writes_database(account, clock, endpoint):
    record = make_item(account)
    add_review(record)
    headers = api_key(account, ["read"])
    before = database_snapshot()
    statements = []

    def record_statement(connection, cursor, statement, parameters, context, executemany):
        statements.append(statement.lstrip().split()[0].upper())

    event.listen(engine, "before_cursor_execute", record_statement)
    try:
        get_ok(account, endpoint, headers=headers)
        get_ok(account, endpoint)
    finally:
        event.remove(engine, "before_cursor_execute", record_statement)
    assert not {"INSERT", "UPDATE", "DELETE", "REPLACE", "CREATE", "DROP", "ALTER"}.intersection(statements)
    assert database_snapshot() == before


@pytest.mark.parametrize("include_answers", [None, False, True])
def test_reviews_reuses_history_shape_and_answers_are_opt_in(account, clock, include_answers):
    record = make_item(account, kind="problem")
    review_id = add_review(record)
    params = {} if include_answers is None else {"include_answers": include_answers}
    result = get_ok(account, "reviews", params=params)
    assert set(result) == {"items", "total", "page", "page_size", "has_more", "date_from", "date_to",
                           "timezone", "server_time"}
    assert result["total"] == 1 and result["page"] == 1 and result["page_size"] == 30
    assert result["has_more"] is False
    assert result["date_from"] == "2030-10-06" and result["date_to"] == "2030-11-04"
    assert result["timezone"] == "Asia/Shanghai"
    assert datetime.fromisoformat(result["server_time"]) == NOW
    expected = account.get(f"/api/v1/items/{record['id']}/reviews").json()["items"][0]
    assert expected["id"] == review_id
    if not include_answers:
        expected.pop("answer_text")
        expected.pop("answer_media")
    expected["item"] = {key: record[key] for key in ("id", "title", "subject", "kind", "source_item_id", "status")}
    assert result["items"] == [expected]
    assert "QUESTION_SECRET" not in json.dumps(result)
    assert "ANSWER_SECRET" not in json.dumps(result)
    if include_answers:
        assert result["items"][0]["answer_text"] == "RESPONSE_SECRET"
        assert result["items"][0]["answer_media"] == ["TEST_ANSWER_MEDIA_SECRET"]
    else:
        assert "RESPONSE_SECRET" not in json.dumps(result)


@pytest.fixture
def history_rows(account):
    entries = {
        "again": (make_item(account, kind="problem"), 1, False, "units"),
        "hard": (make_item(account, kind="problem"), 2, True, ""),
        "good": (make_item(account, subject="math", kind="problem"), 3, True, ""),
        "easy": (make_item(account, subject="english"), 4, None, ""),
        "other_again": (make_item(account, subject="english", kind="problem"), 1, False, "grammar"),
    }
    return {name: (record, add_review(record, rating=rating, independent_completed=completed, blocker=blocker))
            for name, (record, rating, completed, blocker) in entries.items()}


@pytest.mark.parametrize("params,names", [
    ({"subject": "408"}, ["again", "hard"]),
    ({"subject": "math"}, ["good"]),
    ({"subject": "english"}, ["easy", "other_again"]),
    ({"rating": "again"}, ["again", "other_again"]),
    ({"rating": "hard"}, ["hard"]),
    ({"rating": "good"}, ["good"]),
    ({"rating": "easy"}, ["easy"]),
    ({"independent_completed": False}, ["again", "other_again"]),
    ({"independent_completed": True}, ["hard", "good"]),
    ({"has_blocker": True}, ["again", "other_again"]),
    ({"has_blocker": False}, ["hard", "good", "easy"]),
    ({"subject": "408", "rating": "again", "independent_completed": False, "has_blocker": True}, ["again"]),
    ({"rating": "easy", "independent_completed": False}, []),
])
def test_reviews_filters_apply_before_count_and_pagination(account, clock, history_rows, params, names):
    expected = sorted((history_rows[name][1] for name in names), reverse=True)
    result = get_ok(account, "reviews", params={**params, "page_size": 1})
    assert result["total"] == len(expected)
    assert [row["id"] for row in result["items"]] == expected[:1]
    assert result["has_more"] is (len(expected) > 1)


def test_reviews_item_filter_and_missing_or_foreign_item_is_404(account, clock, history_rows):
    record, review_id = history_rows["again"]
    headers = api_key(account, ["read"])
    result = get_ok(account, "reviews", headers=headers, params={"item_id": record["id"]})
    assert result["total"] == 1 and result["items"][0]["id"] == review_id
    assert account.get(f"{AGENT}/reviews", params={"item_id": "missing"}, headers=headers).status_code == 404
    with SessionLocal() as db:
        first_user = db.get(Item, record["id"]).user_id
    account.cookies.clear()
    assert account.post("/api/v1/auth/register", json={
        "username": "other-learner", "password": "test-password-456"}).status_code == 201
    foreign = make_item(account, title="FOREIGN_ITEM")
    foreign_review = add_review(foreign)
    # Guard both sides of the join even if an imported row has inconsistent ownership.
    wrong_item_owner = add_review(foreign, user_id=first_user)
    with SessionLocal() as db:
        foreign_user = db.get(Item, foreign["id"]).user_id
    wrong_review_owner = add_review(record, user_id=foreign_user)
    result = get_ok(account, "reviews", headers=headers, params={"include_deleted": True, "include_undone": True})
    assert result["total"] == 5
    assert not {foreign_review, wrong_item_owner, wrong_review_owner}.intersection(row["id"] for row in result["items"])
    assert account.get(f"{AGENT}/reviews", params={"item_id": foreign["id"], "include_deleted": True},
                       headers=headers).status_code == 404


@pytest.mark.parametrize("include_undone,include_deleted", [(False, False), (True, False), (False, True), (True, True)])
def test_reviews_excludes_future_and_optionally_includes_undone_or_deleted(account, clock, include_undone, include_deleted):
    active = make_item(account)
    deleted = make_item(account)
    assert account.delete(f"/api/v1/items/{deleted['id']}").status_code == 204
    expected = [add_review(active), add_review(make_item(account, status="suspended")),
                add_review(make_item(account, status="draft"))]
    undone = add_review(active, undone=True)
    removed = add_review(deleted)
    both = add_review(deleted, undone=True)
    add_review(active, NOW + timedelta(microseconds=1))
    add_review(deleted, NOW + timedelta(days=1), undone=True)
    if include_undone:
        expected.append(undone)
    if include_deleted:
        expected.append(removed)
        if include_undone:
            expected.append(both)
    result = get_ok(account, "reviews", params={"include_undone": include_undone, "include_deleted": include_deleted,
                                               "date_to": "2030-11-06"})
    assert result["total"] == len(expected)
    assert {row["id"] for row in result["items"]} == set(expected)
    filtered = get_ok(account, "reviews", params={"item_id": deleted["id"], "include_deleted": include_deleted})
    assert filtered["total"] == (1 if include_deleted else 0)


def test_reviews_stable_pagination_over_a_hundred_rows(account, clock):
    records = [make_item(account), make_item(account, subject="math")]
    expected = [add_review(records[index % 2], id=f"review-{index:03}") for index in range(105)]
    newer = add_review(records[0], NOW - timedelta(seconds=1), id="zzz-older")
    expected = [*reversed(expected), newer]
    first = get_ok(account, "reviews", params={"page_size": 100})
    second = get_ok(account, "reviews", params={"page_size": 100, "page": 2})
    assert first["total"] == second["total"] == 106
    assert first["has_more"] is True and second["has_more"] is False
    assert second["page"] == 2 and second["page_size"] == 100
    assert [row["id"] for row in first["items"] + second["items"]] == expected
    empty = get_ok(account, "reviews", params={"page_size": 100, "page": 3})
    assert empty["items"] == [] and empty["total"] == 106 and empty["has_more"] is False


@pytest.mark.parametrize("zone,day,start,end", [
    ("Asia/Shanghai", "2030-01-02", datetime(2030, 1, 1, 16, tzinfo=UTC), datetime(2030, 1, 2, 16, tzinfo=UTC)),
    ("America/New_York", "2030-03-10", datetime(2030, 3, 10, 5, tzinfo=UTC), datetime(2030, 3, 11, 4, tzinfo=UTC)),
    ("America/New_York", "2030-11-03", datetime(2030, 11, 3, 4, tzinfo=UTC), datetime(2030, 11, 4, 5, tzinfo=UTC)),
])
def test_reviews_date_filters_use_local_midnight_and_dst(account, clock, zone, day, start, end):
    set_preferences(timezone=zone)
    record = make_item(account)
    add_review(record, start - timedelta(microseconds=1))
    included = [add_review(record, start), add_review(record, end - timedelta(microseconds=1))]
    add_review(record, end)
    result = get_ok(account, "reviews", params={"date_from": day, "date_to": day})
    assert result["total"] == 2
    assert {row["id"] for row in result["items"]} == set(included)
    assert result["date_from"] == result["date_to"] == day
    assert result["timezone"] == zone


def test_reviews_default_window_uses_thirty_user_dates_not_utc_or_720_hours(account, clock):
    clock(datetime(2030, 11, 4, 2, tzinfo=UTC))  # Still November 3 in New York.
    set_preferences(timezone="America/New_York")
    record = make_item(account)
    start = datetime(2030, 10, 5, 4, tzinfo=UTC)
    add_review(record, start - timedelta(microseconds=1))
    included = add_review(record, start)
    result = get_ok(account, "reviews")
    assert result["date_from"] == "2030-10-05" and result["date_to"] == "2030-11-03"
    assert result["total"] == 1 and result["items"][0]["id"] == included
    assert get_ok(account, "reviews", params={"date_to": "2030-03-10"})["date_from"] == "2030-02-09"


@pytest.mark.parametrize("params", [
    {"page": 0}, {"page": -1}, {"page": "x"}, {"page_size": 0}, {"page_size": 101},
    {"subject": "unknown"}, {"rating": "1"}, {"rating": "Again"}, {"independent_completed": "maybe"},
    {"has_blocker": "maybe"}, {"include_answers": "maybe"}, {"include_deleted": "maybe"}, {"include_undone": "maybe"},
    {"date_from": "garbage"}, {"date_to": "2030-02-30"}, {"date_from": "2030-03-11", "date_to": "2030-03-10"},
    {"date_from": "2029-01-01", "date_to": "2030-01-02"},
    {"date_from": "0001-01-01", "date_to": "0001-01-01"},
    {"date_from": "9999-12-31", "date_to": "9999-12-31"},
])
def test_reviews_invalid_query_is_422(account, clock, params):
    response = account.get(f"{AGENT}/reviews", params=params)
    assert response.status_code == 422, response.text


def test_reviews_accepts_366_inclusive_days_and_from_only(account, clock):
    record = make_item(account)
    review_id = add_review(record, datetime(2029, 1, 1, tzinfo=UTC))
    result = get_ok(account, "reviews", params={"date_from": "2029-01-01", "date_to": "2030-01-01"})
    assert result["total"] == 1 and result["items"][0]["id"] == review_id
    result = get_ok(account, "reviews", params={"date_from": "2030-11-01"})
    assert result["date_to"] == "2030-11-04"


WEAK_FIELDS = {"id", "title", "subject", "kind", "status", "source_item_id", "schedule", "blocker",
               "reviewed_at", "elapsed_days"}


def test_weaknesses_pages_all_failures_beyond_stats_top_ten(account, clock):
    expected = []
    for index in range(25):
        record = make_item(account, title=f"weak-{index}", subject="408" if index < 13 else "math")
        add_review(record, NOW - timedelta(minutes=index))
        expected.append(record["id"])
    first = get_ok(account, "weaknesses", params={"page_size": 10})
    second = get_ok(account, "weaknesses", params={"page_size": 10, "page": 2})
    last = get_ok(account, "weaknesses", params={"page_size": 10, "page": 3})
    assert set(first) == {"items", "total", "page", "page_size", "has_more", "days", "timezone", "server_time"}
    assert first["total"] == second["total"] == last["total"] == 25
    assert first["has_more"] is True and second["has_more"] is True and last["has_more"] is False
    assert first["days"] == 30 and first["timezone"] == "Asia/Shanghai"
    assert datetime.fromisoformat(first["server_time"]) == NOW
    assert [row["id"] for row in first["items"] + second["items"] + last["items"]] == expected
    for row in first["items"]:
        assert set(row) == WEAK_FIELDS
        assert row["elapsed_days"] == 2
    assert "SECRET" not in json.dumps(first)
    learning = account.get("/api/v1/stats").json()["learning"]
    assert learning["delayed_failure_count"] == 25 and len(learning["delayed_failures"]) == 10
    assert first["items"] == [{k: v for k, v in row.items() if k in WEAK_FIELDS}
                              for row in learning["delayed_failures"]]
    default = get_ok(account, "weaknesses")
    assert default["page_size"] == 30 and len(default["items"]) == 25
    filtered = get_ok(account, "weaknesses", params={"subject": "math", "page_size": 10, "page": 2})
    assert filtered["total"] == 12 and filtered["has_more"] is False
    assert [row["id"] for row in filtered["items"]] == expected[23:]
    empty = get_ok(account, "weaknesses", params={"page": 99})
    assert empty["items"] == [] and empty["total"] == 25 and empty["has_more"] is False


def test_weaknesses_have_stable_item_id_tiebreaker(account, clock):
    ids = [make_item(account)["id"] for _ in range(3)]
    for item_id in ids:
        add_review({"id": item_id})
    pages = [get_ok(account, "weaknesses", params={"page": page, "page_size": 1}) for page in range(1, 4)]
    assert [page["items"][0]["id"] for page in pages] == sorted(ids, reverse=True)


def test_weaknesses_only_clear_on_next_cross_day_success_with_real_reviews(account, clock):
    record = make_item(account, kind="problem")

    def rate(at, rating, version):
        clock(at)
        response = account.post(f"/api/v1/items/{record['id']}/reviews", json={
            "rating": rating, "expected_version": version, "independent_completed": rating != "again",
            "blocker": "forgot units" if rating == "again" else ""})
        assert response.status_code == 201, response.text
        return response.json()["review"]

    def assert_count(count):
        result = get_ok(account, "weaknesses")
        learning = account.get("/api/v1/stats").json()["learning"]
        assert result["total"] == learning["delayed_failure_count"] == count
        assert [row["id"] for row in result["items"]] == [row["id"] for row in learning["delayed_failures"]]
        return result

    rate(NOW - timedelta(days=2), "again", 0)
    assert_count(0)  # New cards are not delayed recall failures.
    rate(NOW - timedelta(days=2) + timedelta(minutes=10), "good", 1)
    assert_count(0)  # Same-day relearning is not delayed recall either.
    failed = rate(NOW, "again", 2)
    assert_count(1)
    rate(NOW + timedelta(minutes=10), "good", 3)
    result = assert_count(1)
    assert result["items"][0]["blocker"] == failed["blocker"]
    assert result["items"][0]["reviewed_at"] == failed["reviewed_at"]
    assert result["items"][0]["elapsed_days"] == 2
    rate(NOW + timedelta(days=1), "good", 4)
    assert_count(0)


@pytest.mark.parametrize("case", ["new", "no_previous", "same_day", "undone", "future", "draft", "suspended", "deleted"])
def test_weaknesses_excludes_invalid_failures(account, clock, case):
    record = make_item(account, status=case if case in ("draft", "suspended") else "active")
    fields = {}
    at = NOW
    if case == "new":
        fields["was_new"] = True
    elif case == "no_previous":
        fields["before"] = {}
    elif case == "same_day":
        fields["before"] = {"last_review": (NOW - timedelta(minutes=5)).isoformat()}
    elif case == "undone":
        fields["undone"] = True
    elif case == "future":
        at += timedelta(microseconds=1)
    elif case == "deleted":
        assert account.delete(f"/api/v1/items/{record['id']}").status_code == 204
    add_review(record, at, **fields)
    result = get_ok(account, "weaknesses")
    assert result["items"] == [] and result["total"] == 0
    assert account.get("/api/v1/stats").json()["learning"]["delayed_failure_count"] == 0


@pytest.mark.parametrize("success", ["same_day", "undone", "future"])
def test_weaknesses_ignores_success_that_does_not_replace_cross_day_failure(account, clock, success):
    record = make_item(account)
    failed_at = NOW - timedelta(days=1)
    add_review(record, failed_at)
    add_review(record, failed_at + timedelta(minutes=5) if success == "same_day" else
               NOW + timedelta(microseconds=1) if success == "future" else NOW,
               rating=3, undone=success == "undone", card_version=2,
               before={"last_review": failed_at.isoformat()}, independent_completed=True, blocker="")
    result = get_ok(account, "weaknesses")
    assert result["total"] == 1
    assert result["items"][0]["id"] == record["id"]
    assert datetime.fromisoformat(result["items"][0]["reviewed_at"]) == failed_at
    assert account.get("/api/v1/stats").json()["learning"]["delayed_failure_count"] == 1


def test_weaknesses_uses_first_valid_answer_on_a_learning_day(account, clock):
    record = make_item(account)
    add_review(record, rating=1, undone=True, card_version=1)
    add_review(record, rating=3, independent_completed=True, blocker="", card_version=2)
    add_review(record, rating=1, card_version=3)
    assert get_ok(account, "weaknesses")["total"] == 0
    assert account.get("/api/v1/stats").json()["learning"]["delayed_failure_count"] == 0


@pytest.mark.parametrize("days", [1, 7, 30, 365])
def test_weaknesses_custom_window_includes_start_only(account, clock, days):
    start = datetime(2030, 11, 3, 16, tzinfo=UTC) - timedelta(days=days - 1)
    inside = make_item(account)
    add_review(inside, start)
    add_review(make_item(account), start - timedelta(microseconds=1))
    result = get_ok(account, "weaknesses", params={"days": days})
    assert result["days"] == days and result["total"] == 1
    assert result["items"][0]["id"] == inside["id"]


@pytest.mark.parametrize("zone,previous,current,expected", [
    ("Asia/Shanghai", datetime(2030, 1, 1, 15, 55, tzinfo=UTC), datetime(2030, 1, 1, 16, 5, tzinfo=UTC), 1),
    ("America/New_York", datetime(2030, 3, 11, 3, 55, tzinfo=UTC), datetime(2030, 3, 11, 4, 5, tzinfo=UTC), 1),
    ("America/New_York", datetime(2030, 11, 4, 4, 55, tzinfo=UTC), datetime(2030, 11, 4, 5, 5, tzinfo=UTC), 1),
    ("America/New_York", datetime(2030, 11, 3, 5, 55, tzinfo=UTC), datetime(2030, 11, 3, 6, 5, tzinfo=UTC), 0),
])
def test_weaknesses_cross_day_means_user_calendar_day_including_dst(account, clock, zone, previous, current, expected):
    set_preferences(timezone=zone)
    clock(current)
    record = make_item(account)
    add_review(record, current, before={"last_review": previous.isoformat()})
    result = get_ok(account, "weaknesses", params={"days": 1})
    assert result["total"] == expected
    assert result["timezone"] == zone
    assert account.get("/api/v1/stats").json()["learning"]["delayed_failure_count"] == expected
    if expected:
        assert result["items"][0]["elapsed_days"] == 1


def test_weaknesses_scopes_both_reviews_and_items_to_user(account, clock):
    owned = make_item(account)
    add_review(owned)
    no_own_review = make_item(account)
    headers = api_key(account, ["read"])
    with SessionLocal() as db:
        owner = db.get(Item, owned["id"]).user_id
    account.cookies.clear()
    assert account.post("/api/v1/auth/register", json={
        "username": "foreign-user", "password": "test-password-456"}).status_code == 201
    foreign = make_item(account, title="FOREIGN_WEAKNESS")
    add_review(foreign)
    add_review(foreign, user_id=owner)
    with SessionLocal() as db:
        foreign_owner = db.get(Item, foreign["id"]).user_id
    add_review(no_own_review, user_id=foreign_owner)
    result = get_ok(account, "weaknesses", headers=headers)
    assert result["total"] == 1 and result["items"][0]["id"] == owned["id"]
    assert "FOREIGN_WEAKNESS" not in json.dumps(result)


@pytest.mark.parametrize("params", [
    {"days": 0}, {"days": 366}, {"days": "x"}, {"days": 1.5}, {"subject": "unknown"},
    {"page": 0}, {"page": -1}, {"page_size": 0}, {"page_size": 101},
])
def test_weaknesses_invalid_query_is_422(account, clock, params):
    response = account.get(f"{AGENT}/weaknesses", params=params)
    assert response.status_code == 422, response.text


def test_learning_summary_optional_days_and_limit_keep_defaults(account, clock):
    from zoneinfo import ZoneInfo

    from app.reviews import day_bounds
    from app.stats import learning_summary

    source = make_item(account, kind="problem")
    for _ in range(12):
        add_review(make_item(account, kind="problem", source_item_id=source["id"]))
    add_review(make_item(account), NOW - timedelta(days=40))
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.username == "learner"))
        start, _ = day_bounds(user, NOW)
        zone = ZoneInfo("Asia/Shanghai")
        items = db.scalars(select(Item).where(Item.user_id == user.id)).all()
        recent = db.execute(select(Review, Item.subject).join(Item).where(Review.user_id == user.id)).all()
        original = learning_summary(recent, items, start, zone)
        assert original[1]["delayed_failure_count"] == 12
        explicit = learning_summary(recent, items, start, zone, days=30, limit=10)
        assert explicit == original
        full = learning_summary(recent, items, start, zone, days=45, limit=None)[1]
        assert full["delayed_failure_count"] == len(full["delayed_failures"]) == 13
        assert len(full["covered_weak_points"]) == len(full["problem_results"]) == 12
        limited = learning_summary(recent, items, start, zone, days=1, limit=1)[1]
        assert limited["delayed_failure_count"] == 12
        for key in ("delayed_failures", "covered_weak_points", "problem_results"):
            assert len(original[1][key]) == 10
            assert len(limited[key]) == 1
