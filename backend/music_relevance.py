# -*- coding: utf-8 -*-
"""推荐相关性模型：标签特异性(IDF) + 情绪/任务语义邻接 + 能量与节奏百分位归一化

为什么需要这一层（基于 53.7 万首曲库的实测诊断）：
1) mood_tags 中 balanced 占 96%、task_tags 中 general+relax 占 83%，
   这些"兜底标签"若按等权命中参与打分，等于把匹配退化成随机；
   因此引入 IDF 特异性权重，兜底标签权重≈0，具体标签权重→1。
2) 策略模板与曲库词表不一致（energized/happy/warm 在曲库中不存在），
   导致情绪层完全失效；这里做别名归一化 + 词族邻接，词表不一致也能命中最近的邻居。
3) energy 有 95% 落在 4~6、tempo 有 70% 落在 80~99，
   绝对值比较几乎没有区分度；改用经验分布百分位 + 高斯核，
   使"跑步要 9 分能量"能真正区分 energy=6 / 5 / 4 的歌。

本模块只依赖标准库，保持项目"零第三方依赖"的架构约定。
"""
import math
import re
from typing import Dict, List, Optional, Sequence, Tuple

# --------------------------------------------------------------------------
# 1. 情绪词归一化
# --------------------------------------------------------------------------

# 策略/LLM 可能给出的同义词 → 曲库实际词表
MOOD_ALIASES = {
    "energized": "energetic", "energy": "energetic", "upbeat": "energetic",
    "excited": "energetic", "exciting": "energetic", "hype": "energetic",
    "hyper": "energetic", "driving": "energetic", "fast": "energetic",
    "power": "powerful", "epic": "powerful", "heroic": "powerful",
    "strong": "powerful", "intense": "powerful", "heavy": "powerful",
    "happy": "joyful", "cheerful": "joyful", "glad": "joyful",
    "delighted": "joyful", "bright": "joyful", "sunny": "joyful",
    "celebration": "celebratory", "party": "festive", "carnival": "festive",
    "holiday": "festive", "warm": "soothing", "gentle": "soothing",
    "tender": "soothing", "soft": "soothing", "sweet": "soothing",
    "melancholy": "sad", "sadness": "sad", "blue": "sad", "sorrow": "sad",
    "chill": "relaxed", "chillout": "relaxed", "mellow": "relaxed",
    "easy": "relaxed", "serene": "peaceful", "tranquil": "peaceful",
    "zen": "peaceful", "quiet": "calm", "silent": "calm", "noisy": "groovy",
    "concentrate": "focused", "concentration": "focused", "focus": "focused",
    "attentive": "focused", "uplifting": "hopeful", "optimistic": "hopeful",
    "motivated": "inspired", "motivating": "inspired", "inspiring": "inspired",
    "creative": "inspired", "nostalgic": "dreamy", "romantic_mood": "romantic",
    "romance": "romantic", "love": "romantic", "groove": "groovy",
    "awake": "alert", "energetic_dance": "groovy",
    "neutral": "", "none": "", "normal": "", "balanced_": "balanced",
}

# 情绪词族（同一族内互为"接近"；valence/arousal 相近）
MOOD_CLUSTER = {
    "calm": "low", "peaceful": "low", "soothing": "low", "relaxed": "low",
    "dreamy": "low", "romantic": "low",
    "energetic": "high", "powerful": "high", "groovy": "high",
    "joyful": "pos", "festive": "pos", "celebratory": "pos",
    "inspired": "pos", "hopeful": "pos",
    "focused": "focus", "alert": "focus",
    "sad": "sad",
    "balanced": "neutral",
}

# 词族间邻接度（对称）
_CLUSTER_AFF = {
    ("low", "low"): 1.0, ("high", "high"): 1.0, ("pos", "pos"): 1.0,
    ("focus", "focus"): 1.0, ("sad", "sad"): 1.0, ("neutral", "neutral"): 1.0,
    ("low", "focus"): 0.35, ("low", "pos"): 0.15, ("low", "high"): 0.0,
    ("low", "sad"): 0.35,
    ("high", "pos"): 0.60, ("high", "focus"): 0.35, ("high", "sad"): 0.0,
    ("focus", "pos"): 0.30, ("focus", "sad"): 0.15,
    ("pos", "sad"): 0.05,
}
# 兜底标签 balanced：与任何情绪都不冲突，但也不提供信息
NEUTRAL_MOOD_AFF = 0.25
# 未知情绪的兜底邻接度（宁可中性，也不要误伤）
UNKNOWN_MOOD_AFF = 0.20


def cluster_affinity(cluster_a, cluster_b):
    """两个情绪词族之间的邻接度"""
    if not cluster_a or not cluster_b:
        return 0.0
    if cluster_a == cluster_b:
        return 1.0
    v = _CLUSTER_AFF.get((cluster_a, cluster_b))
    if v is None:
        v = _CLUSTER_AFF.get((cluster_b, cluster_a), 0.0)
    return v


def normalize_mood(mood: str, vocab: Optional[Sequence[str]] = None) -> str:
    """把任意情绪词归一化到曲库词表；无法命中时返回空串（=不做情绪约束）"""
    m = (mood or "").strip().lower().replace(" ", "_")
    if not m:
        return ""
    if vocab and m in vocab:
        return m
    alias = MOOD_ALIASES.get(m)
    if alias is not None:
        m = alias
    if not m:
        return ""
    if vocab is None or m in vocab:
        return m
    # 前缀/包含兜底：calm_vibe → calm / relaxed_energy → relaxed
    for part in re.split(r"[_\-\s/]+", m):
        if part in vocab:
            return part
        hit = MOOD_ALIASES.get(part)
        if hit and hit in vocab:
            return hit
    for v in vocab:
        if len(v) >= 4 and (v in m or m in v):
            return v
    return ""


def mood_affinity(mood: str, song_moods: Sequence[str],
                  vocab: Optional[Sequence[str]] = None) -> float:
    """请求情绪与歌曲情绪的邻接度 0~1（歌曲可能带多个情绪标签，取最大）"""
    target = normalize_mood(mood, vocab)
    if not target or not song_moods:
        return UNKNOWN_MOOD_AFF
    best = 0.0
    for raw in song_moods:
        m = normalize_mood(raw, vocab)
        if not m:
            continue
        if m == target:
            return 1.0
        if m == "balanced":
            best = max(best, NEUTRAL_MOOD_AFF)
            continue
        ct, cs = MOOD_CLUSTER.get(target, ""), MOOD_CLUSTER.get(m, "")
        if ct and cs:
            best = max(best, _CLUSTER_AFF.get((ct, cs),
                                              _CLUSTER_AFF.get((cs, ct), 0.1)))
    return best if best > 0 else UNKNOWN_MOOD_AFF


# --------------------------------------------------------------------------
# 2. 任务语义邻接
# --------------------------------------------------------------------------

# 任务词族：(集合, 族内邻接度)
TASK_GROUPS = (
    ({"coding", "focus", "study", "reading", "creative"}, 0.50),
    ({"relax", "sleep", "meditation", "reading", "travel"}, 0.45),
    ({"workout", "gaming", "entertainment", "celebration", "social"}, 0.50),
    ({"commute", "travel", "entertainment"}, 0.50),
    ({"travel", "social"}, 0.25),
)

CATCH_ALL_TASKS = frozenset({"general"})


def task_affinity(task: str, song_tasks: Sequence[str]) -> float:
    """请求任务与歌曲任务标签的邻接度 0~1"""
    t = (task or "").strip().lower()
    if not t or not song_tasks:
        return UNKNOWN_MOOD_AFF
    best = 0.0
    for raw in song_tasks:
        s = (raw or "").strip().lower()
        if not s:
            continue
        if s == t:
            return 1.0
        if s in CATCH_ALL_TASKS or t in CATCH_ALL_TASKS:
            best = max(best, 0.25)
            continue
        for group, aff in TASK_GROUPS:
            if t in group and s in group and aff > best:
                best = aff
    return best if best > 0 else 0.12


# --------------------------------------------------------------------------
# 3. 风格邻接
# --------------------------------------------------------------------------

GENRE_FAMILIES = (
    ({"classical", "neo-classical", "minimalist", "ambient"}, 0.45),
    ({"electronic", "hip-hop", "r&b"}, 0.40),
    ({"rock", "indie", "pop"}, 0.35),
    ({"jazz", "r&b", "soul"}, 0.45),
    ({"folk", "indie", "ambient"}, 0.35),
)


def genre_affinity(song_genre: str, wanted: Sequence[str]) -> float:
    """歌曲风格与策略期望风格的邻接度 0~1（取最大）"""
    g = (song_genre or "").strip().lower()
    if not g or not wanted:
        return 0.0
    best = 0.0
    wanted_l = [str(w).strip().lower() for w in wanted if w]
    for w in wanted_l:
        if w == g:
            return 1.0
        for group, aff in GENRE_FAMILIES:
            if g in group and w in group:
                best = max(best, aff)
                break
    return best


# --------------------------------------------------------------------------
# 4. 节奏区间解析
# --------------------------------------------------------------------------

_TEMPO_RE = re.compile(r"(\d{2,3})\s*(?:-|~|–|—|到|至)\s*(\d{2,3})")
_TEMPO_SINGLE_RE = re.compile(r"(\d{2,3})")


def parse_tempo_range(text: str) -> Optional[Tuple[int, int]]:
    """解析 '140-170 BPM' / '120 BPM' / '50~80' 等写法 → (lo, hi)"""
    if not text:
        return None
    s = str(text)
    m = _TEMPO_RE.search(s)
    if m:
        lo, hi = int(m.group(1)), int(m.group(2))
        if lo > hi:
            lo, hi = hi, lo
        return (max(30, lo), min(220, hi))
    m = _TEMPO_SINGLE_RE.search(s)
    if m:
        v = int(m.group(1))
        if 30 <= v <= 220:
            return (v - 12, v + 12)
    return None


# --------------------------------------------------------------------------
# 4.5 标题质量：刷量号/白噪音/K歌/有声书等低质内容降权
# --------------------------------------------------------------------------

# 曲库里有 8%+ 的歌是"白噪音/助眠/合集/节目/伴奏"类刷量内容，
# 它们标签齐全、又常被计入高产艺人，会把大众度信号带偏，最终把
# "写代码专用白噪音""婴儿哄睡神曲"推给用户。这里统一降权。
# 一级：非音乐内容（白噪音/ASMR/有声节目/卡拉OK/合集），任何场景都是低质
_JUNK_STRONG_RE = re.compile(
    u"(白噪音|白噪声|白色声音|粉红噪音|粉色噪音|棕噪音|噪音|噪声|雨声|水声|流水声|海浪声|"
    u"雷声|雷电|打雷|下雨|下雨的声音|的风声|的声音|风声|虫鸣|鸟叫|小溪|河流|火堆|壁炉|"
    u"大自然的?声音|自然音|自然之声|环境音|氛围音|吹风机|风扇|"
    u"嘘声|嘘嘘|子宫|胎心|羊水|ASMR|asmr|纯享版|循环版|循环播放|单曲循环|"
    u"伴奏|伴唱|翻唱|卡拉ok|karaoke|made popular|in the style of|8-?bit|"
    u"dj版|鬼步|喊麦|串烧|车载|铃声|彩铃|试音|无损|hifi|整轨|"
    # 剪辑片段（"猜不透 (舒缓钢琴版片段|37秒舒缓钢琴版片段)"这类搬运号产物）：
    # 只匹配"版片段"与"N秒"两种形态，避免误伤《记忆的片段》这类正常歌名
    u"版片段|\\d+\\s*秒|"
    u"合集|精选集|歌单|排行榜|"
    u"音乐治疗|养生音乐|能量音乐|脑波|阿尔法波|双耳节拍|胎教|婴儿|宝宝|"
    u"节目|电台|广播剧|有声书|说书|讲书|朗读|诵读|第\\d+[集期章回]|"
    u"white ?noise|thunder ?storm|rainfall|rain ?(sounds?|and)|ocean sounds|"
    u"nature sounds|binaural|sleep sounds|asmr|"
    # 英文白噪音/疗愈音频的标题模板："<场景> Sounds"/"<场景> Relaxation Sounds"
    u"(sleep|relax|relaxation|relaxing|rain|nature|ocean|white|pink|brown|thunder|"
    u"water|wind|heal|meditat|spa|calm|therap|ambien|soothing)[a-z]*\\s+(?:[a-z]+\\s+){0,3}sounds?\\b)",
    re.IGNORECASE)

# 二级：场景相关（助眠/催眠类）——睡眠、放松场景下是正常内容，其他场景视为低质
_JUNK_CONTEXT_RE = re.compile(
    u"(助眠|催眠曲|哄睡|入睡|失眠|睡眠|安眠|摇篮曲|疗愈|减压|解压|"
    u"静心音乐|冥想音乐|瑜伽音乐|轻音乐|纯音乐|纯音|钢琴曲|背景音乐|bgm|"
    u"for (relaxing )?sleep(ing)?|relaxing sleep|deep sleep)",
    re.IGNORECASE)

# 睡眠/放松类任务：助眠类标题在这里是正常内容
_SLEEPY_TASKS = frozenset({"sleep", "relax", "meditation"})
# 二级中"较轻"的标记（纯音乐/轻音乐等只是偏合集化，轻微降权即可）
_MILD_MARKERS = (u"轻音乐", u"纯音乐", u"纯音", u"钢琴曲", u"背景音乐", u"bgm",
                 u"静心音乐", u"冥想音乐", u"瑜伽音乐")

# 低能量场景下明显"吵闹"的标题：曲库元数据偶有错标（摇滚单曲被标成 ambient/低能量），
# 标题是唯一可靠的反证信号，此时轻度降权
_LOUD_TITLE_RE = re.compile(
    u"(\\brock\\b|重金属|朋克|\\bmetal\\b|\\bpunk\\b|硬核|蹦迪|嗨曲|炸裂|"
    u"\\bremix\\b|鬼畜|喊麦)", re.IGNORECASE)

# 串烧/联唱：3 段以上以 + 拼接（正常歌名极少出现 3 个加号）
_MEDLEY_RE = re.compile(r"[+＋][^+＋]{1,30}[+＋][^+＋]{1,30}[+＋]")
# 超长合集标题里的"功能词"计数用词表
_FUNC_TITLE_HITS_RE = re.compile(
    r"纯音乐|轻音乐|名曲|音乐盒|放松|减压|解压|疗愈|治愈|助眠|睡眠|"
    r"冥想|瑜伽|专注|学习|阅读|安静|背景音乐|古典音乐|钢琴|古筝|二胡|笛子|"
    r"relax|sleep|study|music|piano", re.I)

JUNK_TITLE_PENALTY = 0.30
MILD_TITLE_PENALTY = 0.80
LOUD_TITLE_PENALTY = 0.70
# 低于该能量目标时，"摇滚/Remix"类标题视为与场景冲突
_QUIET_ENERGY_MAX = 3


def _contains_any(text, markers):
    low = (text or "").lower()
    return any(m.lower() in low for m in markers)


def is_junk_title(song, ctx=None):
    """是否是低质/刷量内容（白噪音、有声节目、K歌、合集等）"""
    title = getattr(song, "title", "") or ""
    if _JUNK_STRONG_RE.search(title):
        return True
    if _JUNK_CONTEXT_RE.search(title):
        if ctx is not None and getattr(ctx, "task_tag", "") in _SLEEPY_TASKS:
            return False
        # 纯音乐/轻音乐类只是偏合集化，不算"非音乐内容"
        return not _contains_any(title, _MILD_MARKERS)
    # 串烧/联唱：一首"歌"里拼了三四首歌名（《k歌之王+shall we talk+单车+…》），
    # 播放体验与推荐理由都对不上，任何场景都不该出现。
    if _MEDLEY_RE.search(title):
        return True
    # 超长功能型标题（合集号批量上传）：CJK 标题 ≥28 字且堆了 3 个以上功能词，
    # 例：超好聽的中國古典音樂 笛子名曲 古箏音樂 放鬆心情 安靜音樂 瑜伽音樂…
    if len(title) >= 28 and len(_FUNC_TITLE_HITS_RE.findall(title)) >= 3:
        return True
    return False


def title_penalty(song, ctx=None):
    """低质标题降权系数，正常歌曲为 1.0"""
    title = getattr(song, "title", "") or ""
    if _JUNK_STRONG_RE.search(title):
        return JUNK_TITLE_PENALTY
    if ctx is not None and int(getattr(ctx, "energy", 5) or 5) <= _QUIET_ENERGY_MAX \
            and _LOUD_TITLE_RE.search(title):
        return LOUD_TITLE_PENALTY
    if _JUNK_CONTEXT_RE.search(title):
        if ctx is not None and getattr(ctx, "task_tag", "") in _SLEEPY_TASKS:
            return MILD_TITLE_PENALTY
        if _contains_any(title, _MILD_MARKERS):
            return MILD_TITLE_PENALTY
        return JUNK_TITLE_PENALTY
    return 1.0


# --------------------------------------------------------------------------
# 4.6 状态词歌名：用户要的是"氛围"，不是"点歌"
# --------------------------------------------------------------------------

# 这些词是用户描述**想要的音乐氛围/场景**时最常用的修饰词（"晚上安静地看书"
# "来点舒缓的"），但它们同时也是热门歌名：曲库中标题含"安静"的歌有 400+ 首，
# 其中相当一部分是按关键词"安静"抓取入库、并被统一打上 reading/calm 标签的。
# 于是"看书 + 平静"这类请求会让这批"歌名即状态词"的曲子凭标签挤进推荐位，
# 表现得像"系统在按歌名匹配"。
#
# 设计原则：**状态词只映射到音乐元素（情绪/能量/节奏/风格/是否纯音），
# 绝不作为歌名或搜索关键词参与匹配**；歌名恰好蹭到状态词的曲子另作降权，
# 让排序重新回到音乐属性本身。
STATE_WORDS = frozenset({
    "安静", "宁静", "平静", "清静", "寂静", "安详", "安宁", "恬静",
    "舒缓", "放松", "轻松", "治愈", "温暖", "温柔", "温馨", "浪漫", "甜蜜",
    "开心", "快乐", "欢快", "兴奋", "激动", "伤感", "悲伤", "难过", "忧伤",
    "孤独", "寂寞", "思念", "怀旧", "励志", "热血", "激昂", "专注", "提神",
    "梦幻", "空灵", "冥想", "助眠", "催眠", "失眠", "清新", "动感", "元气",
})

# 歌名蹭状态词、且歌曲属性与之不契合 → 强力降权（只是名字像，音乐并不对）
TITLE_STATE_PENALTY = 0.30
# 歌名蹭状态词、但音乐属性确实契合（纯音 + 能量接近）→ 仅轻微降权
TITLE_STATE_PENALTY_MILD = 0.70
# 按状态词抓取入库的歌（keywords 全由状态词构成）→ 标签可信度低，轻度降权
STATE_KW_PENALTY = 0.45

_KW_SPLIT_RE = re.compile(r"[\s+/,、]+")


def is_state_only_keyword(kw):
    """曲库抓取关键词是否"整体就是状态词"（如"安静"；而"钢琴 安静"不算）"""
    if not kw:
        return False
    parts = [p for p in _KW_SPLIT_RE.split(str(kw).strip().lower()) if p]
    return bool(parts) and all(p in STATE_WORDS for p in parts)


def title_state_penalty(song, ctx=None):
    """歌名/入库关键词直接由状态词构成时的降权系数（正常歌曲为 1.0）

    用户说"安静地看书"时，"安静"描述的是想要的氛围，而不是在点《安静》
    这首歌。因此凡是歌名里带这个状态词的曲子，都不能因为"名字像"就占位；
    只有当它的音乐属性（纯音、能量档）本身确实贴合当前请求时，才允许
    以轻微降权的方式保留，由情绪/能量/节奏等元素决定它是否真的合适。

    另外，曲库里有一批歌是**用状态词当搜索词**抓进来的（search_keyword
    整串就是"安静"），它们被批量打上 reading/calm 之类的标签——标签来自
    关键词而非音乐本身，可信度低，因此即便用户本轮没提这个词，也只按
    轻度降权处理，让排序更多依赖能量/节奏等客观元素。
    """
    title = getattr(song, "title", "") or ""
    said = getattr(ctx, "state_words", None) if ctx is not None else None

    # 1) 用户本轮说到的状态词出现在歌名里 → 强力降权（或音乐确实契合时轻降）
    if said and any(w and w in title for w in said):
        try:
            near = abs(int(getattr(song, "energy", 5) or 5)
                       - int(getattr(ctx, "energy", 5) or 5)) <= 1
        except (TypeError, ValueError):
            near = False
        if bool(getattr(song, "instrumental", False)) and near:
            return TITLE_STATE_PENALTY_MILD
        return TITLE_STATE_PENALTY

    # 2) 用户没提，但这首歌本身就是按状态词抓取入库的 → 标签可信度低
    if is_state_only_keyword(getattr(song, "search_keyword", "")):
        return STATE_KW_PENALTY

    return 1.0


# --------------------------------------------------------------------------
# 4.7 演唱会版 / 串烧版：同名内容里的"次优版本"
# --------------------------------------------------------------------------
# 用户要的通常是录音室原曲。曲库里 (Live)/演唱会/巡演/音乐节版本非常多（主流
# 歌手的现场专辑、颁奖礼现场），串烧更是把三五首歌拼成一条标题。它们既不小众
# 也不低质，因此**不做过滤**（用户点名"想听演唱会/现场"时反而应优先），只在
# 用户没提现场时降权，让录音室版本排在前面。
LIVE_TITLE_PENALTY = 0.70     # 现场版：(Live)/演唱会/巡演/音乐节/颁奖礼…
MEDLEY_TITLE_PENALTY = 0.55   # 串烧/联唱：三首以上用 + 拼接的标题

# 现场版标记：优先识别括号内的 (Live)、以及中文"现场/演唱会"这类明确措辞。
# 不匹配裸词 Live（"Live Forever"这类正常歌名），避免误伤。
_LIVE_TITLE_RE = re.compile(
    r"[（(\[【]\s*live|live\s*(ver|version|版|edit)\b|"
    r"现场|演唱会|巡演|音乐会|音乐节|颁奖|歌友会|不插电|unplugged|\btour\b|concert",
    re.I)

# 串烧：三首以上用 + 拼接（两段式 "A+B" 不在此列，正常歌名也可能是二段），
# 或标题直接写明串烧/联唱/组曲/medley。
_MEDLEY_TITLE_RE = re.compile(
    r"[^+＋]{1,40}[+＋][^+＋]{1,40}[+＋]|串烧|联唱|medley|組曲|组曲", re.I)

# 用户**主动要**现场/演唱会时，上述降权一律不生效
_LIVE_INTENT_RE = re.compile(
    r"演唱会|现场|live|巡演|音乐会|音乐节|不插电|unplugged|签唱|歌友会", re.I)


def has_live_intent(text) -> bool:
    """用户这次是否点名要"现场/演唱会"版本"""
    return bool(text) and bool(_LIVE_INTENT_RE.search(str(text)))


def is_live_version(song) -> bool:
    """是否为现场/演唱会版本"""
    return bool(_LIVE_TITLE_RE.search(getattr(song, "title", "") or ""))


def is_medley(song) -> bool:
    """是否为串烧/联唱版本"""
    return bool(_MEDLEY_TITLE_RE.search(getattr(song, "title", "") or ""))


def title_live_penalty(song, ctx=None) -> float:
    """现场版/串烧版的降权系数（录音室原曲与用户点名现场时为 1.0）"""
    if ctx is not None and getattr(ctx, "live_intent", False):
        return 1.0
    title = getattr(song, "title", "") or ""
    if not title:
        return 1.0
    p = 1.0
    if _MEDLEY_TITLE_RE.search(title):
        p *= MEDLEY_TITLE_PENALTY
    if _LIVE_TITLE_RE.search(title):
        p *= LIVE_TITLE_PENALTY
    return p


# --------------------------------------------------------------------------
# 5. 请求上下文与打分模型
# --------------------------------------------------------------------------

class RequestContext(object):
    """一次推荐请求的全部意图信息"""

    __slots__ = ("task_tag", "mood", "energy", "tempo_range", "genres",
                 "instrumental_preferred", "language", "language_explicit",
                 "pref_genres", "pref_energy", "pref_instrumental",
                 "session_recent", "theme_ids", "theme_strength",
                 "state_words", "live_intent")

    def __init__(self, task_tag="", mood="", energy=5, tempo_range=None,
                 genres=None, instrumental_preferred=False,
                 language="no_preference", language_explicit=False,
                 pref_genres=None, pref_energy="both", pref_instrumental="both",
                 session_recent=(), theme_ids=None, theme_strength=0.0,
                 state_words=None, live_intent=False):
        self.task_tag = task_tag or ""
        self.mood = mood or ""
        self.energy = 5 if energy is None else int(energy)
        self.tempo_range = tempo_range
        self.genres = list(genres or [])
        self.instrumental_preferred = bool(instrumental_preferred)
        self.language = language or "no_preference"
        self.language_explicit = bool(language_explicit)
        self.pref_genres = {str(g).lower() for g in (pref_genres or [])}
        self.pref_energy = pref_energy or "both"
        self.pref_instrumental = pref_instrumental or "both"
        self.session_recent = set(session_recent)
        # 关键词意图命中（"世界杯""想听周杰伦"）：只加权重，不直接占推荐位
        self.theme_ids = frozenset(theme_ids or ())
        self.theme_strength = float(theme_strength or 0.0)
        # 用户这次说到的"氛围状态词"（安静/舒缓/治愈…）：仅用于给歌名降权
        self.state_words = frozenset(state_words or ())
        # 用户这次是否点名要现场/演唱会版本（是则不降权现场版与串烧）
        self.live_intent = bool(live_intent)


class RelevanceModel(object):
    """把歌曲的客观属性映射成"与当前请求的相关度"0~1

    权重设计原则：请求越具体（IDF 越高）权重越大；兜底标签权重≈0，
    从而让具体信号（情绪词族、能量百分位、风格）主导排序。
    大众度权重不低（W_POP + W_MAINSTREAM），因为用户明确要求
    "优先推大众歌、小众歌要足够好听且适配才推"——大众度是并列的一等信号，
    但仍不能压过任务/情绪匹配，否则会推荐"高热度但不对味"的歌。
    """

    # 基础权重（会被特异性调制后再归一化）
    W_TASK = 0.30
    W_MOOD = 0.26
    W_ENERGY = 0.16
    W_TEMPO = 0.08
    W_GENRE = 0.09
    W_INSTR = 0.16
    W_POP = 0.20
    W_LANG = 0.05
    # 关键词意图命中：具体意图（关键词覆盖的歌少）权重高，泛意图几乎为 0
    W_THEME = 0.24
    # 单曲级热度（来自"热门歌曲/hits"类关键词抓取）：权重较高，但被 hit_gate
    # 严格门控——只在已经适配（任务/情绪命中）的歌之间做优先级，因此可以放心
    # 给大权重，让"知名歌手的热门曲"稳定压过"同一歌手的冷门 B 面"。
    W_HIT = 0.12
    # 大众度分层加分：主流艺人（曲库中作品多的成熟歌手）额外加权，
    # 与 W_POP 叠加生效，使"大众优先"在排序中稳定体现。
    W_MAINSTREAM = 0.14
    # 能量/节奏百分位高斯核宽度
    SIGMA_ENERGY = 0.32
    SIGMA_TEMPO = 0.28

    # ---- 大众度分层阈值（基于 popularity_score 0~6）----
    # popularity_score = min(6, log1p(艺人在库歌曲数))
    #   ≳4.4 → 曲库收录 80+ 首作品（约前 1.5% 艺人），按主流歌手对待
    #   ≳3.0 → 收录 19+ 首，属于有稳定作品的成熟艺人（mid）
    #   <3.0 → 冷门艺人 / 单曲作者（obscure）
    # 注：阈值上调是因为曲库按关键词抓取，"在库歌曲数"会被批量上传放大——
    # 旧的 3.5（≈30 首）把 2400+ 位艺人（含大量小众民谣/氛围号）都算成主流。
    POP_MAINSTREAM = 4.4
    POP_MID = 3.0

    def __init__(self, db):
        self.db = db
        self.task_spec = getattr(db, "task_tag_spec", {}) or {}
        self.mood_spec = getattr(db, "mood_tag_spec", {}) or {}
        self.genre_spec = getattr(db, "genre_spec", {}) or {}
        self.energy_cdf = getattr(db, "energy_cdf", None) or {}
        self.tempo_cdf = getattr(db, "tempo_cdf", None) or []
        self.mood_vocab = getattr(db, "mood_vocab", None) or ()

    # ---- 各分项 ----

    def task_component(self, song, ctx):
        return task_affinity(ctx.task_tag, song.task_tags)

    def mood_component(self, song, ctx):
        return mood_affinity(ctx.mood, song.mood_tags, self.mood_vocab)

    def energy_percentile(self, energy):
        """把 1~10 的能量值映射到曲库经验分布百分位"""
        e = int(energy if energy is not None else 5)
        if isinstance(self.energy_cdf, dict) and self.energy_cdf:
            return float(self.energy_cdf.get(e, 0.5))
        return min(1.0, max(0.0, (e - 1) / 9.0))

    def tempo_percentile(self, bpm):
        cdf = self.tempo_cdf
        if not cdf:
            return min(1.0, max(0.0, (int(bpm or 90) - 40) / 120.0))
        idx = int(bpm or 90)
        if idx < 0:
            idx = 0
        if idx >= len(cdf):
            idx = len(cdf) - 1
        return float(cdf[idx])

    @staticmethod
    def _gauss(diff, sigma):
        if diff <= 0:
            return 1.0
        return math.exp(-(diff / sigma) ** 2)

    def energy_component(self, song, ctx, prep=None):
        """能量契合度 = 百分位通道(区分 4/5/6 档) + 绝对差通道(区分 6/8/10 档)

        纯百分位会把 energy=8/9/10 当成几乎相同（顶部被压缩到 0.99+），
        纯绝对差又区分不了 4~6（95% 的歌都在这一段），因此两者各占一半。
        """
        e_target_p = prep["e_target"] if prep else self.energy_percentile(ctx.energy)
        target_e = prep["e_raw"] if prep else int(ctx.energy or 5)
        song_e = int(getattr(song, "energy", 5) or 5)
        song_p = self.energy_percentile(song_e)
        pct_fit = self._gauss(abs(song_p - e_target_p), self.SIGMA_ENERGY)
        abs_fit = self._gauss(abs(song_e - target_e) / 3.5, 0.6)
        e_fit = 0.35 * pct_fit + 0.65 * abs_fit

        t_target = prep["t_target"] if prep else None
        t_mid = None
        if t_target is None:
            if not ctx.tempo_range:
                return e_fit
            t_mid = (ctx.tempo_range[0] + ctx.tempo_range[1]) / 2.0
            t_target = self.tempo_percentile(t_mid)
        t_song = self.tempo_percentile(getattr(song, "tempo_bpm", 90))
        t_pct = self._gauss(abs(t_song - t_target), self.SIGMA_TEMPO)
        if t_mid is None:
            t_mid = (ctx.tempo_range[0] + ctx.tempo_range[1]) / 2.0 if ctx.tempo_range else None
        if t_mid is None:
            return 0.6 * e_fit + 0.4 * t_pct
        t_abs = self._gauss(abs(int(getattr(song, "tempo_bpm", 90) or 90) - t_mid) / 60.0, 0.6)
        t_fit = 0.6 * t_pct + 0.4 * t_abs
        return 0.6 * e_fit + 0.4 * t_fit

    def genre_component(self, song, ctx):
        return genre_affinity(getattr(song, "genre", ""), ctx.genres)

    def instrument_component(self, song, ctx):
        instrumental = bool(getattr(song, "instrumental", False))
        if ctx.instrumental_preferred:
            return 1.0 if instrumental else 0.25
        return 0.60 if instrumental else 1.0

    def popularity_component(self, song):
        # pop = log1p(在库歌曲数)，封顶 6（≈400 首）。分母用 6 而不是 5：
        # 除以 5 会让 148 首以上的艺人全部打满，头部艺人之间再也拉不开差距。
        pop = self.db.popularity_score(song)
        return min(1.0, pop / 6.0)

    def hit_component(self, song):
        """单曲级热度：该曲是否来自"热门歌曲/hits"类关键词抓取（0/1）"""
        fn = getattr(self.db, "is_hit_song", None)
        return 1.0 if (fn and fn(song)) else 0.0

    def mainstream_component(self, song, prep=None):
        """大众度分层：主流艺人 1.0 / 中间 0.45 / 冷门 0.0

        用户诉求是"优先推大众歌，小众歌要好听且适配才推"。分层而非线性，
        是为了在一等权重上明确拉开"知名歌手"与"冷门作者"的差距；
        冷门作品仍可通过任务/情绪/能量等匹配信号进入推荐位（见 _select 的
        小众配额与高门槛规则），不会被一刀切掉。
        """
        pop = self.db.popularity_score(song)
        if pop >= self.POP_MAINSTREAM:
            return 1.0
        if pop >= self.POP_MID:
            return 0.45
        return 0.0

    def relevance_gate(self, song, ctx, prep, task_aff: float,
                       mood_aff: float) -> float:
        """大众度加分的"适配闸门"系数 0~1。

        "优先大众"不能压过"适不适合"——一首知名度很高但与场景情绪完全
        不搭的歌（写作业时推《烈火快车》），不该因为大众度高就挤掉一首
        真正适配的歌。因此大众度加分按歌曲的场景/情绪/风格匹配度打折：
          · 任务或情绪命中  → 1.0（全额享受大众度加成）
          · 风格命中        → 0.6
          · 全不命中        → 0.15（仍留一点，保证不至于只推冷门）
        """
        if task_aff >= 0.25 or mood_aff >= 0.5:
            return 1.0
        if self.genre_component(song, ctx) >= 0.5:
            return 0.6
        return 0.15

    def hit_gate(self, song, ctx, prep, task_aff: float,
                 mood_aff: float) -> float:
        """热门曲目加分的闸门 0/1。

        与 relevance_gate 的区别：这里**没有 0.15 的兜底分**。大众度可以
        对"完全不搭"的歌保留一点点加分（避免只推冷门），但"单曲热度"不行——
        否则一首与场景无关的热门歌（写作业时推强节奏热单）会靠热度挤掉真正
        适配的歌，违背"适配度优先"。热度只用于在**已经适配**的候选之间排序。
        """
        return 1.0 if (task_aff >= 0.25 or mood_aff >= 0.5) else 0.0

    # ---- 请求级预处理（与歌曲无关的量只算一次）----

    def prepare(self, ctx, song_language_fn=None):
        spec_task = self.task_spec.get(ctx.task_tag, 0.35)
        mood_norm = normalize_mood(ctx.mood, self.mood_vocab)
        spec_mood = self.mood_spec.get(mood_norm, 0.35) if mood_norm else 0.0
        spec_genre = max([self.genre_spec.get(str(g).lower(), 0.3)
                          for g in ctx.genres] or [0.0])
        w = {
            "task": self.W_TASK * spec_task,
            "mood": self.W_MOOD * spec_mood,
            "energy": self.W_ENERGY,
            "genre": self.W_GENRE * spec_genre,
            "instr": self.W_INSTR,
            "pop": self.W_POP,
            # 大众度分层加分：与 pop 叠加，强化"主流优先"
            "mainstream": self.W_MAINSTREAM,
            # 任何被点名的语种（含日/韩/其它语言）都启用语言权重
            "lang": (self.W_LANG
                     if ctx.language and ctx.language != "no_preference" else 0.0),
            "theme": self.W_THEME * ctx.theme_strength if ctx.theme_ids else 0.0,
            # 单曲热度：和大众度一样要过"适配闸门"，不允许只凭热门挤掉更适配的歌
            "hit": self.W_HIT,
        }
        # 曲库里该任务是否真有对应情绪的歌？若没有（如 study 几乎没有 energetic），
        # 说明"任务标签"和"情绪目标"在曲库里不可兼得，此时让情绪主导排序，
        # 否则用户会拿到"标签对但情绪完全相反"的歌（刷题要提神却推来安神纯音）。
        if mood_norm and mood_norm != "balanced" and ctx.task_tag:
            task_total = len(getattr(self.db, "_task_index", {}).get(ctx.task_tag, ()))
            support = 0
            if task_total:
                cluster = MOOD_CLUSTER.get(mood_norm)
                mates = [m for m in self.mood_vocab
                         if m != "balanced" and MOOD_CLUSTER.get(m) == cluster]
                pairs = getattr(self.db, "_pair_index", {})
                for m in mates:
                    support += len(pairs.get((ctx.task_tag, m), ()))
                if support / float(task_total) < 0.02:
                    w["task"] *= 0.65
                    w["mood"] *= 1.25
        return {
            "w": w,
            "total": sum(w.values()) or 1.0,
            "task": ctx.task_tag,
            "mood_norm": mood_norm,
            "e_target": self.energy_percentile(ctx.energy),
            "e_raw": int(ctx.energy or 5),
            "t_target": (self.tempo_percentile(
                (ctx.tempo_range[0] + ctx.tempo_range[1]) / 2.0)
                if ctx.tempo_range else None),
            "lang_fn": song_language_fn,
            "language": ctx.language,
        }

    # ---- 组合 ----

    def score(self, song, ctx, prepared=None, song_language_fn=None):
        """返回 0~1 的相关度（越大越相关）"""
        prep = prepared if prepared is not None else self.prepare(ctx, song_language_fn)
        w = prep["w"]
        penalty = title_penalty(song, ctx) if prep.get("quality", True) else 1.0
        # 歌名蹭状态词（用户说的是氛围而非点歌）→ 额外降权，防止"按歌名匹配"
        penalty *= title_state_penalty(song, ctx)
        # 现场版/串烧版：用户没点名要现场时降权，让录音室原曲排前面
        penalty *= title_live_penalty(song, ctx)
        task_aff = self.task_component(song, ctx)
        # 情绪与场景耦合：情绪命中只有在"歌本身属于这个场景"时才算满分
        # （否则"开车犯困"会被派对电音拿下——情绪对，但场景完全不对）
        mood_aff = self.mood_component(song, ctx) * (0.45 + 0.55 * task_aff)
        s = (w["task"] * task_aff +
             w["mood"] * mood_aff +
             w["energy"] * self.energy_component(song, ctx, prep) +
             w["genre"] * self.genre_component(song, ctx) +
             w["instr"] * self.instrument_component(song, ctx) +
             w["pop"] * self.popularity_component(song) +
             w["mainstream"] * self.mainstream_component(song)
             * self.relevance_gate(song, ctx, prep, task_aff, mood_aff) +
             w.get("hit", 0.0) * self.hit_component(song)
             * self.hit_gate(song, ctx, prep, task_aff, mood_aff))
        if w["lang"] and prep.get("lang_fn") is not None:
            if prep["lang_fn"](song) == prep["language"]:
                s += w["lang"]
        if w.get("theme") and song.id in ctx.theme_ids:
            s += w["theme"]
        s = s / prep["total"]
        if penalty != 1.0:
            s *= penalty          # 白噪音/合集/节目等低质内容整体降权
        return s

    def explain(self, song, ctx):
        """给出该歌命中的关键信号（用于推荐理由）"""
        tags = []
        if ctx.task_tag and task_affinity(ctx.task_tag, song.task_tags) >= 0.25:
            hit = [t for t in (song.task_tags or []) if t]
            if hit:
                tags.append("场景:" + hit[0])
        aff = mood_affinity(ctx.mood, song.mood_tags, self.mood_vocab)
        if aff >= 0.5:
            hit = [m for m in (song.mood_tags or []) if m and m != "balanced"]
            if hit:
                tags.append("情绪:" + hit[0])
        return tags
