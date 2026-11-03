// 화면 공통 도우미. 데이터는 textContent로만 넣는다(innerHTML에 서버 값 금지 → XSS 방지).
import { api } from "./api.js";

export const $ = (sel, el = document) => el.querySelector(sel);
const stop = () => new Promise(() => {}); // 이동 중에는 뒤 코드가 돌지 않게

// 로그인 뒤 돌아갈 주소는 같은 사이트 상대 경로만(열린 리디렉션 방지)
export const safeNext = (n, fallback = "app.html") => (n && /^\/(?![/\\])[^\s\\]*$/.test(n) ? n : fallback); // "//x"·"/\x"는 다른 사이트로 해석된다

// 화면 보호: 로그인 안 했으면 로그인 화면, 임시 비밀번호면 변경 화면, 역할이 다르면 안내. 진짜 막는 곳은 서버다.
export async function guard({ role } = {}) {
  let me;
  try {
    me = await api("/api/auth/me");
  } catch (e) {
    if (e.status === 401) { location.href = "login.html?next=" + encodeURIComponent(location.pathname); return stop(); }
    throw e;
  }
  if (me.must_change && !location.pathname.endsWith("change-password.html")) { location.href = "change-password.html"; return stop(); }
  if (role && me.role !== role) {
    const m = document.createElement("main");
    m.innerHTML = '<div class="state error" role="alert">✕ 이 화면을 볼 권한이 없습니다. <a href="app.html">내 화면으로</a></div>';
    document.body.replaceChildren(m);
    return stop();
  }
  return me;
}

// 글자 로고: brand.css의 --brand-name 첫 단어는 --brand, 나머지는 --brand-2 색
export function wordmark() {
  const name = getComputedStyle(document.documentElement).getPropertyValue("--brand-name").trim().replace(/^["']|["']$/g, "") || "서비스";
  const [first, ...rest] = name.split(" ");
  const el = document.createElement("span");
  el.className = "wordmark";
  el.append(first + (rest.length ? " " : ""));
  if (rest.length) { const s = document.createElement("span"); s.textContent = rest.join(" "); el.append(s); }
  return el;
}

// 헤더: 로고 한 곳(static/brand-logo.png가 있으면 이미지, 없으면 글자 로고) + 역할별 메뉴 + 사용자 + 로그아웃
export function renderHeader(me) {
  const menu = [["app.html", "내 화면"], ...(me.role === "admin" ? [["admin.html", "운영자"]] : [])];
  const h = document.createElement("header");
  h.className = "header";
  const logo = document.createElement("a");
  logo.className = "logo"; logo.href = "app.html"; logo.setAttribute("aria-label", "홈");
  const img = new Image();
  img.alt = "로고"; img.src = "brand-logo.png";
  img.onerror = () => img.replaceWith(wordmark());
  logo.append(img);
  const nav = document.createElement("nav");
  for (const [href, label] of menu) {
    const a = document.createElement("a");
    a.href = href; a.textContent = label;
    if (location.pathname.endsWith(href)) a.setAttribute("aria-current", "page");
    nav.append(a);
  }
  const who = document.createElement("span");
  who.className = "who"; who.textContent = `${me.name}(${me.role_label})`;
  const out = document.createElement("button");
  out.className = "btn small"; out.type = "button"; out.textContent = "로그아웃";
  out.onclick = async () => { await api("/api/auth/logout", { method: "POST" }); location.href = "login.html"; };
  h.append(logo, nav, who, out);
  document.body.prepend(h);
}

// 로딩·빈 결과·오류 세 상태를 모든 데이터 영역이 같은 모양으로
export function showState(el, kind, text) {
  const d = document.createElement("div");
  d.className = "state " + kind;
  d.setAttribute("role", kind === "error" ? "alert" : "status");
  d.textContent = (kind === "error" ? "✕ " : "") + text;
  el.replaceChildren(d);
}

// cols: [[키, 제목, (값, 행) => 표시값?], ...]
export function fillTable(el, cols, rows, emptyText = "아직 없습니다.") {
  if (!rows.length) return showState(el, "empty", emptyText);
  const t = document.createElement("table");
  const head = t.createTHead().insertRow();
  for (const [, label] of cols) { const th = document.createElement("th"); th.textContent = label; head.append(th); }
  const body = t.createTBody();
  for (const r of rows) {
    const tr = body.insertRow();
    for (const [key, , fmt] of cols) {
      const v = fmt ? fmt(r[key], r) : r[key];
      const td = tr.insertCell();
      if (v instanceof Node) td.append(v); else td.textContent = v ?? "";
      if (typeof r[key] === "number") td.className = "num";
    }
  }
  const wrap = document.createElement("div");
  wrap.className = "table-wrap"; wrap.append(t);
  el.replaceChildren(wrap);
}

// SQLite CURRENT_TIMESTAMP는 UTC("2026-11-03 09:54:09")다. 화면에는 브라우저 시간대(한국이면 KST)로 보여 준다.
export function fmtTime(v) {
  if (!v) return "";
  const d = new Date(v.replace(" ", "T") + "Z"), p = (n) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`;
}

export function toast(text) {
  const d = document.createElement("div");
  d.className = "toast"; d.setAttribute("role", "status"); d.textContent = text;
  document.body.append(d);
  setTimeout(() => d.remove(), 3000);
}

// 칸별 오류: <div class="field"><input name="x"><div class="error" id="x-error"></div></div>
export function fieldErrors(form, fields = {}) {
  for (const input of form.querySelectorAll("input")) {
    const msgs = fields[input.name];
    const box = form.querySelector(`#${input.name}-error`);
    input.setAttribute("aria-invalid", msgs ? "true" : "false");
    if (box) box.textContent = msgs ? msgs.join(", ") : "";
  }
}

export async function busy(button, work) {
  button.disabled = true;
  try { return await work(); } finally { button.disabled = false; }
}

// 비밀번호 규칙 체크리스트: 서버 정책(/api/auth/policy)을 받아 그리고, 입력마다 ✓/○. 최종 판정은 서버.
const LABEL = { upper: ["영문 대문자", /[A-Z]/], lower: ["영문 소문자", /[a-z]/], digit: ["숫자", /[0-9]/], symbol: ["특수문자", /[!-\/:-@[-`{-~]/] };
export async function passwordChecklist(pwInput, listEl, usernameInput) {
  const p = await api("/api/auth/policy");
  const rules = [[`${p.pw_min}~${p.pw_max}자`, (v) => v.length >= p.pw_min && v.length <= p.pw_max],
    ...p.require.map((k) => [`${LABEL[k][0]} 1개 이상`, (v) => LABEL[k][1].test(v)]),
    ["아이디를 포함하지 않기", (v) => !usernameInput || !usernameInput.value || !v.toLowerCase().includes(usernameInput.value.toLowerCase())]];
  const items = rules.map(([text]) => { const li = document.createElement("li"); li.textContent = text; return li; });
  listEl.replaceChildren(...items);
  const update = () => rules.forEach(([, ok], i) => items[i].classList.toggle("ok", ok(pwInput.value)));
  pwInput.addEventListener("input", update);
  usernameInput?.addEventListener?.("input", update); // 입력칸이 아닌 {value} 객체도 받는다
  update();
  return p;
}
