"""
5단계(발행) 중 publish.py의 실제 상호작용 함수(fill_title, fill_body_blocks,
set_category, set_tags, set_visibility, click_final_publish)를 검증한다.

실제 네이버 블로그 대신 fixtures/mock_editor_outer.html(네이버 SmartEditor의
실제 클래스명을 그대로 흉내낸 mock DOM)을 열어서 테스트한다. 로그인/네트워크/
실제 계정이 전혀 필요 없고, publish.py의 SELECTORS 값이 코드와 어긋나면
바로 여기서 실패한다.
"""

from pathlib import Path

import pytest
from playwright.sync_api import sync_playwright

from conftest import FIXTURES_DIR

import publish as pub

MOCK_PAGE = FIXTURES_DIR / "mock_editor_outer.html"
COVER_IMAGE = FIXTURES_DIR / "topic_sample" / "images" / "cover.png"


@pytest.fixture
def mock_page():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()
        page.goto(MOCK_PAGE.as_uri())
        page.wait_for_load_state("networkidle")
        yield page
        browser.close()


@pytest.mark.parametrize(
    "cookie_names,expected",
    [
        ([], False),
        (["NID_AUT"], False),
        (["NID_SES"], False),
        (["NID_AUT", "NID_SES"], True),
        (["NID_AUT", "NID_SES", "NNB", "NAC"], True),
    ],
)
def test_has_valid_login_cookies_pure_logic(cookie_names, expected):
    cookies = [{"name": name, "value": "x"} for name in cookie_names]
    assert pub._has_valid_login_cookies(cookies) == expected


def test_is_logged_in_false_without_cookies():
    """실제 네이버 프로필이 아닌 빈 브라우저 컨텍스트라면 로그인되어 있지 않아야 한다."""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        try:
            assert pub.is_logged_in(context) is False
        finally:
            browser.close()


def test_is_logged_in_true_with_mock_naver_cookies():
    """NID_AUT/NID_SES 쿠키를 수동으로 주입하면 로그인된 것으로 판단해야 한다."""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        try:
            context.add_cookies([
                {"name": "NID_AUT", "value": "fake", "domain": ".naver.com", "path": "/"},
                {"name": "NID_SES", "value": "fake", "domain": ".naver.com", "path": "/"},
            ])
            assert pub.is_logged_in(context) is True
        finally:
            browser.close()


def test_no_selectors_left_as_todo():
    """셀렉터 검증이 끝난 상태라면 TODO: verify가 하나도 남아있으면 안 된다."""
    todo_keys = [k for k, v in pub.SELECTORS.items() if v == "TODO: verify"]
    assert todo_keys == [], f"아직 채우지 않은 셀렉터: {todo_keys}"


def test_fill_title_and_body(mock_page):
    page = mock_page
    frame = page.frame_locator("iframe#mainFrame")

    pub.fill_title(page, frame, "테스트 제목입니다")
    pub.fill_body_blocks(page, frame, [
        {"type": "text", "content": "첫 문단입니다.\n둘째 줄입니다."},
        {"type": "image", "path": str(COVER_IMAGE)},
        {"type": "text", "content": "이미지 다음 문단입니다."},
    ])

    title_text = frame.locator("#mock-title").inner_text()
    assert title_text == "테스트 제목입니다"

    body_text = frame.locator("#mock-body-container").inner_text()
    assert "첫 문단입니다." in body_text
    assert "둘째 줄입니다." in body_text
    assert "이미지 다음 문단입니다." in body_text

    images = frame.locator("body").evaluate("() => window.testState.images")
    assert images == ["cover.png"]


def test_fill_heading_inserts_quotation_style2(mock_page):
    page = mock_page
    frame = page.frame_locator("iframe#mainFrame")

    body_area = frame.locator(".se-text-paragraph").nth(1)
    body_area.click()

    pub.fill_heading(page, frame, "이것은 소제목입니다")

    quote = frame.locator(".se-quotation").first
    assert "quote-line-style" in (quote.get_attribute("class") or "")
    assert "이것은 소제목입니다" in quote.inner_text()

    # 인용구 밖으로 나가 이어서 본문을 입력할 수 있어야 한다.
    page.keyboard.type("소제목 다음 문단입니다.", delay=5)
    assert "소제목 다음 문단입니다." in frame.locator(".mock-after-block").last.inner_text()


def test_fill_heading_with_bold_marker_applies_inline_bold(mock_page):
    page = mock_page
    frame = page.frame_locator("iframe#mainFrame")

    body_area = frame.locator(".se-text-paragraph").nth(1)
    body_area.click()

    pub.fill_heading(page, frame, "일반 **강조된키워드** 나머지")

    quote_html = frame.locator(".mock-quote-content").first.evaluate("el => el.innerHTML")
    quote_text = frame.locator(".mock-quote-content").first.inner_text().replace("\xa0", " ")
    assert quote_text == "일반 강조된키워드 나머지"
    assert "**" not in quote_text
    assert "<b>강조된키워드</b>" in quote_html


def test_type_with_inline_bold_in_text_block(mock_page):
    page = mock_page
    frame = page.frame_locator("iframe#mainFrame")

    pub.fill_body_blocks(page, frame, [
        {"type": "text", "content": "앞부분 **중요키워드** 뒷부분입니다."},
    ])

    para_text = frame.locator("#mock-body-first").inner_text().replace("\xa0", " ")
    assert "앞부분 중요키워드 뒷부분입니다." in para_text
    assert "<b>중요키워드</b>" in frame.locator("#mock-body-first").evaluate("el => el.innerHTML")


def test_insert_table_matches_row_and_col_count(mock_page):
    page = mock_page
    frame = page.frame_locator("iframe#mainFrame")

    body_area = frame.locator(".se-text-paragraph").nth(1)
    body_area.click()

    rows = [
        ["구분", "이전", "이후", "비고"],
        ["A 지표", "100", "150", "상승"],
        ["B 지표", "200", "240", "상승"],
        ["C 지표", "10", "5", "하락"],
    ]
    pub.insert_table(page, frame, rows)

    table = frame.locator("table.se-table-content")
    assert table.locator("tr").count() == 4
    assert table.locator("tr").first.locator("td").count() == 4

    cell_texts = table.locator("td .se-text-paragraph").all_inner_texts()
    assert cell_texts == [cell for row in rows for cell in row]

    # 표 삽입 뒤 본문 맨 아래로 커서가 이동해, 이어서 문단을 입력할 수 있어야 한다.
    page.keyboard.type("표 다음 문단입니다.", delay=5)
    assert "표 다음 문단입니다." in frame.locator(".mock-after-block").last.inner_text()


def test_category_tags_and_draft_save(mock_page):
    page = mock_page
    frame = page.frame_locator("iframe#mainFrame")

    pub.open_publish_dialog(frame)
    pub.set_category(frame, "아프리카 여행 정보")
    pub.set_tags(page, frame, ["태그1", "태그2"])
    pub.set_visibility(frame, "private")
    pub.click_final_publish(frame, save_as_draft=True)

    state = frame.locator("body").evaluate("() => window.testState")
    assert state["category"] == "아프리카 여행 정보"
    assert state["tags"] == ["태그1", "태그2"]
    assert state["action"] == "draft"

    checked_id = frame.locator("input[name='open_type']:checked").get_attribute("id")
    assert checked_id == "open_private"


def test_visibility_neighbor_does_not_match_both_neighbor(mock_page):
    """'이웃공개'와 '서로이웃공개'는 부분 문자열 관계라, 정확히 원하는 라디오만 선택되어야 한다."""
    page = mock_page
    frame = page.frame_locator("iframe#mainFrame")

    pub.open_publish_dialog(frame)
    pub.set_visibility(frame, "neighbors")

    checked_id = frame.locator("input[name='open_type']:checked").get_attribute("id")
    assert checked_id == "open_neighbor"  # "open_both_neighbor"가 아니어야 함


def test_final_publish_click_sets_public(mock_page):
    page = mock_page
    frame = page.frame_locator("iframe#mainFrame")

    pub.open_publish_dialog(frame)
    pub.set_visibility(frame, "public")
    pub.click_final_publish(frame, save_as_draft=False)

    state = frame.locator("body").evaluate("() => window.testState")
    assert state["action"] == "publish"
    checked_id = frame.locator("input[name='open_type']:checked").get_attribute("id")
    assert checked_id == "open_public"


def test_category_exact_match_does_not_pick_similar_name(mock_page):
    """'아프리카 여행 정보'를 골랐을 때 부분 문자열이 겹치는 '여행 정보'가 선택되면 안 된다."""
    page = mock_page
    frame = page.frame_locator("iframe#mainFrame")

    pub.open_publish_dialog(frame)
    pub.set_category(frame, "아프리카 여행 정보")

    label_text = frame.locator("#cat-label").inner_text()
    assert label_text == "아프리카 여행 정보"
