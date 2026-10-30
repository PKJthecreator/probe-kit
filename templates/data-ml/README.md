# data-ml — 표 데이터 예측·분류·품질 분석

쓰는 때: 불량·이상 예측, 수율·계측값 회귀, 공정 데이터 분석, 6시그마·SPC 판정.
첫 명령: `python check_data.py train.csv --target y --time date --id id --test test.csv` → `python train.py --train train.csv --target y --time date --id id --test test.csv --sample sample_submission.csv`
필요: pandas, scikit-learn(LightGBM·XGBoost는 설치돼 있으면 자동 추가, 없으면 HistGradientBoosting으로 대신). 각 파일은 `--demo` 또는 `python 파일.py`로 자체 점검된다.

| 파일 | 하는 일 |
|---|---|
| `check_data.py` | 행·열·결측·중복·키·누수 후보·기간별 변화·test 새 범주 (probe-data-check 1) |
| `train.py` | 시간·그룹·무작위 분할, 기준선(dummy·선형) + 부스팅, 학습·검증 나란히, 혼동행렬, 순열 중요도, `--final` holdout 1회, 제출 파일 |
| `features.py` | 대상별 시차·이동통계(shift로 누수 차단), 학습 분할로만 fit하는 SPC z점수·3σ 이탈, 의미 있는 비율 |
| `spc.py` | I-MR 관리한계(MR/1.128), Western Electric 규칙, Cp·Cpk, 추적 신호 |
| `analyze.py` | 그룹별 분모·평균·중앙값·비율, 전체 대비 차이·효과 크기, scipy 검정(있을 때), 같은 집계를 SQL(sqlite3)로 재계산해 대조 |
| `train.py --cv k` | 후보를 k겹 교차검증 평균±표준편차로 비교(시간→TimeSeriesSplit, 그룹→GroupKFold, 분류→층화). 양성이 적거나 차이가 작을 때 |

## 기술 후보 (사용자가 고른다. 추천은 굵게)
| 층 | 후보 | 언제 |
|---|---|---|
| 기준선 | **Dummy + 로지스틱/Ridge**, 규칙 하나(임계값) | 항상 먼저. 복잡한 모델은 기준선이 왜 실패하는지 설명된 뒤 |
| 주력 모델 | **HistGradientBoosting**(scikit-learn만 있으면 됨), LightGBM, XGBoost, RandomForest | 표 데이터 기본. HGB는 결측을 그대로 처리(다른 모델은 설치 버전의 결측 지원을 확인하고 안 되면 파이프라인 안에서 대체) |
| 불균형 | **class_weight="balanced" + 검증에서 임계값 선택**, PR-AUC, SMOTE(imbalanced-learn) | 양성이 적을 때. SMOTE는 학습 분할 안에서만 |
| 이상 탐지(라벨 없음) | **IsolationForest**, One-Class SVM, SPC 3σ 규칙 | 불량 라벨이 거의 없을 때 |
| 파생변수 | **시차·이동통계(대상별)**, SPC z·이탈, 비율·차이, 시간 구간 | 공정 데이터. 설명할 수 있는 것만 |
| 해석 | **순열 중요도 + 그룹별 표**, SHAP(설치돼 있으면), 부분의존 | 중요도는 관계의 크기, 원인 아님 |
| 튜닝 | **기본값 → 1~2개 하이퍼파라미터만**, Optuna(설치 시) | 70% 이후에는 하지 않는다 |
| 시계열 | `../timeseries/` | 미래 값 예측 |
| 딥러닝 | PyTorch·Keras의 LSTM(순차)·CNN(웨이퍼맵 같은 이미지) | 과제가 요구하거나 데이터 형태·시간·실행 환경이 맞을 때만. 표 데이터는 부스팅 우선, 같은 분할에서 기준선과 비교 |

## 집계·분석·통계 (모델을 만들지 않는 과제, 또는 모델 전 분석)
| 층 | 후보 | 언제 |
|---|---|---|
| 집계 | **pandas groupby·pivot**, SQL(sqlite3 표준, duckdb 설치 시, PostgreSQL 서버가 있을 때) | 원본이 DB면 SQL, 파일이면 pandas. 결과 숫자는 다른 방법으로 한 번 더 계산 |
| 시각화 | **matplotlib → PNG**, plotly(설치 시, HTML 한 파일에 내장) | 그림이 결론을 뒷받침할 때만. 인터넷 없는 곳에 줄 거면 PNG |
| 비교·검정 | scipy.stats: t-검정·ANOVA·카이제곱·Mann-Whitney(정규성 의심 시) | 그룹 차이를 주장할 때(6시그마 Analyze). 효과 크기·신뢰구간과 함께, 여러 번 비교하면 보정 |
| 관계 | 상관 행렬·VIF(공선성), 회귀 계수 | 변수끼리 너무 닮았는지 볼 때. 관계이지 원인 아님 |
| 구조 찾기 | StandardScaler → PCA, KMeans(실루엣으로 k 확인) | 라벨 없이 패턴·그룹을 찾을 때. 각각 필요할 때만 |
| 이상치 | IQR, 3σ(관리도), 다변량 IsolationForest | 지우기 전에 기록 오류인지 실제 공정 특성인지 구분(data-check 4) |
| 회귀 진단 | 수정 R², 잔차 등분산(Breusch-Pagan)·정규성(Q-Q), 조건수·VIF(statsmodels 있을 때) | 회귀 계수로 설명할 때. 비선형이면 2차항·로그 변환을 설명력 증가분으로 비교해 고른다 |

## 현업 수준 체크 (첫 완주 뒤·wrap 전에 ✓/✗/생략(이유)로 보고)
1. 분할이 사용 장면과 맞다(시간·그룹·무작위 이유 한 줄), 전처리는 파이프라인 안에서 학습 분할로만 fit
2. 기준선과 같은 분할·지표·seed로 나란히 비교했다(`outputs/metrics.json`)
3. 누수 점검: 예측 시점에 모르는 열, 이름이 판정·결과인 열, 혼자 점수를 올리는 열을 뺐거나 이유를 적었다
4. 불균형이면 정확도 대신 PR-AUC·재현율·정밀도, 양성 개수(`n_pos`)를 함께 적었다
5. 오류 분석: `valid_predictions.csv`로 FP/FN(큰 잔차)의 공통점(설비·기간·구간)을 표로 봤다
6. 내부 holdout은 확정 뒤 `--final`로 한 번만, 그 값을 최종 성능으로 적었다
7. 제출 파일 형식·행 수·ID 문자열(앞자리 0)을 README·sample과 대조했다
8. 공정 판단이면 관리한계(데이터에서 계산)와 규격한계(고객·설계 요구)를 구분했다
9. (분석 과제) 숫자마다 분모·기간·그룹을 밝혔고, 핵심 숫자는 다른 방법으로 다시 계산해 맞췄다
10. (그림·관계를 보였다면) 그림에 축·단위·n이 있고, 상관·중요도를 원인으로 쓰지 않았다
11. (검정을 썼다면) 가정·효과 크기·다중 비교 보정을 적었다
12. (회귀 계수로 설명한다면) 수정 R²·잔차 등분산·정규성·VIF를 확인했고 어긋나면 한계로 적었다
