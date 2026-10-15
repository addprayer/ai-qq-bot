"""pytest 公共准备工作。

这里做两件事：

1. **在任何模块导入之前**设置测试用的环境变量，
   避免测试读到真实 ``.env`` 里的密钥，也避免因为没填配置而失败。
2. 提供几个常用 fixture（假的机器人对象、模拟事件、自造的 AI 客户端）。
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# 1. 让 tests/ 能 import 到项目根目录下的 config 与 src
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# ---------------------------------------------------------------------------
# 2. 先设置测试环境变量（必须在 import config / src 之前）
#
#    注意：pydantic-settings 里「进程环境变量」优先级高于 .env 文件，
#    所以这里设好之后，测试就不会被真实的 .env 影响。
# ---------------------------------------------------------------------------
TEST_API_KEY = "sk-test-0000000000000000000000000000"
TEST_TOKEN = "test-token-1234567890"

os.environ.update(
    {
        "BOT_NAME": "测试助手",
        "AI_API_KEY": TEST_API_KEY,
        "AI_BASE_URL": "https://api.deepseek.com",
        "AI_MODEL": "deepseek-chat",
        "AI_TIMEOUT": "5",
        "AI_MAX_RETRIES": "0",
        "AI_TEMPERATURE": "0.0",
        "AI_MAX_TOKENS": "100",
        "AI_SYSTEM_PROMPT": "测试用系统提示",
        "ONEBOT_ACCESS_TOKEN": TEST_TOKEN,
        "ONEBOT_WS_URLS": "[]",
        "HOST": "127.0.0.1",
        "PORT": "8080",
        "LOG_LEVEL": "WARNING",
        "LOG_TO_FILE": "false",
        "HISTORY_MAX_TURNS": "3",
        "HISTORY_BACKEND": "memory",
        "HISTORY_DB_PATH": "",
        "MAX_QUESTION_LENGTH": "100",
        "MAX_REPLY_LENGTH": "200",
        "COOLDOWN_SECONDS": "5",
        # NoneBot 自己也会解析这两个环境变量，所以要用它认识的 JSON 写法
        "SUPERUSERS": "[]",
        "COMMAND_START": '["/"]',
    }
)

import pytest  # noqa: E402

# ---------------------------------------------------------------------------
# 3. 初始化 NoneBot
#
#    on_command / on_message 这类装饰器需要 driver 已经初始化，
#    否则会报 "NoneBot has not been initialized."。
#    注意：必须在 import src.ai_chat 之前执行。
# ---------------------------------------------------------------------------
import nonebot  # noqa: E402

nonebot.init(
    driver="~fastapi+~websockets",
    log_level="WARNING",
    host="127.0.0.1",
    port=8080,
    onebot_access_token=TEST_TOKEN,
)


# ---------------------------------------------------------------------------
# 4. fixture
# ---------------------------------------------------------------------------


@pytest.fixture()
def work_dir() -> "Path":
    """一个可读写的临时目录。

    不用 pytest 自带的 ``tmp_path``：它内部用 ``tempfile.mkdtemp`` 创建权限为
    ``0o700`` 的目录，在开启文件沙箱的环境里会导致
    ``PermissionError: [WinError 5]``（连 SQLite 都打不开数据库文件）。
    这里改用普通 ``mkdir``（权限正常），测试结束后尽力清理。
    """
    import shutil
    import uuid

    base = PROJECT_ROOT / ".tmp" / "tests"
    base.mkdir(parents=True, exist_ok=True)
    path = base / f"case-{uuid.uuid4().hex[:8]}"
    path.mkdir(parents=True, exist_ok=True)
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)


@pytest.fixture()
def settings():
    """一份干净的配置对象（每次测试都重新从环境变量读取）。"""
    from config import reload_settings

    return reload_settings()


@pytest.fixture()
def fake_ai():
    """一个可控的假 AI 客户端，用来验证「成功」路径与上下文传递。"""

    class FakeAIClient:
        configured = True

        def __init__(self) -> None:
            from src.ai_client import AIResult

            self._result_cls = AIResult
            self.calls: list[tuple[str, list]] = []
            self.next_reply = "这是测试回复"
            self.next_ok = True

        async def chat(self, question, history=()):  # noqa: ANN001, ANN201
            self.calls.append((question, list(history)))
            if self.next_ok:
                return self._result_cls(ok=True, text=self.next_reply, usage={"total_tokens": 1})
            return self._result_cls(ok=False, text="模拟失败", error_kind="unknown_error")

    return FakeAIClient()


@pytest.fixture()
def harness(monkeypatch, fake_ai):
    """测试抓手：构造假的 Bot + 事件，并驱动真实的响应器。

    用法::

        await harness.send_group_message("你好", user_id=111, group_id=222)
        print(harness.sent_texts)     # 机器人实际发出的文本
    """
    from tests.harness import BotHarness

    with BotHarness(ai_client=fake_ai) as h:
        yield h
