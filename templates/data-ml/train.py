"""표 데이터 예측 뼈대: 분할 → 기준선 → 후보 모델 → 검증 지표 → 제출 파일.
과제 README의 지표·분할·제출 형식이 이 기본값보다 우선한다. 뼈대이므로 과제에 맞게 고쳐 쓴다.

사용:
  python train.py --train train.csv --target y [--test test.csv --id id --sample sample_submission.csv]
                  [--time date | --group lot_id] [--task clf|reg] [--metric f1] [--drop col1,col2]
  python train.py ... --cost 10:1     # 이진 분류: 놓침(FN) 1건 비용 10, 오경보(FP) 1건 비용 1로 검증에서 임계값 선택
  python train.py ... --proba        # 제출에 라벨 대신 양성 확률(과제가 확률을 요구할 때)
  python train.py ... --cv 5         # 후보를 k겹 교차검증 평균±표준편차로 비교(시간·그룹 분할 규칙 그대로)
  python train.py ... --final        # 확정 뒤 한 번만: 내부 holdout 평가 (보고 다시 고르지 않는다)
  python train.py --demo             # 합성 데이터로 자체 점검
분할: --time(기존 대상의 미래) > --group(처음 보는 설비·로트) > 무작위(분류면 층화).
산출: outputs/metrics.json(데이터 해시·버전 포함), outputs/valid_predictions.csv, outputs/importance.csv, 제출 파일(--out).
"""
import hashlib
import platform
import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import sklearn
from sklearn.compose import ColumnTransformer
from sklearn.dummy import DummyClassifier, DummyRegressor
from sklearn.ensemble import HistGradientBoostingClassifier, HistGradientBoostingRegressor
from sklearn.impute import SimpleImputer
from sklearn.inspection import permutation_importance
from sklearn.linear_model import LogisticRegression, Ridge
from sklearn.metrics import (accuracy_score, average_precision_score, confusion_matrix, f1_score,
                             mean_absolute_error, mean_squared_error, precision_recall_curve,
                             precision_score, r2_score, recall_score, roc_auc_score)
from sklearn.model_selection import GroupShuffleSplit, train_test_split
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import OneHotEncoder, OrdinalEncoder, StandardScaler

SEED = 42
OUT = Path("outputs")


def split(df, target, task, time=None, group=None, frac=0.2):
    """(앞, 뒤) 인덱스. 시간이면 뒤가 미래, 그룹이면 같은 그룹이 양쪽에 섞이지 않는다."""
    if time:
        t = pd.to_datetime(df[time], errors="coerce")
        if t.isna().any():
            raise ValueError(f"시간 열 {time}에 변환 실패 {int(t.isna().sum())}행: 먼저 정리한다")
        cut_time = t.sort_values().iloc[int(len(t) * (1 - frac))]
        return df.index[t < cut_time], df.index[t >= cut_time]  # 같은 시각은 같은 쪽에
    if group:
        if df[group].nunique() < 2:  # 분할 한 번에 2개 이상. 학습·검증·holdout 셋으로 나누려면 전체 3개 이상
            raise ValueError(f"그룹({group})이 {df[group].nunique()}개뿐이라 더 나눌 수 없다(학습·검증·holdout에 전체 3개 이상 필요): 담당자와 시간·무작위 분할을 정한다")
        tr, va = next(GroupShuffleSplit(n_splits=1, test_size=frac, random_state=SEED).split(df, groups=df[group]))
        return df.index[tr], df.index[va]
    strat = df[target] if task == "clf" and df[target].value_counts().min() >= 2 else None
    tr, va = train_test_split(df.index, test_size=frac, random_state=SEED, stratify=strat)
    return pd.Index(tr), pd.Index(va)


def candidates(task, num, cat, y):
    """기준선(dummy·선형) + 트리 부스팅. LightGBM·XGBoost는 설치돼 있을 때만 추가(새 설치는 승인 후)."""
    linear_pre = ColumnTransformer([
        ("num", make_pipeline(SimpleImputer(strategy="median"), StandardScaler()), num),
        ("cat", make_pipeline(SimpleImputer(strategy="most_frequent"), OneHotEncoder(handle_unknown="ignore")), cat)])
    tree_pre = ColumnTransformer([
        ("num", "passthrough", num),
        ("cat", OrdinalEncoder(handle_unknown="use_encoded_value", unknown_value=-1, encoded_missing_value=-1), cat)])
    if task == "clf":
        models = {"dummy": make_pipeline(linear_pre, DummyClassifier(strategy="prior")),
                  "logistic": make_pipeline(linear_pre, LogisticRegression(max_iter=2000, class_weight="balanced")),
                  "hgb": make_pipeline(tree_pre, HistGradientBoostingClassifier(random_state=SEED, class_weight="balanced"))}
    else:
        models = {"dummy": make_pipeline(linear_pre, DummyRegressor(strategy="median")),
                  "ridge": make_pipeline(linear_pre, Ridge()),
                  "hgb": make_pipeline(tree_pre, HistGradientBoostingRegressor(random_state=SEED))}
    try:
        import lightgbm as lgb
        est = lgb.LGBMClassifier(random_state=SEED, verbose=-1, class_weight="balanced") if task == "clf" else lgb.LGBMRegressor(random_state=SEED, verbose=-1)
        models["lgbm"] = make_pipeline(tree_pre, est)
    except ImportError:
        pass
    try:
        import xgboost as xgb
        if task == "reg" or set(y.unique()) == set(range(y.nunique())):  # XGB 분류는 라벨이 0..k-1일 때만
            est = xgb.XGBClassifier(random_state=SEED, n_estimators=300) if task == "clf" else xgb.XGBRegressor(random_state=SEED, n_estimators=300)
            models["xgb"] = make_pipeline(tree_pre, est)
    except ImportError:
        pass
    return models


LOWER_BETTER = {"mae", "rmse"}


def scores(task, y, pred, proba=None, classes=None):
    if task == "reg":
        return {"mae": round(mean_absolute_error(y, pred), 4), "rmse": round(mean_squared_error(y, pred) ** 0.5, 4), "r2": round(r2_score(y, pred), 4)}
    s = {"accuracy": accuracy_score(y, pred), "f1_macro": f1_score(y, pred, average="macro")}
    if proba is not None and proba.shape[1] == 2:  # 이진: 양성 = model.classes_[1] (예: 1, "NG")
        pos = classes[1]
        s |= {"f1": f1_score(y, pred, pos_label=pos, zero_division=0), "precision": precision_score(y, pred, pos_label=pos, zero_division=0),
              "recall": recall_score(y, pred, pos_label=pos, zero_division=0), "n_pos": int((y == pos).sum())}
        if (y == pos).any() and not (y == pos).all():  # 한 클래스뿐이면 AUC 계산 불가 → 생략
            s |= {"roc_auc": roc_auc_score(y == pos, proba[:, 1]), "pr_auc": average_precision_score(y == pos, proba[:, 1])}
    return {k: round(float(v), 4) for k, v in s.items()}


def cost_threshold(y, p_pos, pos, cost_fn, cost_fp):
    """검증 분할에서 FN·FP 비용 합이 최소인 양성 확률 임계값."""
    _, _, th = precision_recall_curve(y == pos, p_pos)
    yp = y.to_numpy() == pos
    costs = [cost_fn * (yp & (p_pos < t)).sum() + cost_fp * (~yp & (p_pos >= t)).sum() for t in th]
    return float(th[int(np.argmin(costs))])


def cv_scores(models, X, y, d, a, task, metric, results):
    """분할 방식은 데이터 계약과 같게: 시간 → 시각 단위 TimeSeriesSplit(같은 시각은 한쪽에, 앞으로만),
    그룹 → GroupKFold, 분류 → 층화. 폴드 하나가 실패해도(한 클래스뿐 등) 그 폴드만 빼고 개수를 남긴다."""
    from sklearn.base import clone
    from sklearn.model_selection import GroupKFold, KFold, StratifiedKFold, TimeSeriesSplit
    if a.time:
        t = pd.to_datetime(d.loc[X.index, a.time])
        uniq = np.sort(t.unique())
        k = min(a.cv, len(uniq) - 1)
    elif a.group:
        groups = d.loc[X.index, a.group]
        k = min(a.cv, groups.nunique())
    elif task == "clf":
        k = min(a.cv, int(y.value_counts().min()))
    else:
        k = min(a.cv, len(X))
    if k < 2:  # 분할기를 만들기 전에 본다(k<2면 생성 단계에서 예외)
        print(f"교차검증 생략: 나눌 수 있는 단위가 부족(k={k})")
        return
    if a.time:
        folds = [(np.flatnonzero(t.isin(uniq[tr]).to_numpy()), np.flatnonzero(t.isin(uniq[va]).to_numpy()))
                 for tr, va in TimeSeriesSplit(k).split(uniq)]
    elif a.group:
        folds = list(GroupKFold(k).split(X, y, groups))
    elif task == "clf":
        folds = list(StratifiedKFold(k, shuffle=True, random_state=SEED).split(X, y))
    else:
        folds = list(KFold(k, shuffle=True, random_state=SEED).split(X))
    for name, m in models.items():
        if "error" in results[name]:
            continue
        vals, failed = [], 0
        for tr_i, va_i in folds:
            try:
                mm = clone(m).fit(X.iloc[tr_i], y.iloc[tr_i])
                proba = mm.predict_proba(X.iloc[va_i]) if task == "clf" else None
                vals.append(scores(task, y.iloc[va_i], mm.predict(X.iloc[va_i]), proba, getattr(mm, "classes_", None)).get(metric, np.nan))
            except Exception:
                failed += 1
        if not vals:
            results[name]["cv"] = {"mean": np.nan, "std": np.nan, "folds": 0, "failed": failed}
            continue
        results[name]["cv"] = {"mean": round(float(np.nanmean(vals)), 4), "std": round(float(np.nanstd(vals)), 4), "folds": len(vals), "failed": failed}
        print(f"{name:9s} cv {metric} {results[name]['cv']['mean']} ± {results[name]['cv']['std']} ({len(vals)}겹, 실패 {failed})")


def fit_eval(model, task, Xtr, ytr, Xva, yva):
    model.fit(Xtr, ytr)
    out = {}
    for name, X, y in (("train", Xtr, ytr), ("valid", Xva, yva)):
        proba = model.predict_proba(X) if task == "clf" else None
        out[name] = scores(task, y, model.predict(X), proba, getattr(model, "classes_", None))
    return out


def run(a):
    if tuple(int(x) for x in sklearn.__version__.split(".")[:2]) < (1, 2):
        sys.exit(f"scikit-learn {sklearn.__version__}: 1.2 이상 필요(HGB class_weight 등). 업그레이드 승인 또는 후보를 줄인다")
    df = pd.read_csv(a.train, dtype={a.id: str} if a.id else None)
    task = a.task or ("clf" if df[a.target].dtype == object or df[a.target].nunique() <= 20 else "reg")  # 틀리면 --task
    metric = a.metric or ("f1" if task == "clf" and df[a.target].nunique() == 2 else "f1_macro" if task == "clf" else "mae")
    drop = {a.target, a.id, a.time, a.group, *filter(None, (a.drop or "").split(","))} - {None}
    feats = [c for c in df.columns if c not in drop]
    num = df[feats].select_dtypes("number").columns.tolist()
    cat = [c for c in feats if c not in num]

    rest, hold = split(df, a.target, task, a.time, a.group, frac=0.15)       # 내부 holdout: --final 전에는 보지 않는다
    tr, va = split(df.loc[rest], a.target, task, a.time, a.group, frac=0.2)
    X, y = df[feats], df[a.target]
    if task == "clf" and y.loc[tr].nunique() < 2:
        raise ValueError("학습 분할에 클래스가 하나뿐: 분할 방식·기간을 바꾸거나 담당자와 타깃 정의를 확인한다")
    print(f"task={task} metric={metric} rows train/valid/holdout={len(tr)}/{len(va)}/{len(hold)} num={len(num)} cat={len(cat)}")

    results = {}
    models = candidates(task, num, cat, y)
    for name, m in models.items():
        try:
            results[name] = fit_eval(m, task, X.loc[tr], y.loc[tr], X.loc[va], y.loc[va])
        except Exception as e:  # 후보 하나의 실패가 전체를 멈추지 않게. 실패도 기록한다(crash)
            results[name] = {"error": f"{type(e).__name__}: {e}"}
        print(f"{name:9s}", results[name].get("error") or f"train {results[name]['train'].get(metric)}  valid {results[name]['valid'].get(metric)}")
    if a.cv:  # 남은 학습 부분(holdout 제외)에서 k겹 교차검증: 평균±표준편차로 고른다(데이터가 적거나 차이가 작을 때)
        cv_scores(models, X.loc[rest], y.loc[rest], df.loc[rest], a, task, metric, results)
    ok = {k: v for k, v in results.items() if "error" not in v and metric in v["valid"]}
    if not ok:
        raise ValueError(f"지표 {metric}를 계산한 후보가 없다. 결과: {results}")
    use_cv = a.cv and all(not np.isnan(v.get("cv", {}).get("mean", np.nan)) for v in ok.values())
    key = (lambda k: ok[k]["cv"]["mean"]) if use_cv else (lambda k: ok[k]["valid"][metric])
    pick = a.model or (min if metric in LOWER_BETTER else max)(ok, key=key)
    best = models[pick]
    best.fit(X.loc[tr], y.loc[tr])  # 마지막 루프 모델이 아닐 수 있으니 다시 맞춘다
    binary = task == "clf" and y.nunique() == 2
    thr, pos = 0.5, (best.classes_[1] if binary else None)
    if binary and a.cost:
        cfn, cfp = map(float, a.cost.split(":"))
        thr = cost_threshold(y.loc[va], best.predict_proba(X.loc[va])[:, 1], pos, cfn, cfp)
        print(f"비용 {a.cost}(FN:FP) 기준 임계값 {thr:.4f} (검증에서 선택, holdout으로 다시 고르지 않는다)")
        # results의 valid 점수는 임계값 0.5 기준이다. 실제로 쓰는 임계값의 점수는 valid_at_threshold로 따로 남긴다.

    def predict(Xp):
        if binary and a.cost:
            return np.where(best.predict_proba(Xp)[:, 1] >= thr, pos, best.classes_[0])
        return best.predict(Xp)

    OUT.mkdir(exist_ok=True)
    va_pred = pd.DataFrame({"row": va, "y": y.loc[va].values, "pred": predict(X.loc[va])})
    if a.id:
        va_pred.insert(0, a.id, df.loc[va, a.id].values)
    va_pred.to_csv(OUT / "valid_predictions.csv", index=False)  # FP/FN·큰 잔차 분석용(probe-experiment 4)
    if task == "clf":
        labels = sorted(y.unique())
        pd.DataFrame(confusion_matrix(va_pred.y, va_pred.pred, labels=labels), index=labels, columns=labels).to_csv(OUT / "confusion_matrix.csv")
    imp = permutation_importance(best, X.loc[va], y.loc[va], n_repeats=5, random_state=SEED)  # 관계의 크기일 뿐 원인이 아니다
    pd.Series(imp.importances_mean, index=feats).sort_values(ascending=False).head(30).to_csv(OUT / "importance.csv", header=["perm_importance"])

    at_thr = scores(task, y.loc[va], predict(X.loc[va]), best.predict_proba(X.loc[va]), best.classes_) if binary and a.cost else None
    report = {"task": task, "metric": metric, "picked": pick, "threshold": thr if binary else None, "valid_at_threshold": at_thr,
              "split": {"time": a.time, "group": a.group, "seed": SEED},
              "manifest": {"train_sha256": hashlib.sha256(Path(a.train).read_bytes()).hexdigest()[:16], "python": platform.python_version(),
                           "sklearn": sklearn.__version__, "pandas": pd.__version__},
              "rows": {"train": len(tr), "valid": len(va), "holdout": len(hold)}, "features": feats, "results": results}
    if a.final:  # 확정 설정 그대로 holdout 한 번
        proba = best.predict_proba(X.loc[hold]) if task == "clf" else None
        report["holdout"] = scores(task, y.loc[hold], predict(X.loc[hold]), proba, getattr(best, "classes_", None))
        print("HOLDOUT", report["holdout"])
    (OUT / "metrics.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    if a.test:
        te = pd.read_csv(a.test, dtype={a.id: str} if a.id else None)
        pred = best.predict_proba(te[feats])[:, 1] if a.proba and binary else predict(te[feats])
        key0 = a.id or "id"
        out = pd.DataFrame({key0: te[a.id] if a.id else range(len(te)), "pred": pred})
        if a.sample:  # sample의 열 이름·ID 순서를 그대로 따른다
            sample = pd.read_csv(a.sample, dtype=str)
            key, col = sample.columns[0], sample.columns[1]
            if sample[key].duplicated().any() or out[key0].duplicated().any():
                raise ValueError("sample 또는 test에 중복 ID가 있다: 담당자에게 제출 단위를 확인한다")
            if len(sample) != len(out) or set(sample[key]) != set(out[key0].astype(str)):
                raise ValueError(f"sample과 test의 ID 집합·행 수가 다르다: sample {len(sample)} / test {len(out)}")
            sub = sample[[key]].merge(out.astype({key0: str}).rename(columns={key0: key, "pred": col}), on=key, how="left", validate="one_to_one")
        else:
            sub = out.rename(columns={"pred": a.target})
        assert sub.iloc[:, 1].notna().all(), "예측 결측"
        sub.to_csv(a.out, index=False)
        print(f"제출 파일 {a.out}: {sub.shape}, 열 {sub.columns.tolist()} - README 형식과 대조할 것(probe-verify)")
    return report


def demo():
    rng = np.random.default_rng(0)
    n = 1200
    df = pd.DataFrame({"id": [f"{i:05d}" for i in range(n)], "date": pd.date_range("2026-01-01", periods=n, freq="h"),
                       "line": rng.choice(["A", "B", "C"], n), "temp": rng.normal(200, 5, n), "pressure": rng.normal(1.0, 0.1, n)})
    df.loc[rng.choice(n, 50, replace=False), "pressure"] = np.nan
    logit = 0.4 * (df.temp - 200) + 3 * (df.pressure.fillna(1) - 1) + (df.line == "C") * 1.0 - 2
    df["defect"] = (rng.random(n) < 1 / (1 + np.exp(-logit))).astype(int)
    tmp = Path("outputs") / "_demo"
    tmp.mkdir(parents=True, exist_ok=True)
    df.to_csv(tmp / "train.csv", index=False)
    df.drop(columns="defect").tail(100).to_csv(tmp / "test.csv", index=False)
    pd.DataFrame({"id": df.id.tail(100).iloc[::-1], "defect": 0}).to_csv(tmp / "sample.csv", index=False)  # 순서가 test와 다르다
    a = parse(["--train", str(tmp / "train.csv"), "--target", "defect", "--id", "id", "--time", "date", "--cost", "5:1",
               "--test", str(tmp / "test.csv"), "--sample", str(tmp / "sample.csv"), "--out", str(tmp / "submission.csv"), "--final", "--cv", "3"])
    r = run(a)
    assert all("cv" in v for v in r["results"].values()), "교차검증 결과"
    best = r["results"][r["picked"]]["valid"]["f1"]
    assert best > r["results"]["dummy"]["valid"]["f1"], "기준선보다 나아야 함"
    sub = pd.read_csv(tmp / "submission.csv", dtype={"id": str})
    assert len(sub) == 100 and sub.id.iloc[0] == "01199", "제출 행 수·sample ID 순서·문자열 보존"
    print("demo PASS")


def parse(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--train")
    ap.add_argument("--target")
    ap.add_argument("--test")
    ap.add_argument("--id")
    ap.add_argument("--sample", help="sample_submission.csv: 열 이름·순서를 그대로 쓴다")
    ap.add_argument("--out", default="submission.csv")
    ap.add_argument("--time")
    ap.add_argument("--group")
    ap.add_argument("--task", choices=["clf", "reg"])
    ap.add_argument("--metric")
    ap.add_argument("--model", help="자동 선택 대신 이 후보로 확정")
    ap.add_argument("--drop", help="입력에서 뺄 열(누수 후보 등), 쉼표 구분")
    ap.add_argument("--cost", help="이진 분류 FN:FP 비용, 예 10:1")
    ap.add_argument("--proba", action="store_true", help="제출을 양성 확률로")
    ap.add_argument("--cv", type=int, help="k겹 교차검증으로 후보 비교(holdout은 제외한 부분에서)")
    ap.add_argument("--final", action="store_true")
    ap.add_argument("--demo", action="store_true")
    return ap.parse_args(argv)


if __name__ == "__main__":
    args = parse()
    if args.demo:
        demo()
    elif not (args.train and args.target):
        sys.exit("--train, --target 필요 (또는 --demo)")
    else:
        run(args)
