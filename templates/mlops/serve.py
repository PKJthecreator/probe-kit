"""모델 운영 API 뼈대: 예측(응답에 모델 버전) → 실측 피드백 → 잔차 드리프트 경보 → 사람 승인 승격·롤백.
경보는 재학습을 자동으로 돌리지 않는다(후보 학습 → registry.gate → 사람 승인 promote 순서).
승격은 등록 때 남긴 게이트 결과(register(..., gate=gate(...)))가 통과인 버전만 받는다. 모델 운영 API를 과제가 요구할 때만 쓴다.
실행: REG_DIR=registry uvicorn serve:app --host 0.0.0.0 --port 8001   (registry.py와 같은 폴더)
테스트: python serve.py   (FastAPI TestClient = httpx 필요)
주의: /model/promote·/model/rollback은 운영에서 인증 뒤에 둔다. 여기서는 confirm·approver만 확인한다.
"""
import json
import os
import sqlite3
import time
import uuid
from contextlib import asynccontextmanager, contextmanager

import pandas as pd
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

import registry

REG = os.getenv("REG_DIR", "registry")
DB = os.getenv("SERVE_DB", "serve.db")
WARMUP = int(os.getenv("DRIFT_WARMUP", "30"))   # 기준 잔차가 메타에 없으면 처음 n건 피드백으로 기준을 잡는다


class PredictIn(BaseModel):
    features: dict = Field(min_length=1)


class FeedbackIn(BaseModel):
    request_id: str
    actual: float


class Approve(BaseModel):
    approver: str = Field(min_length=1)
    confirm: bool = False
    version: str | None = None


@contextmanager
def db():
    """요청마다 열고 commit 뒤 닫는다(sqlite3의 with는 commit만 하고 닫지 않는다)."""
    conn = sqlite3.connect(DB, timeout=5, check_same_thread=False)
    try:
        conn.execute("CREATE TABLE IF NOT EXISTS pred(id TEXT PRIMARY KEY, version TEXT, features TEXT, pred REAL, actual REAL, ts REAL)")
        yield conn
        conn.commit()
    finally:
        conn.close()


def load(app):
    """운영 버전을 읽고 드리프트 기준을 정한다. 버전이 바뀌면 다시 부른다(재기동 없이)."""
    version, model = registry.load_production(REG)
    meta = registry._load(REG)["versions"].get(version, {}) if version else {}
    ref = meta.get("ref_residuals")
    app.state.model, app.state.version = model, version
    app.state.drift = registry.ResidualDrift(ref) if ref else None
    app.state.warmup = []


@asynccontextmanager
async def lifespan(app: FastAPI):
    load(app)
    yield


app = FastAPI(title="모델 운영 API", lifespan=lifespan)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/readyz")
def ready():
    if app.state.model is None:
        raise HTTPException(503, "운영 모델 없음")
    return {"status": "ready", "model_version": app.state.version}


@app.post("/predict")
def predict(x: PredictIn):
    if app.state.model is None:
        raise HTTPException(503, "운영 모델 없음")
    try:
        y = float(app.state.model.predict(pd.DataFrame([x.features]))[0])
    except (KeyError, ValueError) as e:
        raise HTTPException(422, f"입력 열·값 확인: {e}")
    rid = uuid.uuid4().hex[:12]
    with db() as conn:
        conn.execute("INSERT INTO pred VALUES (?,?,?,?,?,?)", (rid, app.state.version, json.dumps(x.features), y, None, time.time()))
    return {"request_id": rid, "prediction": y, "model_version": app.state.version}


@app.post("/feedback")
def feedback(f: FeedbackIn):
    with db() as conn:
        # 조건부 UPDATE 한 번으로 판정: 동시에 같은 피드백이 와도 한 건만 반영된다
        changed = conn.execute("UPDATE pred SET actual=? WHERE id=? AND actual IS NULL", (f.actual, f.request_id)).rowcount
        row = conn.execute("SELECT pred, version FROM pred WHERE id=?", (f.request_id,)).fetchone()
        if not row:
            raise HTTPException(404, "없는 request_id")
        if not changed:
            raise HTTPException(409, "이미 실측이 들어온 요청(중복 집계 방지)")
    residual = f.actual - row[0]
    if row[1] != app.state.version:   # 승격 전 버전의 예측 → 저장만, 지금 버전의 드리프트에는 넣지 않는다
        return {"residual": residual, "status": f"이전 버전({row[1]}) 피드백: 저장만", "model_version": row[1]}
    if app.state.drift is None:   # 기준 잡는 중
        app.state.warmup.append(residual)
        if len(app.state.warmup) >= WARMUP:
            app.state.drift = registry.ResidualDrift(app.state.warmup)
        return {"residual": residual, "status": f"기준 수집 {len(app.state.warmup)}/{WARMUP}"}
    r = app.state.drift.update(residual)
    return {"residual": residual, **r, "status": "drift_alarm: 후보 학습·게이트·승인 검토" if r["alarm"] else "ok", "model_version": row[1]}


@app.get("/model")
def model_info():
    state = registry._load(REG)
    return {"production": state["production"], "previous": state["previous"],
            "metrics": state["versions"].get(state["production"] or "", {}).get("metrics")}


@app.post("/model/promote")
def promote(a: Approve):
    meta = registry._load(REG)["versions"].get(a.version or "", {})
    if meta and meta.get("gate", {}).get("decision") != "awaiting_approval":
        raise HTTPException(409, "게이트 통과 기록이 없는 버전은 승격하지 않는다(register(..., gate=...))")
    try:
        registry.promote(REG, a.version, confirm=a.confirm, approver=a.approver)
    except PermissionError as e:
        raise HTTPException(403, str(e))
    except KeyError:
        raise HTTPException(404, f"없는 버전: {a.version}")
    load(app)
    return {"production": app.state.version}


@app.post("/model/rollback")
def rollback(a: Approve):
    if not a.confirm:
        raise HTTPException(403, "롤백도 사람 확인(confirm=true, approver)이 필요하다")
    try:
        registry.rollback(REG)
    except RuntimeError as e:
        raise HTTPException(409, str(e))
    load(app)
    return {"production": app.state.version}


if __name__ == "__main__":
    import tempfile

    import numpy as np
    from fastapi.testclient import TestClient
    from sklearn.linear_model import LinearRegression

    tmp = tempfile.mkdtemp()
    REG, DB = os.path.join(tmp, "reg"), os.path.join(tmp, "serve.db")
    rng = np.random.default_rng(0)
    X = pd.DataFrame({"temp": rng.normal(200, 5, 200), "pressure": rng.normal(1, 0.1, 200)})
    yv = 2 * X.temp + 10 * X.pressure + rng.normal(0, 1, 200)
    m1 = LinearRegression().fit(X, yv)
    v1 = registry.register(REG, m1, {"all": {"mae": 0.8}}, ref_residuals=list(yv - m1.predict(X)))
    registry.promote(REG, v1, confirm=True, approver="kim")
    with TestClient(app) as c:
        assert c.get("/readyz").json()["model_version"] == v1
        p = c.post("/predict", json={"features": {"temp": 200, "pressure": 1.0}}).json()
        assert p["model_version"] == v1 and abs(p["prediction"] - 410) < 2
        assert c.post("/predict", json={"features": {}}).status_code == 422
        assert c.post("/predict", json={"features": {"temp": 200}}).status_code == 422, "열이 빠지면 422"
        ok = c.post("/feedback", json={"request_id": p["request_id"], "actual": p["prediction"] + 0.5}).json()
        assert ok["alarm"] is False
        alarms = [c.post("/feedback", json={"request_id": c.post("/predict", json={"features": {"temp": 200, "pressure": 1.0}}).json()["request_id"],
                                            "actual": 430}).json()["alarm"] for _ in range(2)]
        assert alarms == [False, True], "두 번째 큰 잔차에서 경보(5개 중 2개)"
        m2 = LinearRegression().fit(X, yv + 20)
        v_bad = registry.register(REG, m2, {"all": {"mae": 9.0}}, gate=registry.gate({"all": {"mae": 9.0}}, {"all": {"mae": 0.8}}, {"all": 1.0}))
        assert c.post("/model/promote", json={"version": v_bad, "approver": "lee", "confirm": True}).status_code == 409, "게이트 실패 버전 승격 금지"
        v2 = registry.register(REG, m2, {"all": {"mae": 0.8}}, ref_residuals=list(yv + 20 - m2.predict(X)),
                               gate=registry.gate({"all": {"mae": 0.8}}, {"all": {"mae": 0.8}}, {"all": 1.0}))
        assert c.post("/model/promote", json={"version": v2, "approver": "lee"}).status_code == 403, "확인 없이 승격 금지"
        assert c.post("/model/promote", json={"version": v2, "approver": "lee", "confirm": True}).json()["production"] == v2
        assert c.post("/predict", json={"features": {"temp": 200, "pressure": 1.0}}).json()["model_version"] == v2, "재기동 없이 새 버전 응답"
        old = c.post("/predict", json={"features": {"temp": 200, "pressure": 1.0}}).json()   # v2 예측
        assert c.post("/model/rollback", json={"approver": "lee", "confirm": True}).json()["production"] == v1
        fb = c.post("/feedback", json={"request_id": old["request_id"], "actual": 999}).json()
        assert "저장만" in fb["status"], "롤백 전 버전의 피드백은 현재 드리프트에 섞지 않는다"
        assert c.post("/feedback", json={"request_id": old["request_id"], "actual": 1}).status_code == 409, "중복 피드백 거부"
        assert c.post("/feedback", json={"request_id": "nope", "actual": 1}).status_code == 404
    print("serve PASS")
