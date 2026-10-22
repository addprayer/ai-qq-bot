"""指令与对话逻辑测试。

覆盖：
* /帮助、/清空、/ai 的指令逻辑
* @机器人才触发，普通群消息不触发
* 不同群、不同用户的上下文隔离
* 冷却时间
* AI 失败时的错误处理与「失败不写入历史」
* 输入/输出长度限制
"""

from __future__ import annotations

import pytest

from tests.harness import SELF_ID, extract_ats, extract_texts


def _http_client_module():
    """取 openai SDK 使用的 HTTP 客户端模块。

    openai 1.x / 2.x 用 ``httpx``，3.x 换成了 ``httpx2``，
    这里做兼容，避免因为 SDK 升级把测试弄挂。
    """
    try:
        import httpx2 as http_client  # type: ignore[import-not-found]
    except ImportError:  # pragma: no cover - 取决于安装的 openai 版本
        import httpx as http_client  # type: ignore[no-redef]
    return http_client

# ---------------------------------------------------------------------------
# 纯函数：文本处理
# ---------------------------------------------------------------------------


def test_extract_mention_question_removes_cq_at() -> None:
    from src.message_handler import extract_mention_question

    assert extract_mention_question(f"[CQ:at,qq={SELF_ID}] 什么是快速排序？", SELF_ID) == "什么是快速排序？"
    assert extract_mention_question(f"[CQ:at,qq={SELF_ID}]你好", SELF_ID) == "你好"


def test_extract_mention_question_removes_plain_at() -> None:
    from src.message_handler import extract_mention_question

    assert extract_mention_question("@AI助手 讲个笑话", SELF_ID) == "讲个笑话"


def test_normalize_question_collapses_whitespace_and_truncates() -> None:
    from src.message_handler import normalize_question

    assert normalize_question("  你好   世界  ", 100) == "你好 世界"
    assert len(normalize_question("啊" * 50, 10)) == 10


def test_truncate_reply_adds_marker() -> None:
    from src.message_handler import truncate_reply

    assert truncate_reply("短回复", 100) == "短回复"
    long_reply = truncate_reply("长" * 500, 50)
    assert len(long_reply) <= 50
    assert "已截断" in long_reply


def test_to_single_line_removes_newlines() -> None:
    from src.message_handler import to_single_line

    # 中文换行直接去掉，不留空格
    assert to_single_line("第一句。\n第二句。") == "第一句。第二句。"
    assert to_single_line("（笑）\r\n嗯，我在。") == "（笑）嗯，我在。"
    # 英文单词之间要留一个空格，不能粘成一个词
    assert to_single_line("hello\nworld") == "hello world"
    # 首尾空白和多余空格会被清掉
    assert to_single_line("  你 好  \n\n") == "你 好"
    assert to_single_line("") == ""
    assert to_single_line(None) == ""  # type: ignore[arg-type]


def test_truncate_reply_outputs_single_line() -> None:
    from src.message_handler import truncate_reply

    assert truncate_reply("第一行\n第二行\n第三行", 200) == "第一行第二行第三行"


def test_is_too_long() -> None:
    from src.message_handler import is_too_long

    assert is_too_long("a" * 10, limit=5) is True
    assert is_too_long("abc", limit=5) is False


def test_session_key_separates_groups_and_users() -> None:
    from src.message_handler import session_key

    assert session_key(111, 222) == ("111", "222")
    assert session_key(111, 333) != session_key(222, 333)
    assert session_key(None, 222) == ("private", "222")


def test_help_text_contains_all_commands() -> None:
    from src.message_handler import build_help_text

    text = build_help_text("测试助手", 5.0, 3)
    for command in ("/ai", "/帮助", "/清空", "@"):
        assert command in text


def test_split_ai_command_variants() -> None:
    from src.ai_chat import split_ai_command

    assert split_ai_command("/ai 你好") == "你好"
    assert split_ai_command("/ai你好") == "你好"
    assert split_ai_command("/AI 你好") == "你好"
    assert split_ai_command("/ai") == ""
    assert split_ai_command("你好") is None
    assert split_ai_command("/帮助") is None


# ---------------------------------------------------------------------------
# 历史隔离（纯逻辑，不经过事件流程）
# ---------------------------------------------------------------------------


def test_history_isolation_between_users_and_groups() -> None:
    """同一个群不同用户、不同群同一用户，历史必须互相隔离。"""
    from src.history import InMemoryHistoryStore

    store = InMemoryHistoryStore(max_turns=5)
    store.append_turn("群A", "用户1", "问题A1", "回答A1")
    store.append_turn("群A", "用户2", "问题A2", "回答A2")
    store.append_turn("群B", "用户1", "问题B1", "回答B1")

    a1 = store.get_messages("群A", "用户1")
    a2 = store.get_messages("群A", "用户2")
    b1 = store.get_messages("群B", "用户1")

    assert [m["content"] for m in a1] == ["问题A1", "回答A1"]
    assert [m["content"] for m in a2] == ["问题A2", "回答A2"]
    assert [m["content"] for m in b1] == ["问题B1", "回答B1"]


def test_history_keeps_only_recent_turns() -> None:
    """超过轮数上限时，最老的对话要被丢掉（控制 token 费用）。"""
    from src.history import InMemoryHistoryStore

    store = InMemoryHistoryStore(max_turns=2)
    for i in range(1, 5):
        store.append_turn("群", "用户", f"问题{i}", f"回答{i}")

    contents = [m["content"] for m in store.get_messages("群", "用户")]
    assert contents == ["问题3", "回答3", "问题4", "回答4"]
    assert store.turn_count("群", "用户") == 2


def test_history_clear_only_affects_target() -> None:
    from src.history import InMemoryHistoryStore

    store = InMemoryHistoryStore(max_turns=5)
    store.append_turn("群", "用户1", "q", "a")
    store.append_turn("群", "用户2", "q", "a")

    removed = store.clear("群", "用户1")
    assert removed == 2
    assert store.get_messages("群", "用户1") == []
    assert len(store.get_messages("群", "用户2")) == 2


def test_history_lru_eviction() -> None:
    """跟踪的用户数超上限时，淘汰最久未使用的会话，避免内存无限增长。"""
    from src.history import InMemoryHistoryStore

    store = InMemoryHistoryStore(max_turns=5, max_users=2)
    store.append_turn("群", "u1", "q1", "a1")
    store.append_turn("群", "u2", "q2", "a2")
    store.append_turn("群", "u3", "q3", "a3")

    assert store.session_count == 2
    assert store.get_messages("群", "u1") == []  # 最早的被淘汰


def test_cooldown_tracker() -> None:
    from src.history import CooldownTracker

    now = [1000.0]
    tracker = CooldownTracker(5.0, clock=lambda: now[0])

    assert tracker.check("群", "u") == 0.0
    tracker.touch("群", "u")
    assert tracker.check("群", "u") == pytest.approx(5.0)

    now[0] += 2.0
    assert tracker.check("群", "u") == pytest.approx(3.0)

    now[0] += 5.0
    assert tracker.check("群", "u") == 0.0

    # 别的用户不受影响
    assert tracker.check("群", "其他人") == 0.0


def test_sqlite_history_persists(work_dir) -> None:
    """SQLite 后端能够持久化，并且重启后仍能读到。"""
    from src.history import SQLiteHistoryStore

    db = work_dir / "history.db"
    store = SQLiteHistoryStore(db, max_turns=3)
    store.append_turn("群", "用户", "问题", "回答")
    store.close()

    reopened = SQLiteHistoryStore(db, max_turns=3)
    assert [m["content"] for m in reopened.get_messages("群", "用户")] == ["问题", "回答"]
    assert reopened.clear("群", "用户") == 1
    assert reopened.turn_count("群", "用户") == 0
    reopened.close()


# ---------------------------------------------------------------------------
# /帮助
# ---------------------------------------------------------------------------


async def test_help_command_replies(harness) -> None:
    result = await harness.send_group_message("/帮助", user_id=10001, group_id=555)
    assert result["responded"] is True
    assert any("使用说明" in text for text in result["texts"])
    assert "/ai" in result["texts"][0]


async def test_help_command_with_at_prefix(harness) -> None:
    """@机器人 /帮助 也要能命中 /帮助 指令。"""
    result = await harness.send_group_message("/帮助", user_id=10001, group_id=555, at_me=True)
    assert any("使用说明" in text for text in result["texts"])


# ---------------------------------------------------------------------------
# /清空
# ---------------------------------------------------------------------------


async def test_clear_command_when_no_history(harness) -> None:
    result = await harness.send_group_message("/清空", user_id=10001, group_id=555)
    assert result["responded"] is True
    assert any("没有对话记录" in text for text in result["texts"])


async def test_clear_command_after_chat(harness) -> None:
    await harness.send_group_message("你好", user_id=10001, group_id=555, at_me=True)
    assert harness.plugin._history.turn_count("555", "10001") == 1

    result = await harness.send_group_message("/清空", user_id=10001, group_id=555)
    assert any("已清除" in text for text in result["texts"])
    assert harness.plugin._history.turn_count("555", "10001") == 0


async def test_clear_only_clears_own_group_history(harness) -> None:
    """清空只影响「自己 + 本群」，不能影响别人或别的群。"""
    await harness.send_group_message("我的问题", user_id=10001, group_id=555, at_me=True)
    await harness.send_group_message("别人的问题", user_id=20002, group_id=555, at_me=True)
    await harness.send_group_message("我在别的群", user_id=10001, group_id=666, at_me=True)

    await harness.send_group_message("/清空", user_id=10001, group_id=555)

    assert harness.plugin._history.turn_count("555", "10001") == 0
    assert harness.plugin._history.turn_count("555", "20002") == 1
    assert harness.plugin._history.turn_count("666", "10001") == 1


# ---------------------------------------------------------------------------
# 触发方式
# ---------------------------------------------------------------------------


async def test_plain_group_message_does_not_trigger_ai(harness) -> None:
    """普通闲聊不能被当成提问——这是「不默认对每条消息调用 AI」的保证。"""
    result = await harness.send_group_message("今天天气不错", user_id=10001, group_id=555)
    assert result["responded"] is False
    assert result["calls"] == []
    assert harness.ai.calls == []


async def test_at_me_triggers_ai(harness) -> None:
    result = await harness.send_group_message("什么是快速排序", user_id=10001, group_id=555, at_me=True)
    assert harness.ai.calls[-1][0] == "什么是快速排序"
    assert any("这是测试回复" in text for text in result["texts"])
    # 回复里要 @ 提问的人
    assert "10001" in extract_ats(result["calls"])


async def test_ai_command_triggers_ai(harness) -> None:
    await harness.send_group_message("/ai 帮我写个函数", user_id=10001, group_id=555)
    assert harness.ai.calls[-1][0] == "帮我写个函数"


async def test_ai_command_without_space(harness) -> None:
    await harness.send_group_message("/ai帮我写个函数", user_id=10001, group_id=555)
    assert harness.ai.calls[-1][0] == "帮我写个函数"


async def test_empty_message_never_prints_help_menu(harness) -> None:
    """空消息可以回一句人话，但绝不能甩出「AI 助手使用说明」那套菜单。"""
    result = await harness.send_group_message("", user_id=10001, group_id=555, at_me=True)
    assert harness.ai.calls == []
    joined = "".join(result["texts"])
    assert "你想问点什么呢" not in joined
    assert "@我 后面直接跟问题" not in joined
    assert "/帮助 查看完整说明" not in joined
    assert joined.strip(), "至少要给一句回应，不能完全沉默"


def _stub_prepare(monkeypatch):
    """把图片准备替换成固定结果，避免测试里真的去下载。"""
    from src.image_input import PreparedImage

    async def fake_prepare(urls, limit=3):
        return [PreparedImage(source="data:image/png;base64,AAA", mime="image/png", size=3, inlined=True)] if urls else []

    monkeypatch.setattr("src.ai_chat.prepare_images", fake_prepare)


async def test_image_only_message_goes_to_ai_with_image(harness, monkeypatch) -> None:
    _stub_prepare(monkeypatch)
    """只发一张表情包：不能被当成「什么都没说」，也不能弹帮助菜单。

    现在会把图片一起发给模型（下载失败时降级为传链接），
    本轮问答也不能是空字符串。
    """
    from nonebot.adapters.onebot.v11 import GroupMessageEvent

    event_dict = harness.make_group_event("", user_id=10001, group_id=555, at_me=True)
    event_dict["message"] = [
        {"type": "at", "data": {"qq": SELF_ID}},
        {"type": "image", "data": {"file": "abc.jpg", "url": "http://example.com/a.jpg", "summary": "[动画表情]"}},
    ]
    event = GroupMessageEvent.model_validate(event_dict)
    before = len(harness.api_calls)
    await harness.bot.handle_event(event)
    joined = "".join(extract_texts(harness.api_calls[before:]))

    assert "你想问点什么呢" not in joined
    assert "/帮助" not in joined
    assert harness.ai.calls, "有图就应该交给模型看"
    question, _history, images = harness.ai.calls[-1]
    assert question.strip(), "不能把空字符串丢给模型"
    assert images, "图片应该被带进请求"


async def test_text_plus_image_sends_both(harness, monkeypatch) -> None:
    _stub_prepare(monkeypatch)
    """「图 + 一句话」：文字照常处理，图片一起发过去。"""
    from nonebot.adapters.onebot.v11 import GroupMessageEvent

    event_dict = harness.make_group_event("这张图什么意思", user_id=10001, group_id=555, at_me=True)
    event_dict["message"] = [
        {"type": "at", "data": {"qq": SELF_ID}},
        {"type": "text", "data": {"text": " 这张图什么意思"}},
        {"type": "image", "data": {"file": "x.jpg", "url": "http://example.com/x.jpg"}},
    ]
    event = GroupMessageEvent.model_validate(event_dict)
    await harness.bot.handle_event(event)
    assert harness.ai.calls, "带文字时应该正常调用 AI"
    question, _history, images = harness.ai.calls[-1]
    assert "这张图什么意思" in question
    assert len(images) == 1


def test_image_urls_extracts_links() -> None:
    """_image_urls 要把消息里的图片链接都取出来，忽略文字段。"""
    from nonebot.adapters.onebot.v11 import GroupMessageEvent

    from src.ai_chat import _image_urls
    import time

    event = GroupMessageEvent.model_validate(
        {
            "post_type": "message",
            "message_type": "group",
            "sub_type": "normal",
            "message_id": 1,
            "group_id": 1,
            "user_id": 2,
            "time": int(time.time()),
            "self_id": int(SELF_ID),
            "raw_message": "hi",
            "font": 0,
            "sender": {"user_id": 2, "nickname": "x"},
            "message": [
                {"type": "text", "data": {"text": "hi"}},
                {"type": "image", "data": {"url": "http://a/1.png"}},
                {"type": "image", "data": {"url": "http://a/2.gif"}},
                {"type": "image", "data": {}},  # 没有 url 的跳过
            ],
        }
    )
    assert _image_urls(event) == ["http://a/1.png", "http://a/2.gif"]


def test_build_messages_with_images_uses_content_blocks() -> None:
    """有图片时，用户消息必须构造成 text + image_url 的数组形式。"""
    from src.ai_client import AIClient

    client = AIClient(
        api_key="sk-example-0000000000000000000000",
        base_url="https://api.deepseek.com",
        model="deepseek-chat",
        system_prompt="sys",
    )
    messages = client._build_messages(  # noqa: SLF001
        "看图", [{"role": "user", "content": "上一轮"}], ["data:image/png;base64,AAA"]
    )
    user_msg = messages[-1]
    assert isinstance(user_msg["content"], list)
    assert user_msg["content"][0] == {"type": "text", "text": "看图"}
    assert user_msg["content"][1]["type"] == "image_url"
    assert user_msg["content"][1]["image_url"]["url"] == "data:image/png;base64,AAA"

    # 没有图片时仍然是纯字符串（保持旧行为，省 token）
    plain = client._build_messages("看图", [])  # noqa: SLF001
    assert plain[-1]["content"] == "看图"


def test_build_messages_placeholder_when_image_only() -> None:
    """只有图片时，chat() 要自动补一句占位说明，不能发空文本。"""
    from src.ai_client import AIClient

    client = AIClient(
        api_key="sk-example-0000000000000000000000",
        base_url="https://api.deepseek.com",
        model="deepseek-chat",
        system_prompt="sys",
    )
    messages = client._build_messages("（对方只发来了图片，没有配文字）", [], ["data:image/png;base64,AAA"])  # noqa: SLF001
    assert "图片" in messages[-1]["content"][0]["text"]


# ---------------------------------------------------------------------------
# 上下文传给 AI
# ---------------------------------------------------------------------------


async def test_history_is_passed_to_ai(harness) -> None:
    await harness.send_group_message("第一个问题", user_id=10001, group_id=555, at_me=True)
    await harness.send_group_message("第二个问题", user_id=10001, group_id=555, at_me=True)

    second_history = harness.ai.calls[-1][1]
    assert [m["content"] for m in second_history] == ["第一个问题", "这是测试回复"]


async def test_ai_context_isolated_between_users(harness) -> None:
    await harness.send_group_message("甲的问题", user_id=10001, group_id=555, at_me=True)
    await harness.send_group_message("乙的问题", user_id=20002, group_id=555, at_me=True)

    yi_history = harness.ai.calls[-1][1]
    assert yi_history == [], "不同用户的上下文串了"


async def test_ai_context_isolated_between_groups(harness) -> None:
    await harness.send_group_message("群一的问题", user_id=10001, group_id=555, at_me=True)
    await harness.send_group_message("群二的问题", user_id=10001, group_id=666, at_me=True)

    assert harness.ai.calls[-1][1] == [], "不同群的上下文串了"


# ---------------------------------------------------------------------------
# 长度限制
# ---------------------------------------------------------------------------


async def test_overlong_question_is_rejected(harness) -> None:
    """超过 max_question_length 的提问要被拒绝，不花冤枉钱。"""
    result = await harness.send_group_message("啊" * 500, user_id=10001, group_id=555, at_me=True)
    assert harness.ai.calls == []
    assert any("太长" in text for text in result["texts"])


async def test_overlong_reply_is_truncated(harness) -> None:
    harness.ai.next_reply = "很长" * 500
    result = await harness.send_group_message("你好", user_id=10001, group_id=555, at_me=True)
    reply = result["texts"][-1]
    assert len(reply) < 400
    assert "已截断" in reply


# ---------------------------------------------------------------------------
# 冷却
# ---------------------------------------------------------------------------


async def test_cooldown_blocks_rapid_requests(fake_ai) -> None:
    from tests.harness import BotHarness

    with BotHarness(ai_client=fake_ai, cooldown_seconds=5.0) as h:
        await h.send_group_message("第一问", user_id=10001, group_id=555, at_me=True)
        assert len(fake_ai.calls) == 1

        result = await h.send_group_message("第二问", user_id=10001, group_id=555, at_me=True)
        assert len(fake_ai.calls) == 1, "冷却期内不该再次调用 AI"
        assert any("慢一点" in text for text in result["texts"])


async def test_cooldown_does_not_block_other_users(fake_ai) -> None:
    from tests.harness import BotHarness

    with BotHarness(ai_client=fake_ai, cooldown_seconds=5.0) as h:
        await h.send_group_message("甲问", user_id=10001, group_id=555, at_me=True)
        await h.send_group_message("乙问", user_id=20002, group_id=555, at_me=True)
        assert len(fake_ai.calls) == 2


# ---------------------------------------------------------------------------
# AI 失败处理
# ---------------------------------------------------------------------------


async def test_ai_failure_returns_friendly_message(harness) -> None:
    harness.ai.next_ok = False
    result = await harness.send_group_message("你好", user_id=10001, group_id=555, at_me=True)
    assert any("模拟失败" in text for text in result["texts"])
    # 失败时不该污染上下文
    assert harness.plugin._history.turn_count("555", "10001") == 0


async def test_ai_not_configured(settings) -> None:
    """没有配置 API Key 时给出明确提示，而不是抛异常。"""
    from src.ai_client import AIClient

    client = AIClient(
        api_key="",
        base_url="https://api.deepseek.com",
        model="deepseek-chat",
        system_prompt="x",
    )
    assert client.configured is False
    result = await client.chat("你好")
    assert result.ok is False
    assert result.error_kind == "not_configured"
    assert "AI_API_KEY" in result.text


# ---------------------------------------------------------------------------
# 私聊
# ---------------------------------------------------------------------------


async def test_private_help_command(harness) -> None:
    """私聊 /帮助 要有响应。"""
    result = await harness.send_private_message("/帮助", user_id=10001)
    assert result["responded"] is True
    assert any("使用说明" in text for text in result["texts"])


async def test_private_plain_text_triggers_ai(harness) -> None:
    """私聊里 to_me 恒为 True，所以直接发问题就会触发（不需要 @）。"""
    result = await harness.send_private_message("你好，介绍一下你自己", user_id=10001)
    assert result["to_me"] is True
    assert harness.ai.calls[-1][0] == "你好，介绍一下你自己"
    assert any("这是测试回复" in text for text in result["texts"])


async def test_private_ai_command(harness) -> None:
    await harness.send_private_message("/ai 什么是二分查找", user_id=10001)
    assert harness.ai.calls[-1][0] == "什么是二分查找"


async def test_private_and_group_history_are_isolated(harness) -> None:
    """私聊记忆与群聊记忆必须互不影响（私聊的 group 键是 "private"）。"""
    await harness.send_private_message("私聊里说的话", user_id=10001)
    await harness.send_group_message("群里说的话", user_id=10001, group_id=555, at_me=True)

    history = harness.plugin._history
    assert history.turn_count("private", "10001") == 1
    assert history.turn_count("555", "10001") == 1

    # 群里的那次调用不应该带上私聊的历史
    assert harness.ai.calls[-1][1] == []


async def test_private_clear_only_affects_private(harness) -> None:
    await harness.send_private_message("私聊内容", user_id=10001)
    await harness.send_group_message("群内容", user_id=10001, group_id=555, at_me=True)

    result = await harness.send_private_message("/清空", user_id=10001)
    assert any("已清除" in text and "私聊" in text for text in result["texts"])
    assert harness.plugin._history.turn_count("private", "10001") == 0
    assert harness.plugin._history.turn_count("555", "10001") == 1  # 群记忆不受影响


# ---------------------------------------------------------------------------
# 错误翻译
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("status", "expected_kind"),
    [
        (401, "auth_failed"),
        (402, "insufficient_balance"),
        (404, "model_not_found"),
        (429, "rate_limited"),
        (500, "server_error"),
    ],
)
def test_classify_http_status_errors(status: int, expected_kind: str) -> None:
    httpx = _http_client_module()
    from openai import APIStatusError

    from src.ai_client import classify_error

    request = httpx.Request("POST", "https://api.deepseek.com/chat/completions")
    response = httpx.Response(status, request=request)
    exc = APIStatusError("boom", response=response, body=None)
    kind, message = classify_error(exc)
    assert kind == expected_kind
    assert message  # 有给用户看的中文提示
    assert "sk-" not in message


def test_classify_timeout_and_network_errors() -> None:
    httpx = _http_client_module()
    from openai import APIConnectionError, APITimeoutError

    from src.ai_client import classify_error

    request = httpx.Request("POST", "https://api.deepseek.com/chat/completions")
    kind, message = classify_error(APITimeoutError(request=request))
    assert kind == "timeout"
    assert "超时" in message

    kind, message = classify_error(APIConnectionError(request=request))
    assert kind == "network_error"
    assert "网络" in message


def test_classify_unknown_error() -> None:
    from src.ai_client import classify_error

    kind, message = classify_error(ValueError("意外情况"))
    assert kind == "unknown_error"
    assert message
