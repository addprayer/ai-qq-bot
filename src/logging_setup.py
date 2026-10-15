"""日志配置。

两条硬性要求：
1. 控制台能看到运行状态，同时按天写入 ``logs/``。
2. **绝不把 API Key / Token 写进日志**——即使第三方库不小心打印了，
   也会被 :func:`mask_secrets` 在落盘前替换成 ``sk-****``。
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

from loguru import logger

# ---------------------------------------------------------------------------
# 脱敏
# ---------------------------------------------------------------------------

#: 形如 Authorization: Bearer sk-xxxx
_BEARER_RE = re.compile(r"(?i)(bearer\s+)([A-Za-z0-9_\-\.]{8,})")
#: 形如 sk-xxxxxxxxxxxxxxxx
_SK_RE = re.compile(r"\bsk-[A-Za-z0-9_\-]{8,}\b")
#: 形如 api_key=xxx / access_token: xxx / "authorization": "xxx"
_KV_RE = re.compile(
    r"(?i)\b(api[_-]?key|access[_-]?token|token|authorization|secret)\b(\s*[:=]\s*)"
    r"(['\"]?)([^\s'\",}]{6,})\3"
)

#: 项目的仓库地址，允许出现在日志里（避免误伤）
_ALLOWLIST = ("github.com",)


def mask_secrets(text: str) -> str:
    """把文本里的密钥替换成掩码。

    这是一个纯函数，方便单元测试。
    """
    if not text:
        return text
    masked = _BEARER_RE.sub(lambda m: f"{m.group(1)}****", text)
    masked = _SK_RE.sub("sk-****", masked)
    masked = _KV_RE.sub(lambda m: f"{m.group(1)}{m.group(2)}{m.group(3)}****{m.group(3)}", masked)
    return masked


def _patcher(record: dict) -> None:
    """loguru 的 patcher：在格式化之前对整条消息脱敏。"""
    record["message"] = mask_secrets(record["message"])


# ---------------------------------------------------------------------------
# 初始化
# ---------------------------------------------------------------------------

_CONSOLE_FORMAT = (
    "<green>{time:HH:mm:ss}</green> | <level>{level: <7}</level> | "
    "<cyan>{name}</cyan> - <level>{message}</level>"
)
_FILE_FORMAT = "{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <7} | {name}:{function}:{line} - {message}"


def setup_logging(
    *,
    level: str = "INFO",
    log_dir: Path,
    to_file: bool = True,
    async_write: bool = False,
) -> None:
    """配置全局日志。

    :param level: 日志级别，建议 INFO；排查问题时用 DEBUG。
    :param log_dir: 日志目录，不存在会自动创建。
    :param to_file: 是否写入文件。
    :param async_write: 是否异步写日志。默认 ``False``——
        异步模式（``enqueue=True``）需要创建进程间管道，
        在受限环境（如某些沙箱、部分精简版 Windows）会报
        ``PermissionError: [WinError 5]``。群机器人日志量很小，
        同步写入完全够用，需要时可打开。
    """
    logger.remove()  # 去掉 loguru 默认的输出，改为自定义格式

    logger.configure(patcher=_patcher)

    logger.add(
        sys.stderr,
        level=level,
        format=_CONSOLE_FORMAT,
        colorize=True,
        backtrace=False,
        diagnose=False,  # 关闭变量值回显，避免意外打印密钥
        enqueue=False,
    )

    if to_file:
        log_dir.mkdir(parents=True, exist_ok=True)
        log_file = log_dir / "bot_{time:YYYY-MM-DD}.log"
        logger.add(
            str(log_file),
            level=level,
            format=_FILE_FORMAT,
            rotation="00:00",  # 每天零点切分
            retention="14 days",  # 只保留 14 天
            encoding="utf-8",
            enqueue=async_write,
            backtrace=False,
            diagnose=False,
        )


__all__ = ["mask_secrets", "setup_logging"]
