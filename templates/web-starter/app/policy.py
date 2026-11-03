"""가입·로그인·세션 규칙 한 곳. 과제·담당자가 정한 값은 여기만 고친다(화면은 /api/auth/policy로 받아 같은 규칙을 그린다).
바꾸면 VERSION을 올리고 tests/의 경계 테스트를 같이 고친다.
"""
import re

VERSION = "2026.11-1"

# 아이디: 영문 소문자로 시작, 소문자·숫자·밑줄 4~20자(서버가 소문자로 바꿔 저장). 사번형이면 r"^\d{8}$"로 교체.
USERNAME_RE = re.compile(r"^[a-z][a-z0-9_]{3,19}$")
USERNAME_HINT = "영문 소문자로 시작, 소문자·숫자·_ 4~20자"

# 비밀번호: 사용자가 요청한 국내식 조합 규칙이 기본. 과제가 다른 규칙을 주면 그 값으로.
# 조합 규칙 없이 '길이 + 흔한 비밀번호 차단'만 쓰려면(NIST SP 800-63B 방식) REQUIRE = () 그리고 PW_MIN = 15.
PW_MIN, PW_MAX = 8, 128
REQUIRE = ("upper", "lower", "digit", "symbol")
COMMON = {"password", "password1!", "qwer1234!", "q1w2e3r4!", "1q2w3e4r!", "admin1234!", "p@ssw0rd", "p@ssw0rd1",
          "abcd1234!", "asdf1234!", "zxcv1234!", "welcome1!", "skhynix1!", "hynix1234!", "iloveyou1!"}  # 소문자로 비교

# 로그인 실패 잠금: 아이디 기준 LOCK_MAX번 실패하면 LOCK_WINDOW초 동안 429. 비밀번호 재설정에 성공하면 풀린다.
LOCK_MAX, LOCK_WINDOW = 5, 15 * 60
# 세션: 마지막 요청 뒤 SESSION_IDLE초, 로그인 뒤 SESSION_ABS초가 지나면 다시 로그인.
SESSION_IDLE, SESSION_ABS = 30 * 60, 8 * 60 * 60
# 비밀번호 재설정 링크 유효 시간, 같은 아이디로 재설정 요청 제한(FORGOT_MAX번 / LOCK_WINDOW초)
RESET_TTL, FORGOT_MAX = 30 * 60, 3

ROLES = {"member": "구성원", "admin": "운영자"}  # 가입은 항상 member. admin은 seed.py로만 만든다.
NAME_MAX = 30
