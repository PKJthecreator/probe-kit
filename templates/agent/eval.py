"""에이전트 평가 세트: 고정 질의로 같은 검사를 돌려 고치기 전·후를 숫자로 비교한다(검색은 rag.py의 hit_at_k·mrr).
CASES를 과제에 맞게 바꾼다. 범주를 고루: 정상 / 없는 대상 / 도구 불필요 / 근거 없음 / 여러 대상 / 경계.
사용: python eval.py [--out outputs/agent_eval.json]   (LLM은 agent.make_llm(): 키·모델이 없으면 FakeLLM)
"""
import argparse
import json
import time
from pathlib import Path

from agent import Deps, answer, make_llm

CASES = [  # (이름, 질의, 불러야 할 도구, 답에 있어야 할 말, 답에 없어야 할 말)
    ("정상", "EQ-002 불량률 알려줘", ["get_defect_rate"], ["3.0", "켜짐"], []),
    ("없는 대상", "EQ-999 불량률", ["get_defect_rate"], ["실패"], ["%"]),
    ("도구 불필요", "안녕하세요", [], [], ["불량률"]),
    ("여러 대상", "EQ-001 EQ-002 비교", ["get_defect_rate"], ["EQ-001", "EQ-002"], []),
]


def run(cases=CASES, llm=None, deps=None):
    llm, rows = llm or make_llm(), []
    for name, q, tools, must, must_not in cases:
        t = time.perf_counter()
        r = answer(q, deps or Deps(), llm)
        used = {f["tool"] for f in r["facts"]}
        checks = {"도구": set(tools) <= used and (bool(tools) or not used),
                  "포함": all(m in r["answer"] for m in must),
                  "금지": not any(m in r["answer"] for m in must_not),
                  "검증 통과": not r["rejected"]}
        rows.append({"case": name, "pass": all(checks.values()), "checks": checks,
                     "ms": round((time.perf_counter() - t) * 1000, 1), "answer": r["answer"]})
    return {"llm": type(llm).__name__, "passed": sum(x["pass"] for x in rows), "total": len(rows), "cases": rows}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="outputs/agent_eval.json")
    a = ap.parse_args()
    rep = run()
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(rep, ensure_ascii=False, indent=2), encoding="utf-8")
    for c in rep["cases"]:
        print(("PASS" if c["pass"] else "FAIL"), c["case"], {k: v for k, v in c["checks"].items() if not v})
    print(f"{rep['llm']}: {rep['passed']}/{rep['total']} -> {a.out}")
    assert rep["llm"] != "FakeLLM" or rep["passed"] == rep["total"], "FakeLLM 기준선은 전부 통과해야 한다"
