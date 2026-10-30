// 실행: node --test   (설치 불필요, Node 18+). 기대값은 요구 문장·담당자 답·손계산에서 정한다.
import { test } from "node:test";
import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { readFileSync } from "node:fs";

const L = createRequire(import.meta.url)("./lib.js");

test("CSV: BOM·CRLF·따옴표 안 쉼표와 \"\" · 헤더 앞 메타의 비밀 키는 버림", () => {
  const t = L.readTable('﻿# exported=2026-10-30 07:05; conn=db://dummy:dummy@host\r\ntime,equipment,item,value,note\r\n2026-10-30 08:00,EQ-1,THK,100.0,"a, ""b"""\r\n');
  assert.equal(t.meta.exported, "2026-10-30 07:05");
  assert.equal(t.meta.conn, undefined);
  assert.equal(t.records[0].values.note, 'a, "b"');
  assert.equal(t.records[0].line, 3);
});

test("헤더 뒤 '#' 손상 줄은 주석으로 삼키지 않고 줄 번호로 알린다", () => {
  const t = L.readTable("time,equipment,item,value\n##########\n2026-10-30 08:00,EQ-1,THK,100\n");
  assert.deepEqual(t.bad, [{ line: 2, reason: "열 1개(기대 4)" }]);
  assert.equal(t.records.length, 1);
});

test("시각: UTC 'Z'는 KST로, 표기 없음은 KST, 엑셀 저장 형식(H:mm)도 읽음", () => {
  assert.equal(L.fmt(L.parseTime("2026-10-29T23:30:00Z")), "10/30 08:30");
  assert.equal(L.fmt(L.parseTime("2026-10-30 8:30")), "10/30 08:30");
  assert.equal(L.parseTime("30/10/2026"), null);
  assert.equal(L.parseTime("2026-02-31 08:00"), null);   // 없는 날짜를 3월로 넘기지 않는다
  assert.equal(L.parseTime("2026-10-30 25:00"), null);
  assert.equal(L.parseTime("2026-02-31T09:00:00Z"), null);   // 시간대가 붙어도 없는 날짜는 거부
  assert.equal(L.parseTime("2026-02-28 09:00:60"), null);
  assert.equal(L.fmt(L.parseTime("2026-10-30T08:30:00+09:00")), "10/30 08:30");
});

test("구간 [시작, 끝): 시작 정각 포함, 끝 정각은 다음 구간", () => {
  const s = L.parseTime("2026-10-29 07:00:00"), e = L.parseTime("2026-10-30 07:00:00");
  assert.equal(L.inWindow(s, s, e), true);
  assert.equal(L.inWindow(e, s, e), false);
});

test("규격 경계와 같으면 안쪽, 부동소수점 경계가 뒤집히지 않음, 기준에 없는 항목은 UNKNOWN", () => {
  assert.equal(L.judge("THK", 105.0), "IN");
  assert.equal(L.judge("THK", 10.51 * 10), "OUT");            // 105.1
  assert.equal(L.judge("THK", 10.5 * 10 + 1e-12), "IN");      // 105.000000000001 → 105.0
  assert.equal(L.judge("XYZ", 1), "UNKNOWN");
});

test("숫자 칸: 빈 값·공백·문자는 null(0으로 오판하지 않음)", () => {
  assert.equal(L.toNumber(""), null);
  assert.equal(L.toNumber("  "), null);
  assert.equal(L.toNumber("NaN"), null);
  assert.equal(L.toNumber("101.5"), 101.5);
  assert.equal(L.toNumber("0"), 0);
});

test("간격 묶음: 직전 발생 후 10분 이내(같으면 포함)는 한 건", () => {
  const t0 = L.parseTime("2026-10-30 08:00");
  const ev = [0, 10, 20, 31].map((m) => ({ key: "EQ-1/E1", t: t0 + m * 60000 }));
  const g = L.groupByGap(ev);
  assert.deepEqual(g.map((x) => x.count), [3, 1]);
});

test("완전 중복 줄 제거", () => {
  const r = [{ values: { a: "1" } }, { values: { a: "1" } }, { values: { a: "2" } }];
  assert.equal(L.dedupe(r).length, 2);
});

test("보고: 확인 안 한 항목은 [미확인], 전화번호 가림, 줄 수 제한 시 요약을 접음", () => {
  const out = L.report({ title: "T", mustCheck: [{ id: "a", text: "EQ-1 규격 밖 담당 010-0000-0000" }, { id: "b", text: "EQ-2" }],
    summary: Array.from({ length: 40 }, (_, i) => `EQ-${i}`), notes: [] }, new Set(["a"]));
  assert.match(out, /\[확인\] EQ-1/);
  assert.match(out, /\[미확인\] EQ-2/);
  assert.doesNotMatch(out, /010-0000-0000/);
  assert.ok(out.split("\n").length <= L.RULES.maxLines);
});

test("화면 파일에 외부 주소·브라우저 저장소 없음", () => {
  for (const f of ["tool.html", "lib.js"]) {
    const s = readFileSync(new URL(f, import.meta.url), "utf8");
    assert.doesNotMatch(s, /(src|href)="https?:|\b(localStorage|sessionStorage|indexedDB)\b/, f);
  }
});
