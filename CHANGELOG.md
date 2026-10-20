# 更新日志

本项目遵循 [语义化版本](https://semver.org/lang/zh-CN/) 与
[Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/) 格式。

发布新版本时的检查清单：

1. 修改 `config.py` 里的 `VERSION`
2. 在本文件顶部新增一节
3. 更新 `docs/release-notes-vX.Y.Z.md`（用于粘贴到 GitHub Release）
4. 打 tag 并推送：`git tag -a vX.Y.Z -m "..." && git push origin vX.Y.Z`
5. 在 GitHub 上基于该 tag 创建 Release

---

## [1.1.0] - 2026-10-15

把机器人的人设换成《电锯人》的玛奇玛。

### 变更

- **默认人设改为玛奇玛（Makima）**：公安对魔特异四课负责人、支配恶魔。
  - 语调轻软平缓、礼貌克制，句末常用「呢」「吧」「哦」
  - 会用敬语拉开距离（「请问」「能拜托你吗」）
  - 夸人时说「好孩子」或「よしよし」
  - 从不失态、不说脏话，反对时说「不是这样哦」
  - 回答控制 200 字以内，平静中带一点压迫感
  - 涉及人性、孤独、欲望的问题会答得意味深长
  - 保留安全边界：不提供违法或伤害他人的具体做法，会用温和方式婉拒
- `BOT_NAME` 默认值改为 `玛奇玛`
- 人设提示词提取为 `config.py` 里的 `DEFAULT_SYSTEM_PROMPT` 常量，
  让 `config.py`、`.env.example`、`.env` 三处保持一致

### 新增

- 新增 3 项人设相关测试：
  - 默认提示词包含角色关键特征（玛奇玛、《电锯人》、说话风格、安全边界）
  - `BOT_NAME` 与默认人设匹配
  - `.env.example` 里也带上了同样的默认人设

### 升级提醒

- 换人设后建议把 `HISTORY_MAX_TURNS` 暂时设为 `0` 清空旧记忆，
  否则新角色可能被旧对话带跑偏；确认正常后再改回 `5`

---

## [1.0.1] - 2026-10-15

修复 v1.0.0 中一键启动脚本无法工作的严重问题。

### 修复

- **修复 `start_all.bat` 启动 NapCat 失败**：
  原先使用 `start "NapCat" cmd /c "cd /d ^"<路径>^" && napcat.bat"`，
  其中的引号转义在带空格的路径下会被 cmd 解析错乱，报错
  `'napcat.bat"' is not recognized as an internal or external command`。
  现改用 `start "NapCat" /d "<路径>" cmd /c "napcat.bat"`，
  **完全不做引号转义**，从根本上避免这类问题。

- **修复 NapCat 已运行时的误启动**：
  端口检测原先使用 PowerShell 的 `Test-NetConnection`，在部分环境下会误判为空闲
  （`TcpTestSucceeded: False`），导致重复拉起 NapCat。
  现改用新增的 `tools/wait_port.py`（直接 socket 连接），检测更可靠。

- **修复等待循环在输入重定向环境下报错**：
  原先用 `timeout /t 2`，在输入被重定向时会报
  `ERROR: Input redirection is not supported`。现改用
  `powershell -Command "Start-Sleep"`。

- 修正 `start_all.bat` 缺少 `EnableDelayedExpansion` 导致
  for 循环内读不到变量的问题。

### 新增

- `tools/wait_port.py`：端口探测小工具，可单独使用
  （`python tools/wait_port.py 6099` 或 `--wait 90`），
  这样批处理里不必再内联易错的 Python/PowerShell 一行命令。

### 测试

- 用桩进程对 `start_all.bat` 做了双分支验证：
  - 端口已占用 → 正确跳过启动，不重复拉起
  - 端口空闲 → 桩在**含空格的目录**中确实被执行，且无引号转义报错

---

## [1.0.0] - 2026-10-15

第一个正式版本。经过真实 QQ 账号 + NapCat + DeepSeek 端到端验证。

### 新增

- **一键启动脚本**（本次版本的主要更新）
  - `start_all.bat`：自动以管理员权限启动 NapCat，等待端口就绪后启动机器人
  - `start_bot.bat`：只启动机器人，支持 `--check` 健康自检模式
  - 启动前会依次检查：虚拟环境、`.env`、`AI_API_KEY` 是否真的填了、NapCat 是否在跑
  - 检测到 NapCat 已在运行时会跳过启动，避免重复拉起
- 四种触发方式：`@机器人 提问`、`/ai 问题`（兼容 `/ai问题` 无空格写法）、`/帮助`、`/清空`
- **私聊支持**：私聊里无需 @，直接发消息即可提问
- 对话上下文按「群 + 用户」完全隔离（私聊单独作为一个会话空间）
- 上下文轮数上限（默认 5 轮），可用于控制 API 费用
- 用户请求冷却（默认 5 秒，可配置为 0 关闭）
- 问题超长拒绝、回复超长自动截断
- DeepSeek 错误分类与中文提示：鉴权失败、余额不足、模型不存在、限流、超时、网络故障、服务端故障
- 对话历史两套后端：内存（默认）/ SQLite 持久化，改一行配置即可切换
- 日志密钥自动脱敏（`sk-xxx`、`Authorization: Bearer xxx`、`api_key=xxx`）
- 开发辅助脚本：`tools/probe_onebot_ws.py`（无 NapCat 也能验证反向 WS）、
  `tools/probe_ai_question.py`（模拟群友提问）

### 安全

- API Key 与 OneBot Token 只存放于 `.env`（用 `SecretStr` 承载，打印配置时自动打码）
- `.gitignore` 排除 `.env`、各类虚拟环境、日志、数据库、NapCat 登录凭据
- 自动化测试会扫描源码与 Git 历史中的疑似密钥
- 默认只监听 `127.0.0.1`，启动时若检测到监听地址被改到公网会给出警告

### 修复

- 修复 `.env` 中 `SUPERUSERS=`（留空）或逗号分隔写法导致机器人无法启动的问题。
  NoneBot 自身的配置解析只接受合法 JSON，现在会先把值规范化再交给它，
  同时 `.env.example` 改为 `SUPERUSERS=[]`
- 修复私聊场景下 `block=True` 的独立冷却响应器会阻断后续响应器的问题
  （NoneBot 中该响应器即使不回复也会停止事件传播）
- 修复 `APIStatusError` 子类判断顺序错误，导致 401/404 被误分类为通用错误
- 修复超长问题被静默截断后仍发送给 AI 的问题，现在会直接拒绝
- 修复 `loguru` 异步写日志在受限环境下报 `WinError 5` 的问题（改为默认同步写入）
- 修复探测脚本会把完整 Token 打印到控制台的问题；并改为自动从 `.env` 读取 Token

### 测试

- 71 项自动化测试，覆盖语法、依赖导入、配置校验、指令逻辑、上下文隔离、
  冷却、长度限制、错误翻译、私聊场景、Git 忽略规则与密钥扫描

### 已知限制

- NapCat 属于非官方 QQ 接入方案，存在账号风险，请使用测试小号
- 私聊对任何能给机器人发消息的人都会触发 AI（群聊必须 @ 或 `/ai`）；
  如需限制，可自行添加私聊白名单
- 余额不足（HTTP 402）的真实报错未实测，仅有单元测试覆盖

---

## 版本格式说明

- `1.0.0` → 主版本.次版本.修订号
- 新增功能递增次版本，修 bug 递增修订号，不兼容改动递增主版本
