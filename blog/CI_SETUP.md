> ⚠️ **2026-07-15부로 기본 운영 방식이 아님.** TIA 블로그는 이제 로컬에서 주 1회 직접
> `content_schedule.py next-batch`로 7건을 한 번에 생성하는 방식이 기본이다(자세한 내용은
> `CLAUDE.md` 참고). 이 문서(GitHub Actions 완전자동화)는 나중에 다시 자동화가 필요할 때를
> 대비한 참고 자료로만 남겨둔다 — `deploy/github-actions/blog-pipeline.yml`도 매일 자동
> 실행되던 `schedule` 트리거를 제거하고 수동 실행(`workflow_dispatch`)만 남긴 상태다. 게다가
> 이 워크플로우는 `topic_queue.py`(구 노션 큐 전용) 기준으로 작성돼 있어 이 문서의 `content_schedule.py`
> 기반 최신 파이프라인과 어긋난다 — 다시 쓰려면 `generate`/`publish-real` job을
> `content_schedule.py next`/`mark-done` 호출로 먼저 맞춰야 한다.

# GitHub Actions로 TIA 블로그 파이프라인 완전자동화 — 설정 가이드

목표: 사람이 매번 앱을 켜두지 않아도, 정해진 시각에 GitHub의 서버에서 0~4단계(주제 선정~조립)와
5단계(임시저장)까지 자동 실행되고, 실제 공개 발행만 GitHub 화면에서 버튼 한 번 눌러 승인하는 구조.

워크플로우 정의: `deploy/github-actions/blog-pipeline.yml` (아래 0번 단계에서 저장소 루트로 옮겨야 함)

---

## 0. 저장소에 파일 배치 + 첫 푸시

`this-is-africa`는 저장소(`gkssk8827/claude`) 루트가 아니라 그 하위 폴더입니다(원본 `blog` 프로젝트와
같은 위계). 반면 GitHub Actions 워크플로우 파일은 **반드시 저장소 루트의 `.github/workflows/`**
안에 있어야 인식됩니다. 그래서 준비해둔 파일을 옮겨야 합니다.

저장소 루트(= `this-is-africa`의 부모 폴더)에서:

```bash
git init                      # 아직 git 저장소가 아니라면
git remote add origin https://github.com/gkssk8827/claude.git

mkdir -p .github/workflows
cp this-is-africa/deploy/github-actions/blog-pipeline.yml .github/workflows/blog-pipeline.yml

git add .
git commit -m "feat: TIA 블로그 파이프라인 GitHub Actions 자동화 추가"
git push -u origin main       # 브랜치명이 다르면 맞게 수정
```

`this-is-africa/deploy/` 폴더는 워크플로우 파일을 옮기고 나면 더 이상 필요 없으니 지워도 됩니다.

---

## 1. GitHub Secrets 등록

`Settings > Secrets and variables > Actions > New repository secret`

| Secret 이름 | 값 | 용도 |
|---|---|---|
| `ANTHROPIC_API_KEY` | [console.anthropic.com](https://console.anthropic.com)에서 발급 | 0~4단계(Claude Code CLI)가 리서치·글쓰기 수행 |
| `OPENAI_API_KEY` | 기존 `blog/.env`에 있는 값과 동일 | 이미지 생성(`generate_photo.py`) |
| `NAVER_STORAGE_STATE_B64` | 아래 2번 절차로 생성 | 5단계(발행)의 네이버 로그인 쿠키 |

**주의**: `ANTHROPIC_API_KEY`로 콘텐츠를 생성하면 실행마다 API 비용이 발생합니다(리서치+글쓰기+조립 1회
분량, 대략 수백 원~1천 원대 수준 — 정확한 금액은 Anthropic 콘솔에서 확인하세요). 이미지 생성도 별도로
OpenAI 비용이 붙습니다.

---

## 2. 네이버 로그인 세션(storage_state) 만들기

`naver_profile` 폴더(39MB, 캐시 포함)를 통째로 CI에 올리는 건 비현실적이고 보안상으로도 좋지 않습니다.
대신 로그인 쿠키만 작은 JSON으로 뽑아 Secret에 등록합니다. **로컬 컴퓨터에서** 실행하세요(2단계 인증은
사람만 할 수 있음):

```bash
cd this-is-africa/blog
python scripts/publish.py capture-session --export-storage-state naver_state.json
```

브라우저가 뜨면 직접 로그인(2단계 인증 포함)합니다. 완료되면 `naver_state.json`이 생성됩니다.

이 파일을 base64로 인코딩해 Secret에 등록:

```bash
base64 -i naver_state.json | pbcopy   # macOS: 클립보드에 복사됨
```

GitHub `NAVER_STORAGE_STATE_B64` Secret 값에 붙여넣기.

**등록 후 로컬의 `naver_state.json` 파일은 반드시 삭제하세요** (git에 커밋 금지 — `this-is-africa/.gitignore`에
`blog/naver_state.json` 등 관련 패턴을 이미 추가해뒀습니다). 로그인 쿠키가 그대로 담긴 민감한 파일입니다.

### 세션 만료 시 (재발급 필요)

네이버 세션은 주기적으로 만료되거나, 새 위치(GitHub Actions의 데이터센터 IP)에서 사용 시 네이버가
이상 로그인으로 판단해 강제로 재인증을 요구할 수 있습니다. `publish-draft`/`publish-real` job이
"로그인 세션이 유효하지 않습니다" 에러로 실패하면, 위 2번 절차를 다시 실행해 Secret을 갱신하세요.

---

## 3. 실제 발행 승인 게이트 설정 (production-publish 환경)

`Settings > Environments > New environment` → 이름 `production-publish` 입력 →
`Required reviewers`에 본인(또는 승인 권한을 줄 사람) 추가 → Save.

이렇게 하면 워크플로우의 `publish-real` job은 **임시저장까지 자동으로 끝난 뒤, 이 환경에 등록된
리뷰어가 Actions 실행 화면에서 "Review deployments" → "Approve and deploy"를 눌러야만** 진행됩니다.
누르지 않으면 영원히 대기 상태로 멈춰 있을 뿐, 자동으로 공개되지 않습니다.

---

## 4. 저장소 쓰기 권한 설정

`Settings > Actions > General > Workflow permissions` → **"Read and write permissions"** 선택 →
Save. (`generate`/`publish-draft`/`publish-real` job이 생성된 글·발행 상태를 저장소에 커밋해서
남기기 때문에 필요합니다.)

---

## 5. 동작 확인

전부 설정한 뒤, `Actions` 탭 → `TIA Blog Pipeline` → `Run workflow`로 수동 실행해 처음부터 끝까지
(승인 전까지) 문제없이 도는지 확인하는 걸 권장합니다. **자동 스케줄(cron)은 제거됐고, 이제
`workflow_dispatch`(수동 실행)만 남아 있습니다** — 기본 운영은 로컬 주 1회 실행이기 때문입니다.

---

## 알려진 리스크와 대안

### 네이버 봇 탐지 (가장 큰 리스크)

`publish.py`는 지금까지 사용자님의 실제 컴퓨터·IP에서만 실행되며 신뢰를 쌓아왔습니다. GitHub Actions의
클라우드 러너는 **매번 새로운 데이터센터 IP**에서 접속하므로, 쿠키가 유효해도 네이버가 "낯선 환경에서의
접속"으로 판단해 재인증을 요구하거나 자동화 탐지에 걸릴 가능성이 기존보다 높습니다. 실제 Chrome
채널(`playwright install chrome`)을 쓰고 `--disable-blink-features=AutomationControlled`를 유지해도
100% 회피를 보장하지는 못합니다.

**대안 — self-hosted runner**: `publish-draft`/`publish-real` job의 `runs-on: ubuntu-latest`를
`runs-on: [self-hosted]`로 바꾸고, 사용자님의 컴퓨터를 GitHub 저장소의 self-hosted runner로 등록하면
(`Settings > Actions > Runners > New self-hosted runner` 안내를 따라 러너 프로그램 설치 후 백그라운드
서비스로 등록), 발행 단계만큼은 지금까지 써온 것과 동일한 로컬 IP/브라우저 환경에서 실행됩니다.
이 경우 `naver_profile` 영구 프로필을 그대로 써도 되므로 `--storage-state` 없이 기존 방식 그대로
동작합니다. 대신 컴퓨터(정확히는 러너 백그라운드 프로세스)가 켜져 있어야 하는 제약은 남지만, Cowork
앱 자체를 띄워둘 필요는 없어 훨씬 가볍습니다. 0~4단계(콘텐츠 생성)는 클라우드 러너 그대로 둬도 무방합니다
(네이버와 무관해 리스크가 없음).

### 셀렉터 깨짐

네이버 SmartEditor ONE의 해시 클래스명이 바뀌면 `publish.py`의 `SELECTORS`가 깨져 발행이 실패합니다.
CI에서는 화면을 볼 사람이 없으므로, 실패 시 `logs/screenshots/`를 아티팩트로 업로드하도록 워크플로우에
이미 넣어뒀습니다 — 실패한 Actions 실행의 Artifacts에서 스크린샷을 내려받아 원인을 확인하세요.

### 비용

매일 자동 실행되므로 Anthropic API(리서치·글쓰기)와 OpenAI API(이미지 생성) 비용이 매일 발생합니다.
필요 없는 날엔 Actions 탭에서 워크플로우를 일시 비활성화(`Disable workflow`)할 수 있습니다.
