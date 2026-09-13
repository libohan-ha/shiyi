import hashlib
import json
from datetime import UTC, datetime, time, timedelta
from uuid import uuid4
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query
from fsrs import Card, Rating, Scheduler
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .database import get_db, utcnow
from .library import check_media, get_item, item_data
from .models import CardState, Item, Review, User
from .schemas import ReviewInput, Subject
from .security import require

router = APIRouter(prefix="/api/v1", tags=["FSRS 复习"])
RATINGS = {"again": 1, "hard": 2, "good": 3, "easy": 4}


def day_bounds(user, now=None):
    zone = ZoneInfo(user.preferences.get("timezone", "Asia/Shanghai"))
    local = (now or utcnow()).astimezone(zone)
    start = datetime.combine(local.date(), time.min, zone)
    return start.astimezone(UTC), (start + timedelta(days=1)).astimezone(UTC)


def scheduler_for(user, subject):
    retention = user.preferences.get("retention", {}).get(subject, .9)
    return Scheduler(desired_retention=retention, enable_fuzzing=False), retention


def state_values(card):
    return {"data": card.to_dict(), "due": card.due, "last_review": card.last_review,
            "stability": card.stability, "difficulty": card.difficulty, "state": int(card.state)}


@router.get("/reviews/due")
def due(subject: Subject | None = None, limit: int = Query(100, ge=1, le=200),
        user: User = Depends(require("read")), db: Session = Depends(get_db)):
    now = utcnow()
    start, end = day_bounds(user, now)
    stmt = select(Item).join(CardState).where(Item.user_id == user.id, Item.status == "active")
    if subject:
        stmt = stmt.where(Item.subject == subject)
    due_stmt = stmt.where(CardState.last_review.is_not(None), CardState.due <= now)
    due_total = db.scalar(select(func.count()).select_from(due_stmt.subquery()))
    reviewed = db.scalars(due_stmt.order_by(CardState.due, Item.id).limit(limit)).unique().all()
    new_done = db.scalar(select(func.count()).select_from(Review).where(
        Review.user_id == user.id, Review.was_new.is_(True), Review.undone.is_(False),
        Review.reviewed_at >= start, Review.reviewed_at < end))
    allowance = max(0, user.preferences.get("daily_new_limit", 15) - new_done)
    new_stmt = stmt.where(CardState.last_review.is_(None))
    new_total = db.scalar(select(func.count()).select_from(new_stmt.subquery()))
    new = db.scalars(new_stmt.order_by(Item.created_at, Item.id).limit(min(max(0, limit - len(reviewed)), allowance))).unique().all()
    next_stmt = select(func.min(CardState.due)).join(Item).where(
        Item.user_id == user.id, Item.status == "active", CardState.last_review.is_not(None), CardState.due > now)
    if subject:
        next_stmt = next_stmt.where(Item.subject == subject)
    return {"items": [item_data(i, include_answer=False) for i in [*reviewed, *new]],
            "due_count": due_total, "new_count": new_total, "new_available": min(allowance, new_total),
            "next_due": db.scalar(next_stmt), "server_time": now}


@router.get("/items/{item_id}/preview")
def preview(item_id: str, user: User = Depends(require("read")), db: Session = Depends(get_db)):
    item = get_item(db, user.id, item_id)
    scheduler, _ = scheduler_for(user, item.subject)
    now = utcnow()
    options = {}
    for name, value in RATINGS.items():
        card, _ = scheduler.review_card(Card.from_dict(item.card.data), Rating(value), review_datetime=now)
        options[name] = {"due": card.due, "interval_seconds": (card.due - now).total_seconds()}
    return {"ratings": options, "version": item.card.version}


def review_data(review):
    return {"id": review.id, "item_id": review.item_id, "rating": review.rating, "reviewed_at": review.reviewed_at,
            "duration_ms": review.duration_ms, "answer_text": review.answer_text, "answer_media": review.answer_media,
            "undone": review.undone, "due": review.after.get("due"), "was_new": review.was_new}


@router.post("/items/{item_id}/reviews", status_code=201)
def submit_review(item_id: str, body: ReviewInput, user: User = Depends(require("review")), db: Session = Depends(get_db)):
    payload = {**body.model_dump(), "item_id": item_id}
    payload_hash = hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    existing = db.scalar(select(Review).where(Review.user_id == user.id, Review.request_id == body.request_id))
    if existing:
        if existing.payload_hash != payload_hash:
            raise HTTPException(409, "此请求 ID 已用于不同的复习提交")
        return {"already_recorded": True, "review": review_data(existing)}
    item = get_item(db, user.id, item_id, lock=True)
    # A concurrent retry may have committed while this request was waiting for the item lock.
    existing = db.scalar(select(Review).where(Review.user_id == user.id, Review.request_id == body.request_id))
    if existing:
        if existing.payload_hash != payload_hash:
            raise HTTPException(409, "此请求 ID 已用于不同的复习提交")
        return {"already_recorded": True, "review": review_data(existing)}
    if item.status != "active":
        raise HTTPException(409, "这条内容当前未加入复习")
    if item.card.version != body.expected_version:
        raise HTTPException(409, "这道题已在其他窗口复习，请刷新后继续")
    check_media(db, user.id, body.answer_media)
    scheduler, retention = scheduler_for(user, item.subject)
    now = utcnow()
    before = item.card.data
    card, log = scheduler.review_card(Card.from_dict(before), Rating(RATINGS[body.rating]),
                                      review_datetime=now, review_duration=body.duration_ms)
    next_version = body.expected_version + 1
    result = db.execute(update(CardState).where(CardState.item_id == item.id,
                        CardState.version == body.expected_version).values(**state_values(card), version=next_version))
    if result.rowcount != 1:
        raise HTTPException(409, "复习状态已更新，请刷新后继续")
    review = Review(id=str(uuid4()), user_id=user.id, item_id=item.id, request_id=body.request_id,
                    payload_hash=payload_hash, rating=RATINGS[body.rating], reviewed_at=now, duration_ms=body.duration_ms,
                    answer_text=body.answer_text, answer_media=body.answer_media, before=before, after=card.to_dict(),
                    fsrs_log=log.to_dict(), was_new=before.get("last_review") is None,
                    card_version=next_version, retention=retention)
    db.add(review)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        existing = db.scalar(select(Review).where(Review.user_id == user.id, Review.request_id == body.request_id))
        if existing and existing.payload_hash == payload_hash:
            return {"already_recorded": True, "review": review_data(existing)}
        raise HTTPException(409, "复习提交冲突，请刷新后重试")
    return {"already_recorded": False, "review": review_data(review)}


@router.get("/items/{item_id}/reviews")
def history(item_id: str, page: int = Query(1, ge=1), user: User = Depends(require("read")), db: Session = Depends(get_db)):
    get_item(db, user.id, item_id)
    stmt = select(Review).where(Review.item_id == item_id, Review.user_id == user.id)
    total = db.scalar(select(func.count()).select_from(stmt.subquery()))
    return {"items": [review_data(r) for r in db.scalars(stmt.order_by(Review.reviewed_at.desc()).offset((page - 1) * 30).limit(30))],
            "total": total, "page": page}


@router.post("/reviews/{review_id}/undo")
def undo(review_id: str, user: User = Depends(require("review")), db: Session = Depends(get_db)):
    review = db.scalar(select(Review).where(Review.id == review_id, Review.user_id == user.id).with_for_update())
    if not review:
        raise HTTPException(404, "复习记录不存在")
    if review.undone:
        return {"undone": True}
    if utcnow() - review.reviewed_at > timedelta(minutes=10):
        raise HTTPException(409, "仅支持撤销 10 分钟内的最近一次评分")
    item = get_item(db, user.id, review.item_id, lock=True)
    if item.status != "active":
        raise HTTPException(409, "请先恢复这条内容，再撤销评分")
    result = db.execute(update(CardState).where(CardState.item_id == review.item_id,
                        CardState.version == review.card_version).values(
                        **state_values(Card.from_dict(review.before)), version=review.card_version + 1))
    if result.rowcount != 1:
        raise HTTPException(409, "这道题有新的复习记录，无法撤销旧评分")
    review.undone = True
    db.commit()
    return {"undone": True}
