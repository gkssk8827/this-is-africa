"""
fetch_notion_topics.py
=======================
TIA(디스이즈아프리카) 고객상담 Q&A 노션 데이터베이스를 읽어와
output/topics/notion-topics.json 으로 저장하는 스크립트.

TIA 프로젝트는 blog(원본) 프로젝트와 달리 주제가 "고객상담 Q&A" 하나로 고정되어
있어, 매 실행마다 trend-scout으로 새 주제를 발굴하지 않는다. 대신 노션 페이지에
정리된 질문 목록을 순서대로 하나씩 블로그 글감으로 소비한다.

이 노션 페이지는 테이블(데이터베이스) 뷰이고 완전히 JS로 렌더링되기 때문에
WebFetch/curl로는 실제 행 데이터를 읽을 수 없다(빈 앱 껍데기만 반환됨). 대신
publish.py와 동일하게 Playwright로 실제 브라우저를 띄워 렌더링한 뒤, 가상 스크롤로
일부만 그려지는 테이블을 끝까지 스크롤하며 모든 행을 수집한다.

사용 예시
---------
python scripts/fetch_notion_topics.py

산출물: output/topics/notion-topics.json
[
  {
    "id": "<질문 텍스트 기반 안정 해시>",
    "question": "...",
    "answer": "...",
    "frequency": "134",
    "category": "상품·프로그램",
    "keywords": "가격,경비,달러,원화,분리표기,환율",
    "source_call": "250422_095854",
    "fact_check_needed": "",
    "notion_publish_status": ""
  },
  ...
]

컬럼 순서는 노션 화면에 보이는 순서를 그대로 따르므로(현재 뷰 = 빈도 내림차순),
이 목록 순서가 곧 "발행 우선순위 = 순차 발행 순서"가 된다.
"""

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT_DIR = Path(__file__).resolve().parent.parent
TOPICS_DIR = ROOT_DIR / "output" / "topics"
OUT_PATH = TOPICS_DIR / "notion-topics.json"

# TIA 고객상담 Q&A 데이터베이스 공개 링크. 노션에서 링크가 바뀌면 여기만 갱신하면 된다.
DEFAULT_NOTION_URL = (
    "https://fixed-park-59c.notion.site/1fda91878d1847fa96b2de738177128d"
    "?v=ce8570f29c6a4b7e82f8b13219c8edb5&source=copy_link"
)

# 컬럼 헤더(노션에 보이는 그대로) -> 내부 필드명 매핑.
# 노션에서 컬럼 순서를 바꾸거나 컬럼을 추가/삭제해도, 헤더 텍스트만 같으면 그대로 동작한다.
HEADER_MAP = {
    "질문": "question",
    "모범응답": "answer",
    "빈도": "frequency",
    "카테고리": "category",
    "핵심키워드": "keywords",
    "출처통화": "source_call",
    "사실확인필요": "fact_check_needed",
    "블로그 발행여부": "notion_publish_status",
}

SCROLL_CONTAINER_SELECTOR = ".notion-scroller.vertical.horizontal"
ROW_SELECTOR = ".notion-table-view-row"
HEADER_CELL_SELECTOR = ".notion-table-view-header-cell"
CELL_SELECTOR = ".notion-table-view-cell"


def _read_header_order(page):
    """노션 테이블의 컬럼 순서(col-index -> 필드명)를 읽는다."""
    headers = page.locator(HEADER_CELL_SELECTOR)
    count = headers.count()
    col_to_field = {}
    for i in range(count):
        text = headers.nth(i).inner_text().strip()
        field = HEADER_MAP.get(text)
        if field:
            col_to_field[str(i)] = field
    missing = set(HEADER_MAP.values()) - set(col_to_field.values())
    if missing:
        print(
            f"경고: 노션 테이블에서 다음 컬럼을 찾지 못했습니다 (헤더 텍스트가 바뀌었을 수 있음): {missing}",
            file=sys.stderr,
        )
    return col_to_field


def _collect_rendered_rows(page):
    """현재 화면(가상 스크롤)에 그려진 행들을 {row_index: {col_index: text}} 형태로 수집한다."""
    return page.evaluate(
        """
        () => {
          const out = {};
          document.querySelectorAll('.notion-table-view-row').forEach(row => {
            const cells = row.querySelectorAll('.notion-table-view-cell');
            let rowIdx = null;
            const vals = {};
            cells.forEach(c => {
              const ri = c.dataset.rowIndex, ci = c.dataset.colIndex;
              if (ri !== undefined) rowIdx = ri;
              vals[ci] = c.innerText;
            });
            if (rowIdx !== null) out[rowIdx] = vals;
          });
          return out;
        }
        """
    )


def _scroll_and_collect_all(page, max_steps=400, scroll_step=700, settle_pause=0.3):
    """가상 스크롤 테이블을 끝까지 내리며 모든 행을 모은다."""
    all_rows = {}
    last_scroll_top = -1
    stable_count = 0

    for _ in range(max_steps):
        all_rows.update(_collect_rendered_rows(page))

        info = page.evaluate(
            """
            (sel) => {
              const el = document.querySelector(sel);
              if (!el) return null;
              return { st: el.scrollTop, sh: el.scrollHeight, ch: el.clientHeight };
            }
            """,
            SCROLL_CONTAINER_SELECTOR,
        )
        if info is None:
            break

        reached_bottom = info["st"] + info["ch"] >= info["sh"] - 2
        if info["st"] == last_scroll_top:
            stable_count += 1
        else:
            stable_count = 0
        last_scroll_top = info["st"]

        if reached_bottom or stable_count > 3:
            break

        page.evaluate(
            """
            (args) => {
              const el = document.querySelector(args.sel);
              el.scrollTop = el.scrollTop + args.step;
            }
            """,
            {"sel": SCROLL_CONTAINER_SELECTOR, "step": scroll_step},
        )
        time.sleep(settle_pause)

    return all_rows


def _topic_id(question: str) -> str:
    """질문 텍스트 기반 안정 ID. 노션 쪽 행 순서가 바뀌어도 동일 질문이면 항상 같은 id를 갖는다."""
    return hashlib.sha1(question.strip().encode("utf-8")).hexdigest()[:12]


def fetch_topics(url: str, headless: bool = True) -> list:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        page = browser.new_page(viewport={"width": 1600, "height": 1000})
        page.goto(url, wait_until="load", timeout=60000)
        time.sleep(5)  # 노션 SPA 초기 렌더링 대기

        col_to_field = _read_header_order(page)
        raw_rows = _scroll_and_collect_all(page)
        browser.close()

    topics = []
    for row_idx in sorted(raw_rows.keys(), key=int):
        raw = raw_rows[row_idx]
        record = {field: raw.get(col, "").strip() for col, field in col_to_field.items()}
        question = record.get("question", "")
        if not question:
            continue
        record["id"] = _topic_id(question)
        record["_row_order"] = int(row_idx)
        topics.append(record)

    return topics


def main():
    parser = argparse.ArgumentParser(description="노션 TIA 고객상담 Q&A 페이지를 읽어 output/topics/notion-topics.json으로 저장")
    parser.add_argument("--url", default=DEFAULT_NOTION_URL, help="노션 페이지(테이블 뷰) 공개 링크")
    parser.add_argument("--headed", action="store_true", help="브라우저 창을 띄워서 실행 (디버깅용)")
    parser.add_argument("--out", default=str(OUT_PATH), help="출력 JSON 경로")
    args = parser.parse_args()

    topics = fetch_topics(args.url, headless=not args.headed)

    if not topics:
        print("노션 페이지에서 주제를 하나도 읽어오지 못했습니다. --headed로 다시 실행해 화면을 직접 확인하세요.", file=sys.stderr)
        sys.exit(1)

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(topics, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"{len(topics)}개 주제를 {out_path}에 저장했습니다.")


if __name__ == "__main__":
    main()
