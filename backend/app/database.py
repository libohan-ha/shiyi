from datetime import UTC, datetime

from sqlalchemy import DateTime, create_engine, event, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.types import TypeDecorator

from .config import settings


def utcnow():
    return datetime.now(UTC)


class UTCDateTime(TypeDecorator):
    impl = DateTime
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is not None:
            return value.astimezone(UTC).replace(tzinfo=None)

    def process_result_value(self, value, dialect):
        return value.replace(tzinfo=UTC) if value is not None else None


class Base(DeclarativeBase):
    pass


engine = create_engine(
    settings.database_url,
    connect_args={"check_same_thread": False, "timeout": 20} if settings.database_url.startswith("sqlite") else {},
    pool_pre_ping=True,
)
if settings.database_url.startswith("sqlite"):
    @event.listens_for(engine, "connect")
    def sqlite_settings(connection, _):
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA journal_mode=WAL")

SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


def lock_sqlite_writer(session):
    """SQLite has no row locks. Serialize short mutations before reading their state."""
    if session.bind.dialect.name == "sqlite":
        connection = session.connection().connection.driver_connection
        if not connection.in_transaction:
            session.execute(text("BEGIN IMMEDIATE"))


@event.listens_for(Session, "after_commit")
def media_committed(session):
    session.info.pop("new_media_files", None)


@event.listens_for(Session, "after_rollback")
def media_rolled_back(session):
    for path in session.info.pop("new_media_files", []):
        path.unlink(missing_ok=True)


def get_db():
    with SessionLocal() as session:
        try:
            yield session
        finally:
            if session.in_transaction():
                session.rollback()
