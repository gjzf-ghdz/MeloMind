"""推荐引擎 - 意图簇候选池 + 相关性打分 + 多样性选择

匹配质量的三处根因修复（对应 53.7 万首曲库实测诊断）：
1) 曲库里 balanced 情绪占 96%、general/relax 任务占 83%，
   旧实现按"命中即 +4 分"等权处理，等于随机排序；现在改用标签特异性
   (IDF) 加权 + (task, mood) 意图簇，兜底标签不再影响排序。
2) 策略模板给出的 energized/happy/warm 在曲库词表中不存在，
   旧实现情绪层完全失效；现在先归一化到词表，再做情绪词族邻接。
3) 旧实现里大众度加权 (int(pop*2)，最高 +12 并放大 1.5 倍) 压过
   任务(4)+情绪(4)，导致"推荐明星"而非"推荐匹配"；现在大众度只占
   7% 权重做平局打破，并加入歌手/风格多样性约束。
"""
import random
import re
import urllib.parse
from collections import deque
from typing import List, Dict, Optional, Tuple

from models import (Song, MusicStrategy, infer_instrument_type, song_language,
                    song_language_fine, language_matches, LANG_GROUPS,
                    language_matches_pref)
from local_music_db import LocalMusicDatabase
from special_noun_detector import SpecialNounDetector
from music_relevance import (RelevanceModel, RequestContext, TASK_GROUPS,
                             MOOD_CLUSTER, normalize_mood, parse_tempo_range,
                             is_junk_title, cluster_affinity, STATE_WORDS,
                             has_live_intent)

QQMUSIC_SEARCH_URL = "https://y.qq.com/n/ryqq/search?w={}"

# task_type → task_tag 映射（16 种任务标签）
TASK_TAG_BY_TASK_TYPE = {
    "coding": "coding", "study": "study", "workout": "workout",
    "commute": "commute", "relax": "relax", "creative": "creative",
    "entertainment": "entertainment", "writing": "creative",
    "sleep": "sleep", "general": "general", "focus": "focus",
    "social": "social", "celebration": "celebration",
    "meditation": "meditation", "reading": "reading",
    "travel": "travel", "gaming": "gaming",
}

# 细粒度子类 → 16 标签（优先于父类映射）
SUBTYPE_TAG_MAP = {
    "entertainment-gaming": "gaming",
    "entertainment-party": "social",
    "entertainment-celebration": "celebration",
    "entertainment-social": "social",
    "workout-yoga": "meditation",
    "relax-meditate": "meditation",
    "study-reading": "reading",
    "coding-deep": "coding",
    "coding-debug": "coding",
    "coding-learn": "coding",
    "coding-review": "coding",
    "commute-driving": "commute",
    "commute-transit": "commute",
    "workout-running": "workout",
    "workout-basketball": "workout",
    "workout-football": "workout",
    "workout-strength": "workout",
    "creative-brainstorm": "creative",
    "creative-design": "creative",
    "study-exam": "study",
    "study-vocab": "study",
    "study-practice": "study",
    "relax-winddown": "relax",
}


def normalize_title_key(title: str) -> str:
    """歌名归一化，用于"同名歌曲只推一首"的去重判定。

    去掉括号后缀（Live/伴奏/版本标注）、空白与大小写差异，
    《我和你 (Live)》《我和你》归为同一首。
    """
    t = (title or "").strip().lower()
    t = re.sub(r"[（(\[【][^)）\]】]*[)）\]】]", "", t)
    t = re.sub(r"[\s\-_·・,，。.]+", "", t)
    return t


class MusicRecommender:
    def __init__(self):
        self.local_db = LocalMusicDatabase()
        self.noun_detector = SpecialNounDetector(self.local_db)
        self.model = RelevanceModel(self.local_db)
        self._session_recent = deque(maxlen=20)

    # ------------------------------------------------------------------
    # 工具
    # ------------------------------------------------------------------
    def _task_type_to_task_tag(self, task_type: str) -> str:
        """task_type → task_tag 映射（优先子类精确映射，再父类兜底）"""
        if task_type in SUBTYPE_TAG_MAP:
            return SUBTYPE_TAG_MAP[task_type]
        parent = task_type.split("-")[0] if "-" in task_type else task_type
        return TASK_TAG_BY_TASK_TYPE.get(parent, "general")

    def _merge_dedupe(self, pool: List[Song], new_songs: List[Song]) -> List[Song]:
        """合并两个歌曲列表并去重"""
        seen = {s.id for s in pool}
        for s in new_songs:
            if s.id not in seen:
                seen.add(s.id)
                pool.append(s)
        return pool

    @staticmethod
    def _song_language(song: Song) -> str:
        """语言板块：instrumental（无歌词）/ chinese / english / other

        统一走 models.song_language —— 纯音乐优先，没有歌词的歌不会
        被计入中文歌 / 英文歌 / 其它语言板块。
        """
        return song_language(song)

    @staticmethod
    def _song_language_fine(song: Song) -> str:
        """细分语种（japanese / korean / ...），用于精确命中"想听日语歌"这类请求"""
        return song_language_fine(song)

    # ------------------------------------------------------------------
    # 主流程
    # ------------------------------------------------------------------
    def recommend(self, strategy: MusicStrategy, limit: int = 8,
                  task_type: str = "", user_message: str = "",
                  language_preference: str = "no_preference",
                  language_explicit: bool = False,
                  user_preferences: dict = None) -> List[Dict]:
        """多信号相关性推荐。

        候选池 = 标题/特殊名词命中 ∪ (task,mood) 意图簇 ∪ 任务标签 ∪
                 情绪标签 ∪ 高/低能量定向采样 ∪ 风格采样 ∪ 全库随机
        排序   = 特异性加权的任务/情绪邻接 + 能量节奏百分位 + 风格 +
                 纯音乐偏好 + 大众度平局项 + 会话去重 + 轻微随机抖动
        选择   = 头部加权抽样 + 歌手/风格多样性约束
        """
        user_preferences = user_preferences or {}
        task_hint = task_type or self._infer_task_from_strategy(strategy)
        task_tag = self._task_type_to_task_tag(task_hint)
        special_kws = self.noun_detector.detect(user_message, task_type) or []

        # 状态词（安静/舒缓/治愈…）：用户描述的是"想要的音乐氛围"，
        # 只允许映射到情绪/能量/风格等音乐元素，绝不作为歌名或关键词检索；
        # 歌名恰好蹭到状态词的曲子（如 400+ 首标题含"安静"的歌）另作降权，
        # 避免"说安静地看书 → 推来一堆叫《安静》的歌"。
        state_words = {w for w in STATE_WORDS if w and w in (user_message or "")}

        energy = strategy.energy_level
        if energy is None:
            energy = 5
        ctx = RequestContext(
            task_tag=task_tag,
            mood=strategy.mood_target or "",
            energy=energy,
            tempo_range=parse_tempo_range(strategy.tempo_range),
            genres=strategy.genres or [],
            instrumental_preferred=bool(strategy.instrumental_preferred),
            language=language_preference,
            language_explicit=language_explicit,
            pref_genres=user_preferences.get("genres") or [],
            pref_energy=user_preferences.get("energy") or "both",
            pref_instrumental=user_preferences.get("instrumental") or "both",
            session_recent=self._session_recent,
            state_words=state_words,
            # 用户点名"演唱会/现场"时不降权现场版与串烧，否则让录音室原曲优先
            live_intent=has_live_intent(user_message),
        )
        print(f"[Recommender] task={task_type} task_tag={task_tag} "
              f"mood={ctx.mood}({normalize_mood(ctx.mood, self.model.mood_vocab) or '-'}) "
              f"energy={energy} tempo={ctx.tempo_range} genres={ctx.genres} "
              f"special_kws={special_kws} state_words={sorted(state_words)}")

        # ---- 命中解析 ----
        # 歌名命中 = 点播（锁定推荐位）；歌手名命中 = 点播歌手（锁定推荐位）；
        # 场景/主题词命中（"助眠""世界杯"）= 只做相关度加分，不占位。
        title_hits, kw_hits, soft_titles = [], [], []
        if user_message:
            raw_titles = self.local_db.search_by_title_in_text(
                user_message, limit=limit * 5)
            title_hits, soft_titles = self._filter_title_hits(raw_titles, user_message)
        # 低质内容（白噪音/有声节目/K歌/工厂翻奏等）即使在标题/关键词里命中
        # 也不占优先位
        def _prio_ok(s):
            return (not is_junk_title(s, ctx)) and \
                self.local_db.popularity_score(s) > 0 and \
                not self._is_factory_cover(s)

        junk_titles = [s for s in title_hits if not _prio_ok(s)]
        if junk_titles:
            title_hits = [s for s in title_hits if _prio_ok(s)]
            soft_titles = soft_titles + junk_titles
            print(f"[Recommender] 低质标题降级 {len(junk_titles)} 首")

        artist_hits, theme_hits, theme_prio = [], [], []
        if special_kws:
            kw_hits = self.local_db.search_by_keywords(special_kws, limit=limit * 8)
            artist_names = {k for k in special_kws if self.local_db.is_artist_name(k)}
            if artist_names:
                artist_hits = [s for s in kw_hits
                               if (s.artist or "").strip() in artist_names]
                artist_ids = {s.id for s in artist_hits}
                theme_hits = [s for s in kw_hits if s.id not in artist_ids]
                # 同一位歌手名下往往几十首：先按当前场景/情绪相关度排一遍，
                # 否则"想听周杰伦"会推给他随意最早入库的 8 首
                prep0 = self.model.prepare(ctx)
                artist_hits.sort(key=lambda s: -self.model.score(s, ctx, prep0))
            else:
                theme_hits = kw_hits
            ctx.theme_ids = {s.id for s in (theme_hits + artist_hits) if _prio_ok(s)}
            ctx.theme_strength = self._theme_strength(special_kws)
            # 命中歌按"名词相关度 → 音乐元素契合度"两段式排序后进入优先位：
            # 用户点名了具体专场（世界杯/甄嬛传/王者荣耀），先把与它直接
            # 相关的歌排满推荐位，情绪/能量只作为第二因素在命中集合内定序。
            theme_prio = [s for s in theme_hits if _prio_ok(s)]
            if theme_prio and ctx.theme_strength > 0:
                prep_t = self.model.prepare(ctx)
                theme_prio.sort(key=lambda s: (
                    -self._noun_relevance(s, special_kws),
                    -self.model.score(s, ctx, prep_t)))
            print(f"[Recommender] 关键词命中 歌手={len(artist_hits)} "
                  f"主题={len(theme_hits)} 优先主题={len(theme_prio)} "
                  f"特异性={ctx.theme_strength:.2f}")
        junk_hits = [s for s in theme_hits if not _prio_ok(s)]
        if junk_hits:
            soft_titles = soft_titles + junk_hits
        if title_hits or artist_hits:
            print(f"[Recommender] 优先命中 标题={len(title_hits)} 歌手={len(artist_hits)}")
        priority_ids = {s.id for s in title_hits} | {s.id for s in artist_hits}
        # 点名歌手时优先位占比更高；主题命中歌同样进优先位（用户点名了专场）
        cap = 1.0 if (artist_hits or theme_prio) else 0.8
        priority = self._rank_priority(title_hits, artist_hits, priority_extra=theme_prio,
                                       limit=limit, cap_ratio=cap)

        # ---- 候选池 ----
        pool = self._build_pool(ctx, priority, limit,
                                extra=list(soft_titles) + theme_hits + artist_hits)

        # ---- 硬条件过滤（语言 / 用户问卷偏好），失败时自动放宽 ----
        pool = self._filter_language(pool, ctx, limit)
        pool = self._filter_user_prefs(pool, ctx, limit, title_ids=priority_ids)

        # ---- 相关性排序 + 多样性选择 ----
        chosen = self._select(pool, ctx, limit, priority, priority_ids)
        if len(chosen) < limit:
            chosen = self._fallback_broaden(chosen, ctx, limit)

        for s in chosen:
            self._session_recent.append(s.id)

        self._enrich_reasons(chosen, strategy, task_hint, special_kws)
        return [s.to_dict() for s in chosen[:limit]]

    # ------------------------------------------------------------------
    # 候选池构建
    # ------------------------------------------------------------------
    def _theme_strength(self, special_kws) -> float:
        """特殊名词的整体优先级强度 0~1。

        只在命中的是**具体专有名词**（甄嬛传/世界杯/王者荣耀）时才高；
        若命中全是泛化类别词（电视剧/游戏/电影），强度归零——这类词
        不该抢推荐位，走常规 task_tag / 情绪匹配即可。
        """
        from special_noun_detector import _is_generic_keyword
        specific = [k for k in (special_kws or []) if not _is_generic_keyword(k)]
        if not specific:
            return 0.0
        return max(self.local_db.keyword_specificity(k) for k in specific)

    def _noun_relevance(self, song, special_kws) -> float:
        """歌与用户点名名词的直接相关度（第一排序因素）。

        分层：标题/专辑/歌手直接含该词(1.0) > search_keyword 命中(0.7)，
        再按命中词的"具体性"加权——具体名(甄嬛传)压过泛化桶(电视剧)，
        长词(世界杯主题曲)压过短词(世界杯)。

        曲库关键词常为"王者荣耀 OST"这类带后缀形态，而歌名里只会出现
        词根"王者荣耀"，因此同时用**词根**参与标题/专辑匹配。
        """
        from special_noun_detector import _is_generic_keyword, _strip_music_tail
        title = (song.title or "")
        album = (song.album or "")
        artist = (song.artist or "")
        kw = (song.search_keyword or "")
        best = 0.0
        for k in (special_kws or []):
            if not k:
                continue
            # 泛化类别词只给很低的分，不允许它盖过具体名
            spec = 0.30 if _is_generic_keyword(k) else 1.0
            spec *= min(1.0, len(k) / 6.0 + 0.5)   # 长词更具体
            # 关键词本体 + 词根（"王者荣耀 OST"/"和平精英 BGM" → 裸名）
            forms = {k}
            stem = _strip_music_tail(k)
            if stem:
                forms.add(stem)
            for f in forms:
                if f in title or f in album:
                    best = max(best, 1.0 * spec)
                elif f in artist:
                    best = max(best, 0.95 * spec)
                elif f in kw:
                    best = max(best, 0.70 * spec)
        return best

    def _rank_priority(self, title_hits: List[Song], kw_hits: List[Song],
                       limit: int, cap_ratio: float = 0.8,
                       priority_extra: List[Song] = None) -> List[Song]:
        """标题命中优先于名词命中；同名歌曲按大众度排序（原唱/知名版本在前）

        priority_extra：已按"名词相关度→音乐元素"排好序的主题命中歌，
        直接追加在歌手命中之后（保持传入顺序，不再打乱）。
        """
        priority, seen, seen_key, artist_used = [], set(), set(), set()
        # 标题命中：同一首歌（同名同歌手）只留一首，同一歌手的同名版本也只留一首；
        # 名词命中（如"想听周杰伦"）需要同一歌手的多首歌，因此不做歌手去重
        for group, dedupe_artist in ((title_hits, True), (kw_hits, False)):
            group = sorted(group,
                           key=lambda s: self.local_db.popularity_score(s),
                           reverse=True)
            for s in group:
                if s.id in seen:
                    continue
                key = ((s.title or "").strip().lower(),
                       (s.artist or "").strip().lower())
                if key in seen_key:
                    continue
                if dedupe_artist and key[1] and key[1] in artist_used:
                    continue
                seen.add(s.id)
                seen_key.add(key)
                if dedupe_artist and key[1]:
                    artist_used.add(key[1])
                priority.append(s)
        # 主题命中歌：保持调用方排好的顺序追加（相关度优先，其次音乐元素）
        for s in (priority_extra or []):
            if s.id in seen:
                continue
            key = ((s.title or "").strip().lower(),
                   (s.artist or "").strip().lower())
            if key in seen_key:
                continue
            seen.add(s.id)
            seen_key.add(key)
            priority.append(s)
        return priority[:max(1, int(limit * cap_ratio))]

    def _filter_title_hits(self, hits: List[Song],
                           user_message: str):
        """标题命中精度过滤 → (确认点歌, 疑似短语误伤)

        "自驾旅行在路上" 会命中《在路上》、"早高峰挤地铁" 会命中《地铁》——
        歌名恰好是日常短语时，子串命中并不代表用户在点歌，若当作优先命中
        会直接挤占推荐位。判定为"确认点歌"的条件（满足其一）：
          · 歌名 ≥ 4 字（足够长，日常语句中不易整词出现）
          · 歌名占用户语句 ≥ 30%（消息本身就是在点这首歌）
          · 歌名占 ≥ 25% 且出自高热艺人（如"来首晴天"→周杰伦）
        未通过者降级为普通候选（仍可能凭相关性被选中，但不占优先位）。
        """
        msg = re.sub(r"[s　-〿＀-￯,.!?~:;()]", "", user_message or "")
        msg_len = max(1, len(msg))
        confirmed, soft = [], []
        for s in hits:
            title = (s.title or "").strip()
            if not title:
                continue
            ratio = len(title) / float(msg_len)
            if len(title) >= 4 or ratio >= 0.30:
                confirmed.append(s)
            elif ratio >= 0.25 and self.local_db.popularity_score(s) >= 5.0:
                confirmed.append(s)
            else:
                soft.append(s)
        return confirmed, soft

    def _candidate_pairs(self, ctx: RequestContext) -> List[Tuple[float, str, str]]:
        """构造 (邻接度, task, mood) 意图簇候选。

        曲库里的 task_tag/mood_tag 其实是抓取时的"意图组合"标签，
        (workout, energetic) 这样的组合命中比两个标签各自命中精确得多。
        """
        task = ctx.task_tag
        if not task:
            return []
        mood = normalize_mood(ctx.mood, self.model.mood_vocab)

        task_cands = [(task, 1.0)]
        for group, aff in TASK_GROUPS:
            if task in group:
                for g in group:
                    if g != task:
                        task_cands.append((g, aff))
        mood_cands = []
        if mood and mood != "balanced":
            mood_cands.append((mood, 1.0))
            cluster = MOOD_CLUSTER.get(mood)
            if cluster:
                for m in self.model.mood_vocab:
                    if m != mood and MOOD_CLUSTER.get(m) == cluster:
                        mood_cands.append((m, 0.55))
            mood_cands.append(("balanced", 0.3))
        elif mood == "balanced":
            mood_cands.append(("balanced", 1.0))

        pairs, seen = [], set()
        for t, tw in task_cands:
            for m, mw in mood_cands:
                aff = tw * mw
                if aff < 0.25:
                    continue
                df = len(self.local_db._pair_index.get((t, m), ()))
                if df < 20:
                    continue
                if (t, m) in seen:
                    continue
                seen.add((t, m))
                pairs.append((aff, t, m))
        pairs.sort(key=lambda x: -(x[0] * (len(self.local_db._pair_index.get((x[1], x[2]), ())) ** 0.35)))
        return pairs[:8]

    def _build_pool(self, ctx: RequestContext, priority: List[Song],
                    limit: int, extra: Optional[List[Song]] = None) -> List[Song]:
        db = self.local_db
        pool: List[Song] = []
        seen = set()

        def _add(songs):
            for s in songs:
                if s.id not in seen:
                    seen.add(s.id)
                    pool.append(s)

        _add(priority)
        _add(extra or ())   # 疑似短语误伤的标题命中：只作为普通候选

        # 1) (task, mood) 意图簇采样（核心信号）
        pairs = self._candidate_pairs(ctx)
        for aff, t, m in pairs:
            n = int(220 + 620 * aff)
            _add(db.sample_by_pair(t, m, limit=n))
        print(f"[Recommender] 意图簇 {len(pairs)} 个 → 池 {len(pool)} 首")

        # 2) 任务标签采样（细粒度任务如 commute/reading 只有几百首，直接进池）
        if ctx.task_tag:
            _add(db.search_by_task_tag(ctx.task_tag, limit=max(400, limit * 60)))

        # 3) 情绪标签采样（兜底情绪 balanced 无区分度，跳过）
        mood_norm = normalize_mood(ctx.mood, self.model.mood_vocab)
        if mood_norm and mood_norm != "balanced" \
                and self.model.mood_spec.get(mood_norm, 0.0) >= 0.25:
            _add(db.search_by_mood_tag(mood_norm, limit=max(300, limit * 40)))
            # 邻近词族（如"提神"→inspired/focused、"欢快"→festive/hopeful）：
            # 曲库里请求情绪与场景标签常常不共存，补上邻居才不会漏掉候选
            for mate in self._neighbour_moods(mood_norm):
                _add(db.search_by_mood_tag(mate, limit=max(150, limit * 20)))

        # 4) 能量定向采样：能量 95% 集中在 4~6，目标极端时必须定向取
        if ctx.energy >= 7 or ctx.energy <= 3:
            band = [ctx.energy - 1, ctx.energy, ctx.energy + 1]
            _add(db.sample_by_energy_band(band, limit=1500))

        # 5) 风格采样（pop 是兜底风格，占比 81%，跳过）
        for g in ctx.genres[:2]:
            if self.model.genre_spec.get(str(g).lower(), 0.0) >= 0.25:
                _add(db.sample_by_genre(g, limit=700))

        # 6) 全库随机（发现性 + 兜底）
        _add(db.sample_random(limit=max(400, limit * 50)))

        print(f"[Recommender] 候选池 {len(pool)} 首")
        return pool

    # ------------------------------------------------------------------
    # 硬条件过滤
    # ------------------------------------------------------------------
    def _neighbour_moods(self, mood: str) -> List[str]:
        """返回相邻情绪词族的代表情绪（按词族邻接度，每族取最常用的一个）

        用于扩大候选池：请求"energetic"时补采样 inspired/focused 等，
        否则曲库里 (场景, 情绪) 组合缺失时会把整类歌漏在池外。
        """
        cluster = MOOD_CLUSTER.get(mood)
        if not cluster:
            return []
        scored = []
        for other in set(MOOD_CLUSTER.values()):
            if other == cluster:
                continue
            aff = cluster_affinity(cluster, other)
            if aff >= 0.3:
                scored.append((aff, other))
        scored.sort(reverse=True)
        out = []
        for aff, other in scored:
            mates = [m for m in self.model.mood_vocab if MOOD_CLUSTER.get(m) == other]
            mates.sort(key=lambda m: len(self.local_db._mood_index.get(m, ())),
                       reverse=True)
            out.extend(mates[:1])
        return out

    def _filter_language(self, pool: List[Song], ctx: RequestContext,
                         limit: int) -> List[Song]:
        """语言偏好过滤（纯音乐不受限；显式声明时只推该语言人声歌）"""
        if ctx.language not in LANG_GROUPS:
            return pool

        if ctx.language_explicit:
            def _ok(s):
                return language_matches(ctx.language, self._song_language_fine(s))
        else:
            # 非点名场景（问卷默认偏好）走偏好口径："英文/日韩等外文"要覆盖日韩，
            # 否则选了"外文"的用户拿不到日韩歌
            def _ok(s):
                return (language_matches_pref(ctx.language,
                                              self._song_language_fine(s))
                        or self._song_language(s) == "instrumental")

        kept = [s for s in pool if _ok(s)]
        if len(kept) < limit and ctx.task_tag:
            # 补抽：从任务/情绪索引扩大样本，避免降级成另一种语言
            existing = {s.id for s in kept}
            extra = self.local_db.search_by_task_tag(ctx.task_tag, limit=3000)
            mood_norm = normalize_mood(ctx.mood, self.model.mood_vocab)
            if mood_norm and mood_norm != "balanced":
                extra += self.local_db.search_by_mood_tag(mood_norm, limit=1000)
            for s in extra:
                if s.id not in existing and _ok(s):
                    kept.append(s)
                    existing.add(s.id)
        if len(kept) >= limit:
            print(f"[Recommender] 语言过滤({ctx.language}): {len(kept)} 首")
            return kept
        if kept:
            # 过滤后池子偏小也不再整池放开：交给 _fallback_broaden 在语言约束内
            # 扩充，否则"来点中文歌"会被英文歌混进来
            print(f"[Recommender] 语言过滤({ctx.language}): {len(kept)} 首（不足 {limit}，转兜底补足）")
            return kept
        print(f"[Recommender] 语言过滤({ctx.language}) 无匹配，改为全池评分加权")
        return pool

    def _filter_user_prefs(self, pool: List[Song], ctx: RequestContext,
                           limit: int, title_ids=None) -> List[Song]:
        """请求硬约束过滤：点名语言 + 纯音乐 yes/no（点名的歌始终保留）

        语言必须**硬过滤**而非只加 0.05 权重——用户说"想听中文歌"时，
        英文/韩文歌即使任务情绪匹配也不该出现（此前只做加分，导致
        结果被英文流行歌占满）。泛化偏好（问卷）与明确点名分别用
        PREF_LANG_GROUPS / LANG_GROUPS 两套映射，日韩倾向不误伤。
        """
        title_ids = title_ids or set()
        if ctx.language and ctx.language in LANG_GROUPS:
            match = (language_matches if ctx.language_explicit
                     else language_matches_pref)
            kept = [s for s in pool
                    if match(ctx.language, self._song_language_fine(s))
                    or (not ctx.language_explicit
                        and self._song_language(s) == "instrumental")
                    or s.id in title_ids]
            if len(kept) >= max(1, limit // 2):
                print(f"[Recommender] 语言硬过滤({ctx.language}): {len(kept)}/{len(pool)} 首")
                pool = kept
            else:
                print(f"[Recommender] 语言过滤后候选过少({len(kept)})，保留全池")
        if ctx.pref_instrumental in ("yes", "no"):
            want = ctx.pref_instrumental == "yes"
            kept = [s for s in pool
                    if bool(s.instrumental) == want or s.id in title_ids]
            if len(kept) >= limit:
                print(f"[Recommender] 用户纯音乐偏好({ctx.pref_instrumental}): {len(kept)} 首")
                return kept
            if kept:
                # 问卷选了"偏好纯音乐/偏好人声"就应当贯彻：池子小也不整池放开，
                # 交给兜底补足按同一偏好扩充
                print(f"[Recommender] 用户纯音乐偏好({ctx.pref_instrumental}): {len(kept)} 首（不足 {limit}，转兜底补足）")
                return kept
        return pool

    # ------------------------------------------------------------------
    # 排序与选择
    # ------------------------------------------------------------------
    def _score_song(self, song: Song, ctx: RequestContext, prep) -> float:
        sc = self.model.score(song, ctx, prep)
        if ctx.pref_genres and (song.genre or "").lower() in ctx.pref_genres:
            sc += 0.05
        if ctx.pref_energy == "low" and song.energy <= 4:
            sc += 0.04
        elif ctx.pref_energy == "high" and song.energy >= 6:
            sc += 0.04
        return sc

    def _select(self, pool: List[Song], ctx: RequestContext, limit: int,
                priority: List[Song], priority_ids) -> List[Song]:
        """头部加权抽样 + 歌手/风格多样性"""
        # 优先位（标题/歌手/主题命中）内部也去重：同名版本与同歌重复命中
        # 不应挤占推荐位
        chosen, _seen_t = [], set()
        for s in priority:
            tk = normalize_title_key(s.title)
            if tk and tk in _seen_t:
                continue
            _seen_t.add(tk)
            chosen.append(s)
        slots = limit - len(chosen)
        if slots <= 0:
            return chosen[:limit]

        candidates = [s for s in pool if s.id not in set(
            x.id for x in chosen)]
        if not candidates:
            return chosen
        # 白噪音/合集/有声节目等低质内容：只有在正常候选不足时才启用。
        # 账号型艺人（音频工厂）也在此排除——它们往往上传量巨大、大众度虚高，
        # 不排除会整屏都是"（纯音版）"批量内容。
        healthy = [s for s in candidates
                   if not is_junk_title(s, ctx)
                   and not self._is_task_phrase_title(s)
                   and not self._is_article_title(s)
                   and not self._is_account_artist(s)
                   and not self._is_factory_cover(s)]
        if len(healthy) >= slots:
            candidates = healthy

        prep = self.model.prepare(ctx)
        recent = ctx.session_recent
        scored = []
        for s in candidates:
            sc = self._score_song(s, ctx, prep)
            if s.id in recent:
                sc *= 0.2                      # 刚推过：显著降权
            sc *= random.uniform(0.93, 1.07)   # 轻微抖动：同一请求多次也有变化
            scored.append((sc, s))
        scored.sort(key=lambda x: -x[0])

        head = scored[:max(limit * 6, limit)]
        head_min = min(sc for sc, _ in head)
        weighted = [((sc - head_min) + 0.05, s) for sc, s in head]

        # 加权随机抽样（score 的 3 次方，相关性主导、保留多样性）
        picks = []
        pool_w = weighted[:]
        target = min(len(pool_w), max(slots * 3, slots))
        while pool_w and len(picks) < target:
            total = sum(w ** 3 for w, _ in pool_w)
            r = random.uniform(0, total)
            cum = 0.0
            for i, (w, s) in enumerate(pool_w):
                cum += w ** 3
                if r <= cum:
                    picks.append(s)
                    pool_w.pop(i)
                    break

        # 多样性约束：同一歌手最多 1 首（必要时放宽到 2），单一风格不超过半数，
        # 同名歌曲最多 1 首（《我和你》有几十个翻唱/同名版本，不能占满列表）
        artist_used, genre_used, title_used = {}, {}, set()
        genre_cap = max(3, limit // 2)
        result = []
        for relax in (1, 2, 99):
            allow_dup_title = (relax == 99)
            for s in list(picks):
                if len(result) >= slots:
                    break
                if s in result:
                    continue
                artist = s.artist or s.title
                genre = (s.genre or "").lower()
                tkey = normalize_title_key(s.title) if not allow_dup_title else None
                if artist_used.get(artist, 0) >= relax:
                    continue
                if tkey and tkey in title_used:
                    continue
                if relax == 1 and genre_used.get(genre, 0) >= genre_cap:
                    continue
                result.append(s)
                artist_used[artist] = artist_used.get(artist, 0) + 1
                genre_used[genre] = genre_used.get(genre, 0) + 1
                if tkey:
                    title_used.add(tkey)
            if len(result) >= slots:
                break

        # ---- 大众度配额与小众高门槛（用户诉求：优先大众，小众要好听且适配）----
        result = self._enforce_mainstream(result, candidates, ctx, prep, slots)
        chosen.extend(result)
        return chosen

    # 非优先位中，主流/成熟艺人作品的目标占比（其余名额留给优质小众）
    # 0.7 → 0.85：用户反馈"还要再大众一点"。适配度仍是第一排序信号，
    # 大众度只决定"同样适配时优先推谁"和小众歌的准入门槛。
    MAINSTREAM_RATIO = 0.85

    # 纯"任务/状态短语"歌名：整首歌名就是一句功能性描述（《集中注意力》
    # 《专注学习》《放松音乐》），几乎都是音频工厂批量上传的梗歌，
    # 不是真正的音乐作品。小众层出现这类标题一律不收。
    _TASK_PHRASE_TITLE_RE = re.compile(
        r"^(集中注意力|专注学习|专注工作|高效学习|认真学习|学习音乐|学习专用|"
        r"写作业|做作业|刷题|备考|自习|图书馆|沉浸学习|深度专注|心流|"
        r"放松音乐|放松心情|舒缓音乐|轻音乐|纯音乐|背景音乐|安静音乐|"
        r"减压音乐|解压音乐|助眠音乐|催眠音乐|睡眠音乐|冥想音乐)$|"
        # 学习/助眠场景的"功能描述型"标题（音频工厂批量生产的背景音）：
        # "自习室春日沉浸放松轻音乐""阅读纯音 享受书本让世界安静""白噪音学习"
        r"^(自习室|自习|阅读|看书|背书|学习|白噪音|专注|助眠|睡眠|冥想)"
        r"[^，。！？]{0,20}"
        r"(纯音|纯音乐|轻音乐|背景音|放松|减压|解压|治愈|专注|助眠|睡眠|"
        r"白噪音|音乐|学习|阅读)$|"
        r"^[^，。！？]{2,20}\s+(纯音|纯音乐|轻音乐|背景音|白噪音)"
        r"\s+[^，。！？]{2,20}$")

    def _pop_band(self, song) -> str:
        """返回歌曲的大众度分层：mainstream / mid / obscure"""
        db = self.local_db
        if hasattr(db, "popularity_score"):
            pop = db.popularity_score(song)
            if pop >= self.model.POP_MAINSTREAM:
                return "mainstream"
            if pop >= self.model.POP_MID:
                return "mid"
        return "obscure"

    # 标题明显是文章/节目/课程体（含感叹号、破折号长句、"自媒体/编程/变现"
    # 等知识付费词），不是歌曲名。小众层出现这类标题一律不收。
    _ARTICLE_TITLE_RE = re.compile(
        r"[！!？?]{1,}.*[！!？?]|"
        r"(自媒体|变现|钞能力|副业|搞钱|干货|必看|教你|学会|方法|技巧|攻略|"
        r"揭秘|真相|盘点|第\d+[集期课讲]|上集|下集|第[一二三四五六七八九十]+[集期])|"
        # "主题：很长的说明性副标题" —— 播客/课程/文章标题的典型形态，
        # 歌曲名极少使用中文冒号 + 20 字以上的解释性尾巴
        r"[：:][^：:]{18,}|"
        # 社交媒体文案特征：话题标签 / 平台名 / 长篇对话式标题
        r"#[^\s#]{2,}|(节目)$|\(节目\)|【片段】|\(翻自|（翻自）|冒泡|抖音|快手|"
        r"\d{3,}集|"
        # 视频回放/发布会/专访类内容（不是歌曲）：
        # "新闻发布会""直播回看""专访""发布会""签售会""见面会"
        r"新闻发布会|直播回看|直播回放|发布会|签售会|见面会|专访|路演|"
        # 日期前缀的资讯/播客条目："2026-08-20 AI不再烧钱：…"
        r"^\d{4}[-/.年]\d{1,2}[-/.月]\d{1,2}|"
        # 播客/专栏期号："010｜非传统…"、"EP12｜…"、"Vol.07 | …"
        r"^\s*(ep|vol|no)?\.?\s*\d{2,4}\s*[｜|·:：]|"
        # 微博/朋友圈式话题串："#乐队的夏天 #马赛克乐队"
        r"#[^\s#]{2,}\s+#")

    # 艺人名是"账号/频道"而非歌手：批量上传的音频号，其作品基本不是正规歌曲。
    # 只保留**强工厂特征**（平台名/频道后缀/有声书/宗教咒铃等），
    # 不含"音乐/工作室"这类正规厂牌也会用的词，避免误伤真歌手。
    _ACCOUNT_ARTIST_RE = re.compile(
        r"(有声|听书|说书|电台|FM|频道|节目|传媒|影音|音乐馆|音乐厅|"
        r"音乐铺|音乐坊|音乐汇|音乐站|音乐空间|官方账号|小助手|搬运|"
        r"冥想|正念|助眠|静心|清心|禅音|佛音|咒语|心经|道观|道乐|"
        r"教会|福音|经文|念诵|诵读|朗读|朗诵|AI主播|配音|"
        r"考研|留学|备考|题库|网课|学堂|教育在线)",
        re.I)

    def _is_account_artist(self, song) -> bool:
        """艺人名像批量上传账号/频道（而非歌手）"""
        a = (getattr(song, "artist", "") or "").strip()
        return bool(a and self._ACCOUNT_ARTIST_RE.search(a))

    # 翻奏黑话："纯音"（后面不带"乐"）是网乐平台"把他人歌曲去人声"的专属标注，
    # 形态有"纯音版/纯音)/纯音宿命版/纯音|Live/纯音氛围版/纯音伴奏曲/纯音安睡曲"
    # 以及"纯音 沉浸式阅读"这类功能背景音。全库 198 首里没有一首出自官方主流歌手
    # ——官方用的是"纯音乐版"(孙燕姿)/"纯享版"(谭维维·黄霄雲)/"无词版"(赵照)。
    # 因此"纯音(非乐)"无条件过滤，不看艺人（拖鞋pd/jaycd/DJ铁柱 等网名号一并排除）。
    # 负向前瞻排除"纯音符/纯音社/纯音色"等正常词，避免误伤。
    _FACTORY_PURE_RE = re.compile(
        r"纯音(?!乐|符|社|色|质|节|位|域|准|阶)",
        re.I)

    # 版本/场景标注：官方也会用这类词（纯享版/纯音乐版/无词版/治愈版…），
    # 不能一刀切；仅当艺人非主流（popularity < 主流阈值，即工厂号/小批量翻奏）
    # 才过滤，官方主流艺人的纯享版/无词版保留。
    _FACTORY_COVER_RE = re.compile(
        r"[（(【]\s*(纯享版|无词版|无人声版|伴奏版|纯音乐版|"
        r"钢琴纯音乐|治愈版|治愈版木吉他|放松版|助眠版|睡眠版|"
        r"学习版|改编版|翻唱版|"
        # 变速/氛围加工号（拖鞋pd 等批量号）：(1.1x DJ 氛围版)/(宿命氛围版)
        r"氛围版|慢摇版|加速版|降速版|夜店版|电音版|车载版|"
        r"\d\.\dx|x\d\.\d)\s*[)）】]",
        re.I)

    def _is_factory_cover(self, song) -> bool:
        """是否为音频工厂的批量翻奏/转存内容"""
        t = (getattr(song, "title", "") or "")
        pop = self.local_db.popularity_score(song)
        # 信号一：翻奏黑话"纯音版"——真艺术家从不用，无条件过滤
        if self._FACTORY_PURE_RE.search(t):
            return True
        # 信号二：版本/场景标注（纯享版/无词版/治愈版…）——官方主流艺人保留，
        # 非主流（< 主流阈值）艺人用这些标注基本都是工厂号/小批量翻奏
        if self._FACTORY_COVER_RE.search(t) \
                and pop < self.model.POP_MAINSTREAM:
            return True
        # 信号三：转存号批量扒歌留下的"书名号不成对"残缺标题
        # （张杰 (明天过后) / 苏打绿《山海 (Live)）——这类账号的作品一律不收
        if t.count("《") != t.count("》") and pop <= 0.0:
            return True
        return False

    def _is_task_phrase_title(self, song) -> bool:
        """歌名本身只是一句任务/状态描述（音频工厂梗歌的特征）"""
        t = (getattr(song, "title", "") or "").strip()
        if not t:
            return False
        if self._TASK_PHRASE_TITLE_RE.match(t):
            return True
        # 去括号后缀后再判一次，如《集中注意力 (纯音乐)》
        import re as _re
        core = _re.sub(r"[（(\[【].*?[)）\]】]", "", t).strip()
        return bool(core and self._TASK_PHRASE_TITLE_RE.match(core))

    def _is_article_title(self, song) -> bool:
        """标题像知识付费/自媒体文章，而非歌曲名"""
        t = (getattr(song, "title", "") or "").strip()
        return bool(t and self._ARTICLE_TITLE_RE.search(t))

    def _enforce_mainstream(self, picked: List[Song], candidates: List[Song],
                            ctx, prep, slots: int) -> List[Song]:
        """对已选结果做大众度配额校正

        规则：
          1. 目标：非优先位里 85% 来自 mainstream/mid，15% 可留给小众。
          2. 小众歌要进榜单，其相关度必须达到"好听且适配"的门槛——
             即高于**候选池中大众歌相关度的 75 分位**（要求冷门歌明显在水准
             之上，而不是只要比同类冷门歌好）。不达标即替换为大众歌。
          3. 若大众候选不足，则保留小众歌（不能为凑配额推不相关的歌）。
        """
        if not picked:
            return picked
        want_main = int(round(slots * self.MAINSTREAM_RATIO))
        bands = {s.id: self._pop_band(s) for s in picked}
        # "好听且适配"门槛 = 候选池中 mainstream/mid 作品相关度的 75 分位
        # （降序排列后取 1/4 处：小众歌必须比 3/4 的主流候选更贴合当前状态）
        main_scores = sorted(
            (self._score_song(s, ctx, prep) for s in candidates
             if self._pop_band(s) in ("mainstream", "mid")), reverse=True)
        bar = (main_scores[len(main_scores) // 4] if main_scores else 0.0)

        def is_ok(s):
            b = bands.get(s.id, "obscure")
            if b in ("mainstream", "mid"):
                return True
            # 小众歌要进榜单必须同时满足"非低质"与"相关度达标"：
            #   · 排除白噪音/合集/节目等低质内容（如《集中注意力》这类
            #     靠歌名蹭状态词的梗歌）；
            #   · 相关度必须达到大众歌中位水平（"好听且适配"门槛）。
            if is_junk_title(s, ctx):
                return False
            if self._is_task_phrase_title(s):
                return False   # 音频工厂梗歌（《集中注意力》等），非真作品
            if self._is_article_title(s):
                return False   # 知识付费/自媒体音频（文章体标题），非歌曲
            if self._is_account_artist(s):
                return False   # 艺人名是批量上传账号/频道，非歌手
            if self.local_db.popularity_score(s) <= 0:
                return False   # 非真人艺人（合集/频道/翻唱号）
            return self._score_song(s, ctx, prep) >= bar

        keep = [s for s in picked if is_ok(s)]
        n_main = sum(1 for s in keep if bands.get(s.id) in ("mainstream", "mid"))
        if n_main >= want_main:
            # 已满足配额：把其余小众按相关度保留头部，维持 30% 小众上限
            ob_keep = [s for s in keep if bands.get(s.id) == "obscure"]
            ob_cap = max(1, slots - want_main)
            if len(ob_keep) > ob_cap:
                ob_keep.sort(key=lambda s: -self._score_song(s, ctx, prep))
                drop = {s.id for s in ob_keep[ob_cap:]}
                keep = [s for s in keep if s.id not in drop]
            return keep[:slots]

        # 配额不足：用池里排名靠前的未选大众歌补足（补足同样避开低质内容）。
        # 注意：配额是用户明确的"优先大众"诉求，必须尽量补足；相关度下限只
        # 用来排除"完全不搭"的凑数歌（阈值放到 0.55×），不能因为门槛过高
        # 让大众名额补不满、结果又变回小众。
        used = {s.id for s in picked}
        titles_used = {normalize_title_key(s.title) for s in keep}
        floor = min((self._score_song(s, ctx, prep) for s in keep), default=0.0)
        add = []
        ranked = sorted(candidates, key=lambda s: -self._score_song(s, ctx, prep))
        for s in ranked:
            if len(keep) + len(add) >= slots:
                break
            if s.id in used or self._pop_band(s) not in ("mainstream", "mid"):
                continue
            if is_junk_title(s, ctx):
                continue
            sc = self._score_song(s, ctx, prep)
            if sc < floor * 0.55:
                continue   # 相关度明显低于已有歌：宁可留空也不要凑数
            tk = normalize_title_key(s.title)
            if tk and tk in titles_used:
                continue
            add.append(s)
            used.add(s.id)
            if tk:
                titles_used.add(tk)
        return (keep + add)[:slots]

    def _fallback_broaden(self, chosen: List[Song], ctx: RequestContext,
                          limit: int) -> List[Song]:
        """候选池不足时从全库兜底补足（按相关性得分排序）"""
        if len(chosen) >= limit:
            return chosen
        seen = {s.id for s in chosen}
        prep = self.model.prepare(ctx)

        def _lang_ok(s):
            # 兜底补足同样要守语言与纯音乐偏好，否则过滤形同虚设
            if ctx.pref_instrumental in ("yes", "no"):
                if bool(s.instrumental) != (ctx.pref_instrumental == "yes"):
                    return False
            if ctx.language not in LANG_GROUPS:
                return True
            match = (language_matches if ctx.language_explicit
                     else language_matches_pref)
            if match(ctx.language, self._song_language_fine(s)):
                return True
            return (not ctx.language_explicit
                    and self._song_language(s) == "instrumental")

        cands = self.local_db.sample_random(6000)
        if ctx.task_tag:
            cands += self.local_db.search_by_task_tag(ctx.task_tag, limit=1500)
        # 兜底补足同样要过滤低质/工厂内容，否则候选池不足时工厂号会从这里回流
        cands = [s for s in cands
                 if s.id not in seen
                 and _lang_ok(s)
                 and not is_junk_title(s, ctx)
                 and not self._is_task_phrase_title(s)
                 and not self._is_article_title(s)
                 and not self._is_account_artist(s)
                 and not self._is_factory_cover(s)]
        cands.sort(key=lambda s: -self._score_song(s, ctx, prep))
        for s in cands:
            if len(chosen) >= limit:
                break
            chosen.append(s)
        print(f"[Recommender] 兜底补足 → {len(chosen)} 首")
        return chosen

    def _infer_task_from_strategy(self, strategy: MusicStrategy) -> str:
        """从策略推断任务类型"""
        genres = [g.lower() for g in strategy.genres]
        note = strategy.notes.lower()
        expl = strategy.explanation.lower()
        combined = note + " " + expl

        # ---- 事件级子类优先识别 ----
        if any(w in combined for w in ["世界杯", "world cup", "生命之杯", "waka waka"]):
            return "entertainment-worldcup"
        if any(w in combined for w in ["奥运", "olympic", "我和你", "手拉手", "北京欢迎你"]):
            return "entertainment-olympics"
        if any(w in combined for w in ["nba", "灌篮高手", "篮球赛", "cba"]):
            return "entertainment-nba"
        if any(w in combined for w in ["足球", "欧冠", "英超", "西甲", "意甲", "德甲", "欧洲杯", "中超", "天下足球"]):
            return "entertainment-football"
        if any(w in combined for w in ["追剧", "看电视", "影视", "ost", "综艺"]):
            return "entertainment-tv"
        if any(w in combined for w in ["游戏", "电竞", "游戏bgm", "英雄联盟", "王者荣耀"]):
            return "entertainment-gaming"
        if any(w in combined for w in ["派对", "party", "舞池"]):
            return "entertainment-party"
        if any(w in combined for w in ["庆祝", "庆祝时刻", "喜悦"]):
            return "entertainment-celebration"
        if any(w in combined for w in ["社交", "约会", "浪漫"]):
            return "entertainment-social"
        if any(w in combined for w in ["打篮球", "投篮", "上篮", "三分球", "运球"]):
            return "workout-basketball"
        if any(w in combined for w in ["踢足球", "踢球"]):
            return "workout-football"
        if any(w in combined for w in ["跑步", "慢跑", "晨跑", "run", "running", "五公里", "十公里"]):
            return "workout-running"
        if any(w in combined for w in ["力量训练", "健身", "举铁", "力量"]):
            return "workout-strength"
        if any(w in combined for w in ["瑜伽", "拉伸", "冥想"]):
            return "workout-yoga"
        if any(w in combined for w in ["头脑风暴", "灵感", "发散思维", "brainstorm"]):
            return "creative-brainstorm"
        if any(w in combined for w in ["设计", "赶截止", "创作"]):
            return "creative-design"
        if any(w in combined for w in ["深度编码", "心流", "深度专注"]):
            return "coding-deep"
        if any(w in combined for w in ["调试", "排错", "反复失败"]):
            return "coding-debug"
        if any(w in combined for w in ["学新技术", "吸收信息"]):
            return "coding-learn"
        if any(w in combined for w in ["代码审查", "细致判断"]):
            return "coding-review"
        if any(w in combined for w in ["考前", "考试"]):
            return "study-exam"
        if any(w in combined for w in ["背单词", "记忆唤醒"]):
            return "study-vocab"
        if any(w in combined for w in ["阅读", "看书"]):
            return "study-reading"
        if any(w in combined for w in ["刷题", "做题"]):
            return "study-practice"
        if any(w in combined for w in ["冥想", "呼吸", "宁静"]):
            return "relax-meditate"
        if any(w in combined for w in ["用脑过度", "抚慰", "休息"]):
            return "relax-winddown"
        if any(w in combined for w in ["开车", "驾驶", "困倦"]):
            return "commute-driving"
        if any(w in combined for w in ["地铁", "通勤", "碎片时间"]):
            return "commute-transit"
        if any(w in combined for w in ["旅行", "travel", "旅途", "风景", "异国", "公路旅行"]):
            return "travel"

        # ---- 父类兜底 ----
        if any(w in combined for w in ["编程", "coding", "代码"]):
            return "coding"
        if any(w in combined for w in ["运动", "workout", "健身"]):
            return "workout"
        if any(w in combined for w in ["学习", "study", "复习"]):
            return "study"
        if any(w in combined for w in ["放松", "relax"]):
            return "relax"
        if any(w in combined for w in ["创意", "creative"]):
            return "creative"
        if any(w in combined for w in ["通勤", "commute"]):
            return "commute"
        if any(w in combined for w in ["睡眠", "sleep"]):
            return "sleep"
        if any(w in combined for w in ["赛事", "运动比赛", "sports"]):
            return "entertainment-football"

        # 按风格推断
        if any(g in genres for g in ["ambient", "classical", "minimalist"]):
            return "focus"
        if any(g in genres for g in ["electronic", "rock", "hip-hop"]):
            if strategy.energy_level >= 7:
                return "workout"
        return "focus"

    def _enrich_reasons(self, songs: List[Song], strategy: MusicStrategy,
                        task_hint: str, intent_kws=None):
        """为每首歌生成推荐理由

        intent_kws：本轮**用户真正点名**的关键词（歌手/作品/事件等专有名词）。
        只有命中这些词时，理由里才写"关键词「X」"——曲库抓取关键词（如"安静"
        "钢琴 安静"）只是入库来源，不代表用户意图，写进理由会让用户误以为
        系统在按歌名匹配。
        """
        intent_kws = set(intent_kws or ())
        reason_templates = {
            ("focus", True): "纯音乐、无歌词干扰，适合深度专注",
            ("focus", False): "节奏稳定、氛围沉浸，助你保持心流",
            ("workout", True): "纯音乐也能燃，驱动运动节奏",
            ("workout", False): "高能量强节奏，点燃运动表现",
            ("study", True): "低频轻声，不干扰信息吸收",
            ("study", False): "温和背景音，陪伴学习时光",
            ("relax", True): "舒缓旋律，帮你卸下压力",
            ("relax", False): "温暖治愈，给情绪一个出口",
            ("creative", True): "层次丰富的氛围音，激发灵感",
            ("creative", False): "律动感强，打开思维边界",
            ("commute", True): "轻松纯音，通勤路上的小确幸",
            ("commute", False): "欢快节奏，点亮每一段路程",
            ("sleep", True): "极致轻柔，带你进入梦乡",
            ("sleep", False): "温暖低语，安抚疲惫身心",
            ("entertainment-worldcup", False): "世界杯主题曲与球迷燃曲，释放足球热情",
            ("entertainment-worldcup", True): "世界杯氛围纯音乐，烘托赛场气氛",
            ("entertainment-olympics", False): "奥运主题曲与励志金曲，为健儿加油",
            ("entertainment-olympics", True): "恢弘激昂的纯音乐，呼应奥运精神",
            ("entertainment-nba", False): "NBA赛场嘻哈摇滚强节奏，放大对抗感",
            ("entertainment-nba", True): "篮球赛场BGM纯音乐，驱动比赛节奏",
            ("entertainment-football", False): "足球赛事主题曲与高能燃曲，带起观赛氛围",
            ("entertainment-football", True): "足球赛事氛围纯音乐，陪伴观赛时刻",
            ("entertainment-tv", False): "影视OST与轻松曲目，陪伴追剧时光",
            ("entertainment-tv", True): "舒缓纯音乐，营造追剧氛围",
            ("entertainment-gaming", False): "游戏BGM与电竞燃曲，激发操作欲",
            ("entertainment-gaming", True): "电子氛围纯音乐，沉浸游戏世界",
            ("entertainment-party", False): "热门派对节奏，让每个人都动起来",
            ("entertainment-party", True): "派对氛围纯音乐，保持舞池节奏",
            ("entertainment-celebration", False): "欢快节奏分享喜悦，庆祝时刻必备",
            ("entertainment-celebration", True): "庆祝氛围纯音乐，烘托喜悦气氛",
            ("entertainment-social", False): "轻松浪漫的节奏，营造社交氛围",
            ("entertainment-social", True): "舒缓纯音乐，陪伴愉悦社交",
            ("workout-running", False): "高BPM强节奏音乐，卡住跑步步伐",
            ("workout-running", True): "跑步节奏纯音乐，驱动步伐",
            ("workout-basketball", False): "嘻哈摇滚强节奏，驱动篮球爆发力",
            ("workout-basketball", True): "篮球运动纯音乐，保持比赛节奏",
            ("workout-football", False): "中高BPM音乐，维持足球跑动节奏",
            ("workout-football", True): "足球运动纯音乐，维持跑动节奏",
            ("workout-strength", False): "厚重强音放大力量感，助力力量训练",
            ("workout-strength", True): "力量训练纯音乐，驱动爆发力",
            ("workout-yoga", True): "极缓纯音乐配合呼吸，瑜伽拉伸首选",
            ("workout-yoga", False): "柔和氛围音乐，配合瑜伽动作",
            ("coding-deep", True): "极简环境音维持心流，深度编码首选",
            ("coding-debug", True): "镇静类纯音乐，理清调试思路",
            ("coding-learn", True): "轻声古典乐，辅助吸收新技术",
            ("coding-review", True): "优雅器乐保持警觉，细致审查代码",
            ("study-exam", True): "极轻古典乐平稳心绪，考前必备",
            ("study-vocab", True): "轻快巴洛克音乐，提升记忆唤醒度",
            ("study-reading", True): "低频纯音最舒适，陪伴阅读时光",
            ("study-practice", True): "节奏感电子纯音，刷题提神",
            ("relax-meditate", True): "极简环境音引导呼吸，冥想首选",
            ("relax-winddown", True): "温暖柔和纯音抚慰，用脑过度首选",
            ("commute-driving", False): "提神音乐保持清醒，安全驾驶第一",
            ("commute-transit", False): "欢快音乐把碎片时间变享受",
            ("travel", True): "悠扬旋律伴随旅途，旅行路上的风景",
            ("travel", False): "轻快节奏点亮旅途，旅行好心情",
            ("gaming", True): "电子氛围沉浸游戏世界，BGM驱动操作",
            ("gaming", False): "电竞燃曲激发操作欲，游戏时刻必备",
            ("social", True): "轻松纯音营造社交氛围，聚会好背景",
            ("social", False): "欢快节奏带动气氛，社交聚会首选",
            ("celebration", True): "欢庆纯音乐烘托喜悦，庆祝时刻必备",
            ("celebration", False): "喜庆节奏分享快乐，庆祝时刻首选",
            ("meditation", True): "极缓环境音引导呼吸，冥想静心首选",
            ("meditation", False): "空灵旋律引导内省，冥想陪伴",
            ("reading", True): "低频纯音不干扰阅读，安静陪伴",
            ("reading", False): "轻柔人声不打扰思绪，阅读好伴侣",
            ("sleep", True): "极致轻柔带你入眠，安神首选",
            ("sleep", False): "温暖低吟安抚身心，助你入睡",
            ("focus", True): "极简环境音维持心流，深度专注首选",
            ("focus", False): "稳定节奏氛围沉浸，助你保持专注",
            ("general", True): "百搭纯音乐，适合多种场景",
            ("general", False): "经典曲目，随时聆听的好选择",
        }

        for s in songs:
            instrumental = getattr(s, 'instrumental', False)
            key = (task_hint, instrumental)
            base_reason = reason_templates.get(
                key, reason_templates.get((task_hint, True),
                    "精准匹配你当前状态"))

            # 附加关键词命中信息：仅当该关键词是本轮用户点名的意图时才展示
            kw_info = ""
            skw = getattr(s, 'search_keyword', '')
            if skw and skw in intent_kws:
                kw_info = f" · 关键词「{skw}」"

            energy_desc = "低能量" if s.energy <= 3 else (
                "中等能量" if s.energy <= 6 else "高能量")
            s.reason = f"{base_reason} | {energy_desc} · {s.genre} · {s.tempo_bpm}BPM{kw_info}"

            # 填充 QQ 音乐跳转链接
            if not getattr(s, 'external_url', ''):
                query = urllib.parse.quote(f"{s.title} {s.artist}")
                s.external_url = QQMUSIC_SEARCH_URL.format(query)

            # 填充 genre
            if not getattr(s, 'genre', ''):
                s.genre = strategy.genres[0] if strategy.genres else "pop"

            # 填充乐器类型
            if not getattr(s, 'instrument_type', ''):
                genre_for_type = getattr(s, 'genre', '') or (
                    strategy.genres[0] if strategy.genres else "")
                s.instrument_type = infer_instrument_type(genre_for_type)
