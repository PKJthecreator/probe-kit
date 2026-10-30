# web-api — 웹 서비스(백엔드 API + 화면)

쓰는 때: 판정·조회·등록 기능이 있는 웹 앱, 대시보드, 모델·에이전트를 API로 내보내기.
첫 명령(이 폴더에서): `python -m pytest -q tests` → `uvicorn app.main:app --host 0.0.0.0 --port 8000` (전용 터미널) → 사용자가 `/`와 `/docs`를 직접 연다.
필요: fastapi, uvicorn(테스트는 pytest, httpx). 없으면 설치 승인을 받거나 표준 라이브러리 `http.server`로 줄인다.

| 파일 | 하는 일 |
|---|---|
| `app/rules.py` | 판정 기준·경계값 한 곳(담당자가 고칠 값). 바꾸면 VERSION을 올린다 |
| `app/main.py` | Pydantic 입력 검증(422), 규칙 판정, 요청별 SQLite 연결(WAL), 공통 500 응답, `/health`·`/readyz`, 정적 화면 |
| `static/index.html` | 입력 → fetch → 결과·로딩·오류 표시(바닐라 JS, 빌드 없음) |
| `tests/test_api.py` | 정상·경계(80.0, 10.0)·실패(422·404)·이력 순서 |
| `vue/JudgeForm.vue` | 과제가 Vue(Vite) 골격을 줬을 때: `<script setup>` 폼 → 로딩 → 오류·결과, 부모에 emit. 받는 쪽이 설치 불가면 빌드 뒤 `static-tool/build.mjs --vite` |

## 기술 후보
| 층 | 후보 | 언제 |
|---|---|---|
| 백엔드 | **FastAPI**(Swagger `/docs` 자동), Flask, Spring Boot(Java 과제·기존 코드가 Java일 때) | 파이썬 데이터·모델과 붙일 때 FastAPI |
| 화면 | **정적 HTML+JS(빌드 없음)**, Vue 3·React(Vite), Next.js(SSR·라우팅 필요할 때), Streamlit·Gradio(데이터 데모) | npm 설치·빌드 시간이 있으면 Vite: `npm create vite@latest web -- --template react-ts`(또는 vue-ts) |
| 화면 스타일 | **기본 CSS**(시스템 글꼴, 폼·표 정렬, 좁은 화면 1단, `label`·`aria-live`), Tailwind·Bootstrap | CSS 프레임워크는 npm 설치가 되고 CDN이 막혀 있지 않을 때만. 인터넷 없는 PC면 기본 CSS |
| 저장 | **SQLite(표준 라이브러리)**, PostgreSQL(compose), SQLAlchemy ORM | 동시 쓰기·여러 서비스가 같은 DB를 쓰면 PostgreSQL |
| 실시간 | 폴링, **SSE(`StreamingResponse`, `text/event-stream`)**, WebSocket | 긴 작업 진행·LLM 토큰 스트리밍은 SSE |
| 구조 | **단일 서비스 + 모듈 분리(routers·rules·repository)**, MSA(서비스별 DB·API 게이트웨이·Kafka 이벤트) | MSA는 과제가 명시할 때만. 아니면 경계만 나눠 둔다 |
| 인증 | 없음(시험), API 키 헤더, OAuth2/JWT(`fastapi.security`) | 과제가 사용자 구분을 요구할 때 |
| 배포 | uvicorn 직접, Docker·compose(`../ops`) | 과제가 컨테이너를 요구할 때 |

## 현업 수준 체크
1. 입력 스키마로 범위·길이를 검증한다(잘못된 입력은 422, 없는 대상은 404, 내부 오류는 내용 숨기고 500)
2. 판정 기준·임계값이 한 파일에 있고, 경계값 포함 여부를 테스트로 고정했다
3. 핵심 사용자 행동 하나가 화면 → API → 저장 → 조회까지 동작하고, 로딩·빈 결과·오류가 화면에 보인다
4. `/docs`(OpenAPI)와 실행 방법이 README(과제 지정 문서)에 있다. 서버는 0.0.0.0, 포트를 알렸다
5. DB 연결을 스레드 간 공유하지 않고, 쓰기는 트랜잭션. SQL은 파라미터 바인딩(문자열 이어붙이기 금지)
6. 비밀값은 환경변수, 로그에는 요청 경로·상태·지연만(개인정보·키 없음)
7. 화면 클릭 확인은 사용자 HUMAN_CHECK, 자동 테스트는 PASS/FAIL로 구분해 적었다
8. 입력마다 라벨, 오류 문구가 어느 칸 문제인지 알려 주고, 좁은 화면에서도 깨지지 않는다
9. 오류 응답 형식이 한 가지다(검증 422는 칸별, 업무 오류 404·409는 `detail`, 500은 내부 내용 숨김)
10. 화면을 붙이기 전에 `/docs`의 Try it out이나 curl로 요청·응답 모양을 먼저 확인했다
