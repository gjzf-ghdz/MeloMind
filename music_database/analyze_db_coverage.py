"""
分析当前数据库已有覆盖，识别补充爬取方向
"""
import json
import os
from collections import Counter

db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "music_database.json")
with open(db_path, "r", encoding="utf-8") as f:
    data = json.load(f)
songs = data["songs"]

print(f"{'='*60}")
print(f"当前数据库分析")
print(f"{'='*60}")
print(f"歌曲总数: {len(songs)}")
print()

# 1. search_keyword 分布
kw_count = Counter(s.get("search_keyword", "") for s in songs)
print(f"search_keyword 分类数: {len(kw_count)}")
print(f"search_keyword Top 30:")
for kw, c in kw_count.most_common(30):
    print(f"  {kw:<30} {c:>4} 首")
print()

# 2. 风格分布
genre_cn = {"classical": "古典", "pop": "流行", "rock": "摇滚",
            "electronic": "电子", "folk": "民谣", "r&b": "R&B",
            "hip-hop": "嘻哈", "jazz": "爵士", "ambient": "轻音乐",
            "neo-classical": "新古典", "minimalist": "极简", "indie": "独立"}
genres = Counter(s.get("genre", "unknown") for s in songs)
print(f"风格分布 ({len(genres)} 种):")
for g, c in genres.most_common():
    cn = genre_cn.get(g, g)
    pct = c / len(songs) * 100
    print(f"  {cn:<10} {c:>5} 首  {pct:>5.1f}%")
print()

# 3. 能量分布
energy_levels = Counter()
for s in songs:
    e = s.get("energy", 5)
    if e <= 3: energy_levels["低(1-3)"] += 1
    elif e <= 6: energy_levels["中(4-6)"] += 1
    else: energy_levels["高(7-10)"] += 1
print(f"能量分布:")
for k, v in energy_levels.items():
    pct = v / len(songs) * 100
    print(f"  {k:<10} {v:>5} 首  {pct:>5.1f}%")
print()

# 4. 纯音乐 vs 人声
inst_count = sum(1 for s in songs if s.get("instrumental"))
print(f"纯音乐: {inst_count} 首 ({inst_count/len(songs)*100:.1f}%)")
print(f"人声歌曲: {len(songs)-inst_count} 首 ({(len(songs)-inst_count)/len(songs)*100:.1f}%)")
print()

# 5. 缺失的热门榜单类关键词
all_kws = set(kw_count.keys())
toplist_kws = {"流行指数榜", "热歌榜", "新歌榜", "原创榜", "飙升榜", "内地榜", "港台榜",
               "欧美榜", "日本榜", "韩国榜", "华语金曲榜", "腾讯音乐人原创榜",
               "网络歌曲榜", "说唱榜", "电音榜", "DJ舞曲榜", "民谣榜", "古典榜",
               "影视金曲榜", "动漫音乐榜", "游戏音乐榜", "KTV点唱榜", "美国公告牌",
               "UK排行", "Billboard", "iTunes", "Spotify"}
missing = toplist_kws - all_kws
print(f"榜单类关键词缺失 {len(missing)} 个:")
for kw in sorted(missing):
    print(f"  - {kw}")
print()

# 6. 缺失的流派类关键词
genre_kw_map = {
    "华语流行": "华语", "粤语流行": "粤语", "华语民谣": "华语民谣", "校园民谣": "校园民谣",
    "古风": "古风", "国风流行": "国风", "华语说唱": "说唱", "华语摇滚": "华语摇滚",
    "City Pop": "City Pop", "华语R&B": "华语R&B", "灵魂乐": "Soul", "放克": "Funk",
    "迪斯科": "Disco", "雷鬼": "Reggae", "蓝调": "Blues", "乡村音乐": "Country",
    "金属": "Metal", "朋克": "Punk", "硬核": "Hardcore", "后摇": "Post-Rock",
    "迷幻摇滚": "Psychedelic", "独立摇滚": "Indie Rock", "车库摇滚": "Garage",
    "Lo-Fi": "Lo-Fi", "蒸汽波": "Vaporwave", "合成器流行": "Synthpop",
    "工业金属": "Industrial", "死亡金属": "Death Metal", "黑金属": "Black Metal",
    "新世纪音乐": "New Age", "氛围音乐": "Ambient Music", "实验音乐": "Experimental",
    "世界音乐": "World Music", "凯尔特音乐": "Celtic", "弗拉门戈": "Flamenco",
    "Bossa Nova": "Bossa Nova", "爵士演唱": "Vocal Jazz", " Bebop": "Bebop",
    "电影原声带": "OST", "电视剧配乐": "电视剧OST", "动漫BGM": "动漫BGM",
    "游戏BGM": "游戏BGM", "音乐剧": "Musical", "合唱": "Choral",
    "唱诗班": "Gregorian", "阿卡贝拉": "Acapella", "Beatbox": "Beatbox",
    "儿歌": "儿歌", "胎教音乐": "胎教", "轻音乐": "轻音乐",
    "中国风": "中国风", "戏曲": "戏曲", "传统民乐": "民乐",
    "周杰伦": "周杰伦", "陈奕迅": "陈奕迅", "林俊杰": "林俊杰", "薛之谦": "薛之谦",
    "李荣浩": "李荣浩", "毛不易": "毛不易", "许嵩": "许嵩", "邓紫棋": "邓紫棋",
    "王菲": "王菲", "刘德华": "刘德华", "张学友": "张学友", "张惠妹": "张惠妹",
    "林俊杰": "林俊杰", "孙燕姿": "孙燕姿", "蔡依林": "蔡依林", "SHE": "SHE",
    "凤凰传奇": "凤凰传奇", "五月天": "五月天", "李健": "李健", "朴树": "朴树",
}
missing_genre = set(genre_kw_map.keys()) - all_kws
print(f"流派/歌手类关键词缺失 {len(missing_genre)} 个")
for kw in sorted(missing_genre)[:20]:
    print(f"  - {kw}")
print(f"  ... 共 {len(missing_genre)} 个")
