# mcp — 주제별 MCP 서버(공개 정보 가져오기)와 읽기 전용 서버 뼈대

## 시험에서 연결하는 법
- 필요할 때만 시험 화면의 MCP 탭에서 서버 설정 JSON을 저장한다. 그러면 준비된 Codex 설정에 반영된다. `~/.codex/config.toml`은 플랫폼이 관리하니 직접 고치지 않는다.
- 형식(작업 폴더의 `.mcp.json`과 같은 모양): `{"mcpServers": {"이름": {"url": "https://…"}}}` — 원격(Streamable HTTP). 로컬 실행은 `{"이름": {"command": "npx", "args": […]}}`.
- 붙여넣기가 막혀 있으면 아래 표의 한 줄 JSON을 직접 친다. 원격 URL 방식이 짧다.
- 확인: 저장 → Codex에서 `/mcp`로 서버·도구가 보이는지 → 공개 질의 한 번 → 결정 절 한 줄(무엇을·왜·밖으로 간 것). 안 되면 우회하지 않고 웹 검색·공식 문서, 표준 라이브러리는 오프라인 `python -m pydoc sqlite3`처럼 본다.

## 원칙
- 기본 0개, 필요하면 1개부터. 서버마다 도구 설명이 대화에 들어가 토큰이 늘어난다.
- 보내도 되는 것: 공개 일반 질의(라이브러리·API 이름, 공개 저장소·데이터셋 이름). 보내지 않는 것: 문제 문장, 과제 파일·데이터·코드·결과물·화면, 과제를 짐작할 수 있는 비공개 맥락(시험 규정: 외부 전송 금지·Outbound 모니터링).
- 쓰기·업로드·실행 도구(`submit_feedback`, `update_*`, `create_*`, 업로드)는 호출하지 않는다.
- `npx` 서버는 첫 실행에 패키지를 내려받는다(외부 통신 + 새 설치) → AGENTS 2대로 승인 후, Node·브라우저가 있는지 먼저 본다.
- 셸로 되는 일(파일·DB·pandas·mlflow·kubectl·docker·날짜)은 MCP로 하지 않는다.

## 주제별 서버
실측 = 2026-10-30 이 PC에서 키 없이 initialize → tools/list(일부는 공개 질의까지). 시험 화면에서의 동작은 [미확인].

| 주제 | 한 줄 JSON(`mcpServers` 안에 넣는 값) | 도구 | 실측 | 주의 |
|---|---|---|---|---|
| 모든 주제의 라이브러리 문법(pandas·scikit-learn·FastAPI·Vue·React·Spring …) | `"context7": {"url": "https://mcp.context7.com/mcp"}` | resolve-library-id, query-docs | 연결·'fastapi' 조회 OK | 라이브러리 이름과 일반 질문만 보낸다 |
| 공개 GitHub 라이브러리 구조·사용법 | `"deepwiki": {"url": "https://mcp.deepwiki.com/mcp"}` | read_wiki_structure·contents, ask_wiki_question(공식 문서엔 ask_question, 10/30 실제 서버 이름) | 연결·fastapi 위키 조회 OK | 답은 생성 요약이라 원문과 대조 |
| OpenAI API·Agents SDK·Codex | `"openai-docs": {"url": "https://developers.openai.com/mcp"}` | search·fetch docs, openapi spec | 연결 OK | |
| LangChain·LangGraph | `"langchain-docs": {"url": "https://docs.langchain.com/mcp"}` | search_docs, query_docs_filesystem | 연결 OK | `submit_feedback`(쓰기) 금지 |
| 공개 데이터셋·사전학습 모델 찾기 | `"huggingface": {"url": "https://huggingface.co/mcp"}` | 익명: hub_repo_search·details, hf_fs, hf_whoami | 연결·'secom' 검색 OK | 과제 데이터로 검색하지 않는다 |
| 외부 공공데이터를 붙여야 하는 과제(어떤 데이터가 있나) | `"data-lens": {"url": "https://service.datahub.kr/projects/public-data-lens/mcp"}` | search_datasets, get_dataset_structure 등 9개 | 연결 OK | 카탈로그만(실데이터 아님). 막히면 웹 검색 |
| Azure·.NET | `"ms-learn": {"url": "https://learn.microsoft.com/api/mcp"}` | docs search·fetch, code samples | 연결 OK | 드물다 |
| 웹 화면 자동 점검 | `"playwright": {"command": "npx", "args": ["-y", "@playwright/mcp@latest", "--headless"]}` | 브라우저 조작 | NOT_RUN(이 PC 정책) | 설치·브라우저·허용 확인 뒤만. localhost 화면도 외부 JS·폰트를 부를 수 있다. 안 되면 사용자 HUMAN_CHECK |
| (대안) 웹 성능·콘솔 | `"chrome-devtools": {"command": "npx", "args": ["-y", "chrome-devtools-mcp@latest", "--headless", "--no-usage-statistics", "--no-performance-crux"], "env": {"CHROME_DEVTOOLS_MCP_NO_UPDATE_CHECKS": "1"}}` | DevTools | NOT_RUN | Chrome 필요. 사용 통계·CrUX(URL을 Google로 조회)·업데이트 확인을 끈 설정이지만 방문 페이지 통신은 남는다 |
| 데이터·SQL·MLOps·DevOps·시간 | 없음 — 셸로(pandas·sqlite3·mlflow·kubectl·docker) | | | 서버·클러스터가 주어지고 과제가 요구할 때만 MLflow 공식 MCP(`uv`)·kubernetes-mcp-server |
| MCP 서버를 만들라는 과제 | `server.py`(이 폴더) | | 자체 점검 OK | 아래 |

예(직접 칠 한 줄): `{"mcpServers": {"context7": {"url": "https://mcp.context7.com/mcp"}}}`

## 쓰지 않는 것
- 개인 키·계정이 필요한 것: 공공데이터포털(data.go.kr) 계열·KOSIS·기상청·KOSHA MCP(서비스키), GitHub MCP(토큰), Kaggle(연결은 되나 익명 검색 실패, 쓰기 도구 섞임).
- 보관·미유지: 예전 SQLite 참조 서버(modelcontextprotocol/servers-archived).
- 셸과 겹치는 것: 파일시스템·DB·Docker·시간·순차 사고 서버.
- 한국 MCP를 더 찾을 때: GitHub `darjeeling/awesome-mcp-korea` 목록(대부분 키 필요).

## server.py (MCP 서버를 만들어야 할 때)
- 시점마다 값이 바뀌는 조회는 Tool, 고정 규칙·문서는 Resource. 상태를 바꾸는 도구는 승인 흐름 없이 넣지 않는다.
- 확인: `python -c "import server; print(server.get_defect_rate('EQ-002'))"`, 연결은 MCP 탭에 `{"mcpServers": {"local": {"command": "python", "args": ["server.py"]}}}` 저장 뒤 `/mcp`.
