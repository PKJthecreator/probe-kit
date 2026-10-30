"""정상·경계·실패 입력 테스트. 기대값은 rules.py 주석(요구 문장)에서 정했다. 구현 코드에서 가져오지 않는다.
실행: python -m pytest -q tests   (fastapi.testclient는 httpx가 필요)
"""
import os
import tempfile

os.environ["APP_DB"] = os.path.join(tempfile.mkdtemp(), "test.db")

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402


def post(c, t, p, eq="EQ-1"):
    return c.post("/api/judgements", json={"equipment_id": eq, "temperature": t, "pressure": p})


def test_flow():
    with TestClient(app) as c:
        assert c.get("/health").json()["status"] == "ok" and c.get("/readyz").status_code == 200
        assert post(c, 25, 1).json()["status"] == "OK"
        assert post(c, 80.0, 1).json()["status"] == "WARN"      # 경계 80.0 포함
        assert post(c, 79.99, 1).json()["status"] == "OK"
        assert post(c, 25, 10.0).json()["status"] == "OK"       # 경계 10.0 통과
        r = post(c, 120, 11)
        assert r.status_code == 201 and r.json()["status"] == "NG" and len(r.json()["reasons"]) == 2
        assert post(c, 25, -1).status_code == 422               # 잘못된 입력
        assert c.post("/api/judgements", json={"equipment_id": ""}).status_code == 422
        hist = c.get("/api/equipment/EQ-1/judgements").json()
        assert hist[0]["status"] == "NG" and len(hist) == 5     # 최신순, 422는 저장 안 됨
        assert c.get("/api/equipment/NONE/judgements").status_code == 404
        assert c.get("/").status_code == 200                     # 화면
