// fetch 래퍼 하나. 화면(DOM)과 무관해서 React·Vue에서도 그대로 import한다.
// - 쿠키(세션)는 같은 출처로 자동 전송. 상태를 바꾸는 요청에는 서버가 요구하는 X-Requested-With 헤더를 붙인다.
// - 401이면 로그인 화면으로(돌아올 주소 next), 그 밖의 실패는 ApiError(status, message, fields)로 던진다.
export class ApiError extends Error {
  constructor(status, message, fields = {}) { super(message); this.status = status; this.fields = fields; }
}

// 상태코드 → 사람이 읽는 문구 한 곳. 서버가 detail 문구를 주면 그쪽이 우선.
export const STATUS_COPY = {
  0: "서버에 연결할 수 없습니다. 서버가 켜져 있는지 확인하세요.",
  400: "요청을 처리할 수 없습니다.", 401: "로그인이 필요합니다.", 403: "권한이 없습니다.", 404: "찾을 수 없습니다.",
  409: "이미 있는 값입니다.", 422: "입력값을 확인하세요.", 429: "잠시 뒤 다시 시도하세요.", 500: "서버 오류입니다. 잠시 뒤 다시 시도하세요.",
};
export const copyFor = (s) => STATUS_COPY[s] || (s >= 500 ? STATUS_COPY[500] : STATUS_COPY[400]);

// React·Vue처럼 한 화면 앱이면 auth.onUnauthorized = () => setUser(null)처럼 연결한다(없으면 로그인 화면으로 이동)
export const auth = { onUnauthorized: null };

export async function api(path, { method = "GET", body } = {}) {
  const headers = { "X-Requested-With": "fetch" };
  if (body !== undefined) headers["Content-Type"] = "application/json";
  let res;
  try {
    res = await fetch(path, { method, headers, credentials: "same-origin", body: body === undefined ? undefined : JSON.stringify(body) });
  } catch {
    throw new ApiError(0, copyFor(0));
  }
  const data = res.status === 204 ? null : await res.json().catch(() => null); // 프록시의 HTML 오류 페이지도 상태 문구로
  if (res.ok) return data;
  const authPage = /\/(login|signup|forgot|reset)\.html$/.test(location.pathname);
  if (res.status === 401 && !path.startsWith("/api/auth/") && !authPage) {
    if (auth.onUnauthorized) auth.onUnauthorized();
    else location.href = "/login.html?next=" + encodeURIComponent(location.pathname + location.search);
  }
  const detail = data && data.detail;
  if (Array.isArray(detail)) { // 422: [{loc:[..., 칸이름], msg}] → 칸별 오류
    const fields = {};
    for (const d of detail) (fields[d.loc.at(-1)] ||= []).push(d.msg);
    throw new ApiError(res.status, copyFor(res.status), fields);
  }
  const err = new ApiError(res.status, typeof detail === "string" ? detail : copyFor(res.status));
  err.retryAfter = Number(res.headers.get("Retry-After")) || 0;
  throw err;
}
