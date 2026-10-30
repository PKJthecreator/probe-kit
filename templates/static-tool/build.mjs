// 한 파일로 묶기: tool.html의 <script src="lib.js">를 내용으로 바꿔 dist/tool.html 하나를 만든다(공유폴더에 그 파일만 두면 된다).
// 또 Vite 빌드 결과(dist/index.html)도 한 파일로 만든다: node build.mjs --vite dist
//   Vite는 <script type="module" src=...>를 쓰므로 file://로 열면 빈 화면이 된다. 내용을 인라인하면 열린다.
// 끝에 외부 주소(http·https·//)와 브라우저 저장소 사용을 검사하고, 있으면 종료 코드 1.
import { readFileSync, writeFileSync, mkdirSync, readdirSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const args = process.argv.slice(2);

function inlineFile(htmlPath, outPath) {
  const base = dirname(htmlPath);
  let html = readFileSync(htmlPath, "utf8");
  const safe = (s) => s.replace(/<\/script/gi, "<\\/script");
  html = html.replace(/<link[^>]+rel="stylesheet"[^>]*href="([^"]+)"[^>]*>/g, (_, href) => `<style>${readFileSync(join(base, href), "utf8")}</style>`);
  html = html.replace(/<script([^>]*?)\ssrc="([^"]+)"[^>]*><\/script>/g, (_, attrs, src) => {
    const module = /type="module"/.test(attrs) ? ' type="module"' : "";   // 인라인 module은 file://에서도 실행된다
    return `<script${module}>${safe(readFileSync(join(base, src), "utf8"))}</script>`;
  });
  html = html.replace(/<link[^>]+rel="modulepreload"[^>]*>/g, "");
  mkdirSync(dirname(outPath), { recursive: true });
  writeFileSync(outPath, html);
  return html;
}

function check(html, label) {
  const problems = [];
  if (/(src|href)="(https?:)?\/\//i.test(html)) problems.push("외부 주소(src/href)");
  if (/\b(localStorage|sessionStorage|indexedDB)\b/.test(html)) problems.push("브라우저 저장소 사용");
  if (/<script[^>]+src=|<link[^>]+href="(?!data:)[^"]+\.(css|js)"/.test(html)) problems.push("인라인되지 않은 파일 참조");
  console.log(problems.length ? `FAIL ${label}: ${problems.join(", ")}` : `PASS ${label}: 한 파일, 외부 호출·저장소 없음`);
  return problems.length === 0;
}

let ok;
if (args[0] === "--vite") {
  const dist = resolve(args[1] || "dist");
  const js = readdirSync(join(dist, "assets")).filter((f) => f.endsWith(".js"));
  if (js.length > 1) console.log(`경고: JS 파일 ${js.length}개(코드 분할). vite.config에 build.rollupOptions.output.inlineDynamicImports=true`);
  ok = check(inlineFile(join(dist, "index.html"), join(dist, "single.html")), join(dist, "single.html"));
} else {
  ok = check(inlineFile(join(here, "tool.html"), join(here, "dist", "tool.html")), "dist/tool.html");
}
process.exitCode = ok ? 0 : 1;
