// 과제가 Vue(Vite)를 요구할 때: 로그인 상태 공유 + 라우터 막기. 서버는 web-starter 그대로.
// 쓰는 법: npm create vite@latest web -- --template vue → src/에 이 파일·LoginForm.vue와 static/api.js·ui.css·brand.css 복사
//   main.js: import "./ui.css"; import "./brand.css"
//   vite.config.js: server: { proxy: { "/api": "http://localhost:8000" } }
//   라우터를 쓰면: router.beforeEach(async (to) => (await allowed(to.meta.role)) || { path: "/login" })
import { ref } from "vue";
import { api, auth } from "./api.js";

export const user = ref(undefined); // undefined = 확인 중, null = 로그인 안 함
auth.onUnauthorized = () => (user.value = null); // 세션이 끊기면 로그인 상태를 비운다

export async function loadMe() {
  try { user.value = await api("/api/auth/me"); } catch { user.value = null; }
  return user.value;
}

export async function login(username, password) {
  user.value = await api("/api/auth/login", { method: "POST", body: { username, password } });
  return user.value;
}

export async function logout() {
  await api("/api/auth/logout", { method: "POST" });
  user.value = null;
}

// 화면 막기는 편의, 진짜 검사는 서버(require_role)
export async function allowed(role) {
  const me = user.value === undefined ? await loadMe() : user.value;
  if (!me) return false;
  if (me.must_change) { location.href = "/change-password.html"; return false; }
  return !role || me.role === role;
}
