"""消息处理的纯逻辑层。

这里**不放任何 NoneBot 事件响应器**，只放「可以做单元测试」的函数：

* 从消息里提取提问内容；
* 处理超长输入 / 超长回复；
* 生成帮助文本；
* 记录请求日志。

真正的响应器在 ``src/ai_chat.py``。这样分层的好处是：
测试不需要真的连 QQ，也能验证核心逻辑。
"""

from __future__ import annotations

from typing import Any, Final

from loguru import logger

# ---------------------------------------------------------------------------
# 常量与文案
# ---------------------------------------------------------------------------

#: 单条群消息允许的最大字符数（超过直接忽略，避免异常输入打爆上下文）
MAX_RAW_MESSAGE_LENGTH: Final[int] = 4000

#: 冷却提示里最多显示秒数
HELP_TEXT: Final[str] = """🤖 AI 助手使用说明

1️⃣ @我提问
    例：@AI助手 什么是快速排序？

2️⃣ /ai 问题
    例：/ai 帮我写一段 Python 读取 Excel 的代码

3️⃣ /帮助
    显示这份说明

4️⃣ /清空
    清除「你在这个群」的对话记忆（其他群、其他人的记忆不受影响）

ℹ️ 说明
• 我只会记住最近几轮对话，用来理解上下文
• 每个群、每个人的记忆互相隔离
• 连续提问有冷却时间，请耐心等待上一条回复"""


def build_help_text(bot_name: str, cooldown_seconds: float, max_turns: int) -> str:
    """生成帮助文本（把实际配置写进去，方便排查）。"""
    return (
        f"{HELP_TEXT}\n\n"
        f"⚙️ 当前设置：机器人名「{bot_name}」｜记忆 {max_turns} 轮｜冷却 {cooldown_seconds:g} 秒"
    )


# ---------------------------------------------------------------------------
# 输入处理
# ---------------------------------------------------------------------------


def extract_mention_question(raw_text: str, bot_self_id: str = "") -> str:
    """从「@机器人 你好」这类文本里取出真正的问题。

    会去掉：

    * CQ 码形式的 @（``[CQ:at,qq=123]``）；
    * 纯文本形式的 @（``@昵称``）；
    * 机器人自己的 QQ 号；
    * 首尾空白。

    :param raw_text: 消息的原始文本（含 CQ 码）
    :param bot_self_id: 机器人自己的 QQ 号
    """
    if not raw_text:
        return ""

    text = raw_text

    # 去掉 CQ:at 码
    while "[CQ:at," in text:
        start = text.find("[CQ:at,")
        end = text.find("]", start)
        if end == -1:
            text = text[:start]
            break
        text = text[:start] + " " + text[end + 1 :]

    # 去掉机器人自己的 QQ 号（CQ 码被删掉后可能残留纯数字）
    if bot_self_id:
        text = text.replace(str(bot_self_id), " ")

    # 去掉纯文本 @昵称
    parts = []
    for token in text.split():
        if token.startswith("@"):
            continue
        parts.append(token)
    text = " ".join(parts)

    return text.strip()


def normalize_question(text: str, max_length: int) -> str:
    """清洗并限制问题长度。

    * 去除首尾空白、把连续空白压成一个空格；
    * 超过 ``max_length`` 时截断（AI 侧还有 token 上限，这里只是第一道闸）。
    """
    cleaned = " ".join((text or "").split())
    if max_length > 0 and len(cleaned) > max_length:
        cleaned = cleaned[:max_length]
    return cleaned


def is_too_long(text: str, limit: int = MAX_RAW_MESSAGE_LENGTH) -> bool:
    """判断原始消息是否长到应该直接忽略。"""
    return len(text or "") > limit


def truncate_reply(text: str, max_length: int) -> str:
    """限制 AI 回复长度，超长则在末尾加省略提示。"""
    text = (text or "").strip()
    if max_length <= 0 or len(text) <= max_length:
        return text
    suffix = "…（内容过长已截断）"
    keep = max(1, max_length - len(suffix))
    return text[:keep].rstrip() + suffix


# ---------------------------------------------------------------------------
# 会话 key
# ---------------------------------------------------------------------------


def session_key(group_id: Any, user_id: Any) -> tuple[str, str]:
    """生成「群 + 用户」的隔离键。

    私聊时 ``group_id`` 传 ``"private"``，这样同一个人私聊与群聊的记忆也是分开的。
    """
    group = str(group_id) if group_id not in (None, "") else "private"
    return (group, str(user_id))


def describe_session(group_id: Any, user_id: Any) -> str:
    """生成用于日志的会话标识（QQ 号在日志里部分打码）。"""
    group, user = session_key(group_id, user_id)
    return f"group={_mask_id(group)} user={_mask_id(user)}"


def _mask_id(value: str) -> str:
    """把 QQ 号中间几位打码，兼顾排查问题与隐私。"""
    if value in {"private", ""}:
        return value or "?"
    if len(value) <= 4:
        return value
    return f"{value[:2]}***{value[-2:]}"


# ---------------------------------------------------------------------------
# 请求日志
# ---------------------------------------------------------------------------


def log_request(
    group_id: Any,
    user_id: Any,
    *,
    source: str,
    question: str,
    ok: bool | None = None,
    error_kind: str | None = None,
    elapsed: float | None = None,
) -> None:
    """统一格式地记录一次请求。

    **不会记录完整问题内容**，只记录长度——避免把群友聊天内容大量落到日志文件里。
    """
    session = describe_session(group_id, user_id)
    if ok is None:
        logger.info("[{}] 收到请求 {} 问题长度={}", source, session, len(question or ""))
        return
    if ok:
        logger.info("[{}] 回复成功 {} 耗时={:.2f}s", source, session, elapsed or 0.0)
    else:
        logger.warning("[{}] 回复失败 {} 原因={}", source, session, error_kind or "unknown")


__all__ = [
    "HELP_TEXT",
    "MAX_RAW_MESSAGE_LENGTH",
    "build_help_text",
    "describe_session",
    "extract_mention_question",
    "is_too_long",
    "log_request",
    "normalize_question",
    "session_key",
    "truncate_reply",
]
