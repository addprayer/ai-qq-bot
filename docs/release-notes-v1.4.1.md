# AI QQ Bot v1.4.1

修复**一键启动脚本在真实环境下打不开 NapCat** 的问题，并把玛奇玛的回复调得更简短。

---

## 一、启动脚本的三个 bug（都已修复）

你之前看到的现象：

```
NapCat directory:                      ← 空
Starting NapCat in a new administrator window ...
系统无法执行指定的程序。                ← 启动失败
```

原因是三个问题叠加：

### 1. 行尾是 LF，不是 CRLF

cmd.exe 对 **LF-only** 的批处理解析不可靠（尤其带 `setlocal` / 标签 / `goto` 时），
导致 `set "NAPCAT_DIR=..."` 没生效 → 路径为空 → 后续命令全错。

**修复**：两个 `.bat` 全部重写为 CRLF，并加了自检
（写完就验证 `纯LF=0`）。

### 2. 混入了中文注释

我往 `.bat` 里加了中文说明，但控制台是 GBK 代码页，
UTF-8 的中文字节被误解码，进一步干扰解析。

**修复**：所有 `.bat` 改为**纯 ASCII**，注释用英文
（已验证 `非ASCII=0`）。

### 3. 没有提权，而 NapCat 需要管理员权限

NapCat 要注入 QQ 主进程，普通权限下 `NapCatWinBootMain.exe` 会起来但登不上、
也不监听 6099。

**修复**：脚本启动时先检测权限，不是管理员就自动用 `RunAs` 重启自己。

细节：

- 用 **SID 检测**（`S-1-16-12288` 高完整性令牌），不用 `fltmc` / `net session`
  —— 后两者在部分机器上即使管理员也返回失败，会导致死循环
- 提权重启时带 `--elevated` 参数，避免"提权后又被检测为非管理员"的无限弹窗

### 顺带：启动时跳过扫码

`NAPCAT_BAT` 从 `napcat.bat` 改为 `napcat.quick.bat`，
启动时带上 QQ 号复用本地已保存的会话。

实测效果：NapCat 直接登录并连上机器人，**没有再弹二维码**。

---

## 二、人设调整

把"允许少量神态/动作描写"换成了更严格的简短要求：

| 原来 | 现在 |
| --- | --- |
| 允许少量神态/动作描写，如"（笑）" | **说话言简意赅、直截了当**，大部分回答只用一句话 |
| — | 不用语气组词，不复述用户的话 |
| — | 不要有口头禅，面对同样的话要有不同表达方式 |

目的是让回复更像真人发的短消息，少一点模板感。

---

## 三、现在启动是什么样

双击 `start_all.bat` → UAC 点「是」→ 应该看到：

```
Administrator mode detected.

============================================================
  AI QQ Bot - full startup (NapCat + Bot)
============================================================

  NapCat directory: C:\napcat\NapCat.52230.Shell

[OK] NapCat is running.

Loading the daily launcher ...
```

然后机器人窗口出现 `Bot <你的QQ号> connected`。

> ⚠️ UAC 如果点「否」，脚本会直接退出，什么都不会启动。

---

## 四、两个已知限制

1. **机器人进程也会以管理员身份运行**（因为整个脚本提权了）。
   本地使用没问题，想更严格可以改成"只给 NapCat 提权"。
2. `napcat.quick.bat` 和 `napcat.json` 在 **NapCat 安装目录**（不在本仓库），
   重装或移动 NapCat 后需要重新设置这两处。

---

## 五、升级方式

```powershell
cd <项目目录>\QQBot
git pull
```

然后双击 `start_all.bat`。

---

## 六、测试

**116 项自动化测试全部通过。**

完整变更见 [CHANGELOG.md](CHANGELOG.md)
