# ops — 컨테이너·compose·CI

쓰는 때: 과제가 Docker 실행, 여러 서비스 구성(MSA), CI·배포 파이프라인을 요구할 때. 요구가 없으면 쓰지 않는다.
필요: Docker(시험 환경에 없을 수 있다. `docker --version`으로 먼저 본다. 없으면 파일만 만들고 실행은 NOT_RUN).
사용: `Dockerfile`·`compose.yaml`은 `../web-api` 폴더에 복사해 쓴다. `requirements.txt`는 `pip freeze`가 아니라 실제로 import하는 패키지만 버전과 함께 적는다.

| 파일 | 하는 일 |
|---|---|
| `Dockerfile` | slim 이미지, 의존성 먼저 복사(빌드 캐시), 비루트 사용자, HEALTHCHECK, 0.0.0.0 |
| `compose.yaml` | api + PostgreSQL, healthcheck 기반 기동 순서, 볼륨 영속, 비밀값은 `.env` |
| `.github/workflows/ci.yml` | checkout → 설치 → pytest |
| `Jenkinsfile` | 테스트(junit) → 이미지(태그 = git SHA) → main일 때만 push, 자격 증명은 Credentials. CI 서버용이라 시험 PC에서는 실행하지 않고 파일만(인터넷·레지스트리 필요) |
| `k8s/` | Deployment(liveness `/health`·readiness `/readyz`·자원 요청/한도·비루트)·Service·Ingress·Kustomize(이미지 태그 한 줄만 CI가 수정 → GitOps) |

## 기술 후보
| 층 | 후보 | 언제 |
|---|---|---|
| 실행 | **uvicorn 직접**, Docker, compose | 컨테이너는 과제가 요구할 때 |
| 오케스트레이션 | compose, Kubernetes(Deployment·Service·ConfigMap, liveness/readiness probe), Argo CD(GitOps) | K8s는 클러스터가 주어질 때만. probe 경로는 `/health`·`/readyz` |
| CI/CD | **GitHub Actions**, Jenkins(Jenkinsfile 단계: checkout→test→build→push) | 원격 실행은 시험 중 확인 불가 → NOT_RUN |
| 관측 | **구조화 로그(경로·상태·지연)**, Prometheus `/metrics` + Grafana | 운영 지표 요구가 있을 때 |

## 현업 수준 체크
1. 이미지에 비밀값·데이터·`.git`이 들어가지 않는다(`.dockerignore`, `.env`는 커밋 금지)
2. 버전 고정한 requirements, 비루트 실행, 헬스체크, 0.0.0.0 바인딩
3. compose 기동 순서는 healthcheck로, 데이터는 볼륨으로 영속
4. 실제로 `docker build`·`docker compose up`을 돌렸으면 로그 경로, 못 돌렸으면 NOT_RUN(사유)
5. 이미지 태그는 `:latest`가 아니라 git SHA·버전(추적·롤백 가능)
6. K8s면 배포 뒤 `kubectl rollout status --timeout`, READY 수, Service Endpoints, 내부 호출 200까지 확인. 클러스터가 없으면 `kubectl kustomize`·`--dry-run=client`로 문법만 보고 배포는 NOT_RUN
7. DB 구조를 바꾸면 새 열 추가 → 앱 배포 → 옛 열 정리 순서(구버전과 함께 돌아도 깨지지 않게)
8. 종료 대기: `terminationGracePeriodSeconds` > preStop + 앱 종료 시간(롤링 배포 중 요청 유실 방지)
