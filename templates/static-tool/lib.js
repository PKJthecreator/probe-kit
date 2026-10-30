/* 정적 업무 도구의 판정·계산(순수 함수). 화면(tool.html)과 분리해 node --test로 검증한다.
   설치·인터넷 없이 브라우저에서 돈다: 외부 호출·브라우저 저장소를 쓰지 않는다.
   아래 RULES는 예시 값이다. 담당자 답으로 바꾸고, 경계값 포함 여부를 주석으로 남긴다. */
(function (root) {
  "use strict";

  const RULES = {
    version: "example-1",
    tzOffsetMin: 9 * 60,       // 표기 없는 시각은 KST로 본다(담당자 확인). "Z"·"+09:00"이 붙은 값은 그대로 해석
    groupGapMin: 10,           // 같은 대상·같은 항목이 직전 발생 후 이 분 안(같으면 포함)에 다시 나오면 한 건
    maxLines: 25,              // 메신저 한 화면
    secretMetaKeys: /pass|pwd|secret|token|key|conn/i,   // 파일 머리 메타에서 버릴 키
    limits: { THK: { lsl: 95, usl: 105 } },              // 규격선과 같으면 규격 안(경계 포함)
    digits: 1,                 // 판정은 표시 자릿수로 반올림한 값으로(부동소수점 경계 뒤집힘 방지)
  };

  /* CSV 한 덩어리 → {meta, header, records:[{line, values}], bad:[{line, reason}]}
     - BOM, CRLF/LF, 따옴표 안 쉼표·"" 처리
     - 헤더 **앞**의 '#' 줄만 메타(key=value). 비밀처럼 보이는 키는 버린다
     - 헤더 **뒤**의 '#' 줄은 주석으로 삼키지 않고 못 읽는 줄로 알린다
     - line은 메모장 기준 1부터 센 물리 줄 번호 */
  function readTable(text, expectedCols) {
    const lines = text.replace(/^﻿/, "").split(/\r?\n/);
    const meta = {}, records = [], bad = [];
    let header = null;
    for (let i = 0; i < lines.length; i++) {
      const raw = lines[i];
      if (!raw.trim()) continue;
      if (!header && raw.startsWith("#")) {
        for (const kv of raw.slice(1).split(/[;,]/)) {
          const m = kv.match(/^\s*([\w.-]+)\s*=\s*(.*)$/);
          if (m && !RULES.secretMetaKeys.test(m[1])) meta[m[1]] = m[2].trim();
        }
        continue;
      }
      const values = splitCsvLine(raw);
      if (!header) { header = values.map((h) => h.trim()); continue; }
      const n = expectedCols || header.length;
      if (values.length !== n) bad.push({ line: i + 1, reason: `열 ${values.length}개(기대 ${n})` });
      else records.push({ line: i + 1, values: Object.fromEntries(header.map((h, k) => [h, values[k]])) });
    }
    return { meta, header, records, bad };
  }

  function splitCsvLine(line) {
    const fields = [];
    let field = "", inQuotes = false, i = 0;
    while (i < line.length) {
      const ch = line[i++];
      if (inQuotes && ch === '"') {
        if (line[i] === '"') { field += '"'; i++; } else inQuotes = false;   // "" 는 따옴표 글자 하나
      } else if (!inQuotes && ch === '"') inQuotes = true;
      else if (!inQuotes && ch === ",") { fields.push(field); field = ""; }
      else field += ch;
    }
    fields.push(field);
    return fields;
  }

  /* 시각 문자열 → epoch ms. "2026-10-25 9:05"(엑셀 저장), "...T...Z"(UTC), 표기 없음(RULES.tzOffsetMin) */
  function parseTime(s) {
    const m = String(s).trim().match(/^(\d{4})-(\d{1,2})-(\d{1,2})[ T](\d{1,2}):(\d{2})(?::(\d{2})(?:\.\d+)?)?\s*(Z|[+-]\d{2}:?\d{2})?$/i);
    if (!m) return null;
    const [Y, Mo, D, h, mi, sec = 0] = m.slice(1, 7).map((x) => +(x || 0));
    if (h > 23 || mi > 59 || sec > 59) return null;
    const ms = Date.UTC(Y, Mo - 1, D, h, mi, sec);
    if (new Date(ms).getUTCMonth() !== Mo - 1 || new Date(ms).getUTCDate() !== D) return null;  // 2월 31일 같은 없는 날짜
    const z = m[7];
    const off = !z ? RULES.tzOffsetMin : /z/i.test(z) ? 0 : (z[0] === "-" ? -1 : 1) * (+z.slice(1, 3) * 60 + +z.slice(-2));
    return ms - off * 60000;
  }

  function fmt(ms, withDate = true) {
    const d = new Date(ms + RULES.tzOffsetMin * 60000);
    const p = (n) => String(n).padStart(2, "0");
    const hm = `${p(d.getUTCHours())}:${p(d.getUTCMinutes())}`;
    return withDate ? `${p(d.getUTCMonth() + 1)}/${p(d.getUTCDate())} ${hm}` : hm;
  }

  /* 반열린 구간 [start, end): 시작 정각은 포함, 끝 정각은 다음 구간 */
  const inWindow = (t, start, end) => t >= start && t < end;

  const round = (x, d = RULES.digits) => Math.round(x * 10 ** d) / 10 ** d;

  /* 숫자 칸: 빈 값·공백·숫자 아님은 null(Number("")는 0이라 그대로 쓰면 정상값으로 오판한다) */
  const toNumber = (s) => (String(s ?? "").trim() === "" ? null : Number.isFinite(Number(s)) ? Number(s) : null);

  /* 규격 판정. 경계와 같으면 안쪽(담당자 확인 사항) */
  function judge(item, value) {
    const lim = RULES.limits[item];
    if (!lim) return "UNKNOWN";        // 기준에 없는 항목: 판정하지 않고 알린다
    const v = round(value);
    return v < lim.lsl || v > lim.usl ? "OUT" : "IN";
  }

  /* 같은 키 사건을 직전 발생과의 간격(≤ gap분)으로 묶는다. 입력은 {key, t} 배열 */
  function groupByGap(events, gapMin = RULES.groupGapMin) {
    const sorted = [...events].sort((a, b) => a.t - b.t);
    const last = new Map(), groups = [];
    for (const e of sorted) {
      const g = last.get(e.key);
      if (g && e.t - g.end <= gapMin * 60000) { g.end = e.t; g.count++; }
      else { const ng = { key: e.key, start: e.t, end: e.t, count: 1 }; groups.push(ng); last.set(e.key, ng); }
    }
    return groups;
  }

  /* 완전히 같은 줄 중복 제거(파일 간 겹침 내보내기) */
  function dedupe(records) {
    const seen = new Set();
    return records.filter((r) => { const k = JSON.stringify(r.values); return !seen.has(k) && seen.add(k); });
  }

  /* 화면·보고에 나가기 전 마지막 방어선. 전화번호·이메일을 가린다(사번 형식은 과제에 맞게 추가) */
  function maskPII(s) {
    return String(s).replace(/01[016789]-?\d{3,4}-?\d{4}/g, "***-****-****").replace(/[\w.+-]+@[\w-]+\.[\w.]+/g, "***@***");
  }

  /* 보고: 일반 텍스트(표 없음). 판정 필요 항목은 확인 체크가 없으면 [미확인]. 판단 문장(원인·조치 결정)은 만들지 않는다.
     줄 수가 넘치면 fold 섹션을 건수 한 줄로 접는다. 판정 필요 섹션은 자르지 않는다 */
  function report({ title, mustCheck, summary, notes }, checked = new Set()) {
    const head = [title, "■ 1. 판정 필요"];
    const one = mustCheck.length ? mustCheck.map((x) => ` - [${checked.has(x.id) ? "확인" : "미확인"}] ${maskPII(x.text)}`) : [" - 없음"];
    const tail = ["■ 3. 기타", ...notes.map((n) => ` - ${maskPII(n)}`), " - (직접 입력)"];
    let two = ["■ 2. 요약", ...summary.map((s) => ` - ${maskPII(s)}`)];
    if (head.length + one.length + two.length + tail.length > RULES.maxLines) two = ["■ 2. 요약", ` - ${summary.length}개 항목(줄 수 제한으로 접음)`];
    return [...head, ...one, ...two, ...tail].join("\n");
  }

  const api = { RULES, readTable, splitCsvLine, parseTime, fmt, inWindow, round, toNumber, judge, groupByGap, dedupe, maskPII, report };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.Lib = api;
})(typeof globalThis !== "undefined" ? globalThis : this);
