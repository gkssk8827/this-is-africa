"""
0단계(노션 주제 큐)의 topic_queue.py에 대한 단위 테스트.
실제 노션 접속 없이, notion-topics.json/publish-state.json을 tmp 경로에 직접 만들어 검증한다.
"""

import json

import pytest

import topic_queue as tq

TOPICS = [
    {"id": "aaa111", "question": "질문1", "answer": "답1", "frequency": "134"},
    {"id": "bbb222", "question": "질문2", "answer": "답2", "frequency": "106"},
    {"id": "ccc333", "question": "질문3", "answer": "답3", "frequency": "92"},
]


@pytest.fixture
def queue_paths(tmp_path, monkeypatch):
    topics_path = tmp_path / "notion-topics.json"
    state_path = tmp_path / "publish-state.json"
    topics_path.write_text(json.dumps(TOPICS, ensure_ascii=False), encoding="utf-8")

    monkeypatch.setattr(tq, "TOPICS_PATH", topics_path)
    monkeypatch.setattr(tq, "STATE_PATH", state_path)
    return topics_path, state_path


def test_next_returns_first_topic_when_state_missing(queue_paths, capsys):
    args = type("Args", (), {})()
    tq.cmd_next(args)
    out = json.loads(capsys.readouterr().out)
    assert out["id"] == "aaa111"


def test_next_skips_already_published(queue_paths):
    _, state_path = queue_paths
    state_path.write_text(
        json.dumps({"published": {"aaa111": {"date": "2026-07-01", "topic_dir": "output/질문1"}}}),
        encoding="utf-8",
    )

    args = type("Args", (), {})()
    import io
    import contextlib

    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        tq.cmd_next(args)

    out = json.loads(buf.getvalue())
    assert out["id"] == "bbb222"


def test_next_exits_nonzero_when_all_published(queue_paths):
    _, state_path = queue_paths
    state_path.write_text(
        json.dumps(
            {
                "published": {
                    "aaa111": {"date": "2026-07-01", "topic_dir": "x"},
                    "bbb222": {"date": "2026-07-02", "topic_dir": "y"},
                    "ccc333": {"date": "2026-07-03", "topic_dir": "z"},
                }
            }
        ),
        encoding="utf-8",
    )

    args = type("Args", (), {})()
    with pytest.raises(SystemExit) as exc_info:
        tq.cmd_next(args)
    assert exc_info.value.code == 1


def test_mark_done_writes_state_and_is_idempotent(queue_paths):
    _, state_path = queue_paths
    args = type("Args", (), {"id": "aaa111", "date": "2026-07-09", "topic_dir": "output/질문1"})()
    tq.cmd_mark_done(args)

    state = json.loads(state_path.read_text(encoding="utf-8"))
    assert state["published"]["aaa111"]["date"] == "2026-07-09"
    assert state["published"]["aaa111"]["topic_dir"] == "output/질문1"

    # 두 번째 topic까지 mark-done 해도 첫 번째 기록이 사라지지 않아야 한다.
    args2 = type("Args", (), {"id": "bbb222", "date": "2026-07-10", "topic_dir": "output/질문2"})()
    tq.cmd_mark_done(args2)
    state = json.loads(state_path.read_text(encoding="utf-8"))
    assert set(state["published"].keys()) == {"aaa111", "bbb222"}


def test_mark_done_defaults_date_to_today_when_omitted(queue_paths):
    _, state_path = queue_paths
    args = type("Args", (), {"id": "aaa111", "date": None, "topic_dir": "output/질문1"})()
    tq.cmd_mark_done(args)

    state = json.loads(state_path.read_text(encoding="utf-8"))
    assert state["published"]["aaa111"]["date"]  # 오늘 날짜가 채워져 있어야 함


def test_next_missing_topics_file_exits_nonzero(tmp_path, monkeypatch):
    monkeypatch.setattr(tq, "TOPICS_PATH", tmp_path / "does-not-exist.json")
    monkeypatch.setattr(tq, "STATE_PATH", tmp_path / "publish-state.json")

    args = type("Args", (), {})()
    with pytest.raises(SystemExit) as exc_info:
        tq.cmd_next(args)
    assert exc_info.value.code == 1
