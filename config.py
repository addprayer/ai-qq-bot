"""项目配置。

所有敏感信息（DeepSeek API Key、OneBot Access Token）**只从 ``.env`` 读取**，
绝不写死在源码里。

设计要点：
1. 使用 ``pydantic-settings``，字段带类型校验，配置写错时启动就会给出清晰报错。
2. 密钥字段使用 ``SecretStr``，即使不小心被打日志也只会显示 ``**********``。
3. ``Settings`` 自带了脱敏的 ``__repr__``，打印配置对象不会泄露密钥。
4. 提供 :func:`validate_runtime_config` 用于「启动时检查必要环境变量」。
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Annotated, Literal

from loguru import logger
from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

# ---------------------------------------------------------------------------
# 路径
# ---------------------------------------------------------------------------

#: 项目根目录（本文件位于 QQBot/config.py，所以父目录就是项目根）
BASE_DIR: Path = Path(__file__).resolve().parent

#: .env 文件路径（固定为项目根目录下的 .env，不依赖「在哪个目录启动」）
ENV_FILE: Path = BASE_DIR / ".env"

#: 日志目录
LOG_DIR: Path = BASE_DIR / "logs"

#: SQLite 对话历史的默认位置（HISTORY_DB_PATH 留空时使用）
DEFAULT_HISTORY_DB: Path = BASE_DIR / "data" / "history.db"

#: 默认人设文件。存在即作为系统提示词使用；可用 .env 的 AI_SYSTEM_PROMPT_FILE 覆盖。
DEFAULT_PERSONA_FILE: Path = BASE_DIR / "personas" / "makima.txt"

#: 内置的极简兜底人设（当既没写内联提示词、人设文件也不存在时使用）
DEFAULT_SYSTEM_PROMPT: str = (
    "你是一个友善、简洁、有分寸的 QQ 聊天伙伴。用中文回答，"
    "像真人在 QQ 上聊天，不要客服腔，不要长篇大论，通常两三句话即可。"
    "不提供违法或伤害他人的具体做法。"
)

#: 项目版本号。发布新版本时同步修改：
#: 1) 这里  2) CHANGELOG.md  3) 打 git tag（如 v1.0.0）
VERSION: str = "1.3.0"


# ---------------------------------------------------------------------------
# 异常
# ---------------------------------------------------------------------------


class ConfigError(RuntimeError):
    """配置文件缺失或填写错误。

    这个异常是**给使用者看的**：消息里会直接说明「去改哪个文件的哪一项」。
    注意：异常消息里绝不能包含密钥明文。
    """


def parse_str_list(value: object) -> list[str]:
    """把 ``.env`` 里的一个值解析成字符串列表。

    同时支持两种新手容易写出的格式：

    * JSON：``["123456", "789012"]``
    * 逗号分隔：``123456,789012``

    解析失败时按逗号分隔处理，尽量不让程序因为一个小格式问题起不来。
    """
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        return [str(item).strip().strip("'\"") for item in value if str(item).strip()]
    text = str(value).strip()
    if not text:
        return []
    if text.startswith("["):
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            parsed = None
        if isinstance(parsed, list):
            return [str(item).strip().strip("'\"") for item in parsed if str(item).strip()]
        # JSON 写坏了，退化成逗号分隔
        text = text.strip("[]")
    return [part.strip().strip("'\"") for part in text.replace(";", ",").split(",") if part.strip()]


# ---------------------------------------------------------------------------
# 配置模型
# ---------------------------------------------------------------------------


class Settings(BaseSettings):
    """整个项目的配置。

    字段名小写，对应 ``.env`` 里的同名大写变量（大小写不敏感）。
    例如 ``ai_api_key`` 对应 ``.env`` 中的 ``AI_API_KEY``。
    """

    model_config = SettingsConfigDict(
        env_file=ENV_FILE,
        env_file_encoding="utf-8",
        extra="ignore",  # .env 里多写的键不会导致启动失败
        case_sensitive=False,
    )

    # ---------------- 机器人基本设置 ----------------
    #: 项目版本号（可用 .env 里的 VERSION 覆盖，一般不用改）
    version: str = Field(default=VERSION, description="项目版本号")
    bot_name: str = Field(default="AI助手", description="机器人名字，用于日志与提示语")
    superusers: Annotated[set[str], NoDecode] = Field(
        default_factory=set, description="超级管理员 QQ 号"
    )

    # ---------------- OneBot V11 / NapCat 连接设置 ----------------
    onebot_access_token: SecretStr = Field(
        default=SecretStr(""),
        description="与 NapCat 里配置的 Token 必须完全一致，留空表示不校验",
    )
    onebot_ws_urls: Annotated[list[str], NoDecode] = Field(
        default_factory=list,
        description="正向 WebSocket 地址列表（本项目默认用反向 WS，一般留空）",
    )

    # ---------------- 机器人监听地址 ----------------
    # 默认只监听 127.0.0.1，避免把端口暴露到公网
    host: str = Field(default="127.0.0.1", description="监听地址，公网部署才需要改")
    port: int = Field(default=8080, ge=1, le=65535, description="监听端口")

    # ---------------- DeepSeek AI 设置 ----------------
    ai_api_key: SecretStr = Field(default=SecretStr(""), description="DeepSeek API Key")
    ai_base_url: str = Field(default="https://api.deepseek.com", description="API 地址")
    ai_model: str = Field(default="deepseek-chat", description="模型名")

    #: 单次请求超时（秒）
    ai_timeout: float = Field(default=60.0, gt=0, le=600)
    #: 失败重试次数（SDK 内部重试，只针对可重试错误）
    ai_max_retries: int = Field(default=2, ge=0, le=5)
    #: 生成温度，0 最稳定、2 最发散
    ai_temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    #: 单次回答最多生成多少 token（控制费用）
    ai_max_tokens: int = Field(default=800, ge=1, le=8192)
    #: 系统提示词（内联写法）。优先级最高，非空时覆盖人设文件
    ai_system_prompt: str = Field(
        default="",
    )
    #: 人设文件路径。内联提示词为空时读取该文件；留空表示不用文件
    ai_system_prompt_file: Path | None = Field(default=DEFAULT_PERSONA_FILE)

    # ---------------- 对话上下文控制 ----------------
    #: 保留最近多少「轮」对话（1 轮 = 1 次用户提问 + 1 次 AI 回答）
    history_max_turns: int = Field(default=5, ge=0, le=50)
    #: 历史存储方式：memory = 内存（重启清空）；sqlite = 写入文件（重启保留）
    history_backend: Literal["memory", "sqlite"] = Field(default="memory")
    #: sqlite 模式下的数据库文件路径；留空则使用默认的 data/history.db
    history_db_path: Path | None = Field(default=None)
    #: 单个用户的问题最大长度（字符），超出会被截断
    max_question_length: int = Field(default=1000, ge=1, le=8000)
    #: 回复最大长度（字符），超出会被截断后附加省略提示
    max_reply_length: int = Field(default=1000, ge=1, le=8000)

    # ---------------- 频率限制 ----------------
    #: 同一用户在同一群内的请求冷却时间（秒），0 表示不限制
    cooldown_seconds: float = Field(default=5.0, ge=0.0, le=3600.0)
    #: 单用户历史缓存上限（防止内存无限增长）
    max_tracked_users: int = Field(default=500, ge=1, le=100000)

    # ---------------- 日志 ----------------
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = Field(default="INFO")
    #: 是否把日志同时写入 logs/ 目录
    log_to_file: bool = Field(default=True)
    #: 是否异步写日志（需要进程间管道；受限环境会报 WinError 5，默认关闭）
    log_async: bool = Field(default=False)

    # ---------------- NoneBot 框架设置 ----------------
    #: 命令前缀（NoneBot 的 COMMAND_START），默认 /
    command_start: Annotated[set[str], NoDecode] = Field(default_factory=lambda: {"/"})

    # ------------------------------------------------------------------
    # 校验
    # ------------------------------------------------------------------

    @field_validator("ai_system_prompt_file", mode="before")
    @classmethod
    def _persona_file_path(cls, value: object) -> object:
        """人设文件路径处理：留空表示不用文件；相对路径按项目根目录解析。"""
        if value is None or (isinstance(value, str) and not value.strip()):
            return None
        path = Path(str(value)).expanduser()
        return path if path.is_absolute() else (BASE_DIR / path)

    @field_validator("history_db_path", mode="before")
    @classmethod
    def _empty_path_to_none(cls, value: object) -> object:
        """允许在 .env 里把路径留空（写成 ``HISTORY_DB_PATH=``）。"""
        if value is None or (isinstance(value, str) and not value.strip()):
            return None
        return value

    @field_validator("command_start", mode="before")
    @classmethod
    def _parse_command_start(cls, value: object) -> object:
        """支持 ``COMMAND_START=["/"]``、``COMMAND_START=/``、``COMMAND_START=/,!``。"""
        parsed = parse_str_list(value)
        return set(parsed) if parsed else {"/"}

    @field_validator("ai_api_key")
    @classmethod
    def _check_api_key_format(cls, value: SecretStr) -> SecretStr:
        """做「格式」检查，不做「真实性」检查（真实性只能在调用 API 时才知道）。"""
        key = value.get_secret_value().strip()
        if not key:
            return value
        # DeepSeek 的 Key 形如 sk-xxxxxxxx，这里只做宽松检查
        if not key.startswith("sk-"):
            raise ValueError(
                "AI_API_KEY 格式看起来不对：DeepSeek 的 Key 通常以 'sk-' 开头。"
                "请检查 .env 中是否粘贴完整、是否多复制了引号或空格。"
            )
        if len(key) < 20:
            raise ValueError("AI_API_KEY 长度过短，可能没有复制完整。")
        return SecretStr(key)

    @field_validator("superusers", mode="before")
    @classmethod
    def _parse_superusers(cls, value: object) -> object:
        """支持 ``SUPERUSERS=123456,234567``，也兼容 ``SUPERUSERS=["123456"]``。"""
        return set(parse_str_list(value))

    @field_validator("onebot_ws_urls", mode="before")
    @classmethod
    def _parse_ws_urls(cls, value: object) -> object:
        """支持 ``ONEBOT_WS_URLS=ws://127.0.0.1:3001``，多个用逗号分隔。"""
        return parse_str_list(value)

    # ------------------------------------------------------------------
    # 便捷属性
    # ------------------------------------------------------------------

    @property
    def is_ai_configured(self) -> bool:
        """是否已经填写 API Key。"""
        return bool(self.ai_api_key.get_secret_value().strip())

    @property
    def access_token(self) -> str:
        """取 OneBot Access Token 明文（仅用于传给适配器，不要写日志）。"""
        return self.onebot_access_token.get_secret_value().strip()

    def masked_api_key(self) -> str:
        """返回脱敏后的 Key，可以安全地打进日志。

        只保留开头几位和结尾几位，中间用 ``****`` 代替。
        （这里刻意不写出完整的示例值，避免密钥扫描工具误报。）
        """
        key = self.ai_api_key.get_secret_value()
        if not key:
            return "(未配置)"
        if len(key) <= 12:
            return key[:3] + "****"
        return f"{key[:7]}****{key[-4:]}"

    def resolve_system_prompt(self) -> str:
        """返回**实际生效**的系统提示词。

        优先级（从高到低）：

        1. ``.env`` 里的 ``AI_SYSTEM_PROMPT``（内联写法，非空时生效）
        2. ``AI_SYSTEM_PROMPT_FILE`` 指向的人设文件（默认 ``personas/makima.txt``）
        3. 代码内置的 :data:`DEFAULT_SYSTEM_PROMPT`

        做到三级兜底的好处：人设文件写坏了、被删了，机器人照样能起来，
        不会因为一句提示词把整个服务卡住。
        """
        inline = (self.ai_system_prompt or "").strip()
        if inline:
            return inline

        path = self.ai_system_prompt_file
        if path is not None:
            try:
                if path.is_file():
                    content = path.read_text(encoding="utf-8").strip()
                    if content:
                        return content
                    logger.warning("人设文件是空的，改用内置兜底人设：{}", path)
                else:
                    logger.warning("人设文件不存在，改用内置兜底人设：{}", path)
            except OSError as exc:  # 权限、编码等问题都不该让机器人起不来
                logger.warning("读取人设文件失败（{}），改用内置兜底人设", exc)

        return DEFAULT_SYSTEM_PROMPT

    def describe(self) -> str:
        """生成一份**可以安全打印**的配置摘要。"""
        return (
            f"AI QQ Bot v{self.version}\n"
            "当前配置：\n"
            f"  - 机器人名称   : {self.bot_name}\n"
            f"  - 监听地址     : http://{self.host}:{self.port}\n"
            f"  - 反向WS路径   : /onebot/v11/ws\n"
            f"  - Access Token : {'已设置' if self.access_token else '未设置'}\n"
            f"  - AI 模型      : {self.ai_model}\n"
            f"  - AI 地址      : {self.ai_base_url}\n"
            f"  - API Key      : {self.masked_api_key()}\n"
            f"  - 上下文轮数   : {self.history_max_turns}（{self.history_backend}）\n"
            f"  - 冷却时间     : {self.cooldown_seconds} 秒"
        )


# ---------------------------------------------------------------------------
# 单例访问
# ---------------------------------------------------------------------------

_settings: Settings | None = None


def get_settings(*, reload: bool = False) -> Settings:
    """获取全局配置对象（进程内只解析一次）。"""
    global _settings
    if _settings is None or reload:
        _settings = Settings()  # type: ignore[call-arg]
    return _settings


def reload_settings() -> Settings:
    """重新读取 ``.env``（改完配置想在不重启的前提下生效时用，测试里也用它）。"""
    return get_settings(reload=True)


# ---------------------------------------------------------------------------
# 与 NoneBot 框架配置对接
# ---------------------------------------------------------------------------

#: 这些字段同时被 NoneBot 自己解析（``nonebot.init`` 内部的 EnvSettingsSource），
#: 而它只会用 ``json.loads`` 解析，**不接受空字符串、也不接受逗号分隔**。
#: 只要环境里存在 ``SUPERUSERS=``（空值），启动就会直接报
#: ``SettingsError: error parsing env var "superusers"``。
_FRAMEWORK_LIST_FIELDS = ("superusers", "command_start")


def sync_framework_env(settings: Settings | None = None) -> dict[str, str]:
    """把本项目解析过的列表型配置，以合法 JSON 回写到环境变量。

    调用时机必须早于 :func:`nonebot.init`。这样无论用户把 ``.env`` 写成
    ``SUPERUSERS=``、``SUPERUSERS=123,456`` 还是 ``SUPERUSERS=["123"]``，
    NoneBot 都能拿到一份合法 JSON，不会再启动失败。

    :return: 实际写入的环境变量（便于测试与排查）
    """
    settings = settings or get_settings()
    written: dict[str, str] = {}
    for field in _FRAMEWORK_LIST_FIELDS:
        value = getattr(settings, field, None)
        if value is None:
            continue
        # set 排序后输出，保证结果稳定可测
        items = sorted(str(item) for item in value)
        text = json.dumps(items, ensure_ascii=False)
        os.environ[field.upper()] = text
        written[field.upper()] = text
    return written


# ---------------------------------------------------------------------------
# 启动自检
# ---------------------------------------------------------------------------


def validate_runtime_config(settings: Settings | None = None) -> list[str]:
    """启动时检查关键配置，返回**警告列表**（不抛异常）。

    只对「一定无法工作」的情况抛 :class:`ConfigError`；
    对「可以启动但功能受限」的情况返回警告文案。

    :raises ConfigError: 缺少 .env 或配置明显无法工作。
    """
    settings = settings or get_settings()

    if not ENV_FILE.exists():
        raise ConfigError(
            f"没有找到配置文件：{ENV_FILE}\n"
            "请把项目里的 .env.example 复制一份并改名为 .env，然后填入你的配置。\n"
            "Windows 命令行操作： copy .env.example .env"
        )

    warnings: list[str] = []
    if not settings.is_ai_configured:
        warnings.append(
            "AI_API_KEY 未配置：机器人仍可启动，但 @机器人 与 /ai 指令会返回「尚未配置」提示，"
            "不会真正调用 DeepSeek。请在 .env 中填写 AI_API_KEY。"
        )
    if not settings.access_token:
        warnings.append(
            "ONEBOT_ACCESS_TOKEN 为空：任何能访问本机 8080 端口的程序都能连上你的机器人。"
            "强烈建议在 NapCat 与本文件中设置同一个 Token。"
        )
    if settings.host not in {"127.0.0.1", "localhost", "::1"}:
        warnings.append(
            f"监听地址为 {settings.host}（非本机回环地址）：管理端口可能暴露到公网，"
            "除非你明确知道自己在做什么，否则请改回 127.0.0.1。"
        )
    return warnings


__all__ = [
    "BASE_DIR",
    "DEFAULT_HISTORY_DB",
    "DEFAULT_PERSONA_FILE",
    "DEFAULT_SYSTEM_PROMPT",
    "ENV_FILE",
    "LOG_DIR",
    "VERSION",
    "ConfigError",
    "Settings",
    "get_settings",
    "parse_str_list",
    "reload_settings",
    "sync_framework_env",
    "validate_runtime_config",
]
