"""
大规模补充爬取 QQ 音乐 — 针对当前数据库缺口定向补充
重点：稀缺风格(摇滚/独立/R&B/嘻哈/爵士/民谣/极简) + 高能量歌曲 + 年代经典 + 语种热门 + OST

运行方式：
  python crawl_genres_massive.py --smoke          # 烟雾测试 10 个关键词
  python crawl_genres_massive.py --per 40         # 完整爬取，每关键词40首
  python crawl_genres_massive.py --list           # 仅列出关键词
  python crawl_genres_massive.py --only genres    # 仅爬稀缺风格
  python crawl_genres_massive.py --only energy    # 仅爬高能量
  python crawl_genres_massive.py --only era       # 仅爬年代经典
  python crawl_genres_massive.py --only lang      # 仅爬语种热门
  python crawl_genres_massive.py --only ost       # 仅爬OST
  python crawl_genres_massive.py --only singer    # 仅爬歌手深度
"""
import json
import os
import sys
import time
import random
import urllib.request
import urllib.parse
import argparse

# 修复 Windows GBK 终端编码问题，避免 print 含非 GBK 字符时崩溃
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

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
# 1. 稀缺风格专项（重点补充：摇滚/独立/R&B/嘻哈/爵士/民谣/极简/电子细分）
# ============================================================
SCARCE_GENRE_KW = [
    # ---- 摇滚（当前仅 66 首 0.4%）----
    "摇滚经典", "欧美摇滚", "华语摇滚", "英国摇滚", "美国摇滚",
    "摇滚金曲", "经典摇滚", "老摇滚", "硬摇滚 Hard Rock", "蓝调摇滚",
    "迷幻摇滚 Psychedelic", "前卫摇滚 Progressive", "车库摇滚 Garage",
    "后摇 Post-Rock", "后摇 纯音乐", "独立摇滚 Indie Rock",
    "朋克 Punk", "朋克摇滚", "流行朋克 Pop Punk", "滑板朋克",
    "金属 Metal", "重金属 Heavy Metal", "死亡金属 Death Metal",
    "黑金属 Black Metal", "工业金属 Industrial Metal", "交响金属",
    "哥特金属", "力量金属 Power Metal", "前卫金属",
    "新金属 Nu Metal", "另类摇滚 Alternative", "垃圾摇滚 Grunge",
    "日系摇滚 J-Rock", "日本摇滚", "韩国摇滚",
    # ---- 独立（当前仅 45 首 0.3%）----
    "独立音乐 Indie", "独立流行 Indie Pop", "独立民谣 Indie Folk",
    "独立电子 Indie Electronic", "独立摇滚经典", "Indie 歌手",
    "卧室流行 Bedroom Pop", "梦幻流行 Dream Pop", "自赏 Shoegaze",
    "Lo-Fi 独立", "独立乐队", "中国独立音乐", "台湾独立音乐",
    # ---- R&B（当前仅 133 首 0.8%）----
    "华语R&B", "欧美R&B", "韩语R&B", "日语R&B",
    "灵魂乐 Soul", "Neo-Soul", "当代R&B", "经典R&B",
    "方大同", "陶喆 R&B", "周杰伦 R&B", "王诗安",
    "H.E.R.", "SZA", "Frank Ocean", "Daniel Caesar",
    "The Weeknd 热门", "Bryson Tiller", "Jhené Aiko",
    # ---- 嘻哈/说唱（当前仅 168 首 1.0%）----
    "华语说唱", "中国说唱", "中文嘻哈", "粤语说唱",
    "欧美说唱", "韩语说唱 K-HipHop", "日语说唱 J-Rap",
    "Trap 嘻哈", "Drill 说唱", "Old School 说唱",
    "Boom Bap", "Mumble Rap", "Lofi Hip Hop 说唱",
    "Eminem 歌曲", "2Pac 经典", "Notorious B.I.G.",
    "Kendrick Lamar", "J. Cole", "Drake 说唱",
    "Travis Scott", "Post Malone 说唱", "Cardi B",
    "Megan Thee Stallion", "Tyler The Creator",
    "GAI", "PG One", "谢帝", "派克特", "刘柏辛",
    "Higher Brothers", "knowknow", "王以太",
    # ---- 爵士（当前仅 248 首 1.5%）----
    "爵士经典", "爵士乐", "Smooth Jazz", "爵士钢琴",
    "冷爵士 Cool Jazz", "硬波普 Hard Bop", "调式爵士 Modal Jazz",
    "Fusion 爵士", "Acid Jazz", "Free Jazz 自由爵士",
    "拉丁爵士 Latin Jazz", "爵士人声 Vocal Jazz",
    "Bossa Nova 巴萨诺瓦", "Bebop 比波普", "大乐队 Big Band",
    "摇摆乐 Swing", "新奥尔良爵士", "现代爵士",
    "Miles Davis", "John Coltrane", "Thelonious Monk",
    "Bill Evans", "Dave Brubeck", "Charlie Parker",
    "Louis Armstrong", "Ella Fitzgerald", "Norah Jones",
    "Michael Bublé", "Diana Krall", "Chet Baker",
    # ---- 民谣（当前仅 205 首 1.3%）----
    "华语民谣", "校园民谣", "城市民谣", "中国民谣",
    "美式民谣 American Folk", "英伦民谣", "凯尔特民谣",
    "民谣吉他", "民谣歌手", "民谣金曲",
    "Bob Dylan", "Joan Baez", "Simon & Garfunkel",
    "李志", "赵雷", "宋冬野", "陈粒", "花粥",
    "郝云", "万晓利", "周云蓬", "钟立风",
    "Patty Smith", "Joni Mitchell", "Leonard Cohen",
    # ---- 极简（当前仅 126 首 0.8%）----
    "极简音乐 Minimalist", "Minimal Piano", "极简钢琴",
    "Ambient Piano 氛围钢琴", "极简主义音乐",
    "Max Richter", "Ludovico Einaudi", "Yann Tiersen",
    "Michael Nyman", "Arvo Pärt", "Philip Glass",
    "Nils Frahm", "Ólafur Arnalds", "Joep Beving",
    # ---- 电子细分 ----
    "House 音乐", "Deep House", "Tech House", "Progressive House",
    "Techno 电子", "Trance 音乐", "Dubstep", "Future Bass",
    "Synthwave 合成器浪潮", "Vaporwave 蒸汽波",
    "Drum and Bass", "Breakbeat", "Garage 音乐",
    "Chillout 电子", "Trip Hop", "IDM 电子",
    "Daft Punk", "Deadmau5", "Avicii",
    "Calvin Harris", "Marshmello", "Zedd",
    "The Chemical Brothers", "Moby", "Aphex Twin",
]

# ============================================================
# 2. 高能量歌曲专项（当前仅 11.1%，需大量补充）
# ============================================================
HIGH_ENERGY_KW = [
    "燃曲", "燃歌", "热血歌曲", "激昂音乐", "励志燃曲",
    "运动燃曲", "健身嗨曲", "跑步嗨曲", "力量训练音乐",
    "派对嗨曲", "舞曲嗨曲", "夜店嗨曲", "电音嗨曲",
    "摇滚燃曲", "金属燃曲", "朋克燃曲", "说唱燃曲",
    "电竞燃曲", "游戏燃曲", "战斗音乐", "Boss战音乐",
    "动漫燃曲", "热血动漫音乐", "战斗动漫音乐",
    "胜利之歌", "冠军之歌", "夺冠音乐",
    "激昂交响", "史诗音乐", "Epic Music", "Trailer Music",
    "Two Steps From Hell", "Hans Zimmer 燃",
    "Imagine Dragons 热门", "Skillet 热门",
    "AC/DC", "Guns N Roses", "Metallica",
    "Linkin Park", "Blink-182", "Green Day",
    "Foo Fighters", "Red Hot Chili Peppers",
    "夜店电音", "DJ 燃曲", "EDM 燃曲", "Festival 音乐",
    " hardstyle", "硬核电音", "激燃BGM",
    "励志英文歌", "励志中文歌", "奋斗歌曲",
    "青春燃曲", "梦想歌曲", "拼搏音乐",
    "热血日韩", "K-Pop 燃曲", "J-Rock 燃曲",
    "拳皇音乐", "火影忍者音乐", "海贼王音乐",
    "龙珠音乐", "进击的巨人音乐", "鬼灭之刃音乐",
]

# ============================================================
# 3. 年代经典（各年代代表歌曲）
# ============================================================
ERA_CLASSIC_KW = [
    # 70s
    "70年代经典", "1970s 经典", "70年代英文歌", "70年代华语老歌",
    "ABBA", "Bee Gees", "Eagles 乐队", "Fleetwood Mac",
    "Led Zeppelin", "Pink Floyd", "Queen 经典",
    "The Rolling Stones", "David Bowie",
    "邓丽君 70年代", "许冠杰 经典", "凤飞飞",
    # 80s
    "80年代经典", "1980s 经典", "80年代英文歌", "80年代华语老歌",
    "80s Pop", "80s Rock", "80s Synth Pop",
    "Michael Jackson 80s", "Madonna 80s", "Prince 80s",
    "Whitney Houston", "George Michael", "Cyndi Lauper",
    "张国荣 80s", "谭咏麟 80s", "陈百强", "梅艳芳",
    "BEYOND 80s", "林子祥", "徐小凤",
    # 90s
    "90年代经典", "1990s 经典", "90年代英文歌", "90年代华语金曲",
    "90s Rock", "90s Hip Hop", "90s R&B",
    "Nirvana", "Pearl Jam", "Radiohead 90s",
    "TLC", "Destiny's Child", "Boyz II Men",
    "2Pac 90s", "Snoop Dogg 90s", "Dr. Dre 90s",
    "张学友 90s", "刘德华 90s", "郭富城", "黎明",
    "王菲 90s", "林忆莲", "李玟", "张信哲",
    "Beyond 90s", "伍佰", "张宇", "周华健",
    # 00s
    "2000年代经典", "2000s 流行", "2000s 摇滚", "2000s R&B",
    "周杰伦 2000s", "孙燕姿 2000s", "蔡依林 2000s",
    "梁静茹 2000s", "林俊杰 2000s", "S.H.E 2000s",
    "Linkin Park 2000s", "Coldplay 2000s", "Eminem 2000s",
    "Beyoncé 2000s", "Rihanna 2000s", "Alicia Keys",
    "Avril Lavigne", "Kelly Clarkson", "P!nk",
    # 10s
    "2010年代经典", "2010s 流行", "2010s 摇滚", "2010s 嘻哈",
    "Adele 2010s", "Taylor Swift 2010s", "Ed Sheeran 2010s",
    "Bruno Mars 2010s", "The Weeknd 2010s", "Drake 2010s",
    "Kendrick Lamar 2010s", "Post Malone 2010s",
    "Billie Eilish", "Lana Del Rey", "Lorde",
    "华晨宇", "毛不易", "周深", "邓紫棋 2010s",
    "李荣浩", "薛之谦 2010s", "陈粒 2010s",
    # 20s
    "2020年代流行", "2020s Pop", "2020s 嘻哈", "2020s R&B",
    "2020 热门歌曲", "2021 热门歌曲", "2022 热门歌曲",
    "2023 热门歌曲", "2024 热门歌曲", "2025 热门歌曲",
    "The Weeknd 2020s", "Dua Lipa 2020s", "Olivia Rodrigo",
    "Doja Cat", "Megan Thee Stallion", "Jack Harlow",
    "告五人", "珂拉琪", "Deca Joins", "脆弱少女组",
]

# ============================================================
# 4. 语种热门（多语种覆盖）
# ============================================================
LANGUAGE_KW = [
    # 英语
    "英文热门歌曲", "English Hits", "英文流行歌曲", "英文经典",
    "Billboard Hot 100", "UK Top 40", "American Top 40",
    "英文情歌", "英文舞曲", "英文摇滚", "英文说唱",
    # 日语
    "日语热门歌曲", "J-POP 热门", "日本流行音乐",
    "日语经典", "日剧主题曲", "日本动漫歌曲",
    "日语情歌", "日语摇滚", "日语民谣",
    "米津玄師 热门", "YOASOBI 热门", "Official髭男dism",
    "Back Number", "Mr. Children", "Spitz",
    "宇多田光 热门", "椎名林檎 热门", "aiko",
    # 韩语
    "韩语热门歌曲", "K-POP 热门", "韩国流行音乐",
    "韩语经典", "韩剧OST", "韩国说唱",
    "韩语情歌", "韩语舞曲", "韩语 ballad",
    "BTS 热门", "BLACKPINK 热门", "TWICE 热门",
    "IU 热门", "EXO 热门", "Stray Kids",
    "SEVENTEEN 热门", "NewJeans 热门", "LE SSERAFIM 热门",
    "aespa 热门", "ITZY", "STAYC",
    # 粤语
    "粤语热门歌曲", "粤语经典", "粤语金曲",
    "粤语情歌", "粤语摇滚", "粤语流行",
    "陈奕迅 粤语", "张学友 粤语", "刘德华 粤语",
    "容祖儿", "杨千嬅", "古巨基", "陈慧琳",
    "谢安琪", "张敬轩", "关淑怡",
    # 其他语种
    "西班牙语热门", "Latin Pop 拉丁流行", "Reggaeton 雷鬼冻",
    "Shakira 热门", "J Balvin", "Bad Bunny",
    "法语热门", "France Pop", "Indie Français",
    "Angèle", "Stromae", "Indila",
    "泰语热门", "Thai Pop", "韩国独立音乐",
    "印度音乐", "Bollywood 歌曲", "Arijit Singh",
]

# ============================================================
# 5. OST / 影视 / 游戏 / 动漫（经典原声）
# ============================================================
OST_KW = [
    # 电影OST
    "经典电影OST", "电影原声带", "电影主题曲",
    "好莱坞电影OST", "华语电影OST", "日本电影OST",
    "迪士尼电影音乐", "宫崎骏音乐", "吉卜力工作室",
    "漫威电影OST", "DC电影OST", "星际穿越 OST",
    "泰坦尼克号 OST", "阿凡达 OST", "哈利波特 OST",
    "指环王 OST", "霍比特人 OST", "星球大战 OST",
    "教父 OST", "肖申克的救赎 OST",
    # 电视剧OST
    "经典电视剧OST", "国产剧OST", "美剧OST",
    "韩剧OST", "日剧OST", "英剧OST",
    "权力的游戏 OST", "老友记 OST", "绝命毒师 OST",
    "怪奇物语 OST", "黑镜 OST",
    "甄嬛传 OST", "琅琊榜 OST", "三体 OST",
    "陈情令 OST", "庆余年 OST", "长月烬明 OST",
    # 动漫OST
    "经典动漫OST", "日本动漫OST", "国漫OST",
    "宫崎骏动漫音乐", "新海诚动漫音乐",
    "火影忍者 OST", "海贼王 OST", "龙珠 OST",
    "灌篮高手 OST", "死神 OST", "进击的巨人 OST",
    "鬼灭之刃 OST", "咒术回战 OST", "一拳超人 OST",
    "钢之炼金术师 OST", "EVA 新世纪福音战士 OST",
    "你的名字 OST", "天气之子 OST", "铃芽之旅 OST",
    # 游戏OST
    "经典游戏OST", "游戏原声带", "游戏BGM",
    "最终幻想 OST", "勇者斗恶龙 OST", "塞尔达传说 OST",
    "超级马里奥 OST", "精灵宝可梦 OST",
    "原神 OST", "王者荣耀 OST", "英雄联盟 OST",
    "魔兽世界 OST", "星际争霸 OST", "暗黑破坏神 OST",
    "Genshin Impact OST", "League of Legends OST",
    "尼尔 机械纪元 OST", "女神异闻录 OST",
    "最终幻想 VII", "Kingdom Hearts OST",
]

# ============================================================
# 6. 歌手专辑深度（补充更多歌曲）
# ============================================================
DEEP_SINGER_KW = [
    # 华语男歌手（专辑深度）
    "周杰伦 专辑", "陈奕迅 专辑", "林俊杰 专辑",
    "薛之谦 专辑", "李荣浩 专辑", "毛不易 专辑",
    "许嵩 专辑", "张杰 专辑", "李健 专辑", "朴树 专辑",
    "王力宏 专辑", "陶喆 专辑", "方大同 专辑",
    "张学友 专辑", "刘德华 专辑", "谭咏麟 专辑",
    "黄家驹 专辑", "张国荣 专辑", "罗大佑 专辑",
    "李宗盛 专辑", "林宥嘉 专辑", "杨宗纬 专辑",
    "萧敬腾 专辑", "华晨宇 专辑", "周深 专辑",
    "邓紫棋 专辑", "张碧晨 专辑", "刘柏辛 专辑",
    # 华语女歌手
    "王菲 专辑", "张惠妹 专辑", "蔡依林 专辑",
    "孙燕姿 专辑", "梁静茹 专辑", "刘若英 专辑",
    "莫文蔚 专辑", "那英 专辑", "田馥甄 专辑",
    "陈绮贞 专辑", "李宇春 专辑", "张靓颖 专辑",
    "萨顶顶 专辑", "邓丽君 专辑", "徐佳莹 专辑",
    "蔡健雅 专辑", "陈粒 专辑", "杨丞琳 专辑",
    # 华语组合/乐队
    "五月天 专辑", "SHE 专辑", "凤凰传奇 专辑",
    "Beyond 专辑", "苏打绿 专辑", "TFBOYS 专辑",
    "时代少年团 专辑", "羽泉 专辑", "动力火车 专辑",
    "逃跑计划 专辑", "万能青年旅店 专辑", "痛仰乐队 专辑",
    "新裤子 专辑", "五条人 专辑", "草东没有派对",
    "马赛克乐队", "达达乐队", "花儿乐队",
    # 欧美
    "Taylor Swift 专辑", "Ed Sheeran 专辑", "Adele 专辑",
    "Bruno Mars 专辑", "Billie Eilish 专辑", "Dua Lipa 专辑",
    "Coldplay 专辑", "Imagine Dragons 专辑", "Maroon 5 专辑",
    "Ariana Grande 专辑", "Shakira 专辑", "Rihanna 专辑",
    "Eminem 专辑", "Kanye West 专辑", "Drake 专辑",
    "Michael Jackson 专辑", "Queen 专辑", "The Beatles 专辑",
    # 日韩
    "BTS 专辑", "BLACKPINK 专辑", "TWICE 专辑",
    "IU 专辑", "BIGBANG 专辑", "EXO 专辑",
    "米津玄師 专辑", "YOASOBI 专辑", "宇多田光 专辑",
    "椎名林檎 专辑", "RADWIMPS 专辑", "ONE OK ROCK 专辑",
    "星野源 专辑", "LiSA 专辑",
    # 古典演奏家
    "郎朗 钢琴", "李云迪 钢琴", "马友友 大提琴",
    "Hilary Hahn", "Yo-Yo Ma Bach", "郎朗 肖邦",
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

def search_and_enrich(kw, limit=50):
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
    if "_songs_dict" not in db:
        db["_songs_dict"] = {s["id"]: s for s in db.get("songs", []) if s.get("id")}
    before = len(db["_songs_dict"])
    for s in new_songs:
        if s["id"] not in db["_songs_dict"]:
            db["_songs_dict"][s["id"]] = s
    return len(db["_songs_dict"]) - before

def crawl_group(db, kws, group_name, per, total_added):
    print(f"\n[{group_name}] 共 {len(kws)} 个关键词...")
    for i, kw in enumerate(kws):
        print(f"  [{i+1}/{len(kws)}] {kw}... ", end="", flush=True)
        songs = search_and_enrich(kw, limit=per)
        added = merge_songs(db, songs)
        total_added += added
        print(f"+{added} (累计 +{total_added})")
        time.sleep(0.6 + random.uniform(0.2, 0.6))
    return total_added

# ============================================================
# 主流程
# ============================================================
def main():
    parser = argparse.ArgumentParser(description="大规模补充爬取QQ音乐")
    parser.add_argument("--per", type=int, default=40, help="每个关键词搜索数量")
    parser.add_argument("--smoke", action="store_true", help="烟雾测试(10个关键词)")
    parser.add_argument("--list", action="store_true", help="仅列出关键词")
    parser.add_argument("--only", choices=["genres","energy","era","lang","ost","singer"],
                        help="仅爬某一类")
    parser.add_argument("--output", default=None)
    args = parser.parse_args()

    db_path = args.output or os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "music_database.json")

    if args.list:
        groups = [
            ("稀缺风格", SCARCE_GENRE_KW),
            ("高能量", HIGH_ENERGY_KW),
            ("年代经典", ERA_CLASSIC_KW),
            ("语种热门", LANGUAGE_KW),
            ("OST", OST_KW),
            ("歌手深度", DEEP_SINGER_KW),
        ]
        for name, kws in groups:
            print(f"\n{name} ({len(kws)}):")
            for i, kw in enumerate(kws[:15], 1):
                print(f"  {i:>2}. {kw}")
            if len(kws) > 15:
                print(f"  ... 共 {len(kws)} 个")
        total = sum(len(k) for _, k in groups)
        print(f"\n总计: {total} 个关键词")
        return

    # 烟雾测试
    if args.smoke:
        smoke_kws = (SCARCE_GENRE_KW[:2] + HIGH_ENERGY_KW[:2] +
                     ERA_CLASSIC_KW[:2] + LANGUAGE_KW[:2] +
                     OST_KW[:1] + DEEP_SINGER_KW[:1])
        print(f"烟雾测试: {len(smoke_kws)} 个关键词, 每个搜 {args.per} 首")
        print("=" * 60)
        db = load_db(db_path)
        db["_songs_dict"] = {s["id"]: s for s in db.get("songs", []) if s.get("id")}
        initial = len(db["_songs_dict"])
        total_added = 0
        for i, kw in enumerate(smoke_kws):
            print(f"  [{i+1}/{len(smoke_kws)}] {kw}... ", end="", flush=True)
            songs = search_and_enrich(kw, limit=args.per)
            added = merge_songs(db, songs)
            total_added += added
            print(f"+{added} (累计 +{total_added})")
            time.sleep(0.5 + random.uniform(0.2, 0.5))
        print(f"\n烟雾测试完成: 初始 {initial} → 新增 {total_added} → 当前 {len(db['_songs_dict'])}")
        save_db(db, db_path)
        print(f"已保存到 {db_path}")
        return

    # 完整爬取
    db = load_db(db_path)
    db["_songs_dict"] = {s["id"]: s for s in db.get("songs", []) if s.get("id")}
    initial_total = len(db["_songs_dict"])
    print(f"初始数据库: {initial_total} 首")
    print(f"每关键词搜索: {args.per} 首")
    print("=" * 60)

    total_added = 0
    groups = []
    if not args.only or args.only == "genres":
        groups.append(("稀缺风格", SCARCE_GENRE_KW))
    if not args.only or args.only == "energy":
        groups.append(("高能量", HIGH_ENERGY_KW))
    if not args.only or args.only == "era":
        groups.append(("年代经典", ERA_CLASSIC_KW))
    if not args.only or args.only == "lang":
        groups.append(("语种热门", LANGUAGE_KW))
    if not args.only or args.only == "ost":
        groups.append(("OST原声", OST_KW))
    if not args.only or args.only == "singer":
        groups.append(("歌手深度", DEEP_SINGER_KW))

    for name, kws in groups:
        total_added = crawl_group(db, kws, name, args.per, total_added)
        # 每组完成保存一次，防止中途失败丢数据
        cur_count = len(db.get("_songs_dict", {}))
        save_db(db, db_path)
        print(f"  [{name}] 组完成，已保存。当前总库: {cur_count} 首")
        # save_db 会删 _songs_dict，下一组需重建
        db["_songs_dict"] = {s["id"]: s for s in db.get("songs", []) if s.get("id")}

    print(f"\n{'='*60}")
    print(f"全部爬取完成!")
    print(f"  初始: {initial_total} 首")
    print(f"  新增: {total_added} 首")
    print(f"  总计: {len(db.get('_songs_dict', db.get('songs', [])))} 首")
    print(f"{'='*60}")
    save_db(db, db_path)
    print(f"数据库已保存: {db_path}")


if __name__ == "__main__":
    main()
