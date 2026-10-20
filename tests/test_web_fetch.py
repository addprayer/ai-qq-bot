"""网页抓取模块的测试。

重点覆盖**安全边界**（不能让群友借机器人访问内网）和纯函数的解析正确性，
真正的联网请求只做一个「失败也不该抛异常」的健壮性测试。
"""

from __future__ import annotations

import pytest

from src.web_fetch import (
    FetchResult,
    build_context,
    check_url,
    fetch_sync,
    find_urls,
    html_to_text,
)

# ---------------------------------------------------------------------------
# 链接识别
# ---------------------------------------------------------------------------


def test_find_urls_extracts_links() -> None:
    text = "帮我看下 https://example.com/a?b=1 这个页面，还有 http://foo.cn/x。"
    assert find_urls(text) == ["https://example.com/a?b=1", "http://foo.cn/x"]


def test_find_urls_strips_trailing_punctuation() -> None:
    assert find_urls("看这个 https://example.com/page。") == ["https://example.com/page"]
    assert find_urls("（https://example.com/x）") == ["https://example.com/x"]


def test_find_urls_respects_limit_and_dedup() -> None:
    text = "https://a.com/1 https://a.com/1 https://b.com/2 https://c.com/3"
    urls = find_urls(text, limit=2)
    assert len(urls) == 2
    assert urls[0] == "https://a.com/1"
    assert urls[1] == "https://b.com/2"


def test_find_urls_ignores_plain_text() -> None:
    assert find_urls("今天天气不错，没有链接") == []


# ---------------------------------------------------------------------------
# 安全：SSRF 防护
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1/admin",
        "http://localhost:8080/",
        "http://192.168.1.1/",
        "http://10.0.0.1/",
        "http://169.254.169.254/latest/meta-data/",  # 云厂商元数据地址
        "file:///C:/Windows/win.ini",
        "ftp://example.com/file",
        "javascript:alert(1)",
        "http://0.0.0.0/",
    ],
)
def test_check_url_blocks_dangerous_targets(url: str) -> None:
    """内网、本机、元数据地址、非 http 协议一律拒绝。"""
    allowed, reason = check_url(url)
    assert allowed is False, f"不该允许访问：{url}"
    assert reason


def test_fetch_sync_refuses_localhost() -> None:
    """即使直接调用抓取函数，本机地址也必须被拒，不会真的发请求。"""
    result = fetch_sync("http://127.0.0.1:8080/onebot/v11/ws", timeout=1)
    assert result.ok is False
    assert "不允许" in result.error or "格式" in result.error


# ---------------------------------------------------------------------------
# HTML → 文本
# ---------------------------------------------------------------------------


def test_html_to_text_extracts_title_and_body() -> None:
    raw = """
    <html><head><title>  我的标题  </title>
    <style>body{color:red}</style></head>
    <body><script>alert(1)</script>
    <p>第一段&amp;内容</p><p>第二段</p>
    </body></html>
    """
    title, body = html_to_text(raw)
    assert title == "我的标题"
    assert "第一段&内容" in body
    assert "第二段" in body
    # 脚本和样式不能被当成正文
    assert "alert" not in body
    assert "color:red" not in body
    # 标签要被清掉
    assert "<p>" not in body


def test_html_to_text_limits_length() -> None:
    title, body = html_to_text("<p>" + "啊" * 10000 + "</p>")
    assert len(body) <= 4000


def test_html_to_text_handles_empty() -> None:
    assert html_to_text("") == ("", "")


# ---------------------------------------------------------------------------
# 上下文拼装
# ---------------------------------------------------------------------------


def test_build_context_success_and_failure() -> None:
    ok = FetchResult(ok=True, url="https://x.com/1", title="标题", text="正文内容")
    bad = FetchResult(ok=False, url="https://x.com/2", error="HTTP 404")
    context = build_context([ok, bad])

    assert "【参考网页】" in context
    assert "标题" in context
    assert "正文内容" in context
    assert "抓取失败" in context
    assert "HTTP 404" in context


def test_build_context_empty() -> None:
    assert build_context([]) == ""


# ---------------------------------------------------------------------------
# 健壮性：联网失败不能抛异常
# ---------------------------------------------------------------------------


def test_fetch_sync_does_not_raise_on_bad_domain() -> None:
    """域名不存在时应该返回失败结果，而不是抛异常把聊天打断。"""
    result = fetch_sync("https://this-domain-should-not-exist-12345.invalid/", timeout=3)
    assert isinstance(result, FetchResult)
    assert result.ok is False
    assert result.error
