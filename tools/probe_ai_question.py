"""一次性验证：模拟网友提问，检查机器人是否返回了友好提示。

用法：机器人已在运行时执行

    # 模拟「@机器人 问题」
    .\\.venv\\Scripts\\python.exe tools\\probe_ai_question.py "你好"

    # 模拟「/ai 问题」（不加 @）
    .\\.venv\\Scripts\\python.exe tools\\probe_ai_question.py --no-at "/ai 你好"
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time

import websockets

URL = f"ws://127.0.0.1:{os.environ.get('PROBE_PORT', '8080')}/onebot/v11/ws"
TOKEN = os.environ.get("PROBE_TOKEN", "dev-local-token-please-change")
SELF_ID = 10000
GROUP_ID = 123456789
USER_ID = 10001


async def main(question: str, *, at_me: bool) -> int:
    headers = {"X-Self-ID": str(SELF_ID), "X-Client-Role": "Universal"}
    if TOKEN:
        headers["Authorization"] = f"Bearer {TOKEN}"

    segments = []
    raw_parts = []
    if at_me:
        segments.append({"type": "at", "data": {"qq": str(SELF_ID)}})
        raw_parts.append(f"[CQ:at,qq={SELF_ID}]")
    segments.append({"type": "text", "data": {"text": f" {question}"}})
    raw_parts.append(f" {question}")

    async with websockets.connect(URL, additional_headers=headers, open_timeout=10) as ws:
        event = {
            "post_type": "message",
            "message_type": "group",
            "sub_type": "normal",
            "message_id": 2001,
            "group_id": GROUP_ID,
            "user_id": USER_ID,
            "time": int(time.time()),
            "self_id": SELF_ID,
            "raw_message": "".join(raw_parts),
            "font": 0,
            "sender": {"user_id": USER_ID, "nickname": "测试群友", "role": "member"},
            "message": segments,
        }
        await ws.send(json.dumps(event))
        print(f"已发送群消息：{'@机器人 ' if at_me else ''}{question}")
        print("等待机器人回复（最多 90 秒，真实调用 API 会比较慢）...")

        while True:
            raw = await asyncio.wait_for(ws.recv(), timeout=90)
            data = json.loads(raw)
            if data.get("action") in {"send_group_msg", "send_msg"}:
                segs = (data.get("params") or {}).get("message") or []
                text = "".join(
                    s.get("data", {}).get("text", "") for s in segs if s.get("type") == "text"
                )
                print()
                print("机器人回复：")
                print("  " + text.replace("\n", "\n  "))
                await ws.send(json.dumps({"status": "ok", "retcode": 0, "data": {"message_id": 1}, "echo": data.get("echo")}))
                return 0
    return 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="模拟群友提问")
    parser.add_argument("question", help="要发送的内容")
    parser.add_argument("--no-at", action="store_true", help="不 @机器人（用于测试 /ai 指令）")
    args = parser.parse_args()
    sys.exit(asyncio.run(main(args.question, at_me=not args.no_at)))
