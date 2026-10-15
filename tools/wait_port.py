"""端口探测小工具，供 start_all.bat 判断 NapCat 是否已在运行。

为什么要单独一个文件，而不是在 .bat 里内联 Python 一行命令：
批处理里的引号转义非常容易出错（这个脚本的前一版就因为转义问题启动失败），
把逻辑放到 .py 里既清晰又能单独测试。

用法::

    python tools/wait_port.py 6099            # 检查一次
    python tools/wait_port.py 6099 --wait 90  # 最多等 90 秒

退出码: 0 = 端口已就绪，1 = 超时/未就绪
"""

from __future__ import annotations

import argparse
import socket
import sys
import time

HOST = "127.0.0.1"


def is_open(port: int, timeout: float = 2.0) -> bool:
    """端口上是否有人在监听。"""
    sock = socket.socket()
    sock.settimeout(timeout)
    try:
        return sock.connect_ex((HOST, port)) == 0
    finally:
        sock.close()


def wait_for(port: int, seconds: float, *, interval: float = 2.0) -> bool:
    """在 seconds 秒内轮询等待端口就绪。"""
    deadline = time.monotonic() + seconds
    while True:
        if is_open(port):
            return True
        if time.monotonic() >= deadline:
            return False
        time.sleep(interval)


def main() -> int:
    parser = argparse.ArgumentParser(description="检查端口是否已在监听")
    parser.add_argument("port", type=int, help="要检查的端口")
    parser.add_argument("--wait", type=float, default=0.0, help="最多等待多少秒")
    parser.add_argument("--quiet", action="store_true", help="不打印任何内容，只用退出码")
    args = parser.parse_args()

    if args.wait > 0:
        ready = wait_for(args.port, args.wait)
    else:
        ready = is_open(args.port)

    if not args.quiet:
        state = "已在监听" if ready else "未监听"
        print(f"{HOST}:{args.port} {state}")
    return 0 if ready else 1


if __name__ == "__main__":
    sys.exit(main())
