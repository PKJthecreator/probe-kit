# agent — 챗봇·LLM 에이전트·RAG

쓰는 때: 설비·품질 질의 챗봇, 문서 근거 답변(RAG), 도구를 부르는 업무 에이전트, 보고서 초안 생성.
첫 명령: `python agent.py --demo` · `python rag.py --demo` → 도구 함수와 `Deps`를 과제 데이터로 바꾼다.
필요: 표준 라이브러리만(FakeLLM). OpenAI는 `openai` 패키지 + `OPENAI_API_KEY` + `OPENAI_MODEL`이 과제에서 주어질 때만. 개인 키는 쓰지 않는다.
웹으로 내보내기: `../web-api/app/main.py`의 lifespan에서 `app.state.llm = make_llm()`로 한 번 만들고 `/api/chat`에서 `answer(q, deps, app.state.llm)` 호출.
알람 분류 + 조치 문서 검색(구현형 과제)을 한 엔드포인트로:
```python
INDEX = BM25(chunk("docs"))          # 시작할 때 한 번(lifespan)
@app.post("/api/triage")
def triage(m: Measurement):
    status, reasons = rules.judge(m.temperature, m.pressure)          # 판정은 규칙
    hits = INDEX.search(" ".join(reasons) or "정상 운전", k=2)          # 근거는 검색, 없으면 []
    return {"status": status, "reasons": reasons, "actions": [{"source": h["source"], "text": h["text"]} for h in hits]}
```

| 파일 | 하는 일 |
|---|---|
| `agent.py` | 도구=순수 함수+의존성 주입, 라우팅(도구 불필요 질의는 바로), 도구 실패 격리·허용 목록, LLM은 `{번호.필드}` 자리표시자만 쓰고 값은 코드가 채움, 직접 쓴 숫자면 재작성 1회 → 사실 카드만 |
| `rag.py` | 문단 청크 + BM25(한글 2-gram), 출처 `파일:줄`, 낮은 점수면 근거 없음, hit@k·MRR 평가, 임베딩 검색과 합칠 때 RRF |
| `eval.py` | 고정 질의 평가 세트(도구 호출·포함·금지·검증 통과), 고치기 전·후 비교 |
| `graph.py` | (과제가 LangGraph를 요구하거나 분기·세션이 늘 때만, `pip install langgraph` 필요) 같은 흐름의 LangGraph 판(plan→lookup→compose→check→재작성 1회→finalize), partial 의존성 주입, thread_id 상태 |

## 기술 후보
| 층 | 후보 | 언제 |
|---|---|---|
| 구조 | **에이전트 하나 + 도구 + RAG**, 멀티 에이전트 | 멀티 에이전트·지휘 에이전트는 토큰·지연이 몇 배. 독립 작업이 크고 많을 때만 |
| 오케스트레이션 | **순수 파이썬 루프(이 뼈대)**, OpenAI Agents SDK(`function_tool`·가드레일·`needs_approval`), LangGraph(상태·분기·체크포인터), LangChain | 분기·재시도·사람 승인 대기가 실제로 필요할 때만 프레임워크 |
| 도구 호출 | **함수 스키마 + 허용 목록 + 인자 검증**, MCP 서버(`../mcp/server.py`) | 조회는 Tool, 고정 문서는 Resource |
| 검색(RAG) | **BM25(설치 불필요)**, 하이브리드(BM25+임베딩), FAISS·Chroma | 문서가 많고 임베딩 키가 있을 때만 벡터 검색 |
| 출력 통제 | **자리표시자(값은 코드가 채움) + 재작성 1회 + 사실 카드**, Pydantic 구조화 출력, 가드레일 | 숫자·판정이 들어가는 답은 항상 |
| 세션 | 메모리 dict(시험), **SQLite 체크포인터**(재시작 후에도 이력 유지) | 대화 이력이 요구될 때 |
| 응답 방식 | 단발 응답, SSE 스트리밍(FastAPI `StreamingResponse`) | 답이 길거나 단계 진행을 보여야 할 때 |
| 비용·지연 | 분류는 작은 모델·작성은 큰 모델, 독립 도구는 `asyncio.gather(..., return_exceptions=True)` | 호출이 많을 때 |
| 파인튜닝 | LoRA·SFT(PEFT) | 180분 과제에선 거의 안 한다. 프롬프트·검색 기준선과 비교할 데이터·GPU·평가셋이 있을 때만 |

## 현업 수준 체크
1. 계산·판정은 코드(도구·규칙), LLM은 도구 선택과 문장만. 숫자·상태는 코드가 채우고, 화면은 코드가 만든 사실 카드를 기준으로 보여 준다
2. 도구는 허용 목록·인자 검증·실패 격리가 있고, 상태를 바꾸는 도구는 사람 승인 뒤에만 실행된다
3. 근거가 없으면 "모른다/찾지 못했다"로 답하는 경로가 테스트돼 있다. 근거는 문서 원문과 출처 ID를 그대로 붙인다(의역해 인용하지 않음)
4. LLM·에이전트 객체는 요청마다 만들지 않고 시작할 때 한 번(lifespan)
5. FakeLLM으로 흐름·테스트를 끝까지 돌렸고, 실제 모델 연결은 했으면 PASS·안 했으면 NOT_RUN으로 구분해 적었다
6. 평가 세트(`eval.py`): 정상 질의·없는 대상·근거 없는 질의·도구 실패·숫자 환각 각 1건 이상, 결과 파일로 남김(검색은 hit@k·MRR)
8. 외부 호출 도구는 시간 제한과 일시적 오류 재시도(`retry`), 입력 오류는 재시도하지 않는다
7. 키·개인정보는 코드·로그·답변에 남기지 않았다
