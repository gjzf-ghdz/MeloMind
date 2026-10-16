"""
全面爬取 QQ 音乐补充数据库 — 覆盖客户端所有核心内容
包括：所有官方榜单 + 流派/国别歌单 + 热门歌手 + 核心曲风流派

运行方式：python crawl_qqmusic_full.py --per 50
输出：合并到 music_database.json
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

QQ = QQMusicSource()

# ============================================================
# 1. QQ音乐官方榜单 (topid) — 桌面客户端完整榜单
# ============================================================
TOPLISTS = [
    # 国内核心榜单
    (4, "流行指数榜"),
    (3, "热歌榜"),
    (26, "新歌榜"),
    (27, "原创榜"),
    (62, "飙升榜"),
    (5, "内地榜"),
    (6, "港台榜"),
    (72, "华语金曲榜"),
    (202, "腾讯音乐人原创榜"),
    (68, "网络歌曲榜"),
    (106, "说唱榜"),
    (70, "电音榜"),
    (69, "DJ舞曲榜"),
    (65, "民谣榜"),
    (108, "古典榜"),
    (67, "影视金曲榜"),
    (80, "动漫音乐榜"),
    (75, "游戏音乐榜"),
    (82, "KTV点唱榜"),
    # 国际/全球榜单
    (116, "欧美榜"),
    (115, "日本榜"),
    (117, "韩国榜"),
    (123, "美国公告牌Billboard"),
    (125, "英国UK排行"),
    (127, "iTunes榜"),
    (129, "Spotify全球榜"),
    (131, "KKBOX台湾榜"),
    (133, "日本公信榜Oricon"),
    (135, "MelOn韩国榜"),
]

# ============================================================
# 2. 流派/国别歌单搜索关键词
# ============================================================
GENRE_PLAYLIST_KW = [
    # 华语
    "华语流行", "粤语流行", "台语流行", "华语民谣", "校园民谣",
    "华语摇滚", "华语说唱", "华语R&B", "City Pop",
    "古风", "国风流行", "中国风",
    # 西洋
    "欧美流行", "欧美摇滚", "欧美说唱", "欧美R&B",
    "Pop", "Rock", "Hip Hop", "R&B",
    "爵士", "Vocal Jazz", " Bebop", "放克 Funk",
    "蓝调 Blues", "灵魂乐 Soul", "Country 乡村音乐",
    "雷鬼 Reggae", "迪斯科 Disco",
    "金属 Metal", "死亡金属", "黑金属", "工业金属", "硬核",
    "朋克 Punk", "后摇 Post-Rock", "迷幻摇滚", "独立摇滚", "车库摇滚",
    "Lo-Fi", "蒸汽波 Vaporwave", "合成器流行 Synthpop",
    "新世纪音乐 New Age", "氛围音乐 Ambient", "世界音乐 World Music",
    "实验音乐 Experimental", "凯尔特 Celtic", "弗拉门戈 Flamenco",
    "Bossa Nova", "拉丁音乐 Latin",
    # 日韩
    "K-POP", "韩语流行", "J-POP", "日语流行", "日语摇滚",
    "日本动漫音乐", "动漫OST", "游戏BGM",
    "City Pop 日本", "J-Rock", "Jazz 日本",
    # 古典
    "古典音乐 交响", "巴洛克音乐", "浪漫主义古典",
    "钢琴协奏曲", "小提琴协奏曲", "弦乐四重奏",
    "巴赫 古典", "莫扎特 古典", "贝多芬 交响",
    "肖邦 钢琴", "李斯特 钢琴", "舒伯特 艺术歌曲",
    # 民乐/传统
    "传统民乐 古筝", "古琴 音乐", "二胡 民乐", "琵琶 独奏",
    "笛子 独奏", "戏曲 京剧", "民乐合奏", "少数民族音乐",
    # 场景
    "电影原声带 OST", "电视剧配乐 OST", "音乐剧 选段",
    "儿歌 童谣", "胎教音乐", "轻音乐 纯音乐",
    "阿卡贝拉 Acapella", "合唱 唱诗班 Gregorian", "Beatbox",
    "跑步运动 燃曲", "健身 健美 音乐", "学习 专注力",
    "睡眠 放松 催眠", "冥想 瑜伽", "咖啡馆 背景音乐",
    "驾驶 公路音乐", "派对 嗨曲", "婚礼 浪漫音乐",
    "KTV 必点金曲", "毕业歌 校园", "怀旧金曲 80年代",
    "怀旧金曲 90年代", "华语金曲 2000年代",
]

# ============================================================
# 3. 热门华语歌手（补充现有数据库中不足的歌手覆盖）
# ============================================================
TOP_SINGERS = [
    # 男歌手
    "周杰伦", "陈奕迅", "林俊杰", "薛之谦", "李荣浩",
    "毛不易", "许嵩", "张杰", "李健", "朴树",
    "王力宏", "陶喆", "方大同", "张学友", "刘德华",
    "谭咏麟", "黄家驹", "张国荣", "罗大佑", "李宗盛",
    "林宥嘉", "杨宗纬", "萧敬腾", "黄子韬", "吴亦凡",
    "张艺兴", "鹿晗", "华晨宇", "邓紫棋", "周深",
    # 女歌手
    "王菲", "张惠妹", "蔡依林", "孙燕姿", "邓紫棋",
    "梁静茹", "刘若英", "莫文蔚", "那英", "田馥甄",
    "陈绮贞", "张碧晨", "李宇春", "张靓颖", "萨顶顶",
    "邓丽君", "徐佳莹", "杨丞琳", "蔡健雅", "陈粒",
    # 组合/乐队
    "五月天", "SHE", "凤凰传奇", "Beyond", "苏打绿",
    "TFBOYS", "时代少年团", "五月天", "羽泉", "动力火车",
    "逃跑计划", "万能青年旅店", "痛仰乐队", "五条人", "新裤子",
    # 欧美歌手
    "Taylor Swift", "Ed Sheeran", "Adele", "Bruno Mars",
    "The Weeknd", "Drake", "Billie Eilish", "Dua Lipa",
    "Coldplay", "Imagine Dragons", "Maroon 5", "Post Malone",
    "Justin Bieber", "Ariana Grande", "Shakira", "Rihanna",
    "Eminem", "Kanye West", "Kendrick Lamar", "Jay Z",
    "Michael Jackson", "Queen", "The Beatles", "Elvis Presley",
    # 日韩歌手
    "BTS", "BLACKPINK", "TWICE", "IU", "BIGBANG",
    "EXO", "SEVENTEEN", "NewJeans", "LE SSERAFIM", "aespa",
    "米津玄師", "YOASOBI", "宇多田光", "椎名林檎", "RADWIMPS",
    "ONE OK ROCK", "星野源", "Yonezu Kenshi", "LiSA",
    # 古典/演奏家
    "李云迪", "郎朗", "马友友", "盛中国",
    "Bach", "Mozart", "Beethoven", "Chopin", "Tchaikovsky",
    "Debussy", "Ravel", "Stravinsky", "Schubert", "Brahms",
]

# ============================================================
# 辅助函数
# ============================================================
def load_db(db_path):
    if not os.path.exists(db_path):
        return {"version": 2, "source": "QQ Music", "songs": [], "total_songs": 0}
    with open(db_path, "r", encoding="utf-8") as f:
        return json.load(f)

def save_db(db, db_path):
    db["songs"] = list(db["_songs_dict"].values())
    db["total_songs"] = len(db["songs"])
    db["version"] = 2
    db["source"] = "QQ Music (y.qq.com)"
    if "_songs_dict" in db:
        del db["_songs_dict"]
    with open(db_path, "w", encoding="utf-8") as f:
        json.dump(db, f, ensure_ascii=False, indent=2)

def fetch_toplist(topid, limit=100):
    """获取榜单歌曲mid列表（走榜单接口）"""
    url = ("https://u.y.qq.com/cgi-bin/musicu.fcg?"
           "g_tk=5381&format=json&inCharset=utf8&outCharset=utf-8")
    payload = {
        "comm": {"g_tk": 5381, "uin": "", "format": "json",
                 "inCharset": "utf-8", "outCharset": "utf-8", "notice": 0},
        "toplist": {"module": "musicToplist.ToplistInfoServer",
                    "method": "GetDetail",
                    "param": {"topid": topid, "offset": 0, "num": limit}},
    }
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=body, method="POST")
    req.add_header("User-Agent",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36")
    req.add_header("Referer", "https://y.qq.com/")
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        info = data.get("toplist", {}).get("data", {})
        slist = info.get("songInfoList", []) or info.get("songList", [])
        return [(s.get("songmid") or s.get("mid", ""),
                 s.get("songname") or s.get("name", ""),
                 (s.get("singer", [{}]) or [{}])[0].get("name", ""),
                 s.get("interval", 240))
                for s in slist]
    except Exception as e:
        print(f"  [榜接口失败] {e}")
        return []

def search_and_enrich(kw, limit=50):
    """搜索关键词并补充元数据"""
    try:
        songs = QQ.search(kw, limit=limit)
    except Exception as e:
        print(f"  [搜索失败] {kw}: {e}")
        return []
    result = []
    for s in songs:
        if not s.id:
            continue
        enriched = enrich_song_metadata(s, kw)
        result.append(enriched)
    return result

def merge_songs(db, new_songs):
    """合并歌曲到数据库（按songmid去重）"""
    if "_songs_dict" not in db:
        db["_songs_dict"] = {s["id"]: s for s in db.get("songs", []) if s.get("id")}
    before = len(db["_songs_dict"])
    for s in new_songs:
        if s["id"] not in db["_songs_dict"]:
            db["_songs_dict"][s["id"]] = s
    added = len(db["_songs_dict"]) - before
    return added

# ============================================================
# 主流程
# ============================================================
def main():
    import argparse
    parser = argparse.ArgumentParser(description="全面爬取QQ音乐补充数据库")
    parser.add_argument("--per", type=int, default=50,
                        help="每个关键词/榜单搜索数量")
    parser.add_argument("--skip-tops", action="store_true",
                        help="跳过榜单爬取")
    parser.add_argument("--skip-genres", action="store_true",
                        help="跳过流派歌单爬取")
    parser.add_argument("--skip-singers", action="store_true",
                        help="跳过歌手爬取")
    parser.add_argument("--max-tops", type=int, default=None,
                        help="最多处理多少个榜单")
    parser.add_argument("--max-genres", type=int, default=None)
    parser.add_argument("--max-singers", type=int, default=None)
    parser.add_argument("--output", default=None)
    parser.add_argument("--list", action="store_true", help="仅列出关键词")
    args = parser.parse_args()

    db_path = args.output or os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "music_database.json")

    if args.list:
        print(f"榜单 ({len(TOPLISTS)}):")
        for tid, name in TOPLISTS:
            print(f"  topid={tid:<4} {name}")
        print(f"\n流派关键词 ({len(GENRE_PLAYLIST_KW)}):")
        for i, kw in enumerate(GENRE_PLAYLIST_KW[:30], 1):
            print(f"  {i:>2}. {kw}")
        if len(GENRE_PLAYLIST_KW) > 30:
            print(f"  ... 共 {len(GENRE_PLAYLIST_KW)} 个")
        print(f"\n热门歌手 ({len(TOP_SINGERS)}):")
        for i, s in enumerate(TOP_SINGERS[:30], 1):
            print(f"  {i:>2}. {s}")
        if len(TOP_SINGERS) > 30:
            print(f"  ... 共 {len(TOP_SINGERS)} 个")
        return

    db = load_db(db_path)
    db["_songs_dict"] = {s["id"]: s for s in db.get("songs", []) if s.get("id")}
    initial_total = len(db["_songs_dict"])
    print(f"初始数据库: {initial_total} 首")
    print(f"每关键词/榜单搜索: {args.per} 首")
    print("=" * 60)

    total_added = 0

    # ---- 阶段 1: 官方榜单 ----
    if not args.skip_tops:
        tops = TOPLISTS
        if args.max_tops:
            tops = tops[:args.max_tops]
        print(f"\n阶段 1/3: 爬取 {len(tops)} 个官方榜单...")
        for i, (topid, name) in enumerate(tops):
            print(f"  [{i+1}/{len(tops)}] 榜单: {name} (topid={topid})... ", end="", flush=True)
            toplist = fetch_toplist(topid, limit=args.per)
            kw_added = 0
            # 先搜榜单名称
            songs = search_and_enrich(f"{name} 榜单", limit=args.per)
            kw_added += merge_songs(db, songs)
            # 对榜单前N首用 标题+歌手 精准搜
            for songmid, title, artist, _ in toplist[:30]:
                time.sleep(0.3 + random.uniform(0.1, 0.3))
                if title and artist:
                    kw = f"{name} 榜单"
                    search_songs = search_and_enrich(f"{title} {artist}", limit=3)
                    for s in search_songs:
                        # 强制 search_keyword 为榜单名
                        s["search_keyword"] = name
                    kw_added += merge_songs(db, search_songs)
            total_added += kw_added
            print(f"+{kw_added} 首 (累计新增 {total_added})")
            time.sleep(0.5 + random.uniform(0.3, 0.6))

    # ---- 阶段 2: 流派/场景歌单 ----
    if not args.skip_genres:
        genres = GENRE_PLAYLIST_KW
        if args.max_genres:
            genres = genres[:args.max_genres]
        print(f"\n阶段 2/3: 爬取 {len(genres)} 个流派/场景关键词...")
        for i, kw in enumerate(genres):
            print(f"  [{i+1}/{len(genres)}] 流派/场景: {kw}... ", end="", flush=True)
            songs = search_and_enrich(kw, limit=args.per)
            added = merge_songs(db, songs)
            total_added += added
            print(f"+{added} 首 (累计新增 {total_added})")
            time.sleep(0.8 + random.uniform(0.3, 0.7))

    # ---- 阶段 3: 热门歌手 ----
    if not args.skip_singers:
        singers = TOP_SINGERS
        if args.max_singers:
            singers = singers[:args.max_singers]
        print(f"\n阶段 3/3: 爬取 {len(singers)} 个热门歌手...")
        for i, singer in enumerate(singers):
            print(f"  [{i+1}/{len(singers)}] 歌手: {singer}... ", end="", flush=True)
            songs = search_and_enrich(f"{singer} 热门歌曲", limit=args.per)
            for s in songs:
                if not s.get("search_keyword") or s["search_keyword"] == f"{singer} 热门歌曲":
                    s["search_keyword"] = singer  # 用人名作关键词，方便后续精确匹配
            added = merge_songs(db, songs)
            total_added += added
            print(f"+{added} 首 (累计新增 {total_added})")
            time.sleep(0.8 + random.uniform(0.3, 0.7))

    # 保存
    print(f"\n{'='*60}")
    print(f"爬取完成!")
    print(f"  初始: {initial_total} 首")
    print(f"  新增: {total_added} 首")
    print(f"  总计: {len(db['_songs_dict'])} 首")
    print(f"{'='*60}")
    save_db(db, db_path)
    print(f"数据库已保存: {db_path}")


if __name__ == "__main__":
    main()
