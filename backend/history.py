"""MeloMind 搜索历史记录 - 纯标准库实现

按用户隔离的搜索历史，JSON 文件存储，原子写入。
结构: { "<username>": [ {query, task_type, songs, timestamp}, ... ] }

每用户最多保留 100 条记录，超出自动淘汰最早的。
"""
import json
import os
import threading
from datetime import datetime

MAX_HISTORY_PER_USER = 100


class HistoryStore:
    def __init__(self, path: str, max_records: int = MAX_HISTORY_PER_USER):
        self.path = path
        self.max_records = max_records
        self._lock = threading.Lock()
        self._data = {}
        self._load()

    def _load(self):
        if not os.path.exists(self.path):
            self._data = {}
            return
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                self._data = json.load(f)
            if not isinstance(self._data, dict):
                self._data = {}
        except (json.JSONDecodeError, OSError):
            self._data = {}

    def _save(self):
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self._data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, self.path)

    def _ensure(self, username: str):
        if username not in self._data:
            self._data[username] = []

    def add(self, username: str, query: str, task_type: str,
            songs: list, reply: str = "") -> bool:
        """添加一条搜索历史记录。songs 应为歌曲摘要列表。"""
        if not query:
            return False
        # 只保留歌曲的摘要信息（避免存储过多数据）
        song_summaries = []
        for s in (songs or [])[:8]:
            song_summaries.append({
                "title": s.get("title", ""),
                "artist": s.get("artist", ""),
                "qqmusic_url": s.get("qqmusic_url", ""),
                "search_keyword": s.get("search_keyword", ""),
            })
        record = {
            "query": query.strip(),
            "task_type": task_type or "",
            "reply": (reply or "")[:2000],
            "songs": song_summaries,
            "timestamp": datetime.now().isoformat(timespec="seconds"),
        }
        with self._lock:
            self._ensure(username)
            self._data[username].insert(0, record)  # 最新的在最前
            # 超出上限淘汰最早的
            if len(self._data[username]) > self.max_records:
                self._data[username] = self._data[username][:self.max_records]
            self._save()
        return True

    def list(self, username: str, limit: int = 50) -> list:
        with self._lock:
            items = self._data.get(username, [])
            return items[:limit]

    def clear(self, username: str) -> bool:
        with self._lock:
            if username in self._data:
                self._data[username] = []
                self._save()
        return True

    def rename_user(self, old_username: str, new_username: str):
        """用户改名后迁移历史数据。"""
        with self._lock:
            if old_username in self._data:
                self._data[new_username] = self._data.pop(old_username)
                self._save()
