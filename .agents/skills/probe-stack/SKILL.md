---
name: probe-stack
description: 과제 유형이 정해진 뒤 기술 스택을 사용자에게 후보 표로 물어 고르고 probe-kit 뼈대(templates/)에서 필요한 파일만 가져오는 단계, 그리고 첫 완주 뒤와 verify 때 결과물이 현업 수준인지 주제별 체크리스트로 점검하는 단계. 웹 서비스(FastAPI·React·Vue·MSA), 챗봇·에이전트·RAG(LangChain·LangGraph·OpenAI), 데이터 분석·예측(sklearn·부스팅·파생변수·SPC·6시그마), 시계열, MLOps(MLflow·드리프트), DevOps(Docker·CI), MCP. Use for tech stack choice, boilerplate, templates, production-quality checklist.
---

# probe-stack — 기술 고르기와 현업 수준 점검

지침 파일(`~/probe-kit/AGENTS.md`, 킷을 다른 곳에 뒀으면 그 경로)을 새 세션이거나 대화가 압축됐거나 지침이 불확실하면 먼저 다시 읽는다.

## 언제
- A. 고르기: probe-frame에서 과제 유형을 보고한 뒤, BRIEF 합의(카드 ③-2)와 **같은 메시지에서 한 번**. 따로 멈추는 단계를 만들지 않는다. frame 빠른 경로면 후보 표도 3줄 이내.
- B. 점검: 첫 완주 직후 한 번, probe-verify 때 한 번 전체 표. 그 사이에는 AGENTS 6의 단계 4줄 보고 "어디서 틀릴 수 있나"에 이번 단계와 관련해 미확인이거나 미충족인 필수 항목 하나만(커밋마다 표를 다시 내지 않는다).
- C. 다시 묻기: 진행 중 새 층(저장·인증·외부 연결·차트·배포·LLM·검색)이 생겨 요구·사용자 경험·보안·시간에 실제 영향이 있으면 그 층만 표 한 줄(추천/대안)로 묻는다. 이미 합의·위임한 것이나 되돌리기 쉬운 세부(이름·색·문구)는 묻지 않고 결정 절에 적은 뒤 진행한다.

## 주제 → 핵심 기술 한눈 표 (자세한 후보·사용 조건·현업 체크는 해당 README)
| 주제 | 핵심 기술 | README |
|---|---|---|
| 웹 서비스 | 백엔드 FastAPI·Spring Boot / 화면 HTML·CSS·JS, Vue·React(Vite)·Next.js / 저장 SQLite·PostgreSQL / 실시간 SSE / 구조 단일 서비스 → MSA(게이트웨이·Kafka) | `web-api` |
| 설치 없는 업무 도구 | HTML 한 파일·FileReader·일반 텍스트 보고·확인 체크, Vite 결과 인라인 | `static-tool` |
| 챗봇·에이전트 | Agents SDK·LangGraph·LangChain / 도구 호출 / RAG(BM25 → 임베딩·FAISS·Chroma) / 구조화 출력·가드레일 / 평가 세트 / 파인튜닝 LoRA(조건부) | `agent` |
| 예측 | sklearn Pipeline·부스팅(HGB·LightGBM·XGBoost)·파생변수(시차·SPC)·불균형·임계값·순열 중요도 / 딥러닝 LSTM·CNN(조건부) | `data-ml` |
| 분석·통계 | pandas·SQL 집계, 시각화, 통계 검정, 공선성, 군집·차원축소, 이상치, SPC·공정능력 | `data-ml` |
| 시계열 | 계절 기준선·전역 부스팅·롤링 백테스트·WAPE / ETS·Croston·LSTM(조건부) | `timeseries` |
| MLOps | 레지스트리·게이트·사람 승인 승격·롤백·드리프트, MLflow | `mlops` |
| DevOps | Docker·compose·CI(GitHub Actions·Jenkins)·K8s(조건부) | `ops` |
| MCP | 문서 조회 서버(기본 미연결), 읽기 전용 서버 | `mcp` |

## A. 고르기 (5분 이내)
1. 설치 확인(읽기 전용, 한 번):
   `python3 -c "import importlib.util as u; print({m: bool(u.find_spec(m)) for m in ['pandas','sklearn','lightgbm','xgboost','fastapi','uvicorn','httpx','pytest','openai','langgraph','mlflow','mcp']})"; node -v; docker --version`
2. 형태는 개발 PC가 아니라 **받는 사람의 환경**(인터넷·설치·서버·저장 가능 여부, frame 점검표 ⑥)으로 정한다. 설치·서버가 안 되면 `static-tool`. 영속 저장이 꼭 필요한데 설치·서버·저장이 모두 안 되면 형태를 임의로 고르지 말고 요구 충돌을 담당자에게 알려 정한다. 받는 사람 환경을 모르면 담당자에게 기술 이름 말고 사용 조건을 묻는다: "실제로 어디서 쓰세요? 인터넷·프로그램 설치가 되나요?"(형태·외부 호출) / "결과를 나중에도 남겨야 하나요, 다른 분도 이어서 보나요?"(저장) / "결과를 다음 사람에게 지금은 어떤 모양으로 넘기세요?"(출력 형식).
   `~/probe-kit/templates/README.md`의 "흔한 과제" 표에서 맞는 행을 고른다(섞였으면 주 산출물 하나 + 보조 하나). **고른 폴더의 README.md만** 읽는다.
3. 사용자에게 후보 표 하나로 묻는다.
   - 형식: `| 층 | 추천 (설치·시간·이유) | 대안 (설치·시간·이유) |`. 예: `| 저장 | SQLite (설치 없음·10분·단일 서비스) | PostgreSQL (서버 필요·30분+·동시 쓰기) |`. 설치 여부를 확인 못 했으면 `[미확인]`, 시간은 `[추정]`.
   - 형태(서버형·HTML 한 파일·스크립트 산출물)가 아직 안 정해졌고 선택에 중요하면 첫 행에서 형태부터, 그 형태 안의 층만 잇는다.
   - 층은 최대 4개(예: 모델·분할·화면·저장). 층마다 `추천 / 대안 1개`.
   - 과제 README·담당자 답이 이미 정한 층은 묻지 않고 `고정`으로 적는다.
   - 추천 기준(앞이 우선): 과제 요구 > 이미 설치됨 > 35% 안에 완주 가능 > 내가 설명할 수 있음 > 현업 표준.
   - 사용자가 고르거나 "추천대로"라고 하면 결정 절에 한 줄(버린 대안과 이유 포함). "알아서"면 추천으로 정하고 `(위임)`.
4. 뼈대 가져오기
   - 필요한 파일만 이름을 적어 복사한다: `cp ~/probe-kit/templates/<폴더>/<파일> <과제 경로>/`. 같은 이름이 있으면 덮어쓰기 전에 diff를 본다. 폴더 통째(`cp -r`)는 쓰지 않는다.
   - 복사만 한 상태로 바로 commit: `chore: probe-kit 뼈대 복사(templates/<폴더>/<파일>), 이후 과제에 맞게 수정`. 이후 diff가 내 작업으로 구분된다.
   - 자체 점검(`--demo` 또는 `python 파일.py`)을 한 번 돌려 이 환경에서 도는지 본다. 그다음 과제 열·규칙·경로로 고치고, 쓰지 않는 함수·옵션·예시 값은 지운다.
   - 뼈대가 과제와 맞지 않으면 억지로 쓰지 않고 직접 짧게 쓴다.
5. 새 설치가 필요하면 AGENTS 2대로 승인 후. 승인이 없으면 설치 없는 대안으로 간다.

## B. 현업 수준 점검
- 고른 폴더 README의 "현업 수준 체크"를 BRIEF 성공 기준과 함께 본다.
- 항목마다 `✓`(근거: 파일:줄·결과 파일·테스트) / `✗`(이유, 고칠지) / `생략`(과제 범위 밖, 이유).
- `✗` 중 필수 요구·입력 검증·누수·보안에 걸리는 것은 바로 다음 작업으로. 나머지는 인계 절 한계에 적는다.
- verify 때 필수 항목이 `✗`면 FAIL, 확인 못 했으면 NOT_RUN으로 적고 완료·PASS로 쓰지 않는다. 범위 밖·선택 항목만 `생략`이나 한계로 둔다.
- 70%가 지나면 `✗`를 새 기능으로 고치지 않고 한계로 적는다(AGENTS 8).
- 보고: `STACK | 체크 n/m ✓ | ✗: … | 생략: …` 한 줄과 `✗` 항목 표(최대 4행).

## 하지 말 것
- 모든 템플릿 폴더를 읽거나 복사하기.
- 과제가 요구하지 않은 MSA·Docker·MLflow·MCP·프레임워크를 "현업처럼 보이게" 넣기.
- 뼈대의 예시 값(rules.py 임계값, agent.py의 Deps 데이터, 데모 열 이름)을 과제 값으로 남겨 두기.
- 원격 MCP에 과제 데이터·코드·문제 문장 보내기(`templates/mcp/README.md`).
