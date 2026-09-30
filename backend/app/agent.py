from datetime import UTC, date, datetime, time, timedelta
from typing import Literal
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .database import get_db, utcnow
from .library import get_item
from .models import Item, Review, User
from .reviews import RATINGS, day_bounds, review_data
from .schemas import Preferences, Subject
from .security import require
from .stats import learning_summary, stats

router = APIRouter(prefix="/api/v1/agent", tags=["Agent 学习上下文"])


@router.get("/context")
def context(request: Request, user: User = Depends(require("read")), db: Session = Depends(get_db)):
    data = stats(user, db)
    preferences = Preferences(**{key: value for key, value in user.preferences.items()
                                 if key in Preferences.model_fields})
    learning = {key: data["learning"][key] for key in (
        "delayed_reviews", "delayed_successes", "delayed_retention", "delayed_failure_count",
        "problems_attempted", "problems_completed")}
    return {"agent_api_version": 1, "study_date": data["forecast"][0]["date"],
            "permissions": [scope for scope in ("read", "write", "review") if scope in request.state.scopes],
            "profile": {"display_name": user.display_name,
                        "preferences": preferences.model_dump(mode="json", exclude={"display_name"})},
            "summary": {**{key: data[key] for key in ("today", "totals", "subjects", "forecast")},
                        "learning": learning},
            "server_time": data["server_time"]}


def review_window(zone, now, date_from, date_to):
    try:
        date_to = date_to or now.astimezone(zone).date()
        date_from = date_from or date_to - timedelta(days=29)
        if not 0 <= (date_to - date_from).days <= 365:
            raise HTTPException(422, "日期须按先后排列，含首尾最多 366 天")
        start = datetime.combine(date_from, time.min, zone).astimezone(UTC)
        end = datetime.combine(date_to + timedelta(days=1), time.min, zone).astimezone(UTC)
    except (OverflowError, ValueError):
        raise HTTPException(422, "日期超出支持范围")
    return date_from, date_to, start, end


@router.get("/reviews")
def reviews(subject: Subject | None = None, item_id: str | None = None,
            rating: Literal["again", "hard", "good", "easy"] | None = None,
            independent_completed: bool | None = None, has_blocker: bool | None = None,
            date_from: date | None = None, date_to: date | None = None,
            include_undone: bool = False, include_deleted: bool = False, include_answers: bool = False,
            page: int = Query(1, ge=1), page_size: int = Query(30, ge=1, le=100),
            user: User = Depends(require("read")), db: Session = Depends(get_db)):
    now = utcnow()
    zone = ZoneInfo(user.preferences.get("timezone", "Asia/Shanghai"))
    date_from, date_to, start, end = review_window(zone, now, date_from, date_to)
    if item_id is not None:
        get_item(db, user.id, item_id)
    stmt = select(Review, Item).join(Item, Review.item_id == Item.id).where(
        Review.user_id == user.id, Item.user_id == user.id,
        Review.reviewed_at >= start, Review.reviewed_at < end, Review.reviewed_at <= now)
    if not include_undone:
        stmt = stmt.where(Review.undone.is_(False))
    if not include_deleted:
        stmt = stmt.where(Item.status != "deleted")
    if subject is not None:
        stmt = stmt.where(Item.subject == subject)
    if item_id is not None:
        stmt = stmt.where(Review.item_id == item_id)
    if rating is not None:
        stmt = stmt.where(Review.rating == RATINGS[rating])
    if independent_completed is not None:
        stmt = stmt.where(Review.independent_completed.is_(independent_completed))
    if has_blocker is not None:
        stmt = stmt.where(Review.blocker != "" if has_blocker else Review.blocker == "")
    total = db.scalar(select(func.count()).select_from(stmt.subquery()))
    rows = db.execute(stmt.order_by(Review.reviewed_at.desc(), Review.id.desc())
                      .offset((page - 1) * page_size).limit(page_size)).all()
    items = []
    for review, item in rows:
        data = review_data(review)
        if not include_answers:
            data.pop("answer_text")
            data.pop("answer_media")
        data["item"] = {key: getattr(item, key) for key in ("id", "title", "subject", "kind", "source_item_id", "status")}
        items.append(data)
    return {"items": items, "total": total, "page": page, "page_size": page_size,
            "has_more": page * page_size < total, "date_from": date_from, "date_to": date_to,
            "timezone": zone.key, "server_time": now}


@router.get("/weaknesses")
def weaknesses(subject: Subject | None = None, days: int = Query(30, ge=1, le=365),
               page: int = Query(1, ge=1), page_size: int = Query(30, ge=1, le=100),
               user: User = Depends(require("read")), db: Session = Depends(get_db)):
    now = utcnow()
    start, _ = day_bounds(user, now)
    zone = ZoneInfo(user.preferences.get("timezone", "Asia/Shanghai"))
    item_stmt = select(Item).where(Item.user_id == user.id, Item.status == "active")
    review_stmt = select(Review, Item.subject).join(Item, Review.item_id == Item.id).where(
        Review.user_id == user.id, Item.user_id == user.id, Item.status == "active",
        Review.undone.is_(False), Review.reviewed_at <= now,
        Review.reviewed_at >= start - timedelta(days=days - 1))
    if subject is not None:
        item_stmt = item_stmt.where(Item.subject == subject)
        review_stmt = review_stmt.where(Item.subject == subject)
    items = db.scalars(item_stmt).unique().all()
    recent = db.execute(review_stmt).all()
    _, learning = learning_summary(recent, items, start, zone, days=days, limit=None)
    failures = sorted(learning["delayed_failures"], key=lambda row: (row["reviewed_at"], row["id"]), reverse=True)
    total = len(failures)
    rows = failures[(page - 1) * page_size:page * page_size]
    return {"items": [{key: row[key] for key in (
                "id", "title", "subject", "kind", "status", "source_item_id", "schedule", "blocker",
                "reviewed_at", "elapsed_days")} for row in rows],
            "total": total, "page": page, "page_size": page_size, "has_more": page * page_size < total,
            "days": days, "timezone": zone.key, "server_time": now}
