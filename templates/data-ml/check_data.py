"""데이터 첫 점검 (probe-data-check 1의 스크립트판). 원본은 읽기만 한다.
사용: python check_data.py train.csv [--target y] [--time date] [--id id] [--test test.csv]
출력은 요약만. 자세한 표가 필요하면 outputs/에 따로 저장한다.
"""
import argparse
import re

import pandas as pd

# 대화·로그에 원본 값이 남지 않게 출력 직전에 가린다(사번처럼 과제마다 다른 형식은 --mask로 추가)
MASKS = [r"01[016789]-?\d{3,4}-?\d{4}", r"[\w.+-]+@[\w-]+\.[\w.]+", r"(?i)(pass\w*|pwd|secret|token|api_?key|conn\w*)\s*[=:]\s*\S+"]


SENSITIVE_COL = re.compile(r"(?i)(^|_)(id|user|name|phone|tel|mobile|email|emp|operator|owner|worker|comment|note|memo)(_|$)|사번|이름|성명|전화|연락처|담당|작업자|비고|메모")


def visible(df, hide=()):
    """값(최소·최대 등)을 보여도 되는 열만. 이름이 사람·ID·자유 텍스트처럼 보이는 열은 뺀다(--hide로 추가)."""
    return [c for c in df.columns if not SENSITIVE_COL.search(str(c)) and c not in hide]


def mask(text, extra=()):
    for rx in [*MASKS, *extra]:
        text = re.sub(rx, "***", text)
    return text


def read(path, id_col=None):
    # ID 열은 문자열로 읽는다(앞자리 0·큰 정수가 숫자 변환에서 깨지지 않게).
    if str(path).endswith(".parquet"):
        df = pd.read_parquet(path)
        return df.astype({id_col: str}) if id_col else df
    return pd.read_csv(path, low_memory=False, dtype={id_col: str} if id_col else None)


def profile(df, target=None, time=None, id_col=None, extra_masks=(), show_rows=False, extra_hide=()):
    print(f"shape={df.shape}")
    print(df.dtypes.value_counts().to_dict())
    if show_rows:  # 기본은 원본 행을 출력하지 않는다(이름·사번은 정규식으로 다 못 가린다)
        print(mask(df.head(3).to_string(max_cols=12, max_colwidth=20), extra_masks))
    else:
        ok = set(visible(df, (*extra_hide, id_col)))
        print("열 요약(dtype, 고유값 수, 숫자 열은 범위. 사람·ID·메모 열은 값 생략):",
              {c: (str(df[c].dtype), int(df[c].nunique())) + ((df[c].min(), df[c].max()) if c in ok and df[c].dtype != object else ())
               for c in df.columns[:30]})
    miss = df.isna().mean()
    miss = miss[miss > 0].sort_values(ascending=False)
    print("결측 비율(0 초과):", miss.round(3).head(15).to_dict())
    print("완전 중복 행:", int(df.duplicated().sum()))
    const = [c for c in df.columns if df[c].nunique(dropna=False) <= 1]
    print("값이 하나뿐인 열:", const)
    keys = [(c, df[c].nunique()) for c in df.columns if df[c].dtype.kind != "f" and df[c].nunique() >= 0.9 * len(df)]
    print("키 후보(고유값≥90%):", keys[:8])
    if id_col:
        print(f"id 중복={int(df[id_col].duplicated().sum())} 결측={int(df[id_col].isna().sum())}")
    target_ok = target in visible(df, (*extra_hide, id_col))  # 민감 열이 타깃이면 값 대신 개수만
    if target:
        y = df[target]
        print("타깃 분포:", f"고유값 {y.nunique()}개(민감 열이라 값 생략)" if not target_ok else y.value_counts(normalize=True).head(10).round(3).to_dict() if y.nunique() <= 20 else y.describe().round(3).to_dict())
        feats = [c for c in df.columns if c not in (target, id_col)]
        if feats and len(feats) <= 60 and len(df) <= 200_000:  # 큰 표에서는 비용이 커서 생략
            conflict = df.groupby(feats, dropna=False)[target].nunique()
            print("특징 같고 타깃 다른 묶음:", int((conflict > 1).sum()))
        num = df.select_dtypes("number").drop(columns=[target], errors="ignore")
        if pd.api.types.is_numeric_dtype(y) and not num.empty:
            corr = num.corrwith(y).abs().sort_values(ascending=False).head(5)
            print("타깃과 |상관| 상위(0.95 이상이면 누수 의심):", corr.round(3).to_dict())
        sus = [c for c in df.columns if any(k in c.lower() for k in ("label", "result", "flag", "hold", "judge", "판정", "결과"))]
        print("이름으로 본 누수 후보:", sus)
    if time:
        t = pd.to_datetime(df[time], errors="coerce")
        print(f"시간 범위 {t.min()} ~ {t.max()} 정렬={t.is_monotonic_increasing} 변환실패={int(t.isna().sum())}")
        print("간격 상위:", t.sort_values().diff().value_counts().head(3).to_dict())
        if target and target_ok and pd.api.types.is_numeric_dtype(df[target]):
            half = t <= t.median()
            print(f"기간 앞/뒤 타깃 평균: {df.loc[half, target].mean():.4g} / {df.loc[~half, target].mean():.4g}")
    num = df[visible(df, (*extra_hide, id_col))].select_dtypes("number")
    if not num.empty:
        print("수치 min/중앙값/max (불가능한 값 확인):")
        print(num.describe(percentiles=[0.5]).T[["min", "50%", "max"]].head(20).round(3).to_string())


def compare_test(train, test, target=None, id_col=None):
    cols_tr = set(train.columns) - {target}
    print("test에 없는 열:", sorted(cols_tr - set(test.columns)), "/ train에 없는 열:", sorted(set(test.columns) - cols_tr))
    for c in train.select_dtypes("object").columns:
        if c in test and c not in (target, id_col):
            new = set(test[c].dropna()) - set(train[c].dropna())
            if new:
                print(f"test 새 범주 {c}: {len(new)}개")  # 값은 출력하지 않는다


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("path")
    ap.add_argument("--target")
    ap.add_argument("--time")
    ap.add_argument("--id", dest="id_col")
    ap.add_argument("--test")
    ap.add_argument("--mask", action="append", default=[], help="추가로 가릴 정규식(예: 사번 형식)")
    ap.add_argument("--show-rows", action="store_true", help="앞 3행을 가린 채 출력(민감정보가 없다고 확인한 뒤에만)")
    ap.add_argument("--hide", action="append", default=[], help="값을 출력하지 않을 열(사번처럼 이름으로 안 잡히는 열)")
    a = ap.parse_args()
    tr = read(a.path, a.id_col)
    profile(tr, a.target, a.time, a.id_col, a.mask, a.show_rows, a.hide)
    if a.test:
        compare_test(tr, read(a.test, a.id_col), a.target, a.id_col)
