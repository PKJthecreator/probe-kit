# web-starter — 로그인 있는 웹 서비스(구성원·운영자)

쓰는 때: 요구에 구성원/운영자/관리자/로그인/권한이 보이는 웹 과제. 로그인이 필요 없으면 `../web-api`. 과제가 인증 방식(JWT·SSO·특정 DB)을 정했으면 그쪽이 우선.
필요: fastapi, uvicorn(테스트는 pytest, httpx). 비밀번호 해시는 표준 라이브러리 scrypt라 추가 설치 없음.

## 되는 것 / 안 되는 것
- 된다: 가입(규칙 체크리스트·중복 확인), 로그인(아이디 저장·비밀번호 보기·5회 실패 15분 잠금), 로그아웃, 비밀번호 찾기→재설정 링크(메일 서버 없으면 발송함), 운영자 임시 비밀번호(첫 로그인 때 변경 강제), 로그인 중 비밀번호 변경, 역할별 화면·API, 남의 데이터 404, 명단 CSV 일괄 등록.
- 안 된다(필요하면 추가): 아이디 찾기, 이메일 인증, 2단계 인증, CSRF 토큰, 여러 워커에서 공유되는 잠금, 소셜 로그인.
- 메일 서버(`SMTP_HOST`)도 데모(`APP_ENV=demo`)도 아니면 재설정 링크가 누구에게도 전달되지 않는다 → 운영자 임시 비밀번호로 처리(찾기 화면 안내가 그렇게 말한다). https 운영이면 `COOKIE_SECURE=1`.

## 첫 명령 (과제 폴더에 필요한 파일만 복사한 뒤)
```
python -m app.security                       # 규칙·해시 자체 점검
node -e "import('./static/ui.js').then(() => console.log('js ok'))"   # 화면 JS 문법 점검(고친 뒤마다)
python -m pytest -q tests                    # API·권한 테스트(httpx 필요)
APP_ENV=demo python seed.py --demo           # 운영자·구성원 계정(무작위 비밀번호가 한 번만 출력)
cp ~/probe-kit/templates/brand/tokens.css static/brand.css     # 회사 색·글꼴(선택, 서버 띄우기 전에)
APP_ENV=demo uvicorn app.main:app --host 0.0.0.0 --port 8000   # 전용 터미널. 사용자가 /login.html을 연다
```
명단으로 계정을 미리 만드는 과제: `python seed.py --csv 명단.csv`(열 username,name[,email][,role]) → 임시 비밀번호는 `outputs/logs/initial_passwords.csv`(커밋 금지).

## 모듈 지도 (서술형: "각 모듈은 무엇을 하나")
| 파일 | 하는 일 | 확인 |
|---|---|---|
| `app/policy.py` | 규칙 값 한 곳: 아이디·비밀번호 규칙, 잠금 횟수·시간, 세션 시간, 역할 이름 | `tests/test_security.py` |
| `app/security.py` | 순수 함수: scrypt 해시·검증, 비밀번호 규칙 검사, 토큰, 실패 잠금 카운터 | `python -m app.security` |
| `app/store.py` | SQLite 연결·표·사용자 만들기·세션 발급(쿠키)·발송함 | `tests/test_auth_api.py` |
| `app/main.py` | 입력 검증(Pydantic), 인증 의존성(`require_user`·`require_role`), `/api/auth`·`/api/admin`·과제 기능 라우트, CSRF 헤더 검사, 보안 헤더, 정적 화면 | `tests/test_auth_api.py` |
| `seed.py` | 데모·운영자·명단 계정 만들기(코드에 비밀번호 없음) | 실행 출력 |
| `static/api.js` | fetch 하나: 헤더·401 이동·오류 문구 표 | 브라우저 |
| `static/ui.js` | 화면 보호·헤더(로고)·로딩/빈/오류 상태·표·칸별 오류·비밀번호 체크리스트·시간 표시 | 브라우저 |
| `static/*.html` | login·signup·forgot·reset·change-password·app(구성원)·admin(운영자) | HUMAN_CHECK |
| `react/AuthKit.jsx`, `vue/` | React·Vue 과제용 로그인 상태·역할 막기·로그인 폼(빌드는 과제에서 확인, 여기선 NOT_RUN) | |

## 인증 흐름 (8단계, 각 단계의 위치와 테스트)
| # | 흐름 | 코드 | 테스트 |
|---|---|---|---|
| 1 | 가입: 규칙 검사 → scrypt 해시 → users(역할은 항상 member) → 바로 로그인 | `main.py signup`, `security.check_password` | `test_signup_rules_and_cookie` |
| 2 | 로그인: 잠금 확인 → 해시 비교(없는 아이디도 가짜 해시로 같은 시간) → 세션 발급 | `main.py login`, `store.start_session` | `test_login_same_error_and_lockout` |
| 3 | 요청마다: 쿠키 → 세션 해시 → 사용자·역할을 DB에서 → 유휴 30분·절대 8시간 확인 | `main.py current_user` | `test_role_matrix` |
| 4 | 권한: 미로그인 401, 역할 없음 403, 남의 항목 404 | `require_role`, `get_item` | `test_role_matrix`, `test_row_ownership_404` |
| 5 | 비밀번호 찾기: 항상 같은 답 → 맞으면 응답 뒤(백그라운드) 1회용 토큰(30분) → 메일 또는 발송함 | `main.py forgot`·`issue_reset`, `store.send_mail`·`to_outbox` | `test_forgot_reset_flow` |
| 6 | 재설정: 토큰 소모 → 해시 교체 → 모든 세션 끊기, 자동 로그인 없음 | `main.py reset` | `test_forgot_reset_flow` |
| 7 | 임시 비밀번호: 운영자 발급 → 기존 세션 끊김 → 바꾸기 전엔 기능 403 | `temp_password`, `require_user` | `test_temp_password_forces_change` |
| 8 | 상태를 바꾸는 요청은 `X-Requested-With: fetch` 헤더가 있어야(쿠키 SameSite=Lax와 함께) | `guard_and_log` | `test_csrf_header_required` |

## 역할 표 (`tests/test_auth_api.py`의 MATRIX + 남의 항목은 `test_row_ownership_404`)
| 경로 | 로그인 안 함 | 구성원 | 운영자 |
|---|---|---|---|
| `/api/auth/me` | 401 | 200 | 200 |
| `/api/public/*`(시간표·공지처럼 공개) | 200 | 200 | 200 |
| `/api/items`(자기 것) · `/api/items/{id}` | 401 | 200 / 남의 것 404 | 200(전체) |
| `/api/admin/*` | 401 | 403 | 200 |
과제 데이터로 바꿀 때: `items`를 과제 표(예: 내 노선·신청)로, 역할 표와 MATRIX를 같이 고친다. 담당 범위가 있는 운영자(예: 노선 담당)는 `require_role` 다음에 담당 범위 조건을 SQL에 넣는다.

## 규칙 바꾸기 (`app/policy.py`) — 담당자에게 현장 말로 묻고 값으로
| 담당자에게(한 번에 하나) | 바뀌는 값 |
|---|---|
| "구성원분들은 계정을 어떻게 받으시나요?" | 직접 가입 그대로 / 명단이면 `seed.py --csv`, 가입 화면 숨김 |
| "로그인할 때 쓰는 번호가 있나요?" | `USERNAME_RE`(예: 사번 8자리 `^\d{8}$`) |
| "비밀번호를 잊으면 지금은 누구에게 연락하시나요?" | 셀프 재설정(메일) / 운영자 임시 비밀번호 |
| "운영자만 봐야 하는 정보가 있나요?" | `/api/admin` 범위, admin.html 메뉴 |
- 비밀번호 기본: 8~128자 + 영문 대·소문자·숫자·특수문자 각 1개 + 아이디 포함 금지 + 흔한 비밀번호 차단. 과제가 다른 규칙을 주면 그 값. 조합 없이 길이 위주(NIST SP 800-63B 방식)로 가려면 `REQUIRE = ()`, `PW_MIN = 15`(그것만으로 NIST 전체 준수는 아니다).

## 고른 것과 버린 것 (서술형: "왜 이렇게 했나")
| 고른 것 | 버린 대안 | 이유 |
|---|---|---|
| 빌드 없는 HTML+JS(기본) | React·Vue·Next | 설치·빌드 0분, Docker 이미지에 파일만 복사, 같은 출처라 쿠키·CORS 문제 없음. 과제가 프레임워크를 요구하면 `react/`·`vue/` |
| 서버 세션(HttpOnly 쿠키, DB엔 해시) | JWT를 JS 저장소에 | 로그아웃·역할 변경·재설정이 즉시 반영, XSS로 토큰이 새지 않음, 설명이 쉽다 |
| scrypt(표준 라이브러리) | bcrypt·argon2 | 추가 설치 없음. 파라미터를 해시에 같이 저장해 나중에 올릴 수 있다 |
| SameSite=Lax + 커스텀 헤더 | CSRF 토큰 | 사내·시험 수준에서 충분하다고 본 [가정]. 외부 공개 서비스면 토큰 추가 |
| 메모리 잠금 카운터 | DB 표 | 워커 1개 전제. 재시작하면 초기화(한계로 적는다) |

## 로그인이 안 될 때 (먼저 볼 7가지)
1. http인데 `COOKIE_SECURE=1` → 쿠키가 안 붙는다. https일 때만 켠다.
2. 화면과 API의 주소(포트)가 다르다 → 쿠키·CORS. 기본은 FastAPI가 화면도 같이 서빙.
3. 계정이 없다 → `seed.py --demo`를 먼저(비밀번호는 그때 한 번만 출력).
4. DB 파일 위치(`APP_DB`)가 바뀌었거나 컨테이너 안이라 재생성 때 사라짐 → 볼륨(`/data/app.db`).
5. 5번 틀려 15분 잠김(429) → 재설정하거나 서버 재시작(메모리 카운터).
6. 화면 JS를 고쳤는데 그대로 → 브라우저 캐시. Ctrl+Shift+R.
7. 상태를 바꾸는 요청이 403 "요청 형식" → `api.js`를 안 거친 fetch(헤더 `X-Requested-With: fetch` 누락).

## 현업 수준 체크
1. 비밀번호 규칙이 서버에서 검사되고 화면 체크리스트와 같다(규칙은 policy.py 한 곳)
2. 해시만 저장, 로그·화면·응답에 비밀번호·토큰 없음(서버 로그는 경로·상태·시간만)
3. 로그인 실패 문구가 아이디 존재를 드러내지 않고, 실패 제한이 있다
4. 권한은 서버 의존성으로 막고(화면 숨김은 편의), 남의 행은 404
5. 재설정 토큰: 1회용·만료·해시 저장·재설정 뒤 세션 폐기·자동 로그인 없음
6. 역할 표와 MATRIX 테스트가 같고, PASS 건수가 0이 아니다
7. 쿠키 HttpOnly·SameSite, https면 Secure. 보안 헤더(nosniff·Referrer-Policy·no-store)
8. 화면 클릭 확인은 HUMAN_CHECK로 따로 적었다
