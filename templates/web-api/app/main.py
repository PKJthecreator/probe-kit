"""FastAPI 뼈대: 입력 검증 → 규칙 판정 → SQLite 저장 → 조회. 화면은 static/, API 문서는 /docs.
- 무거운 객체(모델·에이전트)는 lifespan에서 한 번만 만든다. DB 연결은 요청마다 열고 닫는다(스레드 간 공유 금지).
- 판정 기준은 rules.py 한 곳. LLM을 붙여도 판정·계산은 코드가 하고 LLM은 설명만(../agent).
실행(전용 터미널, 끄지 않는다): uvicorn app.main:app --host 0.0.0.0 --port 8000   ← web-api 폴더에서
테스트: python -m pytest -q tests   (DB 경로는 환경변수 APP_DB, 기본 app.db)
"""
import json
import logging
import os
import sqlite3
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from app import rules

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("app")
DB = os.getenv("APP_DB", "app.db")


class Measurement(BaseModel):
    equipment_id: str = Field(min_length=1, max_length=50, examples=["EQ-001"])
    temperature: float = Field(ge=-50, le=500)
    pressure: float = Field(gt=0, le=100)


class Judgement(BaseModel):
    id: int
    equipment_id: str
    status: str
    reasons: list[str]
    rule_version: str


def connect():
    # 요청마다 새 연결이라 공유는 없지만, FastAPI는 의존성과 엔드포인트를 다른 스레드에서 돌릴 수 있다.
    conn = sqlite3.connect(DB, timeout=5, check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL")  # 읽기·쓰기 동시 요청에서 잠금 대기 줄이기
    return conn


def get_db():
    conn = connect()
    try:
        yield conn
    finally:
        conn.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    with connect() as conn:
        conn.execute("""CREATE TABLE IF NOT EXISTS judgements(
            id INTEGER PRIMARY KEY AUTOINCREMENT, equipment_id TEXT NOT NULL, temperature REAL, pressure REAL,
            status TEXT NOT NULL, reasons TEXT NOT NULL, rule_version TEXT NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP)""")
    log.info("startup db=%s rule_version=%s", DB, rules.VERSION)
    yield


app = FastAPI(title="과제 API", version="0.1.0", lifespan=lifespan)
if os.getenv("CORS_ORIGINS"):  # 화면을 다른 출처(예: Vite 개발 서버)에서 띄울 때만, 허용 출처를 명시해서
    app.add_middleware(CORSMiddleware, allow_origins=os.environ["CORS_ORIGINS"].split(","),
                       allow_methods=["GET", "POST"], allow_headers=["Content-Type"])


@app.middleware("http")
async def access_log(request: Request, call_next):
    t = time.perf_counter()
    resp = await call_next(request)
    log.info("%s %s %s %.1fms", request.method, request.url.path, resp.status_code, (time.perf_counter() - t) * 1000)
    return resp


@app.exception_handler(Exception)
async def unhandled(request: Request, exc: Exception):
    log.exception("unhandled %s", request.url.path)  # 내부 오류 내용은 로그에만, 응답에는 형식만
    return JSONResponse(status_code=500, content={"detail": "internal error"})


@app.get("/health")
def health():  # liveness: 프로세스가 살아 있나
    return {"status": "ok", "rule_version": rules.VERSION}


@app.get("/readyz")
def ready(db: sqlite3.Connection = Depends(get_db)):  # readiness: 의존 자원(DB·모델)이 준비됐나
    db.execute("SELECT 1 FROM judgements LIMIT 1")
    return {"status": "ready"}


@app.post("/api/judgements", response_model=Judgement, status_code=201)
def create_judgement(m: Measurement, db: sqlite3.Connection = Depends(get_db)):
    status, reasons = rules.judge(m.temperature, m.pressure)
    with db:  # 트랜잭션: 실패하면 롤백
        cur = db.execute("INSERT INTO judgements(equipment_id, temperature, pressure, status, reasons, rule_version) VALUES (?,?,?,?,?,?)",
                         (m.equipment_id, m.temperature, m.pressure, status, json.dumps(reasons, ensure_ascii=False), rules.VERSION))
    return Judgement(id=cur.lastrowid, equipment_id=m.equipment_id, status=status, reasons=reasons, rule_version=rules.VERSION)


@app.get("/api/equipment/{equipment_id}/judgements", response_model=list[Judgement])
def list_judgements(equipment_id: str, limit: int = 20, db: sqlite3.Connection = Depends(get_db)):
    rows = db.execute(
        "SELECT id, equipment_id, status, reasons, rule_version FROM judgements WHERE equipment_id=? ORDER BY id DESC LIMIT ?",
        (equipment_id, min(max(limit, 1), 100))).fetchall()
    if not rows:
        raise HTTPException(status_code=404, detail=f"기록 없는 설비: {equipment_id}")
    return [Judgement(id=r[0], equipment_id=r[1], status=r[2], reasons=json.loads(r[3]), rule_version=r[4]) for r in rows]


# 정적 화면은 API 라우트 뒤에 마운트한다(앞에 두면 /api/*를 가린다).
app.mount("/", StaticFiles(directory=Path(__file__).resolve().parent.parent / "static", html=True), name="static")
