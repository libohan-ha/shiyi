from collections import Counter, defaultdict
from datetime import datetime, timedelta
from math import ceil
from statistics import median
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .database import get_db, utcnow
from .library import item_data
from .models import Item, Review, User
from .reviews import day_bounds
from .security import require

router = APIRouter(prefix="/api/v1", tags=["学习统计"])


def learning_summary(recent, items, start, zone):
    today = start.astimezone(zone).date()
    item_map = {item.id: item for item in items}
    today_ids = set()
    problems = {}
    seen_days = set()
    delayed = []
    latest_delayed = {}
    for review, _ in sorted(recent, key=lambda row: (row[0].reviewed_at, row[0].card_version, row[0].id)):
        day = review.reviewed_at.astimezone(zone).date()
        if day == today:
            today_ids.add(review.item_id)
            if review.independent_completed is not None:
                problems[review.item_id] = review
        if review.reviewed_at < start - timedelta(days=29):
            continue
        key = (review.item_id, day)
        if key in seen_days:
            continue
        seen_days.add(key)
        previous = review.before.get("last_review")
        if review.was_new or not previous:
            continue
        previous_day = datetime.fromisoformat(previous).astimezone(zone).date()
        if previous_day < day:
            delayed.append(review)
            latest_delayed[review.item_id] = (review, (day - previous_day).days)
    covered = [item for item in items if item.id in today_ids and item.source_item_id]
    failures = [(item_map[mid], review, gap) for mid, (review, gap) in latest_delayed.items()
                if review.rating == 1 and mid in item_map and item_map[mid].status == "active"]
    failures.sort(key=lambda value: value[1].reviewed_at, reverse=True)
    results = [(item_map[mid], review) for mid, review in problems.items() if mid in item_map]
    results.sort(key=lambda value: value[1].reviewed_at, reverse=True)
    successes = sum(review.rating > 1 for review in delayed)
    return ({"unique_items": len(today_ids), "weak_points_covered": len(covered)},
            {"delayed_reviews": len(delayed), "delayed_successes": successes,
             "delayed_retention": successes / len(delayed) if delayed else None,
             "delayed_failure_count": len(failures),
             "delayed_failures": [{**item_data(item, include_answer=False), "blocker": review.blocker,
                                   "reviewed_at": review.reviewed_at, "elapsed_days": gap}
                                  for item, review, gap in failures[:10]],
             "covered_weak_points": [item_data(item, include_answer=False) for item in covered[:10]],
             "problems_attempted": len(results),
             "problems_completed": sum(review.independent_completed for _, review in results),
             "problem_results": [{**item_data(item, include_answer=False),
                                  "independent_completed": review.independent_completed, "blocker": review.blocker,
                                  "reviewed_at": review.reviewed_at} for item, review in results[:10]]})


@router.get("/stats")
def stats(user: User = Depends(require("read")), db: Session = Depends(get_db)):
    now = utcnow()
    start, end = day_bounds(user, now)
    zone = ZoneInfo(user.preferences.get("timezone", "Asia/Shanghai"))
    today = now.astimezone(zone).date()
    items = db.scalars(select(Item).where(Item.user_id == user.id, Item.status != "deleted")).unique().all()
    recent = db.execute(select(Review, Item.subject).join(Item).where(
        Review.user_id == user.id, Review.undone.is_(False), Review.reviewed_at >= start - timedelta(days=365),
        Review.reviewed_at <= now)).all()
    today_learning, learning = learning_summary(recent, items, start, zone)
    days = Counter()
    daily_minutes = defaultdict(float)
    subject_reviews = defaultdict(list)
    durations = defaultdict(list)
    ratings = Counter()
    today_count = 0
    today_minutes = 0
    new_done = 0
    for review, subject in recent:
        day = review.reviewed_at.astimezone(zone).date()
        days[day] += 1
        daily_minutes[day] += review.duration_ms / 60000
        if day == today:
            today_count += 1
            today_minutes += review.duration_ms / 60000
            new_done += review.was_new
        if review.reviewed_at >= start - timedelta(days=29):
            subject_reviews[subject].append(review.rating)
            ratings[review.rating] += 1
            if review.duration_ms >= 1000:
                durations[subject].append((review.reviewed_at, review.duration_ms))
    active = [i for i in items if i.status == "active"]
    due_items = [i for i in active if i.card.last_review and i.card.due <= now]
    allowance = max(0, user.preferences.get("daily_new_limit", 15) - new_done)
    new_items = sorted((item for item in active if not item.card.last_review), key=lambda item: (item.created_at, item.id))
    planned = Counter(item.subject for item in [*due_items, *new_items[:allowance]])
    estimates = {"408": 90_000, "math": 180_000, "english": 30_000}
    measured = set()
    for subject, samples in durations.items():
        if len(samples) >= 3:
            estimates[subject] = median(duration for _, duration in sorted(samples, reverse=True)[:30])
            measured.add(subject)
    estimated_minutes = ceil(sum(count * estimates[subject] for subject, count in planned.items()) / 60000)
    subjects = []
    for subject in ("408", "math", "english"):
        cards = [i for i in active if i.subject == subject]
        results = subject_reviews[subject]
        subjects.append({"subject": subject, "total": len([i for i in items if i.subject == subject]),
                         "due": len([i for i in cards if i.card.last_review and i.card.due <= now]),
                         "overdue": len([i for i in cards if i.card.last_review and i.card.due < start]),
                         "new": len([i for i in cards if not i.card.last_review]),
                         "reviewed": len([i for i in cards if i.card.last_review]),
                         "retention": sum(r > 1 for r in results) / len(results) if results else None,
                         "reviews_30d": len(results)})
    forecast = []
    for offset in range(14):
        day = today + timedelta(days=offset)
        counts = {s: 0 for s in ("408", "math", "english")}
        for item in active:
            if item.card.last_review and item.card.due.astimezone(zone).date() == day:
                counts[item.subject] += 1
        forecast.append({"date": day.isoformat(), **counts, "total": sum(counts.values())})
    streak = 0
    day = today if days[today] else today - timedelta(days=1)
    while days[day]:
        streak += 1
        day -= timedelta(days=1)
    all_total = db.scalar(select(func.count()).select_from(Review).where(Review.user_id == user.id, Review.undone.is_(False)))
    total_minutes = db.scalar(select(func.sum(Review.duration_ms)).where(Review.user_id == user.id, Review.undone.is_(False))) or 0
    heatmap_start = today - timedelta(days=84 + today.weekday())
    heatmap = [{"date": (heatmap_start + timedelta(days=offset)).isoformat(),
                "count": days[heatmap_start + timedelta(days=offset)]}
               for offset in range((today - heatmap_start).days + 1)]
    lapses = Counter(r.item_id for r, _ in recent if r.rating == 1 and r.reviewed_at >= start - timedelta(days=29))
    weak = sorted([i for i in active if lapses[i.id]], key=lambda i: -lapses[i.id])[:5]
    return {"learning": learning,
            "today": {**today_learning, "reviews": today_count, "minutes": round(today_minutes, 1), "due": len(due_items),
                       "overdue": sum(i.card.due < start for i in due_items),
                       "new": sum(not i.card.last_review for i in active),
                       "new_available": min(allowance, len(new_items)),
                       "estimated_minutes": estimated_minutes,
                       "estimate_from_history": bool(planned) and all(subject in measured for subject in planned),
                       "later_today": sum(bool(i.card.last_review) and now < i.card.due < end for i in active)},
            "totals": {"items": len(items), "mistakes": sum(i.is_mistake for i in items),
                       "reviews": all_total, "minutes": round(total_minutes / 60000), "streak": streak,
                       "active_days": len(days), "retention": sum(n for r, n in ratings.items() if r > 1) / sum(ratings.values()) if ratings else None},
            "subjects": subjects, "heatmap": heatmap, "forecast": forecast, "ratings": dict(ratings),
            "week": [{"date": (today - timedelta(days=d)).isoformat(), "count": days[today - timedelta(days=d)],
                      "minutes": round(daily_minutes[today - timedelta(days=d)], 1)} for d in range(6, -1, -1)],
            "recent_items": [item_data(i) for i in sorted(items, key=lambda i: i.updated_at, reverse=True)[:4]],
            "weak_items": [{**item_data(i), "lapses": lapses[i.id]} for i in weak], "server_time": now}
