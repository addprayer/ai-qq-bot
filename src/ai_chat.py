"""AI 群聊插件（NoneBot2 + OneBot V11）。

对外提供的功能：

=============  ====================================================
触发方式        行为
=============  ====================================================
@机器人 问题     调用 DeepSeek 回答（带上下文）
/ai 问题        同上
/帮助           显示指令说明
/清空           清除「本人在本群」的对话记忆
=============  ====================================================

设计要点：

* 只响应**明确触发**的消息，不会对群里每条消息都调用 AI（省钱、不打扰）。
* 每个「群 + 用户」的上下文互相隔离。
* 有冷却时间，避免短时间重复调用。
* 所有异常都在这里兜住，保证一次 API 失败不会让机器人崩溃。
"""

from __future__ import annotations

import asyncio
import time

from loguru import logger
from nonebot import on_command, on_message
from nonebot.adapters.onebot.v11 import Bot, Event, GroupMessageEvent, Message, MessageSegment
from nonebot.matcher import Matcher
from nonebot.rule import to_me

from config import get_settings
from src.ai_client import AIClient
from src.image_input import prepare_images
from src.web_fetch import FetchResult, build_context, fetch, find_urls
from src.history import CooldownTracker, HistoryStore, build_history_store
from src.message_handler import (
    build_help_text,
    extract_mention_question,
    is_too_long,
    log_request,
    normalize_question,
    truncate_reply,
)

# ---------------------------------------------------------------------------
# 全局对象（插件加载时创建一次）
# ---------------------------------------------------------------------------

_settings = get_settings()
_ai_client: AIClient = AIClient.from_settings(_settings)
_history: HistoryStore = build_history_store(_settings)
_cooldown = CooldownTracker(_settings.cooldown_seconds)


def reload_plugin_state() -> None:
    """按当前配置重建内部对象（改完 .env 想立即生效、或测试需要重置时用）。"""
    global _settings, _ai_client, _history, _cooldown
    _settings = get_settings(reload=True)
    _ai_client = AIClient.from_settings(_settings)
    _history = build_history_store(_settings)
    _cooldown = CooldownTracker(_settings.cooldown_seconds)


# ---------------------------------------------------------------------------
# 规则与响应器
# ---------------------------------------------------------------------------

#: 支持的指令前缀
_COMMAND_PREFIXES = ("/", "／", "!", "！", ".")

#: /ai 指令的写法
_AI_COMMAND_NAMES = ("ai", "AI", "Ai")


def _plain_text(event: Event) -> str:
    """取消息的纯文本部分（去掉 CQ 码），失败时返回空串。"""
    try:
        return event.get_message().extract_plain_text()
    except Exception:  # pragma: no cover - 防御性写法
        return ""


def split_ai_command(text: str) -> str | None:
    """如果文本是 ``/ai 问题`` 或 ``/ai问题``，返回其中的问题部分。

    不是 /ai 指令时返回 ``None``（注意：问题部分可能为空字符串）。
    """
    stripped = (text or "").strip()
    if not stripped.startswith(_COMMAND_PREFIXES):
        return None
    body = stripped[1:].lstrip()
    for name in _AI_COMMAND_NAMES:
        if body.startswith(name):
            return body[len(name) :].strip()
    return None


def ai_command_rule(event: Event) -> bool:
    """``/ai ...`` 形式（允许命令名与问题之间没有空格）。"""
    return split_ai_command(_plain_text(event)) is not None


#: /帮助
matcher_help = on_command("帮助", aliases={"help", "菜单"}, priority=5, block=True)

#: /清空
matcher_clear = on_command("清空", aliases={"重置", "clear", "reset"}, priority=5, block=True)

#: /ai 问题（priority 数字小的先执行；block=True 表示执行后阻止后续响应器）
matcher_ai = on_command("ai", aliases={"AI"}, priority=5, block=True)

#: /ai问题（命令名和问题之间没有空格）
matcher_ai_loose = on_message(rule=ai_command_rule, priority=6, block=True)

#: 被 @ 时兜底响应
matcher_mention = on_message(rule=to_me(), priority=10, block=True)


# ---------------------------------------------------------------------------
# 公共流程
# ---------------------------------------------------------------------------


def _session_ids(event: Event) -> tuple[str, str]:
    """取出用于隔离的 (群号, 用户号)。私聊的群号固定为 ``private``。"""
    user_id = str(getattr(event, "user_id", "unknown"))
    if isinstance(event, GroupMessageEvent):
        return (str(event.group_id), user_id)
    return ("private", user_id)


def _at(user_id: str) -> Message:
    return Message(MessageSegment.at(user_id))


def _image_urls(event: Event) -> list[str]:
    """取出消息里所有图片/表情包的链接。

    QQ 的图片段形如 ``{"type": "image", "data": {"url": "http://..."}}``。
    纯表情包消息的纯文本是空的，只靠文字会把它当成「什么都没发」。
    """
    try:
        message = event.get_message()
    except Exception:  # pragma: no cover - 防御性写法
        return []
    urls: list[str] = []
    for seg in message:
        if getattr(seg, "type", "") != "image":
            continue
        url = getattr(seg, "data", None) or {}
        link = str(url.get("url", "") or "").strip()
        if link:
            urls.append(link)
    return urls


async def _handle_question(
    event: Event,
    matcher: Matcher,
    question: str,
    *,
    source: str,
    check_cooldown: bool = True,
    image_urls: list[str] | None = None,
) -> bool:
    """统一的「提问 -> 调 AI -> 回复」流程。

    :param check_cooldown: 是否检查冷却时间。
        被 @ 触发的兜底响应器传 ``False``——它是在
        :func:`_handle_mention` 里已经确认过冷却之后才调用的。
    :param image_urls: 本条消息里的图片链接（QQ 给的 http 链接）。
        会本地下载后以 base64 内联给模型，最多 3 张。

    :return: 是否已经回复（``True`` 表示已经调用过 ``finish()``）
    """
    group_id, user_id = _session_ids(event)
    image_urls = image_urls or []

    # --- 冷却检查 ---
    # 注意：这里不能用独立的「冷却响应器」，因为 block=True 的响应器
    # 即使只是 return 不回复，NoneBot 也会停止后续事件传播，
    # 会把正常的 @提问 一起挡掉。
    if check_cooldown:
        remaining = _cooldown.check(group_id, user_id)
        if remaining > 0:
            await matcher.finish(_at(user_id) + MessageSegment.text(f" 慢一点～请等 {remaining:.1f} 秒后再问我。"))
            return True

    # 先判断「原始问题」是否过长：如果先做 normalize 截断，
    # 超长问题就会被悄悄截短后发给 AI，既不礼貌也浪费钱。
    if is_too_long(question) or len(question) > _settings.max_question_length:
        await matcher.finish(
            _at(user_id)
            + MessageSegment.text(
                f" 你的问题太长了（超过 {_settings.max_question_length} 字），请精简一下再问我～"
            )
        )
        return True

    question = normalize_question(question, _settings.max_question_length)

    # 既没文字也没图片：不甩「AI 助手使用说明」，只回一句人话
    if not question and not image_urls:
        await matcher.finish(_at(user_id) + MessageSegment.text(" ？你想说什么，我没听清。"))
        return True

    # 只有图片：给模型一句占位说明，让它知道「对方只发了图」
    if not question and image_urls:
        question = "（对方只发来了图片，没有配文字）"

    log_request(group_id, user_id, source=source, question=question or "（图片）")
    _cooldown.touch(group_id, user_id)

    # --- 图片/表情包：下载并内联，随本轮消息一起发给模型 ---
    prepared = await prepare_images(image_urls) if image_urls else []
    if image_urls and not prepared:
        logger.warning("本轮的 {} 张图片全部准备失败，改为纯文字回答", len(image_urls))

    # --- 联网：消息里带链接就抓网页正文，作为【参考网页】喂给模型 ---
    prompt = question
    urls = find_urls(question)
    if urls:
        results = await asyncio.gather(*(fetch(u) for u in urls), return_exceptions=True)
        fetched = [r for r in results if isinstance(r, FetchResult)]
        if fetched:
            context = build_context(fetched)
            prompt = f"{question}\n\n{context}"
            logger.info("已注入网页内容 链接数={} 上下文长度={}", len(fetched), len(context))

    started = time.monotonic()
    history = _history.get_messages(group_id, user_id)
    try:
        # prompt = 原问题（含链接时再追加【参考网页】），history 只存原始对话；
        # images 只在当轮发送，避免历史每轮重复计图片 token
        result = await _ai_client.chat(prompt, history, images=[p.source for p in prepared])
    except Exception as exc:  # noqa: BLE001 - 兜底，任何异常都不该让机器人挂掉
        logger.exception("AI 调用出现未预期异常：{}", type(exc).__name__)
        await matcher.finish(_at(user_id) + MessageSegment.text(" 机器人内部出错了，请稍后再试。"))
        return True

    elapsed = time.monotonic() - started

    if not result.ok:
        log_request(group_id, user_id, source=source, question=question, ok=False, error_kind=result.error_kind)
        await matcher.finish(_at(user_id) + MessageSegment.text(f" {result.text}"))
        return True

    answer = truncate_reply(result.text, _settings.max_reply_length)
    _history.append_turn(group_id, user_id, question or "（图片）", answer)
    log_request(group_id, user_id, source=source, question=question, ok=True, elapsed=elapsed)

    await matcher.finish(_at(user_id) + MessageSegment.text(f" {answer}"))
    return True


# ---------------------------------------------------------------------------
# /帮助
# ---------------------------------------------------------------------------


@matcher_help.handle()
async def _handle_help(matcher: Matcher) -> None:
    await matcher.finish(
        build_help_text(
            _settings.bot_name,
            _settings.cooldown_seconds,
            _settings.history_max_turns,
        )
    )


# ---------------------------------------------------------------------------
# /清空
# ---------------------------------------------------------------------------


@matcher_clear.handle()
async def _handle_clear(event: Event, matcher: Matcher) -> None:
    group_id, user_id = _session_ids(event)
    try:
        removed = _history.clear(group_id, user_id)
    except Exception:  # noqa: BLE001
        logger.exception("/清空 执行失败")
        await matcher.finish(_at(user_id) + MessageSegment.text(" 清理记忆时出错了，请稍后再试。"))
        return

    _cooldown.reset()
    logger.info("已清空会话记忆 group={} user={}", group_id, user_id)
    scope = "本群" if group_id != "private" else "私聊"
    if removed:
        text = f" 已清除你在{scope}的对话记忆（共 {removed} 条消息）。我们可以重新开始了～"
    else:
        text = f" 你在{scope}还没有对话记录，无需清理。"
    await matcher.finish(_at(user_id) + MessageSegment.text(text))


# ---------------------------------------------------------------------------
# /ai 问题
# ---------------------------------------------------------------------------


@matcher_ai.handle()
async def _handle_ai_command(event: Event, matcher: Matcher) -> None:
    question = split_ai_command(_plain_text(event))
    # on_command 已经确认了命令名，这里正常情况下不会是 None
    await _handle_question(event, matcher, question or "", source="指令", image_urls=_image_urls(event))


@matcher_ai_loose.handle()
async def _handle_ai_command_loose(event: Event, matcher: Matcher) -> None:
    question = split_ai_command(_plain_text(event)) or ""
    await _handle_question(event, matcher, question, source="指令", image_urls=_image_urls(event))


# ---------------------------------------------------------------------------
# 被 @ 时
# ---------------------------------------------------------------------------


@matcher_mention.handle()
async def _handle_mention(bot: Bot, event: Event, matcher: Matcher) -> None:
    """被 @ 时的兜底响应（私聊也会走到这里）。

    注意两点：

    * 指令类消息（/帮助、/清空、/ai）在更早的优先级已被 block 拦住；
    * **私聊消息的 ``to_me`` 恒为 True**，所以私聊里直接发问题就会触发，
      不需要 @（这是 OneBot V11 适配器 ``_check_at_me`` 的行为）。
    """
    group_id, user_id = _session_ids(event)

    # 冷却：直接在这里提示并结束。不能放到单独的响应器里——
    # block=True 的响应器即使只是 return 不回复，也会停止事件传播，
    # 把这条正常的 @提问 一起挡掉。
    remaining = _cooldown.check(group_id, user_id)
    if remaining > 0:
        await matcher.finish(_at(user_id) + MessageSegment.text(f" 慢一点～请等 {remaining:.1f} 秒后再问我。"))
        return

    raw = _plain_text(event)
    question = extract_mention_question(raw, bot_self_id=str(getattr(bot, "self_id", "")))
    await _handle_question(
        event,
        matcher,
        question,
        source="@提问",
        check_cooldown=False,
        image_urls=_image_urls(event),
    )


__all__ = ["reload_plugin_state", "split_ai_command"]
