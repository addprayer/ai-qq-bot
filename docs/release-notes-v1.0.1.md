# AI QQ Bot v1.0.1

修复 v1.0.0 中**一键启动脚本无法工作**的严重问题。如果你在用 v1.0.0，请务必更新。

## 修复的问题

### 1. `start_all.bat` 启动 NapCat 直接报错（严重）

v1.0.0 里用的是：

```bat
start "NapCat" cmd /c "cd /d ^"C:\napcat\NapCat.52230.Shell^" && napcat.bat"
```

这串引号转义在**路径含空格时会被 cmd 解析错乱**，结果报：

```
'napcat.bat"' is not recognized as an internal or external command,
operable program or batch file.
```

现在改成：

```bat
start "NapCat" /d "C:\napcat\NapCat.52230.Shell" cmd /c "napcat.bat"
```

**完全不做引号转义**，从根本上消除这个问题。

### 2. NapCat 已在运行时被重复拉起

端口检测原先用 PowerShell 的 `Test-NetConnection`，在部分环境下会误判为空闲
（返回 `TcpTestSucceeded: False`），导致重复启动 NapCat。

现改用新增的 `tools/wait_port.py`（直接 socket 连接），检测更可靠。

### 3. 等待循环在输入重定向环境下报错

原先用 `timeout /t 2`，在输入被重定向时会报
`ERROR: Input redirection is not supported, exiting the process immediately`。
现改用 `powershell -Command "Start-Sleep -Seconds 2"`。

### 4. 变量在 for 循环内读不到

`start_all.bat` 缺少 `EnableDelayedExpansion`，导致循环中 `!PORT_OPEN!` 取不到值。

## 新增

- `tools/wait_port.py` —— 端口探测小工具，可单独使用：

  ```powershell
  .\.venv\Scripts\python.exe tools\wait_port.py 6099            # 检查一次
  .\.venv\Scripts\python.exe tools\wait_port.py 6099 --wait 90  # 最多等 90 秒
  ```

  退出码 `0` 表示端口已就绪，`1` 表示超时。这样批处理里就不必再内联
  容易出错的 Python / PowerShell 一行命令了。

## 验证方式

这次没有只靠"看起来对"，而是用**桩进程**对 `start_all.bat` 做了双分支实测：

| 场景 | 预期 | 实测结果 |
| --- | --- | --- |
| 6099 端口已被占用 | 跳过启动 NapCat，直接进入机器人启动 | ✅ 输出 `NapCat is already running - skipping`，桩未被调用 |
| 6099 端口空闲 | 拉起 NapCat | ✅ 桩在**含空格的目录**中确实被执行，无引号转义报错 |

同时确认了 `wait_port.py` 在端口有/无监听两种情况下的退出码都正确。

## 升级方式

覆盖更新即可，**不需要改动 `.env`**：

```powershell
cd <项目目录>\QQBot
git pull
```

然后双击 `start_all.bat`。

## 完整变更

见 [CHANGELOG.md](CHANGELOG.md)
