"""LLM 에이전트 뼈대: 숫자·판정은 도구(순수 함수)가, LLM은 도구 선택과 문장만.
흐름: 질의 라우팅(단순/도구 필요) → 도구 호출(최대 N회, 도구별 실패 격리) → LLM 초안
      → 검사(LLM이 숫자를 직접 썼나, 없는 자리표시자를 썼나) → 실패 시 재작성 1회 → 그래도 실패면 사실 카드만.
숫자·상태는 LLM이 쓰지 않는다: 초안에는 {0.rate_pct}처럼 "도구 결과 번호.필드" 자리표시자만 쓰고 값은 코드가 채운다.
응답에는 코드가 만든 사실 카드(fact_card)를 항상 함께 낸다. 화면은 이 카드를 기준 값으로 보여 준다.
규칙: 숫자·상태 단어(켜짐/꺼짐)를 직접 쓰면 거부, `%` 앞에는 이름이 _pct로 끝나는 필드만.
한계: "문제 없습니다"처럼 숫자·상태 단어 없는 잘못된 주장은 못 잡는다 → 사실 카드로 대조한다.
LLM: OPENAI_API_KEY와 OPENAI_MODEL(과제가 허용한 모델명)이 둘 다 있으면 OpenAI Responses API, 아니면 결정론 FakeLLM.
     과제가 키를 주지 않으면 FakeLLM으로 흐름·테스트를 끝까지 돌리고, 실제 연결은 NOT_RUN으로 적는다.
실행: python agent.py "EQ-002 최근 불량률 알려줘"     자체 점검: python agent.py --demo
"""
import json
import os
import re
import sys
import time
from dataclasses import dataclass, field
from functools import partial

# ---------- 도구: 프레임워크와 무관한 순수 함수. 데이터는 Deps로 주입(테스트에서 바꿔 끼운다) ----------


@dataclass
class Deps:
    defects: dict = field(default_factory=lambda: {"EQ-001": (3, 1000), "EQ-002": (27, 900)})  # (불량, 생산)
    threshold: float = 0.02  # 불량률 경보 기준 — 담당자가 정할 값


def get_defect_rate(deps: Deps, equipment_id: str) -> dict:
    """설비의 불량률과 경보 여부. 없는 설비면 ValueError."""
    if equipment_id not in deps.defects:
        raise ValueError(f"없는 설비: {equipment_id}")
    bad, total = deps.defects[equipment_id]
    rate = bad / total
    return {"equipment_id": equipment_id, "defects": bad, "produced": total, "rate_pct": round(rate * 100, 2),
            "alert": rate >= deps.threshold, "threshold_pct": deps.threshold * 100}


def list_equipment(deps: Deps) -> dict:
    return {"equipment": sorted(deps.defects)}


TOOLS = {  # 이름 → (함수, 설명, 인자 스키마). OpenAI 도구 정의로 그대로 쓴다.
    "get_defect_rate": (get_defect_rate, "설비 ID의 불량률(%)과 경보 여부를 조회한다",
                        {"type": "object", "properties": {"equipment_id": {"type": "string"}}, "required": ["equipment_id"]}),
    "list_equipment": (list_equipment, "조회 가능한 설비 ID 목록", {"type": "object", "properties": {}}),
}

# ---------- LLM ----------


class FakeLLM:
    """키 없이 흐름을 검증하는 결정론 모델. 설비 ID가 보이면 그 도구를, 아니면 목록 도구를 부른다."""

    def plan(self, question):
        ids = re.findall(r"EQ-\d{3}", question.upper())
        if not ids and not re.search(r"설비|불량|목록", question):
            return []  # 단순 질의: 도구 불필요
        return [("get_defect_rate", {"equipment_id": i}) for i in ids] or [("list_equipment", {})]

    def write(self, question, facts, feedback=None):
        parts = []
        for i, f in enumerate(facts):
            r = f["result"]
            if "rate_pct" in r:
                parts.append(f"{{{i}.equipment_id}} 불량률은 {{{i}.rate_pct}}%이고 경보는 {{{i}.alert}}입니다.")
            elif "equipment" in r:
                parts.append(f"조회 가능한 설비: {{{i}.equipment}}")
            else:
                parts.append(f"{f['tool']} 실패: {{{i}.error}}")
        return " ".join(parts) or "도구 없이 답할 수 있는 질문입니다."


class OpenAILLM:
    """Responses API 함수 호출. ponytail: 도구 선택 1회 + 작성 1회만. 다단계 계획이 필요하면 루프로 늘린다."""

    def __init__(self, model=None):
        from openai import OpenAI
        self.client, self.model = OpenAI(), model or os.environ["OPENAI_MODEL"]

    def plan(self, question):
        tools = [{"type": "function", "name": n, "description": d, "parameters": p} for n, (_, d, p) in TOOLS.items()]
        r = self.client.responses.create(model=self.model, input=question, tools=tools)
        return [(o.name, json.loads(o.arguments or "{}")) for o in r.output if o.type == "function_call"]

    def write(self, question, facts, feedback=None):
        prompt = (f"질문: {question}\n도구 결과(번호: JSON): " + json.dumps({i: f["result"] for i, f in enumerate(facts)}, ensure_ascii=False)
                  + "\n한국어 2문장으로 답하라. 숫자·참거짓 값은 직접 쓰지 말고 반드시 {번호.필드} 자리표시자로 써라(예: {0.rate_pct}%)."
                  " 원인은 '후보'로만 말하라." + (f"\n이전 답의 문제: {feedback}" if feedback else ""))
        return self.client.responses.create(model=self.model, input=prompt).output_text


def make_llm():
    return OpenAILLM() if os.getenv("OPENAI_API_KEY") and os.getenv("OPENAI_MODEL") else FakeLLM()

# ---------- 오케스트레이션 ----------


TRANSIENT = [TimeoutError, ConnectionError]   # 일시적 오류만 재시도. 입력 오류(ValueError 등)는 바로 실패
for _mod, _names in (("httpx", ("TransportError",)), ("requests", ("ConnectionError", "Timeout"))):
    try:  # 설치돼 있으면 그 라이브러리의 시간 초과·연결 오류도(내장 TimeoutError가 아니다)
        TRANSIENT += [getattr(__import__(_mod), n) for n in _names]
    except ImportError:
        pass
TRANSIENT = tuple(TRANSIENT)


def retry(fn, attempts=3, base_delay=0.3):
    """일시적 오류를 지수 대기(0.3→0.9초)로 재시도. 마지막 실패는 그대로 올린다. (결과, 재시도 횟수)
    시간 제한은 도구 안의 호출에 건다(예: httpx.get(url, timeout=5)). 넘으면 TimeoutError로 올라와 재시도된다."""
    for i in range(attempts):
        try:
            return fn(), i
        except TRANSIENT:
            if i == attempts - 1:
                raise
            time.sleep(base_delay * 3 ** i)


def run_tools(deps, calls, max_calls=5):
    """도구별 실패 격리: 한 도구 실패가 전체를 멈추지 않는다. 알 수 없는 도구는 거부. 외부 호출 도구는 retry."""
    facts = []
    for name, args in calls[:max_calls]:
        fn = TOOLS.get(name, (None,))[0]
        try:
            if fn is None:
                raise ValueError(f"허용되지 않은 도구: {name}")
            result, retried = retry(partial(fn, deps, **args))
            facts.append({"tool": name, "args": args, "result": result} | ({"retried": retried} if retried else {}))
        except (ValueError, TypeError, *TRANSIENT) as e:
            facts.append({"tool": name, "args": args, "result": {"error": f"{type(e).__name__}: {e}"}})
    return facts


SLOT = re.compile(r"\{(\d+)\.(\w+)\}")
NUM = re.compile(r"(?<![\w.-])\d+(?:\.\d+)?(?![\w])")  # EQ-002 같은 ID 속 숫자는 빼고 독립된 수만


def _show(v):
    if isinstance(v, bool):
        return "켜짐" if v else "꺼짐"
    return ", ".join(map(str, v)) if isinstance(v, list) else str(v)


def render(text, facts):
    """자리표시자에 도구 결과 값을 코드가 넣는다. 없는 번호·필드면 KeyError."""
    def sub(m):
        i, key = int(m[1]), m[2]
        if i >= len(facts) or key not in facts[i]["result"]:
            raise KeyError(m[0])
        return _show(facts[i]["result"][key])
    return SLOT.sub(sub, text)


STATE = re.compile(r"켜짐|꺼짐")  # _show()가 참·거짓을 쓰는 단어. LLM이 직접 쓰면 거부


def problems(draft, facts, question=""):
    """LLM이 직접 쓴 숫자(질문 속 숫자·목록 번호 제외)·상태 단어, 없는 자리표시자, % 앞의 _pct 아닌 필드를 찾는다."""
    out = [f"% 앞에 비율 아닌 필드 {m[0]}" for m in re.finditer(r"\{\d+\.(\w+)\}\s*%", draft) if not m[1].endswith("_pct")]
    raw = SLOT.sub("", draft)
    out += [f"직접 쓴 상태 {w}" for w in STATE.findall(raw)]
    raw = re.sub(r"(?<=\d),(?=\d{3})", "", raw)          # 1,000 → 1000
    raw = re.sub(r"(?m)^\s*\d+[.)]\s", "", raw)           # 목록 번호 "1. "
    out += [f"직접 쓴 숫자 {n}" for n in NUM.findall(raw) if n not in NUM.findall(question)]
    try:
        render(draft, facts)
    except KeyError as e:
        out.append(f"없는 자리표시자 {e.args[0]}")
    return out


def fact_card(facts):
    """코드가 만든 기준 값. 화면은 LLM 문장보다 이것을 기준으로 보여 준다."""
    return [f"{f['tool']}({', '.join(f'{k}={v}' for k, v in f['args'].items())}): "
            + ", ".join(f"{k}={_show(v)}" for k, v in f["result"].items()) for f in facts]


def answer(question, deps=None, llm=None):
    deps, llm = deps or Deps(), llm or make_llm()
    facts = run_tools(deps, llm.plan(question))
    draft = llm.write(question, facts)
    bad = problems(draft, facts, question)
    if bad:  # 재작성 1회 → 그래도 문제면 사실 카드만
        draft = llm.write(question, facts, feedback="; ".join(bad))
        if problems(draft, facts, question):
            draft = "확인된 사실만 드립니다: " + " / ".join(fact_card(facts))
    return {"answer": render(draft, facts), "fact_card": fact_card(facts), "facts": facts, "rejected": bad}


def demo():
    r = answer("EQ-002 최근 불량률 알려줘", llm=FakeLLM())
    assert r["answer"] == "EQ-002 불량률은 3.0%이고 경보는 켜짐입니다." and not r["rejected"], r
    r = answer("EQ-999 불량률", llm=FakeLLM())
    assert "실패" in r["answer"] and "error" in r["facts"][0]["result"], "없는 설비는 실패를 알리고 죽지 않는다"

    class Liar(FakeLLM):  # 숫자를 직접 쓰는 모델 → 재작성 → 그래도면 사실 카드만
        def write(self, q, facts, feedback=None):
            return "EQ-002 불량률은 27%이고 경보는 꺼짐입니다."
    r = answer("EQ-002 불량률", llm=Liar())
    assert r["rejected"] == ["직접 쓴 상태 꺼짐", "직접 쓴 숫자 27"] and r["answer"].startswith("확인된 사실만") and "alert=켜짐" in r["answer"], r

    class WrongField(FakeLLM):
        def write(self, q, facts, feedback=None):
            return "불량률은 {0.defects}%입니다."
    assert answer("EQ-002 불량률", llm=WrongField())["rejected"] == ["% 앞에 비율 아닌 필드 {0.defects}%"]

    class BadSlot(FakeLLM):
        def write(self, q, facts, feedback=None):
            return "불량률 {0.rate}"
    assert answer("EQ-001 불량률", llm=BadSlot())["rejected"] == ["없는 자리표시자 {0.rate}"]
    assert problems("1. {0.rate_pct}% (총 1,000개 기준)", [{"tool": "t", "args": {}, "result": {"rate_pct": 3}}], "총 1000개") == []
    assert "허용되지 않은" in run_tools(Deps(), [("rm_rf", {})])[0]["result"]["error"]
    assert answer("안녕", llm=FakeLLM())["facts"] == []
    flaky = iter([TimeoutError("느림"), {"ok": 1}])

    def once_slow():
        x = next(flaky)
        if isinstance(x, Exception):
            raise x
        return x
    assert retry(once_slow, base_delay=0) == ({"ok": 1}, 1), "일시적 오류는 재시도"
    try:
        retry(lambda: (_ for _ in ()).throw(ValueError("입력")), base_delay=0)
        raise AssertionError("입력 오류는 재시도하지 않고 바로 실패")
    except ValueError:
        pass
    print("agent demo PASS")


if __name__ == "__main__":
    if sys.argv[1:] == ["--demo"]:
        demo()
    else:
        print(json.dumps(answer(" ".join(sys.argv[1:]) or "설비 목록"), ensure_ascii=False, indent=2))
