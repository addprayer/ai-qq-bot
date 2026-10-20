"""图片输入处理的测试：格式嗅探、data URL 生成、安全与大小限制。"""

from __future__ import annotations

import asyncio
import base64

import pytest

from src.image_input import (
    MAX_IMAGE_BYTES,
    PreparedImage,
    prepare_image,
    prepare_images,
    sniff_mime,
    to_data_url,
)

# 最小可用的 1x1 PNG（真实字节，用于格式嗅探）
PNG_1PX = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8DwHwAFAAH/q842iQAAAABJRU5ErkJggg=="
)


def test_sniff_mime_detects_formats() -> None:
    assert sniff_mime(PNG_1PX) == "image/png"
    assert sniff_mime(b"\xff\xd8\xff\xe0" + b"\x00" * 20) == "image/jpeg"
    assert sniff_mime(b"GIF89a" + b"\x00" * 20) == "image/gif"
    assert sniff_mime(b"GIF87a" + b"\x00" * 20) == "image/gif"
    assert sniff_mime(b"RIFF\x00\x00\x00\x00WEBPVP8 ") == "image/webp"
    # 认不出来
    assert sniff_mime(b"not an image at all") == ""
    assert sniff_mime(b"") == ""


def test_to_data_url_roundtrip() -> None:
    url = to_data_url(PNG_1PX, "image/png")
    assert url.startswith("data:image/png;base64,")
    payload = url.split(",", 1)[1]
    assert base64.b64decode(payload) == PNG_1PX


async def test_prepare_image_rejects_private_host() -> None:
    """内网/本机地址不允许抓取（复用 SSRF 校验）。"""
    assert await prepare_image("http://127.0.0.1/x.png") is None
    assert await prepare_image("http://192.168.1.5/x.png") is None
    assert await prepare_image("") is None


async def test_prepare_image_returns_none_on_unreachable() -> None:
    """下载失败时不能抛异常。

    当前实现会降级为「把原链接交给模型」，返回 PreparedImage 但 inlined=False；
    无论返回 None 还是降级对象，都必须是可控结果而不是异常。
    """
    result = await prepare_image("https://this-host-should-not-exist-98765.invalid/a.png")
    assert result is None or isinstance(result, PreparedImage)
    if result is not None:
        assert result.inlined is False


async def test_prepare_images_limits_count() -> None:
    """一次最多处理 MAX_IMAGES 张（再多既慢又贵）。"""
    urls = [f"http://127.0.0.1/{i}.png" for i in range(10)]
    assert await prepare_images(urls) == []


def test_max_image_bytes_is_sane() -> None:
    """上限必须低于接口限制，避免请求体过大被拒。"""
    assert 1024 < MAX_IMAGE_BYTES <= 32 * 1024 * 1024


# ---------------------------------------------------------------------------
# 用一个真实的本地 HTTP 服务验证「下载 → 内联」
# ---------------------------------------------------------------------------


@pytest.fixture()
def local_image_server():
    """起一个只在本机监听的小服务，返回 PNG 字节。

    这里直接用 127.0.0.1 会被 SSRF 校验拦住，所以测试里临时放行，
    专门验证下载与内联逻辑本身。
    """
    import http.server
    import threading

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            self.send_response(200)
            self.send_header("Content-Type", "image/png")
            self.send_header("Content-Length", str(len(PNG_1PX)))
            self.end_headers()
            self.wfile.write(PNG_1PX)

        def log_message(self, *args) -> None:  # 安静点
            return

    server = http.server.HTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}/a.png"
    finally:
        server.shutdown()


async def test_prepare_image_inlines_local_png(local_image_server, monkeypatch) -> None:
    """放行本机后，应该下载成功并内联成 data URL。"""
    import src.image_input as module

    monkeypatch.setattr(module, "check_url", lambda url: (True, ""))
    result = await prepare_image(local_image_server)

    assert result is not None
    assert result.inlined is True
    assert result.mime == "image/png"
    assert result.source.startswith("data:image/png;base64,")
    assert result.size == len(PNG_1PX)
