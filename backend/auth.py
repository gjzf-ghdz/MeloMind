"""MeloMind 鉴权模块 - 纯标准库实现（零依赖）

提供：
- 密码哈希（PBKDF2-HMAC-SHA256 + 随机 salt）
- 会话令牌（secrets.token_hex）
- 用户表（JSON 文件存储，原子写入）
- 字段校验（用户名 / 密码 / 中国大陆手机号）
"""
import hashlib
import json
import os
import re
import secrets
import threading
from datetime import datetime

PBKDF2_ITERS = 100_000
SALT_BYTES = 16
TOKEN_BYTES = 32

USERNAME_RE = re.compile(r"^[A-Za-z0-9_]{3,20}$")
PHONE_RE = re.compile(r"^1[3-9]\d{9}$")


# ============================================================
# 密码哈希
# ============================================================
def hash_password(password: str):
    """返回 (salt_hex, hash_hex)"""
    salt = secrets.token_bytes(SALT_BYTES)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PBKDF2_ITERS)
    return salt.hex(), dk.hex()


def verify_password(password: str, salt_hex: str, hash_hex: str) -> bool:
    try:
        salt = bytes.fromhex(salt_hex)
        expected = bytes.fromhex(hash_hex)
    except ValueError:
        return False
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PBKDF2_ITERS)
    return secrets.compare_digest(dk, expected)


# ============================================================
# 字段校验
# ============================================================
def validate_username(username: str):
    if not username:
        return False, "用户名不能为空"
    if not USERNAME_RE.match(username):
        return False, "用户名需为 3-20 位字母、数字或下划线"
    return True, ""


def validate_password(password: str):
    if not password:
        return False, "密码不能为空"
    if len(password) < 6 or len(password) > 32:
        return False, "密码长度需为 6-32 位"
    return True, ""


def validate_phone(phone: str):
    if not phone:
        return False, "手机号不能为空"
    if not PHONE_RE.match(phone):
        return False, "手机号格式不正确（需为 11 位中国大陆手机号）"
    return True, ""


# ============================================================
# 用户表（JSON 文件存储）
# ============================================================
class UserStore:
    def __init__(self, path: str):
        self.path = path
        self._lock = threading.Lock()
        self._users = {}
        self._load()

    def _load(self):
        if not os.path.exists(self.path):
            self._users = {"users": []}
            return
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                self._users = json.load(f)
            if "users" not in self._users:
                self._users["users"] = []
        except (json.JSONDecodeError, OSError):
            self._users = {"users": []}

    def _save(self):
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self._users, f, ensure_ascii=False, indent=2)
        os.replace(tmp, self.path)

    def username_exists(self, username: str) -> bool:
        return any(u["username"] == username for u in self._users["users"])

    def phone_exists(self, phone: str) -> bool:
        return any(u.get("phone") == phone for u in self._users["users"])

    def get_user(self, username: str):
        for u in self._users["users"]:
            if u["username"] == username:
                return u
        return None

    def register(self, username: str, password: str, phone: str = ""):
        ok, msg = validate_username(username)
        if not ok:
            return False, msg
        ok, msg = validate_password(password)
        if not ok:
            return False, msg
        with self._lock:
            if self.username_exists(username):
                return False, "用户名已被注册"
            if phone and self.phone_exists(phone):
                return False, "手机号已被注册"
            salt_hex, hash_hex = hash_password(password)
            user = {
                "username": username,
                "phone": phone or "",
                "salt": salt_hex,
                "hash": hash_hex,
                "created_at": datetime.now().isoformat(timespec="seconds"),
                "preferences": {},  # 音乐偏好，注册后调查填充
            }
            self._users["users"].append(user)
            self._save()
        return True, {"username": username, "phone": phone or ""}

    def set_preferences(self, username: str, prefs: dict) -> bool:
        """保存用户音乐偏好"""
        with self._lock:
            user = self.get_user(username)
            if not user:
                return False
            user["preferences"] = prefs or {}
            self._save()
        return True

    def get_preferences(self, username: str) -> dict:
        """获取用户音乐偏好"""
        user = self.get_user(username)
        if not user:
            return {}
        return user.get("preferences") or {}

    def login(self, username: str, password: str):
        user = self.get_user(username)
        if not user:
            return False, "用户名或密码错误"
        if not verify_password(password, user["salt"], user["hash"]):
            return False, "用户名或密码错误"
        return True, {"username": user["username"], "phone": user.get("phone", "")}

    def update_username(self, old_username: str, new_username: str,
                        password: str):
        """修改用户名（需验证当前密码）。成功后返回新用户信息。"""
        user = self.get_user(old_username)
        if not user:
            return False, "用户不存在"
        if not verify_password(password, user["salt"], user["hash"]):
            return False, "密码不正确"
        if new_username == old_username:
            return False, "新用户名与当前用户名相同"
        ok, msg = validate_username(new_username)
        if not ok:
            return False, msg
        with self._lock:
            if self.username_exists(new_username):
                return False, "新用户名已被占用"
            user["username"] = new_username
            self._save()
        return True, {"username": new_username, "phone": user.get("phone", "")}

    def change_password(self, username: str, old_password: str,
                        new_password: str):
        """修改密码（需验证原密码）。"""
        user = self.get_user(username)
        if not user:
            return False, "用户不存在"
        if not verify_password(old_password, user["salt"], user["hash"]):
            return False, "原密码不正确"
        ok, msg = validate_password(new_password)
        if not ok:
            return False, msg
        if old_password == new_password:
            return False, "新密码不能与原密码相同"
        salt_hex, hash_hex = hash_password(new_password)
        with self._lock:
            user["salt"] = salt_hex
            user["hash"] = hash_hex
            self._save()
        return True, ""


# ============================================================
# 会话令牌（内存）
# ============================================================
class AuthSession:
    def __init__(self):
        self._tokens = {}  # token -> username
        self._lock = threading.Lock()

    def issue(self, username: str) -> str:
        token = secrets.token_hex(TOKEN_BYTES)
        with self._lock:
            self._tokens[token] = username
        return token

    def revoke(self, token: str) -> bool:
        with self._lock:
            return self._tokens.pop(token, None) is not None

    def update_username(self, old_username: str, new_username: str):
        """用户改名后同步所有有效会话，使当前登录状态保持有效。"""
        with self._lock:
            for token, uname in self._tokens.items():
                if uname == old_username:
                    self._tokens[token] = new_username

    def get_user(self, token: str):
        if not token:
            return None
        with self._lock:
            return self._tokens.get(token)
