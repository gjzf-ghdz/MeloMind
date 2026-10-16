"""
音乐数据库后处理脚本 - 精细化推断风格/能量/情绪等元数据

运行方式：
  python post_process_db.py music_database.json [output.json]

改进点：
1. 风格推断：综合搜索关键词 + 歌曲名 + 专辑 + 歌手多维度分析
2. 乐器推断：基于风格 + 歌曲是否纯音乐
3. 能量推断：结合歌曲时长 + 风格节奏特征
4. 情绪标签：多标签推断（核心情绪 + 辅助情绪）
5. 纯音乐判断：识别伴奏/纯音乐标记，结合风格特征
"""
import json
import os
import sys
import random
from typing import List, Dict, Optional

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# 确保能导入 backend 模块
_BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend"))
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

from models import infer_instrument_type


# ============================================================
# 1. 多维度风格推断
# ============================================================
# 风格特征词（在歌曲名/专辑/歌手文本中出现则倾向该风格）
GENRE_TEXT_HINTS = {
    "classical": [
        "古典", "钢琴", "协奏曲", "奏鸣曲", "交响乐", "莫扎特", "巴赫",
        "贝多芬", "肖邦", "德彪西", "克莱德曼", "古典乐", "classic",
    ],
    "neo-classical": ["新古典", "piano", "钢琴", "纯音乐", "instrumental"],
    "minimalist": ["极简", "minimal", "环境", "ambient", "氛围"],
    "ambient": ["环境", "氛围", "ambient", "白噪音", "自然", "雨声",
                "森林", "海浪", "环境音乐"],
    "electronic": ["电子", "edm", "techno", "house", "电音", "舞曲",
                    "dj", "electronic", "dubstep", "trap"],
    "rock": ["摇滚", "rock", "金属", "metal", "硬核", "punk", "朋克",
             "heavy metal", "硬核摇滚"],
    "pop": ["流行", "pop", "华语", "港台", "欧美流行", "kpop", "jpop",
            "mtv", "排行榜"],
    "hip-hop": ["嘻哈", "hip-hop", "rap", "说唱", "trap", "mc", "说唱",
                "rap god"],
    "r&b": ["r&b", "rb", "节奏蓝调", "灵魂", "soul", "放克", "funk",
            "节奏布鲁斯"],
    "jazz": ["爵士", "jazz", "蓝调", "blues", "saxophone", "萨克斯",
             "爵士乐"],
    "folk": ["民谣", "folk", "民歌", "木吉他", "acoustic", "乡村",
             "民谣摇滚"],
    "indie": ["独立", "indie", "地下", "原创", "demo"],
}

# 搜索关键词子串 → 风格映射（按优先级排序，前者优先）
KEYWORD_SUBSTR_GENRE = [
    # 古典/新古典/极简（高优先级，避免被纯音乐抢走）
    ("古典", "classical"), ("协奏曲", "classical"), ("奏鸣曲", "classical"),
    ("交响", "classical"), ("莫扎特", "classical"), ("巴赫", "classical"),
    ("贝多芬", "classical"), ("肖邦", "classical"), ("李斯特", "classical"),
    ("舒伯特", "classical"), ("柴可夫斯基", "classical"), ("tchaikovsky", "classical"),
    ("debussy", "classical"), ("ravel", "classical"), ("brahms", "classical"),
    ("极简", "minimalist"), ("minimal", "minimalist"),
    ("max richter", "minimalist"), ("ludovico einaudi", "minimalist"),
    ("yann tiersen", "minimalist"), ("michael nyman", "minimalist"),
    ("arvo pärt", "minimalist"), ("philip glass", "minimalist"),
    ("nils frahm", "minimalist"), ("ólafur arnalds", "minimalist"),
    ("joep beving", "minimalist"),
    # 新古典（钢琴纯音乐）
    ("新古典", "neo-classical"), ("钢琴曲", "neo-classical"),
    ("久石让", "neo-classical"), ("坂本龙一", "neo-classical"),
    ("坂本龍一", "neo-classical"), ("yiruma", "neo-classical"),
    ("李闰珉", "neo-classical"), ("理查德克莱德曼", "neo-classical"),
    ("克莱德曼", "neo-classical"), ("brian crain", "neo-classical"),
    ("kevin kern", "neo-classical"), ("宫崎骏", "neo-classical"),
    ("吉卜力", "neo-classical"), ("新海诚", "neo-classical"),
    # 环境/轻音乐
    ("白噪音", "ambient"), ("雨声", "ambient"), ("森林", "ambient"),
    ("海浪", "ambient"), ("环境音乐", "ambient"), ("自然音", "ambient"),
    ("氛围音乐", "ambient"), ("ambient", "ambient"), ("自然声", "ambient"),
    # 摇滚/金属/朋克
    ("摇滚", "rock"), ("rock", "rock"), ("金属", "rock"), ("metal", "rock"),
    ("朋克", "rock"), ("punk", "rock"), ("硬核", "rock"),
    ("grunge", "rock"), ("nirvana", "rock"), ("ac/dc", "rock"),
    ("guns n roses", "rock"), ("metallica", "rock"), ("linkin park", "rock"),
    ("blink-182", "rock"), ("green day", "rock"), ("foo fighters", "rock"),
    ("red hot chili peppers", "rock"), ("queen", "rock"),
    ("the beatles", "rock"), ("beyond", "rock"), ("五月天", "rock"),
    ("coldplay", "rock"), ("imagine dragons", "rock"),
    ("one ok rock", "rock"), ("radwimps", "rock"),
    # 嘻哈/说唱
    ("嘻哈", "hip-hop"), ("hip-hop", "hip-hop"), ("hip hop", "hip-hop"),
    ("说唱", "hip-hop"), ("rap", "hip-hop"), ("trap", "hip-hop"),
    ("drill", "hip-hop"), ("boom bap", "hip-hop"), ("mumble rap", "hip-hop"),
    ("eminem", "hip-hop"), ("2pac", "hip-hop"), ("drake", "hip-hop"),
    ("kendrick lamar", "hip-hop"), ("j. cole", "hip-hop"),
    ("travis scott", "hip-hop"), ("post malone", "hip-hop"),
    ("kanye west", "hip-hop"), ("jay z", "hip-hop"),
    # R&B/灵魂
    ("r&b", "r&b"), ("rb", "r&b"), ("节奏蓝调", "r&b"), ("节奏布鲁斯", "r&b"),
    ("灵魂", "r&b"), ("soul", "r&b"), ("neo-soul", "r&b"), ("放克", "r&b"),
    ("funk", "r&b"), ("the weeknd", "r&b"), ("sza", "r&b"),
    ("frank ocean", "r&b"), ("daniel caesar", "r&b"), ("h.e.r.", "r&b"),
    ("bryson tiller", "r&b"), ("jhené aiko", "r&b"),
    ("方大同", "r&b"), ("陶喆", "r&b"),
    # 爵士/蓝调
    ("爵士", "jazz"), ("jazz", "jazz"), ("蓝调", "jazz"), ("blues", "jazz"),
    ("萨克斯", "jazz"), ("saxophone", "jazz"), ("bebop", "jazz"),
    ("bossa nova", "jazz"), ("swing", "jazz"), ("big band", "jazz"),
    ("miles davis", "jazz"), ("john coltrane", "jazz"),
    ("thelonious monk", "jazz"), ("bill evans", "jazz"),
    ("dave brubeck", "jazz"), ("charlie parker", "jazz"),
    ("louis armstrong", "jazz"), ("ella fitzgerald", "jazz"),
    ("norah jones", "jazz"), ("michael bublé", "jazz"),
    ("diana krall", "jazz"), ("chet baker", "jazz"),
    # 民谣
    ("民谣", "folk"), ("folk", "folk"), ("民歌", "folk"),
    ("木吉他", "folk"), ("acoustic", "folk"), ("乡村", "folk"),
    ("bob dylan", "folk"), ("joan baez", "folk"),
    ("simon & garfunkel", "folk"), ("赵雷", "folk"), ("宋冬野", "folk"),
    ("陈粒", "folk"), ("花粥", "folk"), ("郝云", "folk"),
    ("万晓利", "folk"), ("周云蓬", "folk"), ("钟立风", "folk"),
    ("joni mitchell", "folk"), ("leonard cohen", "folk"),
    # 独立
    ("独立", "indie"), ("indie", "indie"), ("bedroom pop", "indie"),
    ("dream pop", "indie"), ("shoegaze", "indie"), ("自赏", "indie"),
    ("lo-fi 独立", "indie"), ("indie pop", "indie"), ("indie folk", "indie"),
    ("indie rock", "indie"), ("indie electronic", "indie"),
    ("告五人", "indie"), ("deca joins", "indie"), ("脆弱少女组", "indie"),
    ("草东没有派对", "indie"), ("万能青年旅店", "indie"),
    # 电子
    ("电子", "electronic"), ("edm", "electronic"), ("techno", "electronic"),
    ("house", "electronic"), ("trance", "electronic"), ("dubstep", "electronic"),
    ("future bass", "electronic"), ("synthwave", "electronic"),
    ("vaporwave", "electronic"), ("蒸汽波", "electronic"),
    ("drum and bass", "electronic"), ("breakbeat", "electronic"),
    ("chillout", "electronic"), ("trip hop", "electronic"),
    ("daft punk", "electronic"), ("deadmau5", "electronic"),
    ("avicii", "electronic"), ("calvin harris", "electronic"),
    ("marshmello", "electronic"), ("zedd", "electronic"),
    ("the chemical brothers", "electronic"), ("moby", "electronic"),
    ("aphex twin", "electronic"),
]


def match_keyword_substring(search_keyword: str) -> Optional[str]:
    """子串匹配搜索关键词到风格（按优先级，首个命中返回）"""
    sk_lower = (search_keyword or "").lower()
    for sub, genre in KEYWORD_SUBSTR_GENRE:
        if sub.lower() in sk_lower:
            return genre
    return None


def score_genre_from_text(text: str) -> Dict[str, int]:
    """计算每个风格在文本中的匹配得分"""
    text_lower = (text or "").lower()
    scores = {}
    for genre, hints in GENRE_TEXT_HINTS.items():
        score = 0
        for h in hints:
            if h.lower() in text_lower:
                score += 1
        if score > 0:
            scores[genre] = score
    return scores


def infer_genre(title: str, album: str, artist: str,
                search_keyword: str) -> str:
    """综合多维度推断风格"""
    # 文本包含 title + album + artist + search_keyword
    combined = f"{title} {album} {artist} {search_keyword}"

    # 1. 搜索关键词子串强映射（优先级最高）
    strong = match_keyword_substring(search_keyword)
    if strong:
        # 用文本分析验证
        text_scores = score_genre_from_text(f"{title} {album}")
        text_genre = max(text_scores, key=text_scores.get) if text_scores else None
        if text_genre is None or text_genre == strong:
            return strong
        if text_scores.get(text_genre, 0) >= 2:
            return text_genre
        return strong

    # 2. 纯文本分析（含 search_keyword 和 artist）
    text_scores = score_genre_from_text(combined)
    if text_scores:
        return max(text_scores, key=text_scores.get)

    # 3. 默认
    return "pop"


# ============================================================
# 2. 能量等级精细化推断
# ============================================================
def infer_energy(genre: str, search_keyword: str,
                 duration_sec: int, title: str) -> int:
    """多维度能量推断"""
    # 基础能量（按风格）
    genre_energy_base = {
        "classical": 3, "neo-classical": 3, "minimalist": 2,
        "ambient": 2, "electronic": 7, "rock": 8,
        "pop": 6, "hip-hop": 7, "r&b": 5,
        "jazz": 5, "folk": 4, "indie": 5,
    }
    base = genre_energy_base.get(genre, 5)

    # 搜索关键词调整
    keyword_boost = {
        "劲爆": 3, "热血": 3, "燃": 2, "运动": 2,
        "力量": 3, "史诗": 2, "派对": 2, "舞曲": 2,
        "世界杯": 3, "奥运会": 2, "nba": 3, "篮球": 2,
        "跑步": 2, "健身": 3, "dj": 3, "电子": 2,
        "摇滚": 2, "嘻哈": 2, "说唱": 2,
        "安静": -2, "舒缓": -2, "治愈": -1, "轻音乐": -1,
        "冥想": -3, "钢琴": -2, "纯音乐": -1,
        "悲伤": -2, "伤感": -2,
    }
    boost = keyword_boost.get(search_keyword, 0)

    # 歌曲名中的能量标记
    title_boost = 0
    title_lower = title.lower()
    if any(w in title_lower for w in ["live", "现场", "演唱会"]):
        title_boost += 1
    if any(w in title_lower for w in ["伴奏", "inst", "纯音乐"]):
        title_boost -= 1
    if any(w in title_lower for w in ["remix", "mix", "club"]):
        title_boost += 2

    energy = base + boost + title_boost
    # 时长调整：超长曲(>10min)能量降低
    if duration_sec > 600:
        energy = max(1, energy - 2)
    energy = max(1, min(10, energy))
    return energy


# ============================================================
# 3. 情绪标签多维度推断
# ============================================================
MOOD_RULES = [
    # (条件函数, 情绪标签)
    (lambda sk, g, e, t: sk in ["安静", "舒缓", "钢琴曲", "钢琴", "纯音乐", "轻音乐"], "calm"),
    (lambda sk, g, e, t: sk in ["治愈", "放松", "冥想", "瑜伽"], "soothing"),
    (lambda sk, g, e, t: sk in ["劲爆", "热血", "燃", "运动", "跑步", "健身"], "energetic"),
    (lambda sk, g, e, t: sk in ["欢快", "开心", "快乐", "元气"], "joyful"),
    (lambda sk, g, e, t: sk in ["悲伤", "伤感", "深情"], "sad"),
    (lambda sk, g, e, t: sk in ["励志", "温暖", "正能量"], "hopeful"),
    (lambda sk, g, e, t: sk in ["梦幻", "空灵", "氛围"], "dreamy"),
    (lambda sk, g, e, t: sk in ["节奏", "律动", "放克", "r&b"], "groovy"),
    (lambda sk, g, e, t: sk in ["力量", "史诗"], "powerful"),
    (lambda sk, g, e, t: sk in ["专注", "学习", "编程", "代码", "白噪音"], "focused"),
    (lambda sk, g, e, t: sk in ["灵感", "创意"], "inspired"),
    (lambda sk, g, e, t: sk in ["轻松", "经典", "流行"], "balanced"),
    (lambda sk, g, e, t: sk in ["提神", "清新", "活力"], "alert"),
    (lambda sk, g, e, t: sk in ["欢庆", "庆祝", "派对", "生日"], "festive"),
    (lambda sk, g, e, t: sk in ["浪漫", "情歌", "温馨"], "romantic"),
    (lambda sk, g, e, t: sk in ["世界杯", "世界杯主题曲"], "festive"),
    (lambda sk, g, e, t: sk in ["奥运会", "奥运主题曲"], "inspired"),
    (lambda sk, g, e, t: sk in ["nba", "篮球"], "powerful"),
    (lambda sk, g, e, t: sk in ["足球", "足球之歌"], "energetic"),
    (lambda sk, g, e, t: sk in ["游戏", "电竞"], "energetic"),
    (lambda sk, g, e, t: sk in ["雨", "森林", "海浪"], "peaceful"),
    # 基于风格
    (lambda sk, g, e, t: g in ["ambient", "neo-classical", "minimalist"] and e <= 3, "peaceful"),
    (lambda sk, g, e, t: g == "classical" and e <= 4, "calm"),
    (lambda sk, g, e, t: g == "rock" and e >= 7, "powerful"),
    (lambda sk, g, e, t: g == "electronic" and e >= 7, "energetic"),
    (lambda sk, g, e, t: g == "hip-hop", "energetic"),
    (lambda sk, g, e, t: g == "folk" and e <= 5, "soothing"),
]


def infer_mood_tags(search_keyword: str, genre: str, energy: int,
                    title: str) -> List[str]:
    """推断多标签情绪"""
    tags = []
    for rule_fn, mood in MOOD_RULES:
        try:
            if rule_fn(search_keyword, genre, energy, title):
                if mood not in tags:
                    tags.append(mood)
        except Exception:
            pass

    # 能量补充
    if energy >= 8 and "energetic" not in tags:
        tags.append("energetic")
    if energy <= 3 and "calm" not in tags and "peaceful" not in tags:
        tags.append("peaceful")
    if not tags:
        tags.append("balanced")

    return tags[:3]  # 最多3个标签


# ============================================================
# 4. BPM精细化推断
# ============================================================
GENRE_BPM_RANGE = {
    "classical": (60, 110), "neo-classical": (60, 90), "minimalist": (50, 80),
    "ambient": (50, 75), "electronic": (120, 145), "rock": (120, 150),
    "pop": (100, 128), "hip-hop": (90, 115), "r&b": (70, 100),
    "jazz": (80, 160), "folk": (90, 120), "indie": (90, 125),
}


def infer_bpm(genre: str, energy: int, duration_sec: int) -> int:
    """基于风格+能量推断BPM"""
    lo, hi = GENRE_BPM_RANGE.get(genre, (80, 130))
    # 能量越高 → 越接近上限
    ratio = (energy - 1) / 9.0  # 0.0 ~ 1.0
    center = lo + (hi - lo) * ratio
    bpm = int(center * random.uniform(0.96, 1.04))
    return max(40, min(200, bpm))


# ============================================================
# 5. 纯音乐判断
# ============================================================
def infer_instrumental(title: str, album: str, artist: str,
                       genre: str, search_keyword: str) -> bool:
    """精细判断是否为纯音乐"""
    text = f"{title} {album}".lower()

    # 强纯音乐标记
    instrumental_markers = ["纯音乐", "伴奏", "inst", "instrumental", "纯音",
                            "钢琴曲", "钢琴版", "吉他版"]
    if any(m in text for m in instrumental_markers):
        return True

    # 强人声标记
    vocal_markers = ["版", "live", "现场", "演唱会", "合唱", "feat",
                     "featuring", "演唱", "original"]
    if any(m in text for m in vocal_markers) and "伴奏" not in text:
        return False

    # 基于搜索关键词
    if search_keyword in ["纯音乐", "钢琴曲", "钢琴", "轻音乐",
                          "冥想", "瑜伽", "古典", "环境", "白噪音"]:
        return True

    # 基于风格
    if genre in ["ambient", "minimalist"]:
        return True
    if genre == "classical" and "交响" not in text:
        return True

    # 基于歌手（特定器乐演奏家）
    instrumental_artists = ["钢琴", "克莱德曼", "久石让", "宫崎骏",
                            "max richter", "ludovico einaudi"]
    for ia in instrumental_artists:
        if ia.lower() in (artist or "").lower():
            return True

    # 流行/摇滚/嘻哈通常有人声
    if genre in ["pop", "rock", "hip-hop", "r&b"]:
        return False

    # 默认：不确定则保持原样（非纯音乐）
    return False


# ============================================================
# 6. 任务标签推断
# ============================================================
TASK_TAG_RULES = [
    (["学习", "专注", "编程", "代码", "编程", "古典", "专注"], "study"),
    (["运动", "跑步", "健身", "瑜伽", "电子", "燃"], "workout"),
    (["放松", "冥想", "瑜伽", "环境", "白噪音", "雨声", "森林"], "relax"),
    (["世界杯", "奥运会", "nba", "篮球", "足球", "派对", "游戏", "电竞"], "entertainment"),
    (["摇滚", "嘻哈", "说唱"], "entertainment"),
    (["开车", "通勤"], "commute"),
    (["编程", "代码"], "coding"),
    (["吉他", "民谣", "创作"], "creative"),
]


def infer_task_tags(search_keyword: str, genre: str) -> List[str]:
    """推断任务标签"""
    tags = set()
    for keywords, tag in TASK_TAG_RULES:
        if search_keyword in keywords or genre in keywords:
            tags.add(tag)
    return list(tags) if tags else ["general"]


# ============================================================
# 7. 推荐理由生成
# ============================================================
def genre_cn(genre: str) -> str:
    m = {"classical": "古典", "pop": "流行", "rock": "摇滚", "electronic": "电子",
         "folk": "民谣", "r&b": "R&B", "hip-hop": "嘻哈", "jazz": "爵士",
         "ambient": "轻音乐", "neo-classical": "新古典", "minimalist": "极简",
         "indie": "独立"}
    return m.get(genre, genre)


def mood_cn(mood: str) -> str:
    m = {"calm": "平静", "energetic": "亢奋", "joyful": "欢快", "sad": "悲伤",
         "hopeful": "励志", "dreamy": "梦幻", "groovy": "律动", "focused": "专注",
         "inspired": "灵感", "soothing": "治愈", "balanced": "平衡", "alert": "提神",
         "festive": "欢庆", "celebratory": "庆祝", "romantic": "浪漫",
         "powerful": "力量", "relaxed": "放松", "peaceful": "安宁"}
    return m.get(mood, mood)


def generate_reason(title: str, artist: str, genre: str, energy: int,
                     mood_tags: List[str], instrumental: bool,
                     duration: int, search_keyword: str) -> str:
    """生成精细化推荐理由"""
    # 核心描述
    core_parts = [f"搜索关键词「{search_keyword}」匹配"]

    # 能量特征
    if energy <= 3:
        core_parts.append("舒缓治愈")
    elif energy <= 6:
        core_parts.append("节奏适中")
    else:
        core_parts.append("高能量燃曲")

    # 风格特征
    cn_style = genre_cn(genre)
    if cn_style in ["古典", "新古典", "极简"]:
        core_parts.append(f"{cn_style}韵味")
    elif cn_style in ["摇滚", "嘻哈", "电子"]:
        core_parts.append(f"{cn_style}节拍")
    else:
        core_parts.append(f"典型{cn_style}")

    # 情绪
    primary_mood = mood_cn(mood_tags[0]) if mood_tags else "平衡"
    core_parts.append(f"{primary_mood}氛围")

    # 形式
    form = "纯音乐" if instrumental else "人声演唱"
    mins, secs = duration // 60, duration % 60
    core_parts.append(f"{form} · {mins}分{secs}秒")

    return " | ".join(core_parts)


# ============================================================
# 8. 主后处理逻辑
# ============================================================
def post_process(input_path: str, output_path: str = None):
    """对已有数据库进行精细化后处理"""
    print(f"读取数据库: {input_path}")
    with open(input_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    songs = data.get("songs", [])
    print(f"共 {len(songs)} 首歌曲待后处理")

    updated = []
    stats = {"style_changed": 0, "energy_changed": 0, "mood_changed": 0}

    for i, song in enumerate(songs):
        if (i + 1) % 100 == 0:
            print(f"  处理中: {i+1}/{len(songs)} ...", end="\r")

        title = song.get("title", "")
        album = song.get("album", "")
        artist = song.get("artist", "")
        duration = song.get("duration_sec", 240)
        sk = song.get("search_keyword", "")
        old_genre = song.get("genre", "")
        old_energy = song.get("energy", 5)
        old_moods = song.get("mood_tags", [])

        # 重新推断
        new_genre = infer_genre(title, album, artist, sk)
        new_energy = infer_energy(new_genre, sk, duration, title)
        new_moods = infer_mood_tags(sk, new_genre, new_energy, title)
        new_bpm = infer_bpm(new_genre, new_energy, duration)
        new_inst = infer_instrumental(title, album, artist, new_genre, sk)
        new_instrument = infer_instrument_type(new_genre)
        new_tasks = infer_task_tags(sk, new_genre)
        new_reason = generate_reason(title, artist, new_genre, new_energy,
                                      new_moods, new_inst, duration, sk)

        if new_genre != old_genre:
            stats["style_changed"] += 1
        if new_energy != old_energy:
            stats["energy_changed"] += 1
        if new_moods != old_moods:
            stats["mood_changed"] += 1

        updated_song = {
            **song,
            "genre": new_genre,
            "energy": new_energy,
            "tempo_bpm": new_bpm,
            "instrumental": new_inst,
            "instrument_type": new_instrument,
            "mood_tags": new_moods,
            "task_tags": new_tasks,
            "reason": new_reason,
        }
        updated.append(updated_song)

    output_path = output_path or input_path.replace(".json", "_refined.json")
    result = {
        **data,
        "version": 2,
        "post_processed": True,
        "post_process_stats": stats,
        "songs": updated,
    }
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"\n后处理完成: {output_path}")
    print(f"  风格变更: {stats['style_changed']} 首")
    print(f"  能量变更: {stats['energy_changed']} 首")
    print(f"  情绪变更: {stats['mood_changed']} 首")
    print_summary(updated)


def print_summary(songs: List[Dict]):
    """打印统计摘要"""
    if not songs:
        return

    # 风格分布
    genre_dist = {}
    for s in songs:
        g = s.get("genre", "unknown")
        genre_dist[g] = genre_dist.get(g, 0) + 1

    print("\n风格分布:")
    for g, c in sorted(genre_dist.items(), key=lambda x: -x[1]):
        print(f"  {genre_cn(g):<10} {c:>5} 首  ({100*c//len(songs)}%)")

    # 示例
    print("\n示例（前3首）:")
    for s in songs[:3]:
        print(f"\n  {s['title']} - {s['artist']}")
        print(f"    风格: {s['genre']} | 能量: {s['energy']} | BPM: {s['tempo_bpm']}")
        print(f"    情绪: {', '.join(s['mood_tags'])}")
        print(f"    纯音乐: {s['instrumental']} | 乐器: {s['instrument_type']}")
        print(f"    理由: {s['reason']}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: python post_process_db.py <input.json> [output.json]")
        sys.exit(1)
    inp = sys.argv[1]
    out = sys.argv[2] if len(sys.argv) > 2 else None
    post_process(inp, out)
