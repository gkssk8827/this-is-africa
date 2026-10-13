"""
topic_queue.py
===============
notion-topics.json(노션에서 가져온 Q&A 목록)과 publish-state.json(발행 이력)을 비교해서,
"다음에 발행할 주제"를 순서대로 하나씩 꺼내주는 스크립트.

TIA 프로젝트는 주제가 고객상담 Q&A로 고정되어 있어 trend-scout처럼 매번 새 주제를
찾지 않는다. 대신 노션 목록 순서(= 빈도 내림차순 우선순위)를 그대로 따라가며,
아직 발행하지 않은 것 중 맨 앞 항목을 순차적으로 하나씩 소비한다.

이미 발행된 주제인지는 노션 자체의 "블로그 발행여부" 컬럼이 아니라, 이 프로젝트가
관리하는 output/publish-state.json 하나로만 추적한다(노션 컬럼은 사람이 별도 용도로
쓸 수도 있어 신뢰하지 않음).

서브커맨드
----------
next        아직 발행하지 않은 다음 주제 1개를 JSON으로 출력
mark-done   주제 하나를 "발행 완료"로 기록 (5단계 발행 성공 직후 호출)
status      전체 진행 상황 요약 출력 (총 개수 / 완료 수 / 남은 수)

사용 예시
---------
python scripts/topic_queue.py next
python scripts/topic_queue.py mark-done --id 3f9a2c1b4d0e --topic-dir "output/상품-가격은-어떻게-표기되어-있나요"
python scripts/topic_queue.py status
"""

import argparse
import json
import sys
from datetime import date
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
TOPICS_PATH = ROOT_DIR / "output" / "topics" / "notion-topics.json"
STATE_PATH = ROOT_DIR / "output" / "publish-state.json"


def _load_topics() -> list:
    if not TOPICS_PATH.exists():
        print(
            f"{TOPICS_PATH} 가 없습니다. 먼저 `python scripts/fetch_notion_topics.py`를 실행하세요.",
            file=sys.stderr,
        )
        sys.exit(1)
    return json.loads(TOPICS_PATH.read_text(encoding="utf-8"))


def _load_state() -> dict:
    if not STATE_PATH.exists():
        return {"published": {}}
    return json.loads(STATE_PATH.read_text(encoding="utf-8"))


def _save_state(state: dict) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def cmd_next(args) -> None:
    topics = _load_topics()
    state = _load_state()
    published = state.get("published", {})

    for topic in topics:
        if topic["id"] not in published:
            print(json.dumps(topic, ensure_ascii=False, indent=2))
            return

    print(
        "노션 큐에 아직 발행하지 않은 주제가 더 없습니다. "
        "노션 페이지에 새 항목이 추가됐다면 `python scripts/fetch_notion_topics.py`로 다시 가져오세요.",
        file=sys.stderr,
    )
    sys.exit(1)


def cmd_mark_done(args) -> None:
    state = _load_state()
    publish_date = args.date or date.today().isoformat()
    state.setdefault("published", {})[args.id] = {
        "date": publish_date,
        "topic_dir": args.topic_dir,
    }
    _save_state(state)
    print(f"{args.id} 를 발행 완료로 기록했습니다 (date={publish_date}, topic_dir={args.topic_dir}).")


def cmd_status(args) -> None:
    topics = _load_topics()
    state = _load_state()
    published = state.get("published", {})
    done = sum(1 for t in topics if t["id"] in published)
    total = len(topics)
    print(f"전체 {total}개 중 {done}개 발행 완료, {total - done}개 남음.")


def main():
    parser = argparse.ArgumentParser(description="노션 주제 큐에서 다음 발행 대상을 관리")
    sub = parser.add_subparsers(dest="command", required=True)

    nxt = sub.add_parser("next", help="아직 발행하지 않은 다음 주제 1개를 출력")
    nxt.set_defaults(func=cmd_next)

    done = sub.add_parser("mark-done", help="주제를 발행 완료로 기록")
    done.add_argument("--id", required=True, help="notion-topics.json의 topic id")
    done.add_argument("--date", default=None, help="발행 완료 날짜 (YYYY-MM-DD, 기본값: 오늘)")
    done.add_argument("--topic-dir", required=True, help="해당 주제의 output/[주제] 폴더 경로")
    done.set_defaults(func=cmd_mark_done)

    stat = sub.add_parser("status", help="전체 진행 상황 요약")
    stat.set_defaults(func=cmd_status)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
