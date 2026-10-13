# 디스이즈아프리카(TIA) 네이버 블로그 자동 발행

Claude 대화만으로 TIA 네이버 블로그(`this_africa`) 글을 주 1회 7건씩 만들어 하루 1건씩 예약 발행하는 프로젝트입니다.

- 전체 흐름·규칙: [`blog/CLAUDE.md`](blog/CLAUDE.md)
- 서브 에이전트: `blog/agents/` · 말투/SEO 가이드: `blog/guides/` · 상품/방송/도서/CTA 자료: `products/`
- 발행 예정 목록과 발행 이력: `blog/output/topics/content-schedule.json`, `blog/output/publish-state.json` — **발행 후 반드시 커밋·푸시**해서 최신 상태를 유지하세요.

## 이 저장소에 없는 것 (각자 준비)

| 항목 | 준비 방법 |
| --- | --- |
| `blog/.env` (`OPENAI_API_KEY=`) | 본인 OpenAI 키로 직접 생성. 절대 커밋 금지 |
| `blog/naver_profile/` (네이버 로그인) | `cd blog && python scripts/publish.py capture-session` 후 직접 로그인 |
| `blog/assets/` (방송 원본 영상) | 구글 드라이브에서 필요한 회차만 받아서 같은 경로에 두기 |

> `content-schedule.json`의 일부 broadcast 항목은 `drive_link`에 이전 담당자 컴퓨터의 로컬 영상 경로가 들어 있습니다. 해당 항목을 처리할 때는 영상을 `blog/assets/` 아래에 같은 파일명으로 두고 경로를 본인 폴더 기준으로 바꾸거나, 구글 드라이브 링크로 교체하세요.

## 시작하기

1. 이 저장소를 클론하고 Claude 데스크톱 앱에서 폴더를 연결
2. Claude에게: "blog/requirements.txt로 가상환경 만들고 설치, `playwright install chromium`까지 해줘"
3. `blog/.env`에 키 입력 → 대화 재시작
4. 네이버 로그인(`capture-session`) → `check-login` 확인
5. Claude에게: "blog/CLAUDE.md대로 이번 주 콘텐츠 만들어줘"

자세한 단계별 가이드는 노션 "블로그 자동화 — 이어받아 Claude 대화로 세팅·자동 발행하기" 페이지를 참고하세요.
