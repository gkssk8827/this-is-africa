# 파이프라인 테스트 (Mock 데이터 기반)

CLAUDE.md의 0~5단계 파이프라인이 실제로 잘 동작하는지, **실제 LLM 호출/실제 네이버
계정 없이** mock 데이터로 검증하는 테스트 모음입니다.

## 왜 두 종류의 테스트가 섞여 있나

파이프라인의 단계별 성격이 다르기 때문에 테스트 방식도 다릅니다.

| 단계 | 실체 | 테스트 방식 |
|---|---|---|
| 0. trend-scout | LLM 서브 에이전트 | 테스트 대상 아님 (주제 발굴은 품질 판단이 필요해 코드 테스트 불가) |
| 1. researcher | LLM 서브 에이전트 | **계약 테스트** — agents/researcher.md가 약속한 산출물 구조(제목/메타데이터/개요/참고소스 5개 이상)를 mock research.md로 검증 |
| 2. writer | LLM 서브 에이전트 | **계약 테스트** — agents/writer.md 체크리스트 중 구조적으로 확인 가능한 항목(제목 길이, 인사말 금지, 이미지 마커, FAQ, 요약박스, CTA, 해시태그)을 mock draft.md로 검증 |
| 3. image-maker | LLM 서브 에이전트 | **계약 테스트** — draft.md의 `[[IMAGE: ...]]` 마커가 전부 실제 이미지로 치환되고, 마커 외 내용은 그대로이며, 참조 이미지가 실제로 존재하는지 mock 전/후 픽스처로 검증 |
| 4. assembler | LLM 서브 에이전트 (창작 없이 조립만 함) | **계약 테스트** — final.md가 draft.md와 동일한지, final.html이 self-contained인지, 제목/소제목/표/이미지가 올바르게 변환됐는지 검증 |
| 5. build_post_json.py | 순수 Python 코드 | **실제 단위 테스트(pytest)** — 실제 함수를 mock final.md에 대해 직접 실행 |
| 5. publish.py (에디터 조작) | Python + Playwright | **실제 통합 테스트** — 실제 네이버 대신 `fixtures/mock_editor_*.html`(SmartEditor 실제 클래스명을 그대로 흉내낸 mock DOM)에 대고 publish.py의 실제 함수(fill_title, fill_body_blocks, set_category, set_tags, set_visibility, click_final_publish 등)를 그대로 실행 |
| 5. publish.py (로그인 게이트) | Python + Playwright | **실제 단위/통합 테스트** — `is_logged_in`/`_has_valid_login_cookies`는 가짜 쿠키를 주입해 순수 로직 검증, `publish_post()`는 로그인 안 된(빈) 임시 프로필로 호출해 `open_write_page()` 호출 전에 확실히 멈추는지(SystemExit) 검증 |

**중요한 한계**: 1~4단계는 LLM이 실제로 좋은 글/이미지를 만드는지(창의성·정확성)는
코드로 테스트할 수 없습니다. 여기서 확인하는 건 "산출물이 다음 단계가 기대하는
파일 구조·형식을 지키는가"까지입니다. 반대로 5단계(build_post_json.py, publish.py)는
순수 코드/DOM 조작이라 진짜 함수 단위 테스트가 가능하고, 실제로 실행됩니다.

## 폴더 구조

```
test/
  README.md                          (이 파일)
  conftest.py                        (scripts/를 import 경로에 추가)
  fixtures/
    research_sample.md               (1단계 mock 산출물)
    topic_sample/
      draft_before_images.md         (2단계 mock 산출물 — [[IMAGE: ...]] 마커 있음)
      draft.md                       (3단계 mock 산출물 — 마커가 이미지로 치환됨)
      final.md                       (4단계 mock 산출물)
      final.html                     (4단계 mock 산출물)
      images/
        cover.png, image-01.png      (1x1 더미 PNG)
        image-map.md
    mock_editor_outer.html           (5단계 publish.py 테스트용 — iframe#mainFrame 포함)
    mock_editor_inner.html           (네이버 SmartEditor 실제 클래스명을 흉내낸 mock 에디터)
  test_stage1_research_contract.py
  test_stage2_writer_contract.py
  test_stage3_imagemaker_contract.py
  test_stage4_assembler_contract.py
  test_stage5_build_post_json.py
  test_stage5_publish_mock.py
  test_stage5_login_guard.py           (로그인 세션 확인/게이트 로직 — CLAUDE.md "사전 점검" 요구사항의 코드적 뒷받침)
```

## 실행 방법

```bash
cd blog
pip install pytest   # 최초 1회
python -m pytest test/ -v
```

특정 단계만 실행:

```bash
python -m pytest test/test_stage5_publish_mock.py -v
```

## mock_editor_inner.html이 하는 일

`scripts/publish.py`가 실제로 클릭/타이핑하는 대상은 네이버 SmartEditor ONE의
실제 DOM(해시 클래스명 포함, 예: `button.publish_btn__m9KHH`, `label.radio_label__mB6ia`)
입니다. `mock_editor_inner.html`은 2026-07-08에 실제 계정(now_eoding)에서 직접
확인한 구조를 그대로 재현한 정적 HTML이라, `publish.py`의 SELECTORS 값이 실제와
어긋나면(예: 네이버가 클래스명을 바꾸면) 이 mock에서는 통과하지만 실제 발행에서는
실패할 수 있습니다. **반대로 우리가 publish.py 로직 자체를 잘못 고치면(순서 실수,
부분 일치 vs 정확 일치 버그 등) 이 mock 테스트가 실제 네이버 없이도 바로 잡아냅니다.**

실제로 이 테스트들은 아래 두 회귀를 정확히 잡아내도록 설계되어 있습니다
(둘 다 실제 발행 테스트 중 만났던 버그입니다):

- `test_visibility_neighbor_does_not_match_both_neighbor` — "이웃공개"가 "서로이웃공개"의
  부분 문자열이라 부분 일치로 찾으면 잘못된 라디오가 선택되는 버그
- `test_category_exact_match_does_not_pick_similar_name` — 카테고리명이 서로 부분
  문자열 관계일 때(예: "아프리카 여행 정보" vs "여행 정보") 잘못 선택되는 버그

## 네이버가 SmartEditor 구조를 바꿨을 때

1. `python scripts/publish.py capture-session` 로 로그인 후, 글쓰기 화면에서
   Playwright로 직접 DOM을 열어 바뀐 클래스명을 확인합니다.
2. `scripts/publish.py`의 `SELECTORS`를 새 값으로 갱신합니다.
3. `test/fixtures/mock_editor_inner.html`도 실제 구조에 맞게 같이 갱신합니다
   (그래야 mock 테스트가 새 구조를 계속 검증해줍니다).
4. `python -m pytest test/test_stage5_publish_mock.py -v`로 회귀 확인 후,
   실제 계정에 `--draft --visibility private --headed`로 최종 확인합니다.

## 새 주제로 fixtures를 갱신하고 싶을 때

`fixtures/topic_sample/`은 임의로 지어낸 mock 콘텐츠입니다. 실제 파이프라인 산출물로
바꿔서 테스트하고 싶다면, 실제 `output/[주제]/` 폴더의 draft.md/final.md/
final.html/images를 복사해 `fixtures/topic_sample/`에 덮어쓰면 됩니다 (단,
`test_stage3_imagemaker_contract.py`가 기대하는 `draft_before_images.md`도 함께
준비해야 3단계 계약 테스트가 통과합니다).
