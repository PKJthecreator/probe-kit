"""모델 운영 뼈대(파일 기반, 설치 불필요): 등록 → 게이트(그룹별 기준 + 현행 대비 비악화) → 사람 승인 승격 → 롤백,
그리고 드리프트 감시(잔차 3σ 확인 창, 입력 분포 PSI). 경보와 재학습·승격은 분리한다.
MLflow가 있으면 같은 개념을 log_model / register_model / alias("champion")로 옮긴다(README).
registry/registry.json = {"production": "v2", "previous": "v1", "versions": {"v1": {metrics, data_hash, created}}}
자체 점검: python registry.py
"""
import hashlib
import json
import math
import pickle
import time
from collections import deque
from pathlib import Path


def data_hash(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()[:16]


def _load(reg):
    f = Path(reg) / "registry.json"
    return json.loads(f.read_text(encoding="utf-8")) if f.exists() else {"production": None, "previous": None, "versions": {}}


def _save(reg, state):
    Path(reg).mkdir(parents=True, exist_ok=True)
    (Path(reg) / "registry.json").write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def register(reg, model, metrics, **meta):
    """metrics = {"A": {"mae": 5.1}, "B": {"mae": 7.0}} 처럼 그룹별. 버전 id를 돌려준다."""
    state = _load(reg)
    v = f"v{len(state['versions']) + 1}"
    (Path(reg) / v).mkdir(parents=True, exist_ok=True)
    (Path(reg) / v / "model.pkl").write_bytes(pickle.dumps(model))  # 자기 레지스트리 파일만 읽는다(pickle은 신뢰된 파일만)
    state["versions"][v] = {"metrics": metrics, "created": time.strftime("%Y-%m-%d %H:%M:%S"), **meta}
    _save(reg, state)
    return v


def gate(candidate, production, limits, metric="mae", tol=0.0):
    """그룹마다: 절대 기준(limits, 경계값 포함 통과) 이하 AND 현행 대비 tol 이상 나빠지지 않음. 하나라도 실패면 기각."""
    by = {}
    for g, lim in limits.items():
        c = candidate[g][metric]
        p = production.get(g, {}).get(metric) if production else None
        ok = c <= lim and (p is None or c <= p * (1 + tol))
        by[g] = {"candidate": c, "production": p, "limit": lim, "passed": ok}
    return {"decision": "awaiting_approval" if all(x["passed"] for x in by.values()) else "rejected", "by_group": by}


def promote(reg, version, confirm=False, approver=None):
    """사람이 confirm=True로 요청할 때만 운영 승격. 이전 운영 버전은 롤백용으로 남긴다."""
    if not confirm or not approver:
        raise PermissionError("승격은 사람 승인(confirm=True, approver)이 필요하다")
    state = _load(reg)
    if version not in state["versions"]:
        raise KeyError(version)
    state["previous"], state["production"] = state["production"], version
    state["versions"][version] |= {"promoted_by": approver, "promoted_at": time.strftime("%Y-%m-%d %H:%M:%S")}
    _save(reg, state)


def rollback(reg):
    state = _load(reg)
    if not state["previous"]:
        raise RuntimeError("돌아갈 이전 버전이 없다")
    state["production"], state["previous"] = state["previous"], state["production"]
    _save(reg, state)
    return state["production"]


def load_production(reg):
    state = _load(reg)
    v = state["production"]
    return v, pickle.loads((Path(reg) / v / "model.pkl").read_bytes()) if v else None


class ResidualDrift:
    """기준 잔차의 평균·표준편차로 z를 재고, 최근 window개 중 need개 이상 |z|>sigma면 경보(한 점 튐에 흔들리지 않게)."""

    def __init__(self, reference, sigma=3.0, window=5, need=2):
        n = len(reference)
        self.mean = sum(reference) / n
        self.std = math.sqrt(sum((r - self.mean) ** 2 for r in reference) / n)
        self.sigma, self.need, self.recent = sigma, need, deque(maxlen=window)

    def update(self, residual):
        z = abs(residual - self.mean) / self.std if self.std > 1e-12 else 0.0
        self.recent.append(z > self.sigma)
        return {"z": round(z, 3), "alarm": sum(self.recent) >= self.need}


def psi(expected, actual, bins=10):
    """입력 분포 변화(PSI). 기준 구간 분위수로 구간을 나눈다. 0.1 미만 안정, 0.1~0.25 주의, 0.25 초과 큰 변화."""
    e = sorted(expected)
    edges = [e[int(len(e) * i / bins)] for i in range(1, bins)]

    def share(xs):
        cnt = [0] * bins
        for x in xs:
            cnt[sum(x > b for b in edges)] += 1
        return [max(c / len(xs), 1e-6) for c in cnt]
    pe, pa = share(expected), share(actual)
    return sum((a - b) * math.log(a / b) for a, b in zip(pa, pe))


if __name__ == "__main__":
    import random
    import tempfile
    reg = tempfile.mkdtemp()
    v1 = register(reg, {"w": 1}, {"A": {"mae": 6.0}, "B": {"mae": 7.0}}, data="d1")
    promote(reg, v1, confirm=True, approver="kim")
    cand = {"A": {"mae": 5.5}, "B": {"mae": 7.5}}
    g = gate(cand, _load(reg)["versions"][v1]["metrics"], limits={"A": 6.0, "B": 7.5})
    assert g["decision"] == "rejected" and not g["by_group"]["B"]["passed"], "B가 현행보다 나빠지면 기각"
    assert gate({"A": {"mae": 6.0}}, None, {"A": 6.0})["decision"] != "rejected", "경계값 6.0은 통과"
    v2 = register(reg, {"w": 2}, cand)
    try:
        promote(reg, v2)
        raise AssertionError("승인 없이 승격되면 안 됨")
    except PermissionError:
        pass
    promote(reg, v2, confirm=True, approver="lee")
    assert rollback(reg) == v1 and load_production(reg)[1] == {"w": 1}
    random.seed(0)
    d = ResidualDrift([random.gauss(0, 1) for _ in range(200)])
    assert not d.update(5)["alarm"] and d.update(5)["alarm"], "두 번째 이탈에서 경보"
    base = [random.gauss(0, 1) for _ in range(1000)]
    assert psi(base, [random.gauss(0, 1) for _ in range(1000)]) < 0.1 < psi(base, [random.gauss(1, 1) for _ in range(1000)])
    print("registry PASS")
