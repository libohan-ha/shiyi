import io
import json
import zipfile
from datetime import UTC, datetime

import pytest
from PIL import Image
from sqlalchemy import select, update

from app.config import settings
from app.database import SessionLocal
from app.models import CardState, Chapter, ImportReceipt, Item, ItemMedia, Media, Review


def export_archive(client):
    response = client.get("/api/v1/export")
    assert response.status_code == 200, response.text
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        manifest = json.loads(archive.read("manifest.json"))
        assets = {name: archive.read(name) for name in archive.namelist() if name != "manifest.json"}
    return manifest, assets


def import_archive(client, manifest, assets):
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        archive.writestr("manifest.json", json.dumps(manifest))
        for name, content in assets.items():
            archive.writestr(name, content)
    return client.post("/api/v1/import", files={"file": ("backup.zip", output.getvalue(), "application/zip")})


@pytest.fixture
def feedback_archive(account):
    image = io.BytesIO()
    Image.new("RGB", (4, 4), "white").save(image, "PNG")
    uploaded = account.post("/api/v1/media", files={"file": ("question.png", image.getvalue(), "image/png")})
    assert uploaded.status_code == 201, uploaded.text
    media_id = uploaded.json()["id"]
    chapter = account.post("/api/v1/chapters", json={"subject": "408", "name": "Cache"}).json()
    source_response = account.post("/api/v1/items", json={
        "title": "Source problem", "subject": "408", "kind": "problem", "chapter_id": chapter["id"],
        "question": "Calculate cache groups", "answer": "Capacity / group size", "question_media": [media_id],
    })
    assert source_response.status_code == 201, source_response.text
    source = source_response.json()
    task_response = account.post("/api/v1/items", json={
        "title": "Focused task", "subject": "408", "question": "Convert units", "answer": "Bytes first",
        "source_item_id": source["id"], "answer_media": [media_id],
    })
    assert task_response.status_code == 201, task_response.text
    for version, (completed, rating, blocker) in enumerate([
        (None, "good", ""), (False, "again", "单位换算"), (True, "hard", ""),
    ]):
        response = account.post(f"/api/v1/items/{source['id']}/reviews", json={
            "request_id": f"feedback-{version}", "expected_version": version,
            "rating": rating, "independent_completed": completed, "blocker": blocker,
            "answer_text": f"attempt-{version}", "answer_media": [media_id], "duration_ms": 1000,
        })
        assert response.status_code == 201, response.text
    with SessionLocal() as db:
        db.execute(update(Item).values(
            created_at=datetime(2020, 1, 1, 1, 2, 3, 456789, tzinfo=UTC),
            updated_at=datetime(2021, 2, 3, 4, 5, 6, 123456, tzinfo=UTC),
        ))
        db.commit()
    return export_archive(account)


def test_export_announces_v2(account, item):
    manifest, _ = export_archive(account)
    assert manifest["version"] == 2


def test_export_preserves_true_false_unknown_feedback(feedback_archive):
    manifest, _ = feedback_archive
    feedback = {review["answer_text"]: (review["independent_completed"], review["blocker"])
                for review in manifest["reviews"]}
    assert feedback == {"attempt-0": (None, ""), "attempt-1": (False, "单位换算"), "attempt-2": (True, "")}


@pytest.mark.parametrize("version", [1, 2])
def test_import_accepts_supported_versions(account, item, version):
    manifest, assets = export_archive(account)
    manifest["version"] = version
    response = import_archive(account, manifest, assets)
    assert response.status_code == 200, response.text
    assert response.json() == {"imported": 1, "already_imported": False}


@pytest.mark.parametrize("version", [True, 1.0, "2", 3])
def test_import_rejects_invalid_format_version(account, item, version):
    manifest, assets = export_archive(account)
    manifest["version"] = version
    response = import_archive(account, manifest, assets)
    assert response.status_code == 422, response.text


def stored_state():
    models = (Chapter, Item, CardState, Review, Media, ItemMedia, ImportReceipt)
    with SessionLocal() as db:
        rows = {model.__tablename__: [dict(row) for row in db.execute(
            select(model.__table__).order_by(*model.__table__.primary_key.columns)).mappings()]
                for model in models}
    files = {path.name: path.read_bytes() for path in (settings.data_dir / "media").iterdir() if path.is_file()}
    return rows, files


def archive_items(manifest):
    source = next(item for item in manifest["items"] if item["kind"] == "problem")
    task = next(item for item in manifest["items"] if item["kind"] == "concept")
    return source, task


@pytest.mark.parametrize("other_account", [False, True])
def test_child_before_source_is_linked_only_to_imported_copy(account, feedback_archive, other_account):
    manifest, assets = feedback_archive
    source, task = archive_items(manifest)
    manifest["items"] = [task, source]
    if other_account:
        assert account.post("/api/v1/auth/logout").status_code == 204
        response = account.post("/api/v1/auth/register", json={
            "username": "backup-recipient", "password": "test-password-456",
        })
        assert response.status_code == 201, response.text
    response = import_archive(account, manifest, assets)
    assert response.status_code == 200, response.text
    entries = account.get("/api/v1/items").json()["items"]
    copies = {item["title"]: item for item in entries if item["id"] not in {source["id"], task["id"]}}
    assert len(copies) == 2
    copied_source, copied_task = copies[source["title"]], copies[task["title"]]
    assert copied_task["source_item_id"] == copied_source["id"]
    assert copied_source["source_item_id"] is None
    assert copied_task["schedule"]["version"] == task["schedule"]["version"]
    assert copied_source["schedule"]["version"] == source["schedule"]["version"]
    copied_media = copied_source["question_media"][0]["id"]
    assert copied_media != manifest["media"][0]["id"]
    assert copied_task["answer_media"][0]["id"] == copied_media
    history = account.get(f"/api/v1/items/{copied_source['id']}/reviews").json()["items"]
    assert len(history) == 3
    assert all(review["item_id"] == copied_source["id"] and review["answer_media"] == [copied_media]
               for review in history)


def test_import_keeps_reference_to_soft_deleted_source(account, feedback_archive):
    manifest, _ = feedback_archive
    source, task = archive_items(manifest)
    assert account.delete(f"/api/v1/items/{source['id']}").status_code == 204
    manifest, assets = export_archive(account)
    source, task = archive_items(manifest)
    assert source["status"] == "deleted"
    manifest["items"] = [task, source]
    response = import_archive(account, manifest, assets)
    assert response.status_code == 200, response.text
    with SessionLocal() as db:
        copied_task = db.scalar(select(Item).where(Item.title == task["title"], Item.id != task["id"]))
        copied_source = db.get(Item, copied_task.source_item_id)
        assert copied_source.id != source["id"]
        assert copied_source.status == "deleted"
        assert copied_source.deleted_from == source["deleted_from"]


@pytest.mark.parametrize("case", [
    "self", "duplicate-id", "missing-source", "source-outside-archive", "wrong-subject", "non-problem-source",
    "numeric-source", "empty-source", "empty-id",
])
def test_invalid_source_relationship_rolls_back_everything(account, feedback_archive, case):
    manifest, assets = feedback_archive
    source, task = archive_items(manifest)
    if case == "self":
        source["source_item_id"] = source["id"]
    elif case == "duplicate-id":
        manifest["items"].append(dict(task))
    elif case == "missing-source":
        task["source_item_id"] = "missing"
    elif case == "source-outside-archive":
        manifest["items"] = [task]
        manifest["reviews"] = []
    elif case == "wrong-subject":
        source["subject"] = "math"
        source["chapter_id"] = None
    elif case == "non-problem-source":
        source["kind"] = "concept"
    elif case == "numeric-source":
        task["source_item_id"] = 42
    elif case == "empty-source":
        task["source_item_id"] = ""
    elif case == "empty-id":
        task["id"] = ""
    # Force a newly inserted chapter as well as new media, to exercise rollback fully.
    manifest["chapters"][0]["name"] = "Chapter only in invalid backup"
    before = stored_state()
    response = import_archive(account, manifest, assets)
    assert response.status_code == 422, response.text
    assert stored_state() == before


def test_import_preserves_timestamps_after_source_remapping(account, feedback_archive):
    manifest, assets = feedback_archive
    source, task = archive_items(manifest)
    manifest["items"] = [task, source]
    response = import_archive(account, manifest, assets)
    assert response.status_code == 200, response.text
    with SessionLocal() as db:
        for old in manifest["items"]:
            copied = db.scalar(select(Item).where(Item.title == old["title"], Item.id != old["id"]))
            assert copied.created_at == datetime.fromisoformat(old["created_at"])
            assert copied.updated_at == datetime.fromisoformat(old["updated_at"])
            assert copied.card.data == old["card_data"]
        for old in manifest["reviews"]:
            copied = db.scalar(select(Review).where(Review.answer_text == old["answer_text"], Review.id != old["id"]))
            assert copied.reviewed_at == datetime.fromisoformat(old["reviewed_at"])
            assert copied.before == old["before"]
            assert copied.after == old["after"]


def test_import_preserves_true_false_unknown_feedback(account, feedback_archive):
    manifest, assets = feedback_archive
    response = import_archive(account, manifest, assets)
    assert response.status_code == 200, response.text
    with SessionLocal() as db:
        for old in manifest["reviews"]:
            copied = db.scalar(select(Review).where(Review.answer_text == old["answer_text"], Review.id != old["id"]))
            assert copied.independent_completed is old["independent_completed"]
            assert copied.blocker == old["blocker"]


@pytest.mark.parametrize("version", [1, 2])
def test_missing_feedback_stays_unknown_in_legacy_archives(account, feedback_archive, version):
    manifest, assets = feedback_archive
    manifest["version"] = version
    for old in manifest["items"]:
        old.pop("source_item_id")
    for old in manifest["reviews"]:
        old.pop("independent_completed")
        old.pop("blocker")
    response = import_archive(account, manifest, assets)
    assert response.status_code == 200, response.text
    with SessionLocal() as db:
        old_ids = [item["id"] for item in manifest["items"]]
        copies = db.scalars(select(Item).where(Item.id.not_in(old_ids))).all()
        assert len(copies) == 2
        assert all(item.source_item_id is None for item in copies)
        reviews = db.scalars(select(Review).where(Review.item_id.not_in(old_ids))).all()
        assert len(reviews) == 3
        assert all(review.independent_completed is None and review.blocker == "" for review in reviews)


@pytest.mark.parametrize("field,value", [
    ("independent_completed", "false"), ("independent_completed", "true"),
    ("independent_completed", 0), ("independent_completed", 1),
    ("independent_completed", []), ("independent_completed", {}),
    ("blocker", None), ("blocker", 123), ("blocker", False),
    pytest.param("blocker", "x" * 2001, id="blocker-too-long"),
])
def test_invalid_feedback_rolls_back_rows_media_and_receipt(account, feedback_archive, field, value):
    manifest, assets = feedback_archive
    manifest["reviews"][-1][field] = value
    manifest["chapters"][0]["name"] = "Chapter only in invalid feedback backup"
    before = stored_state()
    response = import_archive(account, manifest, assets)
    assert response.status_code == 422, response.text
    assert stored_state() == before


def test_import_keeps_blocker_at_maximum_length(account, feedback_archive):
    manifest, assets = feedback_archive
    old = next(review for review in manifest["reviews"] if review["independent_completed"] is False)
    old["blocker"] = "卡" * 2000
    response = import_archive(account, manifest, assets)
    assert response.status_code == 200, response.text
    with SessionLocal() as db:
        copied = db.scalar(select(Review).where(Review.answer_text == old["answer_text"], Review.id != old["id"]))
        assert copied.independent_completed is False
        assert copied.blocker == old["blocker"]
