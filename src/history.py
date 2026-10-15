"""对话历史：按「群 + 用户」隔离的上下文管理。

有两种实现：

* :class:`InMemoryHistoryStore` —— 默认，存在内存里，重启即清空。
* :class:`SQLiteHistoryStore` —— 写进 ``data/history.db``，重启后仍然保留。

两者接口一致（:class:`HistoryStore`），可以在 ``.env`` 里用
``HISTORY_BACKEND=sqlite`` 切换。

另外提供 :class:`CooldownTracker`，用于「同一用户短时间内不要重复请求」。
"""

from __future__ import annotations

import sqlite3
import threading
import time
from abc import ABC, abstractmethod
from collections import OrderedDict, deque
from pathlib import Path
from typing import Deque, Iterable

from loguru import logger

Message = dict[str, str]


# ---------------------------------------------------------------------------
# 接口
# ---------------------------------------------------------------------------


class HistoryStore(ABC):
    """对话历史的统一接口。"""

    @abstractmethod
    def append_turn(self, group_id: str, user_id: str, question: str, answer: str) -> None:
        """记录一轮问答。"""

    @abstractmethod
    def get_messages(self, group_id: str, user_id: str) -> list[Message]:
        """取出该用户在该群的上下文消息列表（已按轮数上限裁剪）。"""

    @abstractmethod
    def clear(self, group_id: str, user_id: str) -> int:
        """清空该用户在该群的历史，返回被删除的消息条数。"""

    @abstractmethod
    def turn_count(self, group_id: str, user_id: str) -> int:
        """该用户在该群已经保存了几轮对话。"""

    @abstractmethod
    def clear_all(self) -> None:
        """清空所有历史（测试与运维用）。"""


# ---------------------------------------------------------------------------
# 内存实现
# ---------------------------------------------------------------------------


class InMemoryHistoryStore(HistoryStore):
    """把历史放在内存里，用 ``(群号, 用户号)`` 作为 key 做隔离。

    * 每个 key 最多保存 ``max_turns`` 轮；
    * 最多跟踪 ``max_users`` 个 key，超出时淘汰最久未使用的（LRU）。
    """

    def __init__(self, *, max_turns: int = 5, max_users: int = 500) -> None:
        self.max_turns = max(0, int(max_turns))
        self.max_users = max(1, int(max_users))
        # OrderedDict 的头部是「最久未使用」
        self._store: "OrderedDict[tuple[str, str], Deque[Message]]" = OrderedDict()

    # -- 内部 ------------------------------------------------------------

    @staticmethod
    def _key(group_id: object, user_id: object) -> tuple[str, str]:
        return (str(group_id), str(user_id))

    def _bucket(self, key: tuple[str, str], *, create: bool) -> Deque[Message] | None:
        bucket = self._store.get(key)
        if bucket is None:
            if not create:
                return None
            bucket = deque(maxlen=self.max_turns * 2)
            self._store[key] = bucket
        self._store.move_to_end(key)  # 标记为最近使用
        return bucket

    def _evict(self) -> None:
        while len(self._store) > self.max_users:
            key, _ = self._store.popitem(last=False)
            logger.debug("历史缓存已满，淘汰最久未使用的会话 {}", key)

    def _trim(self, bucket: Deque[Message]) -> None:
        if self.max_turns == 0:
            bucket.clear()
            return
        while len(bucket) > self.max_turns * 2:
            bucket.popleft()

    # -- 接口实现 --------------------------------------------------------

    def append_turn(self, group_id: str, user_id: str, question: str, answer: str) -> None:
        if self.max_turns == 0:
            return
        key = self._key(group_id, user_id)
        bucket = self._bucket(key, create=True)
        assert bucket is not None
        bucket.append({"role": "user", "content": question})
        bucket.append({"role": "assistant", "content": answer})
        self._trim(bucket)
        self._evict()

    def get_messages(self, group_id: str, user_id: str) -> list[Message]:
        bucket = self._bucket(self._key(group_id, user_id), create=False)
        if not bucket:
            return []
        return [dict(item) for item in bucket]

    def clear(self, group_id: str, user_id: str) -> int:
        key = self._key(group_id, user_id)
        bucket = self._store.pop(key, None)
        return len(bucket) if bucket else 0

    def turn_count(self, group_id: str, user_id: str) -> int:
        bucket = self._bucket(self._key(group_id, user_id), create=False)
        return (len(bucket) // 2) if bucket else 0

    def clear_all(self) -> None:
        self._store.clear()

    # -- 运维辅助 --------------------------------------------------------

    @property
    def session_count(self) -> int:
        """当前被跟踪的会话数量。"""
        return len(self._store)


# ---------------------------------------------------------------------------
# SQLite 实现（持久化）
# ---------------------------------------------------------------------------


class SQLiteHistoryStore(HistoryStore):
    """把历史写进 SQLite 文件，重启机器人后上下文仍在。

    使用标准库 ``sqlite3``（同步），单次写入只有几毫秒，
    对 QQ 群机器人这种低并发场景完全够用。
    """

    _SCHEMA = """
    CREATE TABLE IF NOT EXISTS chat_turns (
        id         INTEGER PRIMARY KEY AUTOINCREMENT,
        group_id   TEXT    NOT NULL,
        user_id    TEXT    NOT NULL,
        question   TEXT    NOT NULL,
        answer     TEXT    NOT NULL,
        created_at REAL    NOT NULL
    );
    CREATE INDEX IF NOT EXISTS idx_chat_turns_lookup
        ON chat_turns (group_id, user_id, id DESC);
    """

    def __init__(self, db_path: Path, *, max_turns: int = 5) -> None:
        self.db_path = Path(db_path)
        self.max_turns = max(0, int(max_turns))
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL;")
        self._conn.executescript(self._SCHEMA)
        self._conn.commit()

    # -- 接口实现 --------------------------------------------------------

    def append_turn(self, group_id: str, user_id: str, question: str, answer: str) -> None:
        if self.max_turns == 0:
            return
        with self._lock:
            self._conn.execute(
                "INSERT INTO chat_turns (group_id, user_id, question, answer, created_at)"
                " VALUES (?, ?, ?, ?, ?)",
                (str(group_id), str(user_id), question, answer, time.time()),
            )
            # 只保留最近 max_turns 轮，多余的直接删掉，避免数据库无限增长
            self._conn.execute(
                "DELETE FROM chat_turns WHERE group_id = ? AND user_id = ? AND id NOT IN ("
                "  SELECT id FROM chat_turns WHERE group_id = ? AND user_id = ?"
                "  ORDER BY id DESC LIMIT ?)",
                (str(group_id), str(user_id), str(group_id), str(user_id), self.max_turns),
            )
            self._conn.commit()

    def get_messages(self, group_id: str, user_id: str) -> list[Message]:
        if self.max_turns == 0:
            return []
        with self._lock:
            rows = self._conn.execute(
                "SELECT question, answer FROM chat_turns"
                " WHERE group_id = ? AND user_id = ? ORDER BY id DESC LIMIT ?",
                (str(group_id), str(user_id), self.max_turns),
            ).fetchall()
        messages: list[Message] = []
        for question, answer in reversed(rows):  # 恢复成时间正序
            messages.append({"role": "user", "content": question})
            messages.append({"role": "assistant", "content": answer})
        return messages

    def clear(self, group_id: str, user_id: str) -> int:
        with self._lock:
            cursor = self._conn.execute(
                "DELETE FROM chat_turns WHERE group_id = ? AND user_id = ?",
                (str(group_id), str(user_id)),
            )
            self._conn.commit()
        return int(cursor.rowcount or 0)

    def turn_count(self, group_id: str, user_id: str) -> int:
        with self._lock:
            row = self._conn.execute(
                "SELECT COUNT(*) FROM chat_turns WHERE group_id = ? AND user_id = ?",
                (str(group_id), str(user_id)),
            ).fetchone()
        return int(row[0]) if row else 0

    def clear_all(self) -> None:
        with self._lock:
            self._conn.execute("DELETE FROM chat_turns")
            self._conn.commit()

    def close(self) -> None:
        with self._lock:
            self._conn.close()


# ---------------------------------------------------------------------------
# 冷却（频率限制）
# ---------------------------------------------------------------------------


class CooldownTracker:
    """记录「某个用户上次请求的时间」，用于限制请求频率。

    时间来源可注入（``clock``），方便单元测试不依赖真实等待。
    """

    def __init__(self, seconds: float = 5.0, *, clock=time.monotonic) -> None:
        self.seconds = max(0.0, float(seconds))
        self._clock = clock
        self._last: dict[tuple[str, str], float] = {}

    def check(self, group_id: str, user_id: str) -> float:
        """返回剩余冷却秒数；``0`` 表示可以请求。

        不修改状态——通过检查后需要显式调用 :meth:`touch`。
        """
        if self.seconds <= 0:
            return 0.0
        last = self._last.get((str(group_id), str(user_id)))
        if last is None:
            return 0.0
        remaining = self.seconds - (self._clock() - last)
        return max(0.0, remaining)

    def touch(self, group_id: str, user_id: str) -> None:
        """记录一次成功发起的请求时间。"""
        self._last[(str(group_id), str(user_id))] = self._clock()

    def reset(self) -> None:
        self._last.clear()

    @property
    def tracked(self) -> int:
        return len(self._last)


# ---------------------------------------------------------------------------
# 工厂
# ---------------------------------------------------------------------------


def build_history_store(settings) -> HistoryStore:
    """根据配置创建历史存储。

    ``HISTORY_BACKEND=memory``（默认）或 ``HISTORY_BACKEND=sqlite``。
    """
    from config import DEFAULT_HISTORY_DB

    backend = str(getattr(settings, "history_backend", "memory")).lower()
    max_turns = int(getattr(settings, "history_max_turns", 5))
    if backend == "sqlite":
        db_path = Path(getattr(settings, "history_db_path", None) or DEFAULT_HISTORY_DB)
        logger.info("对话历史使用 SQLite 持久化：{}", db_path)
        return SQLiteHistoryStore(db_path, max_turns=max_turns)
    return InMemoryHistoryStore(max_turns=max_turns)


__all__ = [
    "CooldownTracker",
    "HistoryStore",
    "InMemoryHistoryStore",
    "SQLiteHistoryStore",
    "build_history_store",
]
