"""집계·그룹 비교 뼈대(모델 없는 분석 과제, 또는 모델 전 분석).
- 그룹별 건수(분모)·평균·중앙값·비율을 한 표로, 전체 대비 차이와 효과 크기(Cohen's d / 비율 차)를 함께
- 같은 집계를 SQL(sqlite3, 표준 라이브러리)로 한 번 더 계산해 pandas 결과와 대조(핵심 숫자 이중 확인)
- scipy가 있으면 검정(두 그룹 t-검정 Welch / 셋 이상 ANOVA·Kruskal / 비율은 카이제곱). 없으면 NOT_RUN
사용: python analyze.py --data x.csv --group line --value thk [--rate defect]   (기간·대상 필터는 미리 해서 넣는다)
      python analyze.py --demo
산출: outputs/group_summary.csv, outputs/analysis.json (그림이 필요하면 matplotlib로 이 표를 그린다)
"""
import argparse
import json
import sqlite3
from pathlib import Path

import numpy as np
import pandas as pd

OUT = Path("outputs")


def summarize(df, group, value, rate=None):
    g = df.groupby(group, dropna=False)
    t = pd.DataFrame({"n": g[value].count(), "missing": g[value].apply(lambda s: int(s.isna().sum())),
                      "mean": g[value].mean(), "median": g[value].median(), "std": g[value].std(ddof=1)})
    mu, sd = df[value].mean(), df[value].std(ddof=1)
    t["diff_vs_all"] = t["mean"] - mu
    t["cohen_d_vs_all"] = t["diff_vs_all"] / sd if sd else np.nan   # 0.2 작음 · 0.5 중간 · 0.8 큼(관례)
    if rate:
        t["rate"] = g[rate].mean()            # 0/1 열의 비율. 분모는 n이 아니라 rate 열의 비결측 수
        t["rate_n"] = g[rate].count()
        t["rate_diff_pp"] = (t["rate"] - df[rate].mean()) * 100   # 퍼센트포인트
    return t.reset_index()


def sql_check(df, group, value, rate=None):
    """같은 숫자를 SQL로 다시 계산(pandas와 다른 경로). 열 이름은 큰따옴표로 감싼다."""
    con = sqlite3.connect(":memory:")
    df.to_sql("t", con, index=False)
    q = f'SELECT "{group}" AS g, COUNT("{value}") AS n, AVG("{value}") AS mean' + (f', AVG("{rate}") AS rate' if rate else "") + \
        f' FROM t GROUP BY "{group}"'
    return pd.read_sql_query(q, con)


def tests(df, group, value, rate=None):
    try:
        from scipy import stats
    except ImportError:
        return {"status": "NOT_RUN", "reason": "scipy 없음"}
    groups = [s.dropna().to_numpy() for _, s in df.groupby(group)[value] if s.notna().sum() >= 2]
    out = {}
    if len(groups) == 2:
        out["welch_t"] = stats.ttest_ind(*groups, equal_var=False)._asdict()
    elif len(groups) > 2:
        out["anova"] = stats.f_oneway(*groups)._asdict()
        out["kruskal"] = stats.kruskal(*groups)._asdict()   # 정규성이 의심되면 이쪽을 본다
    if rate:
        table = pd.crosstab(df[group], df[rate])
        if table.shape[1] == 2:
            chi = stats.chi2_contingency(table)
            out["chi2"] = {"statistic": chi.statistic, "pvalue": chi.pvalue}
    return {k: {kk: float(vv) for kk, vv in v.items()} for k, v in out.items()} | {"note": "여러 번 비교하면 보정(Bonferroni 등). p값만으로 결론 내지 않고 효과 크기와 함께"}


def run(a):
    df = pd.read_csv(a.data)
    df[a.group] = df[a.group].astype("string").fillna("(결측)")   # 그룹이 빈 행도 한 그룹으로(SQL NULL과 대조가 어긋나지 않게)
    s = summarize(df, a.group, a.value, a.rate)
    chk = sql_check(df, a.group, a.value, a.rate)
    merged = s.merge(chk, left_on=a.group, right_on="g", suffixes=("", "_sql"))
    agree = bool(np.allclose(merged["n"], merged["n_sql"]) and np.allclose(merged["mean"], merged["mean_sql"]))
    OUT.mkdir(exist_ok=True)
    s.to_csv(OUT / "group_summary.csv", index=False)
    report = {"rows": len(df), "groups": len(s), "sql_crosscheck": "PASS" if agree else "FAIL", "tests": tests(df, a.group, a.value, a.rate)}
    (OUT / "analysis.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(s.round(3).to_string(index=False))
    print("SQL 재계산:", report["sql_crosscheck"], "| 검정:", {k: round(v.get("pvalue", np.nan), 4) for k, v in report["tests"].items() if isinstance(v, dict)})
    return report


def parse(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--data")
    ap.add_argument("--group")
    ap.add_argument("--value")
    ap.add_argument("--rate", help="0/1 열(불량 여부 등)")
    ap.add_argument("--demo", action="store_true")
    return ap.parse_args(argv)


def demo():
    rng = np.random.default_rng(3)
    n = 300
    df = pd.DataFrame({"line": rng.choice(["A", "B", "C"], n), "thk": rng.normal(100, 2, n)})
    df.loc[df.line == "C", "thk"] += 3
    df["defect"] = (df.thk > 103).astype(int)
    df.loc[5, "thk"] = np.nan
    df.loc[7, "line"] = np.nan
    tmp = OUT / "_demo"
    tmp.mkdir(parents=True, exist_ok=True)
    df.to_csv(tmp / "x.csv", index=False)
    r = run(parse(["--data", str(tmp / "x.csv"), "--group", "line", "--value", "thk", "--rate", "defect"]))
    s = pd.read_csv(OUT / "group_summary.csv")
    assert r["sql_crosscheck"] == "PASS"
    assert s.loc[s.line == "C", "cohen_d_vs_all"].item() > 0.5, "C 라인이 크게 높다"
    assert s["n"].sum() == n - 1 and s["missing"].sum() == 1, "결측은 분모에서 빠지고 따로 센다"
    assert "(결측)" in set(s.line), "그룹이 빈 행도 숨기지 않는다"
    print("analyze demo PASS")


if __name__ == "__main__":
    args = parse()
    demo() if args.demo else run(args)
