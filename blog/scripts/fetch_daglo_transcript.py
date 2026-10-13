"""
fetch_daglo_transcript.py
==========================
다글로(daglo.ai) 공유 페이지에서 방송 받아쓰기 스크립트를 발화 단위(화자·타임스탬프·텍스트)로
긁어와 텍스트 파일로 저장하는 스크립트.

**왜 필요한가**: 다글로 공유 페이지(`https://daglo.ai/share/...`)는 완전히 JS로 렌더링되는
가상 스크롤 목록이다. WebFetch/curl로는 빈 껍데기(또는 "요약을 제공하지 않는 보드입니다" 같은
플레이스홀더)만 보이고 실제 발화 데이터는 읽히지 않는다 — `fetch_notion_topics.py`가 노션
테이블을 다루는 것과 똑같은 문제라, 여기서도 Playwright로 실제 브라우저 렌더링 후 목록을
스크롤하며 전체 발화를 수집한다(2026-07-15, broadcast 카테고리 신규 방식 도입 중 확인됨).

**주의**: 다글로가 자동으로 붙이는 화자 라벨("참석자 1", "참석자 2", ...)은 익명 라벨이며
실명이 아니다. 어느 참석자 번호가 특정 인물(예: 박다애 대표)인지는 이 스크립트가 알아낼 수
없다 — 인물 확인은 다른 소스(언론 보도 등)로 하고, 화면 캡처 대상 구간은 영상을 직접 보며
확인해야 한다.

사용 예시
---------
python scripts/fetch_daglo_transcript.py "https://daglo.ai/share/PlqPKAGSq4W8nj0p" \\
    --out ../products/on-air-transcripts/ebs-worldtrip-southafrica-1.txt \\
    --title "세계테마기행 이토록 우아한 남아프리카공화국 1부 - 케이프타운"

산출물은 `[mm:ss] 참석자 N: 대사` 형식의 텍스트 파일이다.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright


def log(msg: str):
    print(f"[fetch_daglo_transcript] {msg}")


def _extract_rows(page):
    return page.eval_on_selector_all(
        "div[data-index]",
        """
        (els) => els.map(el => {
            const idx = el.getAttribute('data-index');
            const btn = el.querySelector('button[title]');
            const speaker = btn ? btn.getAttribute('title') : null;
            const timeSpan = el.querySelector('.hasSpeaker span.shrink-0');
            const time = timeSpan ? timeSpan.textContent.trim() : null;
            const textNodes = el.querySelector('p.textNodes');
            const text = textNodes ? textNodes.textContent.trim() : null;
            return {idx, speaker, time, text};
        })
        """,
    )


def scrape(url: str, max_scrolls: int = 400, stall_limit: int = 15) -> list[dict]:
    rows_by_idx: dict[int, dict] = {}
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.goto(url, wait_until="networkidle", timeout=60000)
        page.wait_for_timeout(2000)

        scroll_container = page.evaluate_handle(
            """
            () => {
                let el = document.querySelector('div[data-index]');
                while (el) {
                    if (el.scrollHeight > el.clientHeight + 10) return el;
                    el = el.parentElement;
                }
                return null;
            }
            """
        )

        stall = 0
        last_count = 0
        for _ in range(max_scrolls):
            for r in _extract_rows(page):
                if r["idx"] is not None:
                    rows_by_idx[int(r["idx"])] = r
            if scroll_container:
                page.evaluate(
                    "(el) => { el.scrollTop = el.scrollTop + el.clientHeight * 0.8; }",
                    scroll_container,
                )
            page.wait_for_timeout(150)
            if len(rows_by_idx) == last_count:
                stall += 1
            else:
                stall = 0
            last_count = len(rows_by_idx)
            if stall > stall_limit:
                break
        browser.close()

    return [rows_by_idx[i] for i in sorted(rows_by_idx.keys())]


def main():
    parser = argparse.ArgumentParser(description="다글로 공유 페이지에서 발화별 스크립트 추출")
    parser.add_argument("url", help="다글로 공유 링크 (https://daglo.ai/share/...)")
    parser.add_argument("--out", required=True, help="저장할 텍스트 파일 경로")
    parser.add_argument("--title", default=None, help="파일 맨 위에 남길 제목(선택)")
    args = parser.parse_args()

    rows = scrape(args.url)
    if not rows:
        log("발화를 하나도 추출하지 못했습니다 — 링크가 유효한지, 페이지가 비공개는 아닌지 확인하세요.")
        sys.exit(1)

    missing = [r for r in rows if not r["time"] or not r["text"]]
    if missing:
        log(f"경고: {len(missing)}개 행에서 시간/텍스트가 비어 있습니다(누락 가능성).")

    lines = []
    if args.title:
        lines.append(f"# {args.title}")
    lines.append(
        "# 출처: 다글로(daglo.ai) 공유 페이지 받아쓰기, Playwright로 재추출"
        " (참석자 번호는 다글로 자동 화자분리 라벨이며 실명 아님 — 인물 확인은 별도 소스 필요)"
    )
    lines.append("")
    for r in rows:
        lines.append(f"[{r['time']}] {r['speaker']}: {r['text']}")

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines), encoding="utf-8")
    log(f"{len(rows)}개 발화 추출 완료 -> {out_path}")


if __name__ == "__main__":
    main()
