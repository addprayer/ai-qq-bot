"""DeepSeek（OpenAI 兼容协议）调用封装。

本模块只做三件事：
1. 组装 messages（系统提示 + 历史 + 本次提问）；
2. 调用异步 API，带超时与重试；
3. 把各种失败翻译成**给群友看的中文提示**，并把技术细节留给日志。

注意：本模块的任何日志、异常消息都不会包含 API Key 明文。
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Sequence

from loguru import logger
from openai import (
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    AsyncOpenAI,
    AuthenticationError,
    BadRequestError,
    NotFoundError,
    PermissionDeniedError,
    RateLimitError,
)

# ---------------------------------------------------------------------------
# 结果模型
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AIResult:
    """一次 AI 调用的结果。

    :param ok: 是否成功
    :param text: 成功时是回答正文，失败时是给用户看的中文提示
    :param usage: token 用量（可能为空）
    :param error_kind: 失败分类，便于测试与统计
    """

    ok: bool
    text: str
    usage: Mapping[str, int] | None = None
    error_kind: str | None = None


# ---------------------------------------------------------------------------
# 错误翻译
# ---------------------------------------------------------------------------


def classify_error(exc: BaseException) -> tuple[str, str]:
    """把异常翻译成 ``(错误分类, 用户可见中文提示)``。

    分类值仅用于日志与测试，不会展示给群友。

    注意：``AuthenticationError`` / ``RateLimitError`` 等都是
    ``APIStatusError`` 的子类，所以必须先判断子类，再判断状态码。
    """
    # --- 1. 具体异常类型优先 ---

    # 鉴权失败（HTTP 401）
    if isinstance(exc, AuthenticationError):
        return (
            "auth_failed",
            "AI 服务鉴权失败（API Key 无效或已失效），请联系机器人管理员检查配置。",
        )
    # 权限不足（HTTP 403）
    if isinstance(exc, PermissionDeniedError):
        return (
            "permission_denied",
            "该 API Key 没有调用这个模型的权限，请联系机器人管理员检查配置。",
        )
    # 模型不存在（HTTP 404）
    if isinstance(exc, NotFoundError):
        return (
            "model_not_found",
            "配置的模型不存在，请联系机器人管理员检查 AI_MODEL 配置。",
        )
    # 触发限流（HTTP 429）
    if isinstance(exc, RateLimitError):
        return ("rate_limited", "请求太频繁，被 AI 服务限流了，请过一会儿再试。")
    # 请求参数问题（HTTP 400）
    if isinstance(exc, BadRequestError):
        return (
            "bad_request",
            "这次请求被 AI 服务拒绝了（可能是问题太长或包含不支持的内容），换个问法试试。",
        )

    # --- 2. 超时与网络问题 ---
    if isinstance(exc, (APITimeoutError, asyncio.TimeoutError, TimeoutError)):
        return ("timeout", "等待 AI 回复超时了，请稍后再试或把问题问短一点。")
    if isinstance(exc, APIConnectionError):
        return ("network_error", "连接 AI 服务失败，请检查本机网络或代理设置。")

    # --- 3. 其他带状态码的错误 ---
    if isinstance(exc, APIStatusError):
        status = exc.status_code
        if status == 402:
            # 余额 / 配额不足（DeepSeek 用 402 表示）
            return (
                "insufficient_balance",
                "AI 服务余额不足，请联系机器人管理员充值后再试。",
            )
        if status == 429:
            return ("rate_limited", "请求太频繁，被 AI 服务限流了，请过一会儿再试。")
        if status == 401:
            return (
                "auth_failed",
                "AI 服务鉴权失败（API Key 无效或已失效），请联系机器人管理员检查配置。",
            )
        if status == 404:
            return (
                "model_not_found",
                "配置的模型不存在，请联系机器人管理员检查 AI_MODEL 配置。",
            )
        if status >= 500:
            return ("server_error", "AI 服务端暂时故障，请稍后再试。")
        return ("api_error", f"AI 服务返回异常（HTTP {status}），请稍后再试。")

    # --- 4. 兜底 ---
    return ("unknown_error", "AI 服务出现未知错误，我已经记录到日志，请稍后再试。")


def _safe_detail(exc: BaseException) -> str:
    """提取可安全写进日志的错误摘要（不包含请求头、不包含 Key）。"""
    if isinstance(exc, APIStatusError):
        return f"HTTP {exc.status_code} ({type(exc).__name__})"
    return f"{type(exc).__name__}: {exc}"


# ---------------------------------------------------------------------------
# 客户端
# ---------------------------------------------------------------------------


class AIClient:
    """DeepSeek 异步客户端封装。

    参数全部来自 :class:`config.Settings`，这里不重复读环境变量。
    """

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str,
        model: str,
        system_prompt: str,
        timeout: float = 60.0,
        max_retries: int = 2,
        temperature: float = 0.7,
        max_tokens: int = 800,
    ) -> None:
        self.model = model
        self.system_prompt = system_prompt
        self.temperature = temperature
        self.max_tokens = max_tokens
        self._api_key = api_key

        if not api_key:
            # 允许「未配置」状态存在，调用时会由 chat() 给出友好提示，
            # 这样机器人依然能启动、能响应 /帮助。
            self._client: AsyncOpenAI | None = None
            return

        self._client = AsyncOpenAI(
            api_key=api_key,
            base_url=base_url,
            timeout=timeout,
            max_retries=max_retries,
        )

    # -- 构造 ------------------------------------------------------------

    @classmethod
    def from_settings(cls, settings: Any) -> "AIClient":
        """从 :class:`config.Settings` 构建。"""
        # 人设可能是 .env 里的内联字符串，也可能来自 personas/*.txt 文件，
        # 统一交给 Settings.resolve_system_prompt() 决定（内联 > 文件 > 内置默认）
        if hasattr(settings, "resolve_system_prompt"):
            system_prompt = settings.resolve_system_prompt()
        else:  # 兼容只提供 ai_system_prompt 的简单配置对象
            system_prompt = getattr(settings, "ai_system_prompt", "")
        return cls(
            api_key=settings.ai_api_key.get_secret_value().strip(),
            base_url=settings.ai_base_url,
            model=settings.ai_model,
            system_prompt=system_prompt,
            timeout=settings.ai_timeout,
            max_retries=settings.ai_max_retries,
            temperature=settings.ai_temperature,
            max_tokens=settings.ai_max_tokens,
        )

    @property
    def configured(self) -> bool:
        """是否已配置 API Key。"""
        return self._client is not None

    # -- 调用 ------------------------------------------------------------

    async def chat(
        self,
        question: str,
        history: Sequence[Mapping[str, str]] = (),
    ) -> AIResult:
        """带历史上下文地问一个问题。

        :param question: 用户本次提问（已做长度校验）
        :param history: 之前的对话，形如
            ``[{"role": "user", "content": "..."}, {"role": "assistant", "content": "..."}]``
        """
        if self._client is None:
            return AIResult(
                ok=False,
                text="机器人还没有配置 DeepSeek API Key，请联系管理员在 .env 中填写 AI_API_KEY。",
                error_kind="not_configured",
            )

        question = (question or "").strip()
        if not question:
            return AIResult(ok=False, text="你想问什么呢？", error_kind="empty_question")

        messages = self._build_messages(question, history)

        try:
            response = await self._client.chat.completions.create(
                model=self.model,
                messages=messages,  # type: ignore[arg-type]
                temperature=self.temperature,
                max_tokens=self.max_tokens,
                stream=False,
            )
        except Exception as exc:  # noqa: BLE001 - 统一在这里翻译成用户可读提示
            kind, message = classify_error(exc)
            # 只记录分类与安全摘要，绝不记录请求头或 Key
            logger.warning("AI 调用失败 [{}] {}", kind, _safe_detail(exc))
            return AIResult(ok=False, text=message, error_kind=kind)

        text = self._extract_text(response)
        if not text:
            logger.warning("AI 返回内容为空，model={}", self.model)
            return AIResult(ok=False, text="AI 这次没有返回内容，请再试一次。", error_kind="empty_reply")

        usage = self._extract_usage(response)
        logger.info(
            "AI 调用成功 model={} prompt_tokens={} completion_tokens={}",
            self.model,
            (usage or {}).get("prompt_tokens", "?"),
            (usage or {}).get("completion_tokens", "?"),
        )
        return AIResult(ok=True, text=text, usage=usage)

    # -- 内部工具 --------------------------------------------------------

    def _build_messages(
        self,
        question: str,
        history: Iterable[Mapping[str, str]],
    ) -> list[dict[str, str]]:
        messages: list[dict[str, str]] = [{"role": "system", "content": self.system_prompt}]
        for item in history:
            role = item.get("role")
            content = item.get("content")
            if role in {"user", "assistant"} and isinstance(content, str) and content:
                messages.append({"role": role, "content": content})
        messages.append({"role": "user", "content": question})
        return messages

    @staticmethod
    def _extract_text(response: Any) -> str:
        try:
            choices = response.choices
        except AttributeError:  # pragma: no cover - 防御性写法
            return ""
        if not choices:
            return ""
        content = getattr(choices[0].message, "content", None)
        return (content or "").strip()

    @staticmethod
    def _extract_usage(response: Any) -> dict[str, int] | None:
        usage = getattr(response, "usage", None)
        if usage is None:
            return None
        data: dict[str, int] = {}
        for key in ("prompt_tokens", "completion_tokens", "total_tokens"):
            value = getattr(usage, key, None)
            if isinstance(value, int):
                data[key] = value
        return data or None


__all__ = ["AIClient", "AIResult", "classify_error"]
