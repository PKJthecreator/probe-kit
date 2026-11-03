"""계정 만들기(web-starter 폴더에서). 고정 비밀번호를 코드에 두지 않는다.
  python seed.py --demo                 운영자 admin·구성원 member01을 무작위 비밀번호로 만들고 한 번만 출력
  ADMIN_USERNAME=… ADMIN_PASSWORD=… python seed.py   운영자 한 명을 지정 값으로(환경변수가 없으면 만들지 않음)
  python seed.py --csv 명단.csv         열 username,name[,email][,role] → 임시 비밀번호로 일괄 등록, 첫 로그인 때 변경 강제
                                        임시 비밀번호는 outputs/logs/initial_passwords.csv(커밋 금지 폴더)에만 쓴다
"""
import argparse
import csv
import os
import secrets
import sqlite3
from pathlib import Path

from app.main import connect, create_user, init_db
from app import policy, security


def temp_pw():
    return secrets.token_urlsafe(9) + "Aa1!"  # 정책(대·소·숫자·특수)을 항상 만족


def add(conn, username, name, pw, role="member", email=None, must_change=False):
    try:
        create_user(conn, username, name, pw, role=role, email=email, must_change=must_change)
        return True
    except sqlite3.IntegrityError:
        print(f"건너뜀(이미 있음): {username}")
        return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--demo", action="store_true")
    ap.add_argument("--csv")
    ap.add_argument("--out", default="outputs/logs/initial_passwords.csv")
    a = ap.parse_args()
    conn = connect()
    init_db(conn)
    if os.getenv("ADMIN_USERNAME") and os.getenv("ADMIN_PASSWORD"):
        if why := security.check_password(os.environ["ADMIN_PASSWORD"], os.environ["ADMIN_USERNAME"]):
            raise SystemExit(f"ADMIN_PASSWORD가 정책에 맞지 않음: {why}")
        add(conn, os.environ["ADMIN_USERNAME"], "운영자", os.environ["ADMIN_PASSWORD"], role="admin")
    if a.demo:
        for username, name, role in (("admin", "운영자", "admin"), ("member01", "구성원1", "member")):
            pw = temp_pw()
            if add(conn, username, name, pw, role=role, email=f"{username}@example.com"):
                print(f"{policy.ROLES[role]} {username} / {pw}   ← 지금만 보인다")
    if a.csv:
        Path(a.out).parent.mkdir(parents=True, exist_ok=True)
        made = 0
        with open(a.csv, encoding="utf-8-sig", newline="") as f, open(a.out, "w", encoding="utf-8", newline="") as out:
            w = csv.writer(out)
            w.writerow(["username", "temp_password"])
            for row in csv.DictReader(f):
                username = row["username"].strip().lower()
                role = row.get("role", "member").strip() or "member"
                if security.check_username(username) or role not in policy.ROLES:
                    print(f"건너뜀(형식): {username} {role}")
                    continue
                pw = temp_pw()
                if add(conn, username, row["name"].strip(), pw, role=role, email=(row.get("email") or "").strip() or None, must_change=True):
                    w.writerow([username, pw])
                    made += 1
        print(f"{made}명 등록, 임시 비밀번호 → {a.out} (커밋·공유 금지)")
    conn.close()


if __name__ == "__main__":
    main()
