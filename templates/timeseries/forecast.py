"""시계열 예측 뼈대(롱 포맷: 대상ID·기간·값). 기준선 → 전역 부스팅 → 롤링 백테스트 → 게이트 → 미래 예측.
사용: python forecast.py --data sales.csv --id item --time month --y qty --h 1 --season 12 [--folds 6]
      python forecast.py --demo
전제: 대상마다 기간이 빠짐없이 있다(수요면 빈 기간을 0으로, 계측이면 결측으로 미리 채운다).
h기 앞 예측은 직접 방식: 시차를 h 이상으로만 써서 예측 시점에 아는 값만 쓴다(누수 차단).
--h는 그 한 시점(t+h)만 예측한다. 1~h 전부 필요하면 h를 바꿔 여러 번 돌려 합친다.
시간 열이 정수(1,2,3·202601)면 날짜로 바꾸지 않고 순서로만 쓴다(이때 미래 예측 행은 만들지 않는다).
산출: outputs/backtest.csv, outputs/backtest_metrics.json, outputs/forecast.csv
"""
import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor

OUT = Path("outputs")


def demand_type(y):
    """ADI(평균 수요 간격)·CV²(0 아닌 수요의 변동)로 4유형. 간헐형·불규칙형은 Croston류가 맞다."""
    nz = y[y != 0]
    if len(nz) == 0:
        return "zero"
    adi, cv2 = len(y) / len(nz), (nz.std(ddof=0) / nz.mean()) ** 2
    return {(False, False): "smooth", (False, True): "erratic", (True, False): "intermittent", (True, True): "lumpy"}[(adi >= 1.32, cv2 >= 0.49)]


def frame(df, a):
    d = df.sort_values([a.id, a.time]).reset_index(drop=True)
    g = d.groupby(a.id)[a.y]
    lags = sorted({a.h, a.h + 1, a.h + 2} | ({a.season} if a.season and a.season >= a.h else set()))
    for k in lags:
        d[f"lag{k}"] = g.shift(k)
    d["ma3"] = d[[f"lag{k}" for k in (a.h, a.h + 1, a.h + 2)]].mean(axis=1)
    d["cal_month"] = d[a.time].dt.month if pd.api.types.is_datetime64_any_dtype(d[a.time]) else 0  # 이름 충돌 방지(시간 열이 month일 수 있음)
    d["sid"] = d[a.id].astype("category").cat.codes
    feats = [f"lag{k}" for k in lags] + ["ma3", "cal_month", "sid"]
    base = {"naive": f"lag{a.h}", "ma3": "ma3"} | ({"snaive": f"lag{a.season}"} if f"lag{a.season}" in d else {})
    return d, feats, base


def fit_gbm(train, feats, y):
    tr = train.dropna(subset=[y])
    return HistGradientBoostingRegressor(random_state=42, max_iter=300).fit(tr[feats], tr[y])


def metrics(y, p):
    """WAPE·편향은 실측 합이 0이면 계산 불가(None). 비교는 None을 맨 뒤로."""
    e = p - y
    s = np.abs(y).sum()
    return {"wape": float(np.abs(e).sum() / s) if s else None, "mae": float(np.abs(e).mean()), "bias": float(e.sum() / s) if s else None}


def _wape_key(r):
    return (r["wape"] is None, r["wape"] if r["wape"] is not None else r["mae"])


def backtest(d, feats, base, a):
    periods = sorted(d[a.time].unique())
    rows = []
    for f in range(a.folds, 0, -1):  # 기준 시점을 한 기씩 옮기며, 학습은 항상 기준 시점까지만
        i = len(periods) - a.h - f
        if i < max(int(a.season or 0), 3) + a.h:
            continue
        train = d[d[a.time] <= periods[i]]
        test = d[d[a.time] == periods[i + a.h]].copy()
        test["gbm"] = fit_gbm(train, feats, a.y).predict(test[feats])
        test["origin"] = periods[i]
        rows.append(test)
    if not rows:
        raise ValueError(f"백테스트할 기간이 부족하다: 기간 {len(periods)}개, 필요 > season+h+folds. --folds·--season을 줄인다")
    bt = pd.concat(rows)
    models = list(base) + ["gbm"]
    for name, col in base.items():
        bt[name] = bt[col]
    res = {m: metrics(bt[a.y].to_numpy(float), bt[m].fillna(bt["naive"]).to_numpy(float)) for m in models}
    return bt[[a.id, a.time, "origin", a.y, *models]], res


def gate(res, margin):
    """후보(gbm)는 최선 기준선보다 WAPE가 margin 이상 좋을 때만 채택. 아니면 기준선을 그대로 쓴다."""
    best_base = min((m for m in res if m != "gbm"), key=lambda m: _wape_key(res[m]))
    g, b = _wape_key(res["gbm"]), _wape_key(res[best_base])
    ok = g[0] == b[0] and g[1] < b[1] * (1 - margin)
    return {"picked": "gbm" if ok else best_base, "best_baseline": best_base, "margin": margin}


def future(df, a):
    """대상별로 다음 h기 자리를 만든다. 기간 간격을 못 읽으면 None."""
    p = pd.Series(sorted(df[a.time].unique()))
    freq = pd.infer_freq(p) if pd.api.types.is_datetime64_any_dtype(p) and len(p) >= 3 else None
    if not freq:
        print("기간 간격을 읽지 못해 미래 예측을 건너뛴다(백테스트 결과만)")
        return None
    nxt = pd.date_range(p.iloc[-1], periods=a.h + 1, freq=freq)[1:]
    fut = pd.MultiIndex.from_product([df[a.id].unique(), nxt], names=[a.id, a.time]).to_frame(index=False)
    return pd.concat([df, fut], ignore_index=True)


def run(a):
    df = pd.read_csv(a.data, dtype={a.id: str})
    if df[a.time].dtype == object:  # 문자열만 날짜로. 정수를 바꾸면 1970년 나노초가 된다
        t = pd.to_datetime(df[a.time], errors="coerce")
        if t.notna().all():
            df[a.time] = t  # 문자열 정렬("2026-2" > "2026-10") 오류를 피한다
    if df.duplicated([a.id, a.time]).any():
        raise ValueError(f"{a.id}·{a.time} 중복 행: 먼저 합계·평균으로 집계한다")
    periods = sorted(df[a.time].unique())
    pos = {p: i for i, p in enumerate(periods)}
    span = df.groupby(a.id)[a.time].agg(lambda s: len(periods) - pos[s.min()])  # 첫 기간부터 끝까지 있어야 할 개수
    gap = df.groupby(a.id)[a.time].nunique() < span
    if gap.any():  # 빈 기간이 있으면 shift(k)가 k기 전이 아니게 된다
        raise ValueError(f"빈 기간이 있는 대상 {int(gap.sum())}개(예 {gap[gap].index[:3].tolist()}): 수요면 0, 계측이면 결측으로 채운 뒤 다시")
    if pd.api.types.is_datetime64_any_dtype(df[a.time]):
        regular = len(periods) < 3 or bool(pd.infer_freq(pd.DatetimeIndex(periods)))
    else:  # 정수 기간: 간격이 일정해야 한다(YYYYMM 정수는 12월→1월에서 깨지므로 날짜 문자열로 바꿔 넣는다)
        regular = pd.Series(periods).diff().dropna().nunique() <= 1
    if not regular:  # 모든 대상이 같은 기간을 빠뜨리면 위 검사로는 안 잡힌다
        msg = "전체 기간 간격이 불규칙하다(공통으로 빠진 기간·YYYYMM 정수 등). 달력 기준으로 채운다"
        if not a.allow_irregular:
            raise ValueError(msg + " (영업일처럼 원래 불규칙하면 --allow-irregular)")
        print("경고:", msg)
    first_origin = periods[max(len(periods) - a.h - a.folds, 0)]
    types = df[df[a.time] <= first_origin].groupby(a.id)[a.y].apply(lambda s: demand_type(s.to_numpy(float)))  # 평가 구간 정보 제외
    print("수요 유형:", types.value_counts().to_dict())
    d, feats, base = frame(df, a)
    bt, res = backtest(d, feats, base, a)
    bt = bt.merge(types.rename("type"), left_on=a.id, right_index=True, how="left")
    by_type = {t: {m: metrics(g[a.y].to_numpy(float), g[m].fillna(g["naive"]).to_numpy(float))["wape"] for m in res} for t, g in bt.groupby("type")}
    decision = gate(res, a.margin)
    OUT.mkdir(exist_ok=True)
    bt.to_csv(OUT / "backtest.csv", index=False)
    report = {"h": a.h, "folds": a.folds, "overall": res, "wape_by_type": by_type, "gate": decision}
    (OUT / "backtest_metrics.json").write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    for m, r in res.items():
        print(f"{m:7s} WAPE {r['wape']} MAE {r['mae']:.4f} bias {r['bias']}")
    print("게이트:", decision)

    full = future(df, a)
    if full is not None:
        f, feats, base = frame(full, a)
        last = f[f[a.y].isna()].copy()
        last = last[last[a.time] == last[a.time].max()]  # h기 앞 지점만
        pick = decision["picked"]
        last["forecast"] = fit_gbm(f, feats, a.y).predict(last[feats]) if pick == "gbm" else last[base[pick]]
        last[[a.id, a.time, "forecast"]].assign(model=pick).to_csv(OUT / "forecast.csv", index=False)
        print(f"미래 예측 {len(last)}행 -> outputs/forecast.csv (모델 {pick})")
    return report


def parse(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--data")
    ap.add_argument("--id")
    ap.add_argument("--time")
    ap.add_argument("--y")
    ap.add_argument("--h", type=int, default=1)
    ap.add_argument("--season", type=int, default=12)
    ap.add_argument("--folds", type=int, default=6)
    ap.add_argument("--margin", type=float, default=0.02, help="기준선 대비 이만큼 좋아야 채택")
    ap.add_argument("--allow-irregular", action="store_true", help="영업일처럼 원래 간격이 불규칙한 자료")
    ap.add_argument("--demo", action="store_true")
    return ap.parse_args(argv)


def demo():
    rng = np.random.default_rng(0)
    months = pd.date_range("2022-01-01", periods=48, freq="MS")
    rows = []
    for k in range(6):
        level = 100 + 20 * k
        season = 15 * np.sin(2 * np.pi * months.month / 12)
        rows.append(pd.DataFrame({"item": f"G{k:02d}", "month": months.strftime("%Y-%m-%d"),
                                  "qty": np.maximum(level + season + rng.normal(0, 5, 48), 0)}))
    tmp = OUT / "_demo"
    tmp.mkdir(parents=True, exist_ok=True)
    pd.concat(rows).to_csv(tmp / "sales.csv", index=False)
    r = run(parse(["--data", str(tmp / "sales.csv"), "--id", "item", "--time", "month", "--y", "qty", "--h", "1", "--season", "12"]))
    assert r["overall"]["snaive"]["wape"] < r["overall"]["naive"]["wape"] * 1.5
    assert (OUT / "forecast.csv").exists() and len(pd.read_csv(OUT / "forecast.csv")) == 6
    assert demand_type(np.array([0, 0, 5, 0, 0, 7, 0, 0])) in ("intermittent", "lumpy")
    print("demo PASS")


if __name__ == "__main__":
    args = parse()
    demo() if args.demo else run(args)
