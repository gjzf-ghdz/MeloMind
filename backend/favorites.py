"""MeloMind 歌曲收藏存储 - 纯标准库实现

按用户隔离的收藏夹，JSON 文件存储，原子写入。
结构: { "<username>": [ {fav_key, song, added_at}, ... ] }
"""
import json
import os
import threading
from datetime import datetime


def make_fav_key(song) -> str:
    """生成收藏去重键：优先用 id，其次 songmid，最后 title|artist。"""
    if not isinstance(song, dict):
        return ""
    key = (song.get("id") or "").strip()
    if key:
        return "id:" + key
    key = (song.get("songmid") or "").strip()
    if key:
        return "sm:" + key
    title = (song.get("title") or "").strip()
    artist = (song.get("artist") or "").strip()
    return "ta:" + title + "|" + artist


class FavoriteStore:
    def __init__(self, path: str):
        self.path = path
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

    def list_favorites(self, username: str):
        with self._lock:
            items = self._data.get(username, [])
            return [dict(item["song"]) for item in items if "song" in item]

    def is_favorited(self, username: str, fav_key: str) -> bool:
        if not fav_key:
            return False
        with self._lock:
            return any(item.get("fav_key") == fav_key
                       for item in self._data.get(username, []))

    def add(self, username: str, song):
        if not isinstance(song, dict) or not song:
            return False, "歌曲数据无效"
        fav_key = make_fav_key(song)
        if not fav_key:
            return False, "无法识别歌曲（缺少 id/标题）"
        with self._lock:
            self._ensure(username)
            items = self._data[username]
            if any(it.get("fav_key") == fav_key for it in items):
                # 幂等：已存在视为成功
                return True, fav_key
            items.append({
                "fav_key": fav_key,
                "song": song,
                "added_at": datetime.now().isoformat(timespec="seconds"),
            })
            self._save()
        return True, fav_key

    def remove(self, username: str, fav_key: str):
        if not fav_key:
            return False, "缺少收藏键"
        with self._lock:
            items = self._data.get(username, [])
            before = len(items)
            self._data[username] = [it for it in items
                                    if it.get("fav_key") != fav_key]
            if len(self._data[username]) == before:
                return False, "未找到该收藏"
            self._save()
        return True, fav_key

    def rename_user(self, old_username: str, new_username: str):
        """用户改名后迁移收藏数据。"""
        with self._lock:
            if old_username in self._data:
                self._data[new_username] = self._data.pop(old_username)
                self._save()
