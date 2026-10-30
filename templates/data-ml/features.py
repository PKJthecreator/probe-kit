"""파생변수 뼈대: 누수 없이, 설명할 수 있는 것만 만든다. 필요한 함수만 가져다 쓴다.
- 결측·특수코드: -9999 같은 코드를 결측으로 바꾸고 `열_isna` 플래그를 남긴다(대체값과 실측을 구분).
- 런→단위 집계: 웨이퍼·로트 한 장의 센서 시계열을 평균·표준편차·최소·최대·마지막·기울기·길이로 요약(가상계측·FDC).
- 시차·이동통계: 대상(설비·로트)별 시간 정렬 후 shift. 현재 행의 값이 들어가지 않게.
  같은 대상·같은 시각 행이 여럿이면 먼저 집계한다(행 순서로 과거를 정하지 않는다).
- SPC 기반: 중심·시그마는 학습 분할에서만 fit, 검증·test에는 transform만. 대상별로 따로 계산.
- 비율: 도메인 의미가 있는 쌍만. 대량 자동 생성은 하지 않는다.
자체 점검: python features.py
"""
import numpy as np
import pandas as pd

D2 = 1.128  # 이동범위(n=2) d2 상수, spc.py와 같은 값. 이 파일만 복사해도 돌도록 직접 둔다


def mark_missing(df, cols, codes=(-9999, -999)):
    """특수코드 → NaN, 그리고 결측 플래그. 플래그는 결측 자체가 신호일 때(센서 끊김 등) 쓸모 있다."""
    out = df.copy()
    for c in cols:
        out[c] = out[c].replace(list(codes), np.nan)
        out[f"{c}_isna"] = out[c].isna().astype(int)
    return out


def _slope(y):
    y = np.asarray(y, float)
    m = ~np.isnan(y)
    return np.polyfit(np.arange(len(y))[m], y[m], 1)[0] if m.sum() >= 2 else np.nan


def aggregate_runs(df, unit, time, cols, step=None):
    """센서 로그(한 행=한 시점) → 단위(웨이퍼·로트·런)당 한 행. step이 있으면 공정 단계별로 나눠 집계."""
    keys = [unit] + ([step] if step else [])
    d = df.sort_values(keys + [time])
    agg = d.groupby(keys)[cols].agg(["mean", "std", "min", "max", "last"])
    agg.columns = [f"{c}_{s}" for c, s in agg.columns]
    slope = d.groupby(keys)[cols].agg(_slope).add_suffix("_slope")
    t = pd.to_datetime(d[time], errors="coerce")
    dur = (t.groupby([d[k] for k in keys]).max() - t.groupby([d[k] for k in keys]).min()).dt.total_seconds().rename("duration_s")
    out = agg.join(slope).join(dur)
    if step:  # 단계별 열을 옆으로 펼친다: temp_mean@S1 ...
        out = out.unstack(step)
        out.columns = [f"{c}@{s}" for c, s in out.columns]
    return out.reset_index()


def add_time_parts(df, time):
    t = pd.to_datetime(df[time])
    return df.assign(hour=t.dt.hour, dow=t.dt.dayofweek, month=t.dt.month)


def add_lag_rolling(df, cols, time, group=None, lags=(1,), windows=(3, 7)):
    """과거 값만 쓰는 시차·이동평균·이동표준편차·차분. 원래 행 순서는 유지한다."""
    key = [group, time] if group else [time]
    if df.duplicated(key).any():
        raise ValueError(f"{key} 중복 행이 있다: 같은 시각을 먼저 집계한다")
    out = df.sort_values(time, kind="stable").copy()
    gkey = out[group] if group else pd.Series(0, index=out.index)
    for c in cols:
        s = out.groupby(gkey, sort=False)[c]
        for k in lags:
            out[f"{c}_lag{k}"] = s.shift(k)
        for w in windows:
            out[f"{c}_ma{w}"] = s.transform(lambda x: x.shift(1).rolling(w, min_periods=1).mean())
            out[f"{c}_sd{w}"] = s.transform(lambda x: x.shift(1).rolling(w, min_periods=2).std())
        out[f"{c}_diff1"] = s.shift(1) - s.shift(2)  # 현재 값을 쓰지 않으므로 타깃 열에도 안전
    return out.loc[df.index]


class SpcFeatures:
    """학습 분할로 fit: 대상별 중심·단기 시그마(MR/1.128). transform: z점수, 3σ 이탈, 이동범위.
    학습에 없던 대상은 전체 통계로 대신한다."""

    def __init__(self, cols, time, group=None):
        self.cols, self.time, self.group = cols, time, group

    def _groups(self, df):
        d = df.sort_values(self.time, kind="stable")
        return d.groupby(self.group, sort=False) if self.group else [(None, d)]

    def fit(self, train):
        self.stats = {}
        for g, d in self._groups(train):
            self.stats[g] = {c: (d[c].mean(), np.abs(d[c].diff()).mean() / D2) for c in self.cols}
        allstats = {c: (train[c].mean(), np.abs(train.sort_values(self.time)[c].diff()).mean() / D2) for c in self.cols}
        self.stats.setdefault("__all__", allstats)
        return self

    def transform(self, df):
        parts = []
        for g, d in self._groups(df):
            d = d.copy()
            for c in self.cols:
                cl, sigma = self.stats.get(g, self.stats["__all__"])[c]
                z = (d[c] - cl) / sigma if sigma and sigma > 0 else 0.0
                d[f"{c}_z"], d[f"{c}_out3"], d[f"{c}_mr"] = z, (np.abs(z) > 3).astype(int), d[c].diff().abs()
            parts.append(d)
        return pd.concat(parts).loc[df.index]


def add_ratios(df, pairs):
    """pairs = [("pressure", "temp"), ...]. 분모 0은 NaN."""
    out = df.copy()
    for a, b in pairs:
        out[f"{a}_per_{b}"] = out[a] / out[b].replace(0, np.nan)
    return out


if __name__ == "__main__":
    df = pd.DataFrame({"t": pd.date_range("2026-01-01", periods=6, freq="D").tolist() * 2,
                       "eq": ["A"] * 6 + ["B"] * 6, "v": [1, 2, 3, 4, 5, 6, 10, 20, 30, 40, 50, 60.0]})
    f = add_lag_rolling(df, ["v"], "t", group="eq", windows=(2,))
    assert np.isnan(f.loc[0, "v_lag1"]) and f.loc[1, "v_lag1"] == 1 and f.loc[7, "v_lag1"] == 10, "그룹 경계에서 섞이면 안 됨"
    assert f.loc[2, "v_ma2"] == 1.5, "현재 행(3)이 이동평균에 들어가면 누수"
    sp = SpcFeatures(["v"], "t", group="eq").fit(df)
    tr = sp.transform(df)
    assert tr.loc[0, "v_mr"] != tr.loc[0, "v_mr"] and tr.loc[6, "v_mr"] != tr.loc[6, "v_mr"], "대상 경계에서 MR이 이어지면 안 됨"
    assert np.isnan(add_ratios(pd.DataFrame({"a": [1.0], "b": [0.0]}), [("a", "b")]).iloc[0, -1])
    m = mark_missing(pd.DataFrame({"x": [1.0, -9999, 3.0]}), ["x"])
    assert m.x.isna().sum() == 1 and m.x_isna.tolist() == [0, 1, 0]
    log = pd.DataFrame({"wafer": ["W1"] * 4 + ["W2"] * 4, "ts": pd.date_range("2026-01-01", periods=8, freq="s"),
                        "step": ["S1", "S1", "S2", "S2"] * 2, "p": [1, 2, 3, 4, 2, 2, 2, 2.0]})
    w = aggregate_runs(log, "wafer", "ts", ["p"])
    assert len(w) == 2 and np.isclose(w.loc[0, "p_slope"], 1.0) and w.loc[1, "p_std"] == 0 and w.loc[0, "duration_s"] == 3
    ws = aggregate_runs(log, "wafer", "ts", ["p"], step="step")
    assert "p_mean@S2" in ws.columns and ws.loc[0, "p_mean@S2"] == 3.5
    print("features PASS")
