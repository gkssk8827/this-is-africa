"""
5단계(발행) 중 build_post_json.py에 대한 단위 테스트.
실제 LLM 호출이나 네이버 접속 없이, fixtures/topic_sample/final.md만으로 검증한다.
"""

import sys
import tempfile
from pathlib import Path

import pytest

from conftest import FIXTURES_DIR

import build_post_json as bpj

TOPIC_DIR = FIXTURES_DIR / "topic_sample"


def test_extract_title():
    lines = (TOPIC_DIR / "final.md").read_text(encoding="utf-8").splitlines()
    title, idx = bpj.extract_title(lines)
    assert title == "테스트 지표 급증, 지금 무엇을 준비해야 할까요"
    assert idx == 0


def test_extract_tags():
    lines = (TOPIC_DIR / "final.md").read_text(encoding="utf-8").splitlines()
    tags, idx = bpj.extract_tags(lines)
    assert tags == ["테스트태그1", "테스트태그2", "테스트태그3"]
    assert idx is not None


def test_build_post_json_full_structure():
    post = bpj.build_post_json(TOPIC_DIR)

    assert post["title"] == "테스트 지표 급증, 지금 무엇을 준비해야 할까요"
    assert post["category"] == "아프리카 여행 정보"
    assert post["tags"] == ["테스트태그1", "테스트태그2", "테스트태그3"]
    assert post["drive_image_urls"] == []

    image_blocks = [b for b in post["body_blocks"] if b["type"] == "image"]
    text_blocks = [b for b in post["body_blocks"] if b["type"] == "text"]
    assert len(image_blocks) == 2
    assert len(text_blocks) >= 1

    # 이미지 경로는 실제로 존재하는 절대경로여야 인서트 단계(파일 선택창)에서 문제가 없다.
    for block in image_blocks:
        assert Path(block["path"]).is_absolute()
        assert Path(block["path"]).exists()

    # 제목/해시태그 줄은 본문 블록에 다시 섞여 들어가면 안 된다.
    joined_text = "\n".join(b["content"] for b in text_blocks)
    assert "테스트 지표 급증, 지금 무엇을 준비해야 할까요" not in joined_text
    assert "#테스트태그1" not in joined_text


def test_build_post_json_strips_markdown_noise():
    post = bpj.build_post_json(TOPIC_DIR)
    joined_text = "\n".join(b["content"] for b in post["body_blocks"] if b["type"] == "text")
    # 헤더(##)와 인용 기호(>)는 정리돼야 하지만, **굵게** 마커는 publish.py가
    # 실제 굵게 서식으로 바꿔 입력해야 하므로 여기서는 남아 있어야 한다.
    assert "##" not in joined_text
    assert not any(line.strip().startswith(">") for line in joined_text.splitlines())


def test_build_post_json_keeps_bold_markers_in_text_and_heading():
    post = bpj.build_post_json(TOPIC_DIR)
    text_blocks = [b for b in post["body_blocks"] if b["type"] == "text"]
    joined_text = "\n".join(b["content"] for b in text_blocks)
    # fixture의 "> **핵심만 보기**" 블록인용에 있던 굵게 마커가 그대로 보존돼야 한다.
    assert "**핵심만 보기**" in joined_text


def test_build_post_json_strips_bold_in_title_and_table_cells():
    lines = [
        "# **굵은** 제목입니다",
        "",
        "| 구분 | **값** |",
        "|---|---|",
        "| A | **100** |",
        "",
        "#태그1",
    ]
    title, title_idx = bpj.extract_title(lines)
    tags, tags_idx = bpj.extract_tags(lines)
    blocks = bpj.build_body_blocks(lines, TOPIC_DIR, title_idx, tags_idx)

    assert title == "굵은 제목입니다"
    tables = [b for b in blocks if b["type"] == "table"]
    assert tables[0]["rows"] == [["구분", "값"], ["A", "100"]]


def test_build_post_json_extracts_heading_blocks():
    post = bpj.build_post_json(TOPIC_DIR)
    headings = [b for b in post["body_blocks"] if b["type"] == "heading"]
    assert [h["content"] for h in headings] == [
        "1. 왜 테스트 지표가 올랐을까요?",
        "2. 테스트 지표를 숫자로 보면 어느 정도일까요?",
        "FAQ",
        "마무리",
    ]
    assert all(h["level"] == 2 for h in headings)

    # 소제목은 text 블록 안에 섞여 들어가면 안 된다 (별도 heading 블록이어야 서식을 입힐 수 있다).
    text_blocks = [b for b in post["body_blocks"] if b["type"] == "text"]
    joined_text = "\n".join(b["content"] for b in text_blocks)
    assert "왜 테스트 지표가 올랐을까요" not in joined_text


def test_build_post_json_extracts_table_block():
    post = bpj.build_post_json(TOPIC_DIR)
    tables = [b for b in post["body_blocks"] if b["type"] == "table"]
    assert len(tables) == 1
    assert tables[0]["rows"] == [
        ["구분", "이전", "이후"],
        ["A 지표", "100", "150"],
        ["B 지표", "200", "240"],
    ]

    # 표의 원본 파이프(|)/구분선(---) 문자가 text 블록에 그대로 새어나가면 안 된다.
    text_blocks = [b for b in post["body_blocks"] if b["type"] == "text"]
    joined_text = "\n".join(b["content"] for b in text_blocks)
    assert "|" not in joined_text


def test_extract_tags_tolerates_trailing_divider():
    lines = (TOPIC_DIR / "final.md").read_text(encoding="utf-8").splitlines()
    lines_with_noise = lines + ["", "---", ""]
    tags, idx = bpj.extract_tags(lines_with_noise)
    assert tags == ["테스트태그1", "테스트태그2", "테스트태그3"]
    assert idx == len(lines) - 1


def test_extract_tags_returns_empty_when_missing():
    lines = ["# 제목", "", "본문 마지막 줄입니다."]
    tags, idx = bpj.extract_tags(lines)
    assert tags == []
    assert idx is None


def test_missing_final_md_raises(tmp_path):
    empty_dir = tmp_path / "no_final_md"
    empty_dir.mkdir()
    with pytest.raises(FileNotFoundError):
        bpj.build_post_json(empty_dir)


def test_cli_writes_post_json(tmp_path):
    """실제 CLI 진입점(main)까지 --topic-dir/--out으로 실행해 파일이 만들어지는지 확인."""
    out_path = tmp_path / "post.json"
    argv_backup = sys.argv
    try:
        sys.argv = [
            "build_post_json.py",
            "--topic-dir", str(TOPIC_DIR),
            "--out", str(out_path),
        ]
        bpj.main()
    finally:
        sys.argv = argv_backup

    assert out_path.exists()
    import json
    data = json.loads(out_path.read_text(encoding="utf-8"))
    assert data["title"] == "테스트 지표 급증, 지금 무엇을 준비해야 할까요"
