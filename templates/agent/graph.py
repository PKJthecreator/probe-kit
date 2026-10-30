"""agent.py와 같은 흐름을 LangGraph StateGraph로(과제가 LangGraph를 요구하거나 분기·재시도·세션이 늘어날 때).
LangGraph는 판단하는 AI가 아니라 흐름 엔진이다: 판정·계산은 도구(코드), LLM은 도구 선택·문장, 검증은 코드.
노드: plan → lookup → compose → check ─(문제 있고 재작성 1회 전)→ compose
                                  └(통과 또는 재작성 뒤에도 문제)→ finalize
노드는 의존성(Deps·LLM)을 functools.partial로 주입받는 순수 함수라 단독 테스트가 된다.
대화 이력이 필요하면 checkpointer(MemorySaver, 재시작 후에도 남겨야 하면 SQLite 체크포인터)와 thread_id.
필요: pip install langgraph (없으면 agent.py만 쓴다)
자체 점검: python graph.py
"""
from functools import partial
from typing import TypedDict

try:
    from langgraph.checkpoint.memory import MemorySaver
    from langgraph.graph import END, StateGraph
except ImportError as e:  # 설치 안 된 환경: 새 설치는 승인 후. 같은 흐름은 agent.py로 돈다
    raise SystemExit("langgraph가 없다: 승인 후 pip install langgraph, 아니면 agent.py를 쓴다") from e

from agent import Deps, FakeLLM, fact_card, problems, render, run_tools


class State(TypedDict, total=False):
    question: str
    calls: list
    facts: list
    draft: str
    feedback: str
    attempts: int
    answer: str
    rejected: list
    fact_card: list


def plan(state, llm):
    """턴마다 이전 턴의 검증 상태를 지운다(같은 thread_id로 이어 물어도 섞이지 않게)."""
    return {"calls": llm.plan(state["question"]), "attempts": 0, "feedback": "", "rejected": [], "draft": "", "answer": ""}


def lookup(state, deps):
    return {"facts": run_tools(deps, state["calls"])}


def compose(state, llm):
    return {"draft": llm.write(state["question"], state["facts"], state.get("feedback")), "attempts": state.get("attempts", 0) + 1}


def check(state):
    bad = problems(state["draft"], state["facts"], state["question"])
    return {"feedback": "; ".join(bad), "rejected": state.get("rejected") or bad}


def after_check(state):
    return "compose" if state["feedback"] and state["attempts"] < 2 else "finalize"


def finalize(state):
    card = fact_card(state["facts"])   # agent.py와 같게: 코드가 만든 사실 카드를 항상 함께
    if state["feedback"]:   # 재작성 뒤에도 문제 → 사실 카드만
        return {"answer": "확인된 사실만 드립니다: " + " / ".join(card), "fact_card": card}
    return {"answer": render(state["draft"], state["facts"]), "fact_card": card}


def build(deps=None, llm=None, checkpointer=None):
    deps, llm = deps or Deps(), llm or FakeLLM()
    g = StateGraph(State)
    for name, fn in [("plan", partial(plan, llm=llm)), ("lookup", partial(lookup, deps=deps)),
                     ("compose", partial(compose, llm=llm)), ("check", check), ("finalize", finalize)]:
        g.add_node(name, fn)
    g.set_entry_point("plan")
    for a, b in [("plan", "lookup"), ("lookup", "compose"), ("compose", "check")]:
        g.add_edge(a, b)
    g.add_conditional_edges("check", after_check, {"compose": "compose", "finalize": "finalize"})
    g.add_edge("finalize", END)
    return g.compile(checkpointer=checkpointer)


if __name__ == "__main__":
    app = build(checkpointer=MemorySaver())
    cfg = {"configurable": {"thread_id": "demo-session"}}
    r = app.invoke({"question": "EQ-002 불량률 알려줘"}, cfg)
    assert r["answer"] == "EQ-002 불량률은 3.0%이고 경보는 켜짐입니다." and r["attempts"] == 1, r

    class Liar(FakeLLM):
        def write(self, q, facts, feedback=None):
            return "EQ-002 불량률은 27%입니다."
    r = build(llm=Liar()).invoke({"question": "EQ-002 불량률"})
    assert r["attempts"] == 2 and r["answer"].startswith("확인된 사실만"), "재작성 1회 뒤에도 문제면 사실 카드"
    assert app.get_state(cfg).values["question"] == "EQ-002 불량률 알려줘", "thread_id로 상태가 남는다"
    assert r["fact_card"], "사실 카드 포함"
    liar_app = build(llm=Liar(), checkpointer=MemorySaver())
    liar_app.invoke({"question": "EQ-002 불량률"}, cfg)
    ok = build(checkpointer=liar_app.checkpointer)
    r2 = ok.invoke({"question": "EQ-001 불량률"}, cfg)
    assert r2["rejected"] == [] and not r2["answer"].startswith("확인된 사실만"), "이전 턴의 반려가 다음 턴에 섞이지 않는다"
    print("graph PASS")
