import hashlib
import json
from datetime import UTC, date, datetime, time, timedelta
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
EXAM_WINDOW_DAYS = 10


def day_bounds(user, now=None):
    zone = ZoneInfo(user.preferences.get("timezone", "Asia/Shanghai"))
    local = (now or utcnow()).astimezone(zone)
    start = datetime.combine(local.date(), time.min, zone)
    return start.astimezone(UTC), (start + timedelta(days=1)).astimezone(UTC)


def exam_window(user, now):
    """Local day starts (UTC) in the final days before the exam that can still take a review.

    Returns (exam_start, days) or None when no future exam date is set.
    """
    raw = user.preferences.get("exam_date")
    if not raw:
        return None
    zone = ZoneInfo(user.preferences.get("timezone", "Asia/Shanghai"))
    exam_day = date.fromisoformat(raw) if isinstance(raw, str) else raw
    exam_start = datetime.combine(exam_day, time.min, zone).astimezone(UTC)
    if exam_start <= now:
        return None
    tomorrow = now.astimezone(zone).date() + timedelta(days=1)
    first = max(tomorrow, exam_day - timedelta(days=EXAM_WINDOW_DAYS))
    days = [datetime.combine(first + timedelta(days=n), time.min, zone).astimezone(UTC)
            for n in range((exam_day - first).days)]
    return exam_start, days


def exam_slot(days, card_id):
    """Spread capped cards evenly over the final window, stably per card."""
    digest = hashlib.sha256(str(card_id).encode()).digest()
    return days[int.from_bytes(digest[:4], "big") % len(days)]


def cap_to_exam(user, card, now):
    """Pull a due date that would land on or after the exam back into the final window."""
    window = exam_window(user, now)
    if not window or not window[1] or card.due < window[0]:
        return False
    card.due = exam_slot(window[1], card.card_id)
    return True


def rebalance_exam(db, user, now=None):
    """Move already-scheduled reviews that fall on or after the exam into the final window."""
    now = now or utcnow()
    window = exam_window(user, now)
    if not window or not window[1]:
        return 0
    states = db.scalars(select(CardState).join(Item).where(
        Item.user_id == user.id, CardState.last_review.is_not(None), CardState.due >= window[0])).all()
    for state in states:
        card = Card.from_dict(state.data)
        card.due = exam_slot(window[1], card.card_id)
        state.data, state.due, state.version = card.to_dict(), card.due, state.version + 1
    if states:
        db.commit()
    return len(states)


def scheduler_for(user, subject):
    retention = user.preferences.get("retention", {}).get(subject, .9)
    return Scheduler(desired_retention=retention, enable_fuzzing=True), retention


def schedule_review(scheduler, user, card, rating, now, duration=None):
    card, log = scheduler.review_card(card, rating, review_datetime=now, review_duration=duration)
    next_day = rating in (Rating.Again, Rating.Hard) and card.due - now < timedelta(days=1)
    if next_day:
        card.due = day_bounds(user, now)[1]
    cap_to_exam(user, card, now)
    return card, log, next_day


def state_values(card):
    return {"data": card.to_dict(), "due": card.due, "last_review": card.last_review,
            "stability": card.stability, "difficulty": card.difficulty, "state": int(card.state)}


@router.get("/reviews/due")
def due(subject: Subject | None = None, limit: int = Query(100, ge=1, le=200),
        user: User = Depends(require("read")), db: Session = Depends(get_db)):
    now = utcnow()
    rebalance_exam(db, user, now)
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
        card, _, next_day = schedule_review(scheduler, user, Card.from_dict(item.card.data), Rating(value), now)
        options[name] = {"due": card.due, "interval_seconds": (card.due - now).total_seconds(), "next_day": next_day}
    return {"ratings": options, "version": item.card.version}


def throughput(steps):
    """贯通率: the share of a problem's steps the learner carried through on their own."""
    return sum(bool(step.get("done")) for step in steps) / len(steps) if steps else None


def review_data(review):
    return {"id": review.id, "item_id": review.item_id, "rating": review.rating, "reviewed_at": review.reviewed_at,
            "duration_ms": review.duration_ms, "answer_text": review.answer_text, "answer_media": review.answer_media,
            "undone": review.undone, "due": review.after.get("due"), "was_new": review.was_new,
            "independent_completed": review.independent_completed, "blocker": review.blocker,
            "steps": review.steps or [], "throughput": throughput(review.steps or [])}


@router.post("/items/{item_id}/reviews", status_code=201)
def submit_review(item_id: str, body: ReviewInput, user: User = Depends(require("review")), db: Session = Depends(get_db)):
    payload = {**body.model_dump(), "item_id": item_id}
    # Keep retries of pre-upgrade requests compatible with their stored payload hashes.
    for field in ("expected_item_version", "independent_completed", "blocker", "steps"):
        if payload[field] is None or payload[field] == "" or payload[field] == []:
            del payload[field]
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
    if body.expected_item_version is not None and item.version != body.expected_item_version:
        raise HTTPException(409, "题目内容已更新，请刷新后重新作答")
    steps = [step.model_dump() for step in body.steps]
    missed = [step["text"].strip() for step in steps if not step["done"]]
    blocker = body.blocker
    if steps and body.independent_completed is None:
        raise HTTPException(422, "记录贯通率前，请先选择这次是否独立完成")
    if steps and body.independent_completed and missed:
        raise HTTPException(422, "已独立完成时，所有步骤都应已做出")
    if body.independent_completed is not None:
        if body.independent_completed != (body.rating != "again"):
            raise HTTPException(422, "未独立完成请选择忘记；困难表示独立完成但费力")
        if not body.independent_completed and not blocker:
            if not missed:
                raise HTTPException(422, "请写下这次未完成的主要卡点")
            # The steps that were not carried through are the blocker.
            blocker = "；".join(missed)[:2000]
    if blocker and body.independent_completed is not False:
        raise HTTPException(422, "主要卡点用于记录未独立完成的题目")
    check_media(db, user.id, body.answer_media)
    scheduler, retention = scheduler_for(user, item.subject)
    now = utcnow()
    before = item.card.data
    card, log, _ = schedule_review(scheduler, user, Card.from_dict(before), Rating(RATINGS[body.rating]),
                                   now, body.duration_ms)
    next_version = body.expected_version + 1
    result = db.execute(update(CardState).where(CardState.item_id == item.id,
                        CardState.version == body.expected_version).values(**state_values(card), version=next_version))
    if result.rowcount != 1:
        raise HTTPException(409, "复习状态已更新，请刷新后继续")
    review = Review(id=str(uuid4()), user_id=user.id, item_id=item.id, request_id=body.request_id,
                    payload_hash=payload_hash, rating=RATINGS[body.rating], reviewed_at=now, duration_ms=body.duration_ms,
                    answer_text=body.answer_text, answer_media=body.answer_media, before=before, after=card.to_dict(),
                    fsrs_log=log.to_dict(), was_new=before.get("last_review") is None,
                    card_version=next_version, retention=retention,
                    independent_completed=body.independent_completed, blocker=blocker, steps=steps)
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


@router.get("/items/{item_id}/throughput")
def item_throughput(item_id: str, user: User = Depends(require("read")), db: Session = Depends(get_db)):
    """First and latest 贯通率 of an item, with the latest steps to tick off on the next attempt."""
    item = get_item(db, user.id, item_id)
    # The attempt recorded when the entry was added counts as the first one.
    attempts = [(item.created_at, item.initial_steps)] if item.initial_steps else []
    attempts += [(r.reviewed_at, r.steps) for r in db.scalars(select(Review).where(
        Review.item_id == item_id, Review.user_id == user.id, Review.undone.is_(False)).order_by(
        Review.reviewed_at, Review.card_version)) if r.steps]
    if not attempts:
        return {"attempts": 0, "first": None, "latest": None}
    snapshot = lambda at, steps: {"throughput": throughput(steps), "steps": steps, "reviewed_at": at}
    return {"attempts": len(attempts), "first": snapshot(*attempts[0]), "latest": snapshot(*attempts[-1])}


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
