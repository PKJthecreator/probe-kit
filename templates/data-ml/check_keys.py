"""여러 CSV 사이 키 관계 점검(probe-data-check 3). 표준 라이브러리만 쓰고 원본 값은 출력하지 않는다(건수·줄 번호만).
사용: python check_keys.py --fk 탑승.csv:emp_id=직원.csv:emp_id [--fk 자식.csv:열=부모.csv:열 ...]
      python check_keys.py --demo
판정: 고아 키(부모에 없는 자식 키)·부모 키 중복 = 오류(종료 1). 빈 키·참조 안 된 부모 = 정보.
입력을 믿을 수 없으면 종료 2: 파일·열이 없음, 머리글 이름 중복(DictReader가 앞 열 값을 덮는다), 칸 수가 머리글과 다른 행.
키는 문자열 그대로 비교한다(앞자리 0 보존, 양끝 공백만 제거). BOM은 utf-8-sig로 읽는다.
처리 규칙(고아 행을 버릴지·보존할지·표시할지)은 담당자 답과 함께 경계 판단표·결정 절에 남긴다.
"""
import argparse
import csv
import sys
import tempfile
from pathlib import Path


def die(msg):
    print(msg, file=sys.stderr)
    sys.exit(2)


def keys(path, col):
    """(키, 줄 번호) 목록과 칸 수가 머리글과 다른 행의 줄 번호."""
    try:
        f = open(path, newline="", encoding="utf-8-sig")
    except OSError as e:
        die(f"{path}: 열 수 없음 ({e.strerror})")
    with f:
        r = csv.DictReader(f)
        names = r.fieldnames or []
        if col not in names:
            die(f"{path}: 열 '{col}' 없음 (머리글 {len(names)}칸)")
        if len(set(names)) != len(names):
            die(f"{path}: 머리글 이름 중복, 같은 이름의 앞 열 값이 덮인다")
        out, bad = [], []
        for row in r:
            if None in row or None in row.values():  # 칸이 남거나(키 None) 모자람(값 None) — 빈 키로 숨지 않게 따로 센다
                bad.append(r.line_num)
            out.append(((row.get(col) or "").strip(), r.line_num))
    return out, bad


def check(child, ccol, parent, pcol):
    kids, kbad = keys(child, ccol)
    pars, pbad = keys(parent, pcol)
    seen, dup = set(), []
    for k, n in pars:
        if k and k in seen:
            dup.append(n)
        seen.add(k)
    used = {k for k, _ in kids}
    return {
        "rows": len(kids),
        "orphan": [n for k, n in kids if k and k not in seen],
        "dup": dup,
        "empty_child": sum(1 for k, _ in kids if not k),
        "empty_parent": sum(1 for k, _ in pars if not k),
        "unref": sum(1 for k in seen if k and k not in used),
        "bad_child": kbad,
        "bad_parent": pbad,
    }


def report(spec, r):
    """출력하고 종료 코드(0 정상 / 1 관계 오류 / 2 입력 오류)를 돌려준다."""
    head = lambda xs: (", ".join(map(str, xs[:5])) + (" ..." if len(xs) > 5 else "")) or "-"
    print(f"{spec}  자식 {r['rows']}행")
    print(f"  오류: 고아 키 {len(r['orphan'])}건(줄 {head(r['orphan'])}) / 부모 키 중복 {len(r['dup'])}건(줄 {head(r['dup'])})")
    print(f"  정보: 빈 자식 키 {r['empty_child']} · 빈 부모 키 {r['empty_parent']} · 참조 안 된 부모 {r['unref']}")
    if r["bad_child"] or r["bad_parent"]:
        print(f"  입력 오류: 칸 수가 머리글과 다른 행: 자식 줄 {head(r['bad_child'])} / 부모 줄 {head(r['bad_parent'])}. 이 판정은 믿을 수 없다")
        return 2
    return 1 if (r["orphan"] or r["dup"]) else 0


def parse(spec):
    try:
        left, right = spec.split("=", 1)
        (c, cc), (p, pc) = left.rsplit(":", 1), right.rsplit(":", 1)  # rsplit: 드라이브 문자(C:)를 살린다
    except ValueError:
        die(f"--fk 형식: 자식.csv:열=부모.csv:열 (받은 값 {spec!r})")
    return c, cc, p, pc


def demo():
    nl = chr(10)
    with tempfile.TemporaryDirectory() as d:
        par, kid = Path(d, "emp.csv"), Path(d, "ride.csv")
        par.write_text(chr(0xFEFF) + nl.join(["emp_id,team", "001,A", "002,A", "002,B", "003,C"]) + nl, encoding="utf-8")  # BOM·중복(줄 4)
        kid.write_text(nl.join(["ride,emp_id", "1,001", "2,004", "3,", "4,002", "5,1"]) + nl, encoding="utf-8")
        r = check(kid, "emp_id", par, "emp_id")
        assert r["orphan"] == [3, 6], r          # 004 없음, '1'은 '001'과 다른 키(앞자리 0 보존)
        assert r["dup"] == [4] and r["empty_child"] == 1 and r["unref"] == 1 and not r["bad_child"], r
        assert report("ride:emp_id=emp:emp_id", r) == 1
        kid.write_text(nl.join(["ride,emp_id", "1,001", "2", "3,002,extra"]) + nl, encoding="utf-8")  # 칸 모자람·남음
        r = check(kid, "emp_id", par, "emp_id")
        assert r["bad_child"] == [3, 4] and r["orphan"] == [] and report("short/extra", r) == 2, r
        kid.write_text(nl.join(["emp_id,emp_id", "999,001"]) + nl, encoding="utf-8")  # 앞 열 999가 덮이는 머리글
        try:
            check(kid, "emp_id", par, "emp_id")
            raise AssertionError("머리글 중복을 통과시켰다")
        except SystemExit as e:
            assert e.code == 2
        print("demo ok")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--fk", action="append", default=[], help="자식.csv:열=부모.csv:열 (여러 번)")
    ap.add_argument("--demo", action="store_true")
    a = ap.parse_args()
    if a.demo:
        demo()
    elif not a.fk:
        ap.error("--fk 또는 --demo")
    else:
        sys.exit(max(report(s, check(*parse(s))) for s in a.fk))
