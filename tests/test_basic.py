"""基础检查：语法、导入、配置、密钥安全、Git 忽略规则。

这些测试对应「六、测试要求」里除了 AI 交互之外的所有检查项。
"""

from __future__ import annotations

import compileall
import os
import subprocess
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent


# ---------------------------------------------------------------------------
# 1. 语法检查
# ---------------------------------------------------------------------------


def test_all_python_files_compile() -> None:
    """所有 .py 文件都能通过语法编译（等价于 py_compile）。"""
    ok = compileall.compile_dir(
        str(PROJECT_ROOT / "src"),
        quiet=2,
        force=True,
    )
    ok = compileall.compile_file(str(PROJECT_ROOT / "bot.py"), quiet=2, force=True) and ok
    ok = compileall.compile_file(str(PROJECT_ROOT / "config.py"), quiet=2, force=True) and ok
    ok = compileall.compile_dir(str(PROJECT_ROOT / "tests"), quiet=2, force=True) and ok
    assert ok, "存在语法错误的 .py 文件"


def test_py_compile_via_subprocess() -> None:
    """用 python -m py_compile 再验证一次（与文档里给用户的命令一致）。"""
    targets = [
        PROJECT_ROOT / "bot.py",
        PROJECT_ROOT / "config.py",
        PROJECT_ROOT / "src" / "ai_client.py",
        PROJECT_ROOT / "src" / "ai_chat.py",
        PROJECT_ROOT / "src" / "history.py",
        PROJECT_ROOT / "src" / "message_handler.py",
        PROJECT_ROOT / "src" / "logging_setup.py",
    ]
    result = subprocess.run(
        [sys.executable, "-m", "py_compile", *map(str, targets)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, f"py_compile 失败：{result.stderr}"


# ---------------------------------------------------------------------------
# 2. 依赖与模块导入
# ---------------------------------------------------------------------------


def test_dependencies_importable() -> None:
    """第三方依赖都能正常导入，并且版本不低于最低要求。"""
    import fastapi
    import nonebot
    import openai
    import pydantic
    import pydantic_settings
    import pytest as pytest_module
    import uvicorn
    import websockets

    assert nonebot.__version__ >= "2.0"
    assert openai.__version__ >= "1.0"
    assert pydantic.VERSION >= "2.0"
    assert fastapi.__version__
    assert uvicorn.__version__
    assert websockets.__version__
    assert pydantic_settings.__version__
    assert pytest_module.__version__


def test_project_modules_importable() -> None:
    """项目自己的模块都能导入。"""
    import config
    import src.ai_client
    import src.history
    import src.logging_setup
    import src.message_handler

    assert config.ENV_FILE.name == ".env"
    assert hasattr(src.ai_client, "AIClient")
    assert hasattr(src.history, "InMemoryHistoryStore")


def test_onebot_adapter_importable() -> None:
    """OneBot V11 适配器的关键对象存在（防止用到已废弃的接口）。"""
    from nonebot.adapters.onebot.v11 import Adapter, Bot, GroupMessageEvent, Message, MessageSegment

    assert Adapter.get_name() == "OneBot V11"
    assert MessageSegment.at(123).type == "at"
    assert MessageSegment.reply(1).type == "reply"
    assert Bot is not None
    assert GroupMessageEvent is not None
    assert Message("abc").extract_plain_text() == "abc"


# ---------------------------------------------------------------------------
# 3. 配置：缺失与错误时的提示
# ---------------------------------------------------------------------------


def test_missing_env_file_raises_helpful_error(monkeypatch, work_dir: Path) -> None:
    """找不到 .env 时，必须抛出带「怎么修」说明的错误，而不是一句天书。"""
    import config

    monkeypatch.setattr(config, "ENV_FILE", work_dir / "不存在的.env")
    fresh = config.Settings()  # 环境变量仍然齐全，所以能构造出来

    with pytest.raises(config.ConfigError) as excinfo:
        config.validate_runtime_config(fresh)

    message = str(excinfo.value)
    assert ".env" in message
    assert ".env.example" in message  # 告诉用户去哪拿模板


def test_bad_api_key_format_is_rejected(monkeypatch) -> None:
    """API Key 格式明显不对时，要给出可读的中文提示。"""
    from pydantic import ValidationError

    import config

    monkeypatch.setenv("AI_API_KEY", "这不是一个sk开头的key")
    with pytest.raises(ValidationError) as excinfo:
        config.Settings()
    assert "AI_API_KEY" in str(excinfo.value)


def test_empty_api_key_is_allowed(monkeypatch) -> None:
    """没填 API Key 时允许启动（只是功能受限），并给出警告。"""
    import config

    monkeypatch.setenv("AI_API_KEY", "")
    settings = config.Settings()
    assert settings.is_ai_configured is False

    monkeypatch.setattr(config, "ENV_FILE", config.ENV_FILE)  # 保持真实 .env 路径
    warnings = config.validate_runtime_config(settings)
    assert any("AI_API_KEY" in w for w in warnings)


def test_public_host_triggers_warning(monkeypatch) -> None:
    """监听地址改成 0.0.0.0 时要提醒用户有暴露风险。"""
    import config

    monkeypatch.setenv("HOST", "0.0.0.0")
    monkeypatch.setenv("ONEBOT_ACCESS_TOKEN", "a-strong-token-123")
    settings = config.Settings()
    warnings = config.validate_runtime_config(settings)
    assert any("暴露" in w or "公网" in w for w in warnings)


def test_default_host_is_localhost(settings) -> None:
    """默认只监听本机地址。"""
    assert settings.host == "127.0.0.1"
    assert settings.port == 8080


def test_env_list_parsing() -> None:
    """`.env` 里列表型配置的容错解析。"""
    from config import parse_str_list

    assert parse_str_list('["123", "456"]') == ["123", "456"]
    assert parse_str_list("123,456") == ["123", "456"]
    assert parse_str_list("[]") == []
    assert parse_str_list("") == []
    assert parse_str_list(None) == []


def test_settings_repr_masks_secrets(settings) -> None:
    """打印配置对象时不能泄露完整 API Key。"""
    from tests.conftest import TEST_API_KEY

    assert TEST_API_KEY not in settings.describe()
    assert TEST_API_KEY not in settings.model_dump_json()
    assert "****" in settings.masked_api_key()


# ---------------------------------------------------------------------------
# 3.1 NoneBot 框架配置兼容性
#
# 回归测试：NoneBot 自己也会解析 SUPERUSERS / COMMAND_START，且只认合法 JSON。
# 只要 .env 里写成 `SUPERUSERS=`（空值）或 `SUPERUSERS=123,456`（逗号分隔），
# 启动就会抛 `SettingsError: error parsing env var "superusers"`。
# 这个坑真实发生过，必须锁住。
# ---------------------------------------------------------------------------


def test_sync_framework_env_writes_valid_json(monkeypatch) -> None:
    """无论 .env 写成哪种形式，回写到环境变量的都必须是 NoneBot 能解析的 JSON。"""
    import json

    import config

    cases = {
        # .env 里的原始写法 -> 期望 NoneBot 看到的 JSON
        "": [],
        "   ": [],
        "[]": [],
        "123456,789012": ["123456", "789012"],
        '["123456"]': ["123456"],
        "123456": ["123456"],
    }
    for raw in cases:
        monkeypatch.setenv("SUPERUSERS", raw)
        monkeypatch.setenv("COMMAND_START", raw or '["/"]')
        fresh = config.Settings()
        written = config.sync_framework_env(fresh)

        # 写回环境变量的必须是合法 JSON，且能被 NoneBot 的解析方式读懂
        parsed = json.loads(written["SUPERUSERS"])
        assert isinstance(parsed, list)
        assert parsed == sorted(cases[raw]) or set(parsed) == set(cases[raw])
        assert json.loads(os.environ["SUPERUSERS"]) == parsed


def test_nonebot_init_survives_empty_superusers(monkeypatch) -> None:
    """空值 / 逗号分隔的 SUPERUSERS 经过规范化后，NoneBot 必须能正常初始化。"""
    import config

    for raw in ("", "123456,789012", "[]"):
        monkeypatch.setenv("SUPERUSERS", raw)
        monkeypatch.setenv("COMMAND_START", '["/"]')
        fresh = config.Settings()
        config.sync_framework_env(fresh)

        # 这里若抛 SettingsError，说明兼容处理失效
        import nonebot

        nonebot.init(driver="~fastapi+~websockets", log_level="CRITICAL")
        assert nonebot.get_driver().config.superusers is not None


def test_env_example_has_no_empty_list_values() -> None:
    """模板里不允许出现会导致启动失败的“留空列表”写法。"""
    text = (PROJECT_ROOT / ".env.example").read_text(encoding="utf-8")
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("#") or "=" not in stripped:
            continue
        key, _, value = stripped.partition("=")
        if key.strip() in {"SUPERUSERS", "COMMAND_START", "ONEBOT_WS_URLS"}:
            assert value.strip(), f".env.example 里 {key} 不能为空（会导致 NoneBot 启动失败）"


# ---------------------------------------------------------------------------
# 3.2 版本号一致性
# ---------------------------------------------------------------------------


def test_version_is_semver(settings) -> None:
    """版本号必须是 x.y.z 形式，并且能在配置摘要里看到。"""
    import re

    import config

    assert re.fullmatch(r"\d+\.\d+\.\d+", config.VERSION), f"版本号格式不对：{config.VERSION}"
    assert settings.version == config.VERSION
    assert f"v{config.VERSION}" in settings.describe()


def test_changelog_documents_current_version(settings) -> None:
    """CHANGELOG.md 里必须有当前版本号的条目（发布时不会漏写）。"""
    changelog = (PROJECT_ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    assert f"## [{settings.version}]" in changelog, (
        f"CHANGELOG.md 中没有 {settings.version} 的条目"
    )


def test_release_notes_file_exists(settings) -> None:
    """每个版本都要有对应的 Release 说明文件（可用于粘贴到 GitHub）。"""
    notes = PROJECT_ROOT / "docs" / f"release-notes-v{settings.version}.md"
    assert notes.is_file(), f"缺少发布说明：{notes.relative_to(PROJECT_ROOT)}"
    text = notes.read_text(encoding="utf-8")
    assert settings.version in text


# ---------------------------------------------------------------------------
# 3.3 端口探测工具（供一键启动脚本使用）
# ---------------------------------------------------------------------------


def test_wait_port_detects_open_port() -> None:
    """wait_port 必须能识别出「有人在监听」。"""
    import socket

    from tools.wait_port import is_open

    with socket.socket() as server:
        server.bind(("127.0.0.1", 0))  # 让系统分配一个空闲端口
        server.listen(1)
        port = server.getsockname()[1]
        assert is_open(port) is True

        # 端口关掉之后应该探测不到
    assert is_open(port) is False


def test_wait_port_wait_times_out() -> None:
    """--wait 在端口始终不可用时要按时返回 False，不能一直等。"""
    import socket
    import time

    from tools.wait_port import wait_for

    # 先占一个端口再释放，确保这个端口号当前没人用
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        dead_port = probe.getsockname()[1]

    started = time.monotonic()
    assert wait_for(dead_port, 1.0, interval=0.2) is False
    elapsed = time.monotonic() - started
    assert 0.9 <= elapsed <= 4.0, f"等待时长异常：{elapsed:.2f}s"


def test_wait_port_cli_exit_code() -> None:
    """命令行方式调用时，退出码必须能被批处理正确判断。"""
    import socket

    script = PROJECT_ROOT / "tools" / "wait_port.py"
    with socket.socket() as server:
        server.bind(("127.0.0.1", 0))
        server.listen(1)
        port = server.getsockname()[1]

        ok = subprocess.run(
            [sys.executable, str(script), str(port), "--quiet"],
            capture_output=True,
            check=False,
        )
        assert ok.returncode == 0, f"端口在监听时应返回 0，实际 {ok.returncode}"

    bad = subprocess.run(
        [sys.executable, str(script), str(port), "--quiet"],
        capture_output=True,
        check=False,
    )
    assert bad.returncode == 1, f"端口已关闭时应返回 1，实际 {bad.returncode}"


# ---------------------------------------------------------------------------
# 4. 日志脱敏
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "raw",
    [
        # 用带 example 标记的假 Key，避免被密钥扫描工具误判为真实密钥
        "Authorization: Bearer sk-example-abcdef1234567890",
        "api_key=sk-example-abcdef1234567890",
        'access_token: "example-token-1234567890abcdef"',
        "调用失败 sk-example-abcdef1234567890 请检查",
    ],
)
def test_mask_secrets_removes_keys(raw: str) -> None:
    """日志脱敏函数必须把各种写法的密钥都换成掩码。"""
    from src.logging_setup import mask_secrets

    masked = mask_secrets(raw)
    # 关键部分（长串凭据）必须被抹掉
    assert "abcdef1234567890" not in masked
    assert "****" in masked


def test_mask_secrets_keeps_normal_text() -> None:
    from src.logging_setup import mask_secrets

    text = "机器人启动成功，监听 127.0.0.1:8080"
    assert mask_secrets(text) == text


def test_no_secret_in_source_files() -> None:
    """源码里不允许出现形如真实 Key 的硬编码字符串。"""
    from src.logging_setup import _SK_RE  # noqa: PLC2701 - 复用同一套识别规则

    offenders: list[str] = []
    for path in list(PROJECT_ROOT.glob("*.py")) + list((PROJECT_ROOT / "src").glob("*.py")):
        text = path.read_text(encoding="utf-8")
        for match in _SK_RE.finditer(text):
            token = match.group(0)
            # 允许明显是占位符的写法
            if any(marker in token.lower() for marker in ("test", "placeholder", "example", "xxx", "your")):
                continue
            offenders.append(f"{path.name}: {token}")
    assert not offenders, f"源码中疑似硬编码密钥：{offenders}"


# ---------------------------------------------------------------------------
# 5. Git 忽略规则 & 敏感文件扫描
# ---------------------------------------------------------------------------


def _git(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def _has_git_repo() -> bool:
    return _git("rev-parse", "--is-inside-work-tree").stdout.strip() == "true"


@pytest.mark.skipif(not _has_git_repo(), reason="尚未初始化 Git 仓库")
def test_gitignore_covers_sensitive_paths() -> None:
    """.gitignore 必须真正忽略所有敏感/无用文件。

    这里用 ``git check-ignore`` 实测，而不是匹配 .gitignore 的文本——
    否则规则写法一变（例如 ``.venv/`` 改成 ``.venv*/``）测试就会误报，
    而实际忽略效果其实是对的。
    """
    targets = [
        ".env",
        ".env.local",
        ".venv/pyvenv.cfg",
        ".venv-backup/pyvenv.cfg",
        "venv/pyvenv.cfg",
        "__pycache__/foo.cpython-314.pyc",
        "logs/bot_2025-01-01.log",
        "data/history.db",
        ".pytest_cache/CACHEDIR.TAG",
        "napcat/session.token",
    ]
    not_ignored = [
        target for target in targets if _git("check-ignore", "-q", target).returncode != 0
    ]
    assert not not_ignored, f"这些路径没有被 .gitignore 忽略：{not_ignored}"


@pytest.mark.skipif(not _has_git_repo(), reason="尚未初始化 Git 仓库")
def test_git_ignores_env_and_venv() -> None:
    """用 git check-ignore 实际验证 .env 与 .venv 被忽略。"""
    for target in (".env", ".venv/pyvenv.cfg", "logs/bot_2025-01-01.log", "data/history.db"):
        result = _git("check-ignore", "-q", target)
        assert result.returncode == 0, f"{target} 没有被 .gitignore 忽略"


@pytest.mark.skipif(not _has_git_repo(), reason="尚未初始化 Git 仓库")
def test_no_sensitive_file_would_be_committed() -> None:
    """待提交文件里不能出现 .env、数据库、日志等敏感文件。"""
    result = _git("ls-files", "--cached", "--others", "--exclude-standard")
    assert result.returncode == 0, result.stderr
    tracked = [line for line in result.stdout.splitlines() if line.strip()]
    bad = [
        name
        for name in tracked
        if name == ".env"
        or name.endswith((".db", ".log", ".token", ".key", ".pem"))
        or name.startswith((".venv/", "logs/", "data/", "napcat/"))
    ]
    assert not bad, f"这些敏感文件会被提交：{bad}"


@pytest.mark.skipif(not _has_git_repo(), reason="尚未初始化 Git 仓库")
def test_commit_history_has_no_env_file() -> None:
    """已经提交的历史里不能出现 .env。"""
    result = _git("log", "--all", "--pretty=format:", "--name-only")
    assert result.returncode == 0, result.stderr
    committed = {line.strip() for line in result.stdout.splitlines() if line.strip()}
    assert ".env" not in committed, "Git 历史里出现了 .env，必须立即清理！"


@pytest.mark.skipif(not _has_git_repo(), reason="尚未初始化 Git 仓库")
def test_no_secret_pattern_in_git_history() -> None:
    """扫描 Git 历史里的疑似 DeepSeek Key。"""
    result = _git("log", "--all", "-p", "--", ".", ":(exclude)*.lock")
    if result.returncode != 0:
        pytest.skip(f"git log 执行失败：{result.stderr}")

    import re

    pattern = re.compile(r"sk-[A-Za-z0-9]{20,}")
    allowed = ("sk-test-", "sk-local-", "sk-替换", "sk-your", "sk-xxxx")
    hits = [
        line.strip()
        for line in result.stdout.splitlines()
        if pattern.search(line) and not any(marker in line for marker in allowed)
    ]
    assert not hits, f"Git 历史中疑似真实密钥：{hits[:5]}"
