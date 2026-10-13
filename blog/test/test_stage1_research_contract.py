"""
1단계(researcher)는 LLM 서브 에이전트라 실제 리서치 품질(출처의 신뢰도, 최신성 판단 등)을
코드로 테스트할 수는 없다. 대신 agents/researcher.md가 약속하는 "산출물 구조" 계약을
mock research.md 픽스처가 지키는지, 그리고 다음 단계(writer)가 필요로 하는 최소 조건을
갖췄는지만 구조적으로 검증한다.
"""

import re

from conftest import FIXTURES_DIR

RESEARCH_MD = FIXTURES_DIR / "research_sample.md"


def _read():
    return RESEARCH_MD.read_text(encoding="utf-8")


def test_research_file_exists():
    assert RESEARCH_MD.exists()


def test_has_h1_title():
    text = _read()
    lines = text.splitlines()
    assert lines[0].startswith("# "), "research.md는 H1 제목으로 시작해야 한다"


def test_has_survey_date_and_source_count_metadata():
    text = _read()
    assert re.search(r"^>\s*조사 기준일:", text, re.MULTILINE), "조사 기준일 메타데이터 누락"
    assert re.search(r"^>\s*소스 수:", text, re.MULTILINE), "소스 수 메타데이터 누락"


def test_has_overview_section():
    text = _read()
    assert "## 개요" in text


def test_has_at_least_five_numbered_sources():
    text = _read()
    match = re.search(r"## 참고 소스\n(.*)", text, re.DOTALL)
    assert match, "참고 소스 섹션이 없다"
    source_lines = [
        line for line in match.group(1).splitlines()
        if re.match(r"^\d+\.\s", line.strip())
    ]
    assert len(source_lines) >= 5, "researcher.md 규칙상 소스는 5개 이상이어야 한다"


def test_every_source_line_has_url():
    text = _read()
    match = re.search(r"## 참고 소스\n(.*)", text, re.DOTALL)
    source_lines = [
        line for line in match.group(1).splitlines()
        if re.match(r"^\d+\.\s", line.strip())
    ]
    for line in source_lines:
        assert "http" in line, f"출처 URL이 없는 소스 라인: {line!r}"
