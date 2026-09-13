import secrets
from datetime import timedelta
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .config import settings
from .database import get_db, utcnow
from .models import APIKey, Chapter, SessionToken, User
from .schemas import Credentials, KeyInput, Login, PasswordInput, Preferences
from .security import (
    COOKIE,
    account_user,
    check_origin,
    current_user,
    digest,
    issue_session,
    password_hasher,
    throttle,
    verify_password,
)

router = APIRouter(prefix="/api/v1", tags=["账号与设置"])
DEFAULT_CHAPTERS = {
    "408": ["数据结构", "计算机组成原理", "操作系统", "计算机网络"],
    "math": ["高等数学", "线性代数", "概率论与数理统计"],
    "english": ["单词", "短语", "长难句", "语法", "阅读理解", "写作表达"],
}


def user_data(user):
    return {"id": user.id, "username": user.username, "display_name": user.display_name,
            "preferences": Preferences(**{**user.preferences, "display_name": user.display_name}).model_dump(mode="json")}


@router.get("/auth/status")
def auth_status(db: Session = Depends(get_db)):
    has_users = bool(db.scalar(select(func.count()).select_from(User)))
    return {"initialized": has_users, "registration_open": settings.allow_registration or not has_users}


@router.post("/auth/register", status_code=201)
def register(body: Credentials, request: Request, response: Response, db: Session = Depends(get_db)):
    check_origin(request)
    throttle(request)
    # Serialize first-owner setup across concurrent requests and server workers.
    if db.bind.dialect.name == "postgresql":
        from sqlalchemy import text
        db.execute(text("SELECT pg_advisory_xact_lock(748192501)"))
    else:
        from sqlalchemy import text
        db.execute(text("BEGIN IMMEDIATE"))
    if not settings.allow_registration and db.scalar(select(func.count()).select_from(User)):
        raise HTTPException(403, "这是私人学习空间，注册已关闭")
    user = User(id=str(uuid4()), username=body.username.lower(), display_name=body.display_name,
                password_hash=password_hasher.hash(body.password), preferences=Preferences().model_dump(mode="json"))
    db.add(user)
    db.flush()
    for subject, names in DEFAULT_CHAPTERS.items():
        for position, name in enumerate(names):
            db.add(Chapter(id=str(uuid4()), user_id=user.id, subject=subject, name=name, position=position))
    issue_session(db, user, response)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "用户名已存在")
    return user_data(user)


@router.post("/auth/login")
def login(body: Login, request: Request, response: Response, db: Session = Depends(get_db)):
    check_origin(request)
    throttle(request)
    user = db.scalar(select(User).where(User.username == body.username.lower()))
    if not user or not verify_password(user.password_hash, body.password):
        raise HTTPException(401, "用户名或密码不正确")
    issue_session(db, user, response)
    db.execute(delete(SessionToken).where(SessionToken.expires_at < utcnow()))
    db.commit()
    return user_data(user)


@router.post("/auth/logout", status_code=204)
def logout(request: Request, response: Response, user: User = Depends(account_user), db: Session = Depends(get_db)):
    token = request.cookies.get(COOKIE)
    if token:
        db.execute(delete(SessionToken).where(SessionToken.token_hash == digest(token)))
        db.commit()
    response.delete_cookie(COOKIE, path="/")


@router.get("/auth/me")
def me(user: User = Depends(current_user)):
    return user_data(user)


@router.put("/preferences")
def save_preferences(body: Preferences, user: User = Depends(account_user), db: Session = Depends(get_db)):
    user.preferences = body.model_dump(mode="json", exclude={"display_name"})
    user.display_name = body.display_name
    db.commit()
    return user_data(user)


@router.post("/auth/password", status_code=204)
def change_password(body: PasswordInput, response: Response,
                    user: User = Depends(account_user), db: Session = Depends(get_db)):
    if not verify_password(user.password_hash, body.current_password):
        raise HTTPException(400, "原密码不正确")
    user.password_hash = password_hasher.hash(body.new_password)
    db.execute(delete(SessionToken).where(SessionToken.user_id == user.id))
    issue_session(db, user, response)
    db.commit()


@router.get("/keys")
def keys(user: User = Depends(account_user), db: Session = Depends(get_db)):
    return [{"id": k.id, "name": k.name, "prefix": k.prefix, "scopes": k.scopes,
             "created_at": k.created_at, "expires_at": k.expires_at} for k in
            db.scalars(select(APIKey).where(APIKey.user_id == user.id).order_by(APIKey.created_at.desc()))]


@router.post("/keys", status_code=201)
def create_key(body: KeyInput, user: User = Depends(account_user), db: Session = Depends(get_db)):
    token = "sy_" + secrets.token_urlsafe(36)
    key = APIKey(id=str(uuid4()), user_id=user.id, name=body.name, scopes=list(set(body.scopes)),
                 prefix=token[:10], token_hash=digest(token),
                 expires_at=utcnow() + timedelta(days=body.expires_days) if body.expires_days else None)
    db.add(key)
    db.commit()
    return {"id": key.id, "token": token, "name": key.name, "scopes": key.scopes}


@router.delete("/keys/{key_id}", status_code=204)
def revoke_key(key_id: str, user: User = Depends(account_user), db: Session = Depends(get_db)):
    key = db.scalar(select(APIKey).where(APIKey.id == key_id, APIKey.user_id == user.id))
    if not key:
        raise HTTPException(404, "密钥不存在")
    db.delete(key)
    db.commit()
