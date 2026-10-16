"""站内 30 秒试听直链解析（多音源）

只做「取试听直链」一件事，且只取音源方**官方提供的试听片段**：

  1. Apple iTunes Search API —— 官方 previewUrl（约 30 秒），免密钥、免登录，
     覆盖中/英/日/韩主流曲目，以及大量古典、钢琴、氛围类纯音乐。
     该 30 秒片段是 Apple 已获授权、面向公众开放试听的推广素材（Promo Content）。
  2. QQ 音乐 vkey 接口       —— 原音源，代码保留；匿名调用已被官方关闭
     （返回 retcode=104009 / invalidq），仅当配置了登录凭据时才启用。

检索策略 ——「按文字体系选店面」：
  Apple 曲库按国家/地区店面分片，美区店面里几乎搜不到华语歌。曲库以华语为主，
  因此中文歌先搜港/台店面，日文歌先搜日本店面，西文歌才走默认（美区）。
  实测「周杰伦 晴天」美区 1 条结果、港/台区各 3 条；这一步把可试听覆盖率
  从 ~79% 提升到 ~97%，并且能把原唱而不是翻唱找回来。

匹配原则（避免「试听是别人的翻唱，用户却以为在听原唱」）：
  · 原唱优先 —— 只有当歌手与原曲吻合时才判定为原唱；
  · 歌手名写法不同但时长几乎一致时（如「陈粒」/「Chen Li」），仍视为原唱；
  · 曲库简体、港澳台店面给繁体（「后来」/「後來」）逐字比对完全对不上时，
    以「歌手吻合 + 曲名长度一致 + Apple 相关性最高 + 时长吻合」认定为原唱；
  · 找不到原唱时，才回退到「曲名完全一致 + 时长差几秒」的他人版本，
    并把 match 标为 "cover"，由前端如实告知「这是谁的翻唱/其它版本」；
  · 曲名相同但时长差得多（很可能只是同名不同歌），以及伴奏、卡拉OK、
    铃声等无意义条目，一律不返回，宁可没有试听也不放错。

版权合规（详见 docs 中的合规说明）：
  · 只转发音源方 CDN 的直链，音频始终由音源方 CDN 直接送达浏览器；
  · 服务端**不下载、不转存、不代理、不缓存音频文件**，只有链接进缓存；
  · 同时返回 store_url（音源方曲目页），前端提供「在 Apple Music 打开」跳转，
    满足 Apple「推广内容须邻近商店入口」的条款要求；
  · 前端明确标注「试听片段由 Apple 提供」，不做二次分发、不用于任何获利场景。
"""
import json
import os
import random
import re
import threading
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request

_BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))

_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

# ---------------- 缓存与限速 ----------------
_CACHE = {}                       # key -> (结果字典 或 {}，过期时间戳)
_CACHE_LOCK = threading.Lock()
_CACHE_VERSION = 5                # 匹配规则/店面策略升级后旧缓存一律作废重算
_TTL_HIT = 6 * 3600               # 命中缓存 6 小时（iTunes 试听片段地址长期有效）
_TTL_MISS = 20 * 60               # 确实没有资源：20 分钟后可再试
_TTL_ERR = 60                     # 接口报错（限流/网络）：1 分钟后即可重试
_MAX_CACHE = 3000

# Apple 官方"建议"约 20 次/分钟，但实测（连续 70 次请求约 14 秒内发完）全部 200、
# 无限流迹象，说明这个数字非常保守。原先按 15 次/60 秒自限，导致用户连续点几首后
# 后续歌曲全部被误判为"音源繁忙"，是试听覆盖率偏低的主因之一。
# 这里放宽到 90 次/60 秒（1.5 次/秒），仍保留 403/429 的退避重试，
# 一旦真被限流会自动降速并短暂缓存错误，不会把"能试听的歌"记成"没有资源"。
_RATE_WINDOW = 60.0
_RATE_MAX = 90
_rate_lock = threading.Lock()
_call_times = []

# ---------------- iTunes ----------------
_ITUNES_API = "https://itunes.apple.com/search"

# 店面（country）优先级 —— 这是"能不能试听"的关键：
# Apple 的曲库按国家/地区店面分片，美区店面里几乎没有华语歌，
# 之前固定用默认（美区）检索，导致大量华语曲目被判成"没有资源"。
# 实测「周杰伦 晴天」：美区 1 条结果、港区/台区各 3 条。
# 因此按标题/歌手的文字体系挑最可能有货的店面，首个店面就命中的概率最高，
# 既省接口调用（限流压力更小），又显著提高可试听比例。
_STOREFRONT_BY_SCRIPT = (
    (re.compile(r"[\u3040-\u30ff]"), ("jp", "tw", "hk", None, "us")),   # 日文
    (re.compile(r"[\uac00-\ud7af]"), ("kr", "jp", None, "hk", "us")),   # 韩文
    (re.compile(r"[\u4e00-\u9fff]"), ("hk", "tw", None, "jp", "gb")),   # 中文
)
_DEFAULT_STOREFRONTS = (None, "gb", "us", "hk")
_MAX_STOREFRONTS = 3              # 单首歌最多试 3 个店面，避免拖慢点播


def _storefronts(title, artist):
    """按曲名/歌手的文字体系给出店面检索顺序。"""
    blob = f"{title or ''} {artist or ''}"
    for rx, order in _STOREFRONT_BY_SCRIPT:
        if rx.search(blob):
            return order
    return _DEFAULT_STOREFRONTS

# 试听结果落盘，重启后依然有效，可大幅减少对接口的重复调用
_PERSIST = os.path.join(_BACKEND_DIR, "preview_cache.json")
_persist_lock = threading.Lock()
_last_save = [0.0]


class PreviewUnavailable(Exception):
    """音源接口暂时不可用（限流 / 网络异常）——不代表这首歌没有资源。"""


def _acquire_slot(max_wait=15.0):
    """滑动窗口限流：保证 60 秒内对 iTunes 的调用不超过 _RATE_MAX 次。

    拿不到空位时最多等 max_wait 秒就放弃（返回 False），避免请求长时间挂起。
    """
    deadline = time.time() + max_wait
    while True:
        with _rate_lock:
            now = time.time()
            while _call_times and now - _call_times[0] > _RATE_WINDOW:
                _call_times.pop(0)
            if len(_call_times) < _RATE_MAX:
                _call_times.append(now)
                return True
            wait = _RATE_WINDOW - (now - _call_times[0]) + 0.05
        if time.time() + wait > deadline:
            return False
        time.sleep(min(max(wait, 0.1), 5.0))


def _load_persist():
    """启动时载入未过期的试听缓存（版本不符则整体丢弃，按新规则重算）。"""
    try:
        with open(_PERSIST, "r", encoding="utf-8") as f:
            data = json.load(f)
        if data.get("v") != _CACHE_VERSION:
            return 0            # 旧规则算出的结果可能把翻唱当成原唱，不能沿用
        now = time.time()
        n = 0
        for key, val in (data.get("entries") or {}).items():
            if isinstance(val, list) and len(val) == 2 and val[1] > now:
                _CACHE[key] = (val[0] if isinstance(val[0], dict) else {}, val[1])
                n += 1
        return n
    except Exception:
        return 0


def _save_persist(force=False):
    """把缓存写回磁盘；默认 20 秒内最多写一次，避免频繁 IO。"""
    now = time.time()
    with _persist_lock:
        if not force and now - _last_save[0] < 20:
            return
        _last_save[0] = now
    try:
        with _CACHE_LOCK:
            snap = {k: [v[0], v[1]] for k, v in _CACHE.items() if v[1] > now}
        tmp = _PERSIST + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"v": _CACHE_VERSION, "entries": snap}, f, ensure_ascii=False)
        os.replace(tmp, _PERSIST)
    except Exception:
        pass


def _norm(s):
    """归一化：全角转半角、去括号内容、去标点符号，用于标题/歌手比对。"""
    s = unicodedata.normalize("NFKC", s or "").lower()
    s = re.sub(r"[\(\[（【].*?[\)\]）】]", " ", s)
    s = re.sub(r"[\s\-_/·、,，.。!！?？'\"“”‘’:：;；&+]+", "", s)
    return s.strip()


# 明显不是正常演唱版本的条目（伴奏 / 卡拉OK / 铃声 / 纯伴奏改编）：
# 拿来当「翻唱」播放体验很差，宁可不给试听。
_REJECT_RE = re.compile(
    r"(伴奏|卡拉\s*ok|karaoke|off\s*vocal|伴唱|铃声|ringtone|"
    r"tribute\s*band|music\s*box|オルゴール)", re.I)

# 多歌手分隔符：「A/B」「A & B」「A feat. B」
_ARTIST_SPLIT_RE = re.compile(r"[;、/&,]|\bfeat\.?\b|\bft\.?\b|\bwith\b", re.I)

_ARTIST_SCORE = {"exact": 60, "contains": 40, "partial": 15, "none": 0}
_DUR_TOL_ORIG = 20.0     # 原唱版本：时长允许的偏差（现场版/remaster 常差十几秒）
_DUR_TOL_COVER = 10.0    # 翻唱版本：必须与原曲时长接近，否则很可能只是「同名不同歌」
_DUR_SAME = 1.5          # 曲名完全相同：时长要几乎一致，才认定为同一录音
_DUR_SAME_CJK = 3.5      # 曲名仅繁简/异体字差异：本身就是「同一首歌」的佐证，可稍放宽


def _is_cjk(s):
    """整串是否都为中日文字符。"""
    return bool(s) and all("\u2e80" <= c <= "\u9fff" for c in s)


def _cjk_fuzzy(a, b):
    """中日文标题 / 艺人的字形相似度。

    曲库是简体、音源方常给繁体（「海阔天空」/「海闊天空」），逐字比对可容忍
    这类差异；字数相差超过 1 个则不采信。
    """
    if not a or not b or abs(len(a) - len(b)) > 1:
        return 0.0
    if not (_is_cjk(a) and _is_cjk(b)):
        return 0.0
    same = sum(1 for x, y in zip(a, b) if x == y)
    return same / float(max(len(a), len(b)))


def _artist_tokens(s):
    """把「A/B & C」这类多歌手串拆成独立歌手名。"""
    return [p.strip() for p in _ARTIST_SPLIT_RE.split(s or "") if p.strip()]


def _artist_level(na, ra, na_tokens):
    """判断歌手吻合度：exact / contains / partial / none。"""
    if not na or not ra:
        return "none"
    if na == ra:
        return "exact"
    if na in ra or ra in na:
        return "contains"
    for x in na_tokens:
        nx = _norm(x)
        if not nx:
            continue
        for y in _artist_tokens(ra):
            ny = _norm(y)
            if ny and (nx == ny or nx in ny or ny in nx):
                return "contains"
    # 繁简 / 异体字差异（如「陈奕迅」/「陳奕迅」）
    if _cjk_fuzzy(na, ra) >= 0.6:
        return "contains"
    common = set(na) & set(ra)
    if len(common) >= max(2, int(len(na) * 0.6)):
        return "partial"
    return "none"


def _evaluate(row, nt, na, na_tokens, duration):
    """评估一条 iTunes 结果与原曲的吻合度。"""
    rt = _norm(row.get("trackName"))
    ra = _norm(row.get("artistName"))
    title_exact = bool(nt) and rt == nt
    title_close = bool(nt and rt) and not title_exact and (
        nt in rt or rt in nt or _cjk_fuzzy(nt, rt) >= 0.6)
    level = _artist_level(na, ra, na_tokens)

    delta = None
    ms = row.get("trackTimeMillis")
    if duration and ms:
        delta = abs(duration - ms / 1000.0)

    score = 100 if title_exact else (50 if title_close else 0)
    score += _ARTIST_SCORE[level]
    if delta is not None and delta <= 5:
        score += 25
    return {"row": row, "score": score, "title_exact": title_exact,
            "title_close": title_close, "level": level, "delta": delta,
            # 繁简差异也算「同一个曲名」；不含「A 是 B 的子串」这种宽松关系
            "title_cjk": title_exact or _cjk_fuzzy(nt, rt) >= 0.6,
            # 曲名长度一致：繁简/异体字逐字比对完全对不上时（「后来」/「後來」）
            # 用来兜底判定「同一首歌」
            "len_same": bool(nt and rt) and len(nt) == len(rt),
            "sim": _cjk_fuzzy(nt, rt)}


# 曲库风格 → Apple 风格白名单（子串匹配）。
# 用途：拦住「曲名相同、其实是另一首歌」的情况。
# 例：Chris Webby《La La La》(hiphop) 与 Naughty Boy《La La La》(Pop) 曲名一模一样，
# 风格白名单对不上，直接排除，不会张冠李戴。
_GENRE_FAMILY = {
    "pop":           ("pop", "vocal", "easy listening", "singer/songwriter",
                      "dance", "soundtrack", "world", "r&b"),
    "rock":          ("rock", "alternative", "metal", "punk", "indie",
                      "singer/songwriter"),
    "folk":          ("folk", "singer/songwriter", "country", "world",
                      "easy listening", "acoustic"),
    "hiphop":        ("hip-hop", "rap", "r&b", "urban"),
    "r&b":           ("r&b", "soul", "funk", "hip-hop", "pop"),
    "electronic":    ("electronic", "dance", "house", "techno", "trance",
                      "edm", "club", "ambient", "new age"),
    "indie":         ("alternative", "indie", "rock", "pop", "singer/songwriter"),
    "jazz":          ("jazz", "blues", "easy listening", "vocal", "bossa"),
    "classical":     ("classical", "new age", "instrumental", "easy listening",
                      "soundtrack", "world", "jazz"),
    "neo-classical": ("classical", "new age", "instrumental", "easy listening",
                      "soundtrack"),
    "minimalist":    ("classical", "new age", "instrumental", "easy listening",
                      "ambient", "electronic"),
    "ambient":       ("ambient", "new age", "electronic", "classical",
                      "instrumental", "easy listening", "dance"),
}


def _genre_ok(db_genre, row):
    """风格是否兼容；任一方缺失时返回 True（不据此拦截）。"""
    fam = _GENRE_FAMILY.get((db_genre or "").strip().lower())
    it = (row.get("primaryGenreName") or "").strip().lower()
    if not fam or not it:
        return True
    return any(k in it for k in fam)


def _weighted_len(s):
    """CJK / 假名 / 谚文按 2 计，其余按 1 计（中日韩标题信息密度更高）。"""
    n = 0
    for ch in s or "":
        n += 2 if ("\u2e80" <= ch <= "\u9fff" or "\u3040" <= ch <= "\u30ff"
                   or "\uac00" <= ch <= "\ud7af") else 1
    return n


def _distinctive(nt):
    """曲名是否足够独特。像「lalala」这种重复字标题同名撞车概率极高，不予采信。"""
    if not nt or _weighted_len(nt) < 6:
        return False
    return len(set(nt)) / float(len(nt)) >= 0.6


def _blob(e):
    return (e["row"].get("trackName") or "") + " " + (e["row"].get("artistName") or "")


def _itunes_search(term, country=None):
    """调用 iTunes 搜索接口，返回结果列表。

    限流 / 网络异常时抛 PreviewUnavailable —— 上层必须区分「接口不可用」和
    「这首歌没有资源」，否则会把本来能试听的歌误标记成不可试听。
    """
    query = {"term": term, "entity": "song", "limit": "8", "media": "music"}
    if country:
        query["country"] = country
    url = _ITUNES_API + "?" + urllib.parse.urlencode(query)
    req = urllib.request.Request(url, headers={
        "User-Agent": _UA,
        "Accept": "application/json, text/javascript, */*; q=0.01",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    })
    last = None
    for attempt in range(3):
        if not _acquire_slot():
            raise PreviewUnavailable("等待限流空位超时")
        try:
            with urllib.request.urlopen(req, timeout=8) as resp:
                data = json.loads(resp.read().decode("utf-8", "replace"))
            return data.get("results") or []
        except urllib.error.HTTPError as e:
            last = e
            if e.code in (403, 429) and attempt < 2:
                time.sleep(3.0 * (attempt + 1))      # 被限流：退避后再试
                continue
            break
        except Exception as e:
            last = e
            break
    raise PreviewUnavailable("%s: %s" % (type(last).__name__, last))


def _pick_best(rows, nt, na, na_tokens, duration, genre=""):
    """从搜索结果里挑试听条目，返回 (评估结果, 类型)。

    类型：
      "original" —— 原唱/官方版本（或可判定为同一录音、同一首歌），优先选用
      "cover"    —— 曲名一致、时长差几秒的他人版本，视为翻唱/其它版本
      ""         —— 没有可信结果，宁可不放，避免张冠李戴

    判定顺序（从严到宽）：
      1. 歌手名吻合                       → 原唱
      2. 曲名独特 + Apple 排序靠前         → 同一首歌换了名字写法（如「周杰伦」/「Jay Chou」）→ 原唱
      3. 曲名一致 + 时长几乎一致            → 同一录音（如「陈粒」写成「Chen Li」）→ 原唱
      4. 曲名一致 + 时长差几秒 + 风格吻合   → 他人翻唱/其它版本 → 标 cover
    """
    cands = []
    for i, r in enumerate(rows):
        if not r.get("previewUrl"):
            continue
        e = _evaluate(r, nt, na, na_tokens, duration)
        e["rank"] = i                  # Apple 的相关性排序，越小越相关
        cands.append(e)
    if not cands:
        return None, ""

    # 1) 原唱：歌手吻合（写法差异也认）
    originals = [e for e in cands
                 if e["level"] != "none"
                 and (e["title_exact"] or e["title_close"])
                 and (e["delta"] is None or e["delta"] <= _DUR_TOL_ORIG)]
    if originals:
        return max(originals, key=lambda e: e["score"]), "original"

    # 1b) 繁体/简体逐字比对完全对不上（「后来」/「後來」、「红日」/「紅日」）：
    #     歌手吻合 + 曲名长度一致 + Apple 相关性最高 + 时长吻合 → 同一首原唱。
    #     曲库是简体、港澳台店面给繁体，"一个字都对不上"很常见，不做这层会大面积漏配。
    #     注意歌手名同样可能繁简不同（「刘若英」/「劉若英」），因此不要求 exact。
    if duration:
        trad = [e for e in cands
                if e["level"] != "none" and e["len_same"] and e["rank"] <= 1
                and e["delta"] is not None and e["delta"] <= _DUR_TOL_ORIG]
        if trad:
            return min(trad, key=lambda e: (e["rank"], e["delta"])), "original"

    # 没有时长可比对时不再往下猜（否则只能靠曲名，容易张冠李戴）
    if not duration:
        return None, ""

    usable = [e for e in cands if not _REJECT_RE.search(_blob(e))]

    # 2) 同一首歌换了名字写法：曲名独特 + Apple 排序靠前。
    #    例：曲库「周杰伦 - 青花瓷」，iTunes 上歌手写作「Jay Chou」，
    #    中文名与英文名对不上，只能借助 Apple 自身的相关性排序来认定。
    #    这一步必须早于下面的「时长一致」，否则会误选同名翻唱版。
    #    注意：这一层不校验风格——曲库的风格标签本身噪声较大
    #    （如莫文蔚被标成 ambient），拿来拦截会误伤真正的原唱。
    renamed = []
    for e in usable:
        # title_cjk：曲名完全一致，或只是繁简/异体字差异（「球迷奇遇记」/「球迷奇遇記」）
        if not e["title_cjk"] or not _distinctive(nt) or e["rank"] > 2:
            continue
        # 排在最前的那个，时长容差放宽；靠后的要求更严
        tol = _DUR_TOL_ORIG if e["rank"] == 0 else (_DUR_SAME + 3.5)
        if e["delta"] is None or e["delta"] <= tol:
            renamed.append(e)
    if renamed:
        return min(renamed, key=lambda e: (e["rank"],
                                          e["delta"] if e["delta"] is not None else 999)), "original"

    # 3) 同一录音：曲名一致 + 时长几乎一致（短标题、罕见曲名的兜底）
    #    例：曲库「李克勤 - 球迷奇遇记」，音源写作「Hacken Lee - 球迷奇遇記」
    same = []
    for e in usable:
        if not e["title_cjk"] or e["delta"] is None or e["rank"] > 2:
            continue
        tol = _DUR_SAME if e["title_exact"] else _DUR_SAME_CJK
        if e["delta"] <= tol:
            same.append(e)
    if same:
        return min(same, key=lambda e: e["delta"]), "original"

    # 4) 他人翻唱/其它版本：曲名一致 + 时长接近 + 风格吻合 → 标注后播放
    covers = [e for e in usable
              if e["title_cjk"] and e["delta"] is not None
              and e["delta"] <= _DUR_TOL_COVER and _genre_ok(genre, e["row"])]
    if covers:
        # 时长越贴近越可信，其次看总分
        return min(covers, key=lambda e: (e["delta"], -e["score"])), "cover"

    return None, ""


def _build_result(pick, kind, songmid=""):
    """把评估结果整理成对外返回结构。"""
    row = pick["row"]
    return {
        "url": row["previewUrl"],
        "match": kind,                                  # original / cover
        "source": "itunes",
        "preview_title": (row.get("trackName") or "").strip(),
        "preview_artist": (row.get("artistName") or "").strip(),
        "preview_album": (row.get("collectionName") or "").strip(),
        # 音源方曲目页：前端据此给出商店入口（同时满足 Apple 推广内容条款）
        "store_url": (row.get("trackViewUrl") or "").strip(),
        "duration_delta": (round(pick["delta"], 1)
                           if pick.get("delta") is not None else None),
    }


def _itunes_preview(title, artist, duration=0.0, genre=""):
    """取 Apple 官方 30 秒试听，返回结果字典；拿不到返回 None。

    优先返回原唱版本；只有找不到原唱时，才回退到「曲名一致 + 时长吻合」的
    他人版本，并把 match 标记为 cover，让前端如实告诉用户这是翻唱。

    检索按「店面优先级」逐个尝试（华语歌先搜港/台店面，日韩先搜日/韩店面），
    多数歌在第一个店面就能命中，因此通常只消耗 1 次接口调用。
    """
    title = (title or "").strip()
    artist = (artist or "").strip()
    if not title:
        return None
    nt, na = _norm(title), _norm(artist)
    na_tokens = _artist_tokens(artist)
    order = _storefronts(title, artist)
    term_full = ((artist + " " + title).strip() if artist else title)[:180]

    pick, kind = None, ""
    for idx, country in enumerate(order[:_MAX_STOREFRONTS]):
        try:
            rows = _itunes_search(term_full, country)
        except PreviewUnavailable:
            if idx == 0:
                # 首个店面就不可用：多半是整体被限流，交给上层按 503 处理让用户重试
                raise
            break
        p, k = _pick_best(rows, nt, na, na_tokens, duration, genre)
        if k == "original":
            return _build_result(p, k)
        if k == "cover" and kind != "cover":
            pick, kind = p, k

    # 主检索没找到原唱时，用「纯曲名」再搜一轮：
    # 歌手名写法差异大（「周杰伦」/「Jay Chou」）时，曲名反而更容易命中
    try:
        more = _itunes_search(title[:180], order[0])
    except PreviewUnavailable:
        more = []
    p2, k2 = _pick_best(more, nt, na, na_tokens, duration, genre)
    if k2 == "original" or (k2 == "cover" and kind != "cover"):
        pick, kind = p2, k2

    # 仍非原唱时，再试：多值歌手取主歌手 + 换一个店面
    if kind != "original" and len(na_tokens) > 1:
        alt = order[1] if len(order) > 1 else order[0]
        try:
            ex_rows = _itunes_search((na_tokens[0] + " " + title)[:180], alt)
        except PreviewUnavailable:
            ex_rows = []
        p3, k3 = _pick_best(ex_rows, nt, na, na_tokens, duration, genre)
        if k3 == "original" or (k3 == "cover" and kind != "cover"):
            pick, kind = p3, k3

    if not pick:
        return None
    return _build_result(pick, kind)


# ---------------- QQ 音乐（原音源，匿名接口已被官方关闭） ----------------
_QQ_API = "https://u.y.qq.com/cgi-bin/musicu.fcg"
_QQ_CRED_FILE = os.path.join(_BACKEND_DIR, "qq_credential.json")
_GUID = str(random.randint(10 ** 9, 10 ** 10 - 1))


def _qq_credential():
    """读取可选的 QQ 音乐登录凭据（uin + cookie）；未配置返回空。"""
    try:
        with open(_QQ_CRED_FILE, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        return str(cfg.get("uin") or "").strip(), str(cfg.get("cookie") or "").strip()
    except Exception:
        return "", ""


def fetch_qq_stream_url(songmid):
    """向 QQ 音乐换取限时直链；未配置凭据或拿不到时返回空串。"""
    mid = (songmid or "").strip()
    if not mid or len(mid) > 32:
        return ""
    uin, cookie = _qq_credential()
    if not uin or not cookie:
        return ""      # 匿名调用已被官方关闭，无凭据直接跳过，不浪费超时
    comm_uin = int(uin) if uin.isdigit() else 0
    payload = {
        "req_0": {
            "module": "vkey.GetVkeyServer",
            "method": "CgiGetVkey",
            "param": {"guid": _GUID, "songmid": [mid], "songtype": [0],
                      "uin": uin, "loginflag": 1, "platform": "20"},
        },
        "comm": {"uin": comm_uin, "format": "json", "ct": 24, "cv": 0},
    }
    req = urllib.request.Request(
        _QQ_API,
        data=json.dumps(payload).encode("utf-8"),
        headers={"User-Agent": _UA, "Referer": "https://y.qq.com/",
                 "Content-Type": "application/json", "Cookie": cookie},
    )
    with urllib.request.urlopen(req, timeout=6) as resp:
        data = json.loads(resp.read().decode("utf-8"))

    info = (data.get("req_0") or {}).get("data") or {}
    urlinfo = info.get("midurlinfo") or []
    purl = (urlinfo[0].get("purl") if urlinfo else "") or ""
    if not purl:
        return ""      # 无版权 / 需要付费 / 未登录，接口会返回空 purl
    hosts = [h for h in (info.get("sip") or []) if h.startswith("http")]
    if not hosts:
        return ""
    return hosts[0].rstrip("/") + "/" + purl.lstrip("/")


def resolve_stream_url(songmid):
    """兼容旧调用：只走 QQ 音乐音源（供自检脚本使用）。"""
    try:
        return fetch_qq_stream_url(songmid)
    except Exception as e:
        print(f"[Preview] QQ 取直链失败 {songmid}: {type(e).__name__}: {e}", flush=True)
        return ""


# ---------------- 对外统一入口 ----------------
def resolve_preview(mid="", title="", artist="", duration=0.0, genre=""):
    """返回试听结果字典（拿不到返回空字典 {}）。

    结构：
      url            —— 可播放的试听直链
      match          —— "original" 原唱（含官方版本）/ "cover" 他人的翻唱或其它版本
      source         —— itunes / qq
      preview_title  —— 实际播放的曲名
      preview_artist —— 实际播放的歌手（翻唱时前端据此告知用户）

    先取 Apple 官方 30 秒试听片段（原唱优先，找不到才回退翻唱版），
    失败再回退 QQ 音乐（需配置登录凭据）。
    """
    mid = (mid or "").strip()
    title = (title or "").strip()
    artist = (artist or "").strip()
    genre = (genre or "").strip()
    try:
        duration = float(duration or 0)
    except (TypeError, ValueError):
        duration = 0.0

    key = mid or (artist + "|" + title).lower()
    if not key:
        return {}

    now = time.time()
    with _CACHE_LOCK:
        hit = _CACHE.get(key)
        if hit and hit[1] > now:
            return dict(hit[0]) if hit[0] else {}

    info = None
    interface_error = False
    try:
        info = _itunes_preview(title, artist, duration, genre)
    except PreviewUnavailable as e:
        interface_error = True
        print(f"[Preview] iTunes 接口不可用 {title} / {artist}: {e}", flush=True)
    except Exception as e:
        interface_error = True
        print(f"[Preview] iTunes 异常 {title} / {artist}: {type(e).__name__}: {e}", flush=True)

    # iTunes 没找到时回退 QQ 音乐（仅在配置了登录凭据时才真正发起请求）
    if not info and mid:
        try:
            url = fetch_qq_stream_url(mid)
            if url:
                # 曲库 mid 对应的就是原曲，直接视为原唱
                info = {"url": url, "match": "original", "source": "qq",
                        "preview_title": title, "preview_artist": artist,
                        "preview_album": "", "store_url": "",
                        "duration_delta": None}
        except Exception as e:
            print(f"[Preview] QQ 取直链失败 {mid}: {type(e).__name__}: {e}", flush=True)

    if info:
        ttl = _TTL_HIT
        payload = dict(info)
    elif interface_error:
        ttl = _TTL_ERR       # 接口问题：只短暂记住，稍后重试，不当成「没有资源」
        payload = {"url": "", "interface_error": True}
    else:
        ttl = _TTL_MISS      # 确实没有资源
        payload = {}

    with _CACHE_LOCK:
        if len(_CACHE) >= _MAX_CACHE:
            _CACHE.clear()
        _CACHE[key] = (payload, now + ttl)
    if payload.get("url"):
        _save_persist()
    return dict(payload)


try:
    _persisted = _load_persist()
    if _persisted:
        print(f"[Preview] 已载入试听缓存 {_persisted} 条", flush=True)
except Exception:
    pass
