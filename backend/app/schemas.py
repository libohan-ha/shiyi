from copy import copy
from datetime import date
from typing import Literal
from uuid import uuid4
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, create_model, field_validator

Subject = Literal["408", "math", "english"]
Difficulty = Literal["basic", "medium", "hard"]
ItemKind = Literal["concept", "problem", "vocabulary", "expression"]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Credentials(StrictModel):
    username: str = Field(min_length=3, max_length=80, pattern=r"^[a-zA-Z0-9_.@-]+$")
    password: str = Field(min_length=10, max_length=128)
    display_name: str = Field(default="同学", min_length=1, max_length=40)


class Login(StrictModel):
    username: str = Field(max_length=80)
    password: str = Field(max_length=128)


class Preferences(StrictModel):
    daily_goal: int = Field(default=30, ge=1, le=1000)
    daily_new_limit: int = Field(default=15, ge=0, le=500)
    retention: dict[str, float] = Field(default_factory=lambda: {"408": .9, "math": .9, "english": .9})
    exam_date: date | None = None
    timezone: str = "Asia/Shanghai"
    display_name: str = Field(default="同学", min_length=1, max_length=40)

    @field_validator("retention")
    @classmethod
    def validate_retention(cls, value):
        if set(value) != {"408", "math", "english"} or any(not .7 <= r <= .97 for r in value.values()):
            raise ValueError("三科目标保持率须介于 70% 与 97% 之间")
        return value

    @field_validator("timezone")
    @classmethod
    def validate_timezone(cls, value):
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError):
            raise ValueError("无效的时区")
        return value


class ItemInput(StrictModel):
    title: str = Field(min_length=1, max_length=240)
    subject: Subject
    chapter_id: str | None = None
    kind: ItemKind = "concept"
    question: str = Field(default="", max_length=60000)
    answer: str = Field(default="", max_length=60000)
    difficulty: Difficulty = "medium"
    tags: list[str] = Field(default_factory=list, max_length=20)
    source: str = Field(default="", max_length=500)
    is_mistake: bool = False
    mistake_reason: str = Field(default="", max_length=10000)
    takeaway: str = Field(default="", max_length=10000)
    status: Literal["active", "draft", "suspended"] = "active"
    external_id: str | None = Field(default=None, max_length=200)
    question_media: list[str] = Field(default_factory=list, max_length=12)
    answer_media: list[str] = Field(default_factory=list, max_length=12)
    expected_version: int | None = Field(default=None, ge=1)

    @field_validator("tags")
    @classmethod
    def validate_tags(cls, tags):
        tags = list(dict.fromkeys(t.strip() for t in tags if t.strip()))
        if any(len(t) > 40 for t in tags):
            raise ValueError("标签最多 40 个字符")
        return tags


def _patch_fields():
    # Omitted fields are allowed; explicitly provided values keep ItemInput's validation.
    fields = {}
    for name, original in ItemInput.model_fields.items():
        field = copy(original)
        field.default = None
        field.default_factory = None
        fields[name] = (original.annotation, field)
    return fields


ItemPatch = create_model("ItemPatch", __base__=ItemInput, **_patch_fields())


class ReviewInput(StrictModel):
    request_id: str = Field(default_factory=lambda: str(uuid4()), min_length=1, max_length=100)
    rating: Literal["again", "hard", "good", "easy"]
    expected_version: int = Field(ge=0)
    duration_ms: int = Field(default=0, ge=0, le=86400000)
    answer_text: str = Field(default="", max_length=30000)
    answer_media: list[str] = Field(default_factory=list, max_length=8)


class ChapterInput(StrictModel):
    subject: Subject
    name: str = Field(min_length=1, max_length=100)


class KeyInput(StrictModel):
    name: str = Field(min_length=1, max_length=80)
    scopes: list[Literal["read", "write", "review"]] = Field(min_length=1, max_length=3)
    expires_days: int | None = Field(default=365, ge=1, le=3650)


class PasswordInput(StrictModel):
    current_password: str = Field(max_length=128)
    new_password: str = Field(min_length=10, max_length=128)
