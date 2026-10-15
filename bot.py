"""AI QQ 群机器人 —— 启动入口。

直接运行本文件即可启动机器人：

    .\\.venv\\Scripts\\python.exe bot.py

启动成功后，NapCat 会用「反向 WebSocket」连到本机：
    ws://127.0.0.1:8080/onebot/v11/ws
"""

from __future__ import annotations

import os
import sys

# ---------------------------------------------------------------------------
# 让 `python bot.py` 在任意目录下都能正确 import 项目内的模块
# ---------------------------------------------------------------------------
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# 必须在 nonebot.init() 之前设置：WebSocket 反向连接需要 websockets 驱动器。
# 注意：这里**不要**给 ONEBOT_ACCESS_TOKEN 设默认值——
# 一旦环境里存在这个变量（哪怕是空串），pydantic-settings 就会优先用它，
# 导致 .env 里填的 Token 被忽略。
os.environ.setdefault("DRIVER", "~fastapi+~websockets")

import nonebot  # noqa: E402
from nonebot.adapters.onebot.v11 import Adapter as OneBotV11Adapter  # noqa: E402
from loguru import logger  # noqa: E402

from config import (  # noqa: E402
    LOG_DIR,
    ConfigError,
    get_settings,
    validate_runtime_config,
)
from src.logging_setup import setup_logging  # noqa: E402

# ---------------------------------------------------------------------------
# 1. 读取并检查配置
# ---------------------------------------------------------------------------
try:
    settings = get_settings()
except Exception as exc:  # pydantic 的校验错误（例如 API Key 格式不对）
    print("=" * 70)
    print("[配置错误] 读取 .env 失败，机器人无法启动：")
    print(f"  {type(exc).__name__}: {exc}")
    print("-" * 70)
    print("请打开项目根目录下的 .env 文件检查对应配置项。")
    print("参考模板：.env.example")
    print("=" * 70)
    raise SystemExit(1) from exc

try:
    config_warnings = validate_runtime_config(settings)
except ConfigError as exc:
    print("=" * 70)
    print("[配置错误] 机器人无法启动：")
    print(exc)
    print("=" * 70)
    raise SystemExit(1) from exc

# ---------------------------------------------------------------------------
# 2. 初始化 NoneBot
# ---------------------------------------------------------------------------
nonebot.init(
    host=settings.host,
    port=settings.port,
    log_level=settings.log_level,
    onebot_access_token=settings.access_token,
)

# 日志（控制台 + 文件），并注册密钥脱敏过滤器
setup_logging(
    level=settings.log_level,
    log_dir=LOG_DIR,
    to_file=settings.log_to_file,
    async_write=settings.log_async,
)

logger.info("正在启动 {} ...", settings.bot_name)
for warning in config_warnings:
    logger.warning("[配置提醒] {}", warning)

# ---------------------------------------------------------------------------
# 3. 注册适配器与插件
# ---------------------------------------------------------------------------
driver = nonebot.get_driver()
driver.register_adapter(OneBotV11Adapter)

nonebot.load_plugin("src.ai_chat")

# ---------------------------------------------------------------------------
# 4. 启动
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    logger.info("配置检查通过，开始监听 {}:{}", settings.host, settings.port)
    logger.info("NapCat 反向 WebSocket 地址： ws://{}:{}/onebot/v11/ws", settings.host, settings.port)
    logger.info("按 Ctrl+C 停止机器人")
    nonebot.run()
