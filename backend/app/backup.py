import hashlib
import io
import json
import math
import zipfile
from datetime import datetime
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from fastapi.responses import Response
from fsrs import Card
from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import settings
from .database import get_db, utcnow
from .library import item_data, set_attachments, store_image, validate_item
from .models import CardState, Chapter, ImportReceipt, Item, Media, Review, User
from .reviews import state_values
from .schemas import ItemInput
from .security import account_user

router = APIRouter(prefix="/api/v1", tags=["数据备份"])


def finite_number(value):
    number = float(value)
    if not math.isfinite(number):
        raise ValueError("备份包含无效的数值")
    return number


def archive_datetime(value):
    timestamp = datetime.fromisoformat(value)
    if timestamp.tzinfo is None:
        raise ValueError("备份中的时间必须包含时区")
    return timestamp


def archive_card(data):
    card = Card.from_dict(data)
    if card.due.tzinfo is None or (card.last_review and card.last_review.tzinfo is None):
        raise ValueError("记忆状态的时间必须包含时区")
    stability, difficulty = data.get("stability"), data.get("difficulty")
    if stability is not None and not (math.isfinite(stability) and stability > 0):
        raise ValueError("无效的记忆稳定性")
    if difficulty is not None and not (math.isfinite(difficulty) and 1 <= difficulty <= 10):
        raise ValueError("无效的记忆难度")
    if card.last_review and (card.stability is None or card.difficulty is None):
        raise ValueError("已复习内容缺少记忆状态")
    steps = {1: (0, 1), 2: (None,), 3: (0,)}
    if card.step not in steps[int(card.state)]:
        raise ValueError("无效的学习步骤")
    return card


@router.get("/export")
def export_data(user: User = Depends(account_user), db: Session = Depends(get_db)):
    items = db.scalars(select(Item).where(Item.user_id == user.id)).unique().all()
    media = db.scalars(select(Media).where(Media.user_id == user.id)).all()
    reviews = db.scalars(select(Review).where(Review.user_id == user.id)).all()
    data = {"format": "shiyi", "version": 1, "exported_at": utcnow().isoformat(), "preferences": user.preferences,
            "chapters": [{"id": c.id, "subject": c.subject, "name": c.name} for c in
                         db.scalars(select(Chapter).where(Chapter.user_id == user.id))],
            "items": [{**item_data(i), "card_data": i.card.data, "deleted_from": i.deleted_from} for i in items],
            "media": [{"id": m.id, "filename": m.filename, "path": f"media/{m.storage_name}"} for m in media],
            "reviews": [{key: getattr(r, key) for key in ("id", "item_id", "rating", "reviewed_at", "duration_ms", "answer_text",
                        "answer_media", "before", "after", "fsrs_log", "was_new", "undone", "card_version", "retention")} for r in reviews]}
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("manifest.json", json.dumps(data, ensure_ascii=False, default=str))
        for m in media:
            path = settings.data_dir / "media" / m.storage_name
            if not path.is_file():
                raise HTTPException(409, "有图片文件缺失，无法生成完整备份")
            archive.write(path, f"media/{m.storage_name}")
    return Response(output.getvalue(), media_type="application/zip", headers={
        "Content-Disposition": f'attachment; filename="shiyi-{utcnow():%Y%m%d-%H%M%S}.zip"'})


@router.post("/import")
def import_data(file: UploadFile, user: User = Depends(account_user), db: Session = Depends(get_db)):
    blob = file.file.read(100 * 1024 * 1024 + 1)
    if len(blob) > 100 * 1024 * 1024:
        raise HTTPException(413, "备份包请控制在 100 MB 以内")
    archive_id = hashlib.sha256(blob).hexdigest()
    receipt = db.get(ImportReceipt, (user.id, archive_id))
    if receipt:
        return {"imported": receipt.count, "already_imported": True}
    created_files = []
    try:
        with zipfile.ZipFile(io.BytesIO(blob)) as archive:
            infos = archive.infolist()
            if len(infos) > 10001 or sum(i.file_size for i in infos) > 250 * 1024 * 1024:
                raise ValueError("备份解压后过大")
            manifest_info = archive.getinfo("manifest.json")
            if manifest_info.file_size > 40 * 1024 * 1024:
                raise ValueError("备份清单过大")
            data = json.loads(archive.read("manifest.json"), parse_float=finite_number, parse_constant=finite_number)
            if not isinstance(data, dict) or data.get("format") != "shiyi" or data.get("version") != 1:
                raise ValueError("请选择拾忆导出的 ZIP 备份")
            if len(data["items"]) > 20000 or len(data["reviews"]) > 200000:
                raise ValueError("备份记录过多")
            chapters = {}
            for old in data["chapters"]:
                existing = db.scalar(select(Chapter).where(Chapter.user_id == user.id, Chapter.subject == old["subject"], Chapter.name == old["name"]))
                if not existing:
                    if old["subject"] not in ("408", "math", "english") or len(old["name"]) > 100:
                        raise ValueError("无效章节")
                    existing = Chapter(id=str(uuid4()), user_id=user.id, subject=old["subject"], name=old["name"], position=100)
                    db.add(existing)
                    db.flush()
                chapters[old["id"]] = existing.id
            media_map = {}
            for old in data["media"]:
                path = old["path"]
                if not path.startswith("media/") or ".." in path or "\\" in path:
                    raise ValueError("无效图片路径")
                info = archive.getinfo(path)
                if info.file_size > settings.max_upload_mb * 1024 * 1024:
                    raise ValueError("备份中的单张图片过大")
                media = store_image(db, user.id, archive.read(info), old["filename"])
                media_map[old["id"]] = media.id
                created_files.append(settings.data_dir / "media" / media.storage_name)
            db.flush()
            item_map = {}
            for old in data["items"]:
                deleted = old.get("status") == "deleted"
                fields = {key: old[key] for key in ItemInput.model_fields if key in old}
                fields.update(chapter_id=chapters.get(old.get("chapter_id")), external_id=None,
                              status="draft" if deleted else old["status"],
                              question_media=[media_map[m["id"]] for m in old["question_media"]],
                              answer_media=[media_map[m["id"]] for m in old["answer_media"]])
                body = ItemInput.model_validate(fields)
                validate_item(db, user, body)
                item = Item(id=str(uuid4()), user_id=user.id, **body.model_dump(exclude={"question_media", "answer_media", "expected_version"}))
                if deleted:
                    item.status = "deleted"
                    item.deleted_from = old.get("deleted_from") or "draft"
                item.created_at = archive_datetime(old["created_at"])
                item.updated_at = archive_datetime(old["updated_at"])
                item.card = CardState(**state_values(archive_card(old["card_data"])), version=old["schedule"]["version"])
                set_attachments(item, body)
                db.add(item)
                item_map[old["id"]] = item.id
            db.flush()
            for old in data["reviews"]:
                rid = str(uuid4())
                if old["rating"] not in (1, 2, 3, 4) or old["duration_ms"] < 0:
                    raise ValueError("无效复习记录")
                archive_card(old["before"])
                archive_card(old["after"])
                db.add(Review(id=rid, user_id=user.id, item_id=item_map[old["item_id"]], request_id=f"import:{rid}",
                              payload_hash="import", reviewed_at=archive_datetime(old["reviewed_at"]),
                              answer_media=[media_map[mid] for mid in old["answer_media"]],
                              **{key: old[key] for key in ("rating", "duration_ms", "answer_text", "before", "after", "fsrs_log",
                                                         "was_new", "undone", "card_version", "retention")}))
            db.add(ImportReceipt(user_id=user.id, archive_id=archive_id, count=len(item_map)))
            db.commit()
            return {"imported": len(item_map), "already_imported": False}
    except (zipfile.BadZipFile, KeyError, TypeError, ValueError, OverflowError, HTTPException) as exc:
        db.rollback()
        for path in created_files:
            path.unlink(missing_ok=True)
        if isinstance(exc, HTTPException):
            raise
        raise HTTPException(422, "备份校验失败，未导入任何内容：" + str(exc)[:160])
    except Exception:
        db.rollback()
        for path in created_files:
            path.unlink(missing_ok=True)
        raise
