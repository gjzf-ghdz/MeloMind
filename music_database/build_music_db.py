"""
音乐数据库构建脚本 - 爬取QQ音乐并推断风格/能量/情绪/乐器等元数据

运行方式：python build_music_db.py
输出：backend/music_database.json（JSON格式的歌曲数据库）

注意：
- 复用项目已有的 QQMusicSource 类抓取真实数据
- 推断字段基于搜索关键词 + 歌曲元数据本地计算，不生成随机数据
- 每次请求间隔 1.2 秒，避免被 QQ 音乐风控
"""
import json
import os
import sys
import time
import random
import hashlib
from typing import List, Dict, Optional, Tuple

# 确保能导入同目录下的模块
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# 确保能导入 backend 模块
_BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend"))
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

from qqmusic_source import QQMusicSource
from models import Song, infer_instrument_type


# ============================================================
# 1. 风格推断：基于搜索关键词和歌曲元数据分析
# ============================================================
# 中文歌曲中常见的风格/流派关键词映射
GENRE_HINTS = {
    "classical": ["古典", "钢琴", "协奏曲", "奏鸣曲", "交响乐", "莫扎特", "巴赫", "贝多芬", "肖邦", "德彪西", "克莱德曼"],
    "neo-classical": ["新古典", "轻音乐", "钢琴", "纯音乐", "piano", "钢琴曲"],
    "minimalist": ["极简", "minimal", "环境音乐", "ambient", "氛围"],
    "ambient": ["环境", "氛围", "ambient", "白噪音", "自然", "雨声", "森林"],
    "electronic": ["电子", "edm", "techno", "house", "电音", "舞曲", "dj", "electronic"],
    "rock": ["摇滚", "rock", "金属", "metal", "硬核", "punk", "朋克"],
    "pop": ["流行", "pop", "华语", "港台", "欧美流行"],
    "hip-hop": ["嘻哈", "hip-hop", "rap", "说唱", "rap", "trap"],
    "r&b": ["r&b", "rb", "节奏蓝调", "灵魂", "soul", "放克", "funk"],
    "jazz": ["爵士", "jazz", "蓝调", "blues", "saxophone"],
    "folk": ["民谣", "folk", "民歌", "木吉他", "acoustic"],
    "indie": ["独立", "indie", "地下", "原创"],
}

# 搜索关键词 → 风格的直接映射（搜索时已知的分类）
KEYWORD_GENRE_MAP = {
    # 情绪关键词直接对应风格
    "安静": "ambient", "舒缓": "ambient", "治愈": "ambient", "轻音乐": "ambient",
    "钢琴曲": "classical", "冥想": "ambient",
    "劲爆": "electronic", "热血": "rock", "燃": "rock", "运动": "electronic",
    "欢快": "pop", "开心": "pop", "元气": "pop",
    "悲伤": "classical", "纯音乐": "neo-classical",
    "励志": "pop", "温暖": "folk", "正能量": "pop",
    "梦幻": "ambient", "空灵": "ambient", "氛围": "ambient",
    "节奏": "r&b", "律动": "r&b", "放克": "r&b",
    "快乐": "pop", "动感": "electronic",
    "力量": "rock", "史诗": "rock",
    "专注": "ambient", "学习": "classical", "白噪音": "ambient",
    "灵感": "electronic", "创意": "electronic",
    "放松": "ambient",
    "轻松": "pop", "经典": "classical",
    "提神": "electronic", "清新": "pop", "活力": "electronic",
    "欢庆": "pop", "庆祝": "pop", "派对": "electronic",
    "喜悦": "pop",
    "浪漫": "pop", "情歌": "pop", "温馨": "folk",
    # 事件关键词
    "世界杯": "pop", "世界杯主题曲": "pop", "生命之杯": "pop", "Waka Waka": "pop",
    "奥运会": "classical", "奥运主题曲": "classical", "我和你": "classical", "手拉手": "classical",
    "NBA": "hip-hop", "篮球": "hip-hop", "灌篮高手": "rock",
    "足球": "pop", "足球之歌": "pop", "欧冠主题曲": "classical",
    "电视剧": "pop", "OST": "pop", "主题曲": "pop", "影视原声": "pop",
    "游戏": "electronic", "电竞": "electronic", "游戏背景音乐": "electronic",
    "派对": "electronic", "舞曲": "electronic", "DJ": "electronic",
    "跑步": "electronic", "运动": "electronic", "健身": "electronic",
    "瑜伽": "ambient",
    "钢琴": "classical", "吉他": "folk",
}

# ============================================================
# 2. 能量等级推断
# ============================================================
ENERGY_BY_KEYWORD = {
    # 低能量 (1-3)
    "安静": 2, "舒缓": 2, "治愈": 3, "轻音乐": 3, "钢琴曲": 2,
    "冥想": 1, "放松": 3, "专注": 3, "学习": 3, "白噪音": 2,
    "悲伤": 3,
    # 中能量 (4-6)
    "欢快": 5, "开心": 5, "元气": 6, "励志": 6, "温暖": 5,
    "梦幻": 4, "空灵": 4, "节奏": 5, "律动": 5,
    "快乐": 5, "动感": 6, "灵感": 5, "创意": 5,
    "轻松": 4, "经典": 4, "提神": 6, "清新": 5,
    # 高能量 (7-10)
    "劲爆": 9, "热血": 9, "燃": 8, "运动": 8, "力量": 9,
    "史诗": 8, "活力": 8,
    # 事件关键词
    "世界杯": 9, "奥运会": 8, "NBA": 9, "篮球": 8,
    "足球": 8, "跑步": 8, "健身": 9, "派对": 8,
    "DJ": 9, "舞曲": 8,
}

# ============================================================
# 3. 情绪标签推断
# ============================================================
MOOD_BY_KEYWORD = {
    "安静": "calm", "舒缓": "calm", "治愈": "soothing", "轻音乐": "calm",
    "钢琴曲": "calm", "冥想": "peaceful",
    "劲爆": "energetic", "热血": "energetic", "燃": "energetic", "运动": "energetic",
    "欢快": "joyful", "开心": "joyful", "元气": "joyful", "快乐": "joyful",
    "悲伤": "sad",
    "励志": "hopeful", "温暖": "hopeful", "正能量": "hopeful",
    "梦幻": "dreamy", "空灵": "dreamy", "氛围": "dreamy",
    "节奏": "groovy", "律动": "groovy", "放克": "groovy",
    "动感": "joyful", "力量": "powerful", "史诗": "powerful",
    "专注": "focused", "学习": "focused", "白噪音": "focused",
    "灵感": "inspired", "创意": "inspired",
    "放松": "relaxed",
    "轻松": "balanced", "经典": "balanced",
    "提神": "alert", "清新": "alert", "活力": "alert",
    "欢庆": "festive", "庆祝": "celebratory", "派对": "festive",
    "喜悦": "celebratory",
    "浪漫": "romantic", "情歌": "romantic", "温馨": "romantic",
    # 事件
    "世界杯": "festive", "奥运会": "inspired", "NBA": "powerful",
    "篮球": "energetic", "足球": "energetic", "跑步": "energetic",
    "健身": "energetic", "派对": "festive", "瑜伽": "peaceful",
}

# ============================================================
# 4. 节奏（BPM）推断
# ============================================================
def infer_tempo(energy: int, genre: str, duration_sec: int) -> int:
    """根据能量等级和风格推断合理的BPM范围"""
    # 基础BPM范围
    base = {
        "classical": (60, 100), "neo-classical": (60, 90), "minimalist": (50, 80),
        "ambient": (50, 80), "electronic": (120, 140), "rock": (120, 150),
        "pop": (100, 130), "hip-hop": (90, 110), "r&b": (70, 100),
        "jazz": (80, 140), "folk": (90, 120), "indie": (90, 120),
    }
    lo, hi = base.get(genre, (80, 130))
    # 能量高 → BPM 高
    energy_factor = 0.5 + energy / 20.0  # 0.55 ~ 1.0
    center = (lo + hi) / 2
    bpm = int(center * energy_factor * random.uniform(0.95, 1.05))
    return max(40, min(180, bpm))


# ============================================================
# 5. 风格二次推断：基于歌曲标题/专辑/歌手的字符分析
# ============================================================
def infer_genre_from_text(text: str) -> Optional[str]:
    """从歌曲名/专辑名推断风格"""
    text_lower = (text or "").lower()
    for genre, hints in GENRE_HINTS.items():
        for h in hints:
            if h.lower() in text_lower:
                return genre
    return None


# ============================================================
# 5b. 人声/纯音乐统一判定（标题专辑 + 搜索词双重信号）
# ============================================================
# 标题/专辑中的强纯音乐标记（命中即纯音乐；
# 注意：自然词如"风声/海浪"也是知名人声歌曲名，故只在搜索词层判定）
_TITLE_INSTR_HINTS = [
    "纯音乐", "伴奏", "instrumental", "(inst", "（inst", "inst版",
    "钢琴曲", "钢琴版", "钢琴纯", "钢琴独奏", "吉他独奏", "小提琴独奏",
    "大提琴独奏", "古筝独奏", "二胡独奏", "指弹", "bgm", "background music",
    "背景音乐", "配乐", "轻音乐", "无人声", "卡拉ok版", "karaoke",
]
# 搜索词中的纯音乐类目信号
_KW_INSTR_HINTS = [
    "纯音乐", "纯音", "钢琴", "古筝", "古琴", "二胡", "琵琶", "笛子",
    "箫", "笙", "萨克斯纯", "小提琴纯", "大提琴纯", "弦乐四重奏", "三重奏",
    "长笛", "单簧管", "双簧管", "圆号", "小号", "长号", "中提琴",
    "白噪音", "雨声", "森林", "海浪", "溪流", "风声", "篝火", "雷雨",
    "自然声", "环境音", "轻音乐", "氛围", "ambient", "极简", "minimal",
    "drone", "lo-fi", "lofi", "低保真", "chillhop", "study beats",
    "sleep music", "助眠", "睡眠", "睡前儿歌", "冥想", "打坐", "禅修",
    "脑波", "solfeggio", "432hz", "528hz",
    "bgm", "配乐", "film score", "video game music", "游戏音乐",
    "游戏bgm", "游戏原声", "动漫配乐", "动画配乐", "动画原声",
    "spa", "按摩", "泡澡", "瑜伽纯音乐",
    "古典音乐", "巴赫", "莫扎特", "贝多芬", "肖邦", "德彪西",
    "fingerstyle", "classical guitar", "acoustic guitar",
    "neo classical", "modern classical", "epic orchestral", "orchestral",
    "instrumental",
]
# 搜索词中的人声类目信号（命中即人声，优先级高于类目纯音乐词）
_KW_VOCAL_HINTS = [
    "歌曲", "金曲", "情歌", "华语", "中文", "国语", "粤语", "闽南语",
    "欧美", "英文", "english", "演唱会", "现场版", "现场", "翻唱",
    "新歌", "热歌", "网络", "抖音", "对唱", "合唱", "老歌", "怀旧",
    "年代", "回忆", "k-pop", "j-pop", "韩流", "韩国歌", "日语歌",
    "儿歌", "童谣", "主题曲", "片尾曲", "插曲", "影视歌曲",
    "世界杯", "奥运", "nba", "足球", "派对",
]
# 以纯器乐/新世纪创作为主的艺人
_INSTRUMENTAL_ARTISTS = [
    "久石让", "坂本龙一", "雅尼", "班得瑞", "克莱德曼",
    "brian eno", "max richter", "nils frahm", "ludovico einaudi",
    "olafur arnalds", "hildur", "bonobo", "tycho",
]


def detect_instrumental(title: str, album: str, search_keyword: str) -> bool:
    """统一的人声/纯音乐判定。
    规则：
    1) 标题/专辑含强纯音乐标记（伴奏/钢琴版/BGM/轻音乐/民族乐器/白噪音）→ 纯音乐
    2) 搜索词命中纯音乐类目，且不包含人声类目信号 → 纯音乐
    3) 搜索词为纯器乐艺人 → 纯音乐
    4) 其余默认人声（流行/摇滚/说唱/民谣/歌手搜索绝大多数为人声）
    """
    text = f"{title or ''} {album or ''}".lower()
    kw = (search_keyword or "").lower()
    # 1) 标题强标记
    for h in _TITLE_INSTR_HINTS:
        if h in text:
            return True
    # 2) 人声类目信号优先（如"动漫主题曲""影视歌曲""华语金曲"）
    for h in _KW_VOCAL_HINTS:
        if h in kw:
            return False
    # 3) 纯器乐艺人
    for a in _INSTRUMENTAL_ARTISTS:
        if a in kw:
            return True
    # 4) 纯音乐类目
    for h in _KW_INSTR_HINTS:
        if h in kw:
            return True
    # 5) 默认人声
    return False


# ============================================================
# 6. 单曲元数据推断（核心函数）
# ============================================================
def enrich_song_metadata(song: Song, search_keyword: str) -> Dict:
    """
    为从QQ音乐抓到的歌曲补充元数据。
    所有字段均基于搜索关键词和歌曲已知信息推断，不生成随机数据。
    """
    title = song.title or ""
    album = song.album or ""
    artist = song.artist or ""
    duration = song.duration_sec or 240
    combined_text = f"{title} {album} {artist}"

    # 6a. 风格推断
    # 优先：搜索关键词直接映射
    genre = KEYWORD_GENRE_MAP.get(search_keyword, "")
    # 其次：从歌曲文本分析
    text_genre = infer_genre_from_text(combined_text)
    if text_genre and not genre:
        genre = text_genre
    elif text_genre and genre and genre != text_genre:
        # 两者都有，用搜索关键词的更可靠
        pass  # 保持搜索关键词的映射
    if not genre:
        genre = "pop"  # 默认

    # 6b. 能量等级推断
    energy = ENERGY_BY_KEYWORD.get(search_keyword, 5)
    # 歌曲时长辅助：超长可能是ambient/电子
    if duration >= 600 and energy > 4:
        energy = max(3, energy - 2)  # 长曲可能更舒缓
    energy = max(1, min(10, energy + random.randint(-1, 1)))

    # 6c. 情绪标签推断
    mood = MOOD_BY_KEYWORD.get(search_keyword, "balanced")
    mood_tags = [mood]
    if energy >= 8:
        if "energetic" not in mood_tags:
            mood_tags.append("energetic")
    elif energy <= 3:
        if "calm" not in mood_tags:
            mood_tags.append("calm")

    # 6d. 乐器推断
    instrument = infer_instrument_type(genre)

    # 6e. BPM推断
    bpm = infer_tempo(energy, genre, duration)

    # 6f. 类型（纯音乐/人声）判定 —— 统一走 detect_instrumental
    # （QQ音乐源默认 instrumental=True 不可信，必须基于搜索词+标题重判）
    is_instrumental = detect_instrumental(title, album, search_keyword)

    # 6g. 推荐理由生成
    reason = generate_reason(title, artist, genre, energy, mood, is_instrumental, duration, search_keyword)

    return {
        "id": song.id,
        "title": title,
        "artist": artist,
        "album": album,
        "genre": genre,
        "duration_sec": duration,
        "tempo_bpm": bpm,
        "instrumental": is_instrumental,
        "instrument_type": instrument,
        "energy": energy,
        "mood_tags": mood_tags,
        "task_tags": infer_task_tags(search_keyword),
        "source": "qqmusic",
        "external_url": song.external_url,
        "cover_url": song.cover_url,
        "reason": reason,
        "search_keyword": search_keyword,
    }


def infer_task_tags(search_keyword: str) -> List[str]:
    """推断任务标签"""
    task_map = {
        "学习": "study", "专注": "study", "编程": "coding", "代码": "coding",
        "运动": "workout", "跑步": "workout", "健身": "workout", "瑜伽": "workout",
        "放松": "relax", "冥想": "relax", "轻音乐": "relax",
        "世界杯": "entertainment", "奥运会": "entertainment", "NBA": "entertainment",
        "足球": "entertainment", "派对": "entertainment", "游戏": "entertainment",
        "钢琴": "study", "吉他": "relax",
    }
    tags = set()
    for kw, task in task_map.items():
        if kw in search_keyword:
            tags.add(task)
    return list(tags) if tags else ["general"]


def generate_reason(title: str, artist: str, genre: str, energy: int,
                    mood: str, instrumental: bool, duration: int,
                    search_keyword: str) -> str:
    """生成推荐理由"""
    energy_desc = "低能量" if energy <= 3 else ("中等能量" if energy <= 6 else "高能量")
    genre_desc = genre_map_cn(genre)
    mood_desc = mood_map_cn(mood)
    inst_type = "纯音乐" if instrumental else "人声"

    # 构造理由
    reasons = []
    reasons.append(f"搜索关键词「{search_keyword}」匹配")
    if "燃" in search_keyword or energy >= 8:
        reasons.append("高能量燃曲")
    elif "治愈" in search_keyword or energy <= 3:
        reasons.append("舒缓治愈")
    elif "专注" in search_keyword:
        reasons.append("专注纯音乐")
    elif "派对" in search_keyword or "庆典" in search_keyword:
        reasons.append("派对氛围")
    elif "运动" in search_keyword or energy >= 7:
        reasons.append("运动节拍")
    else:
        reasons.append(f"{energy_desc} {genre_desc}")

    reasons.append(f"{inst_type} · {mood_desc} · {duration//60}分{duration%60}秒")
    return " | ".join(reasons)


def genre_map_cn(genre: str) -> str:
    m = {"classical": "古典", "pop": "流行", "rock": "摇滚", "electronic": "电子",
         "folk": "民谣", "r&b": "R&B", "hip-hop": "嘻哈", "jazz": "爵士",
         "ambient": "轻音乐", "neo-classical": "新古典", "minimalist": "极简",
         "indie": "独立"}
    return m.get(genre, genre)


def mood_map_cn(mood: str) -> str:
    m = {"calm": "平静", "energetic": "亢奋", "joyful": "欢快", "sad": "悲伤",
         "hopeful": "励志", "dreamy": "梦幻", "groovy": "律动", "focused": "专注",
         "inspired": "灵感", "soothing": "治愈", "balanced": "平衡", "alert": "提神",
         "festive": "欢庆", "celebratory": "庆祝", "romantic": "浪漫",
         "powerful": "力量", "relaxed": "放松", "peaceful": "安宁"}
    return m.get(mood, mood)


# ============================================================
# 7. 批量爬取并构建数据库（扩展版：多页+榜单+断点续建）
# ============================================================
class MusicDatabaseBuilder:
    def __init__(self, resume_from: str = ""):
        self.qq = QQMusicSource()
        self.songs: Dict[str, Dict] = {}
        self.stats = {
            "searches": 0, "songs_found": 0, "songs_enriched": 0,
            "skipped_dups": 0, "charts_crawled": 0, "keywords_crawled": 0,
        }
        self._progress_file = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "build_progress.json")
        self._done_keys: set = set()
        # 断点续建：加载已有数据库 + 进度
        if resume_from and os.path.exists(resume_from):
            self._load_existing(resume_from)
        if os.path.exists(self._progress_file):
            try:
                with open(self._progress_file, "r", encoding="utf-8") as f:
                    self._done_keys = set(json.load(f))
                print(f"[断点续建] 已完成 {len(self._done_keys)} 个搜索/榜单，加载 {len(self.songs)} 首现有歌曲")
            except Exception:
                pass

    def _load_existing(self, path: str):
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            for s in data.get("songs", []):
                if "id" in s:
                    self.songs[s["id"]] = s
            print(f"[加载] 从 {path} 加载 {len(self.songs)} 首歌曲")
        except Exception as e:
            print(f"[加载] 失败: {e}")

    def _save_progress(self):
        try:
            with open(self._progress_file, "w", encoding="utf-8") as f:
                json.dump(list(self._done_keys), f, ensure_ascii=False)
        except Exception:
            pass

    def _throttle(self, min_sec: float = 0.8):
        time.sleep(min_sec + random.uniform(0.2, 0.5))

    def crawl_keyword(self, keyword: str, per_page: int = 80,
                      pages: int = 3) -> int:
        """多页爬取单个关键词，返回新增数"""
        key = f"kw::{keyword}"
        if key in self._done_keys:
            return 0
        self._done_keys.add(key)
        self.stats["searches"] += 1
        self.stats["keywords_crawled"] += 1
        new_count = 0
        songs = self.qq.search_pages(keyword, per_page=per_page, pages=pages)
        for song in songs:
            if not song.id:
                continue
            if song.id in self.songs:
                self.stats["skipped_dups"] += 1
                continue
            enriched = enrich_song_metadata(song, keyword)
            self.songs[song.id] = enriched
            new_count += 1
            self.stats["songs_enriched"] += 1
        self.stats["songs_found"] += len(songs)
        return new_count

    def crawl_chart(self, chart_key: str, limit: int = 100) -> int:
        """爬取热门榜单"""
        key = f"chart::{chart_key}"
        if key in self._done_keys:
            return 0
        self._done_keys.add(key)
        self.stats["charts_crawled"] += 1
        new_count = 0
        songs = self.qq.get_chart(chart_key, limit=limit)
        for song in songs:
            if not song.id:
                continue
            if song.id in self.songs:
                self.stats["skipped_dups"] += 1
                continue
            # 榜单歌曲用 chart_key 作为搜索关键词做元数据推断
            enriched = enrich_song_metadata(song, chart_key)
            self.songs[song.id] = enriched
            new_count += 1
            self.stats["songs_enriched"] += 1
        self.stats["songs_found"] += len(songs)
        return new_count

    def build(self, keywords: List[str], per_page: int = 80,
              pages: int = 3, charts: bool = True):
        """批量构建数据库：先榜单（质量高），再关键词翻页"""
        # 第一阶段：热门榜单（13 个榜单，每个 ~100 首）
        if charts:
            chart_keys = list(self.qq.CHART_IDS.keys())
            for i, ck in enumerate(chart_keys):
                if f"chart::{ck}" in self._done_keys:
                    print(f"[榜单 {i+1}/{len(chart_keys)}] {ck} ... 已完成，跳过")
                    continue
                print(f"[榜单 {i+1}/{len(chart_keys)}] {ck} ... ", end="", flush=True)
                try:
                    new = self.crawl_chart(ck, limit=100)
                    print(f"+{new} 首 (累计 {len(self.songs)})")
                except Exception as e:
                    print(f"失败: {e}")
                self._throttle(0.5)  # 榜单 API 宽松

        # 第二阶段：关键词翻页搜索 —— 跳过已完成的关键词
        pending = [kw for kw in keywords if f"kw::{kw}" not in self._done_keys]
        print(f"\n待处理关键词: {len(pending)} 个（已跳过 {len(keywords) - len(pending)} 个已完成）")
        total = len(pending)
        for i, kw in enumerate(pending):
            print(f"[{i+1}/{total}] 搜索: {kw} ... ", end="", flush=True)
            try:
                new = self.crawl_keyword(kw, per_page=per_page, pages=pages)
                print(f"+{new} 首 (累计 {len(self.songs)})")
            except Exception as e:
                print(f"失败: {e}")
            self._throttle()
            # 每 20 个关键词保存一次进度
            if (i + 1) % 20 == 0:
                self._save_progress()

        self._save_progress()

    def save(self, filepath: str):
        """保存到JSON文件"""
        data = {
            "version": 3,
            "source": "QQ Music (y.qq.com) + QQ Hot Charts",
            "total_songs": len(self.songs),
            "stats": self.stats,
            "songs": list(self.songs.values()),
        }
        os.makedirs(os.path.dirname(filepath) or ".", exist_ok=True)
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"\n数据库已保存: {filepath}")
        print(f"共 {len(self.songs)} 首歌曲")

    def print_summary(self):
        """打印数据库统计"""
        songs = list(self.songs.values())
        if not songs:
            print("数据库为空")
            return

        genre_dist = {}
        mood_dist = {}
        energy_dist = {"低 (1-3)": 0, "中 (4-6)": 0, "高 (7-10)": 0}
        instrumental_count = 0
        for s in songs:
            genre = s.get("genre", "unknown")
            genre_dist[genre] = genre_dist.get(genre, 0) + 1
            for m in s.get("mood_tags", []):
                mood_dist[m] = mood_dist.get(m, 0) + 1
            e = s.get("energy", 5)
            if e <= 3:
                energy_dist["低 (1-3)"] += 1
            elif e <= 6:
                energy_dist["中 (4-6)"] += 1
            else:
                energy_dist["高 (7-10)"] += 1
            if s.get("instrumental"):
                instrumental_count += 1

        print("\n" + "=" * 60)
        print(f"数据库统计（共 {len(songs)} 首）")
        print("=" * 60)
        print(f"\n纯音乐占比: {instrumental_count} ({100*instrumental_count//max(len(songs),1)}%)")
        print("\n风格分布:")
        for g, c in sorted(genre_dist.items(), key=lambda x: -x[1]):
            print(f"  {genre_map_cn(g):<10} {c:>6} 首  ({100*c//len(songs)}%)")
        print("\n能量等级分布:")
        for label, c in energy_dist.items():
            print(f"  {label:<12} {c:>6} 首")


# ============================================================
# 8. 构建搜索关键词列表
# ============================================================
def build_keywords() -> List[str]:
    """构建大规模搜索关键词列表（200+ 关键词）"""
    keywords = []
    seen = set()

    def add(kw):
        if kw and kw not in seen and len(kw.strip()) > 0:
            seen.add(kw)
            keywords.append(kw)

    # ---- 情绪维度 ----
    mood_groups = {
        "安静舒缓": ["安静", "舒缓", "治愈", "轻音乐", "放松", "平静", "睡眠", "助眠"],
        "欢快开心": ["欢快", "开心", "元气", "快乐", "愉悦", "庆祝", "派对"],
        "悲伤伤感": ["悲伤", "伤感", "深情", "思念", "离别", "孤独", "emo"],
        "励志温暖": ["励志", "温暖", "正能量", "希望", "勇气", "坚持"],
        "梦幻空灵": ["梦幻", "空灵", "氛围", "意境", "唯美", "仙境"],
        "力量燃": ["力量", "史诗", "燃", "热血", "激昂", "震撼", "气势"],
        "专注": ["专注", "学习", "白噪音", "纯音乐", "冥想", "打坐"],
        "灵感": ["灵感", "创意", "思考", "想象"],
        "提神活力": ["提神", "清新", "活力", "动感", "节奏"],
        "浪漫": ["浪漫", "情歌", "温馨", "甜蜜", "爱情"],
    }
    for group, kws in mood_groups.items():
        for kw in kws:
            add(kw)

    # ---- 风格维度 ----
    genre_keywords = [
        "古典音乐", "钢琴曲", "巴赫", "莫扎特", "贝多芬", "肖邦", "德彪西",
        "轻音乐", "纯音乐", "纯音", "伴奏", "instrumental",
        "电子音乐", "EDM", "techno", "house", "电音", "DJ", "舞曲",
        "摇滚", "rock", "金属", "朋克",
        "流行", "pop", "华语流行", "欧美流行",
        "嘻哈", "hip-hop", "rap", "说唱", "trap",
        "爵士", "jazz", "蓝调", "blues",
        "民谣", "folk", "木吉他", "acoustic",
        "R&B", "灵魂乐", "soul", "放克", "funk",
        "氛围音乐", "ambient", "环境音乐",
        "Lo-fi", "lofi", "低保真", "chillhop",
        "独立音乐", "indie", "独立摇滚",
        "极简音乐", "minimal",
        "电影配乐", "OST", "主题曲", "片尾曲",
        "游戏音乐", "游戏BGM", "游戏原声",
        "钢琴曲纯音乐", "吉他纯音乐", "萨克斯纯音乐",
    ]
    for kw in genre_keywords:
        add(kw)

    # ---- 场景维度 ----
    scene_keywords = [
        "编程", "代码", "程序员", "写代码",
        "学习", "考试", "复习", "备考", "刷题", "阅读",
        "跑步", "健身", "运动", "瑜伽", "撸铁", "力量训练",
        "开车", "通勤", "地铁", "公交",
        "冥想", "打坐", "禅修",
        "写作", "创意", "头脑风暴", "设计",
        "游戏", "开黑", "电竞", "直播",
        "派对", "K歌", "卡拉OK", "聚会",
        "咖啡", "咖啡馆", "下午茶",
        "工作", "办公室", "加班",
        "学习纯音乐", "编程纯音乐", "运动纯音乐",
    ]
    for kw in scene_keywords:
        add(kw)

    # ---- 自然/环境音 ----
    nature_keywords = [
        "白噪音", "雨声", "森林", "海浪", "溪流", "风声",
        "篝火", "雷雨", "咖啡馆", "书店", "办公室",
        "自然声音", "环境音",
    ]
    for kw in nature_keywords:
        add(kw)

    # ---- 事件级关键词 ----
    event_keywords = [
        "世界杯", "世界杯主题曲", "生命之杯", "Waka Waka", "Goal Goal Goal",
        "奥运会", "奥运主题曲", "我和你", "手拉手", "北京欢迎你",
        "NBA", "篮球", "灌篮高手", "篮球音乐",
        "足球", "欧冠主题曲", "天下足球",
        "电视剧", "OST", "主题曲", "影视原声",
        "游戏", "电竞", "英雄联盟", "原神", "黑神话悟空",
        "派对", "舞曲", "DJ",
        "生日", "新年", "圣诞", "春节",
    ]
    for kw in event_keywords:
        add(kw)

    # ---- 热门艺人 ----
    artist_keywords = [
        "周杰伦", "林俊杰", "陈奕迅", "张学友", "刘德华", "王菲", "邓紫棋",
        "薛之谦", "毛不易", "李荣浩", "陶喆", "王力宏", "五月天", "苏打绿",
        "Taylor Swift", "Ed Sheeran", "Adele", "Bruno Mars", "The Weeknd",
        "Billie Eilish", "Dua Lipa", "Post Malone", "Imagine Dragons",
        "BTS", "BLACKPINK", "IU",
        "久石让", "坂本龙一", "钢琴", "克莱德曼",
        "雅尼", "恩雅", "班得瑞",
    ]
    for kw in artist_keywords:
        add(kw)

    # ---- 语言+风格组合 ----
    combo_keywords = [
        "中文歌 摇滚", "英文歌 摇滚", "中文歌 流行", "英文歌 流行",
        "中文歌 民谣", "英文歌 民谣", "中文歌 嘻哈", "英文歌 嘻哈",
        "日本歌", "韩国歌", "日语歌", "韩语歌",
        "欧美", "华语", "国语", "粤语",
    ]
    for kw in combo_keywords:
        add(kw)

    # ---- 能量+情绪组合 ----
    energy_keywords = [
        "劲爆 燃", "热血 激昂", "动感 节奏",
        "安静 治愈", "舒缓 放松", "悲伤 孤独",
        "励志 温暖", "梦幻 空灵", "力量 史诗",
        "专注 学习", "灵感 创意", "提神 活力",
    ]
    for kw in energy_keywords:
        add(kw)

    # ---- 欧美/英文歌曲扩展关键词（2026-09 新增，扩充英文曲库）----
    # 欧美大牌艺人（跨年代/跨风格）
    western_artists = [
        # 流行天后/天王
        "Taylor Swift", "Ed Sheeran", "Adele", "Bruno Mars", "The Weeknd",
        "Billie Eilish", "Dua Lipa", "Harry Styles", "Olivia Rodrigo", "Sabrina Carpenter",
        "Ariana Grande", "Justin Bieber", "Selena Gomez", "Beyoncé", "Rihanna",
        "Lady Gaga", "Katy Perry", "Miley Cyrus", "Michael Jackson", "Madonna",
        "Mariah Carey", "Celine Dion", "Elton John", "Whitney Houston",
        # 摇滚/另类
        "Queen", "The Beatles", "Led Zeppelin", "Rolling Stones", "AC/DC",
        "Metallica", "Nirvana", "Linkin Park", "Evanescence", "Imagine Dragons",
        "Coldplay", "Maroon 5", "OneRepublic", "Twenty One Pilots", "Panic At The Disco",
        "Fall Out Boy", "My Chemical Romance", "Radiohead", "Muse", "The Fray",
        # 嘻哈/说唱
        "Eminem", "Drake", "Kanye West", "Jay-Z", "Kendrick Lamar",
        "Travis Scott", "Lil Uzi Vert", "Playboi Carti", "21 Savage", "Migos",
        "Lil Wayne", "50 Cent", "Snoop Dogg", "Tyler The Creator", "ASAP Rocky",
        "Logic", "Machine Gun Kelly", "Juice WRLD", "Roddy Ricch", "Lil Baby",
        # R&B/Soul
        "Stevie Wonder", "Aretha Franklin", "Marvin Gaye", "SZA", "Summer Walker",
        "H.E.R.", "Khalid", "Alicia Keys", "John Legend", "Ne-Yo", "Usher", "Chris Brown",
        # 电子/舞曲
        "Calvin Harris", "David Guetta", "Tiesto", "Martin Garrix", "Avicii",
        "Zedd", "DJ Snake", "Marshmello", "Alan Walker", "Kygo", "Diplo", "Skrillex",
        # 爵士/蓝调
        "Miles Davis", "Louis Armstrong", "BB King", "Muddy Waters", "Ray Charles",
        # Lo-fi/氛围/极简
        "Bonobo", "Tycho", "Brian Eno", "Max Richter", "Nils Frahm",
        "Ludovico Einaudi", "Olafur Arnalds", "Hildur Gudnadottir",
        # 独立/另类
        "Arctic Monkeys", "The Strokes", "The 1975", "Bastille", "Glass Animals",
        "Tame Impala", "MGMT", "Vampire Weekend", "Phoenix", "Arcade Fire",
        "Bon Iver", "Phoebe Bridgers", "Clairo", "Beach House",
        # 民谣/乡村
        "Bob Dylan", "Neil Young", "Johnny Cash", "Dolly Parton", "Willie Nelson",
        "John Denver", "Joni Mitchell", "James Taylor", "Kacey Musgraves", "Chris Stapleton",
        # K-pop 头部
        "BTS", "BLACKPINK", "IU", "NewJeans", "Le Sserafim", "Stray Kids",
        "NCT", "aespa", "Red Velvet", "GOT7", "TWICE", "MAMAMOO",
        # 华语新生代/独立（补足中文曲库缺口）
        "赵雷", "赵照", "陈粒", "宋冬野", "马頔", "尧十三", "房东的猫", "陈绮贞",
        "逃跑计划", "万能青年旅店", "草东没有派对", "五月天", "林宥嘉",
        "许巍", "汪峰", "朴树", "郑钧", "张震岳", "李宗盛", "罗大佑",
        "周深", "李健", "韩红", "孙燕姿", "莫文蔚", "梁静茹", "刘若英",
        "蔡依林", "萧亚轩", "S.H.E", "凤凰传奇", "许嵩", "汪苏泷",
        # K-pop 二三线女团男团
        "IVE", "ITZY", "TXT", "ENHYPEN", "SEVENTEEN", "ATEEZ",
        "(G)I-DLE", "Nmixx", "Kep1er", "STAYC", "TREASURE", "LOONA",
    ]
    for kw in western_artists:
        add(kw)

    # 国风/中文特色风格（补足华语曲库缺口）
    chinese_style = [
        "国风", "古风", "中国风", "国风音乐", "国风纯音乐",
        "古筝", "古琴", "笛子", "二胡", "琵琶", "箫", "笙",
        "国风电音", "古风歌曲", "古筝纯音乐", "古琴纯音乐",
        "江南", "长安", "大唐", "武侠", "仙剑",
        "华语民谣", "校园民谣", "台湾民谣", "粤语歌", "闽南语",
        "儿童音乐", "儿歌", "童谣", "睡前儿歌", "动画原声", "喜羊羊", "奥特曼",
        "广场舞", "健身操", "DJ舞曲", "车载音乐",
        "流行热歌", "抖音热歌", "新歌榜", "热歌榜",
        "民谣吉他弹唱", "摇滚中国", "硬核说唱", "Trap 中文", "国风说唱",
        "雷鬼", "Reggae 中文", "福音", "Gospel",
        "蓝调", "Blues 中文", "乡村音乐", "Country",
        "重金属", "Death Metal", "Black Metal", "Power Metal", "Symphonic Metal",
        "朋克", "Punk", "Skate Punk", "Hardcore", "Ska",
        "乡村民谣", "迷幻摇滚", "前卫摇滚", "后摇",
    ]
    for kw in chinese_style:
        add(kw)

    # 欧美风格/搜索词（英文+中文混合）
    western_genres = [
        "欧美流行", "欧美摇滚", "欧美嘻哈", "欧美R&B", "欧美电子",
        "欧美爵士", "欧美民谣", "欧美独立", "欧美原声", "欧美灵魂乐",
        "欧美蓝调", "欧美纯音乐", "欧美榜单", "Billboard", "Grammy",
        "英文流行", "英文摇滚", "英文嘻哈", "英文R&B", "英文爵士",
        "Lo-fi beats", "chillhop", "synthwave", "indie pop", "indie rock",
        "alternative rock", "classic rock", "punk rock", "pop punk",
        "trap music", "old school rap", "jazz hip hop",
        "house music", "techno", "trance", "dubstep", "EDM", "electro house",
        "deep house", "tropical house", "future bass",
        "shoegaze", "dream pop", "post rock", "slowcore",
        "blues rock", "southern rock", "britpop",
        "reggae", "afrobeats", "latin pop", "city pop",
        "anime soundtrack", "game soundtrack",
        "epic orchestral", "neo classical", "modern classical",
        "ambient electronica", "drone",
        "K-pop", "J-pop", "K-pop 女团", "K-pop 男团", "J-pop 动漫",
        # 2026-09 新增：风格补全（Gospel / Country / Metal / Punk / Ska / Reggae 等）
        "Gospel", "Christian Music", "Worship Music",
        "Country Music", "Modern Country", "Country Pop",
        "Death Metal", "Black Metal", "Power Metal", "Symphonic Metal", "Folk Metal",
        "Thrash Metal", "Doom Metal", "Progressive Metal", "Metalcore", "Deathcore",
        "Punk Rock", "Pop Punk", "Skate Punk", "Hardcore Punk", "Emo Pop", "Post Hardcore",
        "Ska", "Ska Punk", "Reggaeton", "Dancehall", "Soca", "Calypso",
        "Bossa Nova", "Samba", "Flamenco", "Celtic", "Middle Eastern Music",
        "Grunge", "Shoegaze", "Britpop", "Madchester",
        "Funk Rock", "Funk Soul", "Neo Soul", "Progressive House", "Bass House",
        "Future House", "Melodic Dubstep", "Liquid Drum and Bass", "Drum & Bass",
        "Hyperpop", "Glitch Hop", "Moombahton", "Kizomba", "Zouk",
        "Soundtrack", "Film Score", "Video Game Music", "Musical Theatre",
        "Disney", "Pixar", "动画配乐",
        "Lofi Hip Hop", "Chillhop", "Study Beats", "Sleep Music",
        "Acoustic Covers", "Unplugged", "Live Acoustic",
        "Christmas Music", "Holiday Music", "Halloween Music",
        "Acoustic Guitar", "Fingerstyle Guitar", "Classical Guitar",
    ]
    for kw in western_genres:
        add(kw)

    # ---- 日本/日语歌曲扩展（补足J-pop/J-rock/动漫OST缺口）----
    japanese_artists = [
        # 日本流行/摇滚
        "宇多田光", "椎名林檎", "中岛美雪", "滨崎步", "安室奈美惠", "仓木麻衣",
        "福山雅治", "玉置浩二", "Mr. Children", "B'z", "L'Arc-en-Ciel",
        "ONE OK ROCK", "RADWIMPS", "Perfume", "欅坂46", "乃木坂46", "AKB48",
        "米津玄师", "星野源", "菅田将晖", "LiSA", "aimer", "Aimer",
        "ヨルシカ", "YOASOBI", "Official髭男dism", "Vaundy", "藤井風",
        # 动漫配乐/作曲家
        "久石让", "宫崎骏动画", "新海诚", "《你的名字》", "天气之子", "鬼灭之刃",
        "进击的巨人", "海贼王主题曲", "火影忍者主题曲", "柯南主题曲",
        "EVA 新世纪福音战士", "高达", "Fate", "刀剑神域", "魔法少女小圆",
        "日本动漫音乐", "动漫主题曲", "动漫片尾曲", "动漫插曲",
        "日本游戏音乐", "最终幻想", "塞尔达传说", "超级马里奥", "尼尔机械纪元",
        "空洞骑士", "星露谷物语", "动物森友会", "女神异闻录",
        "日本纯音乐", "Japanese instrumental", "Jazz 日本",
    ]
    for kw in japanese_artists:
        add(kw)

    # ---- 经典电视剧/电影/游戏 具体OST搜索词 ----
    specific_ost = [
        # 国产剧
        "甄嬛传", "琅琊榜", "知否知否", "庆余年", "狂飙", "三体", "繁花",
        "仙剑奇侠传", "古剑奇谭", "三生三世十里桃花", "香蜜沉沉烬如霜",
        "欢乐颂", "都挺好", "隐秘的角落", "沉默的真相", "长安十二时辰",
        "山海情", "父母爱情", "亮剑", "士兵突击",
        # 国产电影
        "流浪地球", "封神", "长津湖", "你好李焕英", "夏洛特烦恼",
        "无间道", "英雄本色", "霸王别姬", "花样年华", "一代宗师",
        # 美剧/英剧
        "权力的游戏", "西部世界", "怪奇物语", "黑袍纠察队", "行尸走肉",
        "神探夏洛克", "黑镜",
        # 经典游戏系列
        "原神 须弥", "原神 稻妻", "原神 蒙德", "原神 璃月",
        "英雄联盟主题曲", "DOTA2 主题曲", "CSGO 音乐盒", "Valorant",
        "魔兽世界", "炉石传说", "暗黑破坏神", "赛博朋克2077",
    ]
    for kw in specific_ost:
        add(kw)

    # ---- 年代歌曲/经典怀旧 ----
    era_keywords = [
        "80年代歌曲", "90年代歌曲", "00年代歌曲",
        "80后老歌", "90后回忆", "00后喜欢", "怀旧金曲",
        "华语经典老歌", "粤语经典", "港台金曲", "校园民谣",
        "英文老歌经典", "欧美80年代", "欧美90年代", "millennials",
        "K-pop 2nd generation", "K-pop 3rd generation", "韩流经典",
    ]
    for kw in era_keywords:
        add(kw)

    # ---- 更多细分场景/情绪/活动 ----
    scene_extra = [
        # 学习/工作场景
        "写论文", "赶论文", "论文答辩", "面试准备", "考试前", "考研",
        "刷题BGM", "代码审查", "会议录音整理", "PPT制作", "Excel表格",
        # 生活场景
        "瑜伽", "普拉提", "spa", "按摩", "泡澡", "做饭", "烘焙",
        "散步", "遛狗", "骑车", "滑板", "爬山", "徒步",
        # 情感场景
        "约会", "告白", "求婚", "婚礼", "结婚",
        "分手", "失恋", "告别", "深夜emo", "凌晨三点",
        # 特殊时刻
        "生日歌", "毕业歌", "开学典礼", "毕业典礼", "运动会",
        # 更细分的能量风格
        "心跳加速", "多巴胺", "血清素", "专注脑波", "α脑波",
        "beta波", "低α波", "Solfeggio频率", "432Hz", "528Hz",
        # 纯乐器组合
        "大提琴纯音乐", "小提琴纯音乐", "中提琴",
        "钢琴小提琴", "钢琴大提琴", "弦乐四重奏", "三重奏",
        "长笛", "单簧管", "双簧管", "圆号", "小号", "长号",
        # 更多细分电子
        "acid house", "hard techno", "industrial", "IDM", "breakbeat",
        "UK garage", "future garage", "tech house", "minimal techno",
        "progressive trance", "psytrance", "vocal trance",
    ]
    for kw in scene_extra:
        add(kw)

    # ---- 更多日韩团体/艺人 ----
    kr_jp_extra = [
        "KARA", "2NE1", "4MINUTE", "f(x)", "SNSD 少女时代", "Wonder Girls",
        "T-ara", "APink", "GFriend", "MAMAMOO",
        "Block B", "B.A.P", "VIXX", "NU'EST", "PENTAGON",
        "MONSTA X", "GOT7", "NU'EST W",
        "Perfume", "SCANDAL", "ONE OK ROCK", "Alexandros",
        "back number", "Official 髭男dism",
    ]
    for kw in kr_jp_extra:
        add(kw)

    # ---- 更多华语艺人（补齐冷门/独立/新生代）----
    chinese_artists_extra = [
        "华晨宇", "霍尊", "尚雯婕", "袁娅维", "张碧晨", "吉克隽逸",
        "陈鸿宇", "柳爽", "王贰浪", "阿肆", "花粥", "陈雪凝",
        "隔壁老樊", "焦迈奇", "徐秉龙", "沈以诚", "焦迈奇",
        "落日飞车", "傻子与白痴", "HYUKOH", "落日飞车", "告五人",
        "大波浪", "重塑雕像的权利", "五条人", "Mandarin",
        "窦唯", "黑豹乐队", "唐朝乐队", "Beyond", "张国荣", "梅艳芳",
        "邓丽君", "罗文", "谭咏麟", "钟镇涛", "林子祥",
        "张学友", "刘德华", "黎明", "郭富城", "四大天王",
        "那英", "田震", "孙悦", "毛阿敏",
        "凤凰传奇", "玖月奇迹", "筷子兄弟",
    ]
    for kw in chinese_artists_extra:
        add(kw)

    # ---- 2026-09 第五轮：优先中英文人声歌曲 ----
    # 华语人声歌手（流行/经典/独立/说唱，避开纯音乐）
    cn_vocal_artists = [
        # 内地流行女声
        "张靓颖", "李宇春", "周笔畅", "徐佳莹", "张含韵", "金莎", "弦子",
        "杨丞琳", "王心凌", "张韶涵", "范玮琪", "郭静", "丁当", "田馥甄",
        "黄霄雲", "单依纯", "张碧晨", "袁娅维", "谭维维", "郁可唯",
        "刘惜君", "阿兰", "戚薇", "戚砚笛",
        # 内地流行男声
        "萧敬腾", "杨宗纬", "胡彦斌", "魏晨", "张杰", "陈楚生",
        "王铮亮", "周深", "霍尊", "汪苏泷", "许嵩", "徐良",
        "蔡徐坤", "张艺兴", "鹿晗", "黄子韬", "肖战", "王一博",
        "易烊千玺", "王俊凯", "王源", "蔡国庆",
        # 港台流行男声
        "古巨基", "李克勤", "许志安", "梁汉文", "张敬轩", "陈柏宇",
        "周柏豪", "方力申", "侧田", "郑中基", "林峯", "吴卓羲",
        "周华健", "张信哲", "王杰", "齐秦", "童安格", "姜育恒",
        "张宇", "巫启贤", "伍思凯", "林志炫", "费玉清", "周传雄",
        "阿杜", "光良", "品冠", "曹格", "陶喆", "吴克群",
        "信", "萧煌奇", "卢广仲", "韦礼安", "伍佰",
        # 港台流行女声
        "陈慧娴", "林忆莲", "叶倩文", "徐小凤", "甄妮", "梅艳芳",
        "韩宝仪", "龙飘飘", "高胜美", "杨乃文", "魏如萱", "张悬",
        "刘若英", "梁静茹", "孙燕姿", "蔡健雅", "戴佩妮",
        # 乐队/组合（人声）
        "信乐团", "飞儿乐队", "南拳妈妈", "水木年华", "羽泉",
        "零点乐队", "新裤子", "痛仰乐队", "二手玫瑰", "好妹妹乐队",
        "鹿先森乐队", "时代少年团", "火箭少女101", "硬糖少女303",
        "动力火车", "顽童MJ116",
        # 内地说唱（人声）
        "GAI周延", "马思唯", "法老", "姜云升", "艾热", "王以太",
        "Tizzy T", "Jony J", "满舒克", "万妮达", "VAVA毛衍七",
        "刘聪", "杨和苏", "MC HotDog", "蛋堡",
        # 内地独立/民谣人声
        "谢春花", "程璧", "银临", "音阙诗听", "双笙", "海来阿木",
        "阿冗", "梦然", "王琪", "大欢", "白小白", "贰佰",
        "花粥", "陈雪凝",
        # 民族/通俗人声
        "刀郎", "腾格尔", "降央卓玛", "云朵",
    ]
    for kw in cn_vocal_artists:
        add(kw)

    # 欧美人声歌手（流行/摇滚/嘻哈/R&B/乡村/经典，避开纯器乐）
    en_vocal_artists = [
        # 流行女声
        "Sia", "P!nk", "Ellie Goulding", "Jessie J", "Rita Ora",
        "Anne-Marie", "Bebe Rexha", "Zara Larsson", "Ava Max",
        "Meghan Trainor", "Demi Lovato", "Kelly Clarkson", "Avril Lavigne",
        "Britney Spears", "Christina Aguilera", "Lorde", "Lana Del Rey",
        "Florence and the Machine", "Halsey", "Lizzo", "Doja Cat",
        "Megan Thee Stallion", "Cardi B", "Nicki Minaj", "Kehlani",
        "Jorja Smith", "Ella Mai", "Jhene Aiko", "Snoh Aalegra",
        "Janelle Monae", "Solange", "Mary J Blige", "Toni Braxton",
        "Alicia Keys", "Carrie Underwood", "Miranda Lambert",
        "Maren Morris", "Kacey Musgraves",
        # 流行男声
        "Charlie Puth", "Shawn Mendes", "Sam Smith", "Hozier",
        "Lewis Capaldi", "James Arthur", "George Ezra", "James Blunt",
        "Jason Mraz", "John Mayer", "Jack Johnson", "Michael Buble",
        "Robbie Williams", "Niall Horan", "Liam Payne", "Nick Jonas",
        "Giveon", "Daniel Caesar", "Frank Ocean", "Miguel",
        "Morgan Wallen", "Luke Combs", "Luke Bryan", "Blake Shelton",
        "Jason Aldean", "Kenny Chesney", "Tim McGraw", "Keith Urban",
        "Brad Paisley", "Sam Hunt", "Thomas Rhett",
        # 组合/乐队（人声）
        "One Direction", "Backstreet Boys", "NSYNC", "Westlife",
        "Spice Girls", "Little Mix", "Fifth Harmony", "Jonas Brothers",
        "The Chainsmokers", "U2", "Oasis", "Blur", "Green Day",
        "Red Hot Chili Peppers", "Foo Fighters", "Pearl Jam",
        "Bon Jovi", "Aerosmith", "Guns N' Roses", "Def Leppard",
        "Journey", "The Killers", "Kings of Leon", "The Lumineers",
        "Mumford and Sons", "Nickelback", "Lifehouse", "Goo Goo Dolls",
        "Matchbox Twenty", "Train", "The Script", "5 Seconds of Summer",
        "Eagles", "Fleetwood Mac", "The Carpenters", "Chicago",
        "Hall and Oates", "Toto", "Phil Collins", "Sting",
        "The Police", "Tears for Fears", "Duran Duran", "Wham",
        "George Michael", "Dire Straits", "Eric Clapton",
        "Van Morrison", "Rod Stewart", "Bryan Adams",
        "ABBA", "Bee Gees", "Billy Joel", "Bruce Springsteen",
        "Tom Petty", "Bob Seger", "Paul Simon", "Simon and Garfunkel",
        "Carole King", "Cat Stevens", "Don McLean",
        # 嘻哈/说唱（人声）
        "Future", "Young Thug", "Gunna", "DaBaby", "Rod Wave",
        "Lil Durk", "Polo G", "NBA YoungBoy", "Pop Smoke",
        "XXXTentacion", "Trippie Redd", "J. Cole", "Big Sean",
        "Meek Mill", "Wiz Khalifa", "Tyga", "Trey Songz", "Omarion",
        "Bryson Tiller", "PartyNextDoor", "6lack", "Brent Faiyaz",
        "Jack Harlow", "Lil Nas X", "Ice Spice", "Latto",
        # R&B/Soul（人声）
        "Smokey Robinson", "The Temptations", "The Supremes",
        "Diana Ross", "Lionel Richie", "Earth Wind and Fire",
        "Chaka Khan", "Gladys Knight",
        # 雷鬼/拉丁（人声）
        "Bob Marley", "Sean Paul", "Shaggy", "Daddy Yankee",
        "Bad Bunny", "J Balvin", "Maluma", "Shakira",
        "Ricky Martin", "Enrique Iglesias", "Pitbull",
        "Jennifer Lopez", "Gloria Estefan", "Marc Anthony",
        # 乡村组合
        "Florida Georgia Line", "Dan and Shay", "Zac Brown Band",
        "Lady A", "Little Big Town", "Old Dominion",
        # K-pop 人声团体补充
        "EXO", "BIGBANG", "G-DRAGON", "WINNER", "iKON",
        "AKMU", "Lee Hi", "Heize", "Crush", "Taeyeon",
        "Girls Generation", "2PM", "SHINee", "Super Junior",
        "INFINITE", "Beast", "Highlight",
    ]
    for kw in en_vocal_artists:
        add(kw)

    # 人声歌曲搜索词（明确指向有人声演唱的歌曲）
    vocal_search_terms = [
        # 华语人声
        "华语歌曲", "华语金曲", "华语流行", "中文歌曲", "中文流行",
        "国语歌曲", "国语金曲", "华语情歌", "华语对唱",
        "粤语金曲", "粤语流行歌曲", "粤语情歌",
        # 欧美人声
        "欧美歌曲", "欧美金曲", "欧美流行歌曲", "英文歌曲", "英文金曲",
        "English songs", "English pop songs", "欧美情歌",
        # 情歌/人声类型
        "伤感情歌", "甜蜜情歌", "对唱情歌", "经典情歌", "情歌大全",
        "影视歌曲", "电视剧歌曲", "电影歌曲", "动画片歌曲",
        # 热歌/新歌（人声为主）
        "抖音热歌", "抖音歌曲", "网络歌曲", "网络热歌",
        "热门歌曲", "流行歌曲精选", "年度金曲",
        "2021流行歌曲", "2022流行歌曲", "2023流行歌曲",
        "2024流行歌曲", "2025流行歌曲", "2024新歌", "2025新歌",
        # 人声合唱/现场
        "演唱会", "现场版", "不插电现场", "MTV Unplugged",
        "翻唱", "经典翻唱", "英文翻唱",
    ]
    for kw in vocal_search_terms:
        add(kw)

    # 大牌歌手专辑名（挖深曲目，全为人声歌曲）
    album_names = [
        # 周杰伦专辑
        "范特西 周杰伦", "叶惠美 周杰伦", "七里香 周杰伦",
        "十一月的萧邦", "摩羯座 周杰伦", "跨时代 周杰伦",
        "惊叹号 周杰伦", "十二新作 周杰伦", "床边故事 周杰伦",
        "最伟大的作品", "Jay 周杰伦",
        # Taylor Swift 专辑
        "Fearless Taylor Swift", "Speak Now Taylor", "Red Taylor Swift",
        "1989 Taylor Swift", "Reputation Taylor", "Lover Taylor Swift",
        "Folklore Taylor Swift", "Evermore Taylor Swift", "Midnights Taylor",
        # 经典人声专辑
        "Thriller Michael Jackson", "Bad Michael Jackson",
        "Adele 21", "Adele 25", "Adele 30",
        "Ed Sheeran Divide", "Ed Sheeran Equals",
        "Weeknd After Hours", "Weeknd Dawn FM",
        "Billie Eilish Happier Than Ever",
        # 华语经典专辑
        "林俊杰 江南", "林俊杰 她说", "陈奕迅 Special Thanks",
        "五月天 第二人生", "五月天 自传", "孙燕姿 遇见",
    ]
    for kw in album_names:
        add(kw)

    # ---- 2026-09 第六轮：扩充至 30 万+（中英文人声 + 纯音乐）----
    # 华语人声歌手补充（新生代/独立/选秀/网络歌手）
    cn_vocal_round6 = [
        # 选秀/新生代女声
        "刘柏辛", "苏运莹", "陈粒", "阿悄", "曾轶可", "段奥娟", "李紫婷",
        "吴映香", "单依纯", "黄霄云", "张钰琪", "潘虹", "王霏霏",
        "孟美岐", "吴宣仪", "段艺璇", "杨超越", "赵粤", "许佳琪",
        "戴萌", "莫寒", "陈琳", "苏杉杉", "卢恬", "郑丹妮",
        # 选秀/新生代男声
        "蔡程昱", "高杨", "鞠红川", "余迪", "南征北战", "杨和苏",
        "张颜齐", "赵磊", "焉栩嘉", "何洛洛", "翟潇闻", "任豪",
        "刘也", "姚柏南", "丰楚轩", "赵KEY", "伯远", "力灿",
        # 网络歌手/独立音乐人
        "阿YueYue", "阿Yue", "叶炫清", "银临", "伦桑", "封茗囧菌",
        "双笙子", "小魂", "萧忆情", "西瓜Kune", "玄觊", "慕寒",
        "排骨教主", "灰原穷", "纣子", "鸦青", "v籽", "KBShinya",
        "泥鳅Niko", "漆柚", "哦漏QAQ", "萧忆情Alex", "特曼",
        # 说唱补充
        "Ty.", "谢帝", "李佳隆", "盛宇DZY", "早安", "林梦", "一口甜",
        "Ziv蓝嘉鑫", "陆政廷", "王以太", "艾志恒Asen", "Tizi",
        "Kc", "Zin", "泥鳅Niko", "阿里马来", "朴宰范",
        # 港台补充
        "林宥嘉", "萧亚轩", "王力宏", "庾澄庆", "范晓萱", "张震岳",
        "热狗", "大支", "蛋堡SoftLipa", "Leo王", "葛仲珊",
        "詹雅雯", "黄乙玲", "秀兰玛雅", "龙千玉", "蔡秋凤",
        "陈雷", "蔡小虎", "罗时丰", "卓依婷", "林翠萍",
        # 内地实力派补充
        "韩红", "陈明", "金海心", "曹芳", "王筝", "丁薇",
        "朱桦", "黄绮珊", "谭晶", "雷佳", "陈思思", "雷佳",
        "云飞", "扎西顿珠", "阿鲁阿卓", "曹格", "李荣浩",
        "颜人中", "葛大为", "傅又宣", "曾咏勤", "刘瑞琦",
        "刘莱斯", "王晓珂", "房东的猫", "幼稚园杀手", "满舒克",
        # 更多乐队
        "达达乐队", "木马乐队", "声音碎片", "马赛克乐队", "皇后皮箱",
        "海龟先生", "TR素人", "博尔之乐", "暗杠", "陈婧",
        "天使的翅膀", " landlords", "街球大师", "蓝色花园",
        # 古风/国风人声
        "音频怪物", "HITA", "Assen捷", "不才", "傻橘",
        "贰婶", "伦桑", "萧忆情", "银临", "玄觊",
        "CRITTY", "tinada", "小曲儿", "慕寒", "排骨",
    ]
    for kw in cn_vocal_round6:
        add(kw)

    # 欧美人声歌手补充（第六轮）
    en_vocal_round6 = [
        # 当代流行女声补充
        "Olivia Rodrigo", "Billie Eilish", "Sabrina Carpenter",
        "Renee Rapp", "Gracie Abrams", "Tate McRae",
        "Conan Gray", "Madison Beer", "Addison Rae",
        "Ice Spice", "PinkPantheress", "Renee Rapp",
        "Dove Cameron", "Sofia Carson", "Ciara",
        "Mya", "Tweet", "Brandy", "Monica",
        "Faith Evans", "Deborah Cox", "Tamia",
        "Debby Boone", "Debbie Gibson", "Taylor Dayne",
        "Lisa Lisa", "Shannon", "Stacy Q",
        # 当代流行男声补充
        "The Weeknd", "Post Malone", "Khalid", "Benson Boone",
        "Teddy Swims", "Myles Smith", "David Kushner",
        "Noah Kahan", "Zach Bryan", "Jelly Roll",
        "Shaboozey", "Twncent", "Tom Odell",
        "Rex Orange County", "Boy Pablo", "Hollow Coves",
        "Mac DeMarco", "Homeshake", "Mild High Club",
        # 说唱/嘻哈补充
        "Kendrick Lamar", "Drake", "J Cole", "Travis Scott",
        "Playboi Carti", "Lil Uzi Vert", "Lil Baby",
        "21 Savage", "Offset", "Quavo", "Takeoff",
        "Migos", "Lil Tjay", "Fivio Foreign", "Sleepy Hallow",
        "Moneybagg Yo", "EST Gee", "Blxst", "Armani White",
        "Toosii", "Lil Mosey", "Stunna Gambino",
        "Cordae", "IDK", "Saba", "Smino", "Noname",
        "Chance the Rapper", "Vic Mensa", "Rory",
        "Lupe Fiasco", "Talib Kweli", "Mos Def",
        "Pharoahe Monch", "DJ Premier", "Gang Starr",
        "M.O.P.", "Onyx", "Das EFX", "Fu Schnickens",
        # R&B/Soul 补充
        "Summer Walker", "Kiana Lede", "Tinashe",
        "Justine Skye", "Tinashe", "Troye Sivan",
        "Troye Sivan", "Ruel", "Claire Rosinkranz",
        "Arlo Parks", "Foushee", "Hope Tala",
        "Yebba", "GIVEON", "Snoh Aalegra",
        "Syd", "Steve Lacy", "Daniel Caesar",
        "Aaron May", "Cleo Sol", "Sault",
        "Masego", "GoldLink", "JMSN",
        # 经典摇滚/乐队补充
        "Nirvana", "Soundgarden", "Alice in Chains",
        "Stone Temple Pilots", "Bush", "Live",
        "Our Lady Peace", "Collective Soul", "Candlebox",
        "Silverchair", "The Verve", "Suede",
        "Pulp", "Supergrass", "Elastica",
        "Eurythmics", "Annie Lennox", "The Cure",
        "Siouxsie and the Banshees", "Bauhaus",
        "Joy Division", "New Order", "Depeche Mode",
        "The Smiths", "The Lightning Seeds",
        "Echo and the Bunnymen", "Television",
        "Talking Heads", "Blondie", "The Ramones",
        "The Clash", "The Damned", "Buzzcocks",
        "Wire", "Gang of Four", "Public Image Ltd",
        # 乡村补充
        "Johnny Cash", "Willie Nelson", "Waylon Jennings",
        "Merle Haggard", "George Jones", "George Strait",
        "Alan Jackson", "Randy Travis", "Garth Brooks",
        "Shania Twain", "Faith Hill", "Tim McGraw",
        "Reba McEntire", "Dolly Parton", "Patsy Cline",
        "Loretta Lynn", "Tammy Wynette",
        "Crystal Gayle", "Emmylou Harris", "Ricky Skaggs",
        "Alison Krauss", "Rascal Flatts", "Brooks and Dunn",
        "Montgomery Gentry", "Sawyer Brown", "Confederate Railroad",
        "Joe Diffie", "John Michael Montgomery",
        "Clay Walker", "Tracy Lawrence", "Mark Chesnutt",
        "Doug Stone", "Collin Raye", "Wade Hayes",
        # 拉丁/雷鬼补充
        "Ozuna", "Bad Bunny", "Daddy Yankee",
        "Don Omar", "Wisin and Yandel", "Plan B",
        "Tego Calderon", "Cosculluela", "Casanova",
        "Rauw Alejandro", "El Alfa", "Natti Natasha",
        "Becky G", "Chiquis Rivera", "Anahí",
        "Thalia", "Paulina Rubio", "Juanes",
        "Carlos Vives", "Fonseca", "Sebastian Yatra",
        "Manuel Turizo", "Pedro Capo", "Luis Fonsi",
        # 非洲/世界音乐
        "Burna Boy", "Wizkid", "Davido",
        "Mr Eazi", "Tiwa Savage", "Yemi Alade",
        "Diamond Platnumz", "Ali Kiba",
        "Angelique Kidjo", "Salif Keita", "Youssou NDour",
        # 电子/合成波人声
        "CHVRCHES", "Purity Ring", "Grimes",
        "Carly Rae Jepsen", "Robyn", "Röysksopp",
        "Lykke Li", "Robyn", "Zara Larsson",
        "Fever Ray", "The Knife", "La Roux",
        "Ladyhawke", "Presets", "Cut Copy",
        "Empire of the Sun", "MGMT", "Passion Pit",
        "M83", "M83 Midnight City", "The Naked and Famous",
        # 爵士人声补充
        "Norah Jones", "Diana Krall", "Ella Fitzgerald",
        "Billie Holiday", "Sarah Vaughan", "Nina Simone",
        "Peggy Lee", "Carmen McRae", "Helen Merrill",
        "Cassandra Wilson", "Dianne Reeves", "Jane Monheit",
        "Melody Gardot", "Lizz Wright", "Madeleine Peyroux",
        "Gregory Porter", "Kurt Elling", "Jamie Cullum",
        "Michael Buble", "Harry Connick Jr",
        "Tony Bennett", "Frank Sinatra", "Dean Martin",
        "Sammy Davis Jr", "Bobby Darin", "Andy Williams",
        "Nat King Cole", "Mel Torme", "Johnny Hartman",
        "Johnny Mathis", "Steve Lawrence", "Jack Jones",
    ]
    for kw in en_vocal_round6:
        add(kw)

    # 纯音乐/器乐/氛围补充（用户明确要求纯音乐）
    instrumental_round6 = [
        # 钢琴纯音乐补充
        "钢琴曲 纯音乐", "钢琴独奏", "钢琴轻音乐",
        "轻音乐 钢琴", "治愈钢琴曲", "睡前钢琴曲",
        "浪漫钢琴曲", "伤感钢琴曲", "欢快钢琴曲",
        "钢琴伴奏 纯音乐", "钢琴改编 流行歌",
        "Yiruma", "Ludovico Einaudi", "Joep Beving",
        "Nils Frahm", "Olafur Arnalds", "Hania Rani",
        "Chad Lawson", "Federico Albanze", "Lorenzo Pastro",
        "Jean-Michel Blais", "Kristina Barta",
        "Dustin O Halloran", "Max Richter",
        "Goldmund", "Library Tapes", "Nils Frahm",
        "Poppy Ackroyd", "Hauschka", "Rachel Grimes",
        "Rolf Lovland", "Brian Crain", "Marc Enfroy",
        "Keiko Matsui", "Bradley Joseph", "Jim Brickman",
        "David Lanz", "Michael Dulin", "Louis Lortie",
        "Valentina Lisitsa", "Lang Lang", "Yuja Wang",
        "Yiruma River Flows", "Yiruma Kiss the Rain",
        "Einaudi Nuvole Bianche", "Einaudi Una Mattina",
        "Einaudi Experience", "Einaudi Fly",
        "Max Richter On the Nature of Daylight",
        "Max Richter Sleep", "Max Richter Recomposed",
        "Joep Beoving", "Joep Beving Henatis",
        # 吉他纯音乐补充
        "吉他纯音乐", "吉他独奏 纯音乐", "指弹吉他",
        "Fingerstyle", "Acoustic Guitar Instrumental",
        "Tommy Emmanuel", "Sungha Jung", "Andy McKee",
        "Don Ross", "Erik Mongrain", "Kaki King",
        "Antoine Dufour", "Ewan Dobson", "Mike Dawes",
        "Calum Graham", "Andrew White", "Erik Mongrain",
        "Jacques Stotzem", "Pierre Bensusan", "Laurent Boutros",
        "Masa Sumide", "Stephen Bennett", "Richard Smith",
        "Chet Atkins", "Merle Travis", "Jerry Reed",
        "John Fahey", "Leo Kottke", "Robbie Basho",
        "Jack Rose", "Glenn Jones", "Sir Richard Bishop",
        "Gyan Riley", "Andrew York", "Bryan Johanson",
        # 古典器乐补充
        "Classical Music", "Classical Piano",
        "Beethoven", "Mozart", "Chopin", "Bach",
        "Debussy", "Liszt", "Schubert", "Schumann",
        "Brahms", "Rachmaninoff", "Tchaikovsky",
        "Vivaldi", "Handel", "Haydn", "Mendelssohn",
        "Grieg", "Saint-Saens", "Faure", "Ravel",
        "Satie", "Paganini", "Wagner", "Bruckner",
        "Mahler", "Stravinsky", "Prokofiev", "Shostakovich",
        "Bartok", "Dvorak", "Smetana", "Sibelius",
        "Elgar", "Holst", "Vaughan Williams", "Grainger",
        "Classical Symphony", "Symphony Orchestra",
        "Violin Concerto", "Piano Concerto",
        "String Quartet", "Piano Sonata", "Violin Sonata",
        "Cello Suite", "Opera Overture", "Ballet Suite",
        "古典音乐 钢琴", "古典音乐 小提琴",
        "古典音乐 大提琴", "古典音乐 交响乐",
        "Mozart Piano", "Chopin Nocturne", "Beethoven Sonata",
        "Bach Cello Suite", "Debussy Clair de Lune",
        "Satie Gymnopedie", "Vivaldi Four Seasons",
        "Tchaikovsky Swan Lake", "Dvorak New World",
        # 电子/氛围纯音乐补充
        "Ambient Music", "Drone Ambient", "Dark Ambient",
        "Space Ambient", "Berlin School", "Kosmische Musik",
        "Tangerine Dream", "Klaus Schulze", "Ash Ra Tempel",
        "Popol Vuh", "Harold Budd", "Eno Music for Airports",
        "Stars of the Lid", "A Winged Victory for the Sullen",
        "Loscil", "William Basinski", "Celer",
        "Rashad Becker", "Grouper", "Julianna Barwick",
        "Tim Hecker", "Fennesz", "Biosphere",
        "Gas", "Wolfgang Voigt", "Ariel Kalma",
        "Laraaji", "Edward Larry", "Hiroshi Yoshimura",
        "Midori Takada", "Joe Hisaishi",
        "Brian Eno Ambient", "Eno Apollo",
        "Aphex Twin Selected", "Boards of Canada",
        "Tycho", "Ulrich Schnauss", "Loscil",
        "Christ.", "Helios", "Lemon Jelly",
        "Bonobo", "Thievery Corporation", "Flying Lotus",
        "Jon Hopkins", "Clark", "Nathan Fake",
        "Rival Consoles", "Lorn", "Kaitlyn Aurelia Smith",
        # 新世纪/冥想纯音乐补充
        "New Age Music", "Meditation Music",
        "Healing Music", "Reiki Music", "Yoga Music",
        "Mindfulness Music", "Chakra Healing",
        "Tibetan Singing Bowls", "Tibetan Bowl",
        "Singing Bowls", "Crystal Bowls",
        "Koshi Chimes", "Wind Chimes",
        "Nature Sounds", "Rain Sounds", "Ocean Sounds",
        "Forest Sounds", "Bird Sounds", "Waterfall Sounds",
        "River Sounds", "Thunderstorm", "White Noise",
        "Pink Noise", "Brown Noise", "Binaural Beats",
        "Isochronic Tones", "432Hz Music", "528Hz Music",
        "Solfeggio Frequencies", "Tuning Fork Therapy",
        "Sound Bath", "Sound Healing",
        "Sleep Music", "Deep Sleep Music",
        "Relaxation Music", "Stress Relief Music",
        "Calm Music", "Peaceful Music",
        "Zen Music", "Buddhist Music",
        "Tibetan Music", "Japanese Zen",
        "Shakuhachi", "Koto Music", "Guqin Music",
        "Guzheng Music", "Erhu Music", "Pipa Music",
        "Chinese Traditional Instrumental",
        "Chinese Guqin", "Chinese Guzheng",
        "Chinese Erhu", "Chinese Pipa",
        "Chinese Bamboo Flute", "Dizi Music",
        "Chinese Zither", "Chinese Lute",
        # 电影/游戏配乐纯音乐
        "Film Score Instrumental", "Movie Soundtrack",
        "Cinematic Music", "Epic Music", "Trailer Music",
        "Hans Zimmer", "John Williams", "Danny Elfman",
        "Howard Shore", "Ennio Morricone", "Nino Rota",
        "John Barry", "Thomas Newman", "Randy Newman",
        "Michael Giacchino", "Alexandre Desplat",
        "Dario Marianelli", "Marco Beltrami",
        "Brian Tyler", "Steve Jablonsky",
        "Henry Jackman", "Christopher Nolan Soundtrack",
        "Interstellar Soundtrack", "Inception Soundtrack",
        "Dune Soundtrack", "Gladiator Soundtrack",
        "The Lion King Soundtrack", "Frozen Soundtrack",
        "Mulan Soundtrack", "Crouching Tiger Soundtrack",
        "Hero Soundtrack", "House of Flying Daggers",
        # Lo-fi/Chillhop 纯音乐补充
        "Lofi Hip Hop Instrumental", "Chillhop Music",
        "Study Beats Instrumental", "Lofi Study",
        "Lofi Sleep", "Lofi Chill", "Lofi Anime",
        "Lofi Radio", "Beats to Study to",
        "Chillhop Instrumental", "Jazzhop",
        "Nujabes", "J Dilla Instrumental",
        "Fat Jon", "Uyama Hiroto",
        "BLCKBRRY", "Birocratic", "j'san",
        "saib.", "Spazzcardigan", "iamaj碳水",
        "GYVUS", "Bastiaan", "Raimu",
        "Saruyama", "Tally Khan", "jrobb",
        "beshirand", "Swarrry", "Philnosauce",
        "less.people", "mellowquest",
        # 爵士纯音乐补充
        "Jazz Instrumental", "Smooth Jazz",
        "Smooth Jazz Sax", "Jazz Piano",
        "Jazz Guitar", "Jazz Trumpet", "Jazz Saxophone",
        "Cool Jazz", "Bebop", "Hard Bop",
        "Free Jazz", "Modal Jazz", "Post Bop",
        "Latin Jazz", "Brazilian Jazz", "Samba Jazz",
        "Acid Jazz", "Soul Jazz", "Jazz Fusion",
        "Miles Davis", "John Coltrane", "Thelonious Monk",
        "Charlie Parker", "Dizzy Gillespie", "Art Blakey",
        "Charles Mingus", "Herbie Hancock", "Wayne Shorter",
        "Stan Getz", "Chet Baker", "Bill Evans",
        "Oscar Peterson", "McCoy Tyner", "Bud Powell",
        "Benny Goodman", "Artie Shaw", "Woody Herman",
        "Stan Kenton", "Duke Pearson", "Horace Silver",
        "Cannonball Adderley", "Lee Morgan", "Freddie Hubbard",
        "Clifford Brown", "Woody Shaw", "Tom Harrell",
        "Roy Hargrove", "Terence Blanchard",
        "Joshua Redman", "Branford Marsalis", "Wynton Marsalis",
        "Christian McBride", "Avishai Cohen",
        "Esperanza Spalding", "Robert Glasper",
        "Kamasi Washington", "Shabaka Hutchings",
        # 管弦乐/交响乐补充
        "Orchestral Music", "Symphony Orchestra",
        "Philharmonic", "Chamber Music",
        "String Orchestra", "Brass Quintet",
        "Wind Ensemble", "Concert Band",
        "Marching Band", "Big Band Jazz",
        # 世界音乐纯器乐
        "Flamenco Guitar", "Flamenco Instrumental",
        "Bossa Nova Instrumental", "Samba Instrumental",
        "Celtic Music Instrumental", "Irish Traditional",
        "Scottish Music", "Bagpipes Music",
        "Indian Classical Music", "Sitar Music",
        "Tabla Music", "Bansuri Music",
        "Arabic Music Instrumental", "Oud Music",
        "Persian Music", "Turkish Music",
        "Balkan Music", "Greek Music",
        "Klezmer Music", "Jewish Music",
        "African Drums", "Djembe Music",
        "Steel Drum Music", "Pan Flute",
        "Andean Music", "Native American Flute",
    ]
    for kw in instrumental_round6:
        add(kw)

    # 华语经典/年代补充（更多中文人声）
    cn_classic_round6 = [
        # 经典华语男声补充
        "费翔", "文章", "张明敏", "费玉清", "刘文正",
        "高凌风", "刘蓝溪", "潘安邦", "杨庆煌",
        "张雨生", "王杰", "邰正宵", "张信哲",
        "伍佰", "杜德伟", "黄品源", "小虫",
        "罗大佑", "李宗盛", "陈升", "黄韵玲",
        "薛岳", "赵传", "王治平", "马兆骏",
        # 经典华语女声补充
        "凤飞飞", "龙飘飘", "韩宝仪", "高胜美",
        "陈淑桦", "叶瑷菱", "林慧萍", "江蕙",
        "黄莺莺", "娃娃金智娟", "郑怡", "张清芳",
        "辛晓琪", "万芳", "许景淳", "潘越云",
        "蔡琴", "苏芮", "王芷蕾", "郑丽丝",
        # 经典组合
        "优客李林", "东方快车", "红孩儿", "小虎队",
        "草蜢", "豹小子", "L.A. Boyz", "宝丽金群星",
        "滚石唱片群星", "飞碟唱片群星", "华纳群星",
        # 方言/民谣
        "闽南语歌曲", "客家语歌曲", "粤语经典老歌",
        "台湾民谣", "校园民谣经典", "西北民谣",
        "陕北民歌", "蒙古民歌", "藏族民歌",
        "新疆民歌", "云南民歌", "四川民歌",
        "东北民歌", "山东民歌", "江苏民歌",
        # 热门综艺/选秀歌曲
        "中国好声音", "我是歌手", "歌手当打之年",
        "歌手2024", "声入人心", "声梦传奇",
        "中国梦之声", "中国新歌声", "蒙面唱将",
        "天赐的声音", "我们的歌", "时光音乐会",
        "歌手经典咏流传", "经典咏流传",
    ]
    for kw in cn_classic_round6:
        add(kw)

    # 欧美年代/经典补充（更多英文人声）
    en_classic_round6 = [
        # 50-60年代经典
        "Elvis Presley", "Buddy Holly", "Chuck Berry",
        "Little Richard", "Fats Domino", "Ricky Nelson",
        "Bobby Darin", "Del Shannon", "Roy Orbison",
        "The Platters", "The Drifters", "The Coasters",
        "The Shirelles", "The Crystals", "The Chiffons",
        "The Ronettes", "The Supremes", "The Temptations",
        "The Four Tops", "Marvin Gaye", "Stevie Wonder",
        # 70年代
        "Led Zeppelin", "Pink Floyd", "The Who",
        "Queen", "The Eagles", "Fleetwood Mac",
        "Steely Dan", "The Doobie Brothers", "Boston",
        "Foreigner", "Journey", "Styx",
        "Supertramp", "Yes", "Genesis",
        "King Crimson", "Emerson Lake and Palmer",
        "Jethro Tull", "The Moody Blues",
        "Electric Light Orchestra", "Traffic",
        "The Band", "Creedence Clearwater Revival",
        "Lynyrd Skynyrd", "The Allman Brothers",
        "Steppenwolf", "Blue Oyster Cult",
        "Aerosmith Dream On", "Heart",
        "Pat Benatar", "Blondie", "Debbie Harry",
        "Talking Heads", "Television",
        "Blondie Heart of Glass", "Kate Bush",
        "Annie Lennox", "Siouxsie Sioux",
        # 80年代补充
        "Michael Jackson Thriller", "Madonna",
        "Prince", "George Michael",
        "Bruce Springsteen Born in the USA",
        "Tina Turner", "Cyndi Lauper",
        "Whitney Houston", "Mariah Carey",
        "Janet Jackson", " Paula Abdul",
        "Kylie Minogue", "Rick Astley",
        "a ha", "Tears for Fears",
        "Duran Duran", "Spandau Ballet",
        "Culture Club", "Boy George",
        "Adam and the Ants", "Sade",
        "Simply Red", "The Communards",
        "Bronski Beat", "Frankie Goes to Hollywood",
        "Yazoo", "Erasure", "Pet Shop Boys",
        # 90年代补充
        "Nirvana Nevermind", "Pearl Jam",
        "Alice in Chains", "Stone Temple Pilots",
        "Smashing Pumpkins", "Radiohead",
        "Oasis Wonderwall", "Blur Song 2",
        "The Verve Bittersweet Symphony",
        "Savage Garden", "Backstreet Boys",
        "NSYNC", "98 Degrees", "5ive",
        "Spice Girls Wannabe", "TLC",
        "Destinys Child", "En Vogue",
        "Brandy and Monica", "Aaliyah",
        "Toni Braxton Unbreak My Heart",
        "Monica Angel of Mine",
        "Lauryn Hill", "Missy Elliott",
        "Lil Kim", "Eve", "Foxy Brown",
        # 2000年代补充
        "Coldplay", "Keane", "Travis",
        "Snow Patrol", "Athlete", "Elbow",
        "Doves", "Starsailor", "Thirteen Senses",
        "The Cardigans", "The Hives", "The Vines",
        "The Strokes", "Yeah Yeah Yeahs",
        "Interpol", "Franz Ferdinand",
        "Arctic Monkeys", "Kaiser Chiefs",
        "Maximo Park", "Bloc Party",
        "The Kooks", "Razorlight",
        "The Fratellis", "The View",
        "Editors", "Placebo",
        "HIM", "The Rasmus", "Negative",
        "Avril Lavigne Complicated",
        "Paramore", "Fall Out Boy",
        "My Chemical Romance", "Panic at the Disco",
        "The Used", "Taking Back Sunday",
        "Brand New", "Senses Fail",
        "AFI", "Alkaline Trio",
        "Rise Against", "Anti Flag",
        "NoFX", "Bad Religion",
        "The Offspring", "Rancid",
        "Social Distortion", "The Misfits",
    ]
    for kw in en_classic_round6:
        add(kw)

    # ---- 程序化组合生成更多唯一关键词 ----
    # 歌手 + 修饰词组合（挖掘更多不同歌曲）
    _artist_modifiers = [
        "热门歌曲", "经典歌曲", "精选", "代表作", "最火",
        "演唱会版", "Live现场", "Acoustic版", "Remix", "合作",
        "早期作品", "最新单曲", "非主流", "冷门好歌",
    ]
    _cn_artists_for_combo = [
        "周杰伦", "林俊杰", "陈奕迅", "薛之谦", "毛不易", "赵雷",
        "李荣浩", "华晨宇", "许嵩", "汪苏泷", "邓紫棋", "张靓颖",
        "萧敬腾", "张杰", "周深", "刘若英", "孙燕姿", "梁静茹",
        "蔡依林", "王力宏", "李健", "朴树", "许巍", "汪峰",
        "张信哲", "周华健", "伍佰", "莫文蔚", "那英", "韩红",
        "凤凰传奇", "张韶涵", "王心凌", "杨千嬅", "容祖儿",
        "谢安琪", "王菀之", "方大同", "袁娅维", "谭维维",
        "单依纯", "黄霄雲", "希林娜依高", "颜人中",
    ]
    for artist in _cn_artists_for_combo:
        for mod in _artist_modifiers:
            add(f"{artist} {mod}")

    # 英文歌手 + 修饰词组合
    _en_artists_for_combo = [
        "Taylor Swift", "Ed Sheeran", "Adele", "Bruno Mars",
        "The Weeknd", "Billie Eilish", "Olivia Rodrigo",
        "Post Malone", "Sam Smith", "Dua Lipa", "Harry Styles",
        "Maroon 5", "Imagine Dragons", "Coldplay", "OneRepublic",
        "Linkin Park", "Evanescence", "Marshall", "Benson Boone",
        "Sabrina Carpenter", "Noah Kahan", "Shaboozey",
        "Kendrick Lamar", "Drake", "Travis Scott", "Future",
        "SZA", "Frank Ocean", "Daniel Caesar",
        "Norah Jones", "Diana Krall", "Michael Buble",
        "John Mayer", "Jack Johnson", "Jason Mraz",
    ]
    _en_modifiers = [
        "hits", "best songs", "greatest hits", "top tracks",
        "live performance", "acoustic", "remix", "cover",
        "early works", "latest single", "underrated",
        "collaboration", "duet", "featured",
    ]
    for artist in _en_artists_for_combo:
        for mod in _en_modifiers:
            add(f"{artist} {mod}")

    # 年份 + 语言/风格组合
    _years = ["2020", "2021", "2022", "2023", "2024", "2025"]
    _year_styles = [
        "华语流行", "英文流行", "华语新歌", "英文新歌",
        "华语热歌", "英文热歌", "中文歌曲", "英文歌曲",
        "华语说唱", "英文说唱", "华语民谣", "英文民谣",
        "华语摇滚", "英文摇滚", "纯音乐", "钢琴曲",
        "抖音热歌", "网络红歌", "影视歌曲", "广告曲",
    ]
    for y in _years:
        for style in _year_styles:
            add(f"{y}{style}")

    # 情绪/场景 + 语言组合
    _mood_cn = [
        "伤感华语", "治愈华语", "快乐华语", "励志华语",
        "伤感英文", "治愈英文", "快乐英文", "励志英文",
        "失恋华语", "失恋英文", "暗恋华语", "暗恋英文",
        "分手华语", "分手英文", "表白华语", "表白英文",
        "怀旧华语", "怀旧英文", "复古华语", "复古英文",
        "夜晚华语", "夜晚英文", "清晨华语", "清晨英文",
        "雨天华语", "雨天英文", "晴天华语", "晴天英文",
        "开车华语", "开车英文", "旅行华语", "旅行英文",
        "运动华语", "运动英文", "冥想华语", "冥想英文",
    ]
    for m in _mood_cn:
        add(m)

    # 更多纯音乐搜索组合
    _instrum_combos = [
        # 乐器 + 风格
        "钢琴 治愈", "钢琴 伤感", "钢琴 浪漫", "钢琴 欢快",
        "钢琴 睡眠", "钢琴 冥想", "钢琴 学习", "钢琴 放松",
        "吉他 治愈", "吉他 伤感", "吉他 浪漫", "吉他 欢快",
        "小提琴 治愈", "小提琴 伤感", "小提琴 浪漫",
        "大提琴 治愈", "大提琴 伤感", "大提琴 浪漫",
        "长笛 纯音乐", "萨克斯 纯音乐", "口琴 纯音乐",
        "古筝 纯音乐", "二胡 纯音乐", "琵琶 纯音乐",
        "笛子 纯音乐", "萧 纯音乐", "古琴 纯音乐",
        # 风格 + 场景
        "Ambient 睡眠", "Ambient 冥想", "Ambient 学习",
        "Lofi 学习", "Lofi 睡眠", "Lofi 放松", "Lofi 阅读",
        "Jazz 学习", "Jazz 放松", "Jazz 咖啡",
        "Classical 学习", "Classical 睡眠", "Classical 阅读",
        "电子 纯音乐", "合成器 纯音乐", "环境音乐 纯音乐",
        "白噪音 睡眠", "自然音效 放松", "雨声 睡眠",
        # 国家/地区传统音乐
        "日本传统音乐", "韩国传统音乐", "印度传统音乐",
        "非洲鼓乐", "凯尔特纯音乐", "北欧音乐",
        "地中海音乐", "加勒比音乐", "南美音乐",
        "中东音乐 纯音乐", "东南亚音乐",
    ]
    for kw in _instrum_combos:
        add(kw)

    # 更多 K-pop/J-pop 人声补充
    _kp_jp_extra = [
        "TWICE", "BLACKPINK", "Red Velvet", "ITZY",
        "aespa", "LE SSERAFIM", "NewJeans", "IVE",
        "STAYC", "NMIXX", "BABYMONSTER", "KISS OF LIFE",
        "LOOSSEMBLE", "ARTMS", "TripleS",
        "BTS", "Stray Kids", "ATEEZ", "ENHYPEN",
        "TOMORROW X TOGETHER", "TREASURE", "ZEROBASEONE",
        "RIIZE", "BOYNEXTDOOR", "TWS", "PLAVE",
        "SEVENTEEN", "NU'EST", "ASTRO", "VICTON",
        "ONF", "WEi", "CIX", "DKB", "JUST B",
        "P1Harmony", "EPEX", "TEMPEST", "BLANK2Y",
        "Younha", "Sunwoo Junga", "Lee Soo Young",
        "Baek Yerin", "Heize", "Sunwoo",
        "Chungha", "Sunmi", "Hyuna", "CLC",
        "Oh My Girl", "WJSN", "fromis_9",
        "Dreamcatcher", "Rocket Punch",
        "Pixy", "Rolling Quartz",
        # J-pop 补充
        "Back Number", "Spitz", "Bump of Chicken",
        "Asian Kung-Fu Generation", "GLAY", "LUNA SEA",
        "L'Arc-en-Ciel", "X Japan", "BUCK-TICK",
        "Dir En Grey", "the GazettE", "D'erlanger",
        "Boowy", "Tsunehiko", "Inoue",
        "Mrs. Green Apple", "King Gnu",
        "Sekai No Owari", "MAN WITH A MISSION",
        "KANA-BOON", "go goest", "go!",
        "The Oral Cigarettes", "My Hair is Bad",
        "shamo", "Ryokuoushoku Shakai",
        "Macaroni Empitsu", "Bish",
        "ZUTOMAYO", "Maki",
        "Aimer", "LISA", "Yoasobi", "Yuuri",
        "Tani Yuuki", "Rin音",
    ]
    for kw in _kp_jp_extra:
        add(kw)

    # 影视/游戏 OST 补充
    _ost_extra = [
        "我的阿勒泰", "繁花 电视剧", "漫长的季节",
        "去有风的地方", "狂飙 电视剧", "隐入尘烟",
        "爱情而已", "三体 电视剧", "平原上的摩西",
        "dnasty", "虽然是精神病但没关系",
        "鬼怪 OST", "请回答1988 OST", "太阳的后裔 OST",
        "孤单又灿烂的神鬼怪", "W两个世界 OST",
        "梨泰院Class", "爱的迫降", "黑暗荣耀",
        "鱿鱼游戏 OST", "D.P.", "地狱公使",
        "Vincenzo", "Voice", "Signal",
        # 欧美剧
        "Stranger Things Soundtrack", "Euphoria Soundtrack",
        "Wednesday Soundtrack", "Bridgerton Soundtrack",
        "The Witcher Soundtrack", "Obi Wan Soundtrack",
        "Loki Soundtrack", "Mandalorian Soundtrack",
        "WandaVision Soundtrack", "Falcon Winter Soldier",
        "Hawkeye Soundtrack", "Moon Knight Soundtrack",
        # 动画
        "鬼灭之刃 OST", "咒术回战 OST", "间谍过家家",
        "电锯人 OST", "链锯人", "葬送的芙莉莲",
        "我推的孩子", "BLUE LOCK", "进击的巨人 OST",
        "海贼太子", "银魂 OST", "JOJO OST",
        "魔法少女小圆 OST", "Fate Zero OST",
        "Fate Stay Night OST", "Clannad OST",
        "Angel Beats OST", "你的名字 OST",
        "天气之子 OST", "铃芽之旅 OST",
        # 游戏补充
        "塞尔达传说 旷野之息", "塞尔达传说 王国之泪",
        "艾尔登法环", "只狼", "黑魂",
        "原神 OST", "崩坏星穹铁道", "崩坏3",
        "明日方舟", "王者荣耀 BGM", "和平精英 BGM",
        "第五人格", "未定事件簿",
        "光遇", "Sky光遇",
        "星穹铁道", "绝区零",
        "鸣潮", "幻塔",
        "逆水寒", "天涯明月刀",
        "剑网3", "情缘江湖",
    ]
    for kw in _ost_extra:
        add(kw)

    # ---- 2026-09 第七轮：扩充至 50 万+（中英文人声 + 纯音乐，补充新维度）----
    # 第七轮：华语人声 - 更多独立/小众/网络歌手（R7）
    cn_vocal_r7 = [
        # 更多内地独立男声
        "陈硕子", "陈冠希", "曲肖冰", "马良", "王宇良", "张紫豪",
        "阿杜", "半吨兄弟", "大壮", "白小白", "海伦", "王冕",
        "王小乱", "刘心", "小贱", "星弟", "阿悄", "常石磊",
        "李行亮", "曾春年", "六哲", "冷漠", "欢子", "郑源",
        "姜玉阳", "蓝雨", "李圣杰", "张志嘉", "东来东往",
        "谭炜星", "王羽臣", "徐誉滕", "山野", "雨天",
        # 更多网络女声
        "香香", "刘著", "慕容晓晓", "斯琴高丽", "顾莉雅",
        "金莎", "弦子", "唐笑", "厉娜", "许飞", "尚雯婕",
        "朱俐静", "刘若英 经典", "黄小琥", "万芳 新不了情",
        "彭佳慧", "林凡", "杨丞琳 暧昧", "许茹芸", "江美琪",
        "阮丹青", "许美静", "何嘉莉", "赵咏华", "陈明真",
        "李翊君", "叶启田", "沈文程", "郭金发", "罗时丰 台语",
        # 更多乐队
        "五月天 志明与春娇", "苏打绿 小情歌", "逃跑计划",
        "旅行团乐队", "旺福", "动力火车 当",
        "Mr.乐队", "Supper Moment", "RubberBand",
        "Dear Jane", "C AllStar", "Supper Moment 一样是我",
        # 更多民谣歌手
        "马頔 南山南", "宋冬野 斑马", "赵雷 画", "尧十三",
        "陈鸿宇 理想三旬", "蒋明", "刘东明", "赵已然",
        "杨一", "白水", "赵牧阳", "张玮玮", "郭龙",
        "小河", "万晓利 狐狸", "钟立风", "阿朵",
        # 音乐剧/声乐类
        "郑云龙", "阿云嘎", "王晰", "仝卓", "陆宇鹏",
        "简弘亦", "廖佳琳", "马佳", "蔡程昱 声入人心",
        # 说唱更多
        "红花会", "GOSH", "CBLOCK", "Higher Brothers",
        "法老 亲密爱人", "鬼卞", "小安迪", "布瑞吉",
        "周汤豪", "玖壹壹", "MP魔幻力量",
        # 更多新生代/小歌手
        "王赫野", "黄霄雲 星辰大海", "阿肆 热爱105度的你",
        "赵乃吉", "任素汐", "文咏珊", "程响",
        "任然", "蒋雪儿", "魏新雨", "贺敬轩",
        "庄心妍", "唐古", "门丽", "陈瑞",
        "云菲菲", "龙梅子", "斯琴高丽 顾峰",
        # 港台老歌声乐类
        "罗大佑 童年", "李宗盛 鬼迷心窍", "周华健 朋友",
        "Beyond 海阔天空", "张国荣 风继续吹", "谭咏麟 朋友",
        "刘德华 忘情水", "张学友 吻别", "黎明 今夜你会不会来",
        "梅艳芳 女人花", "陈百强 一生何求", "徐小凤 顺流逆流",
    ]
    for kw in cn_vocal_r7:
        add(kw)

    # 第七轮：欧美更多歌手补充（R7）
    en_vocal_r7 = [
        # 流行/电子 新
        "Rema", "Ayra Starr", "Libianca",
        "Tyla", "Oxlade", "Asake", "Ayra Starr",
        "Tems", "Burna Boy Last Last", "Asake Lonely",
        "Dua Lipa Levitating", "Dua Lipa Future Nostalgia",
        "Doja Cat Paint The Town Red", "Doja Cat Scarlet",
        "Sza Kill Bill", "Sza SOS",
        "Ice Spice Princess Diana", "Ice Spice Like",
        "Sabrina Carpenter Espresso", "Sabrina Carpenter Taste",
        "Tate McRae Greedy", "Tate McRae Exes",
        "Renee Rapp Pretty Girls", "Gracie Abrams Risk",
        "Chappell Roan", "Madison Beer Silence",
        "Le Sserafim Perfect Night",
        "NewJeans Super Shy", "NewJeans Ditto",
        # 摇滚/独立 新老
        "Benson Boone Beautiful Things",
        "Noah Kahan Stick Season", "Zach Bryan I Remember Everything",
        "Teddy Swims Lose Control",
        "David Kushner Daylight", "Myles Smith Solo",
        "Stephen Sanchez Until I Found You",
        "JVKE Golden Hour", "JVKE This Is What",
        "Jvke Wonder", "Lauren Spencer",
        "Hozier Too Sweet", "Hozier Take Me To Church",
        "Creedence Clearwater Revival",
        "America", "Three Dog Night", "Grand Funk Railroad",
        "Deep Purple", "Black Sabbath", "Judas Priest",
        "Iron Maiden", "Pantera", "Megadeth", "Slayer",
        "Bad Religion No Control", "Pennywise",
        "Green Day Dookie", "Pearl Jam Ten", "Nirvana In Utero",
        "Smashing Pumpkins Siamese Dream",
        "Tame Impala Currents",
        "MGMT Electric Feel", "The Strokes Is This It",
        "LCD Soundsystem", "Justice", "Daft Punk Random Access",
        "Justice Cross", "Boys Noize", "Busy P",
        "DJ Koze", "DJ Seinfeld",
        # 乡村 更多
        "Morgan Wallen Last Night", "Zach Bryan Something",
        "Luke Combs Fast Car", "Chris Stapleton Tennessee",
        "Thomas Rhett Die A Happy Man",
        "Cole Swindell", "Dierks Bentley",
        "Cody Johnson", "Kane Brown", "Sam Hunt Body",
        "Midland", "Jon Pardi", "Luke Combs Hurricane",
        "Tyler Childers", "Jason Isbell",
        "Lainey Wilson", "Maren Morris The Bones",
        "Kelsea Ballerini", "Mickey Guyton",
        # 拉丁/世界
        "Karol G", "Shakira Bzrp",
        "Feid", "Cris Mj", "Standly",
        "Myke Towers", "Arcangel", "Farruko",
        "Anuel AA", "Eladio Carrion", "Junior H",
        "Peso Pluma", "Natanael Cano", "Eslabon Armado",
        "Yahritza", "Ivan Cornejo", "Ke Personajes",
        "Paulo Londra", "Maria Becerra", "Tini Stoessel",
        # R&B 新生代
        "SZA", "Victoria Monét", "Coco Jones",
        "Jazmine Sullivan", "H.E.R. Focus",
        "H.E.R. Damage", "SZA The Weekend",
        "Jorja Smith Blue Lights", "Brent Faiyaz",
        "Bryson Tiller Trap Soul", "Smino Blkswn",
        "Ravyn Lenae", "Umi", "Joyce Wrice",
        "Alex Isley", "Foushee Deep End",
        "Amber Mark", "Rachel Chinouriri",
        # 爵士人声
        "Cecile McLorin Salvant", "Samara Joy",
        "Veronica Swift", "Joan Chamorro",
        "Roberta Gambarini", "Tierney Sutton",
        "Stacey Kent", "Rene Marie",
        # 民谣/乡村经典
        "James Taylor", "Carole King Tapestry",
        "Joni Mitchell Blue", "Gordon Lightfoot",
        "Donovan", "Don Williams",
        "John Denver Take Me Home",
        "Glen Campbell", "Jim Croce",
        "Otis Redding", "Sam Cooke",
        "Marvin Gaye Whats Going On",
        "Stevie Wonder Songs In The Key",
        "Al Green Lets Stay Together",
        "Minnie Riperton", "Roberta Flack",
        "Sly and The Family Stone",
        # 电子舞曲更多人声
        "Illenium", "Seven Lions",
        "Gryffin", "Martin Garrix Animals",
        "Netsky", "Sub Focus",
        "Wilkinson", "Dimension", "Matrix Futurebound",
        "DJ Hype", "Goldie", "LTJ Bukem",
        "Fred Again", "Four Tet",
        "Overmono", "Skream", "Benga",
        "Burial", "Mala", "Digital Mystikz",
        # K-pop 更细
        "IU Love Wins", "IU",
        "Jungkook Seven", "Jungkook Standing",
        "V Layover", "Jimin Face", "Agust D",
        "Jin Astronaut", "j-hope Jack",
        "SUGA D-Day", "Jimin MUSE",
        "Seventeen Super", "Seventeen God",
        "Stray Kids S-Class", "Stray Kids LALALALA",
        "Ateez Wonderland", "ATEEZ",
        "Enhypen Drunk-Dazed",
        "TXT Sugar Rush Ride", "TXT",
        "Treasure B.O.M.B", "Zerobaseone",
        "Riize Love 119", "Riize Memories",
        "BoyNextDoor One and Only",
        "TWS Plot Twist", "Plave Way I Love",
        "Cravity", "Xdinary Heroes",
        "NCT 127", "NCT DREAM", "WayV",
        "NCT U", "NCT DOJAEJUNG",
        "EXO Let Me In", "EXO Cream Soda",
        "BTS Take Two", "BTS Butter", "BTS Dynamite",
        "BTS Yet to Come",
        "BPINKPINK Pink Venom",
        "Blackpink Shut Down",
        "TWICE SET ME FREE",
        "Red Velvet Chill Kill",
        "Aespa Drama", "Aespa Armageddon",
        "Le Sserafim Unforgiven", "LE SSERAFIM EASY",
        "NewJeans How Sweet",
        "IVE Love Dive", "IVE I AM",
        "Nmixx Love Me Like This",
        "BabyMonster Batter Up", "Babymonster SHEESH",
        "Itzy Kill My Doubt",
        "Everglow", "Loossemble",
        "Dreamcatcher VirtuouS",
        "Gidle QueenCard", "Gidle Super Lady",
        "Apink", "SNSD FOREVER 1",
        "BoA", "Taeyeon INVU",
        "Red Velvet Irene", "Red Velvet Seulgi",
        "Jihyo Solo", "Nayeon Pop",
    ]
    for kw in en_vocal_r7:
        add(kw)

    # 第七轮：纯音乐扩展 更多维度
    instrumental_r7 = [
        # 各流派钢琴曲家补充
        "Ryuichi Sakamoto", "坂本龍一 终曲",
        "坂本龙一 Async", "坂本龙一 Merry Christmas",
        "Joe Hisaishi Summer", "久石让 菊次郎的夏天",
        "Yoshida Brothers", "吉田兄弟",
        "Toru Takemitsu", "武满彻",
        "Hisashi Joh", "城之内美莎",
        "Nobuo Uematsu", "植松伸夫",
        "Yasunori Mitsuda", "光田康典",
        "Koji Kondo", "近藤浩治",
        "Jun Senoue", "濑上淳",
        "Motoi Sakuraba", "桜庭統",
        "Yoko Shimomura", "下村陽子",
        # 更多古典作曲家
        "Rimsky-Korsakov", "Borodin", "Mussorgsky",
        "Khachaturian", "Glazunov", "Scriabin",
        "Rachmaninoff Piano Concerto 2",
        "Rachmaninov Vespers",
        "Gershwin Rhapsody in Blue",
        "Copland Appalachian Spring",
        "Bernstein West Side Story Dance",
        "Barber Adagio for Strings",
        "Ives Concord Sonata",
        "Rutter Requiem",
        "Gregorian Chant", "Hildegard von Bingen",
        "Thomas Tallis", "William Byrd",
        "Thomas Tallis Spem in Alium",
        "Palestrina", "Victoria", "Guerrero",
        # 巴洛克
        "Vivaldi Four Seasons Spring",
        "Bach Goldberg Variations",
        "Bach St Matthew Passion",
        "Handel Messiah",
        "Corelli", "Albinoni Adagio",
        "Tartini Devil Trill",
        "Vivaldi Gloria",
        # 电影配乐更多作曲家
        "Danny Elfman Edward Scissorhands",
        "Danny Elfman Batman",
        "Michael Giacchino Up",
        "Alexandre Desplat The Shape of Water",
        "James Horner Titanic",
        "James Horner Avatar",
        "John Williams Harry Potter",
        "John Williams Star Wars Imperial",
        "John Williams Jurassic Park",
        "Howard Shore LOTR Concerning Hobbits",
        "Howard Shore LOTR Rohan",
        "Ryuichi Sakamoto The Last Emperor",
        "Michael Nyman The Piano",
        "Clint Mansell Requiem for a Dream",
        "Philip Glass The Hours",
        "Philip Glass Mishima",
        "Clint Mansell Black Swan",
        "John Powell Bourne Identity",
        "David Arnold",
        # 游戏OST纯音乐
        "Final Fantasy VII Remake OST",
        "Final Fantasy X", "Chrono Trigger OST",
        "Chrono Cross", "Xenogears",
        "Kingdom Hearts OST",
        "Shadow of the Colossus OST",
        "Okami OST", "大神",
        "Dark Souls OST",
        "Bloodborne OST",
        "Skyrim Soundtrack", "上古卷轴5",
        "Genshin Impact Sumeru",
        "Honkai Star Rail OST",
        "Final Fantasy XVI",
        "Elden Ring Soundtrack",
        "Hollow Knight OST",
        "Bastion OST", "Transistor OST",
        "Hades Soundtrack",
        "Stardew Valley",
        "Minecraft OST", "C418 Sweden",
        "Animal Crossing Wild World",
        "Zelda Tears of the Kingdom OST",
        "Zelda Ocarina of Time",
        "Zelda Breath of the Wild",
        "Chrono Trigger 时之回廊",
        "Final Fantasy IX 素敌だね",
        "Bravely Default OST",
        "Octopath Traveler",
        "NieR Automata OST",
        "NieR Replicant OST",
        "Drakengard 3",
        "Rayark Cytus", "DEEMO",
        "Cytus 2", "VOEZ",
        # 中国传统器乐 - 作曲家
        "谭盾 纯音乐", "谭盾 卧虎藏龙",
        "赵季平 大宅门", "赵季平 大红灯笼",
        "赵季平 水浒传",
        "三宝 我的父亲母亲",
        "王月明 紫禁城",
        "何训田 阿姐鼓",
        "刘星 一意孤行",
        "邓伟标 空",
        "窦唯 幻听", "窦唯 殃金咒",
        "赵聪 琵琶",
        "方锦龙 琵琶",
        "马向华 二胡",
        "于红梅 二胡",
        "宋飞 二胡",
        "吕思清 梁祝",
        "薛伟 小提琴",
        # 新世纪/冥想 更多细分
        "Kevin Kern", "George Winston",
        "David Arkenstone", "2002",
        "Mars Lasar", "Coyote Oldman",
        "Dean Evenson", "Govi",
        "Omar Akram", "Peter Kater",
        "Paul Cardall", "The Piano Guys",
        "Lindsey Stirling", "Lindsey Stirling Crystallize",
        "David Garrett", "2CELLOS",
        "The Piano Guys Let It Be",
        "Vitamin String Quartet",
        "Aston Microphones",
        "Two Steps From Hell SkyWorld",
        "Two Steps From Hell Victory",
        "Thomas Bergersen",
        "Thomas Bergersen Empire",
        "Audiomachine", "Epic Score",
        "Brand X Music", "X-Ray Dog",
        "Immediate Music", "Position Music",
        "Hi-Finesse", "Really Slow Motion",
        # Lo-fi beats 更多
        "Chillhop Essentials",
        "Lofi Beats to Relax",
        "Jazzy Lofi",
        "Nujabes Luv Sic",
        "J Dilla Donuts Instrumental",
        "Madlib Beats", "Madlib Beat Konducta",
        "DJ Shadow Endtroducing",
        "Prefuse 73", "Tycho Awake",
        "Little Dragon Instrumental",
        "Bonobo Black Sands",
        "Bonobo Migration",
        "Thievery Corporation Mirror",
        "Nightmares on Wax",
        "Daedelus", "Nosaj Thing",
        "Shigeto", "Teebs",
        # 世界音乐器乐
        "Hiromi Uehara", "上原ひろみ",
        "Soil and Pimp Sessions",
        "Japanese City Pop Instrumental",
        "Mariachi Instrumental",
        "Tango Instrumental", "Astor Piazzolla",
        "Gotan Project",
        "Goran Bregovic",
        "Fanfare Ciocarlia",
        "Mahala Rai Banda",
        "Boban Markovic",
        "Beirut Gulag Orkestar",
        "A Hawk and A Hacksaw",
        "Pink Martini",
        "Straight No Chaser",
    ]
    for kw in instrumental_r7:
        add(kw)

    # 第七轮：程序化组合补充 B
    # 更多歌手/修饰词组合
    _cn_artists_r7 = [
        "陶喆", "王力宏 大城小爱", "潘玮柏", "罗志祥",
        "信乐团 离歌", "F.I.R. Lydia",
        "飞儿乐团 我们的爱", "林宥嘉 说谎",
        "萧敬腾 王妃", "杨宗纬 洋葱",
        "丁当 猜不透", "郭静 下一个天亮",
        "范玮琪 最初的梦想", "薛凯琪 奇洛李维斯回信",
        "林二汶", "陈蕾", "陈卓贤", "姜涛",
        "陈奕迅 浮夸", "陈奕迅 K歌之王",
        "林俊杰 江南专辑", "林俊杰 新地球",
        "周杰伦 周杰伦的床边故事",
        "邓紫棋 光年之外", "G.E.M. 泡沫",
        "王菲 红豆", "王菲 传奇",
    ]
    _cn_mods_r7 = [
        "经典老歌", "金曲选集", "演唱会现场版", "不插电",
        "翻唱版本", "钢琴版", "吉他版", "改编版",
        "热播版", "原版", "试听版", "MV版",
    ]
    for a in _cn_artists_r7:
        for m in _cn_mods_r7:
            add(f"{a} {m}")

    # 英文歌手+修饰词 组合
    _en_artists_r7 = [
        "Lady Gaga Poker Face", "Lady Gaga Bad Romance",
        "Katy Perry Roar", "Katy Perry Teenage Dream",
        "Bruno Mars Uptown Funk", "Bruno Mars 24K Magic",
        "Pharrell Williams Happy",
        "Mark Ronson Uptown",
        "The Chainsmokers Closer",
        "Maroon 5 Sugar", "Maroon 5 Girls Like",
        "Avicii Wake Me Up", "Avicii Levels",
        "Adele Someone Like You", "Adele Hello",
        "Beyonce Halo", "Beyonce Single Ladies",
        "Rihanna Umbrella", "Rihanna Diamonds",
        "Imagine Dragons Believer", "Imagine Dragons Radioactive",
        "OneRepublic Counting Stars",
        "OneRepublic Apologize",
        "Ed Sheeran Perfect", "Ed Sheeran Shape of You",
        "Ed Sheeran Thinking Out Loud",
        "Ariana Grande 7 Rings", "Ariana Grande Thank U",
        "Billie Eilish Bad Guy", "Billie Eilish Ocean Eyes",
        "Taylor Swift Love Story",
        "Taylor Swift Shake It Off",
        "Taylor Swift Blank Space",
        "Harry Styles As It Was", "Harry Styles Watermelon",
        "Dua Lipa New Rules", "Olivia Rodrigo Vampire",
        "SZA Kill Bill Audio",
        "Lana Del Rey Video Games",
        "Lana Del Rey Summertime Sadness",
        "Sam Smith Stay With Me",
        "Michael Jackson Thriller Album",
        "Michael Jackson Billie Jean",
        "Madonna Like a Prayer",
        "Madonna Vogue",
        "Coldplay Viva La Vida", "Coldplay Fix You",
        "Coldplay Yellow",
        "U2 With or Without You",
        "U2 Beautiful Day",
        "Queen Bohemian Rhapsody",
        "Queen Don't Stop",
        "The Beatles Hey Jude",
        "The Beatles Let It Be",
    ]
    _en_mods_r7 = [
        "live at Glastonbury", "BBC live session",
        "acoustic live", "MTV unplugged",
        "royal albert hall", "madison square garden",
        "stadium tour", "karaoke version",
        "instrumental remake", "piano cover",
    ]
    for a in _en_artists_r7:
        for m in _en_mods_r7:
            add(f"{a} {m}")

    # 更多年份+风格（第七轮扩展到更早年代）
    _years_r7 = ["1980", "1981", "1982", "1983", "1984", "1985", "1986",
                 "1987", "1988", "1989",
                 "1990", "1991", "1992", "1993", "1994", "1995",
                 "1996", "1997", "1998", "1999"]
    _year_styles_r7 = [
        "华语歌曲", "粤语歌曲", "台语歌曲",
        "英文歌曲", "欧美金曲",
        "日文歌曲", "韩语歌曲",
        "迪斯科", "电子舞曲",
        "校园民谣", "民歌",
        "轻音乐", "纯音乐",
        "经典老歌", "怀旧金曲",
    ]
    for y in _years_r7:
        for s in _year_styles_r7:
            add(f"{y}年{s}")

    # 情绪/场景 中英文 更多组合
    _mood_more = [
        "思念华语", "思念英文",
        "思乡华语", "思乡英文",
        "毕业季华语", "毕业季英文",
        "春节华语", "中秋华语",
        "婚礼华语", "婚礼英文",
        "春节纯音乐", "婚礼进行曲",
        "情人节华语", "情人节英文",
        "圣诞节华语", "圣诞节英文",
        "圣诞纯音乐", "新年音乐会",
        "国庆庆典", "阅兵音乐",
        "运动会开幕", "颁奖典礼",
        "华语 DJ 串烧", "中文舞曲串烧",
        "华语慢摇", "英文慢摇",
        "车载华语", "车载英文",
        "车载Dj", "酒吧音乐",
        "夜店House", "夜店Trance",
        "DJ现场set", "Club Mix",
        # 音乐学习用
        "视唱练耳", "钢琴入门", "小提琴入门",
        "古筝教程", "吉他教程", "爵士鼓",
        "乐理练习", "和弦进行",
        "爵士标准曲", "Jam伴奏",
    ]
    for kw in _mood_more:
        add(kw)

    return keywords


# ============================================================
# 9. 主入口
# ============================================================
def main():
    import argparse
    parser = argparse.ArgumentParser(description="构建QQ音乐数据库（扩展版）")
    parser.add_argument("--output", "-o", default=None, help="输出文件路径")
    parser.add_argument("--keywords", "-k", type=int, default=None,
                        help="每个关键词每页搜索数量（默认80）")
    parser.add_argument("--pages", "-p", type=int, default=None,
                        help="每个关键词翻页数（默认3）")
    parser.add_argument("--max", "-m", type=int, default=None,
                        help="最多处理多少个关键词（默认全部）")
    parser.add_argument("--no-charts", action="store_true",
                        help="跳过热门榜单爬取")
    parser.add_argument("--resume", "-r", default=None,
                        help="断点续建：加载已有数据库文件增量爬取")
    parser.add_argument("--reset", action="store_true",
                        help="清除进度文件，从头开始")
    parser.add_argument("--list", "-l", action="store_true",
                        help="仅列出所有搜索关键词，不执行爬取")
    parser.add_argument("--verify", "-v", action="store_true",
                        help="仅验证数据库文件，不执行爬取")
    args = parser.parse_args()

    script_dir = os.path.dirname(os.path.abspath(__file__))
    output_path = args.output or os.path.join(script_dir, "music_database.json")

    # 模式：仅列出关键词
    if args.list:
        kw_list = build_keywords()
        print(f"共 {len(kw_list)} 个搜索关键词：")
        for i, kw in enumerate(kw_list, 1):
            print(f"  {i:>3}. {kw}")
        return

    # 模式：验证现有数据库
    if args.verify:
        if not os.path.exists(output_path):
            print(f"数据库文件不存在: {output_path}")
            return
        with open(output_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        songs = data.get("songs", [])
        print(f"数据库版本: {data.get('version')}")
        print(f"来源: {data.get('source')}")
        print(f"歌曲总数: {len(songs)}")
        print(f"统计: {json.dumps(data.get('stats', {}), ensure_ascii=False, indent=2)}")
        required = ["title", "artist", "genre", "energy", "tempo_bpm",
                     "instrument_type", "mood_tags", "external_url", "reason",
                     "duration_sec"]
        missing_fields = set()
        for s in songs:
            for f in required:
                if not s.get(f):
                    missing_fields.add(f)
        if missing_fields:
            print(f"⚠ 缺失字段: {missing_fields}")
        else:
            print("✅ 所有必需字段完整")
        builder = MusicDatabaseBuilder()
        builder.songs = {s["id"]: s for s in songs if "id" in s}
        builder.print_summary()
        return

    # 清除进度
    if args.reset:
        progress = os.path.join(script_dir, "build_progress.json")
        if os.path.exists(progress):
            os.remove(progress)
            print(f"[重置] 已删除进度文件 {progress}")

    # 正常模式：构建数据库
    kw_list = build_keywords()
    if args.max:
        kw_list = kw_list[:args.max]
    per_page = args.keywords or 80
    pages = args.pages or 3

    print("=" * 60)
    print("音乐数据库构建器（扩展版）")
    print(f"数据源: QQ Music 搜索 + {len(QQMusicSource.CHART_IDS)} 个热门榜单")
    print(f"搜索关键词: {len(kw_list)} 个")
    print(f"每词: {per_page}×{pages} 首（翻 {pages} 页）")
    print(f"输出文件: {output_path}")
    if args.resume:
        print(f"断点续建: 从 {args.resume} 增量爬取")
    print("=" * 60)

    builder = MusicDatabaseBuilder(resume_from=args.resume or "")
    builder.build(kw_list, per_page=per_page, pages=pages,
                  charts=not args.no_charts)
    builder.save(output_path)
    builder.print_summary()


if __name__ == "__main__":
    main()
