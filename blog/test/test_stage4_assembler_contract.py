"""
4단계(assembler)도 LLM 서브 에이전트지만, 이 단계는 "창작 없이 그대로 조립"하는
것이 유일한 임무이기 때문에 다른 단계보다 훨씬 더 엄격하게 구조적으로 검증할 수 있다.
agents/assembler.md의 계약을 mock 픽스처(draft.md → final.md/final.html)로 확인한다.
"""

import re

from conftest import FIXTURES_DIR

TOPIC_DIR = FIXTURES_DIR / "topic_sample"
DRAFT_MD = TOPIC_DIR / "draft.md"
FINAL_MD = TOPIC_DIR / "final.md"
FINAL_HTML = TOPIC_DIR / "final.html"


def test_final_md_matches_draft_content():
    """assembler는 내용을 창작·수정하지 않는다. 트레일링 공백 정리 외에는 draft.md 그대로."""
    draft_text = DRAFT_MD.read_text(encoding="utf-8").strip()
    final_text = FINAL_MD.read_text(encoding="utf-8").strip()
    assert draft_text == final_text, "final.md가 draft.md 내용을 그대로 담고 있지 않다"


def test_final_html_is_self_contained():
    """외부 CDN 폰트/스크립트에 의존하면 안 된다."""
    html = FINAL_HTML.read_text(encoding="utf-8")
    assert "http://" not in html and "https://" not in html, (
        "final.html이 외부 리소스(CDN 등)를 참조하고 있다"
    )


def test_final_html_has_inline_style():
    html = FINAL_HTML.read_text(encoding="utf-8")
    assert "<style>" in html


def test_final_html_content_width_around_700px():
    html = FINAL_HTML.read_text(encoding="utf-8")
    assert re.search(r"max-width:\s*700px", html), "본문 폭이 약 700px로 지정되어 있지 않다"


def test_final_html_headings_match_final_md_headings():
    md_text = FINAL_MD.read_text(encoding="utf-8")
    html = FINAL_HTML.read_text(encoding="utf-8")

    md_h2_titles = re.findall(r"^## (.+)$", md_text, re.MULTILINE)
    for title in md_h2_titles:
        assert f"<h2>{title}</h2>" in html or title in html, (
            f"final.md의 소제목 '{title}'이 final.html에 반영되지 않았다"
        )


def test_final_html_images_use_relative_paths():
    html = FINAL_HTML.read_text(encoding="utf-8")
    img_srcs = re.findall(r'<img src="([^"]+)"', html)
    assert len(img_srcs) >= 1
    for src in img_srcs:
        assert not src.startswith("http"), f"이미지 경로가 절대 URL이면 안 된다: {src}"
        assert (TOPIC_DIR / src).exists(), f"final.html이 참조하는 이미지가 실제로 없다: {src}"


def test_final_html_table_rendered():
    md_text = FINAL_MD.read_text(encoding="utf-8")
    html = FINAL_HTML.read_text(encoding="utf-8")
    if "|" in md_text and re.search(r"^\|.*\|$", md_text, re.MULTILINE):
        assert "<table>" in html, "마크다운 표가 있는데 <table>로 변환되지 않았다"


def test_final_md_and_html_have_same_title():
    md_title = FINAL_MD.read_text(encoding="utf-8").splitlines()[0].lstrip("# ").strip()
    html = FINAL_HTML.read_text(encoding="utf-8")
    assert f"<h1>{md_title}</h1>" in html
