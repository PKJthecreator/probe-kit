"""순수 함수: 비밀번호 해시·검사, 토큰, 로그인 실패 잠금. 외부 설치 없음(표준 라이브러리 scrypt).
자체 점검: python -m app.security   (web-starter 폴더에서)
"""
import base64
import hashlib
import hmac
import os
import secrets
import threading
import time

from app import policy

# scrypt N=2^15, r=8, p=3 → 약 32MiB·0.5초(이 값은 해시 문자열에 같이 저장돼 나중에 올려도 옛 해시를 검증할 수 있다).
# 테스트는 SCRYPT_N=1024로 빠르게 돌린다.
N, R, P = int(os.getenv("SCRYPT_N", 2 ** 15)), 8, 3


def _scrypt(pw: str, salt: bytes, n: int, r: int, p: int) -> bytes:
    return hashlib.scrypt(pw.encode(), salt=salt, n=n, r=r, p=p, maxmem=128 * r * (n + p + 2) + 1024 * 1024, dklen=32)


def hash_password(pw: str) -> str:
    salt = secrets.token_bytes(16)
    b64 = lambda b: base64.b64encode(b).decode()  # noqa: E731
    return f"scrypt${N}${R}${P}${b64(salt)}${b64(_scrypt(pw, salt, N, R, P))}"


def verify_password(pw: str, stored: str) -> bool:
    _, n, r, p, salt, digest = stored.split("$")
    got = _scrypt(pw, base64.b64decode(salt), int(n), int(r), int(p))
    return hmac.compare_digest(got, base64.b64decode(digest))  # 비교 시간이 내용에 따라 달라지지 않게


DUMMY_HASH = hash_password(secrets.token_urlsafe(12))  # 없는 아이디도 같은 시간 동안 해시 비교 → 아이디 존재가 응답 시간으로 드러나지 않게


def check_username(u: str) -> list[str]:
    return [] if policy.USERNAME_RE.fullmatch(u) else [f"아이디 규칙: {policy.USERNAME_HINT}"]


def check_password(pw: str, username: str = "") -> list[str]:
    """정책을 어긴 이유 목록(빈 목록이면 통과). 화면 체크리스트와 같은 순서·문구."""
    why = []
    if not policy.PW_MIN <= len(pw) <= policy.PW_MAX:
        why.append(f"{policy.PW_MIN}~{policy.PW_MAX}자")
    rules = {"upper": (str.isupper, "영문 대문자"), "lower": (str.islower, "영문 소문자"),
             "digit": (str.isdigit, "숫자"), "symbol": (lambda c: not c.isalnum() and not c.isspace(), "특수문자")}
    for key in policy.REQUIRE:
        test, label = rules[key]
        if not any(test(c) and c.isascii() for c in pw):
            why.append(f"{label} 1개 이상")
    if username and username.lower() in pw.lower():
        why.append("아이디를 포함하지 않기")
    if pw.lower() in policy.COMMON:
        why.append("흔한 비밀번호 금지")
    return why


def new_token() -> str:
    return secrets.token_urlsafe(32)  # 256비트 난수. 쿠키·링크에는 원문, DB에는 아래 해시만 저장


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


class Throttle:
    """키(아이디)별 실패 시각을 창(window) 안에서 센다. max번 차면 남은 초를 돌려준다.
    ponytail: 메모리 dict라 재시작하면 초기화되고 워커 1개에서만 정확. 워커를 늘리면 DB 표로 옮긴다."""

    def __init__(self, max_fail: int, window: int, clock=time.monotonic):
        self.max, self.window, self.clock, self.hits, self.lock = max_fail, window, clock, {}, threading.Lock()

    def _recent(self, key):
        now = self.clock()
        self.hits[key] = [t for t in self.hits.get(key, []) if now - t < self.window]
        return self.hits[key], now

    def retry_after(self, key) -> int:
        with self.lock:
            recent, now = self._recent(key)
            return int(self.window - (now - recent[0])) + 1 if len(recent) >= self.max else 0

    def take(self, key) -> int:
        """확인과 기록을 한 잠금 안에서: 잠겼으면 남은 초, 아니면 이번 시도를 실패로 먼저 적고 0(성공하면 clear)."""
        with self.lock:
            recent, now = self._recent(key)
            if len(recent) >= self.max:
                return int(self.window - (now - recent[0])) + 1
            recent.append(now)
            return 0

    def fail(self, key):
        with self.lock:
            self._recent(key)[0].append(self.clock())

    def clear(self, key):
        with self.lock:
            self.hits.pop(key, None)


if __name__ == "__main__":
    h = hash_password("Abcd1234!")
    assert verify_password("Abcd1234!", h) and not verify_password("Abcd1234?", h)
    if policy.REQUIRE == ("upper", "lower", "digit", "symbol") and policy.PW_MIN == 8:
        assert check_password("Abcd123!") == []                          # 8자 경계 통과
        assert check_password("Abc123!") == ["8~128자"]                   # 7자
        assert check_password("abcde1234!") == ["영문 대문자 1개 이상"]
        assert check_password("Abcd12345") == ["특수문자 1개 이상"]
        assert "아이디를 포함하지 않기" in check_password("Kim_lee1!", "kim_lee")
        assert "흔한 비밀번호 금지" in check_password("P@ssw0rd1")
    assert check_username("kim01") == [] and check_username("1kim") and check_username("ab")
    t = [0.0]
    th = Throttle(2, 60, clock=lambda: t[0])
    th.fail("a"); assert th.retry_after("a") == 0
    th.fail("a"); assert th.retry_after("a") == 61                    # 2번째 실패에서 잠김
    t[0] = 61; assert th.retry_after("a") == 0                         # 창이 지나면 풀림
    assert token_hash(new_token()) != token_hash(new_token())
    print("security self-check OK")
