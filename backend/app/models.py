from sqlalchemy import JSON, Boolean, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base, UTCDateTime, utcnow


class User(Base):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    username: Mapped[str] = mapped_column(String(80), unique=True)
    display_name: Mapped[str] = mapped_column(String(80))
    password_hash: Mapped[str] = mapped_column(Text)
    preferences: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at = mapped_column(UTCDateTime, default=utcnow)


class SessionToken(Base):
    __tablename__ = "sessions"
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    expires_at = mapped_column(UTCDateTime)


class APIKey(Base):
    __tablename__ = "api_keys"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(80))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    prefix: Mapped[str] = mapped_column(String(20))
    scopes: Mapped[list] = mapped_column(JSON)
    created_at = mapped_column(UTCDateTime, default=utcnow)
    last_used_at = mapped_column(UTCDateTime, nullable=True)
    expires_at = mapped_column(UTCDateTime, nullable=True)


class Chapter(Base):
    __tablename__ = "chapters"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    subject: Mapped[str] = mapped_column(String(20))
    name: Mapped[str] = mapped_column(String(100))
    position: Mapped[int] = mapped_column(Integer, default=0)
    __table_args__ = (UniqueConstraint("user_id", "subject", "name"),)


class Item(Base):
    __tablename__ = "items"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(240))
    subject: Mapped[str] = mapped_column(String(20), index=True)
    chapter_id: Mapped[str | None] = mapped_column(ForeignKey("chapters.id", ondelete="SET NULL"))
    kind: Mapped[str] = mapped_column(String(20), default="concept")
    question: Mapped[str] = mapped_column(Text, default="")
    answer: Mapped[str] = mapped_column(Text, default="")
    difficulty: Mapped[str] = mapped_column(String(20), default="medium")
    tags: Mapped[list] = mapped_column(JSON, default=list)
    source: Mapped[str] = mapped_column(String(500), default="")
    is_mistake: Mapped[bool] = mapped_column(Boolean, default=False)
    mistake_reason: Mapped[str] = mapped_column(Text, default="")
    takeaway: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(20), default="active", index=True)
    deleted_from: Mapped[str | None] = mapped_column(String(20))
    external_id: Mapped[str | None] = mapped_column(String(200))
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at = mapped_column(UTCDateTime, default=utcnow)
    updated_at = mapped_column(UTCDateTime, default=utcnow, onupdate=utcnow)
    card: Mapped["CardState"] = relationship(cascade="all, delete-orphan", uselist=False, lazy="selectin")
    attachments: Mapped[list["ItemMedia"]] = relationship(cascade="all, delete-orphan", lazy="selectin")
    __table_args__ = (UniqueConstraint("user_id", "external_id"), Index("ix_items_owner_status", "user_id", "status"))


class CardState(Base):
    __tablename__ = "card_states"
    item_id: Mapped[str] = mapped_column(ForeignKey("items.id", ondelete="CASCADE"), primary_key=True)
    data: Mapped[dict] = mapped_column(JSON)
    due = mapped_column(UTCDateTime, index=True)
    last_review = mapped_column(UTCDateTime, nullable=True)
    stability: Mapped[float | None] = mapped_column(Float)
    difficulty: Mapped[float | None] = mapped_column(Float)
    state: Mapped[int] = mapped_column(Integer, default=1)
    version: Mapped[int] = mapped_column(Integer, default=0)


class Media(Base):
    __tablename__ = "media"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    filename: Mapped[str] = mapped_column(String(250))
    storage_name: Mapped[str] = mapped_column(String(80), unique=True)
    mime_type: Mapped[str] = mapped_column(String(50))
    size: Mapped[int] = mapped_column(Integer)
    width: Mapped[int] = mapped_column(Integer)
    height: Mapped[int] = mapped_column(Integer)
    created_at = mapped_column(UTCDateTime, default=utcnow)


class ItemMedia(Base):
    __tablename__ = "item_media"
    item_id: Mapped[str] = mapped_column(ForeignKey("items.id", ondelete="CASCADE"), primary_key=True)
    media_id: Mapped[str] = mapped_column(ForeignKey("media.id"), primary_key=True)
    role: Mapped[str] = mapped_column(String(20), primary_key=True)
    position: Mapped[int] = mapped_column(Integer, default=0)
    media: Mapped[Media] = relationship(lazy="joined")


class Review(Base):
    __tablename__ = "reviews"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    item_id: Mapped[str] = mapped_column(ForeignKey("items.id", ondelete="CASCADE"), index=True)
    request_id: Mapped[str] = mapped_column(String(100))
    payload_hash: Mapped[str] = mapped_column(String(64))
    rating: Mapped[int] = mapped_column(Integer)
    reviewed_at = mapped_column(UTCDateTime, default=utcnow, index=True)
    duration_ms: Mapped[int] = mapped_column(Integer, default=0)
    answer_text: Mapped[str] = mapped_column(Text, default="")
    answer_media: Mapped[list] = mapped_column(JSON, default=list)
    before: Mapped[dict] = mapped_column(JSON)
    after: Mapped[dict] = mapped_column(JSON)
    fsrs_log: Mapped[dict] = mapped_column(JSON)
    was_new: Mapped[bool] = mapped_column(Boolean, default=False)
    undone: Mapped[bool] = mapped_column(Boolean, default=False)
    card_version: Mapped[int] = mapped_column(Integer)
    retention: Mapped[float] = mapped_column(Float, default=0.9)
    __table_args__ = (UniqueConstraint("user_id", "request_id"),)


class ImportReceipt(Base):
    __tablename__ = "import_receipts"
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    archive_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    count: Mapped[int] = mapped_column(Integer)
    created_at = mapped_column(UTCDateTime, default=utcnow)
