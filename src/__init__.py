"""AI QQ 群机器人的核心代码包。

模块划分：

* ``ai_client``        —— DeepSeek 调用与错误翻译
* ``history``          —— 对话历史（内存 / SQLite）与冷却
* ``message_handler``  —— 纯逻辑函数（文本清洗、长度限制、帮助文案）
* ``ai_chat``          —— NoneBot2 插件，注册 /ai、/帮助、/清空 与 @触发
* ``logging_setup``    —— 日志与密钥脱敏
"""

__all__ = ["ai_chat", "ai_client", "history", "logging_setup", "message_handler"]
