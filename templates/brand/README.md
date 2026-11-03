# brand — 회사 시나리오 화면에 공식 색·글꼴 입히기 (SK hynix 기본)

| 파일 | 하는 일 |
|---|---|
| `tokens.css` | 변수 16개(색·글꼴·모서리·헤더 높이). 화면은 이 변수만 쓴다 |
| `DESIGN.md` | AI가 화면을 만들기 전에 읽는 규칙(색 역할·대비·글꼴·레이아웃·부품·하지 말 것) |

## 쓰는 법 (과제 폴더에서, 1분)
```
cp ~/probe-kit/templates/brand/tokens.css static/brand.css   # web-starter는 모든 화면이 ui.css 다음에 brand.css를 부른다
cp ~/probe-kit/templates/brand/DESIGN.md docs/DESIGN.md       # 과제 문서 폴더가 있으면. 없으면 Codex에게 경로로 읽게만
```
- 다른 뼈대(static-tool·web-api·Vue/React)도 같은 변수 이름을 쓰면 된다: `<link rel="stylesheet" href="brand.css">` 또는 `import "./brand.css"`.
- 브랜드 없이 시작해도 된다(web-starter `ui.css`에 중립 기본값). 브랜드는 첫 완주 뒤 화면 1개로 확인(HUMAN_CHECK).

## 로고 (기본은 글자 로고)
- 킷에는 로고 파일이 없다(상표). 이미지가 없으면 `ui.js`가 `--brand-name`으로 글자 로고를 그린다.
- 공식 이미지를 쓰는 조건: 과제·담당자·공지가 회사 로고 사용을 막지 않을 때, 헤더 한 곳에만. 받기(작업 폴더의 static에, 실패하면 글자 로고 그대로):
  `curl -fsSL -o static/brand-logo.png https://mis-prod-koce-skhynixhomepage-cdn-01-ep.azureedge.net/img/common/img_logo.png`
  (공식 사이트 헤더 로고 92×48. 큰 CI는 같은 주소의 `img/content/img_ci01.png` 600×296. 2026-11-03 확인)
- 결정 절에 한 줄: 로고 사용 여부와 근거.

## 글꼴
- 공식 사이트는 Roboto + Noto Sans KR(둘 다 무료 공개 라이선스: Apache 2.0 / OFL). 킷에는 파일을 넣지 않고 스택만 둔다(한글 글꼴은 용량이 크고, 외부 `<link>`는 막힌 망에서 화면을 멈출 수 있다).
- 꼭 파일로 넣어야 하면 npm이 될 때 `npm i @fontsource/noto-sans-kr @fontsource/roboto`(Vite 프로젝트에서 import). 받은 글꼴의 라이선스 파일은 같이 둔다.

## 다른 SK 계열사·회사 사이트에서 토큰 뽑기 (5분)
1. `curl -s https://회사주소/ | grep -oE 'href="[^"]+\.css[^"]*"'` → CSS 주소
2. `curl -s <CSS주소> | grep -oiE '#[0-9a-f]{6}\b|#[0-9a-f]{3}\b' | tr A-F a-f | sort | uniq -c | sort -rn | head -20` → 많이 쓰는 색
3. 같은 방법으로 `font-family`, `border-radius`, `@media` 빈도를 본다. 공식 CI 페이지가 있으면 그 값이 우선.
4. 결과를 `tokens.css` 변수에 넣고 DESIGN.md 색 표의 '출처' 칸에 CI/사이트를 구분해 적는다. 사이트 CSS·JS 파일 자체는 복사하지 않는다(저작물).
- 전용 글꼴(예: 통신 계열사의 자사 서체)은 배포 허락이 없으면 쓰지 않고 Noto Sans KR로 대체한다.

## 참고 자료 — AI가 쓰는 것 / 사람이 보는 것
- AI가 바로 쓰는 것: DESIGN.md 형식(사이트별 디자인 규칙을 마크다운으로 적어 에이전트에게 주는 방식), UX 법칙(→ DESIGN.md 6절에 규칙으로 줄임), Lucide·Tabler 아이콘 인라인 SVG, 유니코드 기호.
- 사람이 미리 보고 감을 잡는 것: 화면 갤러리·히어로 섹션 모음·모션 사례·국내 웹 어워드 사이트. 시험 중에 열어 볼 이유는 거의 없다.
- 쓰지 않는 것: 출처 표시가 필요한 무료 아이콘·이미지(화면에 표기 의무), 비상업 라이선스 차트 코드, 영상·모션 제작 SaaS, 노코드 빌더(3시간 과제 범위 밖).
