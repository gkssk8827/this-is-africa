"""
2단계(writer)도 LLM 서브 에이전트라 문장 품질(어투, 자문자답 등)은 코드로 검증할 수 없다.
대신 agents/writer.md의 "완료 전 자가 점검" 체크리스트 중, 구조적으로 검증 가능한
항목만 mock draft(이미지 치환 전) 픽스처로 확인한다.
"""

import re

from conftest import FIXTURES_DIR

DRAFT_MD = FIXTURES_DIR / "topic_sample" / "draft_before_images.md"


def _read():
    return DRAFT_MD.read_text(encoding="utf-8")


def test_draft_file_exists():
    assert DRAFT_MD.exists()


def test_has_h1_title():
    text = _read()
    assert text.splitlines()[0].startswith("# ")


def test_title_length_within_seo_guide_range():
    """seo-geo-guide.md: 제목은 25~40자 내외 권장."""
    title = _read().splitlines()[0].lstrip("# ").strip()
    assert 10 <= len(title) <= 60, f"제목 길이가 비정상적임: {len(title)}자 ({title!r})"


def test_greeting_if_present_is_a_short_opener_not_repeated():
    """seo-geo-guide.md 섹션 3 절충안: 인사말 자체는 없애지 않되, 도입부에 1회만
    짧게 쓰고(본문 전체에 반복하지 않고) 첫 '##' 소제목보다 앞에 나와야 한다."""
    text = _read()
    count = text.count("안녕하세요")
    if count == 0:
        return
    assert count == 1, "인사말은 도입부에 1회만 나와야 한다 (본문 전체에 반복 금지)"
    heading_idx = text.find("\n## ")
    greeting_idx = text.find("안녕하세요")
    if heading_idx != -1:
        assert greeting_idx < heading_idx, "인사말은 첫 소제목보다 앞, 즉 도입부 안에 있어야 한다"


def test_has_image_placeholders_with_description():
    text = _read()
    placeholders = re.findall(r"\[\[IMAGE:\s*(.+?)\]\]", text)
    assert len(placeholders) >= 1, "이미지 자리 표시가 최소 1개는 있어야 한다"
    for desc in placeholders:
        assert len(desc.strip()) >= 4, f"이미지 설명이 너무 짧음: {desc!r}"


def test_has_faq_section():
    assert "## FAQ" in _read()


def test_has_summary_box():
    """style-guide.md/seo-geo-guide.md: '핵심만 보기' 류의 한 줄 요약 박스 권장."""
    assert "핵심만 보기" in _read()


def test_has_closing_cta():
    """style-guide.md 마무리 패턴: '(클릭!) ~해보세요' 형태의 CTA."""
    assert "(클릭!)" in _read()


def test_has_hashtag_line_at_end():
    lines = [l for l in _read().splitlines() if l.strip()]
    last_line = lines[-1].strip()
    assert re.match(r"^(#[^\s#]+)(\s+#[^\s#]+)*$", last_line), (
        f"마지막 줄이 해시태그 형식이 아님: {last_line!r}"
    )
