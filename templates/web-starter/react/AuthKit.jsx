// 과제가 React(Vite)를 요구할 때: 로그인 상태(Provider) + 역할 막기 + 로그인 폼. 서버는 web-starter 그대로.
// 쓰는 법: npm create vite@latest web -- --template react → src/에 이 파일과 static/api.js·ui.css·brand.css 복사
//   main.jsx: import "./ui.css"; import "./brand.css";  <AuthProvider><App/></AuthProvider>
//   vite.config.js: server: { proxy: { "/api": "http://localhost:8000" } }  → 같은 출처라 쿠키·CORS 문제 없음
//   빌드(dist/)는 FastAPI static/에 넣어 같은 출처로 서빙. 회원가입·찾기·재설정은 정적 화면(signup.html 등)을 그대로 써도 된다.
import { createContext, useContext, useEffect, useState } from "react";
import { api, auth } from "./api.js";

const Auth = createContext(null);
export const useAuth = () => useContext(Auth);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(undefined); // undefined = 확인 중, null = 로그인 안 함
  useEffect(() => {
    auth.onUnauthorized = () => setUser(null); // 세션이 끊기면 로그인 폼으로
    api("/api/auth/me").then(setUser, () => setUser(null));
  }, []);
  const login = async (username, password) => setUser(await api("/api/auth/login", { method: "POST", body: { username, password } }));
  const logout = async () => { await api("/api/auth/logout", { method: "POST" }); setUser(null); };
  return <Auth.Provider value={{ user, login, logout }}>{children}</Auth.Provider>;
}

// 화면 막기는 편의일 뿐, 진짜 권한 검사는 서버(require_role)가 한다
export function RequireRole({ role, children, fallback = null }) {
  const { user } = useAuth();
  if (user === undefined) return <div className="state loading" role="status">로그인 확인 중…</div>;
  if (!user) return fallback ?? <LoginForm />;
  if (user.must_change) return <div className="state" role="status">임시 비밀번호입니다. <a href="/change-password.html">비밀번호 바꾸기</a></div>;
  if (role && user.role !== role) return <div className="state error" role="alert">✕ 이 화면을 볼 권한이 없습니다.</div>;
  return children;
}

const SAVED = "savedUsername";
export function LoginForm() {
  const { login } = useAuth();
  const [username, setUsername] = useState(localStorage.getItem(SAVED) || "");
  const [password, setPassword] = useState("");
  const [remember, setRemember] = useState(Boolean(localStorage.getItem(SAVED)));
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  async function submit(e) {
    e.preventDefault();
    setBusy(true); setError("");
    try {
      await login(username, password);
      remember ? localStorage.setItem(SAVED, username.trim()) : localStorage.removeItem(SAVED); // 아이디만 저장
    } catch (err) { setError(err.message); setPassword(""); }
    finally { setBusy(false); }
  }
  return (
    <form className="auth card" onSubmit={submit} noValidate>
      <h1>로그인</h1>
      {error && <div className="alert ng" role="alert">{error}</div>}
      <div className="field"><label htmlFor="u">아이디</label>
        <input id="u" autoComplete="username" value={username} onChange={(e) => setUsername(e.target.value)} required /></div>
      <div className="field"><label htmlFor="p">비밀번호</label>
        <input id="p" type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} required /></div>
      <label className="check"><input type="checkbox" checked={remember} onChange={(e) => setRemember(e.target.checked)} /> 아이디 저장</label>
      <button className="btn primary" disabled={busy || !username || !password}>{busy ? "로그인하는 중…" : "로그인"}</button>
      <div className="links"><a href="/forgot.html">비밀번호 찾기</a><a href="/signup.html">회원가입</a></div>
    </form>
  );
}
