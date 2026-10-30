# templates — 과제 유형별 뼈대 (probe-stack이 고른다)

공개 저장소 probe-kit의 뼈대다. 시험 규정상 공개 템플릿·코드는 활용할 수 있지만 결과물을 통째로 대체하면 안 된다.
그래서 **필요한 파일만** 복사하고, 복사만 한 commit을 따로 남긴 뒤(`chore: probe-kit 뼈대 복사(templates/…)`) 과제 요구에 맞게 고친다. 쓰지 않는 함수는 지운다. 복사한 코드도 내가 설명할 수 있어야 한다(후속 서술형).
모든 `.py`는 `--demo` 또는 `python 파일.py`로 자체 점검된다. 설치가 필요한 것은 각 README 첫 줄에 적었다.
특정 과제의 실제 자료는 들어 있지 않고, 실행 예는 가상 데이터를 쓰는 범용 뼈대다.

| 흔한 과제 | 경로 | 시작 |
|---|---|---|
| 공정 센서·계측으로 불량·수율 예측(SECOM형, 불균형) | `data-ml` | `check_data.py` → `features.mark_missing` → `train.py --time/--group --cost FN:FP` |
| 웨이퍼·런 센서 로그로 계측값 회귀(가상계측, PHM CMP형) | `data-ml` | `features.aggregate_runs(step=…)` → `train.py --task reg --group 설비` |
| 관리도·공정능력·이상 판정(6시그마) | `data-ml/spc.py` | `imr_limits` → `we_rules` → `capability` |
| 그룹 비교·집계 보고(분모·효과 크기·검정, SQL로 재계산) | `data-ml/analyze.py` | `--group --value [--rate]` |
| 집계·비교·통계 분석 보고(모델 없음) | `data-ml` README의 "집계·분석·통계" 절 | pandas·SQL 집계 → 필요하면 검정·그림 → 핵심 숫자 다른 방법으로 재계산 |
| 수요·생산량·센서 다음 값 예측 | `timeseries` | `forecast.py --h --season` |
| 파일을 넣으면 보고·인계 초안이 나오는 도구, 설치·인터넷 안 되는 공용 PC | `static-tool` | `node --test` → `node build.mjs` → `file://`로 열기 |
| Vue(Vite) 골격을 받은 화면 과제 | `web-api/vue/JudgeForm.vue` | 폼·로딩·오류·결과 상태 컴포넌트, API는 `web-api` |
| Vite·React 골격을 받았는데 받는 쪽이 설치·서버 불가 | `static-tool/build.mjs --vite dist` | 빌드 결과를 HTML 한 파일로(기본 `dist/index.html`은 `file://`에서 빈 화면) |
| 판정·조회 웹 서비스(API + 화면), 서버를 띄울 수 있을 때 | `web-api` | `pytest` → `uvicorn` |
| 설비 알람 분류 + 조치 문서 근거 검색(구현형) | `web-api` + `agent` | `rules.py`로 등급 판정, `rag.py`로 SOP 검색, 둘을 `/api/triage` 하나로 묶는다(agent README) |
| 챗봇·도구 호출 에이전트 | `agent` | `agent.py --demo` → 도구·`Deps` 교체 → `eval.py`로 평가 세트. LangGraph가 요구되면 `graph.py` |
| 모델 승격·롤백·드리프트, 모델을 API로 운영 | `mlops` | `registry.py` → `serve.py`(예측·피드백·드리프트·승인 승격) |
| Docker·compose·CI·Jenkins·K8s | `ops` | 과제가 요구할 때만(`k8s/`는 `kubectl kustomize`로 검증) |
| 증거 로그·제출 파일 대조·비밀값 검사 | `harness` | 한 번에 `gate.sh --exclude 원본폴더 --test "테스트 명령" [--sample …]`, 따로 `verify.sh`·`check_submission.py`·`check_secrets.py` |
| MCP 연결(주제별 서버 표, 키 없이 연결 실측)·MCP 서버 구현 | `mcp` | 기본 0개, 필요할 때 1개. README의 원칙 먼저 |

복사 예(작업 폴더에서): `cp ~/probe-kit/templates/data-ml/train.py ~/probe-kit/templates/data-ml/check_data.py .` — 같은 이름 파일이 이미 있으면 덮어쓰기 전에 diff부터 본다.
