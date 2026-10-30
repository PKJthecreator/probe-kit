# mlops — 모델 등록·승격·롤백·드리프트 감시

쓰는 때: "모델을 운영에 올리고 바꾸는 절차", 재학습 조건, 성능 저하 감시, 모델 버전 관리가 과제에 있을 때.
첫 명령: `python registry.py` (자체 점검). 학습 코드(`../data-ml/train.py`)의 결과를 `register()`로 넣는다.
필요: 표준 라이브러리만. MLflow가 설치돼 있으면 같은 개념으로 옮길 수 있다(아래).

`serve.py`(과제가 모델 운영 API를 요구할 때만): FastAPI 운영 API — `/predict`(응답에 모델 버전, 요청 기록) → `/feedback`(실측 → 잔차 → 드리프트 경보, 기준이 없으면 처음 n건으로 잡음) → `/model/promote`·`/model/rollback`(confirm·approver 필수, 재기동 없이 반영). `python serve.py`로 자체 점검(fastapi·httpx 필요).

하는 일: 버전 등록(그룹별 지표·데이터 해시) → `gate()`(그룹마다 절대 기준 이하 + 현행 대비 비악화, 경계값 포함 통과) → `promote(confirm=True, approver=...)` 사람 승인 승격 → `rollback()` 직전 버전 복귀 → `ResidualDrift`(잔차 3σ, 최근 5개 중 2개 이탈이면 경보) · `psi()`(입력 분포 변화).

## 기술 후보
| 층 | 후보 | 언제 |
|---|---|---|
| 실험 기록 | **outputs/metrics.json + git commit**, MLflow Tracking(`mlflow.log_params/log_metrics/log_artifact`) | 실험이 많고 UI 비교가 필요할 때 MLflow |
| 레지스트리 | **파일 기반(이 뼈대)**, MLflow Model Registry(alias `champion`·`challenger`) | 여러 사람이 같은 모델을 쓸 때 MLflow |
| 승격 | **게이트 + 사람 승인**, 섀도(병행) 평가, 카나리 | 자동 승격은 하지 않는다 |
| 감시 | **잔차 관리도·PSI**, Evidently(설치 시), Prometheus 지표 | 경보와 재학습은 분리: 경보 → 후보 학습 → 게이트 → 승인 |
| 재학습 | 전체 재학습, warm start 미세조정(데이터 적을 때) | 최근 데이터만으로 처음부터 학습하면 불안정 |
| 서빙 | FastAPI(`../web-api`), 응답에 모델 버전 표시 | 승격 뒤 재기동 전까지 옛 버전이 응답할 수 있다 |

MLflow로 옮길 때: `mlflow.set_tracking_uri("sqlite:///mlflow.db")` → `with mlflow.start_run(): mlflow.log_metrics(...); mlflow.sklearn.log_model(model, name="model", registered_model_name="m")` → `MlflowClient().set_registered_model_alias("m", "champion", version)`.

## 현업 수준 체크
1. 학습·서빙이 같은 전처리·특징 정의를 공유한다(한 모듈에서 import)
2. 버전마다 데이터 해시·지표·생성 시각이 남고, 응답·로그에 실제 서빙 버전이 보인다
3. 승격은 게이트 통과 + 사람 승인, 롤백 경로를 실제로 한 번 실행해 봤다
4. 드리프트 경보 기준(σ·확인 창)과 재학습 조건(피드백 n건 이상 등)을 숫자로 적었다
5. 게이트 경계값(정확히 기준과 같은 값)이 통과인지 테스트로 고정했다
6. 모델은 요청마다 읽지 않고 시작할 때·승격할 때만 읽는다(지연)
7. 정규화해서 학습했으면 응답 전에 원래 단위로 되돌린다(역변환)는 것을 테스트로 확인했다
8. 드리프트는 최소 표본(기준 n건)과 확인 창(최근 5건 중 2건)을 넘어야 경보 — 한두 건으로 재학습하지 않는다
