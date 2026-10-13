"""
3단계(image-maker)도 LLM 서브 에이전트라 이미지 자체의 디자인 품질은 코드로
검증할 수 없다. 대신 agents/image-maker.md가 약속하는 계약을 mock 픽스처
(draft_before_images.md → draft.md 전환)로 구조적으로 검증한다.

계약:
- draft.md의 모든 [[IMAGE: ...]] 마커가 실제 이미지 마크다운(![...](images/...))으로 치환된다.
- 마커 치환 외에는 문장/순서를 건드리지 않는다.
- 참조된 이미지 파일이 images/ 폴더에 실제로 존재한다.
- image-map.md에 각 이미지가 기록된다.
"""

import re

from conftest import FIXTURES_DIR

TOPIC_DIR = FIXTURES_DIR / "topic_sample"
BEFORE_MD = TOPIC_DIR / "draft_before_images.md"
AFTER_MD = TOPIC_DIR / "draft.md"
IMAGE_MAP = TOPIC_DIR / "images" / "image-map.md"

IMAGE_MARKER_RE = re.compile(r"\[\[IMAGE:\s*(.+?)\]\]")
IMAGE_MD_RE = re.compile(r"!\[(?P<alt>[^\]]*)\]\((?P<path>[^)]+)\)")


def test_no_unreplaced_markers_remain():
    text = AFTER_MD.read_text(encoding="utf-8")
    assert not IMAGE_MARKER_RE.search(text), "치환되지 않은 [[IMAGE: ...]] 마커가 남아있다"


def test_image_count_matches_marker_count():
    before_text = BEFORE_MD.read_text(encoding="utf-8")
    after_text = AFTER_MD.read_text(encoding="utf-8")

    marker_count = len(IMAGE_MARKER_RE.findall(before_text))
    image_count = len(IMAGE_MD_RE.findall(after_text))

    assert marker_count > 0, "테스트 픽스처 자체에 마커가 없다 (픽스처 오류)"
    assert image_count == marker_count, (
        f"마커 {marker_count}개인데 치환된 이미지가 {image_count}개"
    )


def test_referenced_images_exist_on_disk():
    after_text = AFTER_MD.read_text(encoding="utf-8")
    for match in IMAGE_MD_RE.finditer(after_text):
        rel_path = match.group("path")
        assert (TOPIC_DIR / rel_path).exists(), f"참조된 이미지가 실제로 없다: {rel_path}"


def test_non_image_lines_are_unchanged():
    """마커가 있던 줄을 제외한 나머지 문장은 image-maker 전후로 동일해야 한다."""
    before_lines = BEFORE_MD.read_text(encoding="utf-8").splitlines()
    after_lines = AFTER_MD.read_text(encoding="utf-8").splitlines()

    before_non_marker = [l for l in before_lines if not IMAGE_MARKER_RE.search(l)]
    after_non_image = [l for l in after_lines if not IMAGE_MD_RE.search(l)]

    assert before_non_marker == after_non_image, "마커 치환 외의 내용이 변경되었다"


def test_image_map_documents_every_image():
    map_text = IMAGE_MAP.read_text(encoding="utf-8")
    after_text = AFTER_MD.read_text(encoding="utf-8")

    for match in IMAGE_MD_RE.finditer(after_text):
        filename = match.group("path").split("/")[-1]
        assert filename in map_text, f"image-map.md에 {filename} 기록이 없다"


def test_cover_image_is_first_and_documented():
    after_text = AFTER_MD.read_text(encoding="utf-8")
    first_image = IMAGE_MD_RE.search(after_text)
    assert first_image is not None
    assert "cover" in first_image.group("path"), "첫 이미지는 대표 이미지(cover)여야 한다"
