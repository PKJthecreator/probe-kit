"""제출 파일을 sample(또는 README가 정한 열)과 한 줄씩 대조한다. 실패 항목이 있으면 종료 코드 1.
사용: python check_submission.py submission.csv --sample sample_submission.csv [--allowed 0,1] [--range 0:1]
      python check_submission.py submission.csv --cols id,target --rows 1000
"""
import argparse
import csv
import sys


def read(path):
    with open(path, encoding="utf-8-sig", newline="") as f:
        rows = list(csv.reader(f))
    return rows[0], rows[1:]


def check(sub, sample=None, cols=None, rows=None, allowed=None, rng=None):
    head, body = read(sub)
    fails = []
    if sample:
        s_head, s_body = read(sample)
        cols, rows = s_head, len(s_body)
        if [r[0] for r in body] != [r[0] for r in s_body]:
            fails.append("ID 순서·값이 sample과 다르다(앞자리 0·정렬 확인)")
    if cols and head != cols:
        fails.append(f"열 이름·순서 {head} != {cols}")
    if rows is not None and len(body) != rows:
        fails.append(f"행 수 {len(body)} != {rows}")
    if len({r[0] for r in body}) != len(body):
        fails.append("ID 중복")
    vals = [r[1] if len(r) > 1 else "" for r in body]
    if any(v.strip() == "" or v.lower() == "nan" for v in vals):
        fails.append("예측 값 빈칸·NaN")
    if allowed and set(vals) - set(allowed):
        fails.append(f"허용 밖 값 {sorted(set(vals) - set(allowed))[:5]}")
    if rng:
        lo, hi = rng
        bad = [v for v in vals if not _num(v) or not lo <= float(v) <= hi]
        if bad:
            fails.append(f"범위 밖·숫자 아님 {bad[:5]}")
    return fails


def _num(v):
    try:
        float(v)
        return True
    except ValueError:
        return False


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("submission")
    ap.add_argument("--sample")
    ap.add_argument("--cols")
    ap.add_argument("--rows", type=int)
    ap.add_argument("--allowed")
    ap.add_argument("--range")
    a = ap.parse_args()
    fails = check(a.submission, a.sample, a.cols.split(",") if a.cols else None, a.rows,
                  a.allowed.split(",") if a.allowed else None, tuple(map(float, a.range.split(":"))) if a.range else None)
    print("SUBMISSION PASS" if not fails else "SUBMISSION FAIL\n- " + "\n- ".join(fails))
    sys.exit(1 if fails else 0)
