import hashlib
import secrets
import threading
import time
from collections import defaultdict, deque
from datetime import timedelta

from argon2 import PasswordHasher
from argon2.exceptions import VerificationError
from fastapi import Depends, HTTPException, Request, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import settings
from .database import get_db, utcnow
from .models import APIKey, SessionToken, User

password_hasher = PasswordHasher()
COOKIE = "shiyi_session"
attempts: dict[str, deque] = defaultdict(deque)
attempts_lock = threading.Lock()
bearer = HTTPBearer(scheme_name="APIKey", auto_error=False,
                    description="在网页的「偏好与连接 → API 连接」创建密钥，填入完整的 sy_... 密钥。")


def digest(value: str):
    return hashlib.sha256(value.encode()).hexdigest()


def verify_password(encoded, plain):
    try:
        return password_hasher.verify(encoded, plain)
    except VerificationError:
        return False


def throttle(request: Request):
    key = request.client.host if request.client else "unknown"
    now = time.monotonic()
    with attempts_lock:
        if len(attempts) > 5000:
            stale = [k for k, v in attempts.items() if not v or v[-1] < now - 600]
            for k in stale:
                del attempts[k]
        queue = attempts[key]
        while queue and queue[0] < now - 600:
            queue.popleft()
        if len(queue) >= 15:
            raise HTTPException(429, "尝试次数较多，请 10 分钟后再试")
        queue.append(now)


def check_origin(request: Request):
    if request.method in ("GET", "HEAD", "OPTIONS"):
        return
    origin = request.headers.get("origin")
    allowed = {settings.public_url.rstrip("/")}
    allowed.update(value.strip().rstrip("/") for value in settings.allowed_origins.split(",") if value.strip())
    if not settings.secure_cookies:
        allowed.update({"http://localhost:5173", "http://127.0.0.1:5173", "http://127.0.0.1:4173",
                        "http://localhost:4173", "http://127.0.0.1:8765", "http://localhost:8765"})
    if origin and origin.rstrip("/") not in allowed:
        raise HTTPException(403, "请求来源不受信任")
    if not origin and request.headers.get("sec-fetch-site") == "cross-site":
        raise HTTPException(403, "请求来源不受信任")


def issue_session(db, user, response):
    token = secrets.token_urlsafe(40)
    db.add(SessionToken(token_hash=digest(token), user_id=user.id,
                        expires_at=utcnow() + timedelta(days=settings.session_days)))
    response.set_cookie(COOKIE, token, httponly=True, secure=settings.secure_cookies,
                        samesite="lax", max_age=settings.session_days * 86400, path="/")


def current_user(request: Request, db: Session = Depends(get_db),
                 credentials: HTTPAuthorizationCredentials | None = Security(bearer)) -> User:
    authorization = request.headers.get("authorization", "")
    if authorization:
        if not credentials:
            raise HTTPException(401, "请使用 Bearer API 密钥")
        key = db.scalar(select(APIKey).where(APIKey.token_hash == digest(credentials.credentials)))
        if not key or (key.expires_at and key.expires_at <= utcnow()):
            raise HTTPException(401, "API 密钥无效或已过期")
        request.state.scopes = key.scopes
        request.state.api_key = True
        user = db.get(User, key.user_id)
        return user
    token = request.cookies.get(COOKIE)
    session = db.get(SessionToken, digest(token)) if token else None
    if not session or session.expires_at <= utcnow():
        raise HTTPException(401, "请先登录")
    check_origin(request)
    request.state.scopes = ["read", "write", "review"]
    request.state.api_key = False
    return db.get(User, session.user_id)


def require(scope: str):
    def dependency(request: Request, user: User = Depends(current_user)):
        if scope not in request.state.scopes:
            raise HTTPException(403, f"此密钥缺少 {scope} 权限")
        return user
    return dependency


def account_user(request: Request, user: User = Depends(current_user)):
    if request.state.api_key:
        raise HTTPException(403, "账号与密钥管理需要网页登录")
    return user
