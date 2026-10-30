"""SPC·6시그마 뼈대: I-MR 관리도, Western Electric 규칙, 공정능력(Cp·Cpk), 추적 신호.
관리한계는 기준 구간(Phase I, 안정 구간·학습 분할)에서만 계산하고 감시 구간(Phase II)에 적용한다.
자체 점검: python spc.py
"""
import numpy as np

D2 = 1.128  # 이동범위(n=2)의 d2 상수: sigma = 평균 MR / 1.128


def imr_limits(base):
    """기준 구간 값으로 I 관리도의 중심선·시그마·한계. 평균 MR로 단기 시그마를 잡는다."""
    base = np.asarray(base, float)
    sigma = np.abs(np.diff(base)).mean() / D2
    cl = base.mean()
    return {"cl": cl, "sigma": sigma, "ucl": cl + 3 * sigma, "lcl": cl - 3 * sigma}


def we_rules(x, cl, sigma):
    """Western Electric 규칙 위반 위치. 1: 3σ 밖 1점 / 2: 연속 3점 중 2점이 같은 쪽 2σ 밖 / 4: 연속 8점 같은 쪽."""
    z = (np.asarray(x, float) - cl) / sigma
    side = np.sign(z)
    r1 = np.abs(z) > 3
    r2 = np.array([i >= 2 and ((z[i - 2:i + 1] > 2).sum() >= 2 or (z[i - 2:i + 1] < -2).sum() >= 2) for i in range(len(z))])
    run = np.zeros(len(z), int)   # 같은 쪽(0 제외)으로 이어진 길이
    for i, s in enumerate(side):
        run[i] = run[i - 1] + 1 if i and s != 0 and s == side[i - 1] else int(s != 0)
    r4 = run >= 8
    return {"rule1_3sigma": np.flatnonzero(r1).tolist(), "rule2_2of3": np.flatnonzero(r2).tolist(), "rule4_8run": np.flatnonzero(r4).tolist()}


def capability(x, lsl=None, usl=None):
    """공정능력. Cp·Cpk = 단기(군내) 시그마(MR/1.128), Pp·Ppk = 전체 표준편차. 시간 순서대로 넣는다.
    규격(LSL·USL)은 고객·설계 요구이고 관리한계와 다르다. 한쪽 규격만 있으면 그쪽 지수만."""
    x = np.asarray(x, float)
    x = x[~np.isnan(x)]
    if lsl is None and usl is None:
        raise ValueError("규격 한계(LSL 또는 USL)가 필요하다")
    if len(x) < 2:
        raise ValueError("표본이 2개 이상 필요하다")
    mu, s_all, s_within = x.mean(), x.std(ddof=1), np.abs(np.diff(x)).mean() / D2
    out = {"n": len(x), "mean": mu, "sigma_within": s_within, "sigma_overall": s_all}
    for tag, s in (("c", s_within), ("p", s_all)):
        if s <= 0:
            continue  # 변동 0이면 지수 계산 불가
        if lsl is not None and usl is not None:
            out[f"{tag}p"] = (usl - lsl) / (6 * s)
        out[f"{tag}pk"] = min(v for v in ((usl - mu) / (3 * s) if usl is not None else None,
                                          (mu - lsl) / (3 * s) if lsl is not None else None) if v is not None)
    return {k: round(float(v), 4) for k, v in out.items()}


def tracking_signal(actual, forecast):
    """누적 오차 / 평균 절대오차. |TS| > 4 이면 예측 편향 경보(수요예측 관리도)."""
    e = np.asarray(actual, float) - np.asarray(forecast, float)
    mad = np.abs(e).mean()
    return float(e.sum() / mad) if mad > 0 else 0.0


if __name__ == "__main__":
    rng = np.random.default_rng(1)
    base = rng.normal(10, 1, 100)
    lim = imr_limits(base)
    assert abs(lim["cl"] - 10) < 0.3 and 0.7 < lim["sigma"] < 1.3
    shifted = np.r_[rng.normal(10, 1, 20), rng.normal(11.5, 1, 20), [16]]
    v = we_rules(shifted, lim["cl"], lim["sigma"])
    assert 40 in v["rule1_3sigma"] and v["rule4_8run"], v
    cap = capability(base, lsl=7, usl=13)
    assert 0.8 < cap["cpk"] < 1.3 and 0.8 < cap["ppk"] < 1.3, cap
    assert tracking_signal([10, 11, 12], [8, 9, 10]) == 3.0
    print("spc PASS", {k: round(val, 3) for k, val in lim.items()}, cap)
