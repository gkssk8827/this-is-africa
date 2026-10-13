# CLAUDE.md

블로그 글 작성을 서브 에이전트에게 위임해 자동화하는 오케스트레이션 프로젝트.

**2026-07-15 개편: 매일 GitHub Actions로 자동 실행하던 방식을 접고, 주 1회 로컬에서 직접
실행하는 방식으로 바꿨다.** 한 번 실행할 때 7건(=7일치, 기본값)을 한 번에 배치로 생성한다.
(예전 방식이 궁금하면 `CI_SETUP.md` 참고 — 지금은 참고용으로만 남겨뒀고 기본 운영 방식이
아니다.)

**TIA(트래블 디스이즈아프리카) 전용 변형**: 원본 blog 프로젝트와 달리 이 프로젝트는 주제가 7개
고정 카테고리로 한정되어 있다 — 매번 트렌드를 조사해 주제를 새로 뽑지 않는다(단,
`southeast_trend`만 예외 — 아래 참고).

| 카테고리 | 설명 | 주 소스 | 네이버 블로그 카테고리 | 우선순위 |
| :--- | :--- | :--- | :--- | :--- |
| `broadcast` | 방송 참여 관련. **2026-09-13 확정 — 미션/게임 recap이 아니라 그 장면에 나온 여행지·음식·랜드마크 등 실제 여행 정보가 글의 중심**(자세한 내용은 `agents/researcher.md`/`agents/writer.md`의 "broadcast" 절 참고) | 사용자가 매번 제공하는 방송 스크립트+영상(신규), 또는 `../products/on-air.md`(구식, 병행) | TIA LIVE | **1순위** |
| `notice` | 공휴 연휴 공지, 설명회 공지 | 사용자가 그때그때 짧게 전달하거나 content-schedule.json에 미리 등록 | TIA 이야기 | **2순위** |
| `southeast_trend` | 동남부 아프리카 여행 관련 **긍정적** 최신 이슈/트렌드(예: "허니문 여행지 1위 선정" 같은 화제) | 정적 목록 없음 — 매번 researcher가 실시간 웹검색으로 직접 주제를 정함 | 아프리카 여행 정보 | **3순위** |
| `product_daily` | 상품 관련(일자별 연재/후기형) | `../products/packages.md` | TIA 패키지 여행 | 4순위(그 외, 순환) |
| `review` | 여행자 실제 후기형 | (아직 소스 없음 — 사용자가 content-schedule.json에 수기 추가) | 생생 고객 후기 | 4순위(그 외, 순환) |
| `qna` | 여행자 Q&A | 노션 Q&A DB (기존 방식 그대로 유지) | 아프리카 여행 정보 | 4순위(그 외, 순환) |
| `book` | 《이토록아프리카》 도서 관련 | `../products/book.md` | TIA 이야기 | 4순위(그 외, 순환) |

네이버 블로그 카테고리 매핑은 `scripts/build_post_json.py`의 `CATEGORY_MAP`에 있고, 5단계에서
`output/[주제]/meta.json`을 읽어 자동 적용된다(아래 0단계 참고). 카테고리 트리가 바뀌면
`CATEGORY_MAP`만 고치면 된다.

`broadcast`/`notice`/`product_daily`/`review`/`book` 5개는 `output/topics/content-schedule.json`에
미리 정리해둔 목록(또는 그때그때 사용자가 추가한 항목)을 순서대로 소비하고, `qna`만 예외적으로
노션에서 계속 실시간으로 가져온다. `southeast_trend`는 애초에 정적 목록이 없다 — 매 실행마다
researcher가 그날 기준 웹검색으로 직접 주제를 찾는다.

**발행 우선순위**: 매 실행(주 1회, 7건 배치)마다 다음 순서로 슬롯을 채운다 —
**1) 방송 → 2) 공지(있다면) → 3) 동남부 여행 긍정 이슈 → 4) 그 외**(product_daily/review/qna/book,
`content-schedule.json`의 `fallback_rotation` 배열로 순환). 상위 우선순위 카테고리에 남아있는
만큼 먼저 채우고, 그러고도 슬롯이 남아야 다음 우선순위로 넘어간다. 자세한 내용은 아래
"0. 콘텐츠 스케줄에서 이번 배치(7건) 가져오기" 참고.

## 폴더 구조

- `agents/` — 서브 에이전트 정의 (researcher, writer, image-maker, assembler). `trend-scout`는
  이 프로젝트의 기본 파이프라인에서 별도로 호출하지 않는다 — `southeast_trend` 카테고리는
  trend-scout를 부르는 대신 researcher가 스스로 웹검색해서 주제를 정하는 방식으로 통합했다
  (아래 0단계·`agents/researcher.md`의 "southeast_trend" 절 참고). trend-scout.md는 사용자가
  이 7개 카테고리 밖의 주제를 명시적으로 요청할 때만 예외적으로 쓴다.
- `guides/` — 말투(style-guide.md), SEO/GEO(seo-geo-guide.md) 규칙. 모든 글쓰기·이미지 작업의 기준
- `../products/packages.md` — TIA 실제 여행 상품(가격/일정/포함사항/취소규정). `product_daily` 카테고리의 1차 근거 자료이자, `broadcast`/`southeast_trend` 글에서 TIA 상품 연결 지점을 찾을 때도 확인한다.
- `../products/on-air.md` — 박다애 대표 방송·미디어 출연 정리. `broadcast` 카테고리의 구식(레거시) 1차 근거 자료 — 신규 방식(사용자 제공 스크립트)이 없는 항목에 한해 계속 쓰인다.
- `../products/book.md` — 《이토록아프리카》 도서 소재 정리. `book` 카테고리의 1차 근거 자료.
- `../products/cta/cta.md` + `../products/cta/` 안의 이미지들 — **모든 카테고리 공통** 마무리 CTA
  스펙(전환 문구 로테이션 + 카카오톡 채널 링크 + 랜덤 CTA 이미지). `agents/writer.md` 8번
  단계·`agents/image-maker.md`의 "CTA 이미지" 절 참고.
- `output/topics/content-schedule.json` — `broadcast`/`notice`/`product_daily`/`review`/`book` 5개
  카테고리의 발행 예정 목록 + 우선순위(`priority_tiers`)/순환(`fallback_rotation`) 설정.
  **공지/급한 방송 건, 후기는 여기에 사용자가 직접 항목을 추가한다** (형식은 파일 상단 주석 참고).
  방송(broadcast) 항목은 신규 방식(`raw_content`=받아쓰기 스크립트 + `drive_link`=방송 영상
  구글드라이브 링크)과 구식(`source`=on-air.md 섹션) 두 가지가 섞여 있을 수 있다.
- `output/topics/notion-topics.json` — 노션 Q&A 페이지를 스냅샷으로 저장한 캐시 (매 실행마다 갱신)
- `output/publish-state.json` — 카테고리별로 어떤 주제(id)까지 발행했는지 추적하는 상태 파일
- `output/[주제]/` — 주제별 산출물 (meta.json, research.md, draft.md, images/, final.md, final.html, post.json)
- `scripts/fetch_notion_topics.py` — 노션 Q&A 페이지를 Playwright로 렌더링해 읽어와 notion-topics.json으로 저장
- `scripts/content_schedule.py` — content-schedule.json + notion-topics.json + publish-state.json을
  종합해 **이번 배치(기본 7건)에서 발행할 주제 목록을 우선순위대로** 뽑는 상위 스케줄러.
  `next-batch --count 7`이 기본 명령이고, 단발 실행이 필요하면 `next`(1건)도 남아있다. (구
  `topic_queue.py`는 qna 카테고리 전용 하위 로직으로 그대로 남아있고, `content_schedule.py`가 그
  상위에서 조율한다.)
- `scripts/fetch_daglo_transcript.py` — 다글로(daglo.ai) 공유 링크에서 발화별(`[mm:ss] 화자: 대사`)
  전체 스크립트를 Playwright로 추출해 텍스트 파일로 저장 (다글로 페이지는 JS 가상 스크롤이라
  WebFetch로는 못 읽음). `broadcast` 카테고리 신규 방식에서 사용자가 다글로 링크만 준 경우 사용 —
  `agents/researcher.md`의 "broadcast" 절 참고.
- `scripts/extract_screenshot.py` — 방송 영상(구글 드라이브)에서 타임스탬프 기준으로 스크린샷
  추출 (ffmpeg). `broadcast` 카테고리의 **기본 이미지 소스** — `agents/image-maker.md`의
  "방송 화면 캡처" 절 참고 (더 이상 3가지 중 하나의 옵션이 아니라, broadcast 카테고리의 기본값).
- `scripts/build_post_json.py` — final.md를 네이버 발행용 post.json으로 변환
- `scripts/publish.py` — post.json을 실제 네이버 블로그에 발행 (Playwright)

## 전체 흐름: 사전 점검(로그인) + 0단계(이번 배치 7건 선정) + [7건 반복: 1~4단계(글 생성) + 5단계(발행)]

### 사전 점검: 로그인 세션 확인 (배치 실행 시작 시 딱 한 번)

파이프라인 실행이 시작되면 — 주제를 자동으로 가져오든, 사용자가 주제를 직접 줬든 — **다른 무엇보다 먼저** 로그인 세션부터 확인한다. 이번 배치의 7건을 각각 처리할 때마다 반복하는 게 아니라, **배치 시작 시 한 번만** 확인하면 된다(같은 세션 안에서 세션이 만료될 일은 거의 없다). 리서치~조립(1~4단계)을 다 끝내고 나서야 5단계(발행)에서 로그인이 안 돼 있는 걸 발견해 사용자 개입을 다시 받는 일이 없도록 하기 위함이다.

1. `python scripts/publish.py check-login` 실행.
2. **정상(exit 0)이면** 아무 안내 없이 바로 본 파이프라인(0단계)으로 진행한다.
3. **로그인 안 됨(exit 1)이면** 여기서 멈추고 사용자에게 알린다: "네이버 로그인이 안 되어 있습니다. `python scripts/publish.py capture-session`을 실행해 로그인해주세요." 사용자가 직접 로그인해야 하므로(2단계 인증/기기 등록 포함, 메인 에이전트가 대신 할 수 없음) 사용자가 완료했다고 알려줄 때까지 기다린다.
4. 사용자가 로그인 완료를 알리면 `check-login`으로 다시 한번 확인한 뒤 본 파이프라인을 시작한다.

이 절차를 통과하면 이후 1~5단계는 로그인 관련 사용자 개입 없이 끝까지 진행되는 것이 목표다.

### 0. 콘텐츠 스케줄에서 이번 배치(7건) 가져오기

이 단계는 **배치 전체에 대해 한 번만** 수행한다(7건 각각에 대해 반복하지 않음).

1. **배치를 정하기 전에 `python scripts/content_schedule.py history --limit 15`로 최근 발행 이력을 먼저 훑어본다.** 특히 `book`/`broadcast`처럼 같은 소스를 반복해서 쓰는 카테고리는, 최근에 다룬 인물·에피소드·소제목과 겹치지 않는지 확인한다. 겹치면 리서치/글쓰기 단계에서 그 사실을 언급하고 각도를 다르게 잡는다.
2. **사용자가 이번 실행에서 명시적으로 주제를 지정한 경우**(예: "이번엔 이 주제로 하나 써줘"), 그 주제만 예외적으로 처리하고 이번 배치(0단계)는 건너뛴다 — 스케줄 순서와 무관한 예외적 실행이므로 큐 소비 상태는 건드리지 않는다. 다만 실제 발행이 끝나면 5단계에서 반드시 `content_schedule.py mark-done`을 `--source manual`로 호출해 이력에는 남긴다. 어느 카테고리에 해당하는지 애매하면 사용자에게 7개 카테고리 중 어디인지 먼저 물어본다.
3. 그 외의 기본 실행(사용자가 그냥 "이번 주 콘텐츠 만들어줘" 처럼 특정 주제를 안 준 경우)은 항상 아래 순서를 따른다:
   1. `python scripts/fetch_notion_topics.py` 실행 → 노션 Q&A 페이지 최신 상태를 `output/topics/notion-topics.json`으로 갱신 (qna 차례가 아니어도 캐시는 최신으로 유지해둔다).
   2. **방송(broadcast) 자료 확인**: `content-schedule.json`의 items에 status=pending인 broadcast 항목이 있는지 먼저 본다.
      - 신규 방식 항목(`raw_content`+`drive_link` 있음)이나 구식 항목(on-air.md 참조) 중 pending이 있으면 그대로 사용.
      - **pending이 하나도 없으면, 이번 실행이 로컬 대화형 실행이므로 사용자에게 직접 묻는다**: "이번 주 다룰 방송 자료(받아쓰기 스크립트 + 구글 드라이브 영상 링크) 있으신가요? 없으면 다음 우선순위로 넘어갈게요." 사용자가 자료를 주면 그 자리에서 `content-schedule.json`의 items에 새 항목으로 추가(`id`/`category: "broadcast"`/`title_hint`/`raw_content`/`drive_link`/`status: "pending"`)하고 진행한다. 없다고 하면 이번 배치는 broadcast 슬롯 없이 다음 우선순위로 넘어간다.
      - **사용자가 직접 타이핑한 스크립트 대신 구글드라이브 폴더(영상 + 다글로 공유 링크가 정리된 문서 등)를 통째로 주는 경우도 있다.** 이 경우 메인 에이전트가 폴더/문서 내용을 직접 읽어 다글로 공유 링크와 영상 드라이브 링크를 찾아내고, `raw_content`엔 다글로 링크(또는 문서 요약)만 우선 넣어 항목을 만든다 — 실제 발화별 스크립트 추출(`fetch_daglo_transcript.py`)과 공식 사이트/언론 보도 검색은 1단계(researcher)에서 수행한다(`agents/researcher.md`의 "broadcast" 절 참고). 폴더를 통째로 `gdown --folder`로 받지 않는다 — 폴더 안에 큰 영상 파일이 여러 개 섞여 있으면 디스크를 순식간에 채울 수 있다(2026-07-15 실제로 발생); 먼저 `gdown.download_folder(..., skip_download=True)`로 목록만 확인한 뒤 필요한 파일만 개별적으로 받는다.
   3. **공지(notice) 확인**: 마찬가지로 pending 항목이 있는지 먼저 보고, 없으면 사용자에게 직접 묻는다: "이번 주 공지할 내용(연휴 일정, 설명회 등) 있으신가요?" 사용자가 짧게 텍스트로 주면 그 자리에서 `raw_content`에 그대로 넣어 항목을 추가한다. 없다고 하면 다음 우선순위로 넘어간다.
   4. **`python scripts/content_schedule.py next-batch --count 7` 실행** → 방금 확인/추가한 broadcast/notice 항목까지 반영해서, 우선순위(1.broadcast → 2.notice → 3.southeast_trend → 4.그 외)대로 최대 7개 슬롯을 JSON으로 받는다.
      - **`has_topic: false`로 나오면** 여기서 멈추고 사용자에게 "모든 카테고리의 미발행 주제가 소진됐습니다"라고 보고한다. 임의로 새 주제를 만들어내지 않는다.
      - `filled_count`가 7보다 작아도(예: 남은 주제가 5개뿐) 그 개수만큼만 진행한다 — 억지로 7개를 채우지 않는다.
   5. `slots` 배열의 각 항목이 이번 배치에서 처리할 주제 1개씩이다. `category`가 `southeast_trend`이고 `needs_topic_search: true`인 슬롯은 정적 주제가 없다는 뜻이므로, 아래 "southeast_trend 슬롯 처리" 절대로 처리한다. 그 외 슬롯은 기존과 동일하게 `id`/`title_hint`(또는 qna의 `question`)를 그대로 쓴다.
   6. **`slots` 순서대로 하나씩** 아래 "1~5단계: 글 생성 + 발행"을 반복한다. 한 건이 끝나야 다음 건으로 넘어간다(병렬로 진행하지 않음). 각 건이 끝날 때마다 몇 건째인지(예: "3/7건 완료") 사용자에게 짧게 보고한다.

#### southeast_trend 슬롯 처리

- `needs_topic_search: true`인 슬롯을 만나면, **researcher에게 다음을 명시적으로 지시하며 바로 위임한다** (별도로 trend-scout를 부르지 않음): "오늘 날짜 기준으로 동남부 아프리카(케냐·탄자니아·잠비아·짐바브웨·보츠와나·나미비아·남아공 등) 여행과 관련된 **긍정적인** 최신 이슈/트렌드를 웹검색으로 찾아라(예: 여행지 순위·수상, 관광객 증가 소식, 신규 항공노선 취항처럼 밝은 소식. 범죄·질병·정치 불안 등 부정적 소식은 이 카테고리에서 다루지 않는다). 후보 중 `content_schedule.py history --category southeast_trend`에 없는 새로운 주제 1개를 직접 정하고, 그 제목을 근거로 폴더 슬러그를 정해 `research.md`를 작성해라." (`agents/researcher.md`의 "southeast_trend" 절 참고)
- researcher가 주제(제목)와 폴더 슬러그를 확정해 보고하면, **그때 비로소** 메인 에이전트가 `output/[주제]/meta.json`을 만든다: `{"id": "southeast_trend-YYYY-MM-DD-슬러그", "category": "southeast_trend"}`. (다른 카테고리와 달리 이 카테고리만 리서치 이후에 meta.json을 만든다 — 주제 자체를 리서치 단계에서 정하기 때문.)
- 이후 1~4단계(글쓰기~조립)와 5단계(발행)는 다른 카테고리와 동일하게 진행한다.

### 1~5단계: 글 생성 + 발행 (슬롯 하나 기준, 배치의 각 건마다 반복)

1. **리서치**: `agents/researcher.md`대로 → `output/[주제]/research.md`
   - 슬롯의 `category`에 따라 1차 근거 자료가 다르다 (`product_daily`→packages.md, `broadcast`→사용자 제공 스크립트(신규) 또는 on-air.md(구식), `book`→book.md, `qna`→노션 answer/packages.md, `southeast_trend`→실시간 웹검색). 자세한 내용은 `agents/researcher.md`의 "카테고리별 입력 처리" 절 참고.
   - `southeast_trend`가 아닌 슬롯은 **메인 에이전트가 리서치 시작 전에 `output/[주제]/meta.json`을 직접 만든다** (서브 에이전트에게 위임하지 않음): `{"id": "...", "category": "product_daily|review|broadcast|notice|qna|book"}`. 5단계에서 `build_post_json.py`가 이 파일을 읽어 네이버 카테고리를 자동으로 정한다 — 빼먹으면 기본값("아프리카 여행 정보")으로 발행돼버리므로 반드시 만든다. (`southeast_trend`는 위 "southeast_trend 슬롯 처리" 절대로 리서치 이후에 만든다.)
2. **글쓰기**: `agents/writer.md`대로 → `output/[주제]/draft.md`
   - `category`가 `broadcast`이고 research.md에 TIA 상품(packages.md)과 겹치는 지점이 확인됐다면, **반드시** 해당 상품을 본문(특히 CTA/FAQ)에 언급한다 — 선택이 아니라 필수다.
3. **이미지**: `agents/image-maker.md`대로 → draft.md의 `[[IMAGE: ...]]` 마커를 실제 이미지 경로로 치환, `output/[주제]/images/`
   - `category`가 `broadcast`면 **기본적으로 방송 스크린샷을 이미지 소스로 사용한다** (GPT 생성은 스크린샷 확보가 정말 안 될 때만의 예외). 자세한 내용은 `agents/image-maker.md`의 "방송 화면 캡처" 절 참고.
4. **조립**: `agents/assembler.md`대로 → `output/[주제]/final.md`, `output/[주제]/final.html`
5. **발행 — 임시저장 없이, 배치 전체를 한 번에 하루 하나씩 예약 발행 (2026-07-16 개편)**:
   기존에는 `--draft`로 먼저 저장해 건별로 사용자 승인을 받은 뒤에만 실제 발행/예약으로
   전환했지만, 지금은 **배치를 한 번 돌리면 슬롯마다 확인 없이 곧바로 예약 발행까지
   끝낸다.** 슬롯 하나가 끝날 때마다 다음을 순서대로 실행한다 (블로그 ID는 항상
   `this_africa` 고정):
   1. **이번 슬롯에 쓸 예약 날짜를 정한다(2026-08-01 확정 — 빈 날짜 우선 채우기)**:
      배치 시작 시 한 번만 `python scripts/publish.py list-scheduled --blog-id this_africa
      --headed --json`을 실행해 현재 네이버에 이미 예약된 글들의 날짜를 전부 확인한다.
      **내일부터 시작해서, 이미 예약된 날짜들 사이에 비어 있는 날짜가 있으면 그 날짜부터
      우선 채운다** — 예를 들어 8/8·8/10·8/12에 이미 예약이 있고 8/9·8/11이 비어 있다면,
      다음 신규 슬롯은 가장 늦은 날짜(8/12) 다음날이 아니라 **8/9**부터 채운다. 사이에
      비어 있는 날짜가 하나도 없으면(예약 목록이 연속된 경우) 그때 비로소 가장 늦은
      날짜의 다음날부터 시작한다. 이후 슬롯마다 이렇게 채운 빈 날짜들을 순서대로 소비하고,
      빈 날짜를 다 채웠는데도 슬롯이 남으면 그다음부터는 가장 늦은 날짜 다음날부터 하루씩
      늘려간다(시간은 항상 09:00 고정 — 이미 있던 관례를 그대로 따름). 이렇게 하면
      이미 예약돼 있는 글과 겹치지 않으면서도 발행 간격이 들쭉날쭉해지지 않는다.
   2. 다음 두 명령을 실행한다:
      ```
      python scripts/build_post_json.py --topic-dir "output/[주제]"
      python scripts/publish.py publish --post-json "output/[주제]/post.json" --blog-id this_africa --visibility public --publish-at "<이번 슬롯의 예약일> 09:00" --headed
      ```
      `--draft`는 쓰지 않는다 — 임시저장 없이 바로 예약 발행으로 끝낸다. `--visibility`도
      항상 `public`(전체공개)로 고정한다(예약 발행인데 비공개로 걸면 아무도 못 보는
      상태로 공개되는 실수가 될 수 있으니 반드시 `public`).
   - 로그인은 파이프라인 맨 앞의 "사전 점검"에서 이미 확인됐어야 한다. 그런데도 여기서 로그인 관련 에러(로그인 페이지로 리다이렉트 등)가 나면, 그 사이 세션이 만료된 것이므로 실행을 멈추고 사용자에게 `capture-session` 재실행을 안내한다 (자동화 불가 — 메인 에이전트가 대신 로그인할 수 없다). 네이버 봇 탐지를 피하기 위해 이 스크립트는 번들 Chromium이 아니라 실제 설치된 Chrome(`channel="chrome"`)을 persistent profile로 띄운다.
   - `scripts/publish.py`의 `SELECTORS`는 2026-07-08 **now_eoding** 계정 기준으로 실제 값이 채워져 end-to-end로 검증된 값이다. TIA는 다른 네이버 계정(`this_africa`)이므로 SmartEditor ONE의 해시 클래스가 계정마다 다를 가능성이 있다 — **어느 단계에서든 타임아웃/에러가 나면 그 시점에 실행을 멈추고 사용자에게 셀렉터 재확인이 필요하다고 보고한다** (`TODO: verify`로 되돌아간 게 아니라 값 자체가 깨진 것이므로 에러 메시지로 판단). 이렇게 실행을 멈춘 경우에는 그 슬롯을 건너뛰지 말고, 문제를 해결한 뒤 그 슬롯부터 다시 이어서 진행한다.
   - 네이버 UI가 예약 시간의 분을 10분 단위(00/10/20/30/40/50)로만 받아서 스크립트가 자동으로 내림 처리한다. 예약된 글은 네이버 글쓰기 화면 상단 "예약 발행 N건"에서 확인·취소할 수 있다(취소는 `cancel-scheduled` 서브커맨드).
   - **예약 발행이 끝난 직후(임시저장이 아니라 실제로 예약까지 걸린 직후)**, 스케줄로 받은 주제든 사용자가 직접 지정한 주제든 예외 없이 다음을 실행해 상태/이력을 갱신한다:
     ```
     python scripts/content_schedule.py mark-done --category "<category>" --id "<id>" --title "<발행된 글 제목>" --topic-dir "output/[주제]" --source "<schedule 또는 manual>" --keywords "<핵심 키워드1,핵심 키워드2>"
     ```
     - 0단계에서 스케줄로 받은 주제라면 `--source schedule`, `<category>`/`<id>`는 0단계에서 받은 값 그대로 (`southeast_trend`도 `--source schedule`, `<id>`는 리서치 단계에서 정한 슬러그).
     - 사용자가 직접 지정한 주제라면 `--source manual`, `<category>`는 사용자에게 확인받은 카테고리, `<id>`는 새로 만든 알아보기 쉬운 슬러그(예: `review-정모-킬리만자로-2026-07`).
     - `--keywords`는 **`southeast_trend`일 때 반드시 채운다**(리서치 단계에서 researcher가 보고한 핵심 키워드 그대로) — 이 카테고리는 정적 항목이 없어서 안 채우면 30일 재사용 금지 검사가 아예 적용되지 않는다. 그 외 카테고리는 생략해도 된다 — qna는 notion 캐시에서, product_daily/broadcast/book/review/notice는 해당 항목에 `keywords` 필드가 있으면 content-schedule.json에서 자동으로 찾아 채운다(없으면 검사 미적용, 에러 아님).
     - 이걸 빼먹으면 스케줄 주제는 다음 실행에서 중복으로 다시 나오고, 수기 주제는 이력에서 누락돼 다음에 같은 소재를 또 고를 위험이 커진다.
   - **같은 핵심 키워드는 30일 안에 재사용하지 않는다(자동).** `next-batch`/`next`가 후보를 고를 때 이미 이 검사를 거쳐 충돌하는 항목은 자동으로 건너뛰므로(자세한 내용은 `scripts/content_schedule.py` 상단 문서 참고), 메인 에이전트가 별도로 더 확인할 필요는 없다 — 다만 위 `mark-done`에 `--keywords`를 빠뜨리지 않아야 다음 실행에서 이 검사가 제대로 작동한다.

각 건(슬롯)이 끝날 때마다 결과를 짧게 보고하고("N/7건 완료: [제목] — YYYY-MM-DD 09:00 예약") 다음 슬롯으로 넘어갈 것. 배치 전체가 끝나면 최종적으로 몇 건을 예약했는지, 어떤 날짜들인지 요약 보고한다.

## 메인 에이전트(오케스트레이터) 규칙

- **직접 리서치하거나 글을 쓰지 않는다.** 반드시 해당 단계의 서브 에이전트에게 위임한다. (`southeast_trend`의 주제 탐색도 메인 에이전트가 직접 웹검색하지 않고 researcher에게 위임한다.)
- 메인의 역할은 배치 계획(0단계), 슬롯별 단계 순서 관리, 입출력 경로 확인, 사용자 보고뿐이다.
- **0단계(콘텐츠 스케줄)는 trend-scout처럼 서브 에이전트에게 위임하는 게 아니라, `fetch_notion_topics.py` / `content_schedule.py` 스크립트를 직접 실행하는 것이다.** 이 프로젝트는 주제가 이미 7개 카테고리로 한정돼 있어 별도로 트렌드를 조사할 필요가 없다 — `southeast_trend`만 예외적으로 researcher가 웹검색으로 주제 자체를 정한다(위 "southeast_trend 슬롯 처리" 참고).
- **사용자가 이번 실행에서 명시적으로 주제를 준 경우에만** 0단계(배치 선정)를 건너뛰고 바로 1단계(researcher)로 위임한다. 그 외에는 항상 `next-batch`로 이번 배치를 자동으로 가져온다.
- **broadcast/notice 슬롯을 채우기 전, `content-schedule.json`에 pending 항목이 없으면 사용자에게 이번 주 자료(방송 스크립트+영상 / 공지 내용)가 있는지 먼저 물어본다.** 로컬 대화형 실행이므로 이 확인이 가능하고, 물어보지 않고 임의로 건너뛰거나 지어내지 않는다.
- **5단계(발행)는 서브 에이전트가 아니라 스크립트 실행이다. 2026-07-16부터 임시저장(`--draft`)/건별 승인 단계 없이, 배치를 한 번 돌리면 슬롯마다 곧바로 예약 발행까지 끝낸다** (`--visibility public` + `--publish-at`, 하루 한 건씩 순서대로). 배치 시작 시 `list-scheduled --json`으로 다음 예약 가능 날짜를 한 번 계산해두고 슬롯마다 하루씩 늘려간다.
- **예약 발행이 끝난 직후 `content_schedule.py mark-done`을 실행하는 것을 잊지 않는다 — 스케줄 주제든 사용자가 직접 지정한 주제든 예외 없이 호출한다** (`--source`만 각각 `schedule`/`manual`로 다르게). 스케줄 주제에서 이걸 놓치면 다음 실행에서 같은 주제가 중복으로 나오고, 수기 주제에서 놓치면 발행 이력에서 누락돼 다음에 같은 소재를 또 고를 수 있다.
- **같은 핵심 키워드는 30일 안에 재사용하지 않는다.** `next-batch`/`next`가 이미 자동으로 걸러주므로 별도 확인은 필요 없지만, `southeast_trend`는 정적 항목이 없어 이 규칙이 오직 `mark-done --keywords`로 기록한 값에만 의존한다 — **`southeast_trend` 발행 후 `--keywords`를 빠뜨리면 다음 실행부터 이 카테고리의 중복 방지가 무력화된다.**
- **새 배치를 정하기 전에는 `content_schedule.py history`로 최근 발행 이력을 먼저 확인한다.** 특히 book/broadcast처럼 소스가 겹치기 쉬운 카테고리나 southeast_trend에서 같은 인물·에피소드·이슈를 반복하지 않기 위함이다.
- **broadcast 콘텐츠에서 research.md에 TIA 상품과 겹치는 지점이 확인되면, writer 단계에 반드시 그 상품을 언급하도록 지시한다.** 선택 사항이 아니다.
- **broadcast 콘텐츠의 이미지는 기본적으로 방송 스크린샷이다.** image-maker에게 GPT 생성을 기본값으로 지시하지 않는다 — 스크린샷 확보가 정말 안 될 때만의 예외다.
- **사전 점검(로그인)을 건너뛰지 않는다.** 배치 시작 전, 0단계를 시작하기 전에 반드시 `check-login`을 먼저 실행한다. 로그인이 안 돼 있는데 이를 무시하고 리서치부터 진행하면, 다 끝난 뒤 5단계에서야 막혀 사용자 개입을 다시 받아야 하므로 이 순서를 지키는 것이 중요하다.
