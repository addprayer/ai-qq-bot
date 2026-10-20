# AI QQ 群机器人

**当前版本：v1.4.0** ｜ [更新日志](CHANGELOG.md) ｜ [发布说明](docs/release-notes-v1.4.0.md)

一个跑在**你自己的 Windows 电脑**上的 AI QQ 群机器人。
用 [NapCat](https://github.com/NapNeko/NapCatQQ) 登录 QQ，通过 **OneBot V11 协议**接入
[NoneBot2](https://nonebot.dev/) 框架，再调用 **DeepSeek API** 生成回复。

> ✅ 已完成**真实 QQ 账号 + NapCat + DeepSeek** 端到端验证：
> 私聊提问由 AI 回答，耗时 0.7~0.8 秒，上下文记忆与群/用户隔离均正常。

> ⚠️ **NapCat 属于非官方接入方案**，通过修改 QQ 客户端实现，存在**账号被限制或封禁的风险**。
> 请务必使用**你有权控制的测试小号**，不要用主力账号。相关风险请自行评估。

---

## 一、它能做什么

| 触发方式 | 效果 |
| --- | --- |
| `@机器人 问题` | 调用 DeepSeek 回答，带最近几轮上下文 |
| `/ai 问题` | 同上（也支持 `/ai问题` 这种没空格的写法） |
| `/帮助` | 返回指令说明 |
| `/清空` | 清除**你在这个群**的对话记忆 |

其它行为约定：

- **只响应明确触发**：群里普通闲聊不会被拿去调用 AI，省钱也不打扰。
- **上下文隔离**：每个群、每个人的对话记忆互不影响。
- **冷却时间**：默认同一用户 5 秒内只能问一次。
- **长度限制**：问题过长会被拒绝，回复过长会被截断。
- **错误兜底**：超时、余额不足、Key 失效、模型不存在、网络故障都会返回中文提示，**不会让机器人崩溃**。
- **密钥安全**：所有密钥只放在 `.env`（已被 `.gitignore` 排除），日志里会自动脱敏。

### 人设：玛奇玛

默认人设是《电锯人》中的 **玛奇玛（Makima）**，但重点不在"扮演动漫角色"，
而在**像一个真人在 QQ 上聊天**：

- 温柔、知性、从容，带一点妩媚感，语气不急不躁
- 情绪稳定、有判断力、有主动性，**不轻易讨好，也不轻易被带偏**
- 回复短（1~4 句为主），偶尔带一点神态描写，比如「（笑）」「（偏头看你）」
- 明确禁止客服腔：「作为 AI」「我理解你的感受」「希望这对你有帮助」这类一律不出现
- 被问「你是不是 AI」会**诚实承认**，然后自然接回话题，不会硬装真人

效果示例（真实调用 DeepSeek 的输出）：

> **群友**：今天上班好累啊，不想干了
>
> **玛奇玛**：（偏头看你）累到说"不想干了"，那多半不是活儿本身压的，是心里憋着点什么吧。是今天特别糟，还是这阵子都这样？

> **群友**：你是不是AI啊
>
> **玛奇玛**：（笑）我是挂在QQ上的玛奇玛聊天机器人，陪你聊聊天可以，但别把我当真人哦。不过刚才那句"不想干了"，我可是认真在听的——是今天出了什么事吗？

### 怎么改人设

人设写在独立文件里，**直接用记事本编辑就行，不用动代码**：

```
personas/makima.txt
```

优先级是 **内联 > 文件 > 代码内置兜底**。也就是说：

| 想做什么 | 怎么做 |
| --- | --- |
| 微调玛奇玛的措辞 | 直接改 `personas/makima.txt` |
| 临时换成别的人设 | 在 `.env` 里把提示词写进 `AI_SYSTEM_PROMPT=`（会覆盖文件） |
| 完全不用文件 | `.env` 里 `AI_SYSTEM_PROMPT_FILE=` 留空 |
| 文件写坏/被删了 | 自动回落到内置兜底人设，**机器人照样能启动**，日志里会有警告 |

> 💡 换人设后建议重启机器人。因为默认 `HISTORY_BACKEND=memory`，
> 重启会自动清空旧对话记忆，新角色不会被上一版人设带跑偏。

---

## 二、目录结构

```
QQBot/
├── bot.py                    # 启动入口：读配置 → 起日志 → 注册适配器 → 加载插件 → 启动
├── config.py                 # 配置定义与校验（从 .env 读取，密钥用 SecretStr）
├── start_all.bat             # ★日常使用：一键启动 NapCat + 机器人
├── start_bot.bat             # 只启动机器人（支持 --check 自检）
├── requirements.txt          # 依赖清单（已锁定版本）
├── pytest.ini                # 测试配置
├── CHANGELOG.md              # 更新日志（每个版本的变化）
├── .env.example              # 配置模板（只有占位符，可安全上传）
├── .env                      # 你的真实配置（★已被 .gitignore 排除，不会上传）
├── .gitignore                # 排除密钥、虚拟环境、日志、数据库等
├── README.md                 # 本文件
├── src/
│   ├── __init__.py
│   ├── ai_chat.py            # NoneBot2 插件：注册 /ai、/帮助、/清空 与 @触发
│   ├── ai_client.py          # DeepSeek 调用封装 + 错误翻译
│   ├── history.py            # 对话历史（内存 / SQLite）与冷却计时
│   ├── message_handler.py    # 纯逻辑：文本清洗、长度限制、帮助文案（可单测）
│   └── logging_setup.py      # 日志配置 + 密钥脱敏
├── tests/
│   ├── __init__.py
│   ├── conftest.py           # 测试环境准备（不读真实 .env）
│   ├── harness.py            # 测试抓手：不需要 QQ 就能驱动真实事件流程
│   ├── test_basic.py         # 语法/导入/配置/Git 忽略规则/密钥扫描
│   └── test_ai_chat.py       # 指令逻辑/历史隔离/冷却/错误处理
├── tools/
│   ├── probe_onebot_ws.py    # 不需要 NapCat 就能验证反向 WebSocket 是否打通
│   └── probe_ai_question.py  # 模拟群友提问，验证完整回复链路
└── docs/
    └── setup_windows.md      # Windows 从零安装、配置、启动、排错（详细版）
```

数据目录（运行时自动创建，不会上传）：

```
logs/bot_YYYY-MM-DD.log       # 运行日志（日志里的密钥已被脱敏）
data/history.db               # 仅当 HISTORY_BACKEND=sqlite 时生成
```

> 关于目录设计的说明：NoneBot2 的社区惯例是把事件响应器放进插件包
> （如 `src/plugins/xxx.py`）。本项目按你的目录要求保留 `src/` 结构，
> 把插件文件放在 `src/ai_chat.py`，通过 `bot.py` 里的
> `nonebot.load_plugin("src.ai_chat")` 加载，效果与插件目录结构完全一致，
> 同时让「纯逻辑」（`message_handler.py` / `history.py` / `ai_client.py`）
> 可以脱离 NoneBot 单独测试。

---

## 三、日常启动（装好之后每次这样用）

首次安装请先看 [四、快速开始](#四快速开始-首次安装)。**装好之后，日常启动只需要双击一个文件。**

| 文件 | 作用 |
| --- | --- |
| **`start_all.bat`** | **推荐**：自动启动 NapCat（会弹 UAC 提权窗口）+ 机器人 |
| `start_bot.bat` | 只启动机器人（NapCat 已经在运行时用）|
| `start_bot.bat --check` | 只做健康检查：虚拟环境、`.env`、API Key、NapCat 是否就绪 |

**操作步骤**：

1. 打开 `QQBot` 文件夹
2. 双击 **`start_all.bat`**
3. 弹出 UAC 提示时点 **「是」**（NapCat 需要管理员权限）
4. 出现一个 `NapCat` 窗口和一个机器人窗口 —— **两个都最小化，不要关**

✅ **成功标志**：机器人窗口里出现
```
[INFO] nonebot.utils | OneBot V11 | Bot <你的QQ号> connected
```

然后就能在 QQ 里 `@机器人 提问` 了。

> ⚠️ **不要把两个窗口点 ×**。想停止机器人，在窗口里按 `Ctrl + C`。
> ⚠️ NapCat 如果提示要扫码登录，用手机 QQ 扫一下即可。
> ⚠️ 如果你把 NapCat 装在别的位置，用记事本打开 `start_all.bat`，
> 修改 `NAPCAT_DIR=` 那一行。

**开机后需要重新双击一次**，这两个程序不会自动开机启动。
（想开机自启，可以把 `start_all.bat` 的快捷方式放进
`文件资源管理器地址栏输入 shell:startup` 打开的文件夹里。）

---

## 四、快速开始（首次安装）

完整细节见 **[docs/setup_windows.md](docs/setup_windows.md)**，这里是精简版。

### 1. 准备环境

需要 **Python 3.10 或更高**（本项目在 **Python 3.14.5** 上实测通过）和 **Git**。

```powershell
cd QQBot
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

### 2. 填写配置

```powershell
copy .env.example .env
notepad .env
```

至少要改两项：

- `AI_API_KEY` —— 到 <https://platform.deepseek.com/api_keys> 创建，形如 `sk-xxxxxx`
- `ONEBOT_ACCESS_TOKEN` —— 自己随便定一个长随机串，**要和 NapCat 里填的一模一样**

### 3. 启动

```powershell
.\.venv\Scripts\python.exe bot.py
```

看到下面这些就说明成功了：

```
[SUCCESS] nonebot | Running NoneBot...
[SUCCESS] nonebot.internal.driver.abstract | Loaded adapters: OneBot V11
[INFO] uvicorn.server | Uvicorn running on http://127.0.0.1:8080
```

### 4. 让它连上 QQ

按 **[docs/setup_windows.md](docs/setup_windows.md)** 里的 NapCat 章节操作。

> 💡 **强烈建议用「一键版」**（`NapCat.Shell.Windows.OneKey.zip`）：
> 它自带一个与 NapCat 版本匹配的 QQ，不会和你现有的 QQ 冲突。
> 手动版（`NapCat.Shell.zip`）要求 QQ 版本与 NapCat 声明的一致，
> 若 QQ 自动更新过就会报 `Cannot find module '...loadNapCat.js'`。

步骤概览：启动 NapCat 并扫码登录 → 打开 WebUI（改掉初始密码）→
新建 **WebSocket 客户端**，URL 填 `ws://127.0.0.1:8080/onebot/v11/ws`，
Token 与 `.env` 一致，消息格式选 `array`，启用并保存。

连接成功后，机器人窗口里会出现 `Bot <你的QQ号> connected`。

### 5. 不需要 QQ 也能先自测

机器人正在运行时，在**另一个** PowerShell 窗口执行：

```powershell
# 只验证反向 WebSocket 通不通（会打印机器人返回的帮助文本）
.\.venv\Scripts\python.exe tools\probe_onebot_ws.py --send-message

# 模拟群友提问（会真的调用 DeepSeek）
.\.venv\Scripts\python.exe tools\probe_ai_question.py "你好"
.\.venv\Scripts\python.exe tools\probe_ai_question.py --no-at "/ai 你好"
```

---

## 五、配置项说明（.env）

| 变量 | 说明 | 默认值 |
| --- | --- | --- |
| `BOT_NAME` | 机器人名字，用于日志和提示 | `玛奇玛` |
| `SUPERUSERS` | 超管 QQ 号，多个用逗号分隔 | 空 |
| `LOG_LEVEL` | 日志级别 `DEBUG/INFO/WARNING/ERROR` | `INFO` |
| `HOST` / `PORT` | 监听地址与端口。**默认只监听 127.0.0.1，别改成 0.0.0.0** | `127.0.0.1` / `8080` |
| `ONEBOT_ACCESS_TOKEN` | 与 NapCat 一致的访问令牌 | 无（空表示不校验） |
| `AI_API_KEY` | DeepSeek API Key | 无 |
| `AI_BASE_URL` | API 地址 | `https://api.deepseek.com` |
| `AI_MODEL` | 模型名，`deepseek-chat` 或 `deepseek-reasoner` | `deepseek-chat` |
| `AI_TIMEOUT` | 单次请求超时（秒） | `60` |
| `AI_MAX_RETRIES` | 失败自动重试次数 | `2` |
| `AI_TEMPERATURE` | 生成温度，0 最稳定 | `0.7` |
| `AI_MAX_TOKENS` | 单次回答最多生成多少 token（**直接决定费用**） | `800` |
| `AI_SYSTEM_PROMPT` | 机器人人设。默认是《电锯人》的**玛奇玛**，改这一行即可换角色 | 见模板 |
| `HISTORY_MAX_TURNS` | 记住最近几轮对话 | `5` |
| `HISTORY_BACKEND` | `memory`（重启清空）或 `sqlite`（重启保留） | `memory` |
| `HISTORY_DB_PATH` | sqlite 数据库位置，留空用 `data/history.db` | 空 |
| `MAX_QUESTION_LENGTH` | 超过这个长度的问题会被**拒绝**（不发给 AI） | `1000` |
| `MAX_REPLY_LENGTH` | 回复超过这个长度会被**截断** | `1000` |
| `COOLDOWN_SECONDS` | 同一用户在同一群的冷却秒数，`0` 表示不限 | `5` |
| `LOG_ASYNC` | 异步写日志开关（受限环境保持 `false`） | `false` |

---

## 六、测试

```powershell
# 全部测试
.\.venv\Scripts\python.exe -m pytest

# 只看结果概览
.\.venv\Scripts\python.exe -m pytest -q

# 单独跑某一类
.\.venv\Scripts\python.exe -m pytest tests/test_ai_chat.py
```

测试覆盖的内容：

- Python 语法编译检查（`compileall` + `py_compile`）
- 依赖与模块导入检查（含 OneBot V11 适配器接口）
- 配置缺失 / Key 格式错误时的中文报错
- `/帮助`、`/清空`、`/ai` 的指令逻辑
- **不同群、不同用户的上下文隔离**
- AI 失败（401/402/404/429/500/超时/网络）的错误分类与提示
- 冷却时间生效与不误伤其他用户
- 超长输入被拒绝、超长回复被截断
- **`.gitignore` 是否真的忽略了 `.env`、`.venv`、日志、数据库**
- **Git 历史里是否混入真实密钥**

---

## 七、上传到 GitHub

> 详细步骤（含 GitHub 网页操作与浏览器授权）见
> [docs/setup_windows.md](docs/setup_windows.md#七上传到-github)。

```powershell
cd QQBot

# 1. 确认没有敏感文件被跟踪（应该没有输出）
git status --ignored --short | Select-String "\.env$"

# 2. 初始化并提交
git init
git add .
git commit -m "Initial commit: AI QQ bot"

# 3. 关联你在 GitHub 上新建的【空】仓库，然后推送
git remote add origin https://github.com/<你的用户名>/<仓库名>.git
git branch -M main
git push -u origin main
```

推送时会弹出浏览器让你登录 GitHub 授权（Git Credential Manager 流程）。
**不要把自己的密码、Personal Access Token 发给任何人。**

---

## 八、当前完成情况

### ✅ 已实现并通过测试

- 全部 12 项核心功能需求与 8 项安全/配置要求
- NoneBot2 + OneBot V11 反向 WebSocket 接入、启动、事件分发
- `@机器人` / `/ai` / `/帮助` / `/清空` 四个入口
- 上下文隔离、轮数上限、冷却、长度限制
- DeepSeek 错误分类与中文提示（6 类）
- 日志密钥脱敏 + `.gitignore` 安全规则
- 内存与 SQLite 两套历史后端
- 68 项自动化测试

### 🧪 已验证方式（重要，请如实阅读）

| 项目 | 验证方式 |
| --- | --- |
| 反向 WebSocket 握手 | ✅ **真实启动机器人 + 真实 WebSocket 客户端**，日志出现 `Bot <QQ号> connected` |
| 消息处理 → 发送回复 | ✅ **真实端到端**：模拟 OneBot 客户端发消息，收到机器人的 `send_group_msg` 调用 |
| DeepSeek 调用与错误处理 | ✅ **真实网络调用**：占位 Key 请求 DeepSeek 收到 HTTP 401，正确分类为 `auth_failed` |
| DeepSeek 正常回答 + 上下文 | ✅ **真实 API**：两轮对话，第二轮能复述第一轮内容 |
| **真实 QQ 收发消息** | ✅ **已用真实 QQ 账号 + NapCat + 真实 DeepSeek 打通**：私聊提问收到回答，日志含 token 用量与耗时（0.71s / 0.83s） |
| 指令逻辑 / 隔离 / 冷却 / 限长 | ✅ 自动化测试（`tests/test_ai_chat.py`，含私聊场景） |
| Git 忽略规则 / 密钥扫描 | ✅ 自动化测试（`tests/test_basic.py`） |

### ⚠️ 尚未验证

| 项目 | 原因 |
| --- | --- |
| 余额不足（HTTP 402）的真实报错 | 需要欠费账号才能复现；代码已按 HTTP 402 处理，并有单元测试覆盖 |
| `deepseek-reasoner` 模型 | 未用真实 Key 调用过，可自行把 `AI_MODEL` 改掉验证 |
| 大规模群聊下的并发表现 | 未做压力测试 |

> 📌 **使用范围提醒**：私聊对**任何能给机器人发消息的人**都会触发 AI（群聊必须 @ 或 `/ai`）。
> 如果担心被陌生人消耗额度，建议给机器人加私聊白名单（见「十、后续可扩展方向」）。

---

## 九、常见报错

| 现象 | 原因与解决 |
| --- | --- |
| `[配置错误] 没有找到配置文件` | 没建 `.env`。执行 `copy .env.example .env` |
| `AI_API_KEY 格式看起来不对` | Key 没复制完整，或首尾多了空格/引号 |
| 机器人启动后日志没有 `Bot xxx connected` | NapCat 没连上：检查地址是否为 `ws://127.0.0.1:8080/onebot/v11/ws`、Token 是否与 `.env` 完全一致 |
| 群里 @机器人 完全没反应 | ①机器人窗口是否有日志；②NapCat 是否显示已连接；③是否 @ 到了正确的账号 |
| 回复「AI 服务鉴权失败」 | `AI_API_KEY` 无效或已过期，去 DeepSeek 控制台重新创建 |
| 回复「AI 服务余额不足」 | DeepSeek 账户没余额了，去充值 |
| 回复「配置的模型不存在」 | `AI_MODEL` 拼错了，只用 `deepseek-chat` 或 `deepseek-reasoner` |
| 回复「等待 AI 回复超时」 | 网络不稳或问题太长。可调大 `AI_TIMEOUT`，或检查代理 |
| 回复「慢一点～」 | 冷却机制生效，等几秒再问，或改小 `COOLDOWN_SECONDS` |
| 端口被占用 `[Errno 10048]` | 8080 被别的程序占了，改 `.env` 里的 `PORT`，NapCat 那边同步改 |
| `PermissionError: [WinError 5]` 写日志失败 | 把 `LOG_ASYNC` 设为 `false`（默认已是 false） |
| `pip install` 卡住或报网络错误 | 换国内镜像：`-i https://pypi.tuna.tsinghua.edu.cn/simple` |

更多排错细节见 [docs/setup_windows.md](docs/setup_windows.md#九常见报错排查)。

---

## 十、安全提醒

1. `.env` 里全是密钥，**永远不要提交到 Git**。`.gitignore` 已排除，但你自己也别手动 `git add -f`。
2. `HOST` 保持 `127.0.0.1`。改成 `0.0.0.0` 等于把机器人管理端口暴露到公网，非常危险。
3. `ONEBOT_ACCESS_TOKEN` 一定要设，否则本机任何程序都能连上你的机器人。
4. 日志会自动把 `sk-xxx`、`Authorization: Bearer xxx`、`api_key=xxx` 替换成掩码，
   但**请不要把 `LOG_LEVEL` 改成 DEBUG 后把完整日志发到公开场合**。
5. NapCat 会持有你的 QQ 登录凭据。它的数据目录（含 `session.token`、`device.json`）
   已被 `.gitignore` 排除，请不要上传。
6. 用测试小号，不用主力号。

---

## 十一、后续可扩展方向

- **私聊白名单**：私聊目前对任何发消息的人都触发 AI，建议限制为指定 QQ 号
- 把 `HISTORY_BACKEND` 改成 `sqlite`，重启后上下文仍在（代码已实现，改配置即可）
- 增加「只允许指定群使用」的群白名单
- 增加每人每日调用次数上限，进一步控制费用
- 接入图片理解 / 语音等其他能力
- 用 `nb-cli` 把 `src/ai_chat.py` 拆成标准插件包，发布到 NoneBot 插件商店
