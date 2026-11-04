"""API 흐름·권한 테스트. 실행(web-starter 폴더): python -m pytest -q tests   (fastapi.testclient는 httpx가 필요)
MATRIX = README의 역할 표와 같은 내용: (메서드, 경로, 역할, 기대 상태코드). 역할 표를 바꾸면 여기도 바꾼다.
"""
import os
import re
import tempfile

os.environ["APP_DB"] = os.path.join(tempfile.mkdtemp(), "test.db")
os.environ["APP_ENV"] = "demo"
os.environ.setdefault("SCRYPT_N", "1024")

from fastapi.testclient import TestClient  # noqa: E402

from app import policy, store  # noqa: E402
from app.main import app, login_fail  # noqa: E402

H = {"X-Requested-With": "fetch"}
PW = "Abcd1234!z"


def client():
    return TestClient(app, headers=H)


def signup(c, username, email=None):
    return c.post("/api/auth/signup", json={"username": username, "name": username, "email": email or f"{username}@example.com", "password": PW})


def make_admin(username="boss01"):
    conn = store.connect()
    store.init_db(conn)
    store.create_user(conn, username, "운영자", PW, role="admin")
    conn.close()


MATRIX = [  # 역할: none(로그인 안 함) / member / admin
    ("GET", "/api/public/info", "none", 200),
    ("GET", "/api/auth/me", "none", 401),
    ("GET", "/api/items", "none", 401),
    ("GET", "/api/items", "member", 200),
    ("GET", "/api/items", "admin", 200),
    ("GET", "/api/auth/me", "member", 200),
    ("GET", "/api/admin/users", "none", 401),
    ("GET", "/api/admin/users", "member", 403),
    ("GET", "/api/admin/users", "admin", 200),
    ("GET", "/api/admin/outbox", "member", 403),
    ("GET", "/api/admin/outbox", "admin", 200),
]


def test_role_matrix():
    with client() as c:
        make_admin()
        sessions = {"none": client(), "member": client(), "admin": client()}
        assert signup(sessions["member"], "mem01").status_code == 201
        assert sessions["admin"].post("/api/auth/login", json={"username": "boss01", "password": PW}).status_code == 200
        for method, path, role, want in MATRIX:
            got = sessions[role].request(method, path).status_code
            assert got == want, (method, path, role, got)
        assert c.get("/").status_code == 200


def test_signup_rules_and_cookie():
    with client() as c:
        r = c.post("/api/auth/signup", json={"username": "lee01", "name": "이", "password": "abc"})
        assert r.status_code == 422 and r.json()["detail"][0]["loc"] == ["body", "password"]
        assert c.post("/api/auth/signup", json={"username": "1bad", "name": "x", "password": PW}).status_code == 422
        r = signup(c, "lee01")
        assert r.status_code == 201 and r.json()["role"] == "member"          # 가입은 항상 구성원
        cookie = r.headers["set-cookie"].lower()
        assert "httponly" in cookie and "samesite=lax" in cookie
        assert signup(client(), "lee01").status_code == 409                    # 중복
        assert c.post("/api/auth/signup", json={"username": "x" * 5, "name": "x", "password": PW, "role": "admin"}).json()["role"] == "member"


def test_login_same_error_and_lockout():
    with client() as c:
        signup(c, "park01")
        c2 = client()
        wrong = c2.post("/api/auth/login", json={"username": "park01", "password": "Wrong123!x"})
        nouser = c2.post("/api/auth/login", json={"username": "nobody1", "password": "Wrong123!x"})
        assert wrong.status_code == nouser.status_code == 401 and wrong.json() == nouser.json()  # 어느 쪽이 틀렸는지 안 알려 줌
        for _ in range(policy.LOCK_MAX - 1):
            c2.post("/api/auth/login", json={"username": "park01", "password": "Wrong123!x"})
        locked = c2.post("/api/auth/login", json={"username": "park01", "password": PW})
        assert locked.status_code == 429 and int(locked.headers["retry-after"]) > 0
        login_fail.clear("park01")
        assert c2.post("/api/auth/login", json={"username": "park01", "password": PW}).status_code == 200


def test_csrf_header_required():
    with client() as c:
        signup(c, "choi01")
        bare = TestClient(app)
        bare.cookies = c.cookies
        assert bare.post("/api/items", json={"title": "x"}).status_code == 403    # 헤더 없는 변경 요청 거절
        assert c.post("/api/items", json={"title": "x"}).status_code == 201


def test_row_ownership_404():
    with client() as a, client() as b:
        signup(a, "own01"); signup(b, "own02")
        item = a.post("/api/items", json={"title": "내 것"}).json()
        assert a.get(f"/api/items/{item['id']}").status_code == 200
        assert b.get(f"/api/items/{item['id']}").status_code == 404             # 남의 것은 존재도 숨김
        assert all(i["owner_id"] != item["owner_id"] for i in b.get("/api/items").json())


def test_concurrent_edit_409():
    with client() as a, client() as b:
        signup(a, "edit01"); signup(b, "edit02")
        item = a.post("/api/items", json={"title": "처음"}).json()
        url, v = f"/api/items/{item['id']}", item["version"]
        assert b.patch(url, json={"title": "남이", "version": v}).status_code == 404   # 권한이 409보다 먼저
        first = a.patch(url, json={"title": "먼저", "version": v})
        assert first.status_code == 200 and first.json()["version"] == v + 1
        assert a.patch(url, json={"title": "늦게", "version": v}).status_code == 409   # 옛 version으로 두 번째 저장
        assert a.get(url).json()["title"] == "먼저"                                    # 덮어쓰지 않았다


def test_forgot_reset_flow():
    with client() as c:
        signup(c, "jung01", email="jung@example.com")
        anon = client()
        same1 = anon.post("/api/auth/forgot", json={"username": "jung01", "email": "jung@example.com"}).json()
        same2 = anon.post("/api/auth/forgot", json={"username": "ghost01", "email": "g@example.com"}).json()
        assert same1 == same2                                                   # 가입 여부를 알려 주지 않음
        make_admin("boss02")
        adm = client()
        adm.post("/api/auth/login", json={"username": "boss02", "password": PW})
        anon.post("/api/auth/forgot", json={"username": "jung01", "email": "jung@example.com"})  # 링크 두 개
        bodies = [r["body"] for r in adm.get("/api/admin/outbox").json()]                       # 최신순
        token, older = (re.search(r"#token=(\S+)", x).group(1) for x in bodies[:2])
        assert anon.post("/api/auth/reset", json={"token": token, "password": "weak"}).status_code == 422
        assert anon.post("/api/auth/reset", json={"token": token, "password": "Newpass12!"}).status_code == 200
        assert anon.post("/api/auth/reset", json={"token": token, "password": "Newpass12!"}).status_code == 400  # 1회용
        assert anon.post("/api/auth/reset", json={"token": older, "password": "Other123!x"}).status_code == 400  # 같은 사람의 다른 링크도 무효
        assert c.get("/api/auth/me").status_code == 401                         # 재설정 뒤 기존 세션 끊김
        assert anon.get("/api/auth/me").status_code == 401                      # 자동 로그인 없음
        assert anon.post("/api/auth/login", json={"username": "jung01", "password": "Newpass12!"}).status_code == 200


def test_temp_password_forces_change():
    with client() as c:
        uid = signup(c, "han01").json()["id"]
        make_admin("boss03")
        adm = client()
        adm.post("/api/auth/login", json={"username": "boss03", "password": PW})
        temp = adm.post(f"/api/admin/users/{uid}/temp-password").json()["temp_password"]
        assert c.get("/api/auth/me").status_code == 401                         # 기존 세션 끊김
        u = client()
        assert u.post("/api/auth/login", json={"username": "han01", "password": temp}).json()["must_change"] is True
        assert u.get("/api/items").status_code == 403                           # 바꾸기 전에는 기능 막힘
        assert u.post("/api/auth/password", json={"current": temp, "new": "Changed12!"}).status_code == 200
        assert u.get("/api/items").status_code == 200
        assert u.post("/api/auth/logout").status_code == 204 and u.get("/api/auth/me").status_code == 401
