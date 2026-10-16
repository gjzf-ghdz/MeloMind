"""本地音乐数据库加载器 - 从 music_database.json 加载并构建索引"""
import json
import math
import mmap
import os
import random
import re
import sys
from collections import Counter
from typing import List, Dict, Optional
from models import (Song, infer_instrumental,
                    artist_lang_hints, set_artist_lang_hints, set_lyrics_lang)

_CJK_RE = re.compile(r'[一-鿿]')


def _has_chinese(text: str) -> bool:
    """判断文本是否包含中文字符"""
    return bool(_CJK_RE.search(text or ""))


def _intern(s: str) -> str:
    """对低基数字符串做 intern（相同内容共享同一对象）。

    artist/album/genre/search_keyword/标签 等字段重复度极高（如同一歌手
    上百首歌、5400 个关键词覆盖 53 万首），json.loads 每首歌都创建新字符串
    对象；intern 后 53 万份副本压缩为唯一值份数，可省百 MB 级常驻内存。
    """
    return sys.intern(s) if s else s


# 标题精准命中黑名单：这些"歌名"实为日常用语/请求词/泛化短语，
# 出现在用户消息中不代表用户在点名这首歌，禁止当作标题命中
_TITLE_HIT_BLACKLIST = frozenset({
    # —— 语言/请求类词（最易误伤，如"我喜欢听英文歌"命中《英文歌》《我喜欢》）——
    "英文歌", "中文歌", "英语歌", "华语歌", "国语歌", "粤语歌", "日语歌", "韩文歌",
    "外语歌", "外文歌", "纯音乐", "轻音乐", "背景音乐", "伴奏", "钢琴曲", "吉他曲",
    "音乐", "歌曲", "歌单", "推荐", "好听的歌", "新歌", "老歌", "经典歌",
    "什么歌", "有什么歌", "来点歌", "来首歌", "点一首歌", "唱首歌",
    "一首歌", "这首歌", "那首歌", "每首歌", "几首歌", "点歌",
    "我喜欢", "我喜欢你", "我爱你", "喜欢你", "喜欢", "想听", "听音乐", "听歌",
    # —— 高频日常短语（同为歌名但句子里出现概率极高）——
    "对不起", "没关系", "为什么", "怎么办", "一个人", "两个人", "没有人", "有些人",
    "是不是", "能不能", "可不可以", "有没有", "怎么样", "下雨天", "天黑黑",
    "我们的", "你们的", "他们的", "自己的", "小时候", "长大后", "那一年",
    "第一次", "下一次", "每一次", "有一天", "那一天", "这一天",
    "我爱他", "我爱她", "你爱我", "爱着你", "想着你", "念着你", "等着你",
    "舍不得", "放不下", "忘不了", "算了吧", "再见了", "别回头", "无所谓",
    "不容易", "不后悔", "不将就", "不完美", "刚刚好", "还不错", "都挺好",
    # —— 场景/情绪泛化词 ——
    "在路上", "路上", "地铁", "通勤", "风景", "出发", "回家", "旅途", "远方",
    "好无聊", "无聊", "提神", "睡不着", "助眠", "白噪音", "晚安", "你好", "凌晨",
    "工作", "工作歌", "工作音乐", "上班", "下班", "上课", "下课", "考试", "复习",
    "加班", "加班歌",
    "放松", "放松歌", "放松音乐", "休息", "睡觉", "睡觉歌", "睡眠曲", "催眠曲",
    "失眠", "做梦", "醒来", "起床", "熬夜",
    "运动", "运动会", "运动歌", "跑步", "跑步歌", "健身", "健身房", "健身操",
    "健身歌", "开车", "开车歌", "通勤", "通勤歌", "旅行", "旅行歌", "旅游",
    "出发", "回家", "游戏", "游戏歌", "打游戏", "看书", "阅读", "写作", "编程",
    "写代码", "学习", "学习歌", "学习音乐", "瑜伽音乐", "冥想音乐", "胎教音乐",
    "背景音乐", "背景音",
    "开心", "快乐", "高兴", "难过", "伤心", "焦虑", "烦躁", "孤独", "寂寞",
    "心情", "情绪", "感觉", "觉得", "希望", "想要",
})

# —— 非真人艺术家黑名单：合集/卡拉OK/有声书/佚名/上传频道等，不享受大众度加权 ——
_NON_ARTIST_EXACT = frozenset({
    "群星", "华语群星", "欧美群星", "日韩群星", "various artists",
    "纯音乐", "佚名", "未知", "未知歌手", "网络歌手", "anonymous",
    "dj", "喜马拉雅", "小酷说书", "有声书", "评书", "party tyme",
    "forskjellige artister", "verschiedene interpreten", "群星合集",
    # 唱片公司/厂牌名（元数据把厂牌写进艺人栏）：它们是合集条目，不是歌手
    # （线上实测："宝丽金"名下 77 首，标题多为《1》《2》这类合集曲目）
    "宝丽金", "环球唱片", "华纳唱片", "滚石唱片", "英皇娱乐", "杰威尔",
    "摩登天空", "太合音乐", "福茂唱片", "海蝶音乐", "相信音乐", "华研国际",
    "金牌大风", "百代唱片", "索尼音乐", "环球音乐", "华研唱片", "群星唱片",
    # 元数据错位（歌名串到艺人名栏的常见短词）
    "考试", "情人节", "周末", "放假", "假期", "毕业", "寒假", "暑假",
})

# 频道/号/合集类名称特征（批量上传的疗愈号、翻唱号、有声频道等）：
# 真正的歌手/乐队名字几乎不会包含这些词，而音频工厂账号高频包含
_NON_ARTIST_RE = re.compile(
    r"(karaoke|卡拉ok|party tyme|covers?\b|beats\b|\bdj\b|various|"
    r"classical artists|anonymous|unknown|"
    r"音乐|疗愈|助眠|深度睡眠|催眠|哄睡|安眠|白噪音|白噪声|睡眠|静心|减压|解压|"
    r"说书|讲书|读书|朗读|诵读|传媒|有声|频道|电台|广播剧|节目|"
    r"胎教|养生|双耳节拍|脑波|冥想引导|打坐|轻音乐|纯音乐|纯音|伴奏|伴唱|翻唱|"
    r"宝宝|婴儿|助眠|串烧|车载|慢摇|广场舞|喊麦|试音|无损|hifi|"
    r"音乐馆|音乐厅|音乐铺|音乐坊|音乐台|音乐盒|音乐汇|音乐站|音乐空间|"
    r"大脑|上班|背景音|脑电波|脑波|频率|赫兹|\d+\s*hz|禅音|佛音|咒语|心经|"
    r"自然声|雨声|水声|环境音|氛围音|安神|静心|清心|"
    r"钢琴曲|古筝曲|二胡曲|胎教音乐|睡眠音乐|瑜伽音乐|"
    r"群星|合辑|合集|精选集|歌单|排行榜|团队|工作室|工坊|"
    r"reiki|relaxation|sound therapy|healing music|music therapy|sleepy|"
    r"sleep sounds|nature sounds|white noise|瑜伽|脉轮|颂钵|音疗|冥想音乐|睡眠音乐馆|"
    # 多语种"群星合集"署名（挪威语 forskjellige artister 等），非真人歌手
    r"artister|artistes|verschiedene|allerlei|compilation|"
    r"^\s*various\b)",
    re.IGNORECASE)


# 音频工厂号特征（一）：作品名带"翻奏/版本标注"后缀
# （《Dehors (纯音版)》《爱乐之城 (…钢琴间奏)》《Sometimes When It Rains (长笛版)》）。
_FACTORY_TITLE_RE = re.compile(
    r"[（(【]\s*(纯音版|纯音乐版|纯音|钢琴纯音乐|钢琴版纯音|治愈版|治愈版木吉他|"
    r"放松版|助眠版|睡眠版|学习版|纯享版|无词版|无人声版|伴奏版|翻唱版|"
    r"钢琴版|吉他版|古筝版|长笛版|小提琴版|dj版|remix|翻奏|改编版|"
    # 变速/氛围加工号（拖鞋pd 等）：(1.1x DJ 氛围版)/(宿命氛围版)/(慢摇版)
    r"氛围版|慢摇版|加速版|降速版|夜店版|电音版|车载版|"
    r"\d\.\dx|x\d\.\d)\s*[)）】]",
    re.I)

# 音频工厂号特征（二）：作品名"书名号不成对"。
# 转存型账号批量扒取他人歌曲时，标题常见「歌手《歌名」「歌名》 (Live)」这类
# 只出现一个《或》的残缺写法（张杰 (明天过后) / 苏打绿《山海 (Live)）。
# 全库 527,742 首中只有 12 位艺人出现 ≥2 次该形态，其中 9 位正是转存号，
# 而周杰伦/久石让/郎朗/薛之谦/苏打绿/许嵩等真实歌手为 0 次——零误伤。
_FACTORY_BOOKMARK_RATIO = 0.15   # 不平衡书名号占比阈值
_FACTORY_VERSION_RATIO = 0.30    # "纯音版/钢琴版/remix"等版本标注占比阈值
_FACTORY_MIN_SONGS = 4           # 样本量下限：作品太少不足以判定为工厂号

# 音频工厂号特征（三）：标题几乎**每一首**都带括号标注，且标注内容是"加工类"词。
# 这类账号（拖鞋pd 358 首括号占 94%、加工词 67%）靠批量发布变速/氛围/混音版本
# 堆出高作品数，从而伪装成"大众艺人"，但追不上特征（一）的固定标签表。
# 判据要求两条同时成立，以避开真实歌手的正规再版：
#   · 括号占比 ≥85%：真实歌手即使大量发现场/重制，也远达不到（周杰伦 40%、
#     陈奕迅 36%、张学友 42%、The Beatles 84%）；
#   · 加工词占比 ≥50%：正规再版用的是 Live/Remastered/Expanded/Deluxe，
#     且常以本名标注（"小情歌 (苏打绿版)"），这两类都不计入加工词。
_FACTORY_PAREN_RE = re.compile(r"[（(【]([^)）】]{1,24})[)）】]")
_FACTORY_PROCESS_RE = re.compile(
    r"版|混音|remix|dj|dance|house|mix|氛围|纯享|片段|变速|慢摇|车载|spa|背景音|"
    r"重低音|环绕|助眠|疗愈|白噪音|串烧|降调|升调", re.I)
_FACTORY_LEGIT_RE = re.compile(
    r"re-?master|expanded|deluxe|edition|live|演唱会|巡演|现场|acoustic|unplugged|"
    r"demo|anniversary|周年|原版|原唱|正式版|studio|explicit", re.I)
_FACTORY_PAREN_RATIO = 0.85        # 标题带括号标注的占比阈值
_FACTORY_PROCESS_RATIO = 0.50      # 其中"加工类"标注的占比阈值
_FACTORY_PAREN_MIN_SONGS = 40      # 占比类判据的样本下限（小样本噪声大）


def _factory_paren_stats(lst, artist: str):
    """(括号标注占比, 加工类标注占比)。以本名标注的再版（"苏打绿版"）算正规。"""
    n = float(len(lst))
    paren = 0
    process = 0
    for s in lst:
        m = _FACTORY_PAREN_RE.search(s.title or "")
        if not m:
            continue
        paren += 1
        tag = m.group(1)
        if artist and artist in tag:
            continue          # "小情歌 (苏打绿版)" —— 本人标注的再版，非加工
        if _FACTORY_PROCESS_RE.search(tag) and not _FACTORY_LEGIT_RE.search(tag):
            process += 1
    return paren / n, process / n


# 曲库里歌曲数达到该阈值的艺人姓名才被当作"可点播歌手"
_MIN_ARTIST_SONGS = 5

# 歌曲级"热度"信号：抓取关键词本身就是"热门/榜单"类时，
# 说明这首歌是当时从该艺人的热门曲目里扒到的（而非冷门 B 面）。
# 曲库没有播放量字段，这是唯一可用的**单曲级**热度证据（覆盖约 4% 曲目）。
_HIT_KW_RE = re.compile(
    r"热门歌曲|热门单曲|经典老歌|金曲|热歌|热播|必听|神曲|串烧榜|排行榜|榜|"
    r"hits?|top\s*tracks|greatest|best\s*of|chart",
    re.I)


def _has_unbalanced_bookmark(title: str) -> bool:
    """标题里《》数量不成对（转存号批量扒歌留下的残缺写法）"""
    t = title or ""
    return t.count("《") != t.count("》")


def _is_non_artist(name: str) -> bool:
    n = (name or "").strip().lower()
    return n in _NON_ARTIST_EXACT or bool(_NON_ARTIST_RE.search(n))


def _load_lyrics_lang(path: str) -> int:
    """加载歌词实测语种表（离线生成）；缺失或损坏时静默降级为原判定逻辑。"""
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        print(f"[LocalDB] 歌词语种表未加载: {e}")
        return 0
    set_lyrics_lang(data)
    return len(data) if isinstance(data, dict) else 0


class LocalMusicDatabase:
    """单例，进程内缓存整库 + 三级索引"""

    _instance = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self, db_path: Optional[str] = None):
        if self._initialized:
            return
        self._initialized = True
        self._songs: List[Song] = []
        self._kw_index: Dict[str, List[Song]] = {}
        self._task_index: Dict[str, List[Song]] = {}
        self._mood_index: Dict[str, List[Song]] = {}
        self._title_index: Dict[str, List[Song]] = {}
        self._hit_ids: set = set()      # 热门/榜单类关键词抓取到的歌（单曲热度信号）
        self._all_keywords: List[str] = []
        # 大众度信号：艺人歌曲数 + 各标签下热门歌曲榜
        self._artist_count: Dict[str, int] = {}
        self._task_top: Dict[str, List[Song]] = {}
        self._mood_top: Dict[str, List[Song]] = {}

        # 相关性打分用：组合索引 + 风格/能量索引 + 统计量
        self._pair_index: Dict[tuple, List[Song]] = {}
        self._pair_top: Dict[tuple, List[Song]] = {}
        self._genre_index: Dict[str, List[Song]] = {}
        self._energy_index: Dict[int, List[Song]] = {}
        self._tempo_hist: List[int] = [0] * 221
        self.task_tag_spec: Dict[str, float] = {}
        self.mood_tag_spec: Dict[str, float] = {}
        self.genre_spec: Dict[str, float] = {}
        self.energy_cdf: Dict[int, float] = {}
        self.tempo_cdf: List[float] = []
        self.mood_vocab: tuple = ()
        self.task_vocab: tuple = ()
        self.genre_vocab: tuple = ()

        if db_path is None:
            backend_dir = os.path.dirname(os.path.abspath(__file__))
            db_path = os.path.join(backend_dir, "..", "music_database",
                                   "music_database.json")
            db_path = os.path.normpath(db_path)

        self._db_path = db_path
        self._load()

    def _load(self):
        """加载 JSON 数据库并构建索引

        内存优化三重手段：
        1. mmap 映射文件（页有磁盘后备，OS 可随时回收，不占匿名内存/不进 swap）；
        2. 括号深度扫描逐首解析，整库文本从不在内存中拼接；
        3. 低基数字段（artist/album/genre/keyword/标签）intern 去重。
        """
        if not os.path.exists(self._db_path):
            print(f"[LocalDB] 数据库文件不存在: {self._db_path}")
            return

        try:
            with open(self._db_path, "rb") as f:
                mm = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
        except Exception as e:
            print(f"[LocalDB] 加载失败: {e}")
            return

        try:
            for obj_bytes in self._iter_song_objects(mm):
                try:
                    d = json.loads(obj_bytes)  # json.loads 原生支持 bytes
                except json.JSONDecodeError:
                    continue
                song = self._dict_to_song(d)
                self._songs.append(song)

                # search_keyword 索引（intern 后键值共享）
                kw = song.search_keyword
                if kw:
                    self._kw_index.setdefault(kw, []).append(song)
                    if _HIT_KW_RE.search(kw):
                        self._hit_ids.add(song.id)

                # task_tags 索引
                for tag in song.task_tags:
                    if tag:
                        self._task_index.setdefault(tag, []).append(song)

                # mood_tags 索引
                for tag in song.mood_tags:
                    if tag:
                        self._mood_index.setdefault(tag, []).append(song)

                # genre / energy / tempo 索引（相关性打分与候选池采样用）
                if song.genre:
                    self._genre_index.setdefault(song.genre, []).append(song)
                self._energy_index.setdefault(song.energy, []).append(song)
                tempo = int(song.tempo_bpm or 0)
                if 0 <= tempo < 221:
                    self._tempo_hist[tempo] += 1

                # (task, mood) 组合索引：抓取标签的本质是"意图簇"，
                # 组合命中（如 workout+energetic）比赛/情绪单独命中精确得多
                for t in song.task_tags:
                    for m in song.mood_tags:
                        self._pair_index.setdefault((t, m), []).append(song)
        finally:
            mm.close()

        # ---- 艺人级语种推断 ----
        # 汉字艺名的日韩作曲家（澤野弘之/久石让/光田康典）作品多为纯拉丁文标题，
        # 单看一条判不出语种；按艺人聚合假名/谚文占比后即可定性，用于把这类
        # 动画/游戏 OST 从"中文歌"里摘出去。只影响"标题主体无汉字"的歌。
        hints = artist_lang_hints(self._songs)
        set_artist_lang_hints(hints)
        if hints:
            n_ja = sum(1 for v in hints.values() if v == "japanese")
            print(f"[LocalDB] 艺人级语种推断 {len(hints)} 个艺人"
                  f"（日语 {n_ja} / 韩语 {len(hints) - n_ja}）")

        # ---- 歌词实测语种表 ----
        # 离线抓取歌词、剔除"词/曲/编曲"等元信息行后按正文文字系统判定，
        # 只覆盖元数据分不出语种的条目；命中即以歌词为准。
        n_lyr = _load_lyrics_lang(os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "lyrics_lang.json"))
        if n_lyr:
            print(f"[LocalDB] 歌词实测语种 {n_lyr} 首")

        # 标题索引：只索引含中文且 >=3 字符的标题，用于专有名词匹配
        for song in self._songs:
            title = (song.title or "").strip()
            if len(title) >= 3 and _has_chinese(title) \
                    and title not in _TITLE_HIT_BLACKLIST:
                self._title_index.setdefault(title, []).append(song)

        self._all_keywords = sorted(self._kw_index.keys())

        # ---- 大众度信号构建 ----
        # 0) 音频工厂号识别：三条互补信号任一中即判定为转存/翻奏工厂账号——
        #    (a) 作品名大量带"纯音版/钢琴版/长笛版"等版本标注；
        #    (b) 作品名出现大量"书名号不成对"的残缺写法（批量扒歌的典型痕迹）；
        #    (c) 几乎所有标题都带"加工类"括号标注（批量变速/混音/氛围版账号）。
        #    这类账号靠上传量堆出高作品数，不能算主流艺人（否则它们会霸榜纯音乐/学习场景）。
        self._factory_artists = set()
        _by_artist: Dict[str, list] = {}
        for s in self._songs:
            if s.artist and not _is_non_artist(s.artist):
                _by_artist.setdefault(s.artist, []).append(s)
        for artist, lst in _by_artist.items():
            if len(lst) < _FACTORY_MIN_SONGS:
                continue
            n = float(len(lst))
            ver_ratio = sum(1 for s in lst
                            if _FACTORY_TITLE_RE.search(s.title or "")) / n
            unb_ratio = sum(1 for s in lst
                            if _has_unbalanced_bookmark(s.title)) / n
            # (c) 标题几乎每首都带"加工类"括号标注（批量变速/混音/氛围版账号）
            paren_ratio, process_ratio = (0.0, 0.0)
            if len(lst) >= _FACTORY_PAREN_MIN_SONGS:
                paren_ratio, process_ratio = _factory_paren_stats(lst, artist)
            if ver_ratio >= _FACTORY_VERSION_RATIO \
                    or unb_ratio >= _FACTORY_BOOKMARK_RATIO \
                    or (paren_ratio >= _FACTORY_PAREN_RATIO
                        and process_ratio >= _FACTORY_PROCESS_RATIO):
                self._factory_artists.add(artist)
        if self._factory_artists:
            print(f"[LocalDB] 识别音频工厂号 {len(self._factory_artists)} 个"
                  f"（不计入大众度）")

        # 1) 艺人歌曲数（曲库中歌曲越多的艺人越大众；合集/卡拉OK/频道号/工厂号不计）
        self._artist_count = Counter(
            s.artist for s in self._songs
            if s.artist and not _is_non_artist(s.artist)
            and s.artist not in self._factory_artists
        )

        # 2) 每个标签下的热门歌曲榜（按艺人大众度降序，预排序取前 400）
        def _top_list(songs: List[Song], n: int = 400) -> List[Song]:
            return sorted(
                songs,
                key=lambda s: self._artist_count.get(s.artist, 0),
                reverse=True
            )[:n]

        self._task_top = {tag: _top_list(lst)
                          for tag, lst in self._task_index.items()}
        self._mood_top = {tag: _top_list(lst)
                          for tag, lst in self._mood_index.items()}

        self._pair_top = {key: _top_list(lst, 150)
                          for key, lst in self._pair_index.items()}

        # 统计量：标签特异性(IDF) + 能量/节奏经验分布
        self._build_stats()

        print(f"[LocalDB] 热门曲目 {len(self._hit_ids)} 首, "
              f"{len(self._all_keywords)} 个关键词, "
              f"{len(self._task_index)} 个任务标签, "
              f"{len(self._mood_index)} 个情绪标签, "
              f"{len(self._title_index)} 个标题索引, "
              f"{len(self._artist_count)} 位艺人（大众度+热度信号就绪）")

    def _build_stats(self):
        """预计算相关性打分统计量。

        - 标签特异性(spec)：IDF 归一化到 0~1。balanced/general/relax 这类
          兜底标签 df 极大 → spec≈0（不参与排序），具体标签 → spec≈1。
        - 能量/节奏经验分布(CDF)：曲库中 95% 的歌能量落在 4~6、70% 的歌
          节奏落在 80~99，绝对差值几乎没有区分度；转为百分位后，
          "跑步要 9 分能量"才能真正区分 energy=6 / 5 / 4 的歌。
        """
        n = max(1, len(self._songs))

        def _spec(index):
            return {tag: min(1.0, math.log(n / max(1, len(lst))) / 5.0)
                    for tag, lst in index.items()}

        self.task_tag_spec = _spec(self._task_index)
        self.mood_tag_spec = _spec(self._mood_index)
        self.genre_spec = _spec(self._genre_index)

        cdf, cum = {}, 0
        for e in range(0, 11):
            cum += len(self._energy_index.get(e, ()))
            cdf[e] = cum / n
        self.energy_cdf = cdf

        cdf_t, cum = [0.0] * 221, 0
        for bpm in range(221):
            cum += self._tempo_hist[bpm]
            cdf_t[bpm] = cum / n
        self.tempo_cdf = cdf_t

        self.mood_vocab = tuple(sorted(self._mood_index.keys()))
        self.task_vocab = tuple(sorted(self._task_index.keys()))
        self.genre_vocab = tuple(sorted(self._genre_index.keys()))
        print(f"[LocalDB] 统计就绪：任务标签 {len(self.task_tag_spec)} / "
              f"情绪标签 {len(self.mood_tag_spec)} / "
              f"风格 {len(self.genre_spec)} / 意图簇 {len(self._pair_index)}")

    def popularity_norm(self, song: Song) -> float:
        """大众度归一化到 0~1（供打分模型使用）"""
        return min(1.0, self.popularity_score(song) / 5.0)

    def _sample(self, songs, limit, top=None, pop_ratio=0.25):
        """随机抽样 + 头部大众歌曲注入（兼顾多样性 70~75% 与可听性 25~30%）"""
        if not songs:
            return []
        limit = max(1, int(limit))
        if len(songs) <= limit:
            return list(songs)
        n_top = min(len(top or ()), max(0, int(limit * pop_ratio)))
        k = max(1, limit - n_top)
        chosen = random.sample(songs, min(k, len(songs)))
        if n_top:
            seen = {s.id for s in chosen}
            for s in list(top)[:n_top]:
                if s.id not in seen:
                    chosen.append(s)
                    seen.add(s.id)
        random.shuffle(chosen)
        return chosen

    def sample_by_pair(self, task: str, mood: str, limit: int = 600) -> List[Song]:
        """按 (task, mood) 意图簇采样：簇内命中比赛/情绪单标签命中更精确"""
        key = (task, mood)
        return self._sample(self._pair_index.get(key, ()), limit,
                            self._pair_top.get(key), pop_ratio=0.3)

    def sample_by_genre(self, genre: str, limit: int = 600) -> List[Song]:
        g = (genre or "").strip().lower()
        return self._sample(self._genre_index.get(g, ()), limit, None, pop_ratio=0.35)

    def sample_by_energy_band(self, energies, limit: int = 1200) -> List[Song]:
        """按能量档位采样：曲库能量高度集中，高/低能量目标需要定向多取"""
        energies = [int(e) for e in energies]
        per = max(1, int(limit // max(1, len(energies))))
        out = []
        for e in energies:
            lst = self._energy_index.get(e)
            if lst:
                out.extend(random.sample(lst, min(per, len(lst))))
        random.shuffle(out)
        return out

    def sample_random(self, limit: int = 800) -> List[Song]:
        if not self._songs:
            return []
        return random.sample(self._songs, min(int(limit), len(self._songs)))

    def popularity_score(self, song: Song) -> float:
        """大众度得分 0~6：艺人在曲库中的歌曲数取 log1p（封顶 6）。
        单曲艺人约 0.7 分，10 首约 2.4 分，100 首约 4.6 分，400+ 首满分。
        合集/频道/翻唱号等非真人艺人一律 0 分；音频工厂号（批量上传
        他人歌曲的纯音版/钢琴版）同样 0 分——上传量不等于知名度。"""
        artist = song.artist or ""
        if not artist or _is_non_artist(artist):
            return 0.0
        if artist in getattr(self, "_factory_artists", ()):
            return 0.0
        return min(6.0, math.log1p(self._artist_count.get(artist, 0)))

    def is_hit_song(self, song) -> bool:
        """该曲是否来自"热门歌曲/hits"类关键词抓取（单曲级热度信号）"""
        return bool(song) and getattr(song, "id", "") in self._hit_ids

    def is_artist_name(self, name: str) -> bool:
        """该词是否是曲库里真实存在的歌手/乐队（用于"想听周杰伦"这类歌手点播）"""
        n = (name or "").strip()
        if not n or _is_non_artist(n):
            return False
        return self._artist_count.get(n, 0) >= _MIN_ARTIST_SONGS

    def keyword_specificity(self, kw: str) -> float:
        """关键词的听歌意图特异性 0~1：命中歌曲越少，意图越明确。

        用于区分"世界杯/暗黑系"（几十~几百首，强意图）与
        "助眠/纯音乐"（几十万首，泛意图）——泛意图不该压过相关度排序。
        """
        df = len(self._kw_index.get(kw, ()))
        total = len(self._songs) or 1
        if df <= 0:
            return 0.0
        return max(0.0, min(1.0, math.log(total / float(df)) / 6.0))

    @staticmethod
    def _iter_song_objects(raw: bytes):
        """在整库 JSON 字节流中定位 songs 数组，逐首 yield 歌曲对象 bytes
        （括号深度扫描；字符串内用 find 快进，正确处理转义引号）。"""
        QUOTE, LBRACE, RBRACE, RBRACK, BACKSLASH = 34, 123, 125, 93, 92
        key_pos = raw.find(b'"songs"')
        if key_pos < 0:
            return
        start = raw.find(b'[', key_pos)
        if start < 0:
            return
        depth = 0
        obj_start = None
        i = start + 1
        n = len(raw)
        while i < n:
            ch = raw[i]
            if ch == QUOTE:
                # 快进跳过整个字符串：找未被反斜杠转义的结束引号
                j = i + 1
                while j < n:
                    q = raw.find(b'"', j)
                    if q < 0:
                        j = n
                        break
                    k = q - 1
                    bs = 0
                    while k >= i and raw[k] == BACKSLASH:
                        bs += 1
                        k -= 1
                    if bs % 2 == 0:
                        j = q + 1
                        break
                    j = q + 1
                i = j
                continue
            if ch == LBRACE:
                if depth == 0:
                    obj_start = i
                depth += 1
            elif ch == RBRACE:
                depth -= 1
                if depth == 0 and obj_start is not None:
                    yield raw[obj_start:i + 1]
                    obj_start = None
            elif ch == RBRACK and depth == 0:
                break
            i += 1

    @staticmethod
    def _dict_to_song(d: dict) -> Song:
        """将数据库字典转换为 Song 对象（低基数字段 intern 去重省内存）"""
        def _tags(key):
            raw = d.get(key) or []
            # 标签来自固定标签集（16 任务 + 18 情绪），intern 后全库共享
            return [_intern(t) for t in raw if t]

        return Song(
            id=d.get("id", ""),
            title=d.get("title", ""),
            artist=_intern(d.get("artist", "")),
            album=_intern(d.get("album", "")),
            genre=_intern(d.get("genre", "")),
            mood_tags=_tags("mood_tags"),
            task_tags=_tags("task_tags"),
            energy=d.get("energy", 5),
            tempo_bpm=d.get("tempo_bpm", 120),
            # 逐曲校正：曲库标记来自抓取搜索词，存在人声/纯音乐互窜；
            # 校正后"无歌词"统一归纯音乐，不再混入中文/英文/其它语言板块
            instrumental=infer_instrumental(
                d.get("title", ""), d.get("album", ""), d.get("artist", ""),
                d.get("genre", ""), d.get("instrumental", False)),
            instrument_type=_intern(d.get("instrument_type", "")),
            duration_sec=d.get("duration_sec", 240),
            cover_url=d.get("cover_url", ""),
            external_url=d.get("external_url", ""),
            source=_intern(d.get("source", "local_db")),
            reason=d.get("reason", ""),
            search_keyword=_intern((d.get("search_keyword") or "").strip()),
        )

    def search_by_keywords(self, kws: List[str], limit: int = 50) -> List[Song]:
        """按 search_keyword 精准匹配（任一命中即返回，并集去重）"""
        result = []
        seen = set()
        for kw in kws:
            for song in self._kw_index.get(kw, []):
                if song.id not in seen:
                    seen.add(song.id)
                    result.append(song)
                if len(result) >= limit:
                    return result
        return result

    def search_by_task_tag(self, tag: str, limit: int = 50) -> List[Song]:
        """按 task_tag 匹配：40% 大众热门 + 60% 随机抽样

        热门部分来自该标签下按艺人大众度预排序的榜单（保证主流歌曲进池），
        随机部分保持风格多样性，避免总被头部艺人垄断。
        """
        songs = self._task_index.get(tag, [])
        if len(songs) <= limit:
            return list(songs)
        top = self._task_top.get(tag, [])
        n_top = min(len(top), limit * 2 // 5)
        chosen = list(top[:n_top])
        chosen_ids = {s.id for s in chosen}
        rest = [s for s in songs if s.id not in chosen_ids]
        chosen += random.sample(rest, min(limit - n_top, len(rest)))
        random.shuffle(chosen)
        return chosen

    def search_by_mood_tag(self, tag: str, limit: int = 50) -> List[Song]:
        """按 mood_tag 匹配：40% 大众热门 + 60% 随机抽样"""
        songs = self._mood_index.get(tag, [])
        if len(songs) <= limit:
            return list(songs)
        top = self._mood_top.get(tag, [])
        n_top = min(len(top), limit * 2 // 5)
        chosen = list(top[:n_top])
        chosen_ids = {s.id for s in chosen}
        rest = [s for s in songs if s.id not in chosen_ids]
        chosen += random.sample(rest, min(limit - n_top, len(rest)))
        random.shuffle(chosen)
        return chosen

    def search_by_title_in_text(self, text: str, limit: int = 50,
                                min_popularity: float = 3.0) -> List[Song]:
        """扫描用户输入，若包含某首歌的标题（专有名词），直接命中

        min_popularity：标题命中要求艺人具备大众度（约 20+ 首歌曲的成熟艺人）。
        用户真正点的歌（如《七里香》）多为知名艺人作品；而小众艺人的"短语
        歌名"（如《放松的音乐》《安静的》）易被日常语句子串误伤，一律过滤。
        """
        if not text:
            return []
        result = []
        seen = set()
        for title, songs in self._title_index.items():
            if title in _TITLE_HIT_BLACKLIST:
                continue
            if title in text:
                for song in songs:
                    if self.popularity_score(song) < min_popularity:
                        continue  # 小众艺人的短语歌名，视为噪声
                    if song.id not in seen:
                        seen.add(song.id)
                        result.append(song)
                    if len(result) >= limit:
                        return result
        return result

    def all_songs(self) -> List[Song]:
        return self._songs

    def all_keywords(self) -> List[str]:
        return self._all_keywords

    @property
    def raw_json_bytes(self) -> bytes:
        """按需从磁盘读取原始数据库字节（/api/music_db 接口用，不常驻内存）"""
        try:
            with open(self._db_path, "rb") as f:
                return f.read()
        except OSError:
            return b'{"songs":[]}'
