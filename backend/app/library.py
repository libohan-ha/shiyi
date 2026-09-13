import io
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from fsrs import Card, Scheduler
from PIL import Image, ImageOps, UnidentifiedImageError
from pydantic import ValidationError
from sqlalchemy import func, or_, select, update
from sqlalchemy.orm import Session

from .config import settings
from .database import get_db, lock_sqlite_writer, utcnow
from .models import CardState, Chapter, Item, ItemMedia, Media, User
from .schemas import ChapterInput, Difficulty, ItemInput, ItemKind, ItemPatch, Subject
from .security import require

router = APIRouter(prefix="/api/v1", tags=["知识与图片"])


def get_item(db, user_id, item_id, lock=False):
    if lock:
        lock_sqlite_writer(db)
    stmt = select(Item).where(Item.id == item_id, Item.user_id == user_id)
    if lock:
        stmt = stmt.with_for_update()
    item = db.scalar(stmt)
    if not item:
        raise HTTPException(404, "内容不存在")
    return item


def media_data(media):
    return {"id": media.id, "url": f"/api/v1/media/{media.id}", "filename": media.filename,
            "width": media.width, "height": media.height, "size": media.size, "mime_type": media.mime_type}


def item_data(item, include_answer=True):
    card = item.card
    data = {key: getattr(item, key) for key in (
        "id", "title", "subject", "chapter_id", "kind", "question", "difficulty", "tags", "source",
        "is_mistake", "status", "external_id", "version", "created_at", "updated_at")}
    data["question_media"] = [media_data(a.media) for a in sorted(item.attachments, key=lambda a: a.position) if a.role == "question"]
    if include_answer:
        data.update(answer=item.answer, mistake_reason=item.mistake_reason, takeaway=item.takeaway)
        data["answer_media"] = [media_data(a.media) for a in sorted(item.attachments, key=lambda a: a.position) if a.role == "answer"]
    data["schedule"] = {"due": card.due, "last_review": card.last_review, "stability": card.stability,
                        "difficulty": card.difficulty, "state": "new" if not card.last_review else
                        {1: "learning", 2: "review", 3: "relearning"}[card.state], "version": card.version,
                        "retrievability": Scheduler().get_card_retrievability(Card.from_dict(card.data)) if card.last_review else None}
    return data


def check_media(db, user_id, ids):
    if not ids:
        return
    if len(set(ids)) != len(ids):
        raise HTTPException(422, "同一区域不能重复添加同一图片")
    count = db.scalar(select(func.count()).select_from(Media).where(Media.id.in_(ids), Media.user_id == user_id))
    if count != len(ids):
        raise HTTPException(422, "图片不存在或不属于当前账号")


def validate_item(db, user, body):
    if body.chapter_id:
        chapter = db.get(Chapter, body.chapter_id)
        if not chapter or chapter.user_id != user.id or chapter.subject != body.subject:
            raise HTTPException(422, "章节与科目不匹配")
    check_media(db, user.id, body.question_media)
    check_media(db, user.id, body.answer_media)
    if body.status != "draft":
        if not body.question and not body.question_media:
            raise HTTPException(422, "加入复习前，请填写问题或上传题图")
        if not body.answer and not body.answer_media:
            raise HTTPException(422, "加入复习前，请补充答案、判定标准或答案图；也可以先保存草稿")


def set_attachments(item, body):
    item.attachments = [ItemMedia(media_id=mid, role=role, position=pos) for role in ("question", "answer")
                        for pos, mid in enumerate(getattr(body, f"{role}_media"))]


@router.get("/chapters")
def chapters(user: User = Depends(require("read")), db: Session = Depends(get_db)):
    return [{"id": c.id, "subject": c.subject, "name": c.name, "position": c.position} for c in
            db.scalars(select(Chapter).where(Chapter.user_id == user.id).order_by(Chapter.position, Chapter.name))]


@router.post("/chapters", status_code=201)
def create_chapter(body: ChapterInput, user: User = Depends(require("write")), db: Session = Depends(get_db)):
    chapter = Chapter(id=str(uuid4()), user_id=user.id, **body.model_dump(), position=100)
    db.add(chapter)
    db.commit()
    return {"id": chapter.id, "subject": chapter.subject, "name": chapter.name, "position": chapter.position}


@router.patch("/chapters/{chapter_id}")
def edit_chapter(chapter_id: str, body: ChapterInput, user: User = Depends(require("write")), db: Session = Depends(get_db)):
    chapter = db.get(Chapter, chapter_id)
    if not chapter or chapter.user_id != user.id:
        raise HTTPException(404, "章节不存在")
    if chapter.subject != body.subject:
        raise HTTPException(422, "章节不能跨科目移动")
    chapter.name = body.name
    db.commit()
    return {"id": chapter.id, "subject": chapter.subject, "name": chapter.name, "position": chapter.position}


@router.delete("/chapters/{chapter_id}", status_code=204)
def remove_chapter(chapter_id: str, user: User = Depends(require("write")), db: Session = Depends(get_db)):
    chapter = db.get(Chapter, chapter_id)
    if not chapter or chapter.user_id != user.id:
        raise HTTPException(404, "章节不存在")
    db.delete(chapter)
    db.commit()


def tag_match(db, value, exact=False):
    # Query decoded JSON values so Chinese, quotes and wildcard characters work on both databases.
    if db.bind.dialect.name == "postgresql":
        entries = func.json_array_elements_text(Item.tags).table_valued("value").render_derived(name="item_tags")
    else:
        entries = func.json_each(Item.tags).table_valued("key", "value").alias("item_tags")
    condition = entries.c.value == value if exact else entries.c.value.ilike(value, escape="\\")
    return select(1).select_from(entries).where(condition).correlate(Item).exists()


@router.get("/items")
def list_items(subject: Subject | None = None, q: str = Query("", max_length=200), chapter_id: str | None = None,
               tag: str | None = Query(None, max_length=40), is_mistake: bool | None = None,
               difficulty: Difficulty | None = None, kind: ItemKind | None = None,
               external_id: str | None = Query(None, max_length=200), status: str = "all", state: str | None = None,
               sort: str = "updated", page: int = Query(1, ge=1), page_size: int = Query(24, ge=1, le=100),
               user: User = Depends(require("read")), db: Session = Depends(get_db)):
    stmt = select(Item).join(CardState).where(Item.user_id == user.id)
    if status == "all":
        stmt = stmt.where(Item.status != "deleted")
    elif status in ("active", "draft", "suspended", "deleted"):
        stmt = stmt.where(Item.status == status)
    else:
        raise HTTPException(422, "无效的内容状态")
    if subject:
        stmt = stmt.where(Item.subject == subject)
    if chapter_id:
        stmt = stmt.where(Item.chapter_id == chapter_id)
    if is_mistake is not None:
        stmt = stmt.where(Item.is_mistake == is_mistake)
    if difficulty:
        stmt = stmt.where(Item.difficulty == difficulty)
    if kind:
        stmt = stmt.where(Item.kind == kind)
    if external_id is not None:
        stmt = stmt.where(Item.external_id == external_id)
    if q:
        pattern = "%" + q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
        stmt = stmt.where(or_(tag_match(db, pattern), *[col.ilike(pattern, escape="\\") for col in
                               (Item.title, Item.question, Item.answer, Item.mistake_reason, Item.takeaway, Item.source)]))
    if tag:
        stmt = stmt.where(tag_match(db, tag, exact=True))
    if state == "new":
        stmt = stmt.where(CardState.last_review.is_(None), Item.status == "active")
    elif state == "due":
        stmt = stmt.where(CardState.due <= utcnow(), CardState.last_review.is_not(None), Item.status == "active")
    elif state in ("learning", "review", "relearning"):
        stmt = stmt.where(CardState.state == {"learning": 1, "review": 2, "relearning": 3}[state], CardState.last_review.is_not(None))
    elif state:
        raise HTTPException(422, "无效的复习状态")
    total = db.scalar(select(func.count()).select_from(stmt.subquery()))
    order = {"updated": Item.updated_at.desc(), "created": Item.created_at.desc(), "due": CardState.due.asc(), "title": Item.title.asc()}
    if sort not in order:
        raise HTTPException(422, "无效的排序方式")
    records = db.scalars(stmt.order_by(order[sort], Item.id).offset((page - 1) * page_size).limit(page_size)).unique().all()
    return {"items": [item_data(i) for i in records], "total": total, "page": page, "page_size": page_size}


@router.post("/items", status_code=201)
def create_item(body: ItemInput, user: User = Depends(require("write")), db: Session = Depends(get_db)):
    validate_item(db, user, body)
    item = Item(id=str(uuid4()), user_id=user.id, **body.model_dump(exclude={"question_media", "answer_media", "expected_version"}))
    card = Card(card_id=uuid4().int % (2 ** 53))
    item.card = CardState(data=card.to_dict(), due=card.due, state=card.state)
    set_attachments(item, body)
    db.add(item)
    db.commit()
    db.refresh(item)
    return item_data(item)


@router.get("/items/{item_id}")
def detail(item_id: str, user: User = Depends(require("read")), db: Session = Depends(get_db)):
    return item_data(get_item(db, user.id, item_id))


@router.patch("/items/{item_id}")
def edit_item(item_id: str, body: ItemPatch, user: User = Depends(require("write")), db: Session = Depends(get_db)):
    item = get_item(db, user.id, item_id, lock=True)
    if item.status == "deleted":
        raise HTTPException(409, "请先从回收站恢复内容")
    original = {key: getattr(item, key) for key in ItemInput.model_fields if hasattr(item, key)}
    original.update({f"{role}_media": [a.media_id for a in sorted(item.attachments, key=lambda a: a.position) if a.role == role]
                     for role in ("question", "answer")})
    try:
        data = ItemInput.model_validate({**original, **body.model_dump(exclude_unset=True)})
    except ValidationError as error:
        raise HTTPException(422, str(error))
    validate_item(db, user, data)
    expected = data.expected_version if data.expected_version is not None else item.version
    result = db.execute(update(Item).where(Item.id == item.id, Item.version == expected).values(version=expected + 1))
    if result.rowcount != 1:
        raise HTTPException(409, "内容已在其他窗口更新，请刷新后重试")
    for key, value in data.model_dump(exclude={"question_media", "answer_media", "expected_version"}).items():
        setattr(item, key, value)
    item.attachments.clear()
    db.flush()
    set_attachments(item, data)
    db.commit()
    db.refresh(item)
    return item_data(item)


@router.delete("/items/{item_id}", status_code=204)
def delete_item(item_id: str, user: User = Depends(require("write")), db: Session = Depends(get_db)):
    item = get_item(db, user.id, item_id, lock=True)
    if item.status != "deleted":
        item.deleted_from = item.status
        item.status = "deleted"
        item.version += 1
        db.commit()


@router.post("/items/{item_id}/restore")
def restore_item(item_id: str, user: User = Depends(require("write")), db: Session = Depends(get_db)):
    item = get_item(db, user.id, item_id, lock=True)
    if item.status == "deleted":
        item.status = item.deleted_from or "active"
        item.deleted_from = None
        item.version += 1
        db.commit()
    return item_data(item)


def store_image(db, user_id, content: bytes, filename: str):
    if len(content) > settings.max_upload_mb * 1024 * 1024:
        raise HTTPException(413, f"单张图片请控制在 {settings.max_upload_mb} MB 以内")
    try:
        with Image.open(io.BytesIO(content)) as source:
            if source.format not in ("JPEG", "PNG", "WEBP", "GIF") or source.width * source.height > 32_000_000:
                raise ValueError("unsupported image")
            image = ImageOps.exif_transpose(source)
            image.load()
            image = image.convert("RGBA" if "A" in image.getbands() or "transparency" in image.info else "RGB")
            buffer = io.BytesIO()
            image.save(buffer, "WEBP", quality=95, lossless=source.format in ("PNG", "GIF", "WEBP"), method=4)
            encoded = buffer.getvalue()
            width, height = image.size
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError):
        raise HTTPException(422, "请上传有效的 JPG、PNG、WebP 或 GIF 图片（不超过 3200 万像素）")
    mid = str(uuid4())
    media = Media(id=mid, user_id=user_id, filename=filename[:250], storage_name=f"{mid}.webp",
                  mime_type="image/webp", size=len(encoded), width=width, height=height)
    path = settings.data_dir / "media" / media.storage_name
    path.write_bytes(encoded)
    db.info.setdefault("new_media_files", []).append(path)
    db.add(media)
    return media


@router.post("/media", status_code=201)
def upload_media(file: UploadFile, user: User = Depends(require("write")), db: Session = Depends(get_db)):
    content = file.file.read(settings.max_upload_mb * 1024 * 1024 + 1)
    media = store_image(db, user.id, content, file.filename or "图片")
    db.commit()
    return media_data(media)


@router.get("/media/{media_id}")
def read_media(media_id: str, user: User = Depends(require("read")), db: Session = Depends(get_db)):
    media = db.get(Media, media_id)
    if not media or media.user_id != user.id:
        raise HTTPException(404, "图片不存在")
    path = settings.data_dir / "media" / media.storage_name
    if not path.is_file():
        raise HTTPException(404, "图片文件缺失，请从备份恢复")
    return FileResponse(path, media_type=media.mime_type,
                        headers={"Cache-Control": "private, no-cache", "X-Content-Type-Options": "nosniff"})
