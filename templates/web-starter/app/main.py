"""로그인 있는 웹 서비스 뼈대: 구성원(member)·운영자(admin) 2역할, 가입 규칙, 아이디 저장, 비밀번호 찾기·재설정, 실패 잠금.
흐름: 화면(static/*.html) → fetch(/api/...) → 입력 검증(이 파일) → 규칙(policy.py)·해시(security.py) → 저장(store.py, SQLite) → JSON 응답 → 화면.
인증: 로그인하면 서버가 무작위 세션 ID를 HttpOnly 쿠키로 준다. DB에는 그 ID의 해시만 저장하고, 요청마다 쿠키 → 세션 → 사용자 → 역할(DB)을 다시 읽는다.
실행(전용 터미널, 끄지 않는다): python seed.py --demo  →  uvicorn app.main:app --host 0.0.0.0 --port 8000   ← web-starter 폴더에서
테스트: python -m app.security  /  python -m pytest -q tests   (TestClient는 httpx 필요)
과제 기능은 맨 아래 '과제 기능' 자리에 라우트를 붙이고 Depends(require_user) 또는 Depends(require_role("admin"))를 건다.
"""
import logging
import os
import secrets
import sqlite3
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, FastAPI, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from app import policy, security
from app.store import DB, DEMO, connect, create_user, end_sessions, get_db, init_db, send_mail, start_session, to_outbox

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("app")
BASE_URL = os.getenv("PUBLIC_BASE_URL", "http://localhost:8000")  # 재설정 링크 주소. 요청 Host 헤더를 믿지 않는다
login_fail = security.Throttle(policy.LOCK_MAX, policy.LOCK_WINDOW)
forgot_hits = security.Throttle(policy.FORGOT_MAX, policy.LOCK_WINDOW)
SAME_ANSWER = {"message": "입력한 정보가 등록된 정보와 일치하면 재설정 안내를 보냈습니다."}


# ---------- 인증 의존성 ----------
def current_user(request: Request, db: sqlite3.Connection = Depends(get_db)):
    sid = request.cookies.get("sid")
    row = sid and db.execute("""SELECT s.sid_hash, s.created, s.last_seen, u.id, u.username, u.name, u.role, u.must_change
        FROM sessions s JOIN users u ON u.id = s.user_id WHERE s.sid_hash = ?""", (security.token_hash(sid),)).fetchone()
    now = time.time()
    if not row or now - row["last_seen"] > policy.SESSION_IDLE or now - row["created"] > policy.SESSION_ABS:
        raise HTTPException(401, "로그인이 필요합니다")
    with db:
        db.execute("UPDATE sessions SET last_seen=? WHERE sid_hash=?", (now, row["sid_hash"]))
    user = dict(row)
    user["expires_in"] = int(min(policy.SESSION_IDLE, policy.SESSION_ABS - (now - row["created"])))
    return user


def require_user(user=Depends(current_user)):
    if user["must_change"]:  # 임시 비밀번호로 들어온 사람은 비밀번호부터 바꾼다
        raise HTTPException(403, "비밀번호를 먼저 바꿔야 합니다")
    return user


def require_role(*roles):
    def check(user=Depends(require_user)):
        if user["role"] not in roles:
            raise HTTPException(403, "권한이 없습니다")
        return user
    return check


def field_error(field, msgs):
    # FastAPI 기본 422와 같은 모양(detail: [{loc, msg}]) → 화면이 칸별로 오류를 붙인다
    raise HTTPException(422, [{"loc": ["body", field], "msg": m, "type": "policy"} for m in msgs])


# ---------- 입력 모양 ----------
class SignupIn(BaseModel):
    username: str = Field(min_length=1, max_length=40)
    name: str = Field(min_length=1, max_length=policy.NAME_MAX)
    email: str = Field(default="", max_length=120, pattern=r"^$|^[^@\s]+@[^@\s]+\.[^@\s]+$")
    password: str = Field(min_length=1, max_length=policy.PW_MAX + 1)  # 길이 규칙 위반은 policy 문구로 알려 준다


class LoginIn(BaseModel):
    username: str = Field(min_length=1, max_length=40)
    password: str = Field(min_length=1, max_length=policy.PW_MAX + 1)


class ForgotIn(BaseModel):
    username: str = Field(min_length=1, max_length=40)
    email: str = Field(min_length=3, max_length=120)


class ResetIn(BaseModel):
    token: str = Field(min_length=20, max_length=100)
    password: str = Field(min_length=1, max_length=policy.PW_MAX + 1)


class PasswordIn(BaseModel):
    current: str = Field(min_length=1, max_length=policy.PW_MAX + 1)
    new: str = Field(min_length=1, max_length=policy.PW_MAX + 1)


def public(u):
    return {"id": u["id"], "username": u["username"], "name": u["name"], "role": u["role"],
            "role_label": policy.ROLES.get(u["role"], u["role"]), "must_change": bool(u["must_change"])}


# ---------- /api/auth ----------
auth = APIRouter(prefix="/api/auth", tags=["auth"])


@auth.get("/policy")
def get_policy():
    return {"username_pattern": policy.USERNAME_RE.pattern, "username_hint": policy.USERNAME_HINT,
            "pw_min": policy.PW_MIN, "pw_max": policy.PW_MAX, "require": list(policy.REQUIRE), "version": policy.VERSION}


@auth.get("/check-username")
def check_username(username: str, db: sqlite3.Connection = Depends(get_db)):
    reasons = security.check_username(username.lower())
    taken = db.execute("SELECT 1 FROM users WHERE username=?", (username.lower(),)).fetchone() is not None
    return {"available": not reasons and not taken, "reasons": reasons + (["이미 쓰는 아이디"] if taken else [])}


@auth.post("/signup", status_code=201)
def signup(body: SignupIn, response: Response, db: sqlite3.Connection = Depends(get_db)):
    username = body.username.strip().lower()
    if why := security.check_username(username):
        field_error("username", why)
    if why := security.check_password(body.password, username):
        field_error("password", why)
    try:
        uid = create_user(db, username, body.name.strip(), body.password, email=body.email or None)  # 역할 칸은 받지 않는다: 항상 member
    except sqlite3.IntegrityError:
        raise HTTPException(409, "이미 쓰는 아이디입니다")
    start_session(db, response, uid)
    return public(db.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone())


@auth.post("/login")
def login(body: LoginIn, response: Response, db: sqlite3.Connection = Depends(get_db)):
    username = body.username.strip().lower()
    if wait := login_fail.take(username):  # 확인과 시도 기록을 한 번에(동시 요청이 잠금을 빠져나가지 않게)
        raise HTTPException(429, f"로그인을 {policy.LOCK_MAX}번 실패해 잠겼습니다. {wait // 60 + 1}분 뒤 다시 하거나 비밀번호를 재설정하세요.",
                            headers={"Retry-After": str(wait)})
    row = db.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()
    ok = security.verify_password(body.password, row["pw_hash"] if row else security.DUMMY_HASH) and row is not None
    if not ok:
        raise HTTPException(401, "아이디 또는 비밀번호가 맞지 않습니다")  # 어느 쪽이 틀렸는지 알려 주지 않는다
    login_fail.clear(username)
    start_session(db, response, row["id"])
    return public(row)


@auth.post("/logout", status_code=204)
def logout(request: Request, response: Response, db: sqlite3.Connection = Depends(get_db)):
    if sid := request.cookies.get("sid"):
        with db:
            db.execute("DELETE FROM sessions WHERE sid_hash=?", (security.token_hash(sid),))
    response.delete_cookie("sid", path="/")


@auth.get("/me")
def me(user=Depends(current_user)):
    return {**public(user), "expires_in": user["expires_in"]}


@auth.post("/password")
def change_password(body: PasswordIn, response: Response, user=Depends(current_user), db: sqlite3.Connection = Depends(get_db)):
    row = db.execute("SELECT pw_hash FROM users WHERE id=?", (user["id"],)).fetchone()
    if not security.verify_password(body.current, row["pw_hash"]):
        field_error("current", ["현재 비밀번호가 맞지 않습니다"])
    if why := security.check_password(body.new, user["username"]):
        field_error("new", why)
    with db:
        db.execute("UPDATE users SET pw_hash=?, must_change=0 WHERE id=?", (security.hash_password(body.new), user["id"]))
        db.execute("UPDATE reset_tokens SET used=1 WHERE user_id=?", (user["id"],))  # 남아 있던 재설정 링크 무효
    end_sessions(db, user["id"])  # 다른 기기 세션도 끊는다
    start_session(db, response, user["id"])  # 이 기기는 새 세션 ID로
    return {"ok": True}


@auth.post("/forgot")
def forgot(body: ForgotIn, background: BackgroundTasks, db: sqlite3.Connection = Depends(get_db)):
    username = body.username.strip().lower()
    if forgot_hits.take(username):
        return SAME_ANSWER
    row = db.execute("SELECT id, email FROM users WHERE username=?", (username,)).fetchone()
    if row and row["email"] and row["email"].lower() == body.email.strip().lower():
        background.add_task(issue_reset, row["id"], row["email"])  # 토큰 저장·발송은 응답 뒤 → 응답 시간·실패로 가입 여부가 드러나지 않게
    return SAME_ANSWER  # 있는 아이디든 없는 아이디든 같은 답


def issue_reset(user_id: int, email: str):
    """1회용 토큰(해시만 저장) → 메일(SMTP_HOST) 또는 발송함. 메일도 데모도 없으면 링크가 전달되지 않으니 운영자 임시 비밀번호를 쓴다."""
    token = security.new_token()
    conn = connect()
    try:
        with conn:
            conn.execute("INSERT INTO reset_tokens VALUES (?,?,?,0)", (security.token_hash(token), user_id, time.time() + policy.RESET_TTL))
        link = f"{BASE_URL}/reset.html#token={token}"  # # 뒤는 서버 로그·Referer에 남지 않는다
        mail = (email, "비밀번호 재설정 안내", f"{policy.RESET_TTL // 60}분 안에 한 번만 쓸 수 있습니다: {link}")
        send_mail(*mail) if os.getenv("SMTP_HOST") else to_outbox(conn, *mail)
    finally:
        conn.close()


@auth.post("/reset")
def reset(body: ResetIn, db: sqlite3.Connection = Depends(get_db)):
    th = security.token_hash(body.token)
    row = db.execute("""SELECT u.id, u.username FROM reset_tokens t JOIN users u ON u.id = t.user_id
        WHERE t.token_hash=? AND t.used=0 AND t.expires>?""", (th, time.time())).fetchone()
    if not row:
        raise HTTPException(400, "링크가 만료됐거나 이미 사용됐습니다. 다시 요청하세요.")
    if why := security.check_password(body.password, row["username"]):
        field_error("password", why)
    new_hash = security.hash_password(body.password)
    with db:  # 토큰 소비를 조건부 UPDATE 한 번으로: 같은 토큰으로 동시에 와도 하나만 통과
        if db.execute("UPDATE reset_tokens SET used=1 WHERE token_hash=? AND used=0 AND expires>?", (th, time.time())).rowcount != 1:
            raise HTTPException(400, "링크가 만료됐거나 이미 사용됐습니다. 다시 요청하세요.")
        db.execute("UPDATE users SET pw_hash=?, must_change=0 WHERE id=?", (new_hash, row["id"]))
        db.execute("UPDATE reset_tokens SET used=1 WHERE user_id=?", (row["id"],))  # 같은 사람의 다른 링크도 무효
        db.execute("DELETE FROM sessions WHERE user_id=?", (row["id"],))  # 재설정 뒤 기존 로그인 모두 끊기, 자동 로그인 없음
    login_fail.clear(row["username"])
    return {"ok": True}


# ---------- /api/admin (운영자만: 라우터 전체에 한 번 건다) ----------
admin = APIRouter(prefix="/api/admin", tags=["admin"], dependencies=[Depends(require_role("admin"))])


@admin.get("/users")
def list_users(q: str = "", db: sqlite3.Connection = Depends(get_db)):
    rows = db.execute("""SELECT id, username, name, role, must_change, created_at FROM users
        WHERE username LIKE ? OR name LIKE ? ORDER BY id LIMIT 200""", (f"%{q}%", f"%{q}%")).fetchall()
    return [{**dict(r), "role_label": policy.ROLES.get(r["role"], r["role"]), "must_change": bool(r["must_change"])} for r in rows]


@admin.post("/users/{user_id}/temp-password")
def temp_password(user_id: int, db: sqlite3.Connection = Depends(get_db)):
    temp = secrets.token_urlsafe(9) + "Aa1!"  # 한 번만 보여 준다. 첫 로그인 때 바꾸게 한다
    with db:
        cur = db.execute("UPDATE users SET pw_hash=?, must_change=1 WHERE id=?", (security.hash_password(temp), user_id))
        db.execute("DELETE FROM sessions WHERE user_id=?", (user_id,))
        db.execute("UPDATE reset_tokens SET used=1 WHERE user_id=?", (user_id,))
    if cur.rowcount == 0:
        raise HTTPException(404, "없는 사용자")
    return {"temp_password": temp}


@admin.get("/outbox")
def outbox(db: sqlite3.Connection = Depends(get_db)):
    if not DEMO:
        raise HTTPException(404, "Not Found")
    return [dict(r) for r in db.execute("SELECT * FROM outbox ORDER BY id DESC LIMIT 50")]


# ---------- 앱 ----------
@asynccontextmanager
async def lifespan(app: FastAPI):
    with connect() as conn:
        init_db(conn)
    log.info("startup db=%s policy=%s demo=%s", DB, policy.VERSION, DEMO)
    yield


app = FastAPI(title="과제 웹 서비스", version="0.1.0", lifespan=lifespan)
app.include_router(auth)
app.include_router(admin)


@app.middleware("http")
async def guard_and_log(request: Request, call_next):
    t = time.perf_counter()
    # CSRF 완화: 상태를 바꾸는 /api 요청은 화면의 fetch만 붙이는 헤더가 있어야 한다(+ 쿠키 SameSite=Lax)
    if request.url.path.startswith("/api/") and request.method not in ("GET", "HEAD", "OPTIONS") \
            and request.headers.get("x-requested-with") != "fetch":
        resp = JSONResponse({"detail": "요청 형식이 맞지 않습니다"}, status_code=403)
    else:
        resp = await call_next(request)
    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["Referrer-Policy"] = "same-origin"
    if request.url.path.startswith("/api/"):
        resp.headers["Cache-Control"] = "no-store"
    log.info("%s %s %s %.1fms", request.method, request.url.path, resp.status_code, (time.perf_counter() - t) * 1000)  # 본문·쿠키는 남기지 않는다
    return resp


@app.exception_handler(Exception)
async def unhandled(request: Request, exc: Exception):
    log.exception("unhandled %s", request.url.path)
    return JSONResponse(status_code=500, content={"detail": "internal error"})


@app.get("/health")
def health():
    return {"status": "ok", "policy": policy.VERSION}


# ---------- 과제 기능 자리: 공개 / 구성원(자기 것만) / 운영자(전체) 3층 예시. items를 과제 데이터로 바꾼다 ----------
class ItemIn(BaseModel):
    title: str = Field(min_length=1, max_length=100)


@app.get("/api/public/info")
def public_info():
    """로그인 없이 보는 정보(예: 시간표·공지). 개인정보는 넣지 않는다."""
    return {"service": app.title, "policy": policy.VERSION}


@app.get("/api/items")
def list_items(user=Depends(require_user), db: sqlite3.Connection = Depends(get_db)):
    """구성원은 자기 것만, 운영자는 전체. 거르는 조건은 화면이 아니라 여기(SQL)에 있다."""
    if user["role"] == "admin":
        rows = db.execute("SELECT * FROM items ORDER BY id DESC LIMIT 200").fetchall()
    else:
        rows = db.execute("SELECT * FROM items WHERE owner_id=? ORDER BY id DESC LIMIT 200", (user["id"],)).fetchall()
    return [dict(r) for r in rows]


@app.post("/api/items", status_code=201)
def create_item(body: ItemIn, user=Depends(require_user), db: sqlite3.Connection = Depends(get_db)):
    with db:
        cur = db.execute("INSERT INTO items(owner_id, title) VALUES (?,?)", (user["id"], body.title.strip()))
    return dict(db.execute("SELECT * FROM items WHERE id=?", (cur.lastrowid,)).fetchone())


@app.get("/api/items/{item_id}")
def get_item(item_id: int, user=Depends(require_user), db: sqlite3.Connection = Depends(get_db)):
    """행 소유권: 남의 항목은 403이 아니라 404(있는지조차 알려 주지 않는다)."""
    row = db.execute("SELECT * FROM items WHERE id=?", (item_id,)).fetchone()
    if not row or (user["role"] != "admin" and row["owner_id"] != user["id"]):
        raise HTTPException(404, "없는 항목")
    return dict(row)


app.mount("/", StaticFiles(directory=Path(__file__).resolve().parent.parent / "static", html=True), name="static")
