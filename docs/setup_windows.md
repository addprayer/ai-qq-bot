# Windows 从零开始安装与配置（保姆级）

本文假设你**什么都没装**，一步步来。每一步都告诉你：

- 在哪里点 / 输入什么
- **怎样判断成功了**

> 全程大约 40～60 分钟。遇到卡住的地方，先看文末
> [九、常见报错排查](#九常见报错排查)。

---

## 目录

1. [安装 Python](#一安装-python)
2. [安装 Git](#二安装-git)
3. [准备项目并安装依赖](#三准备项目并安装依赖)
4. [填写 .env 配置](#四填写-env-配置)
5. [获取 DeepSeek API Key](#五获取-deepseek-api-key)
6. [安装并配置 NapCat](#六安装并配置-napcat)
7. [启动机器人并验证](#七启动机器人并验证)
8. [上传到 GitHub](#八上传到-github)
9. [常见报错排查](#九常见报错排查)
10. [安全与风险](#十安全与风险)

---

## 一、安装 Python

### 1.1 先检查有没有装

按 `Win + R`，输入 `powershell`，回车，打开 PowerShell 窗口。

输入下面这行，回车：

```powershell
python --version
```

- **如果显示 `Python 3.10.x` ~ `Python 3.14.x`** → 已经装好了，跳到
  [1.3 检查 pip](#13-检查-pip)。
- **如果弹出「应用商店」或者提示 `Python was not found`** → 这是 Windows 自带的
  **假入口**，说明你还没装 Python，请继续 1.2。

> ⚠️ 常见误区：Windows 的「应用执行别名」会让 `python` 命令指向 Microsoft Store，
> 看起来像装了其实没有。**只看 `python --version` 有没有打出真实版本号。**

### 1.2 安装 Python

1. 浏览器打开 <https://www.python.org/downloads/windows/>
2. 下载 **Python 3.12** 的 **Windows installer (64-bit)**（3.10～3.14 都可以，本文以 3.12 为例）
3. 双击安装包，**第一步一定要勾选底部的 `Add python.exe to PATH`**，然后点
   `Install Now`
4. 安装完成后，**关闭旧的 PowerShell 窗口，重新打开一个**
5. 再执行一次：

```powershell
python --version
```

✅ **成功标志**：输出类似 `Python 3.12.10`（真实版本号，不是打开应用商店）。

### 1.3 检查 pip

```powershell
python -m pip --version
```

✅ **成功标志**：输出类似 `pip 24.x from C:\...\site-packages\pip (python 3.12)`。

如果报 `No module named pip`，执行：

```powershell
python -m ensurepip --upgrade
python -m pip install --upgrade pip
```

---

## 二、安装 Git

### 2.1 检查

```powershell
git --version
```

- 显示 `git version 2.x.x` → 已安装，跳到 [2.3 配置身份](#23-配置身份)。
- 提示 `无法将"git"项识别为...` → 继续 2.2。

### 2.2 安装

1. 打开 <https://git-scm.com/download/win>，下载 64-bit 安装包
2. 双击运行，**一路点 `Next`** 即可（默认选项都合适）
3. 安装完，**重新打开 PowerShell**，再执行：

```powershell
git --version
```

✅ **成功标志**：输出 `git version 2.4x.x.windows.1`。

### 2.3 配置身份

Git 需要知道你叫什么（这两个值会写进提交记录，不需要和 GitHub 账号一致，但建议一致）：

```powershell
git config --global user.name "你的名字"
git config --global user.email "你的邮箱@example.com"
```

✅ **验证**：

```powershell
git config --global user.name
git config --global user.email
```

能打印出你刚填的内容即可。

### 2.4 确认凭据管理器可用（推送 GitHub 时要用）

```powershell
git config --global credential.helper
```

- 如果输出 `manager` 或 `manager-core` → 没问题。
- **如果什么都没输出**（常见于只装了精简版 Git），执行下面这行补上：

```powershell
git config --global credential.helper manager
```

> 它的作用是：推送时自动弹出浏览器让你登录 GitHub 授权，
> 你**不需要**把密码或 Token 告诉任何人。

---

## 三、准备项目并安装依赖

### 3.1 进入项目目录

假设项目在 `C:\Users\你的用户名\Documents\QQBot`（按你自己的实际路径替换）：

```powershell
cd C:\Users\你的用户名\Documents\QQBot
dir
```

✅ **成功标志**：能看到 `bot.py`、`config.py`、`requirements.txt`、`src`、`tests` 等。

### 3.2 创建虚拟环境

虚拟环境相当于给这个项目单独准备一个「干净的 Python」，不影响系统里的其它项目。

```powershell
python -m venv .venv
```

✅ **成功标志**：当前目录多出 `.venv` 文件夹，里面有 `Scripts\python.exe`。
验证一下：

```powershell
.\.venv\Scripts\python.exe --version
```

### 3.3 安装依赖

```powershell
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

安装过程会下载 30 多个包，1～3 分钟。最后一行应该出现：

```
Successfully installed nonebot2-2.5.0 nonebot-adapter-onebot-2.4.6 openai-3.31.0 ...
```

✅ **成功标志**：看到 `Successfully installed`。

> 🌐 **下载很慢或失败**？换国内镜像重试：
>
> ```powershell
> .\.venv\Scripts\python.exe -m pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
> ```

### 3.4 验证依赖装好了

```powershell
.\.venv\Scripts\python.exe -c "import nonebot, openai; print('依赖 OK', nonebot.__version__, openai.__version__)"
```

✅ **成功标志**：输出 `依赖 OK 2.5.0 3.x.x`。

---

## 四、填写 .env 配置

### 4.1 复制模板

```powershell
copy .env.example .env
```

> ⚠️ `.env` 里全是密钥。`.gitignore` 已经把它排除在 Git 之外，
> **请不要手动 `git add -f .env`**。

### 4.2 生成一个随机的访问令牌

在 PowerShell 里执行下面这行，它会打印一串随机字符：

```powershell
-join ((1..40) | ForEach-Object { '{0:x}' -f (Get-Random -Max 16) })
```

**把这串字符复制下来**，下一步要用两次（一次填 `.env`，一次填 NapCat）。

### 4.3 编辑 .env

```powershell
notepad .env
```

至少改这两项：

```ini
# 换成你刚生成的那串随机字符（两边必须完全一致）
ONEBOT_ACCESS_TOKEN=把刚才那串随机字符粘到这里

# 换成你自己的 DeepSeek Key（见第五节）
AI_API_KEY=sk-你的真实Key
```

保存（`Ctrl + S`）并关闭记事本。

### 4.4 验证配置能正确读取

```powershell
.\.venv\Scripts\python.exe -c "from config import get_settings; print(get_settings().describe())"
```

✅ **成功标志**：打印出一份配置摘要，其中
`API Key : sk-xxxx****xxxx` 是**打了码的**（说明脱敏生效，不会泄露完整 Key）。

如果报 `[配置错误] 没有找到配置文件`，说明 `.env` 没建成功，回到 4.1。
如果报 `AI_API_KEY 格式看起来不对`，检查 Key 是否复制完整、有没有多出引号或空格。

---

## 五、获取 DeepSeek API Key

1. 浏览器打开 <https://platform.deepseek.com/>
2. 注册 / 登录（支持手机号或邮箱）
3. **先充值**（DeepSeek 是按量付费，几块钱就能用很久）
   - 左侧菜单 `充值` / `Top up`
4. 左侧菜单点 **`API keys`**
5. 点 **`创建 API key`**（Create new API key）
6. 名字随便填（例如 `qqbot`），点确定
7. **立刻复制弹出的那串 `sk-` 开头的字符串** —— 它只显示一次！
8. 粘贴到 `.env` 的 `AI_API_KEY=` 后面

✅ **成功标志**：`.env` 里 `AI_API_KEY=sk-` 后面跟着一长串字符（通常 30 位以上）。

> 💡 成本参考：`deepseek-chat` 价格很低，`.env` 里默认
> `AI_MAX_TOKENS=800` 且只记住 5 轮对话，正常群聊一天花不了几毛钱。
> 想更省，把 `HISTORY_MAX_TURNS` 调小到 `3`、`AI_MAX_TOKENS` 调到 `400`。

---

## 六、安装并配置 NapCat

> ⚠️ **风险提示（请先读）**
> NapCat 通过修改 QQ 客户端来实现，属于**非官方接入方案**。
> 使用它可能违反 QQ 用户协议，**存在账号被限制登录或封禁的风险**。
> **请务必使用你有权控制的测试小号，不要用主力账号。**
> 本文只做技术说明，风险请自行评估，后果自负。

### 6.1 下载 NapCat

1. 打开官方仓库 <https://github.com/NapNeko/NapCatQQ/releases>
2. 找到最新版本，下载 **`NapCat.Shell.zip`**（免安装版，最简单）
3. 解压到一个**路径不含中文和空格**的目录，例如 `D:\NapCat`
4. 进入该目录，双击 `launcher.bat`（或 `NapCatWinBootMain.exe`）

### 6.2 登录 QQ

1. 程序会弹出一个二维码窗口（或控制台里显示二维码链接）
2. 用**测试小号**的手机 QQ **扫码登录**
3. 按提示完成验证

✅ **成功标志**：控制台出现类似 `账号 <QQ号> 登录成功` 的提示，
并且窗口里出现 NapCat 的 WebUI 地址（形如 `http://127.0.0.1:6099/webui`）。

> 💡 第一次登录后建议在手机 QQ 上开启「登录保护」或「设备锁」，
> 可以降低风险。

### 6.3 打开 WebUI 并配置网络

1. 在浏览器打开控制台里显示的 WebUI 地址（一般是
   <http://127.0.0.1:6099/webui>）
2. 用控制台打印的 **Token** 登录（首次登录后请立即改掉默认密码）
3. 左侧点击 **`网络配置`**
4. 点击 **`添加配置`**，选择 **`WebSocket 客户端`**（即「反向 WebSocket」）
5. 按下表填写：

| 字段 | 填什么 | 说明 |
| --- | --- | --- |
| 名称 | `nonebot` | 随便起 |
| URL | `ws://127.0.0.1:8080/onebot/v11/ws` | **必须完全一致**，端口和 `.env` 的 `PORT` 对应 |
| 令牌 / Token | 你在 4.2 生成的那串随机字符 | **必须和 `.env` 的 `ONEBOT_ACCESS_TOKEN` 一字不差** |
| 消息格式 | `array` | 必须是 array，不是 string |
| 启用心跳 | 开启 | 保持连接稳定 |
| 心跳间隔 | `30` | 秒 |

6. 点 **`保存`**，然后确保这条配置的开关是 **开启** 状态

### 6.4 判断连接成功

看**机器人运行的那个 PowerShell 窗口**（先按第七节把机器人跑起来），
如果出现：

```
[INFO] nonebot.utils | OneBot V11 | Bot 你的QQ号 connected
```

✅ **连接成功！** 现在去群里发 `@你的机器人 你好` 试试。

如果机器人窗口没有任何反应，或者 NapCat WebUI 显示连接失败：
回到 6.3 检查 URL 与 Token 是否完全一致（注意别多复制空格）。

---

## 七、启动机器人并验证

### 7.1 启动

在项目目录下：

```powershell
.\.venv\Scripts\python.exe bot.py
```

✅ **成功标志**：看到

```
[SUCCESS] nonebot | NoneBot is initializing...
[INFO] nonebot | Current Env: prod
[SUCCESS] nonebot.plugin.manager | Succeeded to load plugin "ai_chat" from "src.ai_chat"
[SUCCESS] nonebot | Running NoneBot...
[SUCCESS] nonebot.internal.driver.abstract | Loaded adapters: OneBot V11
[INFO] uvicorn.server | Uvicorn running on http://127.0.0.1:8080
```

**这个窗口不要关**，关了机器人就停了。按 `Ctrl + C` 停止。

### 7.2 不连 QQ 也能自测（推荐先做这步）

保持机器人运行，**再开一个新的 PowerShell 窗口**，进入项目目录，执行：

```powershell
.\.venv\Scripts\python.exe tools\probe_onebot_ws.py --send-message
```

✅ **成功标志**：打印出机器人的帮助文本。这说明
「机器人 ←→ OneBot 客户端」整条链路都通了。

再验证 AI 通路（会真的调用 DeepSeek，消耗极少量额度）：

```powershell
.\.venv\Scripts\python.exe tools\probe_ai_question.py "你好"
```

- 如果返回正常的 AI 回答 → 全部就绪 ✅
- 如果返回「AI 服务鉴权失败」 → `AI_API_KEY` 不对，回到第五节
- 如果返回「AI 服务余额不足」 → 去 DeepSeek 充值
- 如果返回「等待 AI 回复超时」 → 网络问题，检查代理或调大 `AI_TIMEOUT`

### 7.3 在真实 QQ 群里测试

在群里依次发这些消息，检查机器人反应：

| 发送内容 | 期望结果 |
| --- | --- |
| `/帮助` | 返回使用说明 |
| `@机器人 你好` | 返回 AI 回答 |
| `/ai 中国首都是哪里` | 返回 AI 回答 |
| `@机器人 我刚才问了什么` | 能说出上一轮内容（证明有上下文） |
| `/清空` | 提示已清除记忆 |
| `@机器人 我刚才问了什么` | 表示不知道了（证明清空生效） |

### 7.4 跑一遍自动化测试

```powershell
.\.venv\Scripts\python.exe -m pytest
```

✅ **成功标志**：最后一行类似 `59 passed, 4 skipped`。

> `skipped` 通常出现在还没初始化 Git 仓库时（那 4 项测试依赖 Git）。
> 执行 `git init` 之后再跑，就会变成全部通过。

---

## 八、上传到 GitHub

### 8.1 先做一次安全检查（非常重要）

在项目目录执行：

```powershell
# 确认 .env 被忽略了（应该输出 .env，说明它被 ignore）
git check-ignore -v .env

# 查看哪些文件会被提交（列表里绝对不能出现 .env、.venv、logs、data）
git status --short
```

⚠️ **如果看到 `.env` 出现在待提交列表里，立刻停下！**
检查 `.gitignore` 是否包含 `.env` 这一行，修好再继续。

### 8.2 创建本地提交

```powershell
git init
git add .
git commit -m "Initial commit: AI QQ bot"
```

✅ **成功标志**：输出里有一行 `Initial commit: AI QQ bot`，
并且列出了被提交的文件（大约 15 个，**没有** `.env`）。

### 8.3 在 GitHub 上创建空仓库

1. 浏览器打开 <https://github.com/new>
2. `Repository name` 填 `ai-qq-bot`（或你喜欢的名字）
3. 选择 `Public` 或 `Private`（都可以）
4. **下面的 `Add a README file`、`.gitignore`、`license` 全部不要勾选**
   （因为我们本地已经有文件了，勾了会产生冲突）
5. 点绿色按钮 **`Create repository`**

创建成功后会看到一个空仓库页面，页面上有 `https://github.com/你的用户名/ai-qq-bot.git`
这样的地址，**复制它**。

### 8.4 关联远程仓库并推送

回到 PowerShell（项目目录），把下面的地址换成你刚复制的：

```powershell
git remote add origin https://github.com/你的用户名/ai-qq-bot.git
git branch -M main
git push -u origin main
```

**第一次推送会弹出一个窗口**：

1. 选择 **`Sign in with your browser`**（用浏览器登录）
2. 浏览器会打开 GitHub 授权页面，点 **`Authorize`**
3. 授权成功后窗口自动关闭，命令行继续推送

✅ **成功标志**：命令行出现

```
 * [new branch]      main -> main
branch 'main' set up to track 'origin/main'.
```

然后刷新 GitHub 仓库页面，能看到你的代码文件。

> 🔒 **不需要**把 GitHub 密码、Personal Access Token 或验证码发给任何人（包括我）。
> 上面的浏览器授权是 GitHub 官方流程，凭据由 Windows 凭据管理器保管。

### 8.5 以后修改了代码怎么再次上传

```powershell
git add .
git commit -m "描述你改了什么"
git push
```

---

## 九、常见报错排查

### 启动相关

| 报错 | 原因 | 解决 |
| --- | --- | --- |
| `[配置错误] 没有找到配置文件` | 没有 `.env` | `copy .env.example .env` |
| `AI_API_KEY 格式看起来不对` | Key 首尾有空格/引号，或没复制完整 | 用记事本打开 `.env` 重新粘贴，**不要加引号** |
| `[Errno 10048] error while attempting to bind on address` | 8080 端口被占用 | 改 `.env` 的 `PORT=8081`，同时改 NapCat 的 URL 端口 |
| `ModuleNotFoundError: No module named 'nonebot'` | 依赖装到了系统 Python 而不是虚拟环境 | 用 `.\.venv\Scripts\python.exe -m pip install -r requirements.txt` |
| `ModuleNotFoundError: No module named 'websockets'` | 漏装反向 WS 依赖 | `.\.venv\Scripts\python.exe -m pip install websockets==17.2` |
| `PermissionError: [WinError 5]` 出现在写日志时 | 环境限制了进程间管道 | 把 `.env` 里 `LOG_ASYNC=false`（默认就是 false） |
| 双击 `bot.py` 窗口一闪而过 | 双击不会保留报错信息 | 用 PowerShell 执行，才能看到报错 |

### 连接相关

| 现象 | 检查顺序 |
| --- | --- |
| 机器人日志里没有 `Bot xxx connected` | ① NapCat 的网络配置是否**已启用**；② URL 是否为 `ws://127.0.0.1:8080/onebot/v11/ws`；③ Token 两边是否**完全一致** |
| NapCat 显示「连接成功」但机器人没日志 | 检查机器人窗口的 `PORT` 与 NapCat URL 里的端口是否一致 |
| WebSocket 返回 403 | Token 不匹配，或 NapCat 没带 `X-Self-ID` 头（用官方 NapCat 版本不会有这个问题） |
| 连接一会儿就断 | 打开 NapCat 配置里的「心跳」并设为 30 秒 |

### 使用相关

| 现象 | 原因 | 解决 |
| --- | --- | --- |
| 群里普通聊天机器人不理 | **这是设计如此**，只有 `@机器人` 或 `/ai` 才回复 | 正常行为 |
| @机器人 后没反应 | ① 是否 @ 到了正确账号；② 看机器人窗口有没有报错 | 检查日志 |
| 回复「慢一点～请等 x 秒」 | 冷却机制 | 等几秒，或把 `COOLDOWN_SECONDS` 改小 |
| 回复「你的问题太长了」 | 超过 `MAX_QUESTION_LENGTH`（默认 1000 字） | 精简问题，或调大该配置 |
| 回复被截断，末尾有「内容过长已截断」 | 超过 `MAX_REPLY_LENGTH` | 调大该配置，或在 `AI_SYSTEM_PROMPT` 里要求回答简短 |
| `/ai什么是Python` 没反应 | 这是允许的写法，应该能触发；若不行请改用 `/ai 什么是Python` | 确认是半角 `/` |
| 上下文没有保留 | `HISTORY_MAX_TURNS` 被设为 0 | 改回 `5` |
| 重启机器人后记忆没了 | 默认内存模式 | 把 `HISTORY_BACKEND=sqlite` |

### Git 相关

| 报错 | 解决 |
| --- | --- |
| `fatal: not a git repository` | 先 `git init` |
| `remote origin already exists` | `git remote set-url origin <新地址>` |
| `failed to push some refs` / 提示远程有内容 | 你在 GitHub 建仓库时勾选了 README。改用 `git pull --rebase origin main` 后再 `git push` |
| 推送一直要密码 | 执行 `git config --global credential.helper manager`，重新 `git push` 走浏览器授权 |
| 不小心把 `.env` 提交了 | **立刻停止推送**，然后：<br>`git rm --cached .env`<br>`git commit -m "Remove accidentally committed secrets"`<br>并**马上去 DeepSeek 控制台**把那个 Key 删掉重建 |

---

## 十、安全与风险

### 必须遵守

1. **`.env` 永远不进 Git**。提交前用 `git status --short` 检查一遍。
2. **`HOST` 保持 `127.0.0.1`**。改成 `0.0.0.0` 会把机器人接口暴露到公网。
3. **一定设置 `ONEBOT_ACCESS_TOKEN`**，且足够长足够随机。
4. **用测试小号**跑 NapCat，不用主力账号。
5. **不要把密钥发到群里、Gist、截图或聊天记录里**。

### Key 泄露了怎么办

1. 立刻到 <https://platform.deepseek.com/api_keys> **删除**泄露的那个 Key
2. 创建一个新的，填进本地 `.env`
3. 如果已推到 GitHub：清理 Git 历史（`git rm --cached .env` + 改写历史）或
   **直接把仓库删掉重建**（最省事、最彻底）
4. 检查账单，确认没有异常扣费

### NapCat 风险再提醒

- NapCat 修改 QQ 客户端，**违反腾讯用户协议**，有封号风险
- 它会在本地保存登录凭据（`session.token`、`device.json` 等），
  **这些文件已被 `.gitignore` 排除**，请勿上传
- 腾讯可能随时调整风控策略导致无法登录，这是这类方案的固有风险

---

## 附：常用命令速查

```powershell
# 启动机器人
.\.venv\Scripts\python.exe bot.py

# 跑测试
.\.venv\Scripts\python.exe -m pytest

# 链路自检（机器人需在运行）
.\.venv\Scripts\python.exe tools\probe_onebot_ws.py --send-message
.\.venv\Scripts\python.exe tools\probe_ai_question.py "你好"

# 看配置摘要（Key 会打码）
.\.venv\Scripts\python.exe -c "from config import get_settings; print(get_settings().describe())"

# 语法检查
.\.venv\Scripts\python.exe -m compileall -q bot.py config.py src tests

# Git 三连
git add . ; git commit -m "更新说明" ; git push
```
