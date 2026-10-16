"""MeloMind 服务器 - 音乐推荐，站内 30 秒试听 + 跳转 QQ 音乐"""
import json, os, sys, time, threading, subprocess, shutil
import urllib.parse
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from models import (Analysis, MusicStrategy, infer_instrument_type, LANG_GROUPS,
                    emotion_word)
from llm_engine import LLMEngine
from music_strategy import MusicStrategyGenerator
from recommender import MusicRecommender
from qqmusic_source import get_qqmusic
from auth import UserStore, AuthSession
from favorites import FavoriteStore, make_fav_key
from history import HistoryStore
try:
    from audio_preview import resolve_preview
except Exception as _preview_err:            # 模块缺失/异常时降级：站点照常启动
    print(f"[Preview] 试听模块不可用，已降级为不可试听: "
          f"{type(_preview_err).__name__}: {_preview_err}", flush=True)

    def resolve_preview(mid="", title="", artist="", duration=0.0):
        return {}


llm = LLMEngine()
strategy_gen = MusicStrategyGenerator()
recommender = MusicRecommender()

BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
FRONTEND_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "frontend")

user_store = UserStore(os.path.join(BACKEND_DIR, "users.json"))
auth_session = AuthSession()
fav_store = FavoriteStore(os.path.join(BACKEND_DIR, "favorites.json"))
history_store = HistoryStore(os.path.join(BACKEND_DIR, "history.json"))


class MeloMindHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=FRONTEND_DIR, **kwargs)

    def end_headers(self):
        # 静态资源禁用强缓存：浏览器每次向服务器验证，
        # 文件更新后立即生效，未更新时返回 304 省流量
        path = (getattr(self, "path", "") or "").split("?")[0]
        if not path.startswith("/api/"):
            self.send_header("Cache-Control", "no-cache, must-revalidate")
        super().end_headers()

    def do_POST(self):
        try:
            self._route_post()
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            pass  # 客户端提前断开，无需也无法响应
        except Exception as e:
            import traceback
            traceback.print_exc()
            # 关键兜底：任何未捕获异常都必须返回 JSON，避免前端收到空响应体；
            # 带上异常详情便于远程定位
            try:
                detail = f"{type(e).__name__}: {e}"
                self._send_json({"error": f"服务器内部错误，请稍后重试（{detail}）"}, 500)
            except Exception:
                pass

    def _route_post(self):
        if self.path == "/api/chat":
            self._handle_chat()
        elif self.path == "/api/song_detail":
            self._handle_song_detail()
        elif self.path == "/api/register":
            self._handle_register()
        elif self.path == "/api/login":
            self._handle_login()
        elif self.path == "/api/logout":
            self._handle_logout()
        elif self.path == "/api/user/update_username":
            self._handle_update_username()
        elif self.path == "/api/user/change_password":
            self._handle_change_password()
        elif self.path == "/api/user/preferences":
            self._handle_preferences()
        elif self.path == "/api/favorites/add":
            self._handle_fav_add()
        elif self.path == "/api/favorites/remove":
            self._handle_fav_remove()
        elif self.path == "/api/history":
            self._handle_history_add()
        elif self.path == "/api/deploy":
            self._handle_deploy()
        else:
            self._send_json({"error": "Not found"}, 404)

    def do_GET(self):
        try:
            self._route_get()
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            pass  # 客户端提前断开
        except Exception as e:
            import traceback
            traceback.print_exc()
            try:
                detail = f"{type(e).__name__}: {e}"
                self._send_json({"error": f"服务器内部错误，请稍后重试（{detail}）"}, 500)
            except Exception:
                pass

    def _route_get(self):
        if self.path == "/api/me":
            self._handle_me()
        elif self.path == "/api/favorites":
            self._handle_fav_list()
        elif self.path == "/api/history":
            self._handle_history_list()
        elif self.path == "/api/music_db":
            self._handle_music_db()
        elif self.path == "/api/event_keywords":
            self._handle_event_keywords()
        elif self.path.split("?")[0] == "/api/preview":
            self._handle_preview()
        else:
            super().do_GET()

    def _get_bearer_token(self):
        auth_header = self.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            return auth_header[7:].strip()
        return ""

    def _require_user(self):
        """解析 token 返回 username；失败时发 401 并返回 None。"""
        token = self._get_bearer_token()
        username = auth_session.get_user(token)
        if not username:
            self._send_json({"ok": False, "error": "未登录"}, 401)
            return None
        return username

    def _handle_register(self):
        data = self._read_json()
        if data is None:
            return
        username = (data.get("username") or "").strip()
        password = data.get("password") or ""
        phone = (data.get("phone") or "").strip()

        ok, result = user_store.register(username, password, phone)
        if not ok:
            self._send_json({"ok": False, "error": result}, 400)
            return
        token = auth_session.issue(result["username"])
        self._send_json({
            "ok": True,
            "token": token,
            "user": result,
        })

    def _handle_login(self):
        data = self._read_json()
        if data is None:
            return
        username = (data.get("username") or "").strip()
        password = data.get("password") or ""

        ok, result = user_store.login(username, password)
        if not ok:
            self._send_json({"ok": False, "error": result}, 401)
            return
        token = auth_session.issue(result["username"])
        self._send_json({
            "ok": True,
            "token": token,
            "user": result,
        })

    def _handle_logout(self):
        token = self._get_bearer_token()
        auth_session.revoke(token)
        self._send_json({"ok": True})

    def _handle_me(self):
        token = self._get_bearer_token()
        username = auth_session.get_user(token)
        if not username:
            self._send_json({"ok": False, "error": "未登录"}, 401)
            return
        user = user_store.get_user(username)
        if not user:
            self._send_json({"ok": False, "error": "用户不存在"}, 401)
            return
        self._send_json({
            "ok": True,
            "user": {
                "username": user["username"],
                "phone": user.get("phone", ""),
                "created_at": user.get("created_at", ""),
            },
        })

    def _handle_update_username(self):
        username = self._require_user()
        if username is None:
            return
        data = self._read_json()
        if data is None:
            return
        new_username = (data.get("username") or "").strip()
        password = data.get("password") or ""
        ok, result = user_store.update_username(username, new_username,
                                                password)
        if not ok:
            self._send_json({"ok": False, "error": result}, 400)
            return
        # 同步会话令牌与收藏/历史数据
        auth_session.update_username(username, result["username"])
        fav_store.rename_user(username, result["username"])
        history_store.rename_user(username, result["username"])
        self._send_json({"ok": True, "user": result})

    def _handle_change_password(self):
        username = self._require_user()
        if username is None:
            return
        data = self._read_json()
        if data is None:
            return
        old_password = data.get("old_password") or ""
        new_password = data.get("new_password") or ""
        ok, result = user_store.change_password(username, old_password,
                                                new_password)
        if not ok:
            self._send_json({"ok": False, "error": result}, 400)
            return
        self._send_json({"ok": True})

    def _handle_preferences(self):
        """保存/更新用户音乐偏好（POST）或读取（GET）"""
        username = self._require_user()
        if username is None:
            return
        if self.command == "POST":
            data = self._read_json()
            if data is None:
                return
            # 允许字段白名单；值为 None 的字段直接丢弃，避免 null 污染偏好库
            allowed = {"language", "instrumental", "genres", "energy"}
            prefs = {k: data[k] for k in allowed
                     if k in data and data[k] is not None}
            user_store.set_preferences(username, prefs)
            self._send_json({"ok": True, "preferences": prefs})
        else:  # GET
            prefs = user_store.get_preferences(username)
            self._send_json({"ok": True, "preferences": prefs})

    def _handle_fav_add(self):
        username = self._require_user()
        if username is None:
            return
        data = self._read_json()
        if data is None:
            return
        song = data.get("song")
        if not isinstance(song, dict) or not song:
            self._send_json({"ok": False, "error": "缺少歌曲数据"}, 400)
            return
        ok, result = fav_store.add(username, song)
        if not ok:
            self._send_json({"ok": False, "error": result}, 400)
            return
        self._send_json({
            "ok": True,
            "fav_key": result,
            "count": len(fav_store.list_favorites(username)),
        })

    def _handle_fav_remove(self):
        username = self._require_user()
        if username is None:
            return
        data = self._read_json()
        if data is None:
            return
        fav_key = (data.get("fav_key") or "").strip()
        if not fav_key:
            self._send_json({"ok": False, "error": "缺少收藏键"}, 400)
            return
        ok, result = fav_store.remove(username, fav_key)
        if not ok:
            self._send_json({"ok": False, "error": result}, 400)
            return
        self._send_json({
            "ok": True,
            "count": len(fav_store.list_favorites(username)),
        })

    def _handle_fav_list(self):
        username = self._require_user()
        if username is None:
            return
        favorites = fav_store.list_favorites(username)
        self._send_json({"ok": True, "favorites": favorites})

    def _handle_history_add(self):
        username = self._require_user()
        if username is None:
            return
        data = self._read_json()
        if data is None:
            return
        query = (data.get("query") or "").strip()
        task_type = (data.get("task_type") or "").strip()
        songs = data.get("songs") or []
        reply = data.get("reply") or ""
        if not query:
            self._send_json({"ok": False, "error": "缺少搜索内容"}, 400)
            return
        history_store.add(username, query, task_type, songs, reply)
        self._send_json({"ok": True})

    def _handle_history_list(self):
        username = self._require_user()
        if username is None:
            return
        records = history_store.list(username)
        self._send_json({"ok": True, "history": records})

    def _read_json(self):
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length)
        try:
            return json.loads(body)
        except json.JSONDecodeError:
            self._send_json({"error": "Invalid JSON"}, 400)
            return None

    def _handle_music_db(self):
        """返回本地音乐数据库（前端首次加载后缓存）"""
        body = recommender.local_db.raw_json_bytes
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "public, max-age=3600")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def _handle_event_keywords(self):
        """返回事件关键词配置（前后端共享）"""
        import os as _os
        backend_dir = _os.path.dirname(_os.path.abspath(__file__))
        cfg_path = _os.path.join(backend_dir, "..", "music_database",
                                 "event_keywords.json")
        cfg_path = _os.path.normpath(cfg_path)
        try:
            with open(cfg_path, "rb") as f:
                body = f.read()
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "public, max-age=3600")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(body)
        except FileNotFoundError:
            self._send_json({"error": "event_keywords.json not found"}, 404)

    def _handle_preview(self):
        """站内 30 秒试听：返回音源方提供的试听直链（到期自动失效）

        先取 Apple 官方 30 秒试听片段（免密钥、覆盖广），失败再回退 QQ 音乐。
        原唱优先；找不到原唱时回退他人的翻唱版本，并在响应里带上 match 与
        实际演唱者，让前端能明确标注「试听的是谁的翻唱」。
        只转发直链，不代理音频流——音频始终由音源方 CDN 提供，
        服务器不下载、不缓存、不再分发音频文件。
        """
        query = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)

        def _first(name):
            return (query.get(name) or [""])[0].strip()

        mid, title, artist = _first("mid"), _first("title"), _first("artist")
        genre = _first("genre")
        try:
            duration = float(_first("duration") or 0)
        except ValueError:
            duration = 0.0
        if not mid and not title:
            self._send_json({"ok": False, "url": "", "error": "缺少 songmid 或歌曲信息"}, 400)
            return
        info = resolve_preview(mid, title, artist, duration, genre)
        if not info or not info.get("url"):
            if info.get("interface_error"):
                # 音源接口限流/异常：与「歌曲本身没有试听」区分开，提示可重试
                self._send_json({"ok": False, "url": "", "retry": True,
                                 "error": "音源接口暂时不可用，请稍后重试"}, 503)
                return
            # 无资源：返回空链接，前端降级提示
            self._send_json({"ok": False, "url": "", "error": "该歌曲暂时无法试听"}, 404)
            return
        payload = {"ok": True, "url": info["url"], "expires_in": 21600,
                   "source": info.get("source", ""),
                   "match": info.get("match") or "original"}
        # 音源方曲目页 + 实际播放信息：前端据此给出商店入口与「谁的翻唱」标注
        if info.get("store_url"):
            payload["store_url"] = info["store_url"]
        if payload["match"] != "original":
            payload["preview_artist"] = info.get("preview_artist", "")
            payload["preview_title"] = info.get("preview_title", "")
            payload["preview_album"] = info.get("preview_album", "")
        self._send_json(payload)

    def _handle_chat(self):
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length)
        try:
            data = json.loads(body)
        except json.JSONDecodeError:
            self._send_json({"error": "Invalid JSON"}, 400)
            return

        message = data.get("message", "").strip()
        if not message:
            self._send_json({"error": "Message required"}, 400)
            return

        raw = llm.analyze_user_state(message)

        # LLM 可能对任意字段返回 null（键存在值 None，.get 的默认值不生效），
        # 统一净化为默认值，杜绝 None 流入策略/推荐层引发 TypeError
        for _f in ("task_type", "task_detail", "task_demand", "emotion",
                   "emotion_detail", "regulation_goal"):
            if raw.get(_f) is None:
                raw[_f] = ""
        if raw.get("emotion_intensity") is None:
            raw["emotion_intensity"] = 5
        elif not isinstance(raw["emotion_intensity"], int):
            try:
                raw["emotion_intensity"] = int(raw["emotion_intensity"])
            except (TypeError, ValueError):
                raw["emotion_intensity"] = 5
        if raw.get("need_regulation") is None:
            raw["need_regulation"] = False
        if raw.get("language_preference") is None:
            raw["language_preference"] = "no_preference"

        # 读用户偏好（已登录用户），合并进分析结果
        prefs = {}
        token = self._get_bearer_token()
        username = auth_session.get_user(token) if token else None
        if username:
            prefs = user_store.get_preferences(username) or {}
        # 净化：过滤 None 值（历史问卷可能存入 null，会污染下游判定）
        prefs = {k: v for k, v in prefs.items() if v is not None}

        # 语言偏好：LLM 显式指定 > 用户设置的默认偏好
        llm_lang = raw.get("language_preference", "no_preference")
        # 用户本轮消息里显式点名语种（中文歌/英文歌/日语歌…）→ 只推该语种人声歌，
        # 纯音乐不混入；仅问卷默认偏好时，纯音乐仍可照常推荐
        lang_explicit = llm_lang in LANG_GROUPS
        lang_pref = llm_lang
        if lang_pref == "no_preference" and prefs.get("language"):
            lang_pref = prefs["language"]  # 用户没说但有默认偏好时启用

        analysis = Analysis(
            task_type=raw.get("task_type", ""),
            task_detail=raw.get("task_detail", ""),
            task_demand=raw.get("task_demand", ""),
            emotion=raw.get("emotion", ""),
            emotion_detail=raw.get("emotion_detail", ""),
            emotion_intensity=raw.get("emotion_intensity", 5),
            emotion_source=raw.get("emotion_source", ""),
            need_regulation=raw.get("need_regulation", False),
            regulation_goal=raw.get("regulation_goal", ""),
            language_preference=lang_pref,
            user_preferences=prefs,
        )

        strategy = strategy_gen.generate(analysis)
        songs = recommender.recommend(strategy, task_type=analysis.task_type,
                                       user_message=message,
                                       language_preference=lang_pref,
                                       language_explicit=lang_explicit,
                                       user_preferences=prefs)
        reply = generate_reply(analysis, strategy, songs)

        self._log_chat(message, raw, analysis, songs)

        self._send_json({
            "reply": reply,
            "analysis": analysis.to_dict(),
            "strategy": strategy.to_dict(),
            "songs": songs,
        })

    def _log_chat(self, message: str, raw: dict, analysis: Analysis, songs: list):
        """对话日志（JSONL）：积累真实语料，供复核 bad case / 将来微调用"""
        try:
            record = {
                "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
                "message": message,
                "llm_mode": getattr(llm, "last_mode", "unknown"),
                "analysis": analysis.to_dict(),
                "raw_task_detail": raw.get("task_detail", ""),
                "songs": [f"{s.get('title', '')} - {s.get('artist', '')}"
                          for s in songs[:8]],
            }
            with open(os.path.join(BACKEND_DIR, "chat_logs.jsonl"), "a",
                      encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
        except Exception as e:
            print(f"[ChatLog] 日志写入失败（不影响主流程）: {e}")

    def _handle_song_detail(self):
        """查询 QQ 音乐真实时长 + 推断乐器类型"""
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length)
        try:
            data = json.loads(body)
        except json.JSONDecodeError:
            self._send_json({"error": "Invalid JSON"}, 400)
            return

        title = (data.get("title") or "").strip()
        artist = (data.get("artist") or "").strip()
        genre = (data.get("genre") or "").strip()
        source = data.get("source", "")
        current_duration = data.get("duration_sec", 0)

        result = {
            "duration_sec": int(current_duration or 0),
            "instrument_type": infer_instrument_type(genre),
        }

        # 静态库歌曲需要查询 QQ 音乐获取真实时长
        if source != "qqmusic" and title:
            try:
                qm = get_qqmusic()
                song = qm.search_song_detail(title, artist)
                if song and getattr(song, "duration_sec", 0) > 0:
                    result["duration_sec"] = int(song.duration_sec)
                    result["cover_url"] = song.cover_url
                    result["external_url"] = song.external_url
                    result["from_qqmusic"] = True
            except Exception as e:
                print(f"[SongDetail] QQ query failed: {e}")

        self._send_json(result)

    def _handle_deploy(self):
        """远程更新：接收 zip 部署包，解压覆盖后自动重启服务（需 X-Deploy-Token）"""
        token = self.headers.get("X-Deploy-Token", "")
        token_file = os.path.join(BACKEND_DIR, "deploy_token.txt")
        try:
            with open(token_file, "r", encoding="utf-8") as f:
                expected = f.read().strip()
        except OSError:
            expected = ""
        if not expected or not token or token != expected:
            self._send_json({"ok": False, "error": "forbidden"}, 403)
            return

        length = int(self.headers.get("Content-Length", 0))
        if length <= 0 or length > 50 * 1024 * 1024:
            self._send_json({"ok": False, "error": "bad zip size"}, 400)
            return
        body = self.rfile.read(length)

        # 备份服务器上的用户数据（避免被打包里的旧数据覆盖）
        data_names = ["users.json", "favorites.json", "history.json"]
        backup_dir = "/tmp/melomind_data_backup"
        os.makedirs(backup_dir, exist_ok=True)
        for name in data_names:
            src = os.path.join(BACKEND_DIR, name)
            if os.path.exists(src):
                shutil.copy2(src, os.path.join(backup_dir, name))

        zip_path = "/tmp/melomind_deploy.zip"
        with open(zip_path, "wb") as f:
            f.write(body)
        r = subprocess.run(["unzip", "-o", zip_path, "-d", "/opt/"],
                           capture_output=True, text=True)
        if r.returncode != 0:
            self._send_json({"ok": False,
                             "error": (r.stderr or "unzip failed")[-300:]}, 500)
            return
        subprocess.run(["chmod", "-R", "755", "/opt/melomind"])

        # 恢复用户数据
        for name in data_names:
            b = os.path.join(backup_dir, name)
            dst = os.path.join(BACKEND_DIR, name)
            if os.path.exists(b):
                shutil.copy2(b, dst)

        # 部署包不再携带用户数据；缺失时初始化默认文件
        defaults = {
            "users.json": '{"users":[]}',
            "favorites.json": '{}',
            "history.json": '{}',
        }
        for name, content in defaults.items():
            p = os.path.join(BACKEND_DIR, name)
            if not os.path.exists(p):
                with open(p, "w", encoding="utf-8") as f:
                    f.write(content)

        self._send_json({"ok": True, "msg": "解压完成，服务重启中"})
        print("[Deploy] 新版本已部署，服务重启中...", flush=True)

        def _restart():
            time.sleep(0.5)
            subprocess.Popen(["systemctl", "restart", "melomind"],
                             start_new_session=True)
        threading.Timer(0.2, _restart).start()

    def _send_json(self, data, status=200):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.end_headers()

    def log_message(self, format, *args):
        print(f"[{self.log_date_time_string()}] {args[0]}", flush=True)


def generate_reply(analysis: Analysis, strategy: MusicStrategy,
                   songs: list) -> str:
    task_names = {"coding":"编程","writing":"写作","study":"学习",
                  "workout":"运动","commute":"通勤","relax":"放松",
                  "creative":"创意设计","general":"当前任务"}

    # 细粒度任务状态：如「编程·调试排错」
    tc = task_names.get(analysis.task_type.split("-")[0], analysis.task_type)
    if analysis.task_detail and analysis.task_detail != tc:
        tc = f"{tc}·{analysis.task_detail}"
    # 情绪只取一个词（如"专注"），不把推断过程与细分说明写进回复
    ec = emotion_word(analysis.emotion)

    parts = [f"我理解你正在**{tc}**，情绪偏**{ec}**。"]

    if analysis.need_regulation:
        if analysis.regulation_goal:
            parts.append(f"调节目标：{analysis.regulation_goal}。")
        parts.append(f"这个状态可以通过音乐调节——{strategy.explanation}")
    else:
        parts.append(f"状态不错！{strategy.explanation}")

    source = songs[0].get("source", "") if songs else ""
    source_note = "（来自QQ音乐实时搜索）" if source == "qqmusic" else ""
    parts.append(f"\n为你精选 {len(songs)} 首歌{source_note}，{strategy.notes}。")
    parts.append(f"\n💡 **解决策略**：{strategy.session_advice}")

    song_preview = "\n".join(
        f"  {i+1}. {s['title']} — {s['artist']}"
        for i, s in enumerate(songs[:5])
    )
    parts.append(f"\n📋 推荐歌单（点击卡片即可试听 30 秒）：\n{song_preview}")

    return "".join(parts)


def main():
    port = int(os.environ.get("PORT", "8000"))
    # 多线程：LLM 分析耗时数秒，单线程会阻塞后续所有请求导致排队超时
    server = ThreadingHTTPServer(("0.0.0.0", port), MeloMindHandler)
    print(f"\n  MeloMind 2.0  running at http://localhost:{port}")
    print(f"  音乐推荐 | 本地曲库 + QQ音乐 | 站内 30 秒试听\n")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down...")
        server.shutdown()


if __name__ == "__main__":
    main()
