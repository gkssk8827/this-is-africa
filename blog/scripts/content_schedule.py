"""
content_schedule.py
====================
TIA 블로그는 주제가 7개 고정 카테고리로 한정되어 있다:
  1. broadcast       — 방송 참여 관련 (최우선순위)
  2. notice          — 공휴 연휴 공지, 설명회 공지 (2순위)
  3. southeast_trend — 동남부 아프리카 여행 관련 "긍정적" 최신 이슈/트렌드 (3순위, 실시간 검색)
  4. product_daily   — 상품 관련(일자별 연재/후기형)      ┐
  5. review          — 여행자 실제 후기형                  │ "그 외" — fallback_rotation 순환
  6. qna             — 여행자 Q&A (기존 노션 큐)            │ (4순위)
  7. book            — 《이토록아프리카》 도서 관련         ┘

**2026-07-15 개편: 매일 자동 실행(GitHub Actions) 대신, 주 1회 로컬에서 직접 실행하며 한 번
돌릴 때 7건(기본값)을 한 번에 배치로 뽑는다.** 이 스크립트는 topic_queue.py(노션 Q&A 전용)를
대체하는 게 아니라 그 위에 얹히는 상위 스케줄러다. product_daily/review/broadcast/notice/book
5개 카테고리는 output/topics/content-schedule.json 에 미리 정리해둔 목록을 순서대로 소비하고,
qna 카테고리만 예외적으로 output/topics/notion-topics.json(노션에서 실시간으로 가져온 캐시)을
그대로 재사용한다. southeast_trend는 정적 목록이 전혀 없다 — 매 실행마다 오케스트레이터가
researcher에게 그날 기준 실시간 웹검색으로 "동남부 아프리카 여행 관련 긍정적 이슈"를 직접
찾아 주제를 정하도록 위임한다(이 스크립트는 이 카테고리 슬롯을 needs_topic_search:true 로만
표시하고, 실제 주제 선정은 하지 않는다).

**발행 우선순위(각 배치 실행마다)**: content-schedule.json의 "priority_tiers" 배열
(["broadcast", "notice", "southeast_trend"]) 순서대로, 각 카테고리에 남아있는(pending) 만큼
먼저 채우고, 그러고도 슬롯이 남으면 "fallback_rotation" 배열(그 외 4개 카테고리 순환 패턴)로
나머지를 채운다. fallback_rotation은 지금까지 발행 완료된 총 개수(그 4개 카테고리 합산) %
len(fallback_rotation) 로 "지금이 몇 번째 슬롯인지"를 계산하는 방식이라 별도 커서 파일이
필요 없다. 특정 슬롯의 카테고리가 소진됐으면 그 슬롯은 건너뛰고 다음 카테고리를 시도한다.

공지(notice)/급한 방송(broadcast)/여행자 후기(review) 항목은 자동 생성 대상이 아니므로, 이
스크립트가 건드리지 않는다 — content-schedule.json의 "items" 배열에 아래 형식으로 직접
추가하면 된다:
  {
    "id": "notice-2026추석연휴",
    "category": "notice",
    "title_hint": "2026 추석 연휴 예약 마감 안내",
    "source": "수기입력",
    "raw_content": "여기에 공지 원문/후기 원문 텍스트를 그대로 붙여넣는다. researcher가 이 필드가 있으면 그 내용을 1차 근거로 그대로 사용하고, 없으면 리서치를 진행하지 않고 원문이 필요하다고 보고한다.",
    "status": "pending"
  }
broadcast 신규 방식은 raw_content(받아쓰기 스크립트) + drive_link(방송 영상 구글드라이브
링크) 필드를 함께 채운다 (자세한 내용은 content-schedule.json 상단 주석과 CLAUDE.md 참고).
급한 항목을 새치기시키고 싶으면 items 배열에서 원하는 위치(앞쪽)에 끼워 넣으면 된다 —
같은 카테고리 안에서는 배열 순서대로 소비되기 때문.

서브커맨드
----------
next-batch      이번 실행에서 발행할 주제 N개(기본 7개)를 우선순위대로 JSON 배열로 출력
next            다음에 발행할 주제 1개를 JSON으로 출력 (없으면 has_topic:false) — 단발 실행용
mark-done       특정 카테고리+id를 발행완료로 기록 (5단계 발행 성공 직후 호출)
history         발행 이력 조회 (최근 N개, 카테고리 필터 가능)
status          카테고리별 총/완료/남은 개수 요약
check-keywords  후보 키워드가 최근 30일 내 이미 쓰였는지 미리 확인 (southeast_trend용)

30일 키워드 재사용 금지 (2026-07-15 추가)
-------------------------------------------
같은 핵심 키워드로 30일(KEYWORD_BAN_DAYS) 안에 다시 발행하지 않도록 자동으로 막는다.
- **적용 방식(옵트인)**: 항목(item)에 `"keywords": ["케냐", "허니문"]` 필드가 있어야 검사가
  적용된다. 필드가 없는 항목(대부분의 기존 카탈로그 항목)은 이 검사를 그냥 통과한다 — 예를
  들어 product_daily의 "TIA 스탠다드 24일" 4부작(overview/highlight/booking_tip/inclusion)처럼
  같은 상품명을 의도적으로 반복하는 시리즈는 keywords 필드를 안 채우면 이 규칙의 영향을
  받지 않는다.
- **qna는 예외적으로 자동 적용된다** — notion의 "핵심키워드" 컬럼이 이미 존재하므로, next_from_qna가
  항상 이 필드를 검사한다.
- **충돌 시 동작**: `next-batch`/`next`가 후보를 훑을 때, 키워드가 최근 30일 내 발행 이력과
  겹치면 그 항목을 건너뛰고 **같은 카테고리의 다음 항목**을 시도한다("다른 주제로 넘어감"). 그
  카테고리 전체가 소진/충돌이면 상위 우선순위 로직이 이미 하던 대로 다음 우선순위/카테고리로
  넘어간다 — 별도 처리가 필요 없다.
- **history에 keywords가 쌓여야 검사가 가능하다** — `mark-done` 호출 시 `--keywords`를 직접
  주거나(southeast_trend/신규 broadcast/notice처럼 정적 항목이 없는 경우 필수), 생략하면 qna는
  notion 캐시에서, 그 외는 content-schedule.json items에서 자동으로 찾아 채운다.
- **southeast_trend처럼 주제를 그 자리에서 정하는 경우**, 후보를 확정하기 전에
  `check-keywords --keywords "케냐,허니문"`으로 먼저 검사해서 걸리면 다른 후보를 고른다
  (자세한 내용은 `agents/researcher.md`의 "southeast_trend" 절 참고).

발행 이력(history)에 대하여
----------------------------
`mark-done`으로 기록된 모든 항목은 publish-state.json의 "history" 배열에 title/topic_dir/
source(schedule|manual)/발행시각과 함께 쌓인다. **0단계에서 스케줄대로 나온 주제뿐 아니라,
사용자가 이번 실행에서 직접 지정한 주제(예: "이 후기 써줘")도 실제 발행이 끝나면 반드시
mark-done을 호출해 --source manual로 기록한다.** (CLAUDE.md 참고) 그래야 다음에 주제를 정할 때
`content_schedule.py history`로 지금까지 뭘 다뤘는지 확인하고 같은 소재·같은 각도를 반복하지
않을 수 있다. southeast_trend는 실시간 검색 주제라 id를 새로 만들어 쓴다(예:
southeast_trend-2026-07-15-honeymoon-ranking). 수기 주제는 애초에 content-schedule.json의
items에 없는 id를 써도 되고(그 경우 fallback_rotation 소비 로직에는 영향 없음), --id는 알아보기
쉬운 슬러그를 새로 만들어 쓰면 된다 (예: review-정모-킬리만자로-2026-07).

사용 예시
---------
python scripts/content_schedule.py next-batch --count 7
python scripts/content_schedule.py next
python scripts/content_schedule.py mark-done --category book --id book-1bu-등록금환불세계여행 --title "..." --topic-dir "output/..." --source schedule
python scripts/content_schedule.py mark-done --category review --id review-정모-킬리만자로-2026-07 --title "킬리만자로 후기" --topic-dir "output/..." --source manual
python scripts/content_schedule.py history --category review --limit 10
python scripts/content_schedule.py status
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
SCHEDULE_PATH = ROOT_DIR / "output" / "topics" / "content-schedule.json"
NOTION_TOPICS_PATH = ROOT_DIR / "output" / "topics" / "notion-topics.json"
STATE_PATH = ROOT_DIR / "output" / "publish-state.json"

ALL_CATEGORIES = ["product_daily", "review", "broadcast", "notice", "qna", "book", "southeast_trend"]
FALLBACK_CATEGORIES = ["product_daily", "review", "qna", "book"]  # "그 외" (fallback_rotation 대상)
DEFAULT_PRIORITY_TIERS = ["broadcast", "notice", "southeast_trend"]
DEFAULT_FALLBACK_ROTATION = ["product_daily", "qna", "book", "qna", "book", "qna", "review"]
KEYWORD_BAN_DAYS = 30  # 같은 핵심 키워드는 이 기간(일) 안에 재사용 금지


def parse_keywords(raw) -> set:
    """콤마 구분 문자열이든 리스트든 정규화해서 trim된 non-empty 키워드 set으로 반환."""
    if not raw:
        return set()
    if isinstance(raw, str):
        parts = raw.split(",")
    else:
        parts = raw
    return {p.strip() for p in parts if p and p.strip()}


def recent_keyword_conflict(keywords: set, state: dict, days: int = KEYWORD_BAN_DAYS):
    """keywords 중 하나라도 최근 `days`일 안에 발행된 history 항목의 keywords와 겹치면
    그 충돌 정보를 반환한다. keywords가 비어있으면(= 이 항목에 키워드 정보가 없으면) 검사하지
    않고 None을 반환한다(옵트인 방식 — 키워드를 채워넣은 항목에만 이 규칙이 적용됨)."""
    if not keywords:
        return None
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    for h in state.get("history", []):
        published_at = h.get("published_at")
        if not published_at:
            continue
        try:
            published_dt = datetime.fromisoformat(published_at)
        except ValueError:
            continue
        if published_dt < cutoff:
            continue
        overlap = keywords & set(h.get("keywords") or [])
        if overlap:
            return {
                "overlap_keywords": sorted(overlap),
                "conflict_with": {
                    "id": h.get("id"),
                    "title": h.get("title"),
                    "category": h.get("category"),
                    "published_at": published_at,
                },
            }
    return None


def load_json(path: Path, default):
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def save_state(state: dict):
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def load_state() -> dict:
    state = load_json(STATE_PATH, {})
    for cat in ALL_CATEGORIES:
        state.setdefault(cat, [])
    state.setdefault("history", [])
    return state


def load_schedule() -> dict:
    schedule = load_json(SCHEDULE_PATH, None)
    if schedule is None:
        print(f"콘텐츠 스케줄 파일이 없습니다: {SCHEDULE_PATH}", file=sys.stderr)
        sys.exit(1)
    return schedule


def next_from_static(schedule: dict, state: dict, category: str, extra_exclude: set | None = None):
    """product_daily/review/broadcast/notice/book — items 배열에서 순서대로.

    항목에 "keywords" 필드가 있고, 그 키워드가 최근 KEYWORD_BAN_DAYS일 안에 이미 쓰였다면
    이 항목은 건너뛰고 같은 카테고리의 다음 항목을 시도한다(자동으로 "다른 주제로 이동").
    keywords가 없는 항목(대부분의 기존 카탈로그 항목)은 이 검사 자체가 적용되지 않는다.
    """
    done_ids = set(state.get(category, []))
    if extra_exclude:
        done_ids = done_ids | extra_exclude
    for item in schedule.get("items", []):
        if item.get("category") != category:
            continue
        if item.get("status") == "done":
            continue
        if item["id"] in done_ids:
            continue
        conflict = recent_keyword_conflict(parse_keywords(item.get("keywords")), state)
        if conflict:
            print(f"[keyword-skip] {category}/{item['id']} — 최근 {KEYWORD_BAN_DAYS}일 내 겹치는 키워드"
                  f" {conflict['overlap_keywords']} (충돌: {conflict['conflict_with'].get('title') or conflict['conflict_with'].get('id')})."
                  f" 다음 항목으로 넘어감.", file=sys.stderr)
            continue
        return item
    return None


def next_from_qna(state: dict, extra_exclude: set | None = None):
    """qna — 기존 topic_queue.py와 동일한 소스(notion-topics.json)를 그대로 사용.

    노션의 "핵심키워드"(keywords) 필드를 자동으로 검사해, 최근 KEYWORD_BAN_DAYS일 안에 겹치는
    키워드를 쓴 질문이면 건너뛰고 다음 질문으로 넘어간다.
    """
    topics = load_json(NOTION_TOPICS_PATH, [])
    done_ids = set(state.get("qna", []))
    if extra_exclude:
        done_ids = done_ids | extra_exclude
    for t in topics:
        if t["id"] in done_ids:
            continue
        conflict = recent_keyword_conflict(parse_keywords(t.get("keywords")), state)
        if conflict:
            print(f"[keyword-skip] qna/{t['id']} — 최근 {KEYWORD_BAN_DAYS}일 내 겹치는 키워드"
                  f" {conflict['overlap_keywords']} (충돌: {conflict['conflict_with'].get('title') or conflict['conflict_with'].get('id')})."
                  f" 다음 항목으로 넘어감.", file=sys.stderr)
            continue
        return {
            "id": t["id"],
            "category": "qna",
            "title_hint": t.get("question", ""),
            "source": "notion",
            "raw": t,
        }
    return None


def _next_for_category(schedule: dict, state: dict, category: str, extra_exclude: set):
    if category == "qna":
        return next_from_qna(state, extra_exclude)
    return next_from_static(schedule, state, category, extra_exclude)


def build_batch(schedule: dict, state: dict, count: int, trend_max: int):
    """우선순위(priority_tiers) → fallback_rotation 순으로 최대 count개 슬롯을 채운다."""
    priority_tiers = schedule.get("priority_tiers") or DEFAULT_PRIORITY_TIERS
    fallback_rotation = schedule.get("fallback_rotation") or DEFAULT_FALLBACK_ROTATION

    slots: list[dict] = []
    picked_ids: dict[str, set] = {}  # category -> {id, ...} (이번 배치 안에서 이미 뽑은 것)

    def mark_picked(category: str, item_id: str):
        picked_ids.setdefault(category, set()).add(item_id)

    # 1~2순위: broadcast, notice — pending인 만큼 먼저 채움
    # 3순위: southeast_trend — 정적 목록이 없으므로 실시간 검색 필요 슬롯으로만 표시 (trend_max개 한도)
    for category in priority_tiers:
        if len(slots) >= count:
            break
        if category == "southeast_trend":
            remaining = count - len(slots)
            n_trend = min(trend_max, remaining)
            for _ in range(n_trend):
                slots.append({
                    "category": "southeast_trend",
                    "needs_topic_search": True,
                    "note": "정적 목록 없음 — researcher가 오늘 날짜 기준 실시간 웹검색으로 동남부 아프리카 여행 관련 긍정적 이슈를 찾아 주제를 직접 정한다.",
                })
            continue
        while len(slots) < count:
            item = _next_for_category(schedule, state, category, picked_ids.get(category, set()))
            if not item:
                break
            mark_picked(category, item["id"])
            slots.append(item)

    # 4순위: 그 외(fallback_rotation) — 남은 슬롯을 카테고리 순환으로 채움
    if len(slots) < count and fallback_rotation:
        total_done = sum(len(state.get(cat, [])) for cat in FALLBACK_CATEGORIES)
        n = len(fallback_rotation)
        offset = 0
        stall_guard = 0
        while len(slots) < count and stall_guard < n * (count + 1):
            idx = (total_done + offset) % n
            category = fallback_rotation[idx]
            item = _next_for_category(schedule, state, category, picked_ids.get(category, set()))
            offset += 1
            stall_guard += 1
            if item:
                mark_picked(category, item["id"])
                slots.append(item)
                total_done += 1  # 다음 슬롯 계산이 실제 소비 순서를 반영하도록

    return slots


def cmd_next_batch(args):
    schedule = load_schedule()
    state = load_state()
    slots = build_batch(schedule, state, args.count, args.trend_max)

    if not slots:
        print(json.dumps({"has_topic": False, "note": "모든 카테고리의 미발행 주제가 소진됐습니다."}, ensure_ascii=False))
        return

    print(json.dumps({
        "has_topic": True,
        "requested_count": args.count,
        "filled_count": len(slots),
        "slots": slots,
    }, ensure_ascii=False, indent=2))


def cmd_next(args):
    schedule = load_schedule()
    state = load_state()
    slots = build_batch(schedule, state, 1, trend_max=1)

    if not slots:
        print(json.dumps({"has_topic": False, "note": "모든 카테고리의 미발행 주제가 소진됐습니다."}, ensure_ascii=False))
        return

    print(json.dumps({"has_topic": True, **slots[0]}, ensure_ascii=False, indent=2))


def _autofill_keywords(category: str, item_id: str) -> set:
    """--keywords가 안 주어졌을 때, qna는 notion 캐시에서, 그 외는 content-schedule.json
    items에서 해당 id의 keywords 필드를 찾아 자동으로 채운다. 못 찾으면 빈 set(검사 미적용)."""
    if category == "qna":
        topics = load_json(NOTION_TOPICS_PATH, [])
        for t in topics:
            if t.get("id") == item_id:
                return parse_keywords(t.get("keywords"))
        return set()
    schedule = load_json(SCHEDULE_PATH, {"items": []})
    for item in schedule.get("items", []):
        if item.get("category") == category and item.get("id") == item_id:
            return parse_keywords(item.get("keywords"))
    return set()


def cmd_mark_done(args):
    if args.category not in ALL_CATEGORIES:
        print(f"알 수 없는 카테고리: {args.category} (허용: {ALL_CATEGORIES})", file=sys.stderr)
        sys.exit(1)
    state = load_state()
    if args.id not in state[args.category]:
        state[args.category].append(args.id)

    keywords = parse_keywords(args.keywords) if args.keywords else _autofill_keywords(args.category, args.id)

    state["history"].append({
        "category": args.category,
        "id": args.id,
        "title": args.title,
        "topic_dir": args.topic_dir,
        "source": args.source,
        "keywords": sorted(keywords),
        "published_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    })
    save_state(state)
    kw_note = f" (키워드: {', '.join(sorted(keywords))})" if keywords else " (키워드 없음 — 30일 재사용 금지 검사 대상 아님)"
    print(f"발행완료 기록: [{args.category}] {args.id}" + (f" — {args.title}" if args.title else "") + kw_note)


def cmd_history(args):
    state = load_state()
    history = state.get("history", [])
    if args.category:
        history = [h for h in history if h.get("category") == args.category]
    history = history[-args.limit:]
    if not history:
        print("발행 이력이 없습니다.")
        return
    for h in history:
        print(f"[{h.get('published_at', '?')}] ({h.get('category')}/{h.get('source', '?')}) "
              f"{h.get('title') or h.get('id')} — {h.get('topic_dir') or ''}")


def cmd_check_keywords(args):
    state = load_state()
    keywords = parse_keywords(args.keywords)
    conflict = recent_keyword_conflict(keywords, state, days=args.days)
    if conflict:
        print(json.dumps({"conflict": True, **conflict}, ensure_ascii=False, indent=2))
    else:
        print(json.dumps({"conflict": False}, ensure_ascii=False))


def cmd_status(args):
    schedule = load_schedule()
    state = load_state()
    topics = load_json(NOTION_TOPICS_PATH, [])

    print("카테고리별 진행 상황")
    print("-" * 50)
    for cat in ALL_CATEGORIES:
        done = len(state.get(cat, []))
        if cat == "southeast_trend":
            print(f"  {cat:14s} 정적 목록 없음(실시간 검색) / 발행 완료 {done:4d}")
            continue
        if cat == "qna":
            total = len(topics)
        else:
            total = sum(1 for i in schedule.get("items", []) if i.get("category") == cat)
        remain = max(total - done, 0)
        print(f"  {cat:14s} 총 {total:4d} / 완료 {done:4d} / 남음 {remain:4d}")
    print("-" * 50)
    print(f"  priority_tiers: {schedule.get('priority_tiers') or DEFAULT_PRIORITY_TIERS}")
    print(f"  fallback_rotation(그 외): {schedule.get('fallback_rotation') or DEFAULT_FALLBACK_ROTATION}")


def main():
    parser = argparse.ArgumentParser(description="TIA 블로그 카테고리 로테이션 발행 스케줄러")
    sub = parser.add_subparsers(dest="command", required=True)

    batch = sub.add_parser("next-batch", help="이번 실행에서 발행할 주제 N개(기본 7개)를 우선순위대로 조회")
    batch.add_argument("--count", type=int, default=7, help="이번 배치에서 뽑을 주제 개수 (기본 7 = 주 1회 7일치)")
    batch.add_argument("--trend-max", type=int, default=2,
                        help="southeast_trend(동남부 여행 긍정 이슈) 슬롯 최대 개수 (기본 2 — 무제한으로 두면 방송/공지가 없는 주엔 트렌드가 배치 대부분을 차지할 수 있어 상한을 둠)")
    batch.set_defaults(func=cmd_next_batch)

    nxt = sub.add_parser("next", help="다음 발행 주제 1개 조회 (단발 실행용)")
    nxt.set_defaults(func=cmd_next)

    md = sub.add_parser("mark-done", help="주제 하나를 발행완료로 기록 (스케줄 소비분이든 수기 주제든 전부 여기로 기록)")
    md.add_argument("--category", required=True, choices=ALL_CATEGORIES)
    md.add_argument("--id", required=True)
    md.add_argument("--title", default=None, help="글 제목 (이력 조회 시 사람이 알아보기 위함)")
    md.add_argument("--topic-dir", default=None)
    md.add_argument("--source", default="schedule", choices=["schedule", "manual"],
                     help="schedule=content-schedule.json/notion에서 순서대로 나온 주제, manual=사용자가 이번에 직접 지정한 주제")
    md.add_argument("--keywords", default=None,
                     help="이 글의 핵심 키워드(콤마 구분, 예: '케냐,허니문'). 생략하면 qna는 notion 캐시, "
                          "그 외는 content-schedule.json items에서 자동으로 찾아 채운다(둘 다 없으면 빈 값 = "
                          "30일 재사용 금지 검사 미적용). southeast_trend/신규 broadcast/notice처럼 정적 "
                          "항목이 없는 경우 반드시 직접 지정해야 한다.")
    md.set_defaults(func=cmd_mark_done)

    hist = sub.add_parser("history", help="발행 이력 조회 (새 주제 정할 때 중복/유사 소재 피하는 용도)")
    hist.add_argument("--category", default=None, choices=ALL_CATEGORIES, help="특정 카테고리만 보기")
    hist.add_argument("--limit", type=int, default=20, help="최근 N개만 (기본 20)")
    hist.set_defaults(func=cmd_history)

    st = sub.add_parser("status", help="카테고리별 진행 상황 요약")
    st.set_defaults(func=cmd_status)

    ck = sub.add_parser("check-keywords",
                         help="후보 키워드가 최근 30일 내 이미 쓰였는지 확인 (southeast_trend처럼 "
                              "정적 목록이 없어 주제를 그 자리에서 정할 때, mark-done 전에 미리 검사하는 용도)")
    ck.add_argument("--keywords", required=True, help="검사할 핵심 키워드(콤마 구분, 예: '케냐,허니문')")
    ck.add_argument("--days", type=int, default=KEYWORD_BAN_DAYS, help=f"검사 기간(일), 기본 {KEYWORD_BAN_DAYS}")
    ck.set_defaults(func=cmd_check_keywords)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
