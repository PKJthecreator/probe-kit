"""작업 트리(추적·미추적 파일, .gitignore로 뺀 파일은 제외)와 git 이력 전체에서 비밀값·개인정보 흔적을 찾는다. 찾으면 종료 코드 1.
제공 원본 폴더는 --exclude로 뺀다(원본을 그대로 둔 것은 문제 삼지 않고, 내가 만든 코드·테스트·문서·커밋에 옮긴 것을 찾는다).
사용(저장소 루트에서): python check_secrets.py --exclude uploads --exclude data/raw [--pattern 'H2\\d{6}'] [--literal 비밀값파일.txt]
  --pattern: 과제 데이터에서 본 사번 형식 등을 정규식으로 추가
  --literal: 찾을 실제 값 목록 파일(한 줄 하나, 이 파일 자체는 commit하지 않는다)
PASS는 "이 패턴으로 못 찾았다"는 뜻이지 없다는 보장이 아니다. git 명령이 실패하면 NOT_RUN(종료 코드 2).
출력은 위치와 종류만 보이고 값은 가린다. 테스트용 가짜 값(010-0000-0000, example, dummy, change-me)은 건너뛴다.
"""
import argparse
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

PATTERNS = {
    # 앞 경계는 \b가 아니라 '영문·숫자가 아님'으로: DB_PASSWORD·APP_SECRET처럼 밑줄 뒤에 오는 이름도 잡는다
    "비밀 값(따옴표)": r"(?i)(?<![a-z0-9])(api[_-]?key|secret|token|passw(?:or)?d|pwd)\w*\s*[=:]\s*['\"][^'\"\s]{6,}['\"]",
    "비밀 값(키=값)": r"(?i)(?<![a-z0-9])(api[_-]?key|secret|token|passw(?:or)?d|pwd)\w*=[^\s'\",;]{6,}",
    "키 모양 값": r"\b(sk-[A-Za-z0-9_-]{16,}|ghp_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|hf_[A-Za-z0-9]{20,}|AKIA[0-9A-Z]{16}|xox[baprs]-[A-Za-z0-9-]{10,})",
    "접속 문자열": r"[a-z][a-z0-9+.-]*://[^\s:/@]+:[^\s@/]+@",
    "전화번호": r"\b01[016789]-?\d{3,4}-?\d{4}\b",
    "이메일": r"\b[\w.+-]+@[\w-]+\.[\w.]{2,}\b",
}
ALLOW = re.compile(r"0{3,4}-?0{4}|example|dummy|change-me|fake|\$\{|\{\w+\}", re.I)  # {token}: f-string 자리표시


def scan(text, rules, where, hits, allow=ALLOW):
    """allow=None: 사용자가 준 --pattern·--literal 값은 'fake'·'example'이 들어 있어도 건너뛰지 않는다."""
    for name, rx in rules.items():
        for m in re.finditer(rx, text):
            if allow and allow.search(m.group(0)):
                continue
            line = text.count("\n", 0, m.start()) + 1
            hits.append(f"{where}:{line} {name} {m.group(0)[:4]}***")


def git(*args):
    r = subprocess.run(["git", *args], capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0:
        print(f"SECRETS NOT_RUN: git {args[0]} 실패: {r.stderr.strip()[:200]}")
        sys.exit(2)
    return r.stdout


def files(spec):
    """추적·미추적 파일. -z: 한글 파일명이 "\\354…"처럼 따옴표로 바뀌어 열리지 않는 것을 막는다."""
    return [f for f in git("ls-files", "-z", "--cached", "--others", "--exclude-standard", *spec).split("\0") if f]


def run(exclude=(), pattern=(), literal=None):
    user = {f"추가 패턴{i + 1}": p for i, p in enumerate(pattern)}
    spec = ["--", ".", ":(exclude)*.pyc"] + [f":(exclude){e}" for e in exclude]  # .pyc는 원본 .py를 보면 된다(바이트 열이 오탐)
    if literal:
        vals = [v.strip() for v in open(literal, encoding="utf-8") if v.strip()]
        user |= {f"지정 값{i + 1}": re.escape(v) for i, v in enumerate(vals)}
        if Path(literal).resolve().is_relative_to(Path.cwd().resolve()):  # 저장소 밖 파일이면 뺄 것도 없다(git이 거부)
            spec.append(f":(exclude){literal}")
    hits = []
    for f in files(spec):  # 아직 commit 안 한 파일도
        try:
            text = open(f, encoding="utf-8", errors="replace").read()
        except (IsADirectoryError, FileNotFoundError):
            continue
        scan(text, PATTERNS, f, hits)
        scan(text, user, f, hits, allow=None)
    log = git("log", "--all", "-p", "--format=commit %h %s", *spec)  # 지운 파일·커밋 메시지 포함
    scan(log, PATTERNS, "git이력", hits)
    scan(log, user, "git이력", hits, allow=None)
    return hits


def demo():
    kv = lambda k, v: k + "=" + v  # 이 파일 자체가 검사에 걸리지 않게 실행 때 조립한다
    lines = [kv("DB_PASSWORD", "hunter2sekret"), kv("APP_SECRET", "abcdefgh123"), kv("SECRET_KEY", "zzzzzzzzzz"),
             kv("url?token", "abcdef123"), kv("PASSWORD", "change-me-now"), kv("#token", "{token}")]
    hits = []
    scan(chr(10).join(lines), PATTERNS, "m", hits)
    assert len(hits) == 4, hits  # 밑줄 뒤 이름 3개 + token. change-me·{token}은 가짜 값·자리표시로 건너뜀
    hits = []
    scan("LIVE_fake_R7n4Q9k2", {"지정 값1": re.escape("LIVE_fake_R7n4Q9k2")}, "m", hits, allow=None)
    assert len(hits) == 1, hits  # 지정 값은 'fake'가 들어 있어도 잡는다
    with tempfile.TemporaryDirectory() as d:
        os.chdir(d)
        subprocess.run(["git", "init", "-q"], check=True)
        Path("직원.txt").write_text(kv("api_key", "qqqqqqqqqq"), encoding="utf-8")
        assert any("직원.txt" in h for h in run()), "한글 파일명을 열지 못했다"
        os.chdir(tempfile.gettempdir())
    print("demo ok")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--exclude", action="append", default=[])
    ap.add_argument("--pattern", action="append", default=[])
    ap.add_argument("--literal")
    ap.add_argument("--demo", action="store_true")
    a = ap.parse_args()
    if a.demo:
        sys.exit(demo())
    hits = run(a.exclude, a.pattern, a.literal)
    print("SECRETS PASS" if not hits else "SECRETS FAIL\n- " + "\n- ".join(sorted(set(hits))[:50]))
    sys.exit(1 if hits else 0)
