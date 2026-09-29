import os
import sqlite3
import subprocess
import sys
from contextlib import closing
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1]
OLD_REVISION = "9ce1295fcf53"
NEW_REVISION = "b521cf13a902"
TABLES = ("users", "chapters", "items", "card_states", "media", "item_media", "reviews")
TIMESTAMP = "2020-01-02 03:04:05.123456"


def migrate(directory, direction, revision):
    # Never load an Alembic config or app settings from the real working directory.
    database_url = "sqlite:///" + (directory / "migration.db").as_posix()
    environment = os.environ.copy()
    environment.update(
        SHIYI_DATA_DIR=str(directory / "data"),
        SHIYI_DATABASE_URL=database_url,
        DATABASE_URL=database_url,
        PYTHONPATH=str(BACKEND),
    )
    result = subprocess.run(
        [sys.executable, "-c", """
import sys
from alembic import command
from alembic.config import Config
config = Config()
config.set_main_option("script_location", sys.argv[1])
getattr(command, sys.argv[2])(config, sys.argv[3])
""", str(BACKEND / "migrations"), direction, revision],
        cwd=directory, env=environment, capture_output=True, text=True, timeout=60,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def insert(connection, table, row):
    columns = ", ".join(f'"{column}"' for column in row)
    placeholders = ", ".join("?" for _ in row)
    connection.execute(f'INSERT INTO "{table}" ({columns}) VALUES ({placeholders})', tuple(row.values()))


def seed_history(connection):
    insert(connection, "users", {
        "id": "owner", "username": "legacy", "display_name": "Old learner", "password_hash": "test-only",
        "preferences": '{}', "created_at": TIMESTAMP,
    })
    insert(connection, "chapters", {
        "id": "chapter", "user_id": "owner", "subject": "408", "name": "Cache", "position": 2,
    })
    for item_id in ("source", "task"):
        insert(connection, "items", {
            "id": item_id, "user_id": "owner", "title": item_id, "subject": "408", "chapter_id": "chapter",
            "kind": "problem" if item_id == "source" else "concept", "question": "Question", "answer": "Answer",
            "difficulty": "medium", "tags": '["legacy"]', "source": "book", "is_mistake": 1,
            "mistake_reason": "units", "takeaway": "convert first", "status": "active", "deleted_from": None,
            "external_id": None, "version": 4, "created_at": TIMESTAMP, "updated_at": TIMESTAMP,
        })
        insert(connection, "card_states", {
            "item_id": item_id, "data": '{"legacy": true}', "due": TIMESTAMP, "last_review": TIMESTAMP,
            "stability": 3.5, "difficulty": 5.0, "state": 2, "version": 6,
        })
    insert(connection, "media", {
        "id": "image", "user_id": "owner", "filename": "image.webp", "storage_name": "image.webp",
        "mime_type": "image/webp", "size": 20, "width": 2, "height": 2, "created_at": TIMESTAMP,
    })
    insert(connection, "item_media", {"item_id": "task", "media_id": "image", "role": "question", "position": 0})
    insert(connection, "reviews", {
        "id": "review", "user_id": "owner", "item_id": "task", "request_id": "legacy-request",
        "payload_hash": "legacy", "rating": 1, "reviewed_at": TIMESTAMP, "duration_ms": 1234,
        "answer_text": "historical answer", "answer_media": '["image"]', "before": '{"old": true}',
        "after": '{"new": true}', "fsrs_log": '{}', "was_new": 0, "undone": 0, "card_version": 6,
        "retention": 0.9,
    })
    connection.commit()


def snapshot(connection):
    return {table: [dict(row) for row in connection.execute(f'SELECT * FROM "{table}" ORDER BY 1')]
            for table in TABLES}


def assert_history_preserved(connection, expected):
    actual = snapshot(connection)
    for table, rows in expected.items():
        assert len(actual[table]) == len(rows), f"{table}: migration deleted historical rows"
        columns = rows[0].keys()
        assert [{key: row[key] for key in columns} for row in actual[table]] == rows, table
    assert connection.execute("PRAGMA foreign_key_check").fetchall() == []


@pytest.fixture
def legacy_database(tmp_path):
    migrate(tmp_path, "upgrade", OLD_REVISION)
    with closing(sqlite3.connect(tmp_path / "migration.db")) as connection:
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        seed_history(connection)
        yield connection, tmp_path, snapshot(connection)


def test_upgrade_preserves_history_and_adds_unknown_feedback(legacy_database):
    connection, directory, before = legacy_database
    migrate(directory, "upgrade", "head")
    assert_history_preserved(connection, before)
    assert connection.execute("SELECT version_num FROM alembic_version").fetchone()[0] == NEW_REVISION
    assert [row[0] for row in connection.execute("SELECT source_item_id FROM items")] == [None, None]
    assert tuple(connection.execute("SELECT independent_completed, blocker FROM reviews").fetchone()) == (None, "")
    columns = {row[1]: row for row in connection.execute("PRAGMA table_info(reviews)")}
    assert columns["blocker"][3] == 1
    assert columns["blocker"][4] == "''"
    assert columns["independent_completed"][3] == 0
    indexes = {row[1] for row in connection.execute("PRAGMA index_list(items)")}
    assert "ix_items_source_item_id" in indexes


def test_downgrade_preserves_history_even_with_populated_source_links(tmp_path):
    migrate(tmp_path, "upgrade", "head")
    with closing(sqlite3.connect(tmp_path / "migration.db")) as connection:
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        seed_history(connection)
        connection.execute("UPDATE items SET source_item_id = 'source' WHERE id = 'task'")
        connection.execute("UPDATE reviews SET independent_completed = 0, blocker = 'unit conversion'")
        connection.commit()
        before = snapshot(connection)
        for item in before["items"]:
            item.pop("source_item_id")
        for review in before["reviews"]:
            review.pop("independent_completed")
            review.pop("blocker")
        migrate(tmp_path, "downgrade", OLD_REVISION)
        assert_history_preserved(connection, before)
        assert connection.execute("SELECT version_num FROM alembic_version").fetchone()[0] == OLD_REVISION
        assert "source_item_id" not in {row[1] for row in connection.execute("PRAGMA table_info(items)")}
        assert "blocker" not in {row[1] for row in connection.execute("PRAGMA table_info(reviews)")}
        assert "ix_items_source_item_id" not in {row[1] for row in connection.execute("PRAGMA index_list(items)")}


def test_migrated_source_foreign_key_sets_null_without_deleting_task(legacy_database):
    connection, directory, _ = legacy_database
    migrate(directory, "upgrade", "head")
    connection.execute("UPDATE items SET source_item_id = 'source' WHERE id = 'task'")
    with pytest.raises(sqlite3.IntegrityError):
        connection.execute("UPDATE items SET source_item_id = 'missing' WHERE id = 'task'")
    connection.execute("DELETE FROM items WHERE id = 'source'")
    assert connection.execute("SELECT source_item_id FROM items WHERE id = 'task'").fetchone()[0] is None
    assert connection.execute("SELECT COUNT(*) FROM card_states WHERE item_id = 'task'").fetchone()[0] == 1
    assert connection.execute("SELECT COUNT(*) FROM reviews WHERE item_id = 'task'").fetchone()[0] == 1
    assert connection.execute("SELECT COUNT(*) FROM item_media WHERE item_id = 'task'").fetchone()[0] == 1
    assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
