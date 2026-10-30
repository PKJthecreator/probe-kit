"""RAG 검색 뼈대(설치 불필요): 문서 폴더 → 문단 청크 → BM25(한글은 글자 2-gram) → 출처 붙은 상위 k개.
점수가 기준보다 낮으면 "근거 없음"을 돌려 LLM이 지어내지 않게 한다. 임베딩·벡터DB는 설치·키가 있을 때만 교체.
사용: python rag.py docs/ "질문"        자체 점검: python rag.py --demo
평가: hit_at_k·mrr(질문→정답 출처)로 검색부터 잰다(생성 품질보다 먼저).
하이브리드: 임베딩 검색(Chroma·FAISS 등)을 쓸 수 있으면 두 순위를 rrf()로 합친다(점수 단위가 달라도 순위만 쓴다).
"""
import math
import re
import sys
from collections import Counter
from pathlib import Path


def tokens(text):
    out = []
    for w in re.findall(r"[0-9A-Za-z]+|[가-힣]+", text.lower()):
        out += [w[i:i + 2] for i in range(len(w) - 1)] if re.match(r"[가-힣]", w) and len(w) > 1 else [w]
    return out


def chunk(folder, exts=(".txt", ".md")):
    """빈 줄로 나눈 문단 단위. 출처 = 파일:시작줄."""
    out = []
    for p in sorted(Path(folder).rglob("*")):
        if p.suffix not in exts:
            continue
        lines, start, buf = p.read_text(encoding="utf-8", errors="replace").splitlines(), 1, []
        for i, line in enumerate(lines + [""], 1):
            if line.strip():
                buf.append(line)
                continue
            if buf:
                out.append({"source": f"{p.name}:{start}", "text": "\n".join(buf)})
            buf, start = [], i + 1
    return out


class BM25:
    def __init__(self, docs, k1=1.5, b=0.75):
        self.docs, self.k1, self.b = docs, k1, b
        self.tf = [Counter(tokens(d["text"])) for d in docs]
        self.len = [sum(t.values()) for t in self.tf]
        self.avg = sum(self.len) / max(len(docs), 1)
        df = Counter(w for t in self.tf for w in t)
        self.idf = {w: math.log(1 + (len(docs) - n + 0.5) / (n + 0.5)) for w, n in df.items()}

    def search(self, query, k=3, min_score=1.0):
        q = tokens(query)
        scored = []
        for i, tf in enumerate(self.tf):
            s = sum(self.idf.get(w, 0) * tf[w] * (self.k1 + 1) / (tf[w] + self.k1 * (1 - self.b + self.b * self.len[i] / self.avg)) for w in q)
            scored.append((s, i))
        hits = [dict(self.docs[i], score=round(s, 3)) for s, i in sorted(scored, reverse=True)[:k] if s >= min_score]
        return hits  # 빈 목록 = 근거 없음 → "문서에서 찾지 못했다"고 답한다


def hit_at_k(index, cases, k=3):
    """cases = [(질문, 정답 출처 접두어), ...]. 검색 품질부터 숫자로."""
    return sum(any(h["source"].startswith(src) for h in index.search(q, k)) for q, src in cases) / len(cases)


def mrr(index, cases, k=10):
    """정답이 몇 번째에 나왔나(1/순위의 평균). hit@k가 같아도 정답을 더 위에 올리는 쪽이 높다."""
    total = 0.0
    for q, src in cases:
        ranks = [i for i, h in enumerate(index.search(q, k, min_score=0), 1) if h["source"].startswith(src)]
        total += 1 / ranks[0] if ranks else 0
    return total / len(cases)


def rrf(*rankings, k=60, top=5):
    """Reciprocal Rank Fusion: 여러 검색기의 순위 목록(출처 리스트)을 1/(k+순위) 합으로 합친다."""
    score = {}
    for ranking in rankings:
        for i, src in enumerate(ranking, 1):
            score[src] = score.get(src, 0) + 1 / (k + i)
    return sorted(score, key=score.get, reverse=True)[:top]


def demo():
    import tempfile
    d = Path(tempfile.mkdtemp())
    (d / "manual.md").write_text("# 점검\n설비 점검 전에는 전원을 차단하고 잠금 표지를 붙인다.\n\n"
                                 "# 세정\nCMP 패드 세정은 매 교대마다 한다.\n", encoding="utf-8")
    (d / "faq.txt").write_text("불량률 경보 기준은 2%이다.\n\n경보가 나면 품질팀에 알린다.\n", encoding="utf-8")
    idx = BM25(chunk(d))
    top = idx.search("전원 차단은 언제?")
    assert top and top[0]["source"] == "manual.md:1", top
    assert idx.search("주식 시세 전망") == [], "관련 없는 질문은 근거 없음"
    assert hit_at_k(idx, [("패드 세정 주기", "manual.md"), ("경보 기준", "faq.txt")]) == 1.0
    assert mrr(idx, [("전원 차단", "manual.md:1")]) == 1.0
    assert rrf(["a", "b", "c"], ["c", "a", "d"])[:2] == ["a", "c"], "두 검색기 모두 위에 둔 것이 위로"
    print("rag demo PASS")


if __name__ == "__main__":
    if sys.argv[1:] == ["--demo"]:
        demo()
    else:
        for h in BM25(chunk(sys.argv[1])).search(" ".join(sys.argv[2:])):
            print(f"[{h['source']}] ({h['score']}) {h['text'][:120]}")
