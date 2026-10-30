"""작업 트리(추적·미추적 파일, .gitignore로 뺀 파일은 제외)와 git 이력 전체에서 비밀값·개인정보 흔적을 찾는다. 찾으면 종료 코드 1.
제공 원본 폴더는 --exclude로 뺀다(원본을 그대로 둔 것은 문제 삼지 않고, 내가 만든 코드·테스트·문서·커밋에 옮긴 것을 찾는다).
사용(저장소 루트에서): python check_secrets.py --exclude uploads --exclude data/raw [--pattern 'H2\\d{6}'] [--literal 비밀값파일.txt]
  --pattern: 과제 데이터에서 본 사번 형식 등을 정규식으로 추가
  --literal: 찾을 실제 값 목록 파일(한 줄 하나, 이 파일 자체는 commit하지 않는다)
PASS는 "이 패턴으로 못 찾았다"는 뜻이지 없다는 보장이 아니다. git 명령이 실패하면 NOT_RUN(종료 코드 2).
출력은 위치와 종류만 보이고 값은 가린다. 테스트용 가짜 값(010-0000-0000, example, dummy, change-me)은 건너뛴다.
"""
import argparse
import re
import subprocess
import sys

PATTERNS = {
    "비밀 값(따옴표)": r"(?i)\b(api[_-]?key|secret|token|passw(?:or)?d|pwd)\w*\s*[=:]\s*['\"][^'\"\s]{6,}['\"]",
    "비밀 값(키=값)": r"(?i)\b(api[_-]?key|secret|passw(?:or)?d|pwd)=[^\s'\",;]{6,}",
    "키 모양 값": r"\b(sk-[A-Za-z0-9_-]{16,}|ghp_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|hf_[A-Za-z0-9]{20,}|AKIA[0-9A-Z]{16}|xox[baprs]-[A-Za-z0-9-]{10,})",
    "접속 문자열": r"[a-z][a-z0-9+.-]*://[^\s:/@]+:[^\s@/]+@",
    "전화번호": r"\b01[016789]-?\d{3,4}-?\d{4}\b",
    "이메일": r"\b[\w.+-]+@[\w-]+\.[\w.]{2,}\b",
}
ALLOW = re.compile(r"0{3,4}-?0{4}|example|dummy|change-me|fake|\$\{", re.I)


def scan(text, rules, where, hits):
    for name, rx in rules.items():
        for m in re.finditer(rx, text):
            if ALLOW.search(m.group(0)):
                continue
            line = text.count("\n", 0, m.start()) + 1
            hits.append(f"{where}:{line} {name} {m.group(0)[:4]}***")


def git(*args):
    r = subprocess.run(["git", *args], capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0:
        print(f"SECRETS NOT_RUN: git {args[0]} 실패: {r.stderr.strip()[:200]}")
        sys.exit(2)
    return r.stdout


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--exclude", action="append", default=[])
    ap.add_argument("--pattern", action="append", default=[])
    ap.add_argument("--literal")
    a = ap.parse_args()
    rules = dict(PATTERNS)
    rules |= {f"추가 패턴{i + 1}": p for i, p in enumerate(a.pattern)}
    if a.literal:
        vals = [v.strip() for v in open(a.literal, encoding="utf-8") if v.strip()]
        rules |= {f"지정 값{i + 1}": re.escape(v) for i, v in enumerate(vals)}
    spec = ["--", "."] + [f":(exclude){e}" for e in a.exclude] + ([f":(exclude){a.literal}"] if a.literal else [])
    hits = []
    for f in git("ls-files", "--cached", "--others", "--exclude-standard", *spec).splitlines():  # 아직 commit 안 한 파일도
        try:
            scan(open(f, encoding="utf-8", errors="replace").read(), rules, f, hits)
        except (IsADirectoryError, FileNotFoundError):
            pass
    scan(git("log", "--all", "-p", "--format=commit %h %s", *spec), rules, "git이력", hits)  # 지운 파일·커밋 메시지 포함
    print("SECRETS PASS" if not hits else "SECRETS FAIL\n- " + "\n- ".join(sorted(set(hits))[:50]))
    sys.exit(1 if hits else 0)
