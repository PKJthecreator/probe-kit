"""저장: SQLite 연결(요청마다 열고 닫음)·표 만들기·사용자·세션·발송. 모든 SQL은 ? 바인딩.
DB 경로는 환경변수 APP_DB(기본 app.db). 컨테이너면 볼륨 경로(/data/app.db)로 둬야 재생성 때 계정이 사라지지 않는다.
"""
import logging
import os
import smtplib
import sqlite3
import time
from email.message import EmailMessage

from fastapi import Response

from app import policy, security

DB = os.getenv("APP_DB", "app.db")
DEMO = os.getenv("APP_ENV") == "demo"                     # 운영자 화면의 발송함 열람은 데모에서만
COOKIE_SECURE = os.getenv("COOKIE_SECURE") == "1"         # https에서만 1. http에서 켜면 쿠키가 안 붙어 로그인이 안 된다


def connect():
    conn = sqlite3.connect(DB, timeout=5, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def get_db():
    conn = connect()
    try:
        yield conn
    finally:
        conn.close()


def init_db(conn):
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY, username TEXT UNIQUE NOT NULL, name TEXT NOT NULL, email TEXT,
        pw_hash TEXT NOT NULL, role TEXT NOT NULL DEFAULT 'member', must_change INTEGER NOT NULL DEFAULT 0,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP);
    CREATE TABLE IF NOT EXISTS sessions(sid_hash TEXT PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        created REAL NOT NULL, last_seen REAL NOT NULL);
    CREATE TABLE IF NOT EXISTS reset_tokens(token_hash TEXT PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        expires REAL NOT NULL, used INTEGER NOT NULL DEFAULT 0);
    CREATE TABLE IF NOT EXISTS outbox(id INTEGER PRIMARY KEY, to_addr TEXT, subject TEXT, body TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP);
    CREATE TABLE IF NOT EXISTS items(id INTEGER PRIMARY KEY, owner_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        title TEXT NOT NULL, version INTEGER NOT NULL DEFAULT 1, created_at TEXT DEFAULT CURRENT_TIMESTAMP);
    """)  # 열을 더해도 이미 만든 DB 파일에는 안 생긴다(IF NOT EXISTS) → 새 DB로 시작하거나 ALTER TABLE


def create_user(conn, username, name, password, role="member", email=None, must_change=False):
    with conn:
        cur = conn.execute("INSERT INTO users(username, name, email, pw_hash, role, must_change) VALUES (?,?,?,?,?,?)",
                           (username.lower(), name, email, security.hash_password(password), role, int(must_change)))
    return cur.lastrowid


def start_session(conn, response: Response, user_id: int):
    """무작위 세션 ID → 쿠키(HttpOnly: 화면 JS가 못 읽음). DB에는 해시만."""
    sid, now = security.new_token(), time.time()
    with conn:
        conn.execute("INSERT INTO sessions VALUES (?,?,?,?)", (security.token_hash(sid), user_id, now, now))
    response.set_cookie("sid", sid, httponly=True, samesite="lax", secure=COOKIE_SECURE, max_age=policy.SESSION_ABS, path="/")


def end_sessions(conn, user_id: int):
    with conn:
        conn.execute("DELETE FROM sessions WHERE user_id=?", (user_id,))


def send_mail(to_addr, subject, body):
    """메일 서버(SMTP_HOST)로 보낸다. 응답 뒤 백그라운드에서 돌고, 실패해도 사용자 응답은 같다(원인은 서버 로그에만)."""
    msg = EmailMessage()
    msg["From"], msg["To"], msg["Subject"] = os.getenv("SMTP_FROM", "noreply@example.com"), to_addr, subject
    msg.set_content(body)
    try:
        with smtplib.SMTP(os.environ["SMTP_HOST"], int(os.getenv("SMTP_PORT", 25)), timeout=5) as s:
            s.send_message(msg)
    except OSError:
        logging.getLogger("app").exception("mail failed")


def to_outbox(conn, to_addr, subject, body):
    """메일 서버가 없을 때: outbox 표에 남긴다(데모에서 운영자 화면 '발송함'으로 확인)."""
    with conn:
        conn.execute("INSERT INTO outbox(to_addr, subject, body) VALUES (?,?,?)", (to_addr, subject, body))  # 링크는 로그에 찍지 않는다
