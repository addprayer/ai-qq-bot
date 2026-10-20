"""安全的网页抓取：只取正文文本，给模型当参考资料。

设计上刻意保守：

* 只允许 ``http`` / ``https``；
* 拒绝本机、内网、链路本地等地址（防 SSRF —— 不能让群友借机器人访问内网服务）；
* 限制超时、最大字节数、最多重定向次数；
* 只取正文纯文本（去掉 script/style/标签），并截断到可接受长度；
* 抓回来的内容一律当**数据**用，提示词里已明确要求模型不执行页面里的指令。
"""

from __future__ import annotations

import asyncio
import html
import ipaddress
import re
import socket
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass

from loguru import logger

#: 抓取超时（秒）
DEFAULT_TIMEOUT = 8.0
#: 最多下载多少字节（正文通常远小于此）
MAX_BYTES = 512 * 1024
#: 提取出的正文字符上限（喂给模型的部分）
MAX_TEXT_CHARS = 4000
#: 一次请求最多处理几个链接
MAX_URLS = 2

_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0 Safari/537.36"

_URL_RE = re.compile(
    # 注意：URL 内部允许出现 ? 和 !（查询串/锚点要用），
    # 只把明显不属于链接的字符排除；结尾的标点由 rstrip 去掉。
    r"https?://[^\s<>\"'）)】\]，,。；;！？]+",
    re.IGNORECASE,
)
_TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)
_DROP_BLOCKS = re.compile(
    r"<(script|style|noscript|svg|iframe|head)\b[^>]*>.*?</\1>",
    re.IGNORECASE | re.DOTALL,
)
_BREAK_TAGS = re.compile(r"</?(p|div|br|li|tr|h[1-6]|section|article)\b[^>]*>", re.IGNORECASE)
_ANY_TAG = re.compile(r"<[^>]+>")
_SPACES = re.compile(r"[ \t\u00a0]+")
_BLANK_LINES = re.compile(r"\n{3,}")


@dataclass(frozen=True)
class FetchResult:
    """一次抓取的结果。"""

    ok: bool
    url: str
    title: str = ""
    text: str = ""
    error: str = ""


# ---------------------------------------------------------------------------
# URL 处理
# ---------------------------------------------------------------------------


def find_urls(text: str, limit: int = MAX_URLS) -> list[str]:
    """从一段文字里找出 http(s) 链接（去掉尾部标点）。"""
    seen: list[str] = []
    for match in _URL_RE.finditer(text or ""):
        url = match.group(0).rstrip(".,;:!?)]}》」'\"")
        if url and url not in seen:
            seen.append(url)
        if len(seen) >= limit:
            break
    return seen


def _is_safe_host(host: str) -> bool:
    """主机名解析后不能落在内网/本机/保留地址上。"""
    if not host:
        return False
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror:
        return False

    for info in infos:
        raw = info[4][0]
        try:
            ip = ipaddress.ip_address(raw.split("%")[0])
        except ValueError:
            return False
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_reserved
            or ip.is_multicast
            or ip.is_unspecified
        ):
            return False
    return True


def check_url(url: str) -> tuple[bool, str]:
    """检查链接是否允许抓取，返回 ``(是否允许, 原因)``。"""
    try:
        parsed = urllib.parse.urlparse(url)
    except ValueError:
        return False, "链接格式不对"
    if parsed.scheme not in {"http", "https"}:
        return False, "只支持 http/https 链接"
    if not parsed.hostname:
        return False, "链接缺少域名"
    if not _is_safe_host(parsed.hostname):
        # 不区分「解析失败」和「内网地址」，避免给人探测内网的口径
        return False, "这个地址不允许访问"
    return True, ""


# ---------------------------------------------------------------------------
# HTML → 纯文本
# ---------------------------------------------------------------------------


def html_to_text(raw: str) -> tuple[str, str]:
    """把 HTML 转成 ``(标题, 正文)``。纯函数，方便单测。"""
    if not raw:
        return "", ""

    title_match = _TITLE_RE.search(raw)
    title = html.unescape(_ANY_TAG.sub("", title_match.group(1))).strip() if title_match else ""
    title = _SPACES.sub(" ", title)[:200]

    body = _DROP_BLOCKS.sub(" ", raw)
    body = _BREAK_TAGS.sub("\n", body)
    body = _ANY_TAG.sub(" ", body)
    body = html.unescape(body)
    body = body.replace("\r\n", "\n").replace("\r", "\n")
    body = _SPACES.sub(" ", body)
    body = "\n".join(line.strip() for line in body.split("\n"))
    body = _BLANK_LINES.sub("\n\n", body).strip()
    return title, body[:MAX_TEXT_CHARS]


# ---------------------------------------------------------------------------
# 抓取
# ---------------------------------------------------------------------------


def fetch_sync(url: str, *, timeout: float = DEFAULT_TIMEOUT) -> FetchResult:
    """同步抓取一个页面（内部用，勿在事件循环里直接调用）。"""
    allowed, reason = check_url(url)
    if not allowed:
        return FetchResult(ok=False, url=url, error=reason)

    request = urllib.request.Request(url, headers={"User-Agent": _UA, "Accept-Language": "zh-CN,zh;q=0.9"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310 - 已做 scheme/host 校验
            # 重定向后可能跑到别的主机，再校验一次
            final_url = response.geturl()
            if final_url != url:
                ok, why = check_url(final_url)
                if not ok:
                    return FetchResult(ok=False, url=url, error=f"跳转后的地址被拒绝（{why}）")

            content_type = (response.headers.get("Content-Type") or "").lower()
            raw_bytes = response.read(MAX_BYTES)
    except urllib.error.HTTPError as exc:
        return FetchResult(ok=False, url=url, error=f"HTTP {exc.code}")
    except (urllib.error.URLError, TimeoutError, socket.timeout) as exc:
        return FetchResult(ok=False, url=url, error=f"连接失败：{type(exc).__name__}")
    except Exception as exc:  # noqa: BLE001 - 抓取失败不该影响聊天
        return FetchResult(ok=False, url=url, error=f"抓取异常：{type(exc).__name__}")

    if not any(t in content_type for t in ("text", "html", "xml", "json")):
        return FetchResult(ok=False, url=url, error="这个链接不是网页（可能是图片或文件）")

    charset = "utf-8"
    match = re.search(r"charset=([\w-]+)", content_type)
    if match:
        charset = match.group(1)
    # 国内站点大量使用 gb18030
    if not match:
        head = raw_bytes[:2048].decode("ascii", errors="ignore").lower()
        if "gb2312" in head or "gbk" in head:
            charset = "gb18030"

    try:
        decoded = raw_bytes.decode(charset, errors="replace")
    except LookupError:
        decoded = raw_bytes.decode("utf-8", errors="replace")

    title, body = html_to_text(decoded)
    if not body:
        return FetchResult(ok=False, url=url, title=title, error="页面没有可读的正文")

    return FetchResult(ok=True, url=url, title=title, text=body)


async def fetch(url: str, *, timeout: float = DEFAULT_TIMEOUT) -> FetchResult:
    """异步抓取（放到线程里跑，避免阻塞事件循环）。"""
    result = await asyncio.to_thread(fetch_sync, url, timeout=timeout)
    if result.ok:
        logger.info("网页抓取成功 url={} 标题={} 正文={}字", url, result.title or "(无)", len(result.text))
    else:
        logger.warning("网页抓取失败 url={} 原因={}", url, result.error)
    return result


def build_context(results: list[FetchResult]) -> str:
    """把抓取结果拼成喂给模型的【参考网页】块。"""
    blocks: list[str] = []
    for item in results:
        if item.ok:
            blocks.append(
                f"【参考网页】\nURL: {item.url}\n标题: {item.title or '(无标题)'}\n正文:\n{item.text}"
            )
        else:
            blocks.append(f"【参考网页抓取失败】\nURL: {item.url}\n原因: {item.error}")
    return "\n\n".join(blocks)


__all__ = [
    "DEFAULT_TIMEOUT",
    "FetchResult",
    "MAX_URLS",
    "build_context",
    "check_url",
    "fetch",
    "fetch_sync",
    "find_urls",
    "html_to_text",
]
