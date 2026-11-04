**요구·데이터가 있을 때만. 노선이 주어진 조회 과제는 해당 없음.**

# optimize — 배정·경로 최적화 뼈대

쓰는 때: 구성원·주문 같은 대상을 정원 있는 버스·창구에 나눠 담거나, 여러 지점을 도는 순서를 정해야 한다고 **과제 요구가 말할 때**. 기본으로 깔지 않는다(군집화·최적화를 넣는 것 자체가 목적이 아니다).
첫 명령(이 폴더에서): `python opt.py --demo` — 표준 라이브러리만, 0.01초, assert 통과 시 `opt.py demo OK`.
복사: `cp ~/probe-kit/templates/optimize/opt.py .` 후 복사만 한 commit을 따로 남기고(`chore: probe-kit 뼈대 복사(templates/optimize)`), 쓸 함수만 남기고 지운다. 복사한 코드도 내가 설명할 수 있어야 한다.

## 쓰기 전에 담당자·자료로 확인할 것
1. 노선·정류장·배정이 이미 데이터에 있나? → 있으면 **쓰지 않는다**(조회·표시 과제).
2. 줄이거나 맞출 목표가 무엇인가? (총 이동거리 / 탑승률 / 도보거리 / 미배정 수)
3. 어기면 안 되는 제약은? (버스 정원, 최대 도보거리, 운행 시간, 차량 수) — 세 가지가 요구·데이터에 없으면 기법 고르기 전에 요구 확인이 먼저다.
4. 목표가 둘 이상이면 합치는 방식을 하나 고른다: 가중합(단위가 다르면 가중치 근거를 담당자 답으로) / 우선순위 순(앞 목표가 같을 때만 다음 목표로 비교) / 주 목표만 최적화하고 나머지는 목표 방향에 맞는 상한·하한으로 묶기(예: 탑승률 최소치). 고른 방식과 버린 방식·이유를 결정 절에 한 줄.

## 문제 → 기법 → 쓰는 때 / 안 쓰는 때 → 서술형에서 설명할 문장
| 문제 | 기법(함수) | 쓰는 때 / 안 쓰는 때 | 서술형 문장(사실과 맞을 때만 그대로 쓴다) |
|---|---|---|---|
| 정류장이 안 정해져 있다 | k-means로 좌표 묶기(`kmeans`) | 구성원 좌표가 있고 k를 사람이 정할 수 있을 때 / 노선·정류장이 주어짐, 좌표 없이 주소 글자만 있음, 정원·도보 제약이 핵심(k-means는 모른다) | "정류장이 주어지지 않아 구성원 좌표를 k-means로 k개 묶고, 중심에 가장 가까운 구성원 위치를 정류장 후보로 삼았다. k는 내가 정했고, 정원·최대 도보거리는 k-means가 모르므로 뒤에 지표로 따로 확인했다." / 안 쓴 경우: "노선과 정류장이 CSV로 주어져 새로 만들 필요가 없어 군집화를 쓰지 않았다." |
| 정원 있는 버스에 사람 배정 | 탐욕(`assign_capacity`) | 정원+비용(도보거리)이 있고 넘치면 미배정으로 보고해도 될 때 / 총비용 최적 보장이 요구일 때, 배정이 이미 데이터에 있을 때 | "가까운 (구성원, 버스) 쌍부터 자리가 있으면 배정하고 넘치면 미배정 목록에 남겼다. 탐욕이라 총비용 최적은 아니며(반례: demo에서 101 vs 최적 3) 미배정 사유(거리/정원)를 나눠 보고했다." |
| 정류장을 도는 순서 | 최근접 → 2-opt(`compare_routes`) | 순서가 정해져 있지 않고 한 노선이 여러 정류장을 돌 때 / 순서가 주어짐, 시간창·거리가 비대칭 | "최근접으로 순서를 만들고 2-opt로 다듬은 뒤 같은 입력에서 길이를 비교했다(최근접 X km → 2-opt Y km). 국소 최적이며 직선거리 추정이다." |
| 결과 점검 | `check_assignment`, `metrics` | 항상 | "정원 초과·최대 도보 초과·중복/누락을 알고리즘과 따로 다시 세어 0건을 확인했다." |

## 함수
`haversine_m(a,b)` 위경도 직선거리 m(추정) · `coord_dist(points)` / `matrix_dist(M)` 거리 함수 만들기(소요시간 행렬을 받았으면 후자) · `is_symmetric` · `kmeans(points,k,seed,n_init)` → (labels, medoids, inertia) · `assign_capacity(cost,capacity,max_cost)` → (배정, 미배정) · `tour_len` · `nearest_neighbor` · `two_opt` · `compare_routes(dist,nodes,start,closed)` · `check_assignment` → 위반 목록(빈 목록=0건) · `metrics` → 탑승률·버스별 탑승·최대/평균 도보·정원 초과·미배정(거리/정원).
같은 seed면 같은 결과다. `max_cost`는 **이하**가 허용이다(비용이 같으면 배정, 조금이라도 넘으면 거리 때문에 미배정 — demo가 경계로 고정). 출근 노선(사업장에서 끝남)은 start를 사업장으로 두고 뒤집어 쓴다(대칭 거리 가정).

## 사용 예
```python
from opt import coord_dist, kmeans, haversine_m, assign_capacity, check_assignment, metrics, compare_routes
labels, medoids, _ = kmeans(member_latlon, k=6)                       # k는 내가 정한다
stops = [member_latlon[m] for m in medoids]
cost = [[haversine_m(p, s) for s in stops] for p in member_latlon]    # 직선거리 추정(m)
assign, unassigned = assign_capacity(cost, [40] * 6, max_cost=2500)
assert check_assignment(assign, unassigned, [40] * 6, cost, 2500) == []
print(metrics(assign, unassigned, [40] * 6, cost, 2500))
r = compare_routes(coord_dist([plant] + stops), range(7), 0)          # 0번 = 사업장
```

## 실측 [관측, 이 PC·가상 데이터]
`--demo` 0.01초 · 1500점 k=50 k-means 0.8초(`n_init=1`)/5.4초(`n_init=5`) · 1500×50 비용 계산+배정 0.1초 · 순서 60곳 0.02초, 200곳 0.4초.
최근접 → 2-opt 단축은 입력마다 달랐다: demo 25곳 1.0%, 임의 60곳 13.5%, 200곳 9.9%. 줄어든다고 단정하지 말고 **내 데이터로 재서** 쓴다. 시험 PC의 속도는 [미확인].

## 한계 (코드 주석과 같다)
- 직선거리는 도로·보행 거리가 아니다. 결과 문서에 '추정'이라고 쓴다. 평면 투영(k-means)은 도시 규모에서만 맞다.
- 탐욕 배정은 총비용 최적이 아니다. k-means는 정원·최대 도보를 모르고, k를 자동으로 고르지 않으며, 군집이 비면 해당 medoid가 `None`이다.
- 2-opt는 대칭 거리를 가정하고(비대칭이면 `compare_routes`가 건너뛰고 `two_opt_applied=False`), 국소 최적이며, 시간창·차량 용량·여러 노선 나누기는 다루지 않는다.
- 업그레이드 경로(이름만, 코드 없음): 최적 배정 → 최소비용 흐름·헝가리안 / 용량·시간창 차량 경로 → OR-Tools(`pip install`이 될 때만) / 큰 순회 → 담금질·Or-opt.

## NOTES에 남길 5줄 (기법을 썼든 안 썼든)
```
- 문제: (예) 구성원 N명을 정류장 k곳·정원 C로 배정
- 쓴 기법: (함수, 입력, 파라미터 k·max_cost·seed)
- 안 쓴 기법과 이유: (예) 노선이 주어져 군집화 안 씀 / 최적해법은 설치·시간 때문에 안 씀
- 실제 비교한 것: (예) 최근접 X km vs +2-opt Y km — 비교하지 않은 것은 '비교했다'고 쓰지 않는다
- 한계·미확인: (직선거리 추정, 탐욕 비최적 …)
```

## 웹에 붙일 때 (관리자 전용 실행 → 결과 저장)
```python
import json, sqlite3                        # 관리자만 부르는 라우트에서 실행한 뒤 입력 조건·목적값을 남긴다
db = sqlite3.connect("app.db")
db.execute("CREATE TABLE IF NOT EXISTS runs(id INTEGER PRIMARY KEY, algo TEXT, params TEXT, objective REAL, created TEXT DEFAULT CURRENT_TIMESTAMP)")
with db: db.execute("INSERT INTO runs(algo, params, objective) VALUES (?,?,?)", ("nn+2opt", json.dumps({"k": 6, "max_walk_m": 2500}), r["opt_len"]))
```
구성원 화면에는 자기 배정만 보인다(남의 항목은 404). 이 기록이 "무엇을 썼고 왜 그렇게 정했나"의 증거가 된다.
