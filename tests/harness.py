"""测试抓手：不需要 QQ、不需要 NapCat，直接驱动真实的 NoneBot 响应器。

原理：
1. 造一个真的 ``Bot``（OneBot V11 适配器）和真的 ``GroupMessageEvent``；
2. 把 ``bot.call_api`` 替换成「只记录、不发送」的假实现；
3. 用 ``nonebot.message.handle_event`` 把事件交给真实的事件分发流程。

这样测出来的行为与真实运行一致（包括命令解析、@ 检测、block 逻辑），
但完全不依赖网络。
"""

from __future__ import annotations

import time
from typing import Any

from nonebot.adapters.onebot.v11 import (
    Adapter,
    Bot,
    GroupMessageEvent,
    Message,
    MessageSegment,
    PrivateMessageEvent,
)
from nonebot.exception import FinishedException

SELF_ID = "10000"


class BotHarness:
    """驱动机器人的测试抓手。"""

    def __init__(self, *, ai_client: Any | None = None, cooldown_seconds: float = 0.0) -> None:
        # 用真实的 NoneBot driver 构造适配器与 Bot：
        # 这样 bot.config（昵称等）与真实运行完全一致，
        # 事件预处理逻辑（去 @、判断 to_me）也是真的。
        from nonebot import get_driver

        self.adapter: Adapter = Adapter(get_driver())
        self.bot: Bot = Bot(self.adapter, self_id=SELF_ID)

        # 记录机器人发出的所有 API 调用
        self.api_calls: list[dict[str, Any]] = []

        async def fake_call_api(api: str, **params: Any) -> Any:
            self.api_calls.append({"action": api, "params": params})
            return {"message_id": 12345}

        self.bot.call_api = fake_call_api  # type: ignore[method-assign]

        self.ai = ai_client
        self.cooldown_seconds = cooldown_seconds
        self._patchers: list[Any] = []

    # -- 生命周期 --------------------------------------------------------

    def __enter__(self) -> "BotHarness":
        import src.ai_chat as plugin

        self.plugin = plugin

        # 每次测试都用干净的历史与冷却状态
        from src.history import CooldownTracker, InMemoryHistoryStore

        self._patchers.append(("history", plugin._history))
        self._patchers.append(("cooldown", plugin._cooldown))
        plugin._history = InMemoryHistoryStore(max_turns=plugin._settings.history_max_turns)
        plugin._cooldown = CooldownTracker(self.cooldown_seconds)

        if self.ai is not None:
            self._patchers.append(("ai", plugin._ai_client))
            plugin._ai_client = self.ai
        else:
            self.ai = plugin._ai_client

        return self

    def __exit__(self, *exc_info: object) -> None:
        for name, old in self._patchers:
            if name == "ai":
                self.plugin._ai_client = old
            elif name == "history":
                self.plugin._history = old
            elif name == "cooldown":
                self.plugin._cooldown = old
        self._patchers.clear()

    # -- 构造与投递事件 --------------------------------------------------

    def make_group_event(
        self,
        text: str,
        *,
        user_id: int,
        group_id: int,
        at_me: bool = False,
        nickname: str = "测试群友",
        message_id: int = 1001,
    ) -> dict[str, Any]:
        """构造一条群消息事件（还没有经过适配器解析）。"""
        segments: list[dict[str, Any]] = []
        if at_me:
            segments.append({"type": "at", "data": {"qq": SELF_ID}})
        segments.append({"type": "text", "data": {"text": text}})

        raw = "".join(
            f"[CQ:at,qq={seg['data']['qq']}]" if seg["type"] == "at" else seg["data"]["text"]
            for seg in segments
        )

        return {
            "post_type": "message",
            "message_type": "group",
            "sub_type": "normal",
            "message_id": message_id,
            "group_id": group_id,
            "user_id": user_id,
            "time": int(time.time()),
            "self_id": int(SELF_ID),
            "raw_message": raw,
            "font": 0,
            "sender": {"user_id": user_id, "nickname": nickname, "role": "member"},
            "message": segments,
        }

    async def send_group_message(
        self,
        text: str,
        *,
        user_id: int,
        group_id: int,
        at_me: bool = False,
    ) -> dict[str, Any]:
        """投递一条群消息，返回处理结果（发出的消息、是否被处理等）。"""
        before = len(self.api_calls)
        event_dict = self.make_group_event(text, user_id=user_id, group_id=group_id, at_me=at_me)
        # 直接用适配器的事件模型构造，再由 Bot.handle_event 走真实的
        # 「去 @、判断 to_me、分发响应器」流程。
        event = GroupMessageEvent.model_validate(event_dict)

        finished = False
        try:
            await self.bot.handle_event(event)
        except FinishedException:
            # Matcher.finish() 的正常结束方式（NoneBot 内部就是靠这个异常中断）
            finished = True
        except Exception as exc:  # noqa: BLE001 - 其他异常要暴露出来，方便定位
            raise AssertionError(f"处理消息时出现未预期异常：{type(exc).__name__}: {exc}") from exc

        new_calls = self.api_calls[before:]
        return {
            # finished 只代表 FinishedException 是否传播到了我们这一层；
            # NoneBot 内部会自行捕获它，所以通常都是 False。
            "finished": finished,
            # 更可靠的判断：机器人这次是否真的发了消息
            "responded": bool(new_calls),
            "calls": new_calls,
            "texts": extract_texts(new_calls),
            "to_me": bool(event.to_me),
        }

    # -- 私聊 --------------------------------------------------------------

    def make_private_event(self, text: str, *, user_id: int, message_id: int = 2001) -> dict[str, Any]:
        """构造一条私聊消息事件。"""
        return {
            "post_type": "message",
            "message_type": "private",
            "sub_type": "friend",
            "message_id": message_id,
            "user_id": user_id,
            "time": int(time.time()),
            "self_id": int(SELF_ID),
            "raw_message": text,
            "font": 0,
            "sender": {"user_id": user_id, "nickname": "测试好友"},
            "message": [{"type": "text", "data": {"text": text}}],
        }

    async def send_private_message(self, text: str, *, user_id: int) -> dict[str, Any]:
        """投递一条私聊消息。私聊里 ``to_me`` 恒为 True，不需要 @。"""
        before = len(self.api_calls)
        event = PrivateMessageEvent.model_validate(self.make_private_event(text, user_id=user_id))

        finished = False
        try:
            await self.bot.handle_event(event)
        except FinishedException:
            finished = True
        except Exception as exc:  # noqa: BLE001
            raise AssertionError(f"处理私聊消息时出现未预期异常：{type(exc).__name__}: {exc}") from exc

        new_calls = self.api_calls[before:]
        return {
            "finished": finished,
            "responded": bool(new_calls),
            "calls": new_calls,
            "texts": extract_texts(new_calls),
            "to_me": bool(event.to_me),
        }

    # -- 便捷断言辅助 ----------------------------------------------------

    @property
    def last_texts(self) -> list[str]:
        """最后一次发送的文本列表。"""
        return extract_texts(self.api_calls[-1:])

    @property
    def all_texts(self) -> list[str]:
        return extract_texts(self.api_calls)


def extract_texts(calls: list[dict[str, Any]]) -> list[str]:
    """把 ``call_api`` 记录里的消息内容拼成纯文本。"""
    texts: list[str] = []
    for call in calls:
        message = call.get("params", {}).get("message")
        if isinstance(message, Message):
            texts.append(message.extract_plain_text())
        elif isinstance(message, (list, tuple)):
            buffer = []
            for seg in message:
                if isinstance(seg, dict) and seg.get("type") == "text":
                    buffer.append(str(seg.get("data", {}).get("text", "")))
            texts.append("".join(buffer))
        elif isinstance(message, str):
            texts.append(message)
        else:
            texts.append("")
    return texts


def extract_ats(calls: list[dict[str, Any]]) -> list[str]:
    """取出消息里 @ 了谁。"""
    result: list[str] = []
    for call in calls:
        message = call.get("params", {}).get("message")
        segments: list[Any] = []
        if isinstance(message, Message):
            segments = list(message)
        elif isinstance(message, (list, tuple)):
            segments = list(message)
        for seg in segments:
            if isinstance(seg, MessageSegment) and seg.type == "at":
                result.append(str(seg.data.get("qq", "")))
            elif isinstance(seg, dict) and seg.get("type") == "at":
                result.append(str(seg.get("data", {}).get("qq", "")))
    return result


__all__ = ["BotHarness", "SELF_ID", "extract_ats", "extract_texts"]
