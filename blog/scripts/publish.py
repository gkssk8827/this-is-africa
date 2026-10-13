"""
publish_naver.py
================
네이버 블로그 자동 발행 스크립트 (Playwright, Python)

블로그 파이프라인: trend-scout -> researcher -> writer -> image-maker -> assembler -> [publisher]
이 스크립트는 assembler 가 만든 최종 포스트 데이터(JSON)를 받아 네이버 블로그 SmartEditor ONE에
제목/본문/이미지/카테고리/태그/공개범위를 채우고 발행(또는 임시저장)까지 수행합니다.

⚠️ 중요 — 셀렉터에 대한 주의사항
네이버 SmartEditor ONE은 리액트 기반이라 class 이름 상당수가 해시(예: publish_btn__m9KHH)로
난독화되어 있고 주기적으로 바뀝니다. 아래 SELECTORS 안에 "# TODO: verify" 라고 표시된 항목은
반드시 본인 계정으로 직접 확인해야 합니다. 확인 방법은 하단 "셀렉터 확인 방법" 참고.

사용 예시
---------
1) 로그인 세션 저장 (최초 1회, 사람이 직접 로그인):
   python scripts/publish_naver.py capture-session

2) 포스트 발행 (임시저장/비공개 먼저 테스트):
   python scripts/publish_naver.py publish \
       --post-json output/final_post.json \
       --blog-id yourblogid \
       --visibility private \
       --headed

post-json 파일 형식 (build_post_json.py 출력 규격):
{
  "title": "포스트 제목",
  "body_blocks": [
    {"type": "heading", "level": 2, "content": "소제목"},
    {"type": "text", "content": "본문 문단 1"},
    {"type": "image", "path": "images/photo1.jpg"},
    {"type": "table", "rows": [["구분", "이전", "이후"], ["A", "100", "150"]]},
    {"type": "quote", "content": "핵심만 보기\n\n요약 문장 1\n요약 문장 2"},
    {"type": "text", "content": "본문 문단 2"}
  ],
  "category": "여행팁",
  "tags": ["아프리카여행", "케냐사파리", "디스이즈아프리카"],
  "drive_image_urls": []   // 구글 드라이브 이미지가 있으면 여기에 공유 링크 목록
}
"""

from __future__ import annotations

import argparse
import json
import random
import re
import sys
import time
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

# ---------------------------------------------------------------------------
# 경로 설정
# ---------------------------------------------------------------------------
ROOT_DIR = Path(__file__).resolve().parent.parent
PROFILE_DIR = ROOT_DIR / "naver_profile"
SCREENSHOT_DIR = ROOT_DIR / "logs" / "screenshots"
TMP_IMAGE_DIR = ROOT_DIR / "logs" / "tmp_images"

# 번들 Chromium은 네이버 로그인 봇 탐지(반복 캡차/로그인 루프)에 자주 걸린다.
# 실제 설치된 Chrome(channel="chrome")을 persistent profile로 띄우면 fingerprint가
# 실사용 브라우저와 거의 같아져서 탐지를 크게 줄일 수 있다. 로그인 상태는
# storage_state 파일이 아니라 이 프로필 디렉터리 자체에 계속 저장된다.
LAUNCH_KWARGS = dict(
    channel="chrome",
    args=[
        "--disable-blink-features=AutomationControlled",
        "--no-sandbox",
        "--disable-dev-shm-usage",
    ],
)

NAVER_LOGIN_URL = "https://nid.naver.com/nidlogin.login"
NAVER_BLOG_HOME = "https://blog.naver.com"

# ---------------------------------------------------------------------------
# 브라우저 컨텍스트 오픈 — 로컬(영구 프로필) vs CI(storage_state) 두 가지 모드
# ---------------------------------------------------------------------------
# 로컬 기본값: naver_profile 디렉터리에 로그인 상태가 통째로 저장된 영구 프로필을
#   그대로 재사용한다 (capture-session으로 사람이 최초 1회 로그인).
# CI(GitHub Actions 등) 모드: 무인 환경에는 naver_profile(39MB, 캐시 포함)을 통째로
#   옮기기 어렵고 보안상 바람직하지도 않다. 대신 로그인 쿠키만 담은 작은 JSON
#   파일(storage_state)을 GitHub Secret으로 주입해, 매 실행마다 새 브라우저에
#   그 쿠키만 불러와 로그인 상태를 재현한다.
#   storage_state 파일은 `capture-session --export-storage-state PATH`로 로컬에서
#   미리 뽑아둔다. 자세한 CI 설정은 CI_SETUP.md 참고.
@contextmanager
def open_context(p, headed: bool, storage_state: str | None = None):
    if storage_state:
        browser = p.chromium.launch(headless=not headed, **LAUNCH_KWARGS)
        context = browser.new_context(storage_state=storage_state)
        try:
            yield context
        finally:
            context.close()
            browser.close()
    else:
        PROFILE_DIR.mkdir(parents=True, exist_ok=True)
        context = p.chromium.launch_persistent_context(
            str(PROFILE_DIR), headless=not headed, **LAUNCH_KWARGS
        )
        try:
            yield context
        finally:
            context.close()

# ---------------------------------------------------------------------------
# 셀렉터 (SmartEditor ONE 기준, 2026-07-08 now_eoding 계정에서 직접 확인한 값)
# 네이버가 해시 클래스명을 주기적으로 바꾸므로, 발행이 갑자기 안 되면 이 값들부터
# scripts/inspect_editor*.py류 스크립트로 다시 확인할 것.
# ---------------------------------------------------------------------------
SELECTORS = {
    # 안정적으로 유지되는 편 (iframe/구조 관련)
    "main_iframe": "iframe#mainFrame",
    # "작성 중인 글이 있습니다" 팝업 - 취소(새 글 시작)
    "continue_popup_cancel": "button.se-popup-button-cancel",
    # 도움말 패널 닫기
    "help_panel_close": "button.se-help-panel-close-button",
    # 제목 입력 영역 (첫 클릭 후 타이핑)
    "title_area": ".se-documentTitle .se-text-paragraph",
    # 본문 첫 문단 영역 — 새 글에서는 .se-text-paragraph가 제목(0번)과
    # 본문 첫 문단(1번) 두 개만 존재한다 (예전 .se-main-container 래퍼는
    # 더 이상 없음). 그래서 컨테이너로 스코프하지 않고 순번(1번)으로 찾는다.
    "body_area": ".se-text-paragraph",
    # 사진 첨부 툴바 버튼 (좌측 상단 고정 툴바)
    "image_toolbar_button": "button.se-image-toolbar-button",
    # 삽입된 이미지 요소 (선택/클릭 대상)
    "image_resource": ".se-image-resource",
    # 이미지 선택 시 나타나는 속성 툴바의 "링크" 버튼 — 2026-07-15 this_africa 계정에서 확인
    "image_link_button": 'button.se-link-toolbar-button[data-name="image-link"]',
    "image_link_input": "input.se-custom-layer-link-input",
    "image_link_apply_button": "button.se-custom-layer-link-apply-button",
    # 표 삽입 툴바 버튼 (클릭하면 기본 3행 3열 표가 바로 삽입됨) — 2026-07-09 now_eoding 계정에서 확인
    "table_toolbar_button": "button.se-table-toolbar-button",
    # 표의 행/열 끝에 나타나는 "N행/N열 다음에 추가" 버튼 — 텍스트로 "열 추가"/"행 추가"를
    # 구분해 매칭하고, 매번 마지막(가장 끝) 버튼을 클릭해 표 크기를 한 칸씩 확장한다.
    "table_add_cell_button": "button.se-cell-add-button",
    # 삽입된 표 자체(셀 채우기 대상 스코프를 좁히는 데 사용)
    "table_element": "table.se-table-content",
    "table_cell_paragraph": "td.se-cell .se-text-paragraph",
    # 표를 벗어나 본문 맨 아래에 새 문단을 만드는 버튼
    "canvas_bottom_button": "button.se-canvas-bottom-button",
    # 상단 고정 서식 툴바의 굵게(B) 버튼 — 선택 없이(커서만 있는 상태) 클릭해도
    # 이후 타이핑되는 글자에 굵게가 적용되는 "타이핑 상태 토글"로 동작함을 확인함
    # (2026-07-09 now_eoding 계정, 스크린샷으로 검증). **굵게** 마커를 인라인으로
    # 렌더링하는 데 사용한다.
    "bold_toolbar_button": 'button.se-bold-toolbar-button[data-group="propertyToolbar"]',
    # 인용구 삽입 버튼 (클릭하면 기본 스타일 "인용구1"이 바로 삽입됨)
    "quotation_insert_button": "button.se-insert-quotation-default-toolbar-button",
    # 삽입된 인용구를 세로선 스타일("인용구2")로 바꾸는 버튼 — 소제목을 이 스타일로
    # 표시해 본문과 시각적으로 구분한다 (2026-07-09 now_eoding 계정에서 확인)
    "quotation_style2_button": "button.se-quotation-quotation_line-toolbar-button",

    # ⚠️ 아래는 네이버가 자주 바꾸는 해시 클래스라 주기적 재확인 필요
    "category_selectbox": "button.selectbox_button__IxraO",      # 카테고리 드롭다운 버튼 (발행 팝업 안)
    "category_option_tpl": "div.option_category__mNwDi label",  # 카테고리 리스트 항목 (for 속성 접미사로 매칭, 텍스트 매칭은 스크롤 밖 항목에서 불안정)
    "tag_input": "input#tag-input",             # 태그 입력창
    "tag_chip": "span.tag__ME42L",              # 태그 입력 후 생성되는 칩(chip) 요소 (태그 편집 박스 안, 실제 등록 여부 검증용)
    "publish_open_button": "button.publish_btn__v_kS9",  # 우측 상단 "발행" 버튼 (팝업 여는 버튼)
    "visibility_radio_tpl": "label.radio_label__zTXH0",  # 공개범위 라디오 라벨 (전체공개/이웃공개/서로이웃공개/비공개, 텍스트로 매칭)
    "final_publish_button": "button.confirm_btn__byZZW[data-testid='seOnePublishBtn']",  # 발행 팝업 내부 최종 "발행" 버튼
    "save_draft_button": "button.save_btn__FuUyN",  # 상단 툴바 "저장"(임시저장) 버튼

    # 예약 발행 (2026-09-12 this_africa 계정에서 재확인 — 해시 클래스가 바뀌어 있었음) — "발행 시간" 라디오는
    # visibility_radio_tpl과 같은 class(radio_label__zTXH0)를 공유하므로 재사용한다.
    "schedule_date_input": "input.input_date__UwKAB",  # 날짜 표시 입력창(readonly, 클릭하면 달력 열림)
    "schedule_hour_select": "select.hour_option__Vk2eR",   # 시(0~23) select
    "schedule_minute_select": "select.minute_option__ETsdF",  # 분(00/10/20/30/40/50만 가능) select
    # jQuery UI 데이트피커 — 네이버가 직접 만든 커스텀 UI가 아니라 표준 jQuery UI 위젯이라
    # 셀렉터가 다른 부분보다 안정적일 가능성이 높음.
    "datepicker_title": ".ui-datepicker-title",
    "datepicker_next_month": "button.ui-datepicker-next",
    "datepicker_prev_month": "button.ui-datepicker-prev",
    "datepicker_day_button": "td:not(.ui-state-disabled) > button.ui-state-default",

    # 예약 발행 글 관리 (2026-09-12 재확인 — 해시 클래스가 바뀌어 있었음)
    # 이 버튼을 감싸는 reserve_btn_area 는 예약 건수가 0건이면 CSS로 display:none 처리돼
    # 있어(2026-09-12 실제로 확인 — 클릭 시도 시 "element is not visible"로 타임아웃난다),
    # 클릭 전에 반드시 reserved_count_badge 텍스트로 건수부터 확인해야 한다.
    "reserved_list_open_button": "button.reserve_btn__Yc1V8",  # 상단 "예약 발행 N건" 버튼
    "reserved_count_badge": "strong.num__yCxe6",  # "예약 발행 N건" 버튼 안의 숫자(N) — display:none이어도 text_content()로 읽힘
    "reserved_list_item": "li.item__k1QHQ",  # 예약 목록의 각 항목 (호버해야 삭제 버튼이 보임) — 2026-09-12 재확인
    "reserved_delete_button": "#post_delete_button",

    # 이미지 삽입 시 자동으로 열리는 우측 사이드바("라이브러리" 등, aside.se-sidebar) 닫기 버튼.
    # 이 사이드바가 열린 채로 있으면 표의 오른쪽 끝(4열 이상일 때 "열 추가" 버튼 등)과 겹쳐
    # 클릭이 가로막히는 문제가 있어(2026-07-22 this_africa 계정에서 확인), 표 삽입 전에 닫는다.
    "sidebar_close_button": "button.se-sidebar-close-button",
}


def log(msg: str):
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] {msg}")


def human_delay(a=0.6, b=1.8):
    """사람처럼 보이도록 랜덤 지연."""
    time.sleep(random.uniform(a, b))


def take_failure_screenshot(page, label: str):
    SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = SCREENSHOT_DIR / f"{label}_{ts}.png"
    try:
        page.screenshot(path=str(path), full_page=True)
        log(f"실패 스크린샷 저장: {path}")
    except Exception as e:
        log(f"스크린샷 저장 실패: {e}")


# ---------------------------------------------------------------------------
# 0) 로그인 상태 확인 — capture-session/publish 양쪽에서 공용으로 쓰는 검증 절차
# ---------------------------------------------------------------------------
def _has_valid_login_cookies(cookies: list) -> bool:
    """쿠키 목록만 보고 로그인 여부를 판단하는 순수 로직 (테스트하기 쉽게 분리)."""
    names = {c["name"] for c in cookies}
    return "NID_AUT" in names and "NID_SES" in names


def is_logged_in(context) -> bool:
    """
    현재 context(=naver_profile)가 실제로 네이버에 로그인된 상태인지 쿠키로 확인한다.
    페이지 이동 없이 즉시 확인 가능 (persistent profile의 쿠키 저장소를 바로 조회).
    """
    cookies = context.cookies("https://www.naver.com")
    return _has_valid_login_cookies(cookies)


def check_login(headed: bool = False, storage_state: str | None = None) -> bool:
    """
    capture-session/publish와는 별개로, "지금 로그인이 유효한가"만 빠르게 확인하는 절차.
    publish 실행 전에 미리 점검하거나, capture-session 직후 확인 용도로 쓴다.

    storage_state가 주어지면(CI 모드) naver_profile 대신 그 쿠키 파일로 확인한다.
    """
    if not storage_state and not PROFILE_DIR.exists():
        log(f"로그인 프로필이 없습니다: {PROFILE_DIR}. 먼저 capture-session을 실행하세요.")
        return False
    if storage_state and not Path(storage_state).exists():
        log(f"storage_state 파일이 없습니다: {storage_state}")
        return False

    with sync_playwright() as p:
        with open_context(p, headed=headed, storage_state=storage_state) as context:
            logged_in = is_logged_in(context)
            if logged_in:
                log("로그인 상태 확인: 정상 (NID_AUT/NID_SES 쿠키 존재)")
            else:
                log("로그인 상태 확인: 로그인 안 되어 있거나 세션이 만료됐습니다. "
                    "capture-session을 다시 실행하세요(CI라면 storage_state를 새로 발급해 Secret을 갱신하세요).")
            return logged_in


# ---------------------------------------------------------------------------
# 1) 세션 캡처 모드 — 사람이 직접 로그인 후 storage_state 저장
# ---------------------------------------------------------------------------
def capture_session(timeout_sec: int = 300, export_storage_state: str | None = None):
    """
    브라우저를 띄우고 사람이 직접 로그인하기를 기다린다.
    터미널 input()으로 Enter를 기다리는 대신, 로그인 완료 시 네이버가
    nid.naver.com/nidlogin.login 밖으로 리다이렉트되는 것을 감지해 자동으로
    세션을 저장한다 (자동화 환경에서 stdin으로 Enter를 받을 수 없기 때문).

    export_storage_state가 주어지면, 로그인 성공 직후 쿠키를 그 경로에 JSON으로도
    내보낸다. 이 파일을 GitHub Secret(예: NAVER_STORAGE_STATE)에 base64로 등록해두면
    CI(무인 환경)에서 naver_profile 없이도 로그인 상태를 재현할 수 있다.
    ⚠️ 로그인 쿠키가 그대로 담긴 민감한 파일이다 — 절대 git에 커밋하지 말 것
    (2단계 인증을 우회할 수 있는 자격 증명과 동급으로 취급).
    """
    log(f"브라우저를 엽니다. 뜬 창에서 네이버에 직접 로그인해주세요 (2단계 인증/기기 등록 포함, 최대 {timeout_sec}초 대기).")
    PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            str(PROFILE_DIR), headless=False, **LAUNCH_KWARGS
        )
        page = context.pages[0] if context.pages else context.new_page()
        page.goto(NAVER_LOGIN_URL)

        # nid.naver.com 안에서는 로그인/2단계 인증/기기 등록 등 여러 중간 페이지를
        # 거칠 수 있고, 그 중 일부(기기 등록 확인 등)는 새 탭/팝업으로 뜨기도 한다.
        # 그래서 원래 page 하나만 보지 않고, context 안의 모든 탭을 감시해서
        # 그 중 하나라도 호스트가 nid.naver.com을 벗어났는지로 로그인 완료를 판단한다.
        deadline = time.time() + timeout_sec
        logged_in = False
        last_urls: set[str] = set()
        while time.time() < deadline:
            current_urls = set()
            for p_ in context.pages:
                try:
                    current_urls.add(p_.url)
                except Exception:
                    continue
            if current_urls != last_urls:
                for u in current_urls:
                    log(f"열린 탭: {u}")
                last_urls = current_urls

            for u in current_urls:
                host = urlparse(u).hostname or ""
                if host and host != "nid.naver.com":
                    logged_in = True
                    break
            if logged_in:
                break
            time.sleep(2)

        if not logged_in:
            log(f"{timeout_sec}초 안에 로그인이 감지되지 않았습니다. 프로필을 그대로 둔 채 종료합니다 (다시 시도 가능).")
            context.close()
            sys.exit(1)

        # 로그인 직후 리다이렉트/추가 페이지 로드가 안정될 시간을 약간 준다.
        time.sleep(2)

        # URL이 nid.naver.com을 벗어난 것은 "로그인 절차가 끝났다"는 정황일 뿐,
        # 진짜 로그인 쿠키가 발급됐는지는 별도로 다시 확인한다 (더블체크).
        if not is_logged_in(context):
            log("URL은 로그인 페이지를 벗어났지만 로그인 쿠키(NID_AUT/NID_SES)가 확인되지 않습니다. "
                "다시 시도해주세요.")
            context.close()
            sys.exit(1)

        log(f"로그인 확인 완료 (현재 URL: {page.url}, 쿠키 확인됨) — 프로필에 로그인 상태 저장됨: {PROFILE_DIR}")

        if export_storage_state:
            out_path = Path(export_storage_state)
            out_path.parent.mkdir(parents=True, exist_ok=True)
            context.storage_state(path=str(out_path))
            log(f"storage_state 내보내기 완료: {out_path} "
                f"(GitHub Secret 등록용 — base64로 인코딩해 등록하고, 이 파일 자체는 커밋/공유하지 말 것)")

        context.close()


# ---------------------------------------------------------------------------
# 2) 구글 드라이브 이미지 다운로드 (선택)
# ---------------------------------------------------------------------------
def download_drive_images(drive_urls, dest_dir: Path):
    """
    공유 링크 형태의 구글 드라이브 이미지를 로컬로 다운로드.
    gdown 사용: pip install gdown --break-system-packages
    OneDrive를 쓰는 경우 이 함수 대신 회사 OneDrive 다운로드 로직으로 교체하세요.
    """
    if not drive_urls:
        return []

    try:
        import gdown
    except ImportError:
        log("gdown이 설치되어 있지 않습니다. `pip install gdown --break-system-packages` 실행 필요.")
        raise

    dest_dir.mkdir(parents=True, exist_ok=True)
    local_paths = []
    for i, url in enumerate(drive_urls):
        out_path = dest_dir / f"drive_image_{i}.jpg"
        log(f"드라이브 이미지 다운로드: {url} -> {out_path}")
        gdown.download(url=url, output=str(out_path), fuzzy=True, quiet=False)
        local_paths.append(str(out_path))
    return local_paths


# ---------------------------------------------------------------------------
# 3) 글쓰기 페이지 진입 + 팝업 처리
# ---------------------------------------------------------------------------
def _raise_if_login_redirect(url: str):
    """
    쿠키가 있어도 만료/거부돼서 네이버가 로그인 페이지로 되돌려보낼 수 있다.
    실제로 도착한 URL을 보고 이 경우를 조기에 잡아낸다 (순수 함수라 브라우저 없이 테스트 가능).
    """
    host = urlparse(url).hostname or ""
    if host == "nid.naver.com":
        raise RuntimeError(
            "글쓰기 페이지 진입 시 로그인 페이지로 리다이렉트됐습니다. "
            "세션이 만료된 것으로 보입니다. `python scripts/publish.py capture-session`을 다시 실행해주세요."
        )


def open_write_page(page, blog_id: str):
    write_url = f"{NAVER_BLOG_HOME}/{blog_id}?Redirect=Write&"
    log(f"글쓰기 페이지 접속: {write_url}")
    page.goto(write_url)
    page.wait_for_load_state("networkidle")
    human_delay()

    _raise_if_login_redirect(page.url)

    frame = page.frame_locator(SELECTORS["main_iframe"])

    # "작성 중인 글이 있습니다" 팝업 처리
    try:
        cancel_btn = frame.locator(SELECTORS["continue_popup_cancel"])
        cancel_btn.wait_for(timeout=4000)
        cancel_btn.click()
        log("이어쓰기 팝업 → 취소(새 글 시작) 클릭")
        human_delay()
    except PWTimeout:
        log("이어쓰기 팝업 없음 (정상)")

    # 도움말 패널 팝업 처리
    try:
        help_close = frame.locator(SELECTORS["help_panel_close"])
        help_close.wait_for(timeout=3000)
        help_close.click()
        log("도움말 패널 닫기")
        human_delay()
    except PWTimeout:
        log("도움말 패널 없음 (정상)")

    return frame


# ---------------------------------------------------------------------------
# 4) 콘텐츠 입력
# ---------------------------------------------------------------------------
def fill_title(page, frame, title: str):
    title_area = frame.locator(SELECTORS["title_area"])
    title_area.click()
    human_delay(0.3, 0.7)
    # 타이핑 방식 (사람처럼). 클립보드 방식이 필요하면 page.keyboard 대신
    # context.grant_permissions(["clipboard-read","clipboard-write"]) 후
    # page.evaluate로 navigator.clipboard.writeText(title) 실행 + Ctrl+V 사용.
    page.keyboard.type(title, delay=random.randint(30, 90))
    log(f"제목 입력 완료: {title}")


def type_with_inline_bold(page, frame, text: str, bold_active: bool = False) -> bool:
    """`**` 마커가 섞인 한 줄을 타이핑하면서, 마커로 감싼 부분만 실제 굵게로 입력한다.

    SmartEditor의 굵게 버튼은 선택된 텍스트가 없어도(커서만 있는 상태) 클릭하면
    이후 타이핑되는 글자에 굵게가 적용되는 "타이핑 상태 토글"로 동작한다
    (2026-07-09 now_eoding 계정에서 스크린샷으로 검증). `text.split("**")`로 나눈
    조각 사이사이의 경계마다 이 토글을 뒤집는 방식으로 인라인 굵게를 구현한다.

    `bold_active`: 이 줄이 시작되는 시점에 이미 굵게 구간 안인지(직전 줄에서 닫는
    `**` 없이 넘어온 경우) 나타낸다. 글쓰기 스타일상 문장 하나가 여러 줄로 줄바꿈되면서
    `**굵게**` 마커의 열고 닫는 지점이 서로 다른 줄에 걸치는 경우가 실제로 있었다
    (2026-07-15, 세계테마기행 1부에서 처음 발견 — 그때는 이 상태를 안 넘겨서 두 줄
    다 별표가 그대로 타이핑되는 버그가 있었음). 이 함수는 줄이 끝나는 시점에도 아직
    굵게가 안 닫혔으면(반환값 True) 다음 줄 호출에 그대로 넘겨 이어붙일 수 있게 한다.
    반환 시점엔 항상 실제 에디터의 굵게 토글 버튼 상태를 꺼둔 채로 넘긴다(Enter로
    새 문단/줄바꿈을 만들기 전에 굵게가 새 줄까지 새지 않도록).
    """
    bold_btn = frame.locator(SELECTORS["bold_toolbar_button"])
    if bold_active:
        bold_btn.click()
    parts = text.split("**")
    for i, part in enumerate(parts):
        if part:
            page.keyboard.type(part, delay=random.randint(20, 60))
        if i < len(parts) - 1:
            bold_btn.click()
            bold_active = not bold_active
    if bold_active:
        bold_btn.click()
    return bold_active


def fill_body_blocks(page, frame, body_blocks: list):
    # 새 글 상태에서는 .se-text-paragraph가 제목(0번)/본문 첫 문단(1번) 두 개뿐이다.
    body_area = frame.locator(SELECTORS["body_area"]).nth(1)
    body_area.click()
    human_delay(0.3, 0.7)

    for block in body_blocks:
        btype = block.get("type")
        if btype == "text":
            bold_active = False
            for line in block["content"].split("\n"):
                bold_active = type_with_inline_bold(page, frame, line, bold_active)
                page.keyboard.press("Enter")
                human_delay(0.2, 0.6)
            if bold_active:
                log("경고: 텍스트 블록이 끝났는데 굵게(**) 구간이 안 닫힌 채로 남았습니다 — "
                    "원고에서 ** 쌍이 맞는지 확인하세요.")
        elif btype == "heading":
            fill_heading(page, frame, block["content"])
        elif btype == "quote":
            fill_quote(page, frame, block["content"])
        elif btype == "image":
            insert_image(page, frame, block["path"], link_url=block.get("link"))
        elif btype == "table":
            insert_table(page, frame, block["rows"])
        else:
            log(f"알 수 없는 블록 타입 무시: {btype}")
    log("본문 입력 완료")


def click_canvas_bottom_button(frame):
    """인용구/표 등 컴포넌트 밖으로 나가는 캔버스 하단 버튼을 클릭한다.

    이 버튼은 class에 `__edge-area`가 붙어 있어 마우스가 캔버스 하단 근처로
    hover해야 보이는(hover 전에는 opacity/visibility가 꺼져 있는) 요소다.
    바로 click()만 하면 "element is not visible" 타임아웃이 날 수 있어
    (2026-07-14 this_africa 계정에서 실측), scroll_into_view + hover로 먼저
    보이는 상태를 만든 뒤 클릭한다.
    """
    btn = frame.locator(SELECTORS["canvas_bottom_button"])
    btn.scroll_into_view_if_needed()
    btn.hover()
    human_delay(0.2, 0.4)
    btn.click()


def fill_heading(page, frame, content: str):
    """소제목(H2/H3)을 SmartEditor의 인용구2(세로선) 스타일로 삽입한다.

    본문 문단 스타일을 직접 바꾸는 고정 툴바가 없어서, 대신 인용구 컴포넌트를
    삽입한 뒤 스타일을 인용구2(세로선)로 바꿔 소제목처럼 두드러지게 만든다
    — 2026-07-09 now_eoding 계정에서 실제 렌더링을 스크린샷으로 확인함.
    """
    frame.locator(SELECTORS["quotation_insert_button"]).click()
    human_delay(0.3, 0.5)
    frame.locator(SELECTORS["quotation_style2_button"]).click()
    human_delay(0.2, 0.4)
    bold_active = type_with_inline_bold(page, frame, content)
    if bold_active:
        log("경고: 소제목(heading)에 굵게(**) 구간이 안 닫힌 채로 남았습니다 — "
            "원고에서 ** 쌍이 맞는지 확인하세요.")
    # 인용구 밖으로 나가 본문 맨 아래에 새 문단을 만들고 커서를 그쪽으로 옮긴다.
    click_canvas_bottom_button(frame)
    human_delay(0.3, 0.6)


def fill_quote(page, frame, content: str):
    """본문 인용구 블록(예: "핵심만 보기" 요약)을 SmartEditor의 기본 인용구1
    (큰따옴표 스타일) 컴포넌트로 삽입한다.

    fill_heading과 달리 스타일을 인용구2(세로선)로 바꾸지 않는다 — 기본 스타일
    그대로가 목표(중앙 정렬 큰따옴표 + 출처 입력란)이기 때문. content는 여러 줄일
    수 있고(빈 줄 포함), 각 줄 사이에 Enter를 눌러 같은 인용구 컴포넌트 안에서
    문단을 나눈다(컴포넌트를 벗어나는 건 canvas_bottom_button 클릭뿐).
    """
    frame.locator(SELECTORS["quotation_insert_button"]).click()
    human_delay(0.3, 0.5)
    bold_active = False
    for line in content.split("\n"):
        bold_active = type_with_inline_bold(page, frame, line, bold_active)
        page.keyboard.press("Enter")
        human_delay(0.2, 0.5)
    if bold_active:
        log("경고: 인용구 블록이 끝났는데 굵게(**) 구간이 안 닫힌 채로 남았습니다.")
    click_canvas_bottom_button(frame)
    human_delay(0.3, 0.6)


def close_sidebar_if_open(frame):
    """이미지 삽입 후 자동으로 열리는 우측 사이드바(라이브러리 등)를 닫는다.

    이 사이드바가 열려 있으면 표의 오른쪽 끝 컨트롤("열 추가" 버튼 등)과 겹쳐
    클릭이 가로막힌다(2026-07-22 this_africa 계정에서 4열 이상 표 삽입 시 확인).
    """
    close_btn = frame.locator(SELECTORS["sidebar_close_button"])
    if close_btn.count() and close_btn.first.is_visible():
        close_btn.first.click()
        human_delay(0.2, 0.4)


def insert_table(page, frame, rows: list):
    """마크다운 표를 SmartEditor의 실제 표 위젯으로 삽입한다.

    표 삽입 버튼을 누르면 기본 3행 3열 표가 즉시 삽입되므로(별도 행/열 개수
    입력 다이얼로그 없음), 필요한 크기보다 부족한 행/열은 표 가장자리의
    "N행/N열 다음에 추가" 버튼을 반복 클릭해 늘린다. 필요한 크기가 3보다 작으면
    남는 빈 셀은 그대로 둔다(표 삭제 로직은 만들지 않음 — 실사용 표가 대부분
    3열 이상이라 실익이 적음).
    """
    if not rows:
        return
    n_rows = len(rows)
    n_cols = len(rows[0])

    close_sidebar_if_open(frame)
    frame.locator(SELECTORS["table_toolbar_button"]).click()
    human_delay(0.3, 0.6)

    def click_last(label: str):
        frame.locator(SELECTORS["table_add_cell_button"], has_text=label).last.click()
        # 버튼 클릭 직후 표가 리렌더링되는 동안 너무 빨리 다음 클릭을 쏘면(특히 21행
        # 이상의 긴 표) 행 추가가 씹혀서 실제 행 수가 목표보다 부족해지는 경우가
        # 있었다(2026-07-22 확인) — 여유 있게 대기한다.
        human_delay(0.4, 0.7)

    for _ in range(max(0, n_cols - 3)):
        click_last("열 추가")
    for _ in range(max(0, n_rows - 3)):
        click_last("행 추가")

    table = frame.locator(SELECTORS["table_element"]).last
    cells = table.locator(SELECTORS["table_cell_paragraph"])
    expected_cells = n_rows * n_cols
    for _ in range(20):
        if cells.count() >= expected_cells:
            break
        human_delay(0.3, 0.5)
    actual_cells = cells.count()
    if actual_cells < expected_cells:
        log(f"경고: 표에 필요한 셀 수({expected_cells})만큼 렌더링되지 않음(실제 {actual_cells}) "
            f"— 행/열 추가 버튼 클릭이 일부 누락된 것으로 보임.")
    flat_cells = [cell for row in rows for cell in row]
    for i, cell_text in enumerate(flat_cells):
        cell = cells.nth(i)
        # 행이 많은 표(예: 24일 일정표)는 스크롤 밖 셀에서 actionability 타임아웃이
        # 나는 경우가 있어(2026-07-14, 2026-07-22 this_africa 계정에서 실측), click() 전에
        # 명시적으로 스크롤해 넣는다. 그래도 가끔 한 번에 안 잡히는 셀이 있어(특히 21행
        # 이상의 긴 표), 실패하면 마우스 휠로 화면을 더 내린 뒤 재시도한다(최대 3회).
        for attempt in range(3):
            try:
                cell.scroll_into_view_if_needed(timeout=10000)
                cell.click(timeout=10000)
                break
            except PWTimeout:
                if attempt == 2:
                    raise
                page.mouse.wheel(0, 600)
                human_delay(0.3, 0.6)
        page.keyboard.type(cell_text, delay=random.randint(20, 60))

    # 표 밖으로 나가 본문 맨 아래에 새 문단을 만들고 커서를 그쪽으로 옮긴다.
    click_canvas_bottom_button(frame)
    human_delay(0.3, 0.6)
    log(f"표 삽입 완료 ({n_rows}행 {n_cols}열)")


def insert_image(page, frame, image_path: str, link_url: str | None = None):
    with page.expect_file_chooser() as fc_info:
        frame.locator(SELECTORS["image_toolbar_button"]).click()
    file_chooser = fc_info.value
    file_chooser.set_files(image_path)
    log(f"이미지 첨부: {image_path}")
    human_delay(1.0, 2.0)  # 업로드 처리 대기
    if link_url:
        set_image_link(page, frame, link_url)
    close_sidebar_if_open(frame)
    # 사진 삽입 후 다음 줄로 이동해 커서를 본문에 유지
    page.keyboard.press("Enter")


def set_image_link(page, frame, url: str):
    """방금 삽입된 이미지를 선택하고, 속성 툴바의 링크 버튼으로 URL을 건다.

    2026-07-15 this_africa 계정에서 실제 확인한 흐름: 이미지를 클릭해 선택하면
    상단에 속성 툴바(propertyToolbar)가 나타나고, 그 안의 링크 버튼
    (data-name="image-link")을 클릭하면 URL 입력창이 뜬다. 입력 후 체크(적용) 버튼을
    누르면 이미지 전체가 그 링크로 감싸진다(클릭 시 해당 URL로 이동).
    """
    img = frame.locator(SELECTORS["image_resource"]).last
    img.click()
    human_delay(0.3, 0.6)
    frame.locator(SELECTORS["image_link_button"]).click()
    human_delay(0.3, 0.6)
    link_input = frame.locator(SELECTORS["image_link_input"])
    link_input.click()
    page.keyboard.type(url, delay=random.randint(20, 50))
    frame.locator(SELECTORS["image_link_apply_button"]).click()
    human_delay(0.3, 0.6)
    log(f"이미지에 링크 연결: {url}")


# ---------------------------------------------------------------------------
# 5) 발행 설정 및 실행
# ---------------------------------------------------------------------------
def set_category(frame, category: str):
    if SELECTORS["category_selectbox"] == "TODO: verify":
        log("⚠️ category_selectbox 셀렉터 미설정 — 카테고리 설정을 건너뜁니다. SELECTORS 채운 뒤 사용하세요.")
        return
    frame.locator(SELECTORS["category_selectbox"]).click()
    human_delay()
    # 라디오 label의 for 속성이 "{카테고리ID}_{카테고리명}" 형식이라 접미사
    # 매칭으로 찾는다. 목록이 스크롤 밖에 있어도 text-is보다 안정적으로 매칭된다.
    option = frame.locator(f"{SELECTORS['category_option_tpl']}[for$='_{category}']")
    option.scroll_into_view_if_needed()
    option.click()
    log(f"카테고리 설정: {category}")


def _wait_for_chip_count(chips, target: int, timeout_s: float = 3.0) -> int:
    """칩 개수가 target에 도달할 때까지 짧게 폴링한다(고정 sleep 한 번보다 안전).

    Enter 입력 직후 칩이 DOM에 반영되기까지 약간의 지연이 있을 수 있는데, 고정
    시간만 기다리고 한 번만 확인하면 그 찰나의 렌더링 지연을 "실패"로 오판해
    불필요한 재입력을 유발할 수 있다(2026-07-16 실제로 이 문제로 태그 텍스트가
    "#세계테마기행세계테마기행"처럼 중복/오염되는 회귀 버그가 발생함— 입력창이
    아직 비워지기 전에 재입력을 시도해 이전 텍스트 위에 덧입력됐기 때문). 그래서
    짧은 간격으로 여러 번 재확인해 실제 반영을 기다린 뒤에만 재시도 여부를 판단한다.
    """
    waited = 0.0
    step = 0.2
    count = chips.count()
    while count < target and waited < timeout_s:
        time.sleep(step)
        waited += step
        count = chips.count()
    return count


def set_tags(page, frame, tags: list):
    """태그를 하나씩 입력하고, 최종적으로 칩(chip) 구성이 의도한 태그와 정확히
    일치하는지 검증 후 필요하면 정리한다.

    태그 편집 박스는 화면상 2줄 정도만 보이고 나머지는 스크롤해야 보이는 고정 높이
    UI라(2026-07-16 확인), 화면만 봐서는 마지막 태그가 "누락"된 것처럼 보일 수 있다.
    실제 데이터 유실 여부는 화면이 아니라 칩 요소 개수/내용으로 판단해야 한다.

    ⚠️ Enter 처리가 비동기로 살짝 지연될 때가 있어(2026-07-16 확인), 칩 생성 확인
    "직후" 곧바로 같은 텍스트를 재입력하면 그 지연된 처리가 나중에 엉뚱한(다음
    태그가 이미 섞여 들어간) 입력값으로 커밋되면서 "#세계테마기행남아공여행"처럼
    인접한 두 태그가 붙어버리는 칩이 추가로 생기는 회귀 버그가 실제로 있었다. 이
    문제는 타이핑 중간에 재시도해서 막으려 하지 않고, 대신 전체 태그를 다 입력한
    뒤 마지막에 "칩 내용이 의도한 태그 집합과 정확히 같은가"를 확인해서, 아니라면
    (신뢰할 수 있는) 빈 입력창에서의 Backspace로 끝에서부터 잘못된 칩을 제거하는
    방식으로 정리한다 — 이상하게 생성된 칩은 항상 정상 태그들 뒤에 붙어서
    생기므로, 끝에서부터 지우면 된다. 칩 자체를 클릭해서 지우는 방식은 이 UI에서
    간헐적으로 씹혀 신뢰할 수 없었다(직접 확인함).
    """
    tag_input = frame.locator(SELECTORS["tag_input"])
    chips = frame.locator(SELECTORS["tag_chip"])
    for tag in tags:
        before = chips.count()
        tag_input.click()
        page.keyboard.type(tag, delay=random.randint(30, 70))
        page.keyboard.press("Enter")
        _wait_for_chip_count(chips, before + 1, timeout_s=4.0)

    # 입력이 모두 끝난 뒤에만 최종 상태를 검증 — 타이핑 도중 재시도하지 않는다.
    human_delay(0.5, 0.8)
    valid_tags = set(tags)
    labels = [chips.nth(i).get_attribute("aria-label") for i in range(chips.count())]
    if labels == tags:
        log(f"태그 입력 완료 (칩 {len(labels)}개 확인): {tags}")
        return

    log(f"⚠️ 칩 구성이 의도한 태그와 다릅니다({labels}) — 끝에서부터 정리 시도")
    tag_input.click()
    trim_guard = 0
    while chips.count() > len(valid_tags) and trim_guard < len(valid_tags) + 10:
        before_trim = chips.count()
        page.keyboard.press("Backspace")
        human_delay(0.5, 0.7)
        if chips.count() == before_trim:
            # Backspace가 씹혔을 수 있으니 입력창 포커스를 다시 잡고 재시도한다
            # (2026-07-16 실제로 간헐적으로 포커스가 빠지는 현상 확인함).
            tag_input.click()
            human_delay(0.3, 0.4)
        trim_guard += 1

    final_labels = [chips.nth(i).get_attribute("aria-label") for i in range(chips.count())]
    if set(final_labels) == valid_tags and len(final_labels) == len(valid_tags):
        log(f"태그 정리 완료 (칩 {len(final_labels)}개, 최종 일치 확인): {final_labels}")
    else:
        log(f"❌ 태그 정리 후에도 불일치 — 수동 확인 필요. 현재 칩: {final_labels}")


def open_publish_dialog(frame):
    if SELECTORS["publish_open_button"] == "TODO: verify":
        raise RuntimeError(
            "publish_open_button 셀렉터가 설정되지 않았습니다. "
            "Playwright Inspector로 '발행' 버튼을 확인 후 SELECTORS를 채워주세요."
        )
    frame.locator(SELECTORS["publish_open_button"]).click()
    human_delay()


def set_visibility(frame, visibility: str):
    """visibility: 'private' | 'neighbors' | 'public'"""
    if SELECTORS["visibility_radio_tpl"] == "TODO: verify":
        log("⚠️ visibility_radio_tpl 셀렉터 미설정 — 기본값(전체공개)으로 진행될 수 있습니다.")
        return
    label_map = {"private": "비공개", "neighbors": "이웃공개", "public": "전체공개"}
    label = label_map.get(visibility, "비공개")
    # "이웃공개"는 "서로이웃공개"의 부분 문자열이라 has_text(부분일치)로 찾으면
    # 두 라디오가 동시에 걸려 strict mode 오류가 난다. :text-is()로 정확히
    # 일치하는 라벨 텍스트만 찾는다.
    frame.locator(f"{SELECTORS['visibility_radio_tpl']}:text-is('{label}')").click()
    log(f"공개범위 설정: {label}")


_KOREAN_MONTH_TITLE_RE = re.compile(r"(\d{4})년\s*(\d{1,2})월")


def set_schedule(page, frame, publish_at: datetime):
    """예약 발행 시간을 설정한다 (2026-07-16 this_africa 계정에서 확인한 흐름).

    네이버 발행 패널의 "발행 시간"을 "예약"으로 바꾸면 날짜 입력창(클릭하면 jQuery UI
    데이트피커가 열림) + 시(0~23)/분(00/10/20/30/40/50, 10분 단위만) select가 나타난다.
    분은 10분 단위로만 고를 수 있어서 요청한 분을 10분 단위로 내림 처리한다.
    """
    label = frame.locator(f"{SELECTORS['visibility_radio_tpl']}:text-is('예약')")
    label.click()
    human_delay(0.3, 0.6)

    frame.locator(SELECTORS["schedule_date_input"]).click()
    human_delay(0.3, 0.6)

    target_year, target_month = publish_at.year, publish_at.month
    title_loc = frame.locator(SELECTORS["datepicker_title"])
    for _ in range(24):  # 최대 24개월 앞까지 이동
        m = _KOREAN_MONTH_TITLE_RE.search(title_loc.inner_text())
        if not m:
            raise RuntimeError("데이트피커의 연/월 표시를 읽지 못했습니다 — 화면 구조가 바뀌었을 수 있습니다.")
        shown_year, shown_month = int(m.group(1)), int(m.group(2))
        if (shown_year, shown_month) == (target_year, target_month):
            break
        if (shown_year, shown_month) < (target_year, target_month):
            frame.locator(SELECTORS["datepicker_next_month"]).click()
        else:
            frame.locator(SELECTORS["datepicker_prev_month"]).click()
        human_delay(0.2, 0.4)
    else:
        raise RuntimeError(f"데이트피커에서 {target_year}년 {target_month}월로 이동하지 못했습니다(24개월 한도 초과).")

    frame.locator(SELECTORS["datepicker_day_button"]).filter(has_text=re.compile(rf"^{publish_at.day}$")).click()
    human_delay(0.3, 0.5)

    minute_rounded = (publish_at.minute // 10) * 10
    frame.locator(SELECTORS["schedule_hour_select"]).select_option(f"{publish_at.hour:02d}")
    frame.locator(SELECTORS["schedule_minute_select"]).select_option(f"{minute_rounded:02d}")
    human_delay(0.2, 0.4)
    log(f"예약 발행 시간 설정: {publish_at.strftime('%Y-%m-%d')} {publish_at.hour:02d}:{minute_rounded:02d}"
        + (f" (요청한 분 {publish_at.minute}은 10분 단위로 내림 처리됨)" if minute_rounded != publish_at.minute else ""))


_SCHEDULED_ITEM_DATETIME_RE = re.compile(r"(\d{4})[.\-](\d{1,2})[.\-](\d{1,2})\D+(\d{1,2}):(\d{2})")


def _get_reserved_count(frame) -> int:
    """"예약 발행 N건" 배지 숫자를 읽는다.

    글쓰기 페이지 로드 직후엔 이 배지가 비동기로 채워지는 듯, 실제로는 1건 이상인데도
    곧바로 읽으면 한동안 "0"으로 보이는 경우가 있었다(2026-09-12 실측 — 같은 페이지를
    몇 초 뒤 다시 열었더니 정상적으로 카운트가 보임). 그래서 0으로 읽히면 바로 믿지 않고
    잠깐씩 재확인한다.
    """
    last = 0
    for _ in range(4):
        text = frame.locator(SELECTORS["reserved_count_badge"]).text_content(timeout=5000)
        last = int((text or "0").strip())
        if last > 0:
            return last
        time.sleep(1.5)
    return last


def list_scheduled_posts(blog_id: str, headed: bool = True, storage_state: str | None = None, as_json: bool = False):
    """예약 발행 글 목록을 출력한다 (제목 + 예약 시각).

    `as_json=True`면 사람이 읽는 출력 대신 `[{"title": ..., "datetime": "YYYY-MM-DD HH:MM"}, ...]`
    형식 JSON을 stdout에 찍는다 — 다음 배치를 예약할 때 "현재 가장 늦게 예약된 날짜"를
    자동으로 계산하기 위한 용도(2026-07-16 추가, CLAUDE.md "예약 발행 자동 스케줄링" 참고).
    """
    with sync_playwright() as p:
        with open_context(p, headed=headed, storage_state=storage_state) as context:
            page = context.new_page()
            if not is_logged_in(context):
                log("로그인 세션이 유효하지 않습니다.")
                sys.exit(1)
            frame = open_write_page(page, blog_id)
            badge_count = _get_reserved_count(frame)
            if badge_count == 0:
                # 0건일 때는 "예약 발행 0건" 버튼을 감싼 영역 자체가 display:none이라
                # 클릭하면 타임아웃난다 (2026-09-12 확인) — 배지 텍스트만으로 바로 빈 목록 처리.
                if as_json:
                    print(json.dumps([], ensure_ascii=False))
                else:
                    print("예약 발행 글이 없습니다.")
                return
            frame.locator(SELECTORS["reserved_list_open_button"]).click()
            human_delay(0.5, 1.0)
            items = frame.locator(SELECTORS["reserved_list_item"])
            n = items.count()
            if as_json:
                results = []
                for i in range(n):
                    text = items.nth(i).inner_text()
                    m = _SCHEDULED_ITEM_DATETIME_RE.search(text)
                    dt = f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d} {int(m.group(4)):02d}:{m.group(5)}" if m else None
                    title = text.split("\n")[0].strip()
                    results.append({"title": title, "datetime": dt})
                print(json.dumps(results, ensure_ascii=False))
                return
            if n == 0:
                print("예약 발행 글이 없습니다.")
            else:
                print(f"예약 발행 글 {n}건:")
                for i in range(n):
                    print(f"  - {items.nth(i).inner_text()}".replace("\n", " | "))


def cancel_scheduled_post(blog_id: str, title_contains: str, headed: bool = True,
                           storage_state: str | None = None):
    """제목에 title_contains가 포함된 예약 발행 글을 찾아 삭제한다.

    ⚠️ 네이버가 삭제 시 브라우저 네이티브 confirm() 팝업("선택된 N개의 예약발행 글을
    삭제하시겠습니까? 삭제된 글은 복구되지 않습니다.")을 띄운다. 이 팝업을 처리하지 않으면
    Playwright가 기본적으로 자동 취소해버려서, 클릭 자체는 에러 없이 "성공"한 것처럼 보이지만
    실제로는 삭제되지 않는다(2026-07-16 실제로 이 문제로 두 번 실패한 뒤 원인 파악함). 그래서
    이 함수는 반드시 page.on("dialog", ...)로 accept 처리를 먼저 등록한다.
    """
    with sync_playwright() as p:
        with open_context(p, headed=headed, storage_state=storage_state) as context:
            page = context.new_page()

            def _accept_dialog(dialog):
                log(f"확인 팝업 감지 → 수락: {dialog.message!r}")
                dialog.accept()

            page.on("dialog", _accept_dialog)

            if not is_logged_in(context):
                log("로그인 세션이 유효하지 않습니다.")
                sys.exit(1)
            frame = open_write_page(page, blog_id)
            if _get_reserved_count(frame) == 0:
                log(f"예약 발행 글이 0건입니다 — '{title_contains}'을(를) 찾지 못했습니다.")
                return
            frame.locator(SELECTORS["reserved_list_open_button"]).click()
            human_delay(0.5, 1.0)

            target = frame.locator(SELECTORS["reserved_list_item"]).filter(has_text=title_contains)
            count = target.count()
            if count == 0:
                log(f"'{title_contains}'을(를) 포함하는 예약 글을 찾지 못했습니다.")
                return
            if count > 1:
                log(f"⚠️ '{title_contains}'에 매칭되는 예약 글이 {count}건입니다 — 첫 번째 것만 삭제합니다.")

            item = target.first
            item.hover()
            human_delay(0.3, 0.5)
            # reserved_delete_button은 id 셀렉터인데도 예약 목록의 모든 항목에서
            # id가 중복돼(네이버 마크업 자체 문제) frame 전체를 뒤지면 strict mode
            # violation이 난다(2026-07-21 실제 발생). hover한 item 안으로 스코프를
            # 좁혀서 그 항목의 삭제 버튼만 정확히 클릭한다.
            item.locator(SELECTORS["reserved_delete_button"]).click()
            human_delay(1.0, 1.5)
            log("예약 글 삭제 완료")


def click_final_publish(frame, save_as_draft: bool):
    if save_as_draft:
        if SELECTORS["save_draft_button"] == "TODO: verify":
            log("⚠️ save_draft_button 셀렉터 미설정 — 임시저장을 수행할 수 없습니다.")
            return
        frame.locator(SELECTORS["save_draft_button"]).click()
        log("임시저장 완료")
        return

    if SELECTORS["final_publish_button"] == "TODO: verify":
        raise RuntimeError("final_publish_button 셀렉터가 설정되지 않았습니다.")
    frame.locator(SELECTORS["final_publish_button"]).click()
    log("발행 버튼 클릭 완료")


# ---------------------------------------------------------------------------
# 메인 발행 플로우
# ---------------------------------------------------------------------------
def publish_post(post_json_path: str, blog_id: str, visibility: str, headed: bool, save_as_draft: bool,
                  storage_state: str | None = None, publish_at: datetime | None = None):
    if not storage_state and not PROFILE_DIR.exists():
        log(f"로그인 프로필이 없습니다: {PROFILE_DIR}. 먼저 `capture-session`을 실행하세요.")
        sys.exit(1)
    if storage_state and not Path(storage_state).exists():
        log(f"storage_state 파일이 없습니다: {storage_state}")
        sys.exit(1)
    if publish_at and save_as_draft:
        log("⚠️ --publish-at과 --draft는 같이 쓸 수 없습니다 (임시저장은 예약 개념이 없음). "
            "--draft로 먼저 내용을 확인한 뒤, 승인되면 --draft 없이 --publish-at으로 예약하세요.")
        sys.exit(1)
    if publish_at and publish_at <= datetime.now():
        log(f"⚠️ --publish-at은 미래 시각이어야 합니다 (입력값: {publish_at}, 현재: {datetime.now()}).")
        sys.exit(1)

    post = json.loads(Path(post_json_path).read_text(encoding="utf-8"))

    # 구글 드라이브 이미지가 있으면 로컬로 먼저 다운로드하고 body_blocks 경로 치환
    drive_urls = post.get("drive_image_urls", [])
    if drive_urls:
        local_paths = download_drive_images(drive_urls, TMP_IMAGE_DIR)
        # 다운로드된 이미지를 순서대로 image 블록에 매핑 (path가 비어있는 경우만)
        idx = 0
        for block in post.get("body_blocks", []):
            if block.get("type") == "image" and not block.get("path"):
                block["path"] = local_paths[idx]
                idx += 1

    with sync_playwright() as p:
        with open_context(p, headed=headed, storage_state=storage_state) as context:
            page = context.new_page()

            # 실제로 글쓰기 페이지에 들어가기 전에, 로그인 세션이 아직 유효한지부터 확인한다.
            # (naver_profile/storage_state가 존재하는 것과 "지금 로그인돼 있는 것"은 다르다 —
            # 세션이 만료됐는데도 파일은 남아있을 수 있다.)
            if not is_logged_in(context):
                log("로그인 세션이 유효하지 않습니다 (쿠키 없음/만료). "
                    "로컬이라면 `python scripts/publish.py capture-session`을 다시 실행해 로그인해주세요. "
                    "CI라면 storage_state를 새로 발급해 GitHub Secret을 갱신해주세요.")
                sys.exit(1)
            log("로그인 상태 확인 완료 — 포스팅을 시작합니다.")

            try:
                frame = open_write_page(page, blog_id)

                fill_title(page, frame, post["title"])
                fill_body_blocks(page, frame, post.get("body_blocks", []))

                # 카테고리 선택창/태그 입력창은 "발행" 버튼을 눌러 발행 패널을 열어야
                # 화면에 나타난다 (본문 편집 화면에는 없음). 그래서 반드시 패널을
                # 연 다음에 카테고리/태그를 설정해야 한다.
                open_publish_dialog(frame)

                if post.get("category"):
                    set_category(frame, post["category"])
                if post.get("tags"):
                    set_tags(page, frame, post["tags"])

                set_visibility(frame, visibility)
                if publish_at:
                    set_schedule(page, frame, publish_at)
                click_final_publish(frame, save_as_draft)

                human_delay(1.5, 3.0)
                log("발행 플로우 완료")

            except Exception as e:
                log(f"오류 발생: {e}")
                take_failure_screenshot(page, "publish_error")
                raise


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="네이버 블로그 자동 발행 스크립트")
    sub = parser.add_subparsers(dest="command", required=True)

    cap = sub.add_parser("capture-session", help="브라우저를 열어 수동 로그인 후 세션 저장 (로컬 전용)")
    cap.add_argument("--timeout", type=int, default=300, help="로그인 대기 시간(초), 기본 300초")
    cap.add_argument("--export-storage-state", default=None,
                      help="로그인 성공 후 쿠키를 이 경로에 JSON으로 내보냄 (CI용 GitHub Secret 원본, 절대 커밋 금지)")

    chk = sub.add_parser("check-login", help="포스팅 없이 현재 로그인 세션이 유효한지만 빠르게 확인")
    chk.add_argument("--headed", action="store_true", help="브라우저 창을 띄워서 확인 (기본은 headless)")
    chk.add_argument("--storage-state", default=None,
                      help="CI 모드: naver_profile 대신 이 쿠키 JSON 파일로 로그인 상태를 확인")

    pub = sub.add_parser("publish", help="포스트 발행")
    pub.add_argument("--post-json", required=True, help="assembler가 생성한 포스트 JSON 경로")
    pub.add_argument("--blog-id", required=True, help="네이버 블로그 ID (예: yourblogid)")
    pub.add_argument("--visibility", default="private", choices=["private", "neighbors", "public"])
    pub.add_argument("--headed", action="store_true", help="브라우저 창을 띄워서 실행 (테스트용, CI에서는 사용 안 함)")
    pub.add_argument("--draft", action="store_true", help="발행 대신 임시저장")
    pub.add_argument("--publish-at", default=None,
                      help="예약 발행 시각, 'YYYY-MM-DD HH:MM' 형식(로컬 시간). --draft와 같이 쓸 수 없음 — "
                           "먼저 --draft로 확인한 뒤 승인되면 이 옵션으로 실제 예약 발행을 건다. "
                           "네이버 UI가 분을 10분 단위로만 받아서 자동으로 내림 처리된다.")
    pub.add_argument("--storage-state", default=None,
                      help="CI 모드: naver_profile 대신 이 쿠키 JSON 파일로 로그인해 발행")

    lst = sub.add_parser("list-scheduled", help="예약 발행 글 목록 조회")
    lst.add_argument("--blog-id", required=True)
    lst.add_argument("--headed", action="store_true", default=True)
    lst.add_argument("--storage-state", default=None)
    lst.add_argument("--json", action="store_true", dest="as_json",
                      help="사람이 읽는 출력 대신 JSON으로 출력(다음 예약 가능 날짜 자동 계산용)")

    cnl = sub.add_parser("cancel-scheduled", help="제목에 특정 문자열이 포함된 예약 발행 글 삭제 (복구 불가)")
    cnl.add_argument("--blog-id", required=True)
    cnl.add_argument("--title-contains", required=True, help="삭제할 예약 글의 제목에 포함된 문자열")
    cnl.add_argument("--headed", action="store_true", default=True)
    cnl.add_argument("--storage-state", default=None)

    args = parser.parse_args()

    if args.command == "capture-session":
        capture_session(timeout_sec=args.timeout, export_storage_state=args.export_storage_state)
    elif args.command == "check-login":
        ok = check_login(headed=args.headed, storage_state=args.storage_state)
        sys.exit(0 if ok else 1)
    elif args.command == "list-scheduled":
        list_scheduled_posts(blog_id=args.blog_id, headed=args.headed, storage_state=args.storage_state, as_json=args.as_json)
    elif args.command == "cancel-scheduled":
        cancel_scheduled_post(blog_id=args.blog_id, title_contains=args.title_contains,
                               headed=args.headed, storage_state=args.storage_state)
    elif args.command == "publish":
        publish_at = None
        if args.publish_at:
            try:
                publish_at = datetime.strptime(args.publish_at, "%Y-%m-%d %H:%M")
            except ValueError:
                log(f"--publish-at 형식이 잘못됐습니다: '{args.publish_at}' (예: '2026-07-20 09:00')")
                sys.exit(1)
        publish_post(
            post_json_path=args.post_json,
            blog_id=args.blog_id,
            visibility=args.visibility,
            headed=args.headed,
            save_as_draft=args.draft,
            storage_state=args.storage_state,
            publish_at=publish_at,
        )


if __name__ == "__main__":
    main()