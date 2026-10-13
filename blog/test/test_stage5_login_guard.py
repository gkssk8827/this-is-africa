"""
5단계(발행) 파이프라인이 "로그인 안 된 상태로 조용히 진행하다가 나중에 막히는" 대신
초반에 확실히 멈추는지를 검증한다. CLAUDE.md의 "사전 점검(로그인)" 요구사항의 코드적
뒷받침 — publish_post()가 실제로 로그인 확인 없이는 절대 진행하지 않는지 확인한다.
"""

import json

import pytest
from playwright.sync_api import sync_playwright

import publish as pub


def test_raise_if_login_redirect_raises_on_nid_naver_com():
    with pytest.raises(RuntimeError, match="로그인 페이지로 리다이렉트"):
        pub._raise_if_login_redirect("https://nid.naver.com/nidlogin.login?returl=...")


def test_raise_if_login_redirect_ok_on_blog_domain():
    # 예외가 발생하지 않아야 한다.
    pub._raise_if_login_redirect("https://blog.naver.com/this_africa?Redirect=Write&")


def test_publish_post_exits_without_navigating_when_not_logged_in(tmp_path, monkeypatch):
    """
    로그인 안 된(빈) 프로필로 publish_post를 호출하면, 실제 네이버 글쓰기 페이지로
    이동을 시도하기도 전에 SystemExit(1)로 멈춰야 한다. open_write_page가 호출되면
    실제 네트워크 요청이 나가므로, 그 전에 막혔는지가 핵심이다.
    """
    empty_profile = tmp_path / "empty_profile"
    empty_profile.mkdir()
    monkeypatch.setattr(pub, "PROFILE_DIR", empty_profile)

    called = {"open_write_page": False}

    def fail_if_called(*args, **kwargs):
        called["open_write_page"] = True
        raise AssertionError("로그인 확인도 안 됐는데 open_write_page가 호출됐다")

    monkeypatch.setattr(pub, "open_write_page", fail_if_called)

    post_json = tmp_path / "post.json"
    post_json.write_text(
        json.dumps({
            "title": "제목",
            "body_blocks": [],
            "category": "아프리카 여행 정보",
            "tags": [],
            "drive_image_urls": [],
        }),
        encoding="utf-8",
    )

    with pytest.raises(SystemExit) as exc_info:
        pub.publish_post(
            post_json_path=str(post_json),
            blog_id="dummy-blog-id",
            visibility="private",
            headed=False,
            save_as_draft=True,
        )

    assert exc_info.value.code == 1
    assert called["open_write_page"] is False


def test_check_login_returns_false_for_empty_profile(tmp_path, monkeypatch):
    empty_profile = tmp_path / "empty_profile"
    empty_profile.mkdir()
    monkeypatch.setattr(pub, "PROFILE_DIR", empty_profile)

    assert pub.check_login(headed=False) is False


def test_check_login_returns_false_when_profile_dir_missing(tmp_path, monkeypatch):
    missing_profile = tmp_path / "does_not_exist"
    monkeypatch.setattr(pub, "PROFILE_DIR", missing_profile)

    assert pub.check_login(headed=False) is False
