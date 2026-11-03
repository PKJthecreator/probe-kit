"""배정·경로 최적화 뼈대(표준 라이브러리만). 요구·데이터가 있을 때만 쓴다 — 노선이 이미 주어진 조회 과제에는 해당 없음.
기능: ① k-means로 정류장 후보 묶기(좌표가 있을 때) ② 정원 있는 버스에 구성원 배정(탐욕, 넘치면 미배정 목록)
      ③ 정류장 순서(최근접 → 2-opt)와 둘의 길이 비교 ④ 지표와 제약 위반 점검
거리는 dist(i, j) 함수 하나로 받는다. 좌표면 coord_dist(points)(위경도 직선거리 m — 도로·보행 거리가 아니라 '추정'),
소요시간·거리 행렬을 받았으면 matrix_dist(M). 행렬이 비대칭이면 2-opt는 건너뛴다.
사용: python opt.py --demo   (가상 좌표로 전 기능을 assert로 점검하고, 최근접 vs 2-opt 실측 비교를 출력한다)
      쓸 함수만 작업 폴더로 복사하고 안 쓰는 함수는 지운다(README). 제약(정원·최대 도보거리)은 check_assignment로 따로 센다.
"""
import argparse
import itertools
import math
import random
import time

R_EARTH = 6371000.0  # m


# ── 거리 ──────────────────────────────────────────────────────────────
def haversine_m(a, b):
    """(위도, 경도) 두 점의 지표면 직선거리(m). 도로·보행 거리가 아니므로 결과에는 '직선거리 추정'이라고 적는다."""
    (la1, lo1), (la2, lo2) = a, b
    p1, p2 = math.radians(la1), math.radians(la2)
    h = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lo2 - lo1) / 2) ** 2
    return 2 * R_EARTH * math.asin(min(1.0, math.sqrt(h)))


def coord_dist(points):
    return lambda i, j: haversine_m(points[i], points[j])


def matrix_dist(m):
    return lambda i, j: m[i][j]


def is_symmetric(dist, nodes, tol=1e-9):
    return all(abs(dist(i, j) - dist(j, i)) <= tol for i in nodes for j in nodes if i < j)


# ── ① k-means: 좌표 → 정류장 후보 ─────────────────────────────────────
def _project(points):
    """위경도를 평균 위도 기준 평면(m)으로 편다. 도시 규모에서만 맞다(수십 km 넘으면 오차가 커진다)."""
    lat0 = math.radians(sum(p[0] for p in points) / len(points))
    return [(R_EARTH * math.radians(lon) * math.cos(lat0), R_EARTH * math.radians(lat)) for lat, lon in points]


def _d2(a, b):
    return (a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2


def _kmeans_once(xy, k, rng, max_iter):
    n = len(xy)
    centers = [xy[int(rng.random() * n)]]
    while len(centers) < k:  # k-means++ 초기화: 기존 중심에서 먼 점일수록 잘 뽑힌다
        w = [min(_d2(p, c) for c in centers) for p in xy]
        t, acc, pick = rng.random() * sum(w), 0.0, n - 1
        for i, wi in enumerate(w):
            acc += wi
            if acc >= t:
                pick = i
                break
        centers.append(xy[pick])
    labels = None
    for _ in range(max_iter):
        new = [min(range(k), key=lambda c: (_d2(p, centers[c]), c)) for p in xy]
        if new == labels:
            break
        labels = new
        for c in range(k):
            m = [xy[i] for i in range(n) if labels[i] == c]
            if m:
                centers[c] = (sum(x for x, _ in m) / len(m), sum(y for _, y in m) / len(m))
            else:  # 빈 군집: 자기 중심에서 가장 먼 점을 넘겨받는다
                far = max(range(n), key=lambda i: (_d2(xy[i], centers[labels[i]]), -i))
                centers[c] = xy[far]
    return labels, centers, sum(_d2(xy[i], centers[labels[i]]) for i in range(n))


def kmeans(points, k, seed=0, n_init=5, max_iter=100):
    """(위도, 경도) 목록 → (labels, medoids, inertia_m2). medoids[c] = 군집 중심에 가장 가까운 구성원의 번호(정류장 후보).
    k는 사용자가 정한다(자동 선택 없음). 정원·최대 도보거리는 모른다 — 결과는 check_assignment/metrics로 확인한다.
    같은 seed면 같은 결과. 한계: 점 n·k·반복이 크면 느리다(순수 파이썬). 군집이 비면 해당 medoid는 None."""
    if not 1 <= k <= len(points):
        raise ValueError("k는 1 이상, 점 개수 이하여야 한다")
    xy = _project(points)
    best = None
    for r in range(n_init):
        res = _kmeans_once(xy, k, random.Random(seed + r), max_iter)
        if best is None or res[2] < best[2] - 1e-9:
            best = res
    labels, centers, inertia = best
    medoids = []
    for c in range(k):
        mem = [i for i in range(len(xy)) if labels[i] == c]
        medoids.append(min(mem, key=lambda i: (_d2(xy[i], centers[c]), i)) if mem else None)
    return labels, medoids, inertia


# ── ② 정원 있는 배정: 탐욕 ────────────────────────────────────────────
def assign_capacity(cost, capacity, max_cost=None):
    """cost[i][b] = 구성원 i가 버스(또는 정류장) b를 쓸 때의 비용(예: 걸어가는 거리), None이면 불가. 정원 capacity[b].
    (비용, 구성원, 버스) 오름차순으로 훑으며 자리가 있으면 배정한다. 반환 (배정 {구성원: 버스}, 미배정 [구성원...]).
    한계: 탐욕이라 총비용 최적이 아니다(--demo가 반례와 격차를 보여 준다). 쌍 수 n·m을 전부 정렬한다."""
    pairs = sorted((c, i, b) for i, row in enumerate(cost) for b, c in enumerate(row)
                   if c is not None and (max_cost is None or c <= max_cost))
    left, assign = list(capacity), {}
    for _, i, b in pairs:
        if i not in assign and left[b] > 0:
            assign[i] = b
            left[b] -= 1
    return assign, [i for i in range(len(cost)) if i not in assign]


# ── ③ 정류장 순서: 최근접 → 2-opt ─────────────────────────────────────
def tour_len(dist, t, closed=False):
    n = sum(dist(t[k], t[k + 1]) for k in range(len(t) - 1))
    return n + (dist(t[-1], t[0]) if closed and len(t) > 1 else 0.0)


def nearest_neighbor(dist, nodes, start):
    """start에서 출발해 가장 가까운 미방문 지점으로 계속 간다(동률이면 번호가 작은 쪽). 출근 노선(사업장에서 끝남)은 start를 사업장으로 두고 뒤집어 쓴다."""
    left = [n for n in nodes if n != start]
    t = [start]
    while left:
        nxt = min(left, key=lambda n: (dist(t[-1], n), n))
        left.remove(nxt)
        t.append(nxt)
    return t


def two_opt(dist, t, closed=False):
    """t[0] 고정. 두 간선을 끊어 사이 구간을 뒤집는 것이 더 짧으면 뒤집기를 더 줄일 수 없을 때까지 반복한다.
    대칭 거리를 가정한다(is_symmetric으로 확인). 한계: 국소 최적이지 전체 최적이 아니다. 한 바퀴 O(n²)."""
    t = list(t)
    improved = True
    while improved:
        improved = False
        for i in range(1, len(t) - 1):
            for j in range(i + 1, len(t)):
                a, b, c = t[i - 1], t[i], t[j]
                d = t[j + 1] if j + 1 < len(t) else (t[0] if closed else None)
                old = dist(a, b) + (dist(c, d) if d is not None else 0.0)
                new = dist(a, c) + (dist(b, d) if d is not None else 0.0)
                if new < old - 1e-9:
                    t[i:j + 1] = t[i:j + 1][::-1]
                    improved = True
    return t


def compare_routes(dist, nodes, start, closed=False):
    """최근접 순서와 그 뒤 2-opt를 같은 입력으로 돌려 길이를 비교한다(서술형에서 '비교했다'고 말할 근거).
    거리가 비대칭이면 2-opt를 건너뛰고 two_opt_applied=False로 표시한다."""
    nn = nearest_neighbor(dist, nodes, start)
    sym = is_symmetric(dist, nodes if start in nodes else list(nodes) + [start])
    opt = two_opt(dist, nn, closed) if sym else nn
    nl, ol = tour_len(dist, nn, closed), tour_len(dist, opt, closed)
    return {"nn": nn, "nn_len": nl, "opt": opt, "opt_len": ol, "two_opt_applied": sym,
            "gain_pct": (nl - ol) / nl * 100 if nl else 0.0}


# ── ④ 점검과 지표 ─────────────────────────────────────────────────────
def check_assignment(assign, unassigned, capacity, cost, max_cost=None):
    """배정 알고리즘과 따로 다시 세어 제약 위반 목록을 돌려준다. 빈 목록 = 위반 없음."""
    v = []
    if sorted(list(assign) + list(unassigned)) != list(range(len(cost))):
        v.append("구성원이 중복되거나 빠졌다")
    load = [0] * len(capacity)
    for i, b in assign.items():
        load[b] += 1
        c = cost[i][b]
        if c is None or (max_cost is not None and c > max_cost):
            v.append(f"거리 초과 또는 불가: 구성원 {i} -> 버스 {b}")
    v += [f"정원 초과: 버스 {b} ({load[b]}/{capacity[b]})" for b in range(len(capacity)) if load[b] > capacity[b]]
    return v


def metrics(assign, unassigned, capacity, cost, max_cost=None):
    """탑승률(배정 인원/전체 정원), 버스별 탑승, 최대·평균 도보(cost 단위), 정원 초과 버스 수, 미배정(거리 때문/정원 때문)."""
    load = [0] * len(capacity)
    for b in assign.values():
        load[b] += 1
    walks = [cost[i][b] for i, b in assign.items()]
    reachable = lambda i: any(c is not None and (max_cost is None or c <= max_cost) for c in cost[i])
    far = [i for i in unassigned if not reachable(i)]
    total = sum(capacity)
    return {"assigned": len(assign), "unassigned": len(unassigned), "unassigned_far": len(far),
            "unassigned_full": len(unassigned) - len(far), "ridership": len(assign) / total if total else None,
            "load": load, "max_walk": max(walks) if walks else None, "mean_walk": sum(walks) / len(walks) if walks else None,
            "over_capacity": sum(1 for b in range(len(capacity)) if load[b] > capacity[b])}


# ── 자체 점검 ─────────────────────────────────────────────────────────
def _gauss(rng):  # Box-Muller. random()만 써서 파이썬 버전이 달라도 같은 값이 나온다
    return math.sqrt(-2 * math.log(1 - rng.random())) * math.cos(2 * math.pi * rng.random())


def _brute_total(cost, capacity):  # 아주 작은 입력의 진짜 최적(전부 배정). 탐욕과의 격차를 재는 용도
    best = None
    for combo in itertools.product(range(len(capacity)), repeat=len(cost)):
        if all(combo.count(b) <= capacity[b] for b in range(len(capacity))):
            s = sum(cost[i][b] for i, b in enumerate(combo))
            best = s if best is None else min(best, s)
    return best


def demo():
    # 1) 거리: 적도에서 경도 1도 ≈ 111.19 km
    assert abs(haversine_m((0, 0), (0, 1)) - 111195) < 5 and haversine_m((37, 127), (37, 127)) == 0

    # 2) 2-opt: 교차하는 정사각형 순회(0,0)(1,1)(1,0)(0,1) → 길이 4.83에서 4.0으로
    sq = [(0, 0), (1, 1), (1, 0), (0, 1)]
    m = [[math.dist(p, q) for q in sq] for p in sq]
    d = matrix_dist(m)
    assert abs(tour_len(d, [0, 1, 2, 3], closed=True) - (2 + 2 * math.sqrt(2))) < 1e-9
    fixed = two_opt(d, [0, 1, 2, 3], closed=True)
    assert abs(tour_len(d, fixed, closed=True) - 4.0) < 1e-9 and sorted(fixed) == [0, 1, 2, 3] and fixed[0] == 0
    asym = [[0, 1, 5], [4, 0, 1], [1, 6, 0]]
    r = compare_routes(matrix_dist(asym), [0, 1, 2], 0)
    assert r["two_opt_applied"] is False and r["opt"] == r["nn"]  # 비대칭이면 2-opt를 쓰지 않는다

    # 3) 탐욕 배정: 손으로 푼 답과 비교
    cost = [[1, 9], [2, 9], [3, 9], [4, 9]]
    a, un = assign_capacity(cost, [2, 1])
    assert a == {0: 0, 1: 0, 2: 1} and un == [3] and check_assignment(a, un, [2, 1], cost) == []
    a2, un2 = assign_capacity(cost, [2, 1], max_cost=5)  # 9는 너무 멀다 → 2번도 미배정
    assert a2 == {0: 0, 1: 0} and un2 == [2, 3]
    mt = metrics(a2, un2, [2, 1], cost, max_cost=5)
    assert mt["unassigned_far"] == 0 and mt["unassigned_full"] == 2  # 2·3번은 0번 버스까지 5 이내지만 정원이 찼다
    assert abs(mt["ridership"] - 2 / 3) < 1e-12 and mt["max_walk"] == 2 and mt["load"] == [2, 0]
    a3, un3 = assign_capacity([[1, None], [9, 8]], [1, 1], max_cost=5)  # 1번은 어느 버스도 5 이내가 아니다(None=불가 포함)
    mt3 = metrics(a3, un3, [1, 1], [[1, None], [9, 8]], max_cost=5)
    assert a3 == {0: 0} and un3 == [1] and mt3["unassigned_far"] == 1 and mt3["unassigned_full"] == 0
    # 경계: 비용이 max_cost와 같으면 허용(이하), 조금이라도 넘으면 거리 때문에 미배정
    ae, ue = assign_capacity([[5, 9]], [1, 1], max_cost=5)
    assert ae == {0: 0} and ue == [] and check_assignment(ae, ue, [1, 1], [[5, 9]], 5) == []
    af, uf = assign_capacity([[5.0001]], [1], max_cost=5)
    assert af == {} and uf == [0] and metrics(af, uf, [1], [[5.0001]], 5)["unassigned_far"] == 1
    assert check_assignment({0: 0}, [], [1], [[5.0001]], 5) != []
    az, uz = assign_capacity([[5]], [0], max_cost=5)  # 정원 0: 5는 닿는 거리라 사유는 '정원'
    assert uz == [0] and metrics(az, uz, [0], [[5]], 5)["unassigned_full"] == 1
    bad = check_assignment({0: 0, 1: 0}, [3], [1, 1], cost)  # 점검 함수 자체 확인: 정원 초과·누락을 잡아야 한다
    assert any("정원 초과" in x for x in bad) and any("빠졌다" in x for x in bad)
    hard = [[1, 2], [1, 100]]  # 탐욕이 최적이 아닌 반례
    g, _ = assign_capacity(hard, [1, 1])
    greedy_total, best_total = sum(hard[i][b] for i, b in g.items()), _brute_total(hard, [1, 1])
    assert (greedy_total, best_total) == (101, 3)

    # 4) k-means: 이웃 6곳 × 20명(가상). 같은 이웃은 같은 군집, 같은 seed면 같은 결과
    rng = random.Random(7)
    centers = [(37.00, 127.00), (37.00, 127.12), (37.10, 127.00), (37.10, 127.12), (36.90, 127.06), (37.20, 127.06)]
    pts = [(la + 0.008 * _gauss(rng), lo + 0.008 * _gauss(rng)) for la, lo in centers for _ in range(20)]
    labels, medoids, _ = kmeans(pts, 6, seed=0)
    assert kmeans(pts, 6, seed=0)[0] == labels
    assert all(len({labels[g * 20 + t] for t in range(20)}) == 1 for g in range(6)) and len(set(labels)) == 6
    try:
        kmeans(pts, 0)
        raise SystemExit("k=0은 거부해야 한다")
    except ValueError:
        pass

    # 5) 끝까지: 정류장 = medoid, 정류장마다 버스 1대(정원 18) → 배정 → 지표 → 노선 순서
    stops = [pts[m_] for m_ in medoids]
    capacity = [18] * 6
    walk = [[haversine_m(p, s) for s in stops] for p in pts]
    max_walk = 2500.0
    asg, unas = assign_capacity(walk, capacity, max_walk)
    assert check_assignment(asg, unas, capacity, walk, max_walk) == []
    mt = metrics(asg, unas, capacity, walk, max_walk)
    assert mt["assigned"] + mt["unassigned"] == len(pts) and mt["over_capacity"] == 0 and mt["max_walk"] <= max_walk
    plant = (37.05, 127.30)  # 가상 사업장
    nodes = [plant] + stops
    rt = compare_routes(coord_dist(nodes), range(len(nodes)), 0)
    assert rt["opt_len"] <= rt["nn_len"] + 1e-6

    # 6) 최근접 vs 2-opt 실측: 정류장 25곳(가상, 균일 분포) + 사업장
    rng = random.Random(11)
    big = [(37.0, 127.0)] + [(37.0 + 0.2 * rng.random(), 127.0 + 0.2 * rng.random()) for _ in range(25)]
    cmp_ = compare_routes(coord_dist(big), range(len(big)), 0)
    assert sorted(cmp_["opt"]) == list(range(len(big))) and cmp_["opt"][0] == 0
    assert cmp_["opt_len"] < cmp_["nn_len"] and two_opt(coord_dist(big), cmp_["opt"]) == cmp_["opt"]  # 더 줄일 수 없는 상태

    print("[k-means -> 배정 -> 지표] 구성원 %d명, 정류장 %d곳(버스 정원 %d), 최대 도보 %.0f m 이내만 배정(직선거리 추정)"
          % (len(pts), len(stops), capacity[0], max_walk))
    print("  배정 %d / 미배정 %d (거리 때문 %d, 정원 때문 %d), 탑승률 %.1f%%, 최대 도보 %.0f m, 평균 도보 %.0f m, 정원 초과 버스 %d"
          % (mt["assigned"], mt["unassigned"], mt["unassigned_far"], mt["unassigned_full"], mt["ridership"] * 100,
             mt["max_walk"], mt["mean_walk"], mt["over_capacity"]))
    print("  버스별 탑승 %s" % mt["load"])
    print("[탐욕 배정의 한계] 반례에서 탐욕 총비용 %d vs 최적 %d" % (greedy_total, best_total))
    print("[정류장 순서] 사업장+%d곳: 최근접 %.1f km -> 최근접+2-opt %.1f km (%.1f%% 단축, 직선거리 추정)"
          % (len(big) - 1, cmp_["nn_len"] / 1000, cmp_["opt_len"] / 1000, cmp_["gain_pct"]))
    print("opt.py demo OK")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="배정·경로 최적화 뼈대. 인자 없이 실행해도 자체 점검(--demo)을 돈다.")
    ap.add_argument("--demo", action="store_true", help="가상 데이터로 전 기능을 assert로 점검")
    ap.parse_args()
    t0 = time.perf_counter()
    demo()
    print("소요 %.2f초" % (time.perf_counter() - t0))
