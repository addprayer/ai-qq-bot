"""把 QQ 图片/表情包变成模型能吃的输入。

为什么不能直接把 QQ 给的链接丢给模型：

* QQ 图片 CDN 有防盗链、链接还会过期，模型服务端去下载经常拿不到；
* 链接可能带鉴权参数，第三方抓取会失败。

所以本地先下载，转成 ``data:image/...;base64,...`` 内联传给模型
（DeepSeek 的 Vision 接口明确支持这种格式，且不受防盗链影响）。

安全与成本约束：

* 复用 :mod:`src.web_fetch` 的 SSRF 校验（不允许内网/本机地址）；
* 单张图最大 :data:`MAX_IMAGE_BYTES`，超了就不传（避免请求体过大）；
* 只接受 JPEG / PNG / GIF / WebP（按**文件头**判断，不看扩展名）；
* 下载失败就降级为「把原链接交给模型试一次」，再失败就当作没有图片。
"""

from __future__ import annotations

import asyncio
import base64
import urllib.request
from dataclasses import dataclass

from loguru import logger

from src.web_fetch import check_url

#: 单张图片最大字节数（base64 后约 4/3，仍远小于接口 32MB 上限）
MAX_IMAGE_BYTES = 8 * 1024 * 1024
#: 下载超时（秒）
DOWNLOAD_TIMEOUT = 10.0
#: 一次最多处理几张图（再多既贵又慢）
MAX_IMAGES = 3

_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0 Safari/537.36"
)

#: 文件头 → MIME。按内容判断，避免 QQ 给的扩展名不可靠。
_MAGIC: tuple[tuple[bytes, str], ...] = (
    (b"\xff\xd8\xff", "image/jpeg"),
    (b"\x89PNG\r\n\x1a\n", "image/png"),
    (b"GIF87a", "image/gif"),
    (b"GIF89a", "image/gif"),
)


@dataclass(frozen=True)
class PreparedImage:
    """一张准备好的图片。"""

    #: 可以直接放进 ``image_url.url`` 的值（data URL 或原始 http 链接）
    source: str
    #: MIME 类型（未知时为空）
    mime: str = ""
    #: 字节数（用原始链接时未知，记 0）
    size: int = 0
    #: 是否真的内联成了 base64
    inlined: bool = False


def sniff_mime(data: bytes) -> str:
    """按文件头判断图片类型，认不出来返回空串。"""
    if not data:
        return ""
    for magic, mime in _MAGIC:
        if data.startswith(magic):
            return mime
    # WebP: RIFF....WEBP
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return ""


def to_data_url(data: bytes, mime: str) -> str:
    """把图片字节转成 data URL。"""
    encoded = base64.b64encode(data).decode("ascii")
    return f"data:{mime};base64,{encoded}"


def _download_sync(url: str) -> bytes:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": _UA,
            "Accept": "image/*,*/*;q=0.8",
        },
    )
    # 只读前 MAX_IMAGE_BYTES+1 字节，超限就能发现
    with urllib.request.urlopen(request, timeout=DOWNLOAD_TIMEOUT) as response:  # noqa: S310 - 已做 scheme/host 校验
        return response.read(MAX_IMAGE_BYTES + 1)


async def prepare_image(url: str) -> PreparedImage | None:
    """把一张图片准备成模型可用的输入。

    :return: 准备成功返回 :class:`PreparedImage`，失败返回 ``None``
    """
    url = (url or "").strip()
    if not url:
        return None

    allowed, reason = check_url(url)
    if not allowed:
        logger.warning("图片链接被拒绝：{}（{}）", reason, url[:120])
        return None

    try:
        data = await asyncio.to_thread(_download_sync, url)
    except Exception as exc:  # noqa: BLE001 - 下载失败不该影响聊天
        # 降级：也许模型服务端能拿到这个链接
        logger.warning("图片下载失败，改为直接传递链接：{}（{}）", type(exc).__name__, url[:120])
        return PreparedImage(source=url, inlined=False)

    if len(data) > MAX_IMAGE_BYTES:
        logger.warning("图片超过 {} 字节，跳过：{}", MAX_IMAGE_BYTES, url[:120])
        return None

    mime = sniff_mime(data)
    if not mime:
        logger.warning("图片格式不支持（只接受 JPEG/PNG/GIF/WebP）：{}", url[:120])
        return None

    logger.info("图片已内联 mime={} 大小={}KB", mime, len(data) // 1024)
    return PreparedImage(source=to_data_url(data, mime), mime=mime, size=len(data), inlined=True)


async def prepare_images(urls: list[str], limit: int = MAX_IMAGES) -> list[PreparedImage]:
    """批量准备图片，失败的自动跳过。"""
    targets = [u for u in urls if u][:limit]
    if not targets:
        return []
    results = await asyncio.gather(*(prepare_image(u) for u in targets))
    return [r for r in results if r is not None]


__all__ = [
    "DOWNLOAD_TIMEOUT",
    "MAX_IMAGES",
    "MAX_IMAGE_BYTES",
    "PreparedImage",
    "prepare_image",
    "prepare_images",
    "sniff_mime",
    "to_data_url",
]
