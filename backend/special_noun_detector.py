"""特殊名词检测器 - 从用户输入中识别事件/游戏/影视/人物等**专有名词**

设计原则：关键词精准命中只服务于专有名词（世界杯、奥运会、游戏名、
电影名、电视剧名、动漫名、音乐人、具名曲目等）。"健身/工作/学习/放松"
等描述用户**状态**的泛化场景词，一律走 task_tag / mood / energy 匹配层，
不得作为特殊关键词抢占推荐位。
"""
import json
import os
import re
from typing import List

# —— 泛化词黑名单（剥离音乐修饰后的核心词命中即视为"状态词"而非"专有名词"）——
_GENERIC_CORE_WORDS = frozenset({
    # 场景 / 任务
    "工作", "上班", "下班", "加班", "通勤", "开车", "驾车", "出行", "路上", "旅途",
    "学习", "读书", "看书", "阅读", "考试", "复习", "作业", "写作业", "专注", "专心",
    "办公", "办公室", "编程", "写代码", "代码", "程序", "程序员", "写作业", "做作业",
    "写作", "写方案", "写报告", "写论文", "写文案", "刷题", "做题", "备考", "背单词",
    "背诵", "记忆", "笔记", "记笔记", "自习", "上课", "听课", "网课", "复盘", "总结",
    "健身", "健身房", "健身操", "运动", "跑步", "跑酷", "瑜伽", "冥想", "打坐",
    "放松", "休息", "休闲", "睡觉", "睡眠", "睡前", "失眠", "起床", "熬夜", "午休", "午睡",
    "旅行", "旅游", "散步", "漫步", "骑行", "骑车", "登山", "爬山", "游泳",
    "聚会", "派对", "跳舞", "舞蹈", "舞会", "打扫", "家务", "做家务", "做饭", "烹饪",
    "洗澡", "沐浴", "购物", "逛街", "化妆",
    "追剧", "刷剧", "看剧", "看综艺", "看比赛", "看球", "看直播",
    "太极", "晨跑", "夜跑", "慢跑", "撸铁", "举铁", "拉伸", "有氧", "力量训练",
    "整理", "收纳", "遛狗", "带娃", "哄睡", "听歌", "听音乐",
    "篮球", "篮球赛", "足球", "球赛", "网球", "羽毛球", "乒乓球", "棒球", "排球",
    "高尔夫", "拳击", "搏击", "滑雪", "滑板",
    "游戏", "打游戏", "玩游戏", "电竞", "开黑", "排位", "上分", "通关",
    # 情绪 / 状态
    "开心", "快乐", "高兴", "兴奋", "激动", "难过", "伤心", "悲伤", "忧伤", "忧郁",
    "焦虑", "焦躁", "烦躁", "压力", "紧张", "孤独", "孤单", "寂寞", "浪漫", "治愈",
    "安静", "宁静", "平静", "祥和", "伤感", "失恋", "分手", "想念", "思念", "怀旧",
    "回忆", "纪念", "励志", "热血", "激昂", "振奋", "甜蜜", "温柔", "温馨", "轻松",
    "轻快", "舒缓", "抒情", "震撼", "史诗", "大气", "战斗", "燃", "甜", "丧", "emo",
    "心情", "情绪", "感觉",
    # 音乐类型 / 曲风 / 乐器（类别词，非专有名词）
    "音乐", "歌曲", "歌", "歌单", "纯音乐", "轻音乐", "器乐", "乐器", "背景",
    "背景音乐", "配乐", "原声", "主题曲", "主题歌", "插曲", "片头曲", "片尾曲",
    "片头", "片尾", "钢琴", "钢琴曲", "吉他", "吉他曲", "古筝", "古琴", "二胡",
    "笛子", "笛", "箫", "洞箫", "琵琶", "小提琴", "大提琴", "中提琴", "贝斯",
    "鼓", "架子鼓", "萨克斯", "口琴", "手风琴", "竖琴", "风琴", "交响乐", "交响曲",
    "管弦乐", "奏鸣曲", "夜曲", "小夜曲", "摇篮曲", "圆舞曲", "进行曲", "舞曲",
    "电子", "电音", "摇滚", "金属", "爵士", "民谣", "乡村", "流行", "古典", "嘻哈",
    "说唱", "饶舌", "布鲁斯", "蓝调", "雷鬼", "朋克", "放克", "灵魂乐", "新世纪",
    "氛围", "国风", "中国风", "古风", "华语", "欧美", "日语", "韩语", "粤语", "国语",
    "英语", "中文", "英文", "日文", "韩文", "外文", "外语",
    "头脑风暴", "灵感", "创意", "构思", "思路", "提神", "高效", "效率",
    "开会", "会议", "出差", "早起", "早安", "晚安", "雨天", "雪天", "阴天",
    "加班", "熬夜", "夜宵", "打扫", "整理", "收拾", "采购", "排队",
    "通勤", "上下班", "午休", "小憩", "发呆", "放空", "冥想词",
    "电影", "电视剧", "电视", "动漫", "动画", "卡通", "综艺", "节目", "影视",
    "年代", "经典", "老歌", "新歌", "热门", "排行", "合集", "精选", "推荐", "必备",
    "必听", "歌单", "神曲", "榜单", "催眠", "愉快", "伴奏", "翻唱", "现场", "混音",
    "改编", "原版", "纯钢", "运动会", "超燃", "高燃",
    # 英文场景 / 状态
    "work", "working", "office", "commute", "commuting", "driving", "drive",
    "study", "studying", "reading", "read", "focus", "focused", "concentration",
    "sleep", "sleeping", "sleepy", "bedtime", "relax", "relaxing", "relaxation",
    "chill", "chillout", "calm", "peaceful", "meditation", "meditate", "yoga",
    "workout", "fitness", "gym", "exercise", "running", "run", "jogging",
    "walk", "walking", "travel", "traveling", "party", "dance", "dancing",
    "cooking", "shopping", "gaming", "game", "games", "sports", "sport",
    "basketball", "football", "soccer", "baseball", "tennis",
    "happy", "happiness", "sad", "heartbreak", "romantic", "romance", "love",
    "energetic", "energy", "nostalgia", "nostalgic", "anxious",
    # 英文曲风 / 类别
    "pop", "rock", "jazz", "classical", "classic", "electronic", "edm",
    "electro", "techno", "house", "trance", "dubstep", "hiphop", "hip-hop",
    "rap", "rnb", "r&b", "country", "folk", "metal", "punk", "indie", "lofi",
    "lo-fi", "ambient", "newage", "instrumental", "piano", "guitar", "violin",
    "cello", "flute", "beat", "beats", "mix", "radio", "playlist", "soul",
    "funk", "reggae", "blues", "swing", "band", "ost", "soundtrack",
    "movie", "film", "cinema", "tv", "drama", "anime", "cartoon", "music",
    "song", "songs", "80s", "90s", "00s", "2000s", "70s", "60s",
    "deep", "tech", "tropical", "progressive", "vocal", "future", "acoustic",
    "live", "cover", "remix", "karaoke", "version", "extended", "original",
    "the", "a", "an", "of", "and", "at", "to", "for", "with",
})

# 音乐类修饰词（作为贪婪分词的补充词典；这些词本身也是泛化类别词）
_MUSIC_AFFIXES = (
    "纯音乐", "轻音乐", "背景音乐", "音乐推荐", "歌曲推荐", "主题曲", "主题歌",
    "片头曲", "片尾曲", "交响曲", "奏鸣曲", "音乐", "歌曲", "歌单",
    "配乐", "原声", "必备", "推荐", "精选", "合集", "必听", "神曲", "排行榜",
    "榜单", "插曲", "bgm", "beats", "music", "song", "songs", "playlist",
    "mix", "radio", "ost", "soundtrack", "b.g.m", "歌", "曲",
)

# 切成"中文段 / 英文数字段"（中英混合无空格也能拆开，如 "工作BGM" → 工作 + bgm）
_RUN_RE = re.compile(r"[一-鿿]+|[a-z0-9]+")

# CJK 贪婪分词词典 = 泛化词黑名单 + 音乐修饰词
_CJK_DICT = _GENERIC_CORE_WORDS | {a for a in _MUSIC_AFFIXES
                                   if re.search(r'[一-鿿]', a)}
_LATIN_DICT = _GENERIC_CORE_WORDS | set(_MUSIC_AFFIXES)

# 可以安全剥离的"音乐附属后缀"：曲库里常见 "王者荣耀 OST"/"和平精英 BGM"
# 这类形态，用户口语只会说裸名（"王者荣耀"）。剥离后若剩余部分非空且
# 不是泛化词，即可用作风暴词根参与前缀匹配。
_STRIPPABLE_TAILS = (
    "主题曲", "主题歌", "片头曲", "片尾曲", "插曲", "原声带", "原声",
    "背景音乐", "配乐", "纯音乐", "轻音乐", "音乐", "歌曲", "歌单",
    "ost", "soundtrack", "bgm", "b.g.m", "music", "songs", "song",
    "playlist", "mix", "radio", "remix", "cover", "live", "version",
    "精选", "合集", "必备", "推荐", "神曲", "榜单", "排行榜",
)


def _strip_music_tail(kw: str) -> str:
    """剥离关键词尾部的音乐附属后缀，返回"词根"。

    '王者荣耀 OST' → '王者荣耀'；'世界杯主题曲' → '世界杯'；
    '甄嬛传' → '甄嬛传'（无后缀可剥）。剥离后为空或仍是泛化词则返回 ''。
    """
    s = (kw or "").strip()
    if not s:
        return ""
    low = s.lower()
    for tail in _STRIPPABLE_TAILS:
        if low.endswith(tail.lower()) and len(s) > len(tail):
            s = s[:len(s) - len(tail)].strip(" -_·|/（）()[]【】")
            break
    if not s:
        return ""
    return "" if _is_generic_keyword(s) else s


def _cjk_token_is_generic(t: str) -> bool:
    """中文 token 贪婪分词：整段能被词典（+数字）完全覆盖才算泛化。
    如 "90年代经典歌曲" → 90+年代+经典+歌曲 全覆盖=True；"王者荣耀" 首字失败=False。
    """
    i, n = 0, len(t)
    while i < n:
        if t[i].isdigit():
            i += 1
            continue
        # 从最长开始找词典匹配
        for L in range(min(8, n - i), 0, -1):
            if t[i:i + L] in _CJK_DICT:
                i += L
                break
        else:
            return False
    return True


def _is_generic_keyword(kw: str) -> bool:
    """判断一个爬取关键词是否为"泛化状态词"（而非专有名词）。

    切分为"中文段/英文数字段"后逐段判定：中文段走贪婪分词覆盖（词典 =
    泛化词 + 音乐修饰词），英文段走整词命中；全部泛化才算泛化词，
    只要含一个专有名词片段（人名/事件名/作品名等）即保留。
    """
    core = (kw or "").strip().lower()
    if not core:
        return True
    runs = _RUN_RE.findall(core)
    if not runs:
        return True
    for run in runs:
        if run.isdigit():
            continue
        if '一' <= run[0] <= '鿿':
            if not _cjk_token_is_generic(run):
                return False
        else:
            if run not in _LATIN_DICT:
                return False
    return True


class SpecialNounDetector:
    """两层检测：别名扫描（人工策展）→ DB 专有名词关键词扫描（泛化词过滤）"""

    def __init__(self, local_db=None):
        self._local_db = local_db
        self._user_alias_map = {}
        self._db_keywords = []
        self._entity_keywords = []
        self._kw_set = set()
        self._stem_map = {}      # 词根 → [完整关键词, ...]（王者荣耀 → 王者荣耀 OST/BGM）
        self._load_config()

    def _load_config(self):
        """从 event_keywords.json 加载别名配置，并预过滤 DB 关键词"""
        backend_dir = os.path.dirname(os.path.abspath(__file__))
        cfg_path = os.path.join(backend_dir, "..", "music_database",
                               "event_keywords.json")
        cfg_path = os.path.normpath(cfg_path)

        if os.path.exists(cfg_path):
            try:
                with open(cfg_path, "r", encoding="utf-8") as f:
                    cfg = json.load(f)
                self._user_alias_map = cfg.get("user_alias_map", {})
            except Exception as e:
                print(f"[NounDetector] 配置加载失败: {e}")

        if self._local_db is not None:
            all_kw = self._local_db.all_keywords()
            self._kw_set = set(all_kw)
            # 预过滤：只保留专有名词类关键词（场景/状态/曲风词剔除）
            self._db_keywords = all_kw
            self._entity_keywords = [k for k in all_kw if not _is_generic_keyword(k)]
            # 建词根索引：'王者荣耀 OST' → '王者荣耀'，让用户说裸名也能命中
            for k in self._entity_keywords:
                stem = _strip_music_tail(k)
                if stem and stem != k:
                    self._stem_map.setdefault(stem, []).append(k)
            print(f"[NounDetector] 专有名词关键词 "
                  f"{len(self._entity_keywords)}/{len(all_kw)} "
                  f"（已剔除 {len(all_kw) - len(self._entity_keywords)} 个泛化状态词，"
                  f"词根索引 {len(self._stem_map)} 条）")

    def detect(self, user_message: str, task_type: str = "") -> List[str]:
        """
        检测用户输入中的特殊专有名词，返回匹配的 search_keyword 列表。
        注意：task_type 不再注入关键词——场景状态由 task_tag/能量匹配层处理。

        返回顺序即优先级：具体专有名词（甄嬛传/世界杯/王者荣耀）排在
        泛化类别词（电视剧/游戏/电影）之前。别名映射不再把具体名"降级"
        成泛化桶——只有当用户说的是俗称（"撸啊撸"）时才映射到规范名。
        """
        msg = (user_message or "").lower()
        raw = user_message or ""
        hits = set()

        # (a) 别名扫描（人工策展）。命中别名后，**原名与别名都算命中**：
        #     原名（甄嬛传）通常比别名（电视剧）更具体，丢弃它会损失最强信号。
        for alias, db_kw in self._user_alias_map.items():
            if alias.lower() in msg:
                hits.add(db_kw)
                # 别名本身也是曲库关键词时一并保留，让具体名压过泛化桶
                if alias in self._kw_set:
                    hits.add(alias)
                # 别名是具体名但库里只以带后缀形态存在（王者荣耀 → 王者荣耀 OST）
                for full in self._stem_map.get(alias, []):
                    hits.add(full)

        # (b) DB 专有名词关键词扫描（艺人/事件/作品名等；泛化状态词已过滤）
        for kw in self._entity_keywords:
            if kw and kw in raw:
                hits.add(kw)

        # (c) 词根反向补全：用户说了库里关键词的裸名（"王者荣耀"），
        #     把该词根下的完整关键词（"王者荣耀 OST"/"王者荣耀 BGM"）一并纳入，
        #     保证具体专场直接占满推荐位，而不是退化成泛化桶"游戏"。
        for stem, fulls in self._stem_map.items():
            if stem and stem in raw:
                hits.update(fulls)

        # 具体专有名词优先：泛化类别词排到最后，避免"电视剧"盖过"甄嬛传"
        return sorted(hits, key=lambda k: (_is_generic_keyword(k), -len(k)))
