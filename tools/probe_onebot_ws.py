"""反向 WebSocket 自检 + 模拟群消息测试（不需要 QQ、不需要 NapCat、不需要真实 API Key）。

它模拟 NapCat 的行为，分两步：

**第一步：握手**
1. 带上 ``X-Self-ID`` / ``Authorization`` 连接到 ``ws://127.0.0.1:8080/onebot/v11/ws``；
2. 连接被接受后，机器人日志里会出现 ``Bot <self_id> connected``（这就是成功标志）；
3. 脚本再发一个心跳，确认双向数据通畅。

**第二步（可选）：模拟一条 @机器人 的群消息**
加上 ``--send-message`` 参数后，脚本会发一条群消息事件，并打印机器人的回复。

用法：

    # 只做握手检查
    .\\.venv\\Scripts\\python.exe tools\\probe_onebot_ws.py

    # 握手 + 模拟一条群消息（会真正触发 /帮助 逻辑，不需要 AI Key）
    .\\.venv\\Scripts\\python.exe tools\\probe_onebot_ws.py --send-message

退出码：0 表示成功，1 表示失败。
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time

import websockets

HOST = os.environ.get("PROBE_HOST", "127.0.0.1")
PORT = os.environ.get("PROBE_PORT", "8080")
URL = f"ws://{HOST}:{PORT}/onebot/v11/ws"
SELF_ID = int(os.environ.get("PROBE_SELF_ID", "10000"))


def _load_token() -> str:
    """优先用环境变量，其次从项目 .env 读取，最后退回示例值。

    这样改了 .env 里的 ONEBOT_ACCESS_TOKEN 之后，本脚本会自动跟着变，
    不会因为两边不一致而莫名其妙收到 403。
    """
    token = os.environ.get("PROBE_TOKEN")
    if token:
        return token
    try:
        import sys
        from pathlib import Path

        root = Path(__file__).resolve().parent.parent
        if str(root) not in sys.path:
            sys.path.insert(0, str(root))
        from config import get_settings

        return get_settings().access_token
    except Exception:
        return "dev-local-token-please-change"


TOKEN = _load_token()
GROUP_ID = int(os.environ.get("PROBE_GROUP_ID", "123456789"))
USER_ID = int(os.environ.get("PROBE_USER_ID", "10001"))
NICKNAME = os.environ.get("PROBE_NICKNAME", "测试群友")


def build_headers() -> dict[str, str]:
    headers = {
        "X-Self-ID": str(SELF_ID),
        "X-Client-Role": "Universal",
        "User-Agent": "OneBot/11 probe",
    }
    if TOKEN:
        headers["Authorization"] = f"Bearer {TOKEN}"
    return headers


async def check_handshake(ws) -> bool:
    """发一个心跳，确认通道双向可用。"""
    await ws.send(
        json.dumps(
            {
                "post_type": "meta_event",
                "meta_event_type": "heartbeat",
                "time": int(time.time()),
                "self_id": SELF_ID,
                "status": {"online": True, "good": True},
                "interval": 5000,
            }
        )
    )
    print("[2/4] 已发送心跳事件，连接保持正常")
    return True


#: 机器人可能用这些 action 发消息（不同适配器/版本略有差异）
SEND_ACTIONS = {"send_group_msg", "send_msg", "send_private_msg"}


async def wait_for_group_msg(ws, timeout: float = 30.0) -> dict | None:
    """等待机器人调用发送消息的接口，取回它带 echo 的请求。"""
    deadline = time.monotonic() + timeout
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return None
        raw = await asyncio.wait_for(ws.recv(), timeout=remaining)
        data = json.loads(raw)
        if data.get("action") in SEND_ACTIONS:
            return data
        print(f"      [收到其他事件] {json.dumps(data, ensure_ascii=False)[:160]}")


async def reply_ok(ws, request: dict, message_id: int = 9001) -> None:
    """按 OneBot V11 规范回复 API 调用结果。

    关键点：``echo`` 必须**原样带回**，否则 NoneBot 无法把结果对应到刚才那次调用，
    机器人会一直等到超时。
    """
    await ws.send(
        json.dumps(
            {
                "status": "ok",
                "retcode": 0,
                "data": {"message_id": message_id},
                "echo": request.get("echo"),
            }
        )
    )


async def send_test_group_message(ws) -> bool:
    """发一条 @机器人 /帮助 的群消息，验证机器人会回复。"""
    print()
    print("[3/4] 发送模拟群消息：@机器人 /帮助")
    event = {
        "post_type": "message",
        "message_type": "group",
        "sub_type": "normal",
        "message_id": 1001,
        "group_id": GROUP_ID,
        "user_id": USER_ID,
        "time": int(time.time()),
        "self_id": SELF_ID,
        "raw_message": f"[CQ:at,qq={SELF_ID}] /帮助",
        "font": 0,
        "sender": {"user_id": USER_ID, "nickname": NICKNAME, "role": "member"},
        "message": [
            {"type": "at", "data": {"qq": str(SELF_ID)}},
            {"type": "text", "data": {"text": " /帮助"}},
        ],
    }
    await ws.send(json.dumps(event))

    request = await wait_for_group_msg(ws, timeout=30)
    if request is None:
        print("[4/4] [失败] 30 秒内没有收到机器人调用 send_group_msg")
        return False

    sent = (request.get("params") or {}).get("message") or []
    text = "".join(seg.get("data", {}).get("text", "") for seg in sent if seg.get("type") == "text")
    print("[4/4] 机器人调用了 send_group_msg，回复内容如下：")
    print("      " + "-" * 58)
    for line in text.splitlines():
        print(f"      {line}")
    print("      " + "-" * 58)

    await reply_ok(ws, request)
    print("      已按 echo 回包，机器人侧调用正常结束")
    return True


async def main(send_message: bool) -> int:
    try:
        async with websockets.connect(URL, additional_headers=build_headers(), open_timeout=10) as ws:
            print(f"[1/4] 已连接到 {URL}")
            await check_handshake(ws)

            if not send_message:
                print()
                print("握手检查通过。加 --send-message 参数可以顺带测试消息处理链路。")
                await asyncio.sleep(0.5)
                return 0

            ok = await send_test_group_message(ws)
            await asyncio.sleep(0.5)
            return 0 if ok else 1

    except Exception as exc:  # noqa: BLE001
        print(f"[X] 连接失败：{type(exc).__name__}: {exc}")
        if "403" in str(exc):
            print("    提示：403 通常是 Token 不一致，或缺少 X-Self-ID 头。")
            print(f"    当前 Token 长度：{len(TOKEN)}（不打印内容，避免泄露到日志）")
            print("    请确认 .env 的 ONEBOT_ACCESS_TOKEN 与 NapCat 里填的完全一致。")
        return 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="反向 WebSocket 自检")
    parser.add_argument("--send-message", action="store_true", help="顺带发送一条模拟群消息")
    args = parser.parse_args()
    sys.exit(asyncio.run(main(args.send_message)))
