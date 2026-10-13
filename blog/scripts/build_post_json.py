"""
build_post_json.py
===================
assembler가 만든 final.md를 publish.py가 요구하는 포스트 JSON
(title / body_blocks / category / tags)으로 변환하는 스크립트.

블로그 파이프라인: trend-scout -> researcher -> writer -> image-maker -> assembler -> [build_post_json] -> publish

사용 예시
---------
python scripts/build_post_json.py --topic-dir "output/유류할증료-인하-여름성수기-해외항공권-예약급증"

위 명령은 해당 폴더의 final.md를 읽어 같은 폴더에 post.json을 생성합니다.
태그는 final.md 마지막의 "#태그1 #태그2 ..." 해시태그 줄에서 자동으로 추출합니다.

네이버 카테고리(발행 시 분류)는 콘텐츠 카테고리(0단계 content_schedule.py가 정한
product_daily/broadcast/qna/book/review/notice/southeast_trend)에 따라 CATEGORY_MAP으로 자동 매핑됩니다.
[topic-dir]/meta.json에 {"category": "product_daily"} 같은 형식으로 콘텐츠 카테고리가
저장되어 있으면 그걸 읽어 매핑하고, meta.json이 없거나 매핑에 없는 값이면 기본값
"아프리카 여행 정보"로 폴백합니다. --category 옵션으로 직접 override할 수도 있습니다
(수동 실행/테스트용).

실제 네이버 블로그 카테고리 트리(2026-07-14 확인):
  TIA NEW ── TIA 이야기 / TIA LIVE
  아프리카 여행 ── TIA 패키지 여행 / 아프리카 여행 정보
  (트리 밖) 생생 고객 후기

주의
----
- 마크다운 문법 중 표(`| ... |`)와 소제목(`##`, `###`)은 각각 "table"/"heading"
  타입의 별도 body_blocks로 뽑아내, publish.py가 SmartEditor의 실제 표 삽입 기능과
  인용구2(세로선) 스타일로 서식을 입힙니다.
- 인용구(`>`로 시작하는 연속된 줄)는 "quote" 타입 body_block으로 묶여, publish.py가
  SmartEditor의 기본 인용구1(큰따옴표 스타일) 컴포넌트에 그대로 입력합니다. 연속된
  `>` 줄(빈 `>` 줄 포함)이 하나의 인용구 블록으로 합쳐지고, `>`가 아닌 줄을 만나면
  블록이 끝납니다.
- **굵게** 마커는 제목/표 셀에서는 제거하지만, 소제목·인용구·일반 본문에서는
  `**...**` 형태 그대로 body_blocks에 남겨둡니다. publish.py가 이 마커를 실제
  타이핑 중 굵게 토글로 바꿔 입력하므로, 여기서 미리 지워버리면 안 됩니다.
- 이미지 경로는 body_blocks에서 파일 선택창에 그대로 넘어가야 하므로
  절대경로로 변환합니다.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

FIXED_CATEGORY = "아프리카 여행 정보"  # 매핑에 없는 콘텐츠 카테고리(또는 meta.json 없음)일 때 폴백값

# CTA 이미지(파일명 cta.png)에 자동으로 붙이는 카카오톡 채널 링크.
# products/cta/cta.md 스펙 참고 — image-maker가 이 파일명으로 저장하는 것을 전제로 자동 매칭한다.
CTA_IMAGE_LINK = "http://pf.kakao.com/_likkxl/chat"

# 콘텐츠 카테고리(content_schedule.py의 category) -> 실제 네이버 블로그 카테고리 라벨
CATEGORY_MAP = {
    "product_daily": "TIA 패키지 여행",
    "broadcast": "TIA LIVE",
    "notice": "TIA 이야기",
    "book": "TIA 이야기",
    "review": "생생 고객 후기",
    "qna": "아프리카 여행 정보",
    "southeast_trend": "아프리카 여행 정보",
}

IMAGE_LINE_RE = re.compile(r"^!\[(?P<alt>[^\]]*)\]\((?P<path>[^)]+)\)\s*$")
HASHTAG_LINE_RE = re.compile(r"^(#[^\s#]+(?:\s+#[^\s#]+)*)\s*$")
HEADING_RE = re.compile(r"^#{1,6}\s+(.*)$")
BOLD_RE = re.compile(r"\*\*(.+?)\*\*")
BLOCKQUOTE_RE = re.compile(r"^>\s?(.*)$")
TABLE_ROW_RE = re.compile(r"^\|.*\|$")


def clean_inline(text: str) -> str:
    """제목/표 셀처럼 굵게 서식을 입힐 수 없는 자리에서 **마커를 제거한다.

    소제목·인용구·일반 본문은 **마커를 그대로 유지해야 publish.py가 실제
    굵게 서식으로 바꿔 입력할 수 있으므로 이 함수를 쓰지 않는다.
    """
    text = BOLD_RE.sub(r"\1", text)
    return text


def _split_table_row(line: str) -> list[str]:
    inner = line.strip()[1:-1]
    return [clean_inline(cell.strip()) for cell in inner.split("|")]


def _is_table_separator(line: str) -> bool:
    cells = line.strip()[1:-1].split("|")
    return all(re.fullmatch(r":?-{2,}:?", cell.strip()) for cell in cells)


def extract_title(lines: list[str]) -> tuple[str, int]:
    for i, line in enumerate(lines):
        m = HEADING_RE.match(line.strip())
        if m and line.strip().startswith("# "):
            return clean_inline(m.group(1)).strip(), i
    raise ValueError("final.md에서 '# 제목' 형태의 H1을 찾지 못했습니다.")


def extract_tags(lines: list[str]) -> tuple[list[str], int | None]:
    for i in range(len(lines) - 1, -1, -1):
        stripped = lines[i].strip()
        # 빈 줄이나 구분선(---)은 해시태그 줄 뒤에 실수로 남은 노이즈일 수 있으므로 건너뛴다.
        if not stripped or stripped == "---":
            continue
        m = HASHTAG_LINE_RE.match(stripped)
        if m:
            tags = [t[1:] for t in stripped.split()]
            return tags, i
        # 해시태그 줄보다 먼저 다른 본문 줄을 만나면 탐색 중단
        break
    return [], None


def build_body_blocks(lines: list[str], topic_dir: Path, title_idx: int, tags_idx: int | None) -> list[dict]:
    blocks: list[dict] = []
    text_buf: list[str] = []

    def flush_text():
        if text_buf:
            content = "\n".join(text_buf).strip("\n")
            if content.strip():
                blocks.append({"type": "text", "content": content})
            text_buf.clear()

    n = len(lines)
    i = 0
    while i < n:
        # tags_idx(해시태그 줄)는 태그 필드 추출용으로만 쓰고 건너뛰지 않는다 — 본문
        # 맨 아래에도 그대로 노출해야 네이버에 실제로 보이는 텍스트가 된다(2026-07-16,
        # 태그가 발행 패널의 칩으로만 등록되고 본문에는 안 보인다는 문제 확인 후 수정).
        if i == title_idx:
            i += 1
            continue

        line = lines[i].rstrip()
        stripped = line.strip()

        if stripped == "---":
            flush_text()
            i += 1
            continue

        img_match = IMAGE_LINE_RE.match(stripped)
        if img_match:
            flush_text()
            rel_path = img_match.group("path")
            abs_path = (topic_dir / rel_path).resolve()
            image_block = {"type": "image", "path": str(abs_path)}
            if abs_path.name == "cta.png":
                image_block["link"] = CTA_IMAGE_LINK
            blocks.append(image_block)
            i += 1
            continue

        # 표: 헤더 줄 다음이 |---|---| 형태의 구분선이어야 진짜 표로 인정한다.
        if (
            TABLE_ROW_RE.match(stripped)
            and i + 1 < n
            and TABLE_ROW_RE.match(lines[i + 1].strip())
            and _is_table_separator(lines[i + 1].strip())
        ):
            flush_text()
            rows = [_split_table_row(stripped)]
            j = i + 2
            while j < n and TABLE_ROW_RE.match(lines[j].strip()):
                rows.append(_split_table_row(lines[j].strip()))
                j += 1
            blocks.append({"type": "table", "rows": rows})
            i = j
            continue

        if not stripped:
            text_buf.append("")
            i += 1
            continue

        heading_match = HEADING_RE.match(stripped)
        if heading_match:
            flush_text()
            level = len(stripped) - len(stripped.lstrip("#"))
            blocks.append({
                "type": "heading",
                "level": level,
                "content": heading_match.group(1).strip(),
            })
            i += 1
            continue

        quote_match = BLOCKQUOTE_RE.match(stripped)
        if quote_match:
            flush_text()
            quote_buf = [quote_match.group(1)]
            i += 1
            while i < n:
                next_match = BLOCKQUOTE_RE.match(lines[i].strip())
                if not next_match:
                    break
                quote_buf.append(next_match.group(1))
                i += 1
            content = "\n".join(quote_buf).strip("\n")
            if content.strip():
                blocks.append({"type": "quote", "content": content})
            continue

        text_buf.append(stripped)
        i += 1

    flush_text()
    return blocks


def resolve_naver_category(topic_dir: Path, override: str | None) -> str:
    if override:
        return override
    meta_path = topic_dir / "meta.json"
    if meta_path.exists():
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            content_category = meta.get("category")
            if content_category in CATEGORY_MAP:
                return CATEGORY_MAP[content_category]
            if content_category:
                print(f"경고: meta.json의 category '{content_category}'가 CATEGORY_MAP에 없습니다. "
                      f"기본값 '{FIXED_CATEGORY}'로 폴백합니다.")
        except (json.JSONDecodeError, OSError) as e:
            print(f"경고: meta.json을 읽지 못했습니다({e}). 기본값 '{FIXED_CATEGORY}'로 폴백합니다.")
    return FIXED_CATEGORY


def build_post_json(topic_dir: Path, category_override: str | None = None) -> dict:
    final_md = topic_dir / "final.md"
    if not final_md.exists():
        raise FileNotFoundError(f"final.md가 없습니다: {final_md}")

    lines = final_md.read_text(encoding="utf-8").splitlines()

    title, title_idx = extract_title(lines)
    tags, tags_idx = extract_tags(lines)
    body_blocks = build_body_blocks(lines, topic_dir, title_idx, tags_idx)
    naver_category = resolve_naver_category(topic_dir, category_override)

    return {
        "title": title,
        "body_blocks": body_blocks,
        "category": naver_category,
        # 해시태그는 본문 마지막 줄에 이미 노출되므로, 네이버 "태그 편집" 칩 UI에는
        # 다시 입력하지 않는다(2026-08-19 확정). 칩 입력은 중복일 뿐 아니라
        # publish.py의 set_tags()에 알려진 레이스 컨디션(빠르게 연속 입력 시 칩이
        # 뒤섞이는 버그)이 있어 매번 경고/정리 로직을 타야 했다. tags_for_display는
        # 본문에서 실제로 뽑힌 해시태그를 로그로 확인만 하기 위한 용도.
        "tags": [],
        "tags_for_display": tags,
        "drive_image_urls": [],
    }


def main():
    parser = argparse.ArgumentParser(description="final.md를 publish.py용 post.json으로 변환")
    parser.add_argument("--topic-dir", required=True, help="final.md가 들어있는 output/[주제] 폴더 경로")
    parser.add_argument("--out", default=None, help="출력 JSON 경로 (기본: [topic-dir]/post.json)")
    parser.add_argument("--category", default=None,
                         help="네이버 카테고리 직접 지정 (예: 'TIA LIVE'). 지정하면 meta.json보다 우선함")
    args = parser.parse_args()

    topic_dir = Path(args.topic_dir).resolve()
    post = build_post_json(topic_dir, category_override=args.category)

    out_path = Path(args.out).resolve() if args.out else topic_dir / "post.json"
    out_path.write_text(json.dumps(post, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"post.json 생성 완료: {out_path}")
    print(f"  제목: {post['title']}")
    print(f"  네이버 카테고리: {post['category']}")
    print(f"  본문 해시태그(칩 미입력, 확인용): {post['tags_for_display']}")
    print(f"  본문 블록 수: {len(post['body_blocks'])} (이미지 {sum(1 for b in post['body_blocks'] if b['type'] == 'image')}개)")


if __name__ == "__main__":
    main()
