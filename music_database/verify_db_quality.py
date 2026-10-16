"""全面验证音乐数据库质量"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# 确保能导入 backend 模块
_BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend"))
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       "music_database.json")

REQUIRED_FIELDS = [
    "id", "title", "artist", "album", "genre",
    "duration_sec", "tempo_bpm", "instrumental", "instrument_type",
    "energy", "mood_tags", "task_tags", "external_url", "reason",
    "search_keyword",
]


def main():
    with open(DB_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)

    songs = data["songs"]
    print(f"{'='*60}")
    print(f"音乐数据库质量报告")
    print(f"{'='*60}")
    print(f"版本: {data.get('version')}")
    print(f"来源: {data.get('source')}")
    print(f"歌曲总数: {len(songs)}")
    print()

    # 1. 字段完整性
    print("【1】字段完整性检查")
    missing = {}
    for field in REQUIRED_FIELDS:
        # instrumental 是布尔值，False 是有效值
        if field == "instrumental":
            count = sum(1 for s in songs if s.get(field) is None)
        else:
            count = sum(1 for s in songs if not s.get(field))
        if count:
            missing[field] = count
            pct = 100 * count // len(songs)
            print(f"  ⚠ 字段 '{field}' 缺失: {count} 首 ({pct}%)")
    if not missing:
        print("  ✅ 所有必需字段完整")

    # 2. 风格分布
    print("\n【2】风格分布")
    genre_dist = {}
    for s in songs:
        g = s.get("genre", "unknown")
        genre_dist[g] = genre_dist.get(g, 0) + 1
    for g, c in sorted(genre_dist.items(), key=lambda x: -x[1]):
        pct = 100 * c // len(songs)
        bar = "█" * (pct // 2)
        print(f"  {g:<12} {c:>5} 首 ({pct:>3}%) {bar}")

    # 3. 能量分布
    print("\n【3】能量等级分布")
    energy_buckets = {"1-3 (低)": 0, "4-6 (中)": 0, "7-10 (高)": 0}
    for s in songs:
        e = s.get("energy", 5)
        if e <= 3:
            energy_buckets["1-3 (低)"] += 1
        elif e <= 6:
            energy_buckets["4-6 (中)"] += 1
        else:
            energy_buckets["7-10 (高)"] += 1
    for label, c in energy_buckets.items():
        pct = 100 * c // len(songs)
        bar = "█" * (pct // 2)
        print(f"  {label:<12} {c:>5} 首 ({pct:>3}%) {bar}")

    # 4. 情绪标签分布
    print("\n【4】情绪标签分布 (Top 15)")
    mood_dist = {}
    for s in songs:
        for m in s.get("mood_tags", []):
            mood_dist[m] = mood_dist.get(m, 0) + 1
    mood_cn = {
        "calm": "平静", "energetic": "亢奋", "joyful": "欢快", "sad": "悲伤",
        "hopeful": "励志", "dreamy": "梦幻", "groovy": "律动",
        "focused": "专注", "inspired": "灵感", "soothing": "治愈",
        "balanced": "平衡", "alert": "提神", "festive": "欢庆",
        "celebratory": "庆祝", "romantic": "浪漫", "powerful": "力量",
        "relaxed": "放松", "peaceful": "安宁",
    }
    for m, c in sorted(mood_dist.items(), key=lambda x: -x[1])[:15]:
        cn = mood_cn.get(m, m)
        print(f"  {cn:<10} ({m:<15}) {c:>5} 次")

    # 5. 任务标签分布
    print("\n【5】任务标签分布")
    task_dist = {}
    for s in songs:
        for t in s.get("task_tags", []):
            task_dist[t] = task_dist.get(t, 0) + 1
    task_cn = {"study": "学习", "workout": "运动", "relax": "放松",
               "entertainment": "娱乐", "commute": "通勤", "coding": "编程",
               "creative": "创意", "general": "通用"}
    for t, c in sorted(task_dist.items(), key=lambda x: -x[1]):
        cn = task_cn.get(t, t)
        print(f"  {cn:<10} ({t:<15}) {c:>5} 次")

    # 6. 乐器分布
    print("\n【6】主要乐器分布")
    inst_dist = {}
    for s in songs:
        i = s.get("instrument_type", "未知")
        inst_dist[i] = inst_dist.get(i, 0) + 1
    for i, c in sorted(inst_dist.items(), key=lambda x: -x[1]):
        print(f"  {i:<12} {c:>5} 首")

    # 7. 纯音乐 vs 人声
    print("\n【7】纯音乐 vs 人声")
    inst_count = sum(1 for s in songs if s.get("instrumental"))
    vocal_count = len(songs) - inst_count
    print(f"  纯音乐: {inst_count} 首 ({100*inst_count//len(songs)}%)")
    print(f"  人声演唱: {vocal_count} 首 ({100*vocal_count//len(songs)}%)")

    # 8. 事件关键词收录验证
    print("\n【8】事件关键词收录验证")
    event_checks = {
        "世界杯": ["世界杯", "世界杯主题曲"],
        "奥运会": ["奥运会", "奥运主题曲"],
        "NBA": ["NBA"],
        "足球": ["足球", "足球之歌"],
        "电视剧": ["电视剧", "OST"],
        "游戏": ["游戏", "电竞"],
        "派对": ["派对", "舞曲"],
        "运动": ["跑步", "运动", "健身"],
        "古典": ["古典", "钢琴曲"],
    }
    for category, kws in event_checks.items():
        count = 0
        for s in songs:
            if s.get("search_keyword", "") in kws:
                count += 1
        print(f"  {category}: {count} 首")

    # 9. 推荐理由验证
    print("\n【9】推荐理由质量")
    reason_ok = sum(1 for s in songs if len(s.get("reason", "")) > 10)
    reason_short = sum(1 for s in songs if len(s.get("reason", "")) <= 10)
    print(f"  理由>10字符: {reason_ok} 首 ({100*reason_ok//len(songs)}%)")
    if reason_short:
        print(f"  ⚠ 理由<=10字符: {reason_short} 首")

    # 10. 外部链接验证
    print("\n【10】外部链接质量")
    has_url = sum(1 for s in songs if s.get("external_url", ""))
    print(f"  有QQ音乐链接: {has_url} 首 ({100*has_url//len(songs)}%)")

    print(f"\n{'='*60}")
    print(f"验证完成！")


if __name__ == "__main__":
    main()
