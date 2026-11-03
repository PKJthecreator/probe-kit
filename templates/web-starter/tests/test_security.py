"""순수 함수 경계 테스트(설치 추가 없음, pytest만). 기대값은 policy.py의 규칙 문장에서 정했다.
실행(web-starter 폴더): python -m pytest -q tests/test_security.py
"""
import os

os.environ.setdefault("SCRYPT_N", "1024")  # 테스트만 빠르게. 실서비스 값은 security.py 기본값

from app import policy, security  # noqa: E402


def test_hash_roundtrip():
    h = security.hash_password("Abcd1234!z")
    assert h.startswith("scrypt$1024$") and security.verify_password("Abcd1234!z", h)
    assert not security.verify_password("Abcd1234!Z", h)


def test_password_rules_boundaries():
    assert policy.REQUIRE == ("upper", "lower", "digit", "symbol") and (policy.PW_MIN, policy.PW_MAX) == (8, 128)
    assert security.check_password("Abcd123!") == []                      # 8자 통과
    assert security.check_password("Abc123!") == ["8~128자"]               # 7자
    assert security.check_password("A" * 60 + "a" * 60 + "1234567!") == []  # 128자 통과
    assert "8~128자" in security.check_password("A" * 60 + "a" * 60 + "12345678!")  # 129자
    assert security.check_password("abcde1234!") == ["영문 대문자 1개 이상"]
    assert security.check_password("ABCDE1234!") == ["영문 소문자 1개 이상"]
    assert security.check_password("Abcdefgh!") == ["숫자 1개 이상"]
    assert security.check_password("Abcde12345") == ["특수문자 1개 이상"]
    assert "아이디를 포함하지 않기" in security.check_password("Xkim01yy!", "kim01")
    assert "흔한 비밀번호 금지" in security.check_password("P@ssw0rd1")


def test_username_rule():
    assert security.check_username("kim01") == []
    assert security.check_username("kim") and security.check_username("1kim") and security.check_username("Kim01")


def test_throttle_window():
    t = [0.0]
    th = security.Throttle(5, 900, clock=lambda: t[0])
    for _ in range(4):
        th.fail("u")
    assert th.retry_after("u") == 0           # 4번까지는 안 잠김
    th.fail("u")
    assert th.retry_after("u") > 0            # 5번째에 잠김
    t[0] = 901
    assert th.retry_after("u") == 0           # 창이 지나면 풀림
    th.fail("u"); th.clear("u")
    assert th.retry_after("u") == 0


def test_throttle_take_reserves_attempt():
    th = security.Throttle(2, 60, clock=lambda: 0.0)
    assert th.take("u") == 0 and th.take("u") == 0   # 두 번까지 시도 허용(기록은 시도할 때 먼저)
    assert th.take("u") > 0                          # 세 번째는 확인과 동시에 막힘
    th.clear("u")
    assert th.take("u") == 0                         # 성공하면 clear
