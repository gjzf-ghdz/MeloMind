"""统一数据模型"""
import re
import sys
from dataclasses import dataclass, field
from typing import Dict, List, Optional

# slots=True 为 Python 3.10+ 官方支持（53 万+实例时消除每对象 __dict__，省 100MB+）；
# 3.8/3.9 回退普通 dataclass（mmap + intern 优化仍生效）
_dc_kwargs = {"slots": True} if sys.version_info >= (3, 10) else {}


@dataclass(**_dc_kwargs)
class Song:
    """歌曲信息（纯推荐，不含播放）"""
    id: str
    title: str
    artist: str
    album: str = ""
    genre: str = ""
    mood_tags: List[str] = field(default_factory=list)
    task_tags: List[str] = field(default_factory=list)
    energy: int = 5
    tempo_bpm: int = 120
    instrumental: bool = False
    instrument_type: str = ""   # 乐器类型
    duration_sec: int = 240
    cover_url: str = ""
    external_url: str = ""      # 跳转到外部平台（QQ音乐/Spotify）
    source: str = "static"      # static / qqmusic / spotify
    reason: str = ""            # 推荐理由
    search_keyword: str = ""   # 搜索关键词（用于特殊名词命中与理由生成）

    def to_dict(self) -> dict:
        return {
            "id": self.id, "title": self.title, "artist": self.artist,
            "album": self.album, "genre": self.genre,
            "mood_tags": self.mood_tags, "task_tags": self.task_tags,
            "energy": self.energy, "tempo_bpm": self.tempo_bpm,
            "instrumental": self.instrumental,
            "instrument_type": self.instrument_type, "duration_sec": self.duration_sec,
            "cover_url": self.cover_url, "external_url": self.external_url,
            "source": self.source, "reason": self.reason,
            "search_keyword": self.search_keyword,
            # 语言板块：纯音乐 / 中文歌 / 英文歌 / 其它语言（前端按此分组展示）
            "language": song_language(self),
        }


# dataclass(eq=True) 会把 __hash__ 置为 None（slots 模式同样）；
# 补丁为身份哈希，避免 Song 被意外放入 set/dict 键时抛 unhashable TypeError
Song.__hash__ = lambda self: id(self)


@dataclass
class Analysis:
    """用户状态分析结果"""
    task_type: str = ""
    task_detail: str = ""      # 细粒度任务状态（如：调试排错）
    task_demand: str = ""
    emotion: str = ""
    emotion_detail: str = ""   # 细粒度情绪状态（如：截止压力）
    emotion_intensity: int = 5
    emotion_source: str = ""   # explicit(用户明说) / task_inferred(由任务推断) / context_inferred(由时段等上下文推断)
    need_regulation: bool = False
    regulation_goal: str = ""
    language_preference: str = "no_preference"  # chinese / english / no_preference
    user_preferences: dict = field(default_factory=dict)  # 用户音乐偏好（注册后调查）

    def to_dict(self) -> dict:
        return {
            "task_type": self.task_type, "task_detail": self.task_detail,
            "task_demand": self.task_demand, "emotion": self.emotion,
            "emotion_detail": self.emotion_detail,
            "emotion_intensity": self.emotion_intensity,
            "emotion_source": self.emotion_source,
            "need_regulation": self.need_regulation,
            "regulation_goal": self.regulation_goal,
            "language_preference": self.language_preference,
        }


@dataclass
class MusicStrategy:
    """音乐策略"""
    genres: List[str] = field(default_factory=list)
    energy_level: int = 5
    tempo_range: str = ""
    instrumental_preferred: bool = False
    mood_target: str = ""
    explanation: str = ""
    priority: str = ""
    notes: str = ""
    session_advice: str = ""

    def to_dict(self) -> dict:
        return {
            "genres": self.genres, "energy_level": self.energy_level,
            "tempo_range": self.tempo_range,
            "instrumental_preferred": self.instrumental_preferred,
            "mood_target": self.mood_target, "explanation": self.explanation,
            "priority": self.priority, "notes": self.notes,
            "session_advice": self.session_advice,
        }


# 风格 → 乐器类型推断
GENRE_INSTRUMENT_MAP = {
    "classical": "钢琴",
    "neo-classical": "钢琴",
    "minimalist": "钢琴",
    "ambient": "合成器",
    "electronic": "合成器",
    "folk": "原声吉他",
    "indie": "吉他",
    "rock": "电吉他",
    "pop": "钢琴",
    "jazz": "萨克斯",
    "r&b": "贝斯",
    "hip-hop": "鼓机",
}


def infer_instrument_type(genre: str) -> str:
    g = (genre or "").lower()
    return GENRE_INSTRUMENT_MAP.get(g, "钢琴")


# ======================================================================
# 是否有歌词 → 语言板块归类
#
# 曲库里的 instrumental 字段来自抓取时的搜索词，天然带两类误差：
#   · 人声歌被标成纯音乐（用"伴奏 / lofi / 钢琴曲"等词搜到的人声歌）
#   · 纯音乐被标成人声（OST、后摇、新世纪等器乐曲）
# 这里按 歌名 / 专辑 / 风格 / 艺人 逐曲校正，保证"只要没有歌词就归纯音乐"，
# 不再混进中文歌 / 英文歌 / 其它语言板块。
# ======================================================================

# 明确表示"无歌词"的词（出现即判定纯音乐）
# 注：判定只依据歌名/专辑/艺人文本 —— 曲库 genre 字段噪声大（流行人声歌被标
# classical/ambient 的情况不少），拿风格兜底会把 Ariana Grande 这类歌判成纯音乐。
_STRONG_INST_RE = re.compile(
    r"纯音乐|纯音|器乐|伴奏|无人声|无歌词|卡拉ok|karaoke|"
    r"instrumental|inst\.|off[\s\-]?vocal|"
    r"背景音乐|轻音乐|白噪音|白噪声|环境音|氛围音|八音盒|音乐盒|"
    r"music\s*box|sounds?\s*of\s*nature|nature\s*sounds|rain\s*sounds|white\s*noise|"
    r"助眠|催眠曲|催眠音乐|安眠曲|摇篮曲|疗愈|脑波|α波|自然之声|"
    r"雨声|水声|鸟鸣|森林声|海浪声|纯音合集|"
    r"lofi|lo-?fi|器乐曲|演奏版|独奏曲",
    re.I)

# 明确表示"有人声/歌词"的词（出现即判定有歌词）
_STRONG_VOCAL_RE = re.compile(
    r"人声|vocal\s*version|demo\s*vocal|演唱|翻唱|原唱|对唱|独唱|童声|"
    r"歌词|lyric|\bfeat\.|\bft\.\s",
    re.I)

# 合唱 = 一群人声演唱，必然是"有歌词"的作品（《黄河大合唱》、韩剧合唱 OST 等）。
# 单列是因为"中国交响乐团合唱团"这类艺名同时含"交响乐团"，不加这条会被误判成纯音乐。
_CHORUS_RE = re.compile(r"合唱|chorus|choir|choral|重唱", re.I)

# 现场版 / 母带标注等弱人声信号（器乐现场也存在，优先级低于强信号）
_WEAK_VOCAL_RE = re.compile(
    r"演唱会|现场版|现场|\blive\b|explicit|铃声|\bmv\b|sped\s*up",
    re.I)

# 器乐体裁词（钢琴曲、四重奏、协奏曲…）
# 注意：不再接受 "piano version" / "guitar version"——这是"编曲版本"而非
# "无人声演奏"，K-pop/华语流行里极常见（《… (Guitar Version)》仍有人声）。
_WEAK_INST_RE = re.compile(
    r"钢琴曲|吉他曲|小提琴|大提琴|萨克斯|陶笛|口琴|尤克里里|手风琴|马头琴|"
    r"弦乐|四重奏|五重奏|管弦|交响|协奏曲|奏鸣曲|练习曲|圆舞曲|小步舞曲|"
    r"独奏|instrumental\s*version|"
    r"piano\s*(solo|music|collections?)|guitar\s*solo",
    re.I)

# 演奏者/曲名里的器乐信号（补判被漏的纯音乐）：
#  - 括号内的"无演唱"标注：(纯音乐)/(钢琴版)/(纯筝版)/(吉他独奏)/(Piano Solo)…
#  - 木吉他/指弹/古典吉他/弗拉门戈/二胡独奏等器乐体裁
# 注意：不能接受 (Guitar Version)/(Piano Ver.)！
#   流行/韩流里的"Guitar Version"多指"以吉他伴奏为主、仍有人声"的编曲版本，
#   如《To You My Light (feat. ...) (Guitar Version)》《한사람 (Piano Slow Ver.)》，
#   判成纯音乐是错的。只有 (钢琴版)/(纯筝版)/(器乐版)/(演奏版)/(独奏) 这类
#   明确指向"无人声演奏"的标注才可信。
_INST_PAREN_RE = re.compile(
    r"[（(\[【][^)）\]】]{0,12}?"
    r"(纯音乐|纯音|纯筝|器乐版|演奏版|纯享版|钢琴曲|钢琴版|钢琴独奏|钢琴弹奏|"
    r"吉他版|吉他独奏|木吉他版|电吉他版|古筝版|古琴版|二胡版|琵琶版|笛子版|"
    r"箫版|洞箫版|排箫版|萨克斯版|手风琴版|竖琴版|口琴版|八音盒版|"
    r"instrumental|piano\s*solo|guitar\s*solo|solo\s*(piano|guitar|violin|cello)|"
    r"piano\s*only|无词|无人声)"
    r"[^)）\]】]{0,12}?[)）\]】]",
    re.I)

# 器乐体裁 / 演奏形态（中英）：木吉他、指弹、弗拉门戈、爵士吉他、二胡独奏…
_INST_GENRE_RE = re.compile(
    r"木吉他|指弹|fingerstyle|弗拉门戈|flamenco|古典吉他|classical\s*guitar|"
    r"acoustic\s*guitar|spanish\s*guitar|jazz\s*guitar|guitar\s*(greats|artistry|on\s*fire)|"
    r"二胡独奏|古筝独奏|琵琶独奏|笛子独奏|唢呐独奏|板胡独奏|京胡独奏|柳琴独奏|冬不拉|"
    r"军鼓|小军鼓|马林巴|marimba|定音鼓|"
    r"钢琴小品|piano\s*(pieces|sonata|concerto|suites?|works)|"
    r"cello\s*suites?|violin\s*(concerto|sonata|caprices?)|string\s*quartet|"
    r"chamber\s*music|室内乐|器乐独奏|器乐演奏",
    re.I)

# 古典器乐作品号形态（无风格佐证也可判纯乐器乐）：
#  "Op. 11: II. Andante" / "BWV 846" / "K.522: 2. Menuett" / "OP.20 Scene" / "S. 514"
# 注意：\b 只加在英文缩写前后；"Op." 后可能紧跟空格或数字，故不用 \b 收尾。
_CLASSICAL_WORK_STRICT_RE = re.compile(
    r"\b(?:op|opus|bwv|woo|kv|hob)\.?\s*\d+"
    r"|\bk\.\s*\d+"
    r"|\bs\.\s*\d{2,4}"
    r"|\brv\.?\s*\d+"
    r"|\bd\.\s*\d{2,3}\b"
    r"|\btrv\.?\s*\d+",
    re.I)

# 著名器乐演奏家（只收录"几乎只演奏、不演唱"的独奏家）。
# 这类艺人的作品名常无任何器乐关键词（如 马友友《Salut d'amour》、
# 吕思清《舒伯特:小夜曲》），单看曲名会漏判成英文/中文歌。
# 判定条件是「作品名带古典器乐形态」+「演奏家在此表内」，双条件成立才判，
# 避免把同名翻唱人的流行歌误收。
_FAMOUS_INSTRUMENTALIST_RE = re.compile(
    r"马友友|郎朗|李云迪|王羽佳|吕思清|巫娜|翟慧莉|盛中国|俞丽拿|宋飞|"
    r"赵聪|吴玉霞|唐俊乔|郎毓秀|张维良|刘德海|闵惠芬|蒋彦|"
    r"Paco\s*de\s*Lucia|John\s*Williams|Pepe\s*Romero|Andr[eé]s\s*Segovia|"
    r"Yo-?Yo\s*Ma|Lang\s*Lang|Yuja\s*Wang|Itzhak\s*Perlman|Hilary\s*Hahn|"
    r"Maxim\s*Vengerov|Maksim|Maksim\s*Mrvica|Richard\s*Clayderman|"
    r"Andr[aá]s\s*Schiff|Murray\s*Perahia|Evgeny\s*Kissin|Daniel\s*Barenboim|"
    r"Bill\s*Frisell|Tal\s*Farlow|John\s*H\.?\s*Clarke|Johannes\s*Linstead|"
    r"Antonio\s*De\s*Lucena|Jerry\s*Byrd|Lavinia\s*Meijer|Julian\s*Lloyd\s*Webber|"
    r"Joshua\s*Bell|Edgar\s*Meyer|Radu\s*Lupu|Gustavo\s*Dudamel|"
    r"Herbert\s*Von\s*Karajan|Berliner\s*Philharmoni\w*|Wiener\s*Philharmoni\w*|"
    r"London\s*Symphony|Academy\s*of\s*St\.?\s*Martin",
    re.I)

# 纯音乐/配乐作曲家：本人几乎不演唱，作品绝大多数是器乐（钢琴曲/影视配乐）。
# 曲名常无任何曲式词（久石让《空中散歩》、李闰珉《River Flows in You》、
# 坂本龙一《Merry Christmas Mr. Lawrence》），且 genre 常被误标为 pop，
# 无法靠"古典风格"佐证。这些艺人单独设强规则：只要标题/专辑无强人声信号即判纯音乐。
_PURE_COMPOSER_RE = re.compile(
    r"久石让|Joe\s*Hisaishi|李闰珉|Yiruma|坂本龙一|Ryuichi\s*Sakamoto|"
    r"菅野洋子|Yoko\s*Kanno|Kitaro|喜多郎",
    re.I)

# 纯乐器词（标题里出现即提示器乐，作为**佐证**而非单独定案；
# 不含"吉他"这种泛词，因为"吉他手/Guitar by"是人声歌的常见标注）。
_BARE_INSTRUMENT_RE = re.compile(
    r"\bsaxophone\b|\bcello\b|\bviolin\b|\bviola\b|\bflute\b|\bclarinet\b|"
    r"\bharp\b|\btrumpet\b|\btrombone\b|\boboe\b|\bbassoon\b|\bharpsichord\b|"
    r"\borgan\s*(solo|music)\b|\blute\b|\bduduk\b|\bsitar\b|\bsantoor\b|\boud\b|"
    r"萨克斯|大提琴|小提琴|中提琴|长笛|单簧管|双簧管|竖琴|小号|长号|二胡|"
    r"古筝|古琴|马头琴|陶笛|排箫|洞箫|唢呐|笙|扬琴|柳琴",
    re.I)
# 标题含乐器名但实为诗歌/人声作品（如 奇然《琵琶行》、许嵩《琴师》），
# 不得据此判纯音乐。
_BARE_INSTR_EXCLUDE_RE = re.compile(r"琵琶行|琵琶语|琴师|吉他手|钢琴师|提琴手|琴师")

# 标题里带"人声体裁词"但实为器乐的知名作品（少数例外，需点名放行）。
# 例：巴赫《G弦上的咏叹调》含"咏叹调(aria)"却是纯器乐；
#     《无词歌》含"歌"却无词。
_KNOWN_INSTR_WORK_RE = re.compile(
    r"G弦上的咏叹调|Air\s+on\s+the\s+G\s+String|无词歌|Songs?\s+Without\s+Words|"
    r"婚礼进行曲|Wedding\s+March|摇篮曲\s*\(?器乐|"
    r"土耳其进行曲|Turkish\s+March|命运交响曲|欢乐颂\s*\(?交响|"
    r"哥德堡|Goldberg\s*Variations?|哥德堡变奏曲|"
    r"彼得与狼|Peter\s+and\s+the\s+Wolf",
    re.I)

# 器乐作品名形态：仅作为「风格/演奏家」成立时的**补充佐证**，绝不单独判定。
# 因为《夜曲》(周杰伦)、《小夜曲》等流行歌名与古典曲式同名，单用会大量误收。
# 这里只保留"流行歌名几乎不会用"的高度特异写法（带作曲家前缀、芭蕾/协奏标题、
# 无词歌、gymnopedie 等）。
_CLASSICAL_TITLE_FORM_RE = re.compile(
    r"[a-z\u00c0-\u024f\u4e00-\u9fff]+\s*[:：\-—–]\s*(小夜曲|夜曲|圆舞曲|练习曲|前奏曲|"
    r"间奏曲|叙事曲|摇篮曲|幻想曲|变奏曲|咏叹调)|"
    r"无词歌|songs?\s*without\s*words|gymnop[eé]die|"
    r"ballet\s*suite|swan\s*lake|the\s*nutcracker|danse\s*des|"
    r"canon\s*in\s*d\b|moonlight\s*sonata|f[uü]r\s*elise|"
    r"arr\.?\s*for\s*(harp|guitar|cello|violin|piano|organ)",
    re.I)

# 影视/游戏原声（人声与器乐混杂，需结合风格与艺人再判）
_OST_RE = re.compile(r"\bost\b|soundtrack|サウンドトラック|原声带|原聲帶|影视原声", re.I)

# 以器乐为主的风格。古典 / 新古典 / 极简 / 氛围四类里器乐作品占绝大多数，
# 但该字段本身有噪声（个别流行人声歌被标为 classical/ambient），
# 因此不能单凭风格判定，只作为「作品特征 / 演奏者特征」成立时的佐证。
_CLASSICAL_GENRES = frozenset({"classical", "neo-classical", "minimalist", "ambient"})

# 乐器演奏者 / 音乐制作号（原声带判定时用于区分器乐原声与流行人声OST）
_INSTR_ARTIST_RE = re.compile(
    r"orchestra|ensemble|quartet|quintet|trio|sinfonia|philharmonic|piano|guitar|"
    r"beats|project|collective|various\s*artists|"
    r"演奏|纯音乐|音乐|工作室|疗愈|助眠|频道|钢琴|乐器",
    re.I)

# ----------------------------------------------------------------------
# 古典 / 器乐作品的结构特征
#
# 曲库里大量"无歌词"的作品（肖邦练习曲、贝多芬交响曲、克莱德曼钢琴曲…）
# 曲名里既没有"纯音乐"也没有"instrumental"，只凭关键词会漏判，
# 于是被当成按文字体系分类的"中文歌 / 英文歌"。这里补充按作品结构判定：
#   · 作品编号（Op. / BWV / K. / WoO）
#   · "No. 12 in C Minor" 这类作品序号 + 调性
#   · 乐章编号（"I." "II." "III."）或速度术语（Allegro / Andante / Largo…）
#   · 古典曲式名（Concerto / Sonata / Etude / Nocturne / Symphony…）
# 注意：Cantata / Oratorio / Mass / Lied / 合唱 等带人声的体裁不在列表内。
# ----------------------------------------------------------------------
_CLASSICAL_WORK_RE = re.compile(
    r"\b(opus|op\.|bwv|woo|k\.\s*\d|kv\.?\s*\d|hob\.|d\.\s*\d{2,3})\b|"
    r"\bno\.\s*\d+\s*(in\s+[a-g][#b]?\s*(major|minor))?|"
    r"\b(concerto|symphony|sinfonia|sonata|etude|étude|nocturne|prelude|fugue|"
    r"waltz|valse|rondo|variations?|suite|arabesque|impromptu|ballade|serenade|"
    r"barcarolle|caprice|capriccio|toccata|intermezzo|scherzo|partita|invention|"
    r"gymnop[eé]die|canon|march|mazurka|polonaise|tarantella|"
    r"adagio|andante|allegro|largo|presto|vivace|lento|maestoso|moderato|"
    r"overture|ritornello|divertimento)\b",
    re.I)

# 中文古典曲式名（简繁）："第40號交響曲第一樂章"、"土耳其进行曲"、"月光奏鸣曲"。
# 只收录流行歌名几乎不会用的高特异曲式（交响曲/协奏曲/奏鸣曲/进行曲/赋格…），
# 不含"夜曲/小夜曲/摇篮曲/圆舞曲"（周杰伦《夜曲》等流行歌同名，靠 genre 佐证也
# 可能因 genre 误标而误伤）。同样需要步骤 4 的 genre/器乐线索佐证才定案。
_CLASSICAL_WORK_CN_RE = re.compile(
    r"交响曲|交響曲|协奏曲|協奏曲|奏鸣曲|奏鳴曲|进行曲|進行曲|"
    r"赋格|賦格|变奏曲|變奏曲|组曲|組曲|序曲|练习曲|練習曲|随想曲|隨想曲|"
    r"托卡塔|创意曲|創意曲|前奏曲|间奏曲|間奏曲|诙谐曲|詼諧曲|"
    r"交响诗|交響詩|乐章|樂章|"
    r"第[一二三四五六七八九十百\d]+[号號]?\s*(交响|交響|协奏|協奏|奏鸣|奏鳴|进行|進行)",
    re.I)

# 乐章编号开头（罗马数字 + 分隔符），如「I. Allegro con brio」「III. Scherzo」
_MOVEMENT_RE = re.compile(r"^\s*(i{1,3}|iv|v|vi{0,3}|ix|x)\s*[\.\-\u2013\u2014]\s*\S", re.I)

# 乐器 / 演奏者 / 器乐专辑线索：仅作为风格是古典类时的佐证，不单独判定
_INS_HINT_RE = re.compile(
    r"piano|guitar|violin|cello|viola|saxophone|\bsax\b|flute|clarinet|harp|organ|"
    r"orchestra|ensemble|quartet|quintet|sinfonia|philharmoni\w*|soloists?|"
    r"instrumental|acoustic|strings|chamber|recital|concerto|ambient|new\s*age|"
    r"meditation|典藏|精选|合集|合辑|collection|essential|complete|greatest|best\s*of|"
    r"钢琴|吉他|小提琴|大提琴|中提琴|萨克斯|长笛|陶笛|口琴|竖琴|管风琴|尤克里里|"
    r"马头琴|古筝|琵琶|二胡|笛子|手风琴|弦乐|管弦|交响|乐团|爱乐|"
    r"演奏|独奏|协奏|纯音乐|纯音|器乐|轻音乐|音乐盒|八音盒|"
    r"睡眠|睡前|入睡|静心|减压|疗愈|放松|专注",
    re.I)

# 带"人声角色 / 声乐体裁"标记的条目：康塔塔、清唱剧、宣叙调、咏叹调、
# 声部名等，说明是歌唱作品而非器乐（《马太受难曲》的 Evangelist 段落等）。
# 注意：
#   · 不含"aria"单词——《哥德堡变奏曲》的 Aria 开头是纯器乐；
#   · 声部名排除 "tenor sax" / "baritone guitar" 这类乐器写法。
_VOCAL_FORM_RE = re.compile(
    r"recitative|oratorio|cantata|cantate|\bchoir\b|\bchorus\b|madrigal|motet|lieder|"
    r"soprano|mezzo[\s\-]?soprano|evangelist|"
    r"\btenor\b(?!\s*sax)|\bbaritone\b(?!\s*(sax|guitar|uke))|"
    r"宣叙调|咏叹调|清唱剧|康塔塔|声乐|女高音|男高音|男中音|女中音",
    re.I)

# 假名字母：故意排除 ・(U+30FB) 与 ー(U+30FC)。这两个是标点/长音符而非字母，
# 中文专辑名常拿它们当装饰（《午后琴语・放松时光》），算进来会把中文歌误判成日语。
_LYRICS_SCRIPT_KANA_RE = re.compile(r"[\u3040-\u30fa\u30fd-\u30ff]")
_LYRICS_SCRIPT_HANGUL_RE = re.compile(r"[\uac00-\ud7af\u1100-\u11ff\u3130-\u318f]")
_LYRICS_SCRIPT_CJK_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")
# 西里尔 / 希腊 / 泰 / 阿拉伯 / 天城文 / 希伯来：既非中文也非英文
_LYRICS_SCRIPT_OTHER_RE = re.compile(
    r"[\u0400-\u04ff\u0370-\u03ff\u0e00-\u0e7f\u0600-\u06ff\u0900-\u097f\u0590-\u05ff]")

# ----------------------------------------------------------------------
# 艺人级语种推断：治"汉字艺名 + 无汉字标题"被误判成中文歌
#
# 动画/游戏 OST 的作曲家常以汉字署名（澤野弘之 / 久石让 / 光田康典 / 梶浦由记），
# 作品标题又常是纯拉丁文（《[Solo-Leveling]SymphonicSuite-Lv.1》）。歌名与艺人都
# 没有假名、专辑名也没有，于是被判定成"中文歌"，混进"想听中文歌"的结果里。
#
# 单个艺人看不出来，但**整个艺人的作品集**能看出来：这些人的专辑名大量是日文
# （《俺だけレベルアップな件 Original Soundtrack》），假名出现比例很高。于是按艺人
# 聚合统计假名/谚文占比，占比和样本量都够，就认定该艺人是日语/韩语艺人。
#
# 只用于纠正"标题主体无汉字、仅因艺人名是汉字才判中文"的歌——带汉字的歌一律不动，
# 否则会把邓丽君（在日本发展、作品集里假名占比也不低）的中文歌整片搬走。
_ARTIST_LANG_HINTS: Dict[str, str] = {}

_ARTIST_LANG_MIN_HITS = 3      # 证据条数下限，避免一两首日文翻唱就把艺人整体定性
_ARTIST_LANG_MIN_RATIO = 0.15  # 证据占比下限（中文艺人实测 0%~1%，日韩艺人普遍 >20%）
_ARTIST_LANG_EVIDENCE_MIN = 2  # 单首歌要出现几个假名字母才算一条证据

# 只用于"这条算不算日文证据"：真假名字母（排除 ・ ー）。
_ARTIST_LANG_KANA_RE = re.compile(r"[\u3041-\u309f\u30a1-\u30fa]")
_ARTIST_LANG_HANGUL_RE = re.compile(r"[\uac00-\ud7af]")


def artist_lang_hints(songs) -> Dict[str, str]:
    """按艺人聚合假名/谚文证据，推断艺人级语种（japanese / korean）

    返回 {艺人名: "japanese" | "korean"}；证据不足或艺人名本身已带假名/谚文的
    不参与（那些条目本来就能逐条判对）。
    """
    stat: Dict[str, list] = {}
    for song in songs:
        artist = (getattr(song, "artist", "") or "").strip()
        if not artist:
            continue
        st = stat.get(artist)
        if st is None:
            st = stat[artist] = [0, 0, 0]      # [总数, 假名, 谚文]
        st[0] += 1
        text = (getattr(song, "title", "") or "") + " " \
            + (getattr(song, "album", "") or "")
        # 单首歌要出现 >=2 个假名字母才算一条日文证据：中文条目偶尔会借一个 の
        # 当装饰（专辑《香の香翻唱》），只有一个假名字母时不足以定性。
        if len(_ARTIST_LANG_KANA_RE.findall(text)) >= _ARTIST_LANG_EVIDENCE_MIN:
            st[1] += 1
        if len(_ARTIST_LANG_HANGUL_RE.findall(text)) >= _ARTIST_LANG_EVIDENCE_MIN:
            st[2] += 1

    hints: Dict[str, str] = {}
    for artist, (total, kana, hangul) in stat.items():
        if _ARTIST_LANG_KANA_RE.search(artist) \
                or _ARTIST_LANG_HANGUL_RE.search(artist):
            continue
        if kana >= _ARTIST_LANG_MIN_HITS \
                and kana / total >= _ARTIST_LANG_MIN_RATIO:
            hints[artist] = "japanese"
        elif hangul >= _ARTIST_LANG_MIN_HITS \
                and hangul / total >= _ARTIST_LANG_MIN_RATIO:
            hints[artist] = "korean"
    return hints


def set_artist_lang_hints(hints) -> None:
    _ARTIST_LANG_HINTS.clear()
    if hints:
        _ARTIST_LANG_HINTS.update(hints)


def artist_lang_hint(artist) -> str:
    return _ARTIST_LANG_HINTS.get((artist or "").strip(), "")


# 歌词实测语种表：离线抓取歌词、剔除"词/曲/编曲/版权"等元信息行后按正文文字
# 系统判定（明细见 backend/lyrics_lang.json）。元数据（歌名/专辑/艺人名）分不出
# 语种时以它为准——"中国人唱的英文歌"正是靠这张表从中文歌里摘出来的，
# 判断依据是歌词本身，与艺人国籍/姓名无关。
_LYRICS_LANG: Dict[str, str] = {}


def set_lyrics_lang(mapping) -> None:
    _LYRICS_LANG.clear()
    if mapping:
        _LYRICS_LANG.update(mapping)


def lyrics_lang(song_id) -> str:
    return _LYRICS_LANG.get(song_id or "", "")


# 板块中文名（前后端共用同一套口径）
LANGUAGE_LABELS = {
    "instrumental": "纯音乐",
    "chinese": "中文歌",
    "english": "英文歌",
    "other": "其它语言",
}

# 用户点名的语言 → 命中的细分语种集合
# 界面上只有四个板块（中/英/其它/纯音乐），但"想听日语歌"仍要能精确命中，
# 因此请求侧保留 japanese / korean 等细分语种，"other" 覆盖日韩以外的一切外语。
LANG_GROUPS = {
    "chinese": ("chinese",),
    "english": ("english",),
    "japanese": ("japanese",),
    "korean": ("korean",),
    "other": ("japanese", "korean", "other"),
}


def infer_instrumental(title: str, album: str, artist: str,
                       genre: str, db_flag: bool) -> bool:
    """逐曲判定"是否无歌词"（True=纯音乐，归入纯音乐板块）

    判定顺序（先拦人声，再认器乐，最后才沿用曲库标记）：
      1. 强无歌词词（纯音乐 / 伴奏 / 白噪音…）
      2. 强人声词 / 合唱（出现即排除，优先级高于一切器乐特征）
      3. 括号内乐器标注（(钢琴版)/(Guitar Ver.)）/ 器乐体裁词（木吉他/指弹/二胡独奏）
      4. 严格作品号（Op./BWV/K.）+ 风格或演奏者佐证
      5. 古典器乐作品结构（作品号 / 乐章编号 / 曲式名）+ 风格或演奏者佐证
      6. 器乐体裁词（钢琴曲 / 四重奏 / 协奏曲…）
      7. 原声带（结合艺人特征与风格再判）
      8. 弱人声词（现场 / 铃声…）
      9. 器乐类风格 + 乐器 / 演奏者线索
     10. 沿用曲库标记
    """
    title = title or ""
    album = album or ""
    artist = artist or ""
    text = f"{title} {album}"
    g = (genre or "").strip().lower()
    aux = f"{album} {artist}"

    # 1) 明确"无歌词"
    if _STRONG_INST_RE.search(text):
        return True
    # 2) 明确"有歌词"：强人声词 / 合唱（含艺人名，如"××少儿合唱团"）/ 声乐体裁。
    #    必须先于所有器乐特征，避免器乐型艺人名、专辑名误伤。
    #    例外 1：极少数标题含人声体裁词、实为器乐的知名作品先行放行。
    #    例外 2：标题带明确的"无人声演奏"标注（钢琴版/纯筝版/器乐版…），
    #            即使同一条目里还有"原唱：×××"这类版权署名，也判纯音乐。
    #            例：《梦中的婚礼 (钢琴版I原唱：胡彦斌)》。
    if _KNOWN_INSTR_WORK_RE.search(text) or _INST_PAREN_RE.search(title):
        return True
    # 著名器乐演奏家 + 强古典曲式（协奏曲/交响曲/奏鸣曲…）优先放行：
    # 郎朗《柴可夫斯基第一钢琴协奏曲》这类条目，专辑常带"跨年演唱会"等词
    # （他在演唱会上弹钢琴而非演唱），不能因此误判为人声。
    if _FAMOUS_INSTRUMENTALIST_RE.search(artist) and (
            _CLASSICAL_WORK_CN_RE.search(title)
            or _CLASSICAL_WORK_STRICT_RE.search(title)):
        return True
    if _STRONG_VOCAL_RE.search(text) or _CHORUS_RE.search(aux) \
            or _VOCAL_FORM_RE.search(text):
        return False
    # 2.5) 纯音乐/配乐作曲家：本人不演唱，作品几乎全是器乐。
    #      已过上面的强人声/合唱/声乐体裁拦截，此处直接判纯音乐。
    if _PURE_COMPOSER_RE.search(artist):
        return True
    # 3) 括号内乐器标注 / 器乐体裁词：信号足够强，不必依赖风格佐证。
    #    例：《晴天(钢琴版)》《Kiss The Rain (Guitar Ver.)》《箫版·大鱼》
    #    放在人声拦截之后，避免"现场版/翻唱(吉他版)"里带人声词的被误收。
    if _INST_PAREN_RE.search(text) or _INST_GENRE_RE.search(text):
        return True
    # 3.5) 严格作品号（Op. / BWV / K. / WoO / S.）：这是**高特异**信号——
    #      流行/民谣几乎不会带古典作品号，因此可直接判纯音乐。
    #      例："Humoresque No. 7 ... Op. 101"、"Swan Lake OP.20"、
    #      "Mozart: ... K.522: 2. Menuett"、"Mephisto Waltz No. 1, S. 514"。
    #      仍先过第 2 步人声/合唱/声乐体裁拦截（如 "K.522 ... Soprano"）。
    if _CLASSICAL_WORK_STRICT_RE.search(title):
        return True
    # 3.6) 著名器乐独奏家 + 曲名带古典器乐形态（作品号 / 曲式 / 无词歌…）
    #      例：马友友《Salut d'amour, Op. 12》、吕思清《舒伯特:小夜曲》。
    #      双条件才能成立，避免同名翻唱人的流行歌被误收。
    if _FAMOUS_INSTRUMENTALIST_RE.search(artist) and (
            _CLASSICAL_WORK_STRICT_RE.search(title)
            or _CLASSICAL_WORK_RE.search(title)
            or _CLASSICAL_WORK_CN_RE.search(title)
            or _CLASSICAL_TITLE_FORM_RE.search(title)
            or _INS_HINT_RE.search(aux)
            or _MOVEMENT_RE.match(title)
            or g in _CLASSICAL_GENRES):
        return True
    # 3.7) 曲名形态就是器乐作品（无词歌 / Ballet Suite / Arr. for Harp…）
    #      且风格或演奏者/专辑指向器乐 —— 例：Gymnopédie (Arr. for Harp)
    if _CLASSICAL_TITLE_FORM_RE.search(title):
        if g in _CLASSICAL_GENRES or _INS_HINT_RE.search(aux) \
                or _FAMOUS_INSTRUMENTALIST_RE.search(artist):
            return True
    # 3.8) 曲名/专辑就是乐器词本身（如 "Jazz saxophone"、"最美大提琴"），
    #      这是纯器乐专辑的典型命名。排除《琵琶行》《琴师》这类
    #      "含乐器名但实为人声歌"的作品。
    if _BARE_INSTRUMENT_RE.search(text) and not _WEAK_VOCAL_RE.search(text) \
            and not _BARE_INSTR_EXCLUDE_RE.search(title):
        return True
    # 4) 古典 / 器乐作品：曲名带作品结构特征，且风格或演奏者指向器乐
    if _MOVEMENT_RE.match(title) or _CLASSICAL_WORK_RE.search(title) \
            or _CLASSICAL_WORK_CN_RE.search(title):
        if g in _CLASSICAL_GENRES or _INS_HINT_RE.search(aux):
            return True
    # 4.5) 器乐体裁词
    if _WEAK_INST_RE.search(text):
        return True
    # 5) 原声带人声/器乐混杂：韩剧 OST 多为人声，器乐原声多出自演奏者与古典厂牌
    if _OST_RE.search(text):
        return bool(_INSTR_ARTIST_RE.search(artist)) or g in _CLASSICAL_GENRES
    # 6) 弱人声信号
    if _WEAK_VOCAL_RE.search(text):
        return False
    # 7) 器乐类风格 + 乐器 / 演奏者线索
    #    例：李闰珉《Kiss The Rain》（neo-classical，专辑 Healing Piano）
    if g in _CLASSICAL_GENRES and _INS_HINT_RE.search(aux):
        return True
    # 8) 沿用曲库标记
    return bool(db_flag)


def song_language_fine(song: "Song") -> str:
    """细分语种：instrumental / chinese / english / japanese / korean / other

    日语、韩语在界面上与其它外语同属"其它语言"板块，但用户点名
    "想听日语歌"时要能精确命中，因此这里保留比板块更细的结果。
    """
    if getattr(song, "instrumental", False):
        return "instrumental"
    title = song.title or ""
    artist = song.artist or ""
    text = f"{title} {artist}"
    # 假名/谚文优先于汉字：日语歌常带汉字、韩语歌常带汉字团名
    if _LYRICS_SCRIPT_KANA_RE.search(text):
        return "japanese"
    if _LYRICS_SCRIPT_HANGUL_RE.search(text):
        return "korean"
    # 专辑名里的假名/谚文同样能定性：日韩动画·剧集 OST 常由汉字名艺人演唱
    # （澤野弘之《Call of Silence》专辑「TVアニメ「進撃の巨人」…」、梶浦由记
    # 《this is my despair》专辑「劇場版 魔法少女まどか☆マギカ…」），
    # 只看歌名与艺人名会把它们误判成中文歌、混进"想听中文歌"的结果里。
    # 实测：15.7 万首判为中文的歌里仅 2,362 首（1.5%）命中该形态，且几乎全是
    # 日韩 OST；周杰伦等头部中文歌手各仅 0~1 首受影响，误伤可忽略。
    album = getattr(song, "album", "") or ""
    if _LYRICS_SCRIPT_KANA_RE.search(album):
        return "japanese"
    if _LYRICS_SCRIPT_HANGUL_RE.search(album):
        return "korean"
    # 歌词实测语种优先于一切"看名字"的推断：方大同/陶喆/陈冠希等华语歌手的
    # 英文歌，歌名与艺人名都是汉字，只有歌词能证明唱的是英文；日韩艺人拿汉字
    # 当歌名同理（LiSA《紅蓮華》、Mr.Children《口笛》）。离线抓取，见
    # lyrics_lang.json；没有歌词证据时才轮到下面几段按名字判断。
    measured = _LYRICS_LANG.get(song.id)
    if measured:
        return measured
    # 中文判定只看"歌名主体（去括号注释）+ 艺人名"：
    # 英文歌常带中文注释后缀（"2026世界杯开幕式现场""第68届格莱美奖"），
    # 若汉字全在括号注释里、主体与艺人都无汉字，应判英文而非中文。
    title_core = re.sub(r"[（(【\[][^)）】\]]*[)）】\]]", " ", title)
    if _LYRICS_SCRIPT_CJK_RE.search(title_core):
        return "chinese"
    # 无歌词证据时退到艺人级推断："标题主体没有汉字"此刻判中文只是因为艺人名
    # 是汉字，而汉字艺名的日韩艺人（澤野弘之 / 郑成河）正是靠这条路混进来的。
    # 带汉字的标题在上面已经返回，所以这里不会动到邓丽君等人的中文歌。
    if _LYRICS_SCRIPT_CJK_RE.search(artist):
        hint = _ARTIST_LANG_HINTS.get(artist.strip())
        return hint or "chinese"
    if _LYRICS_SCRIPT_OTHER_RE.search(text):
        return "other"
    return "english"


def song_language(song: "Song") -> str:
    """语言板块归类：instrumental / chinese / english / other

    纯音乐优先于语言判断——只要没有歌词就归纯音乐板块，
    不再计入中文歌 / 英文歌 / 其它语言；日韩等语种并入"其它语言"。
    """
    fine = song_language_fine(song)
    return "other" if fine in ("japanese", "korean") else fine


def language_matches(request_lang: str, fine_lang: str) -> bool:
    """用户点名的语言是否命中该曲的细分语种（映射见 LANG_GROUPS）"""
    return fine_lang in LANG_GROUPS.get(request_lang or "", ())


# 用户问卷里的"英文/日韩等外文"是偏好口径：选它代表"外文歌都行"。
# 必须与"点名要英文歌"（LANG_GROUPS["english"]）分开，否则日韩歌会被挡掉。
PREF_LANG_GROUPS = {
    "chinese": ("chinese",),
    "english": ("english", "japanese", "korean", "other"),
    "other": ("japanese", "korean", "other"),
}


def language_matches_pref(request_lang: str, fine_lang: str) -> bool:
    """按"用户偏好"口径匹配语种（问卷默认偏好等非点名场景使用）"""
    groups = PREF_LANG_GROUPS if (request_lang or "") in PREF_LANG_GROUPS \
        else LANG_GROUPS
    return fine_lang in groups.get(request_lang or "", ())


def language_label(code: str) -> str:
    return LANGUAGE_LABELS.get(code or "", LANGUAGE_LABELS["other"])


# ----------------------------------------------------------------------
# 情绪 → 单一情绪词
#
# 界面上"情绪"一栏只呈现一个词（如"专注""焦虑"），不展示推断过程，
# 也不把"情绪·细分说明"拼成一长串。情绪编码形如 calm-focused：
# 先看细分词（focused → 专注），细分词不是情绪词时（如 anxious-deadline 的
# deadline）再回退到大类（anxious → 焦虑）。
# ----------------------------------------------------------------------
EMOTION_WORDS = {
    # 愉悦 / 高唤醒
    "happy": "愉悦", "joyful": "愉悦", "delighted": "愉悦", "excited": "激动",
    "festive": "亢奋", "celebratory": "狂喜", "social": "轻快", "romantic": "浪漫",
    "confident": "自信", "hopeful": "期待", "uplifting": "振奋", "energetic": "活力",
    "energized": "提神", "powerful": "力量", "inspired": "灵感",
    # 平静 / 中性
    "calm": "平静", "relaxed": "松弛", "serene": "宁静", "peaceful": "安宁",
    "soothing": "舒缓", "warm": "温暖", "dreamy": "梦幻", "nostalgic": "怀旧",
    "reflective": "沉思", "mysterious": "神秘", "balanced": "平稳",
    "neutral": "平稳", "ordinary": "平稳", "bored": "无聊",
    # 专注
    "focused": "专注", "alert": "清醒",
    # 负向
    "anxious": "焦虑", "tension": "紧绷", "overwhelmed": "紧绷",
    "pressured": "紧张", "stressed": "紧张", "worried": "担忧",
    "tired": "疲惫", "sleepy": "困倦", "exhausted": "疲惫", "fatigued": "疲惫",
    "sad": "低落", "depressed": "低落", "lonely": "孤单", "melancholic": "惆怅",
    "frustrated": "受挫", "angry": "烦躁", "annoyed": "烦躁",
}


def emotion_word(emotion: str) -> str:
    """把情绪编码（如 calm-focused / anxious-deadline）压成一个情绪词。"""
    parts = [p for p in (emotion or "").strip().split("-") if p]
    if not parts:
        return "平稳"
    for p in reversed(parts):
        w = EMOTION_WORDS.get(p)
        if w:
            return w
    return EMOTION_WORDS.get(parts[0], "平稳")
