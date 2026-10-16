"""
重新标注 task_tags - 16 种任务标签（子串匹配 + 风格/能量回退）

用法:
  python retag_16.py [input.json] [output.json]

只更新 task_tags 字段，保留其它所有字段不变。
"""
import json
import os
import sys
import collections

# ============================================================
# 16 种任务标签
# ============================================================
# 1. coding      编码 / 深度工作
# 2. study       学习 / 记忆 / 考试
# 3. workout     运动 / 跑步 / 健身
# 4. commute     通勤 / 驾驶
# 5. relax       放松 / 治愈 / 休息
# 6. creative    创意 / 灵感
# 7. entertainment 娱乐赛事 (世界杯/奥运/NBA/影视)
# 8. social      社交 / 派对 / 约会
# 9. celebration 庆祝 / 节日
# 10. meditation 冥想 / 禅意
# 11. reading    阅读 / 安静
# 12. travel     旅行 / 民谣 / 异国
# 13. sleep      睡眠 / 助眠 / 自然音
# 14. focus      专注 / 极简 / 环境
# 15. gaming     游戏 / 电竞
# 16. general    通用兜底

# 关键词子串规则：(task_tag, [子串列表])  - 子串在 search_keyword 中出现即命中
KEYWORD_RULES = [
    ("coding", ["深度工作", "白噪音", "编程", "代码", "心流", "深度专注",
                "深度编码", "coder", "coding", "排错", "调试", "代码审查"]),
    ("study", ["学习", "记忆", "考试", "巴洛克", "背单词", "刷题", "做题",
               "协奏", "弦乐", "莫扎特", "巴赫", "贝多芬", "奏鸣曲", "交响",
               "记忆唤醒", "考前", "复习", "吸收"]),
    ("workout", ["运动", "跑步", "健身", "力量", "热血", "燃曲", "劲爆",
                 "edm", "dj", "电子舞曲", "力量训练", "举铁", "晨跑", "慢跑",
                 "高强度", "马拉松", "五公里", "十公里", "running", "跑",
                 "健身操", "动感单车"]),
    ("commute", ["通勤", "地铁", "驾驶", "开车", "公路", "碎片时间",
                 "驾车", "出行"]),
    ("relax", ["放松", "休息", "治愈", "安神", "抚慰", "舒缓", "下班",
               "轻音乐", "治愈钢琴", "浪漫钢琴", "理查德克莱德曼",
               "spa", "水疗", "放松钢琴", "解压", "休闲", "下午茶",
               "发呆", "放空", "悠闲"]),
    ("creative", ["灵感", "创意", "设计", "氛围", "头脑风暴", "einaudi",
                 "久石让", "hisaishi", "坂本龙一", "sakamoto", "发散思维",
                 "cran", "lanz", "winston", "创作", "艺术家", "灵感激发"]),
    ("entertainment", ["世界杯", "奥运", "nba", "足球", "影视", "综艺",
                       "赛事", "欧冠", "英超", "灌篮", "主题曲",
                       "西甲", "意甲", "德甲", "中超", "cba", "欧洲杯",
                       "足球之歌", "赛事观看", "看球", "观赛"]),
    ("social", ["派对", "舞池", "约会", "浪漫", "社交", "聚会",
                "咖啡馆", "商场", "商店", "舞会", "联谊",
                "聚餐", "朋友", "社交聚会"]),
    ("celebration", ["庆祝", "喜悦", "节日", "圣诞", "生日", "欢庆",
                     "新年", "婚礼", "庆典", "喜庆", "贺", "派对庆祝"]),
    ("meditation", ["冥想", "432hz", "颂钵", "禅意", "呼吸", "灵气",
                    "reiki", "古琴", "尺八", "瑜伽", "太极", "禅修",
                    "正念", "静心", "打坐", "气功"]),
    ("reading", ["阅读", "安静", "书店", "看书", "伴读", "读书",
                 "图书馆", "书房"]),
    ("travel", ["旅行", "旅途", "风景", "异国", "公路旅行", "指弹",
                "民谣", "世界音乐", "非洲", "日本", "越南", "蒙古",
                "印度", "夏威夷", "凯尔特", "拉丁", "异域", "流浪",
                "卡林巴", "拇指琴", "三味线", "太鼓", "呼麦"]),
    ("sleep", ["助眠", "睡眠", "入眠", "摇篮曲", "雨声", "海浪",
               "森林", "鸟鸣", "自然纯音乐", "自然音效", "流水",
               "深度睡眠", "安眠", "催眠", "夜曲", "晚安"]),
    ("focus", ["极简", "环境音", "深度", "minimal", "ambient",
               "downtempo", "专注", "工作bgm", "心流", "环境音乐",
               "降噪", "白噪音"]),
    ("gaming", ["游戏", "电竞", "rpg", "bgm", "战斗", "boss",
                "英雄联盟", "王者荣耀", "副本", "地图", "解谜",
                "ost", "原声", "boss战", "战斗热血", "结局"]),
]

# 风格 + 能量回退：当 search_keyword 没命中任何规则时使用
# 注意：pop 不强制分配，交给能量逻辑细分
GENRE_FALLBACK = {
    "classical": ["study", "relax"],
    "neo-classical": ["relax", "creative"],
    "minimalist": ["focus", "coding"],
    "ambient": ["focus", "sleep", "relax"],
    "electronic": ["workout", "gaming"],
    "rock": ["workout", "entertainment"],
    "pop": [],
    "hip-hop": ["workout"],
    "r&b": ["relax"],
    "jazz": ["relax"],
    "folk": ["travel", "relax"],
    "indie": ["creative", "relax"],
}


def infer_task_tags_16(search_keyword, genre, energy, mood_tags, instrumental):
    """16 标签推断：子串匹配 + 风格/能量回退"""
    tags = []
    sk_lower = (search_keyword or "").lower()
    genre_lower = (genre or "").lower()

    # 1. 关键词子串匹配
    for tag, substrings in KEYWORD_RULES:
        for sub in substrings:
            if sub.lower() in sk_lower:
                if tag not in tags:
                    tags.append(tag)
                break  # 该标签已命中，跳到下一标签

    # 2. 风格回退（仅当关键词没命中足够标签时）
    if len(tags) < 2:
        for tag in GENRE_FALLBACK.get(genre_lower, []):
            if tag not in tags:
                tags.append(tag)

    # 3. 能量回退（仅当风格回退仍不足时）
    if not tags:
        if energy >= 8:
            tags = ["entertainment", "workout"]
        elif energy >= 7:
            tags = ["workout"]
        elif energy <= 2:
            tags = ["sleep", "relax"]
        elif energy <= 4:
            tags = ["relax"]
        elif instrumental:
            tags = ["focus"]
        else:
            tags = ["general"]

    # 4. 兜底：至少有一个标签
    if not tags:
        tags = ["general"]

    # 限制最多 4 个标签
    return tags[:4]


def main():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    inp = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
        script_dir, "music_database.json")
    out = sys.argv[2] if len(sys.argv) > 2 else inp  # 默认原地更新

    print(f"读取: {inp}")
    with open(inp, "r", encoding="utf-8") as f:
        data = json.load(f)

    songs = data.get("songs", [])
    print(f"共 {len(songs)} 首歌曲待重新标注 task_tags")

    before = collections.Counter()
    after = collections.Counter()
    multi_tag_count = 0

    for s in songs:
        for t in (s.get("task_tags") or []):
            before[t] += 1

        sk = s.get("search_keyword", "")
        genre = s.get("genre", "")
        energy = s.get("energy", 5)
        mood_tags = s.get("mood_tags", [])
        instrumental = s.get("instrumental", False)

        new_tags = infer_task_tags_16(sk, genre, energy, mood_tags, instrumental)
        s["task_tags"] = new_tags

        for t in new_tags:
            after[t] += 1
        if len(new_tags) > 1:
            multi_tag_count += 1

    # 原子写入
    tmp = out + ".tmp"
    result = {**data, "version": 3, "retag_16": True}
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    os.replace(tmp, out)

    print(f"\n写入: {out}")
    print(f"\n=== task_tags 变化 ===")
    all_tags = sorted(set(list(before.keys()) + list(after.keys())))
    print(f"{'标签':<16} {'之前':>8} {'之后':>8} {'变化':>8}")
    for tag in all_tags:
        b = before.get(tag, 0)
        a = after.get(tag, 0)
        diff = a - b
        sign = "+" if diff >= 0 else ""
        print(f"  {tag:<14} {b:>8} {a:>8} {sign}{diff:>7}")
    print(f"\n多标签歌曲数: {multi_tag_count} / {len(songs)} ({100*multi_tag_count//len(songs)}%)")


if __name__ == "__main__":
    main()
