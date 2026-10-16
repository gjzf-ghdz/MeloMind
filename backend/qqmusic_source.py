"""QQ音乐数据源 - 纯搜索 + 歌曲信息，不获取播放链接"""
import json
import urllib.request
import urllib.parse
from typing import List, Optional
from models import Song, infer_instrument_type


class QQMusicSource:
    """QQ音乐搜索源"""

    BASE_SEARCH = "https://c.y.qq.com/soso/fcgi-bin/client_search_cp"
    SONG_URL_FMT = "https://y.qq.com/n/ryqq/songDetail/{songmid}"
    # QQ 热门榜单 API（无需登录）
    BASE_CHART = "https://c.y.qq.com/qzone/fcg-bin/fcg_ucc_getcdinfo_byids_cp.fcg"

    # QQ 官方榜单 ID（从 https://y.qq.com/n/ryqq/toplist 可查）
    CHART_IDS = {
        "hot": "26",           # 热歌榜
        "new": "3",            # 新歌榜
        "original": "100",     # 原创榜
        "eu_us": "1899",       # 欧美榜
        "korean": "1601",      # 韩国榜
        "japanese": "1602",    # 日本榜
        "classical": "1247",   # 古典榜
        "electronic": "2184",  # 电子榜
        "hiphop": "178",       # 说唱榜
        "rock": "1248",        # 摇滚榜
        "folk": "1249",        # 民谣榜
        "rnb": "2175",         # R&B榜
        "tencent": "4",        # 腾讯音乐榜
    }

    GENRE_MAP = {
        "classical": "古典", "pop": "流行", "rock": "摇滚",
        "electronic": "电子", "folk": "民谣", "r&b": "R&B",
        "hip-hop": "嘻哈", "jazz": "爵士", "ambient": "轻音乐",
        "neo-classical": "轻音乐", "minimalist": "轻音乐",
        "indie": "民谣",
    }

    MOOD_KEYWORDS = {
        "calm": ["安静", "舒缓", "治愈", "轻音乐"],
        "peaceful": ["安静", "钢琴曲", "冥想"],
        "energetic": ["劲爆", "热血", "燃", "运动"],
        "happy": ["欢快", "开心", "元气"],
        "melancholic": ["伤感", "深情", "治愈"],
        "sad": ["悲伤", "钢琴", "纯音乐"],
        "hopeful": ["励志", "温暖", "正能量"],
        "dreamy": ["梦幻", "空灵", "氛围"],
        "groovy": ["节奏", "律动", "放克"],
        "joyful": ["欢快", "快乐", "动感"],
        "powerful": ["力量", "史诗", "燃"],
        "focused": ["专注", "学习", "白噪音"],
        "inspired": ["灵感", "创意", "氛围"],
        "soothing": ["治愈", "放松", "轻音乐"],
        "balanced": ["轻松", "流行", "经典"],
        "alert": ["提神", "清新", "活力"],
        "festive": ["欢庆", "庆祝", "派对"],
        "celebratory": ["庆祝", "欢庆", "喜悦"],
        "romantic": ["浪漫", "情歌", "温馨"],
        "lively": ["活力", "欢快", "动感"],
        "energized": ["提神", "活力", "动感"],
        "relaxed": ["轻松", "舒缓", "放松"],
        "warm": ["温暖", "治愈", "柔和"],
    }

    TASK_KEYWORDS = {
        "focus": ["专注", "学习", "轻音乐"],
        "deep-work": ["专注", "白噪音", "纯音乐"],
        "study": ["学习", "阅读", "古典"],
        "relax": ["放松", "治愈", "冥想"],
        "workout": ["运动", "健身", "跑步"],
        "creative": ["灵感", "创意", "氛围"],
        "commute": ["轻松", "流行", "开车"],
        "sleep": ["睡眠", "钢琴", "白噪音"],
        "coding": ["编程", "专注", "轻音乐"],
        "writing": ["写作", "安静", "古典"],
    }

    # 事件级搜索词表：不同事件推荐不同歌曲（如世界杯→世界杯主题曲）
    EVENT_KEYWORDS = {
        "entertainment-worldcup": ["世界杯", "世界杯主题曲", "生命之杯", "Waka Waka", "意大利之夏", "Goal Goal Goal"],
        "entertainment-olympics": ["奥运会", "奥运主题曲", "我和你", "手拉手", "北京欢迎你", "超越", "我和你 奥运"],
        "entertainment-nba": ["NBA", "篮球", "灌篮高手", "篮球音乐", "NBA主题曲", "灌篮高手 主题曲"],
        "entertainment-football": ["足球", "足球之歌", "欧冠主题曲", "天下足球", "英超", "西甲", "足球 主题曲"],
        "entertainment-tv": ["电视剧", "OST", "主题曲", "追剧", "影视原声", "电视剧 主题曲"],
        "entertainment-gaming": ["游戏", "电竞", "游戏背景音乐", "英雄联盟", "游戏BGM", "原神"],
        "entertainment-party": ["派对", "舞曲", "DJ", "派对音乐", "狂欢"],
        "entertainment-celebration": ["庆祝", "生日", "欢庆", "庆祝歌", "恭喜"],
        "entertainment-social": ["浪漫", "情歌", "约会", "温馨", "社交音乐"],
        "workout-running": ["跑步", "运动", "健身", "跑步音乐", "运动 燃"],
        "workout-basketball": ["篮球", "运动", "嘻哈", "篮球音乐", "街球"],
        "workout-football": ["足球", "运动", "足球音乐", "踢球"],
        "workout-strength": ["健身", "力量", "撸铁", "健身音乐", "力量训练"],
        "workout-yoga": ["瑜伽", "冥想", "轻音乐", "瑜伽音乐"],
    }

    def __init__(self):
        pass

    def search(self, keyword: str, limit: int = 20, page: int = 1) -> List[Song]:
        params = {"w": keyword, "format": "json", "p": page, "n": limit, "cr": 1}
        query = urllib.parse.urlencode(params)
        url = f"{self.BASE_SEARCH}?{query}"

        req = urllib.request.Request(url)
        req.add_header("User-Agent",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36")
        req.add_header("Referer", "https://y.qq.com")

        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            return self._parse_results(data, limit)
        except Exception as e:
            print(f"[QQMusic] Search error: {e}")
            return []

    def search_pages(self, keyword: str, per_page: int = 80,
                     pages: int = 3) -> List[Song]:
        """多页搜索，返回去重后的歌曲列表"""
        all_songs = []
        seen = set()
        for p in range(1, pages + 1):
            songs = self.search(keyword, limit=per_page, page=p)
            if not songs:
                break
            for s in songs:
                if s.id not in seen:
                    seen.add(s.id)
                    all_songs.append(s)
        return all_songs

    def get_chart(self, chart_key: str = "hot", limit: int = 100) -> List[Song]:
        """获取 QQ 音乐热门榜单歌曲（需要登录态，可能返回空）"""
        cdid = self.CHART_IDS.get(chart_key)
        if not cdid:
            return []
        params = {"disstid": cdid, "format": "json", "type": 1,
                  "json": 1, "utf8": 1, "onlysong": 1}
        query = urllib.parse.urlencode(params)
        url = f"{self.BASE_CHART}?{query}"

        req = urllib.request.Request(url)
        req.add_header("User-Agent",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36")
        req.add_header("Referer", f"https://y.qq.com/n/ryqq/toplist/{cdid}")
        req.add_header("Origin", "https://y.qq.com")

        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                text = resp.read().decode("utf-8")
            if text.startswith("callback"):
                text = text[text.index("(") + 1:text.rindex(")")]
            data = json.loads(text)
            return self._parse_chart(data, limit)
        except Exception as e:
            print(f"[QQMusic] Chart({chart_key}) error: {e}")
            return []

    def _parse_chart(self, data: dict, limit: int) -> List[Song]:
        """解析榜单 JSON"""
        try:
            cdlist = data.get("cdlist", [])
            songs = []
            if cdlist:
                song_list = cdlist[0].get("songlist", [])
            else:
                song_list = []
            for item in song_list[:limit]:
                songmid = item.get("songmid", "")
                songname = item.get("songname", "")
                singers = item.get("singer", [])
                artist = singers[0].get("name", "未知") if singers else "未知"
                album = item.get("albumname", "")
                interval = item.get("interval", 0)
                albummid = item.get("albummid", "")
                cover = ""
                if albummid:
                    cover = f"https://y.gtimg.cn/music/photo_new/T002R300x300M000{albummid}.jpg"
                external = self.SONG_URL_FMT.format(songmid=songmid) if songmid else ""
                songs.append(Song(
                    id=songmid, title=songname, artist=artist,
                    album=album, duration_sec=interval,
                    cover_url=cover, external_url=external,
                    source="qqmusic", instrumental=True,
                ))
            return songs
        except Exception as e:
            print(f"[QQMusic] Chart parse error: {e}")
            return []

    def search_by_mood_task(self, mood: str, task: str = "",
                            limit: int = 20,
                            event_kw: Optional[list] = None) -> List[Song]:
        """情绪+任务组合搜索。event_kw 优先级最高，用于事件级精细化推荐。"""
        all_songs = []
        seen = set()
        queries = []
        force_instrumental = True

        # ---- 事件级关键词优先（如世界杯主题曲，要带歌词，不强制纯音乐） ----
        if event_kw:
            force_instrumental = False
            # 组合：两个事件词拼一起做主查询
            if len(event_kw) >= 2:
                queries.append(f"{event_kw[0]} {event_kw[1]}")
            queries.extend(event_kw[:4])

        # ---- 情绪+任务关键词补充 ----
        keywords = []
        if mood:
            kws = self.MOOD_KEYWORDS.get(mood, [mood])
            keywords.extend(kws[:2])
        if task:
            kws = self.TASK_KEYWORDS.get(task, [task])
            keywords.extend(kws[:2])
        if not keywords and not event_kw:
            keywords = ["推荐"]

        # 组合搜索词
        if len(keywords) >= 2:
            queries.append(f"{keywords[0]} {keywords[2]}" if len(keywords) > 2
                          else f"{keywords[0]} {keywords[1]}")
        queries.extend(keywords)

        # 专注类任务强制纯音乐；事件类任务（有 event_kw）保留人声主题曲
        if force_instrumental:
            queries = [f"{q} 纯音乐" for q in queries]

        # 去重查询词
        seen_q = set()
        unique_queries = []
        for q in queries:
            if q not in seen_q:
                seen_q.add(q)
                unique_queries.append(q)

        per_q = max(3, limit // max(1, len(unique_queries)) + 3)
        for q in unique_queries[:5]:
            songs = self.search(q, limit=per_q)
            for s in songs:
                if s.id not in seen:
                    seen.add(s.id)
                    all_songs.append(s)
            if len(all_songs) >= limit:
                break

        return all_songs[:limit]

    def search_by_genre(self, genre: str, limit: int = 20) -> List[Song]:
        kw = self.GENRE_MAP.get(genre.lower(), genre)
        return self.search(kw, limit=limit)

    def _parse_results(self, data: dict, limit: int) -> List[Song]:
        try:
            song_list = data.get("data", {}).get("song", {}).get("list", [])
            songs = []
            for item in song_list:
                songmid = item.get("songmid", "")
                songname = item.get("songname", "") or item.get("title", "")

                singers = item.get("singer", [])
                artist = singers[0].get("name", "未知") if singers else "未知"

                album = item.get("albumname", "") or item.get("album", {}).get("name", "")
                interval = item.get("interval", 0)
                albummid = item.get("albummid", "")
                cover = ""
                if albummid:
                    cover = f"https://y.gtimg.cn/music/photo_new/T002R300x300M000{albummid}.jpg"
                external = self.SONG_URL_FMT.format(songmid=songmid) if songmid else ""

                songs.append(Song(
                    id=songmid, title=songname, artist=artist,
                    album=album, duration_sec=interval,
                    cover_url=cover, external_url=external,
                    source="qqmusic", instrumental=True,
                ))
            return songs[:limit]
        except Exception as e:
            print(f"[QQMusic] Parse error: {e}")
            return []


    def search_song_detail(self, title: str, artist: str = "") -> Optional[Song]:
        """搜索单曲详情，返回真实时长等（用于详情弹窗）"""
        query = title if not artist else f"{title} {artist}"
        results = self.search(query, limit=5)
        if not results:
            return None
        # 找最匹配：标题完全一致优先，否则模糊匹配
        target = title.lower().strip()
        for s in results:
            if s.title.lower().strip() == target:
                return s
        # 模糊匹配：标题包含
        for s in results:
            if target in s.title.lower():
                return s
        return results[0]


_qqmusic_instance: Optional[QQMusicSource] = None

def get_qqmusic() -> QQMusicSource:
    global _qqmusic_instance
    if _qqmusic_instance is None:
        _qqmusic_instance = QQMusicSource()
    return _qqmusic_instance
