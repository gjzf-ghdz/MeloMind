"""
爬取QQ音乐榜单歌曲 - 补充音乐数据库

运行方式：python supplement_toplist.py
输出：在现有 music_database.json 基础上追加榜单歌曲

支持的榜单（topid）：
  4 = 流行指数榜
  3 = 热歌榜
  26 = 新歌榜
  27 = 原创榜
"""
import json
import os
import sys
import time
import random
import urllib.request
import urllib.parse

# 确保能导入 backend 模块
_BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend"))
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if _SCRIPT_DIR not in sys.path:
    sys.path.insert(0, _SCRIPT_DIR)

from qqmusic_source import QQMusicSource
from models import Song, infer_instrument_type
from build_music_db import enrich_song_metadata


# QQ音乐榜单接口
TOPLIST_URL = "https://c.y.qq.com/v8/fcg-bin/fcg_v8_toplist_cp.fcg"

# 榜单 ID 映射
TOPLIST_MAP = {
    4: "流行指数榜",
    3: "热歌榜",
    26: "新歌榜",
    27: "原创榜",
}


def fetch_toplist(topid: int = 4, limit: int = 100) -> list:
    """获取QQ音乐榜单歌曲列表"""
    params = {
        "topid": str(topid),
        "format": "json",
        "type": "top",
        "platform": "1",
        "g_tk": "5381",
        "n": str(limit),
    }
    query = urllib.parse.urlencode(params)
    url = f"{TOPLIST_URL}?{query}"

    req = urllib.request.Request(url)
    req.add_header("User-Agent",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36")
    req.add_header("Referer", "https://y.qq.com/n/ryqq/toplist/4")
    req.add_header("Accept", "application/json, text/plain, */*")

    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            raw = resp.read().decode("utf-8")
        # QQ音乐可能返回带 callback 的 JSONP，需清理
        if raw.startswith("callback"):
            raw = raw[raw.index("(") + 1: raw.rindex(")")]
        data = json.loads(raw)
        return _parse_toplist(data, topid)
    except Exception as e:
        print(f"[Toplist] 获取榜单失败: {e}")
        # 回退方案：尝试 musicu.fcg 接口
        return fetch_toplist_fallback(topid, limit)


def fetch_toplist_fallback(topid: int = 4, limit: int = 100) -> list:
    """备用接口：musicu.fcg"""
    url = ("https://u.y.qq.com/cgi-bin/musicu.fcg?"
           "g_tk=5381&format=json&inCharset=utf8&outCharset=utf-8")
    data_payload = {
        "comm": {"g_tk": 5381, "uin": "", "format": "json",
                 "inCharset": "utf-8", "outCharset": "utf-8", "notice": 0},
        "toplist": {"module": "musicToplist.ToplistInfoServer",
                    "method": "GetDetail",
                    "param": {"topid": topid, "offset": 0, "num": limit}},
    }
    body = json.dumps(data_payload).encode("utf-8")

    req = urllib.request.Request(url, data=body, method="POST")
    req.add_header("User-Agent",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36")
    req.add_header("Referer", "https://y.qq.com/n/ryqq/toplist/4")
    req.add_header("Content-Type", "application/json")

    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            raw = resp.read().decode("utf-8")
        data = json.loads(raw)
        return _parse_toplist_fcg(data)
    except Exception as e:
        print(f"[Toplist] 备用接口也失败: {e}")
        return []


def _parse_toplist(data: dict, topid: int) -> list:
    """解析榜单接口返回的 songmid 列表"""
    songs = []
    songlist = data.get("songlist", []) or data.get("data", {}).get("songlist", [])
    for item in songlist:
        item_data = item.get("data", item) if isinstance(item, dict) else {}
        songmid = item_data.get("songmid") or item_data.get("mid")
        if not songmid:
            continue
        title = item_data.get("songname") or item_data.get("name", "")
        singer = item_data.get("singer", [{}])
        artist = singer[0].get("name", "") if singer else ""
        album = item_data.get("albumname", "") or item_data.get("album", {}).get("name", "")
        interval = item_data.get("interval", 240)
        songs.append({
            "songmid": songmid,
            "title": title,
            "artist": artist,
            "album": album,
            "interval": interval,
        })
    return songs


def _parse_toplist_fcg(data: dict) -> list:
    """解析 musicu.fcg 接口返回"""
    songs = []
    info = data.get("toplist", {}).get("data", {})
    song_list = info.get("songInfoList", []) or info.get("songList", [])
    for item in song_list:
        songmid = item.get("songmid") or item.get("mid")
        if not songmid:
            continue
        title = item.get("songname") or item.get("name", "")
        singer = item.get("singer", [{}])
        artist = singer[0].get("name", "") if singer and isinstance(singer, list) else ""
        album = item.get("albumname", "") or item.get("album", {}).get("name", "")
        interval = item.get("interval", 240)
        songs.append({
            "songmid": songmid,
            "title": title,
            "artist": artist,
            "album": album,
            "interval": interval,
        })
    return songs


def search_song_by_info(qq: QQMusicSource, title: str, artist: str) -> Song:
    """通过歌曲信息搜索获取完整 Song 对象"""
    keyword = f"{title} {artist}".strip()
    results = qq.search(keyword, limit=5)
    # 优先匹配标题+歌手
    for s in results:
        if title and title in s.title:
            return s
    return results[0] if results else None


def supplement(db_path: str, topid: int = 4, limit: int = 100):
    """补充爬取榜单歌曲"""
    # 加载现有数据库
    if not os.path.exists(db_path):
        print(f"数据库不存在: {db_path}")
        return
    with open(db_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    existing_songs = {s["id"]: s for s in data.get("songs", []) if "id" in s}
    print(f"现有数据库: {len(existing_songs)} 首歌曲")
    print(f"目标榜单: {TOPLIST_MAP.get(topid, '未知榜单')} (topid={topid})")
    print("=" * 60)

    # 1. 获取榜单歌曲列表
    print("正在获取榜单...")
    toplist_songs = fetch_toplist(topid, limit)
    print(f"榜单共 {len(toplist_songs)} 首歌曲")

    if not toplist_songs:
        print("榜单获取失败，尝试备用方案：用榜单名称搜索")
        qq = QQMusicSource()
        keyword = f"{TOPLIST_MAP.get(topid, '流行')} 榜单"
        songs = qq.search(keyword, limit=limit)
        new_count = 0
        for song in songs:
            if song.id and song.id not in existing_songs:
                enriched = enrich_song_metadata(song, keyword)
                existing_songs[song.id] = enriched
                new_count += 1
        print(f"通过搜索补充: +{new_count} 首")
        _save(data, existing_songs, db_path)
        return

    # 2. 对每首榜单歌曲，搜索获取完整信息
    print("\n开始爬取榜单歌曲详情...")
    qq = QQMusicSource()
    new_count = 0
    dup_count = 0
    fail_count = 0

    for i, ts in enumerate(toplist_songs):
        title = ts.get("title", "")
        artist = ts.get("artist", "")
        songmid = ts.get("songmid", "")
        print(f"[{i+1}/{len(toplist_songs)}] {title} - {artist} ... ", end="", flush=True)

        # 优先用 songmid 搜索
        try:
            songs = qq.search(f"{title} {artist}".strip(), limit=5)
            matched = None
            for s in songs:
                if songmid and songmid == s.id:
                    matched = s
                    break
            if not matched and songs:
                # 标题匹配
                for s in songs:
                    if title and title in s.title:
                        matched = s
                        break
            if not matched and songs:
                matched = songs[0]

            if matched:
                if matched.id in existing_songs:
                    dup_count += 1
                    print("重复")
                else:
                    enriched = enrich_song_metadata(matched, f"{TOPLIST_MAP.get(topid, '流行')}榜单")
                    existing_songs[matched.id] = enriched
                    new_count += 1
                    print(f"新增 (能量={enriched['energy']} 风格={enriched['genre']})")
            else:
                fail_count += 1
                print("未找到")
        except Exception as e:
            fail_count += 1
            print(f"失败: {e}")

        # 节流
        time.sleep(1.0 + random.uniform(0.3, 0.6))

    print("\n" + "=" * 60)
    print(f"爬取完成！")
    print(f"  新增歌曲: {new_count} 首")
    print(f"  重复跳过: {dup_count} 首")
    print(f"  失败: {fail_count} 首")
    print(f"  数据库总量: {len(existing_songs)} 首")

    _save(data, existing_songs, db_path)


def _save(data: dict, songs: dict, db_path: str):
    """保存数据库"""
    data["songs"] = list(songs.values())
    data["total_songs"] = len(songs)
    data["version"] = 2
    data["source"] = "QQ Music (y.qq.com)"
    data["supplemented_toplist"] = True
    with open(db_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"\n数据库已保存: {db_path}")


def main():
    import argparse
    parser = argparse.ArgumentParser(description="爬取QQ音乐榜单补充数据库")
    parser.add_argument("--topid", "-t", type=int, default=4,
                        help="榜单ID (4=流行指数榜 3=热歌榜 26=新歌榜 27=原创榜)")
    parser.add_argument("--output", "-o", default=None, help="数据库文件路径")
    parser.add_argument("--limit", "-l", type=int, default=100, help="爬取数量")
    parser.add_argument("--list", action="store_true", help="列出支持的榜单")
    args = parser.parse_args()

    if args.list:
        print("支持的QQ音乐榜单：")
        for tid, name in TOPLIST_MAP.items():
            print(f"  topid={tid:<3} {name}")
        return

    db_path = args.output or os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "music_database.json")
    supplement(db_path, topid=args.topid, limit=args.limit)


if __name__ == "__main__":
    main()
