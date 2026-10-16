"""验证特殊名词优先推送相关歌曲"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from recommender import MusicRecommender
from models import MusicStrategy

rec = MusicRecommender()

# (用户消息, 期望命中的关键词/标题片段)
TESTS = [
    ("我在看世界杯", "世界杯"),
    ("我在看甄嬛传", None),       # 电视剧名 → 别名映射到"电视剧" + 标题可能含"甄嬛传"
    ("我在看泰坦尼克号", None),    # 电影名 → 别名映射到"电影配乐"
    ("我在玩王者荣耀", "游戏"),
    ("我在看千与千寻", None),      # 电影名/动画 → 标题可能含"千与千寻"
    ("我在看灌篮高手", None),      # 动漫 → 标题或别名
    ("我在看三体", None),          # 电视剧名 → 别名映射到"电视剧"
    ("我在听卡农", "卡农"),        # 名曲 → 别名直接匹配
    ("我在听致爱丽丝", "致爱丽丝"),
    ("我在看流浪地球", None),       # 电影名 → 别名映射到"电影配乐"
    ("我在玩原神", "游戏"),
    ("我在看鬼灭之刃", None),      # 动漫名
    ("我在听久石让", "久石让"),     # 艺术家
]

print("=" * 70)
print("特殊名词优先推送验证")
print("=" * 70)

for msg, expected_kw in TESTS:
    strategy = MusicStrategy(
        genres=["pop"], energy_level=5, mood_target="balanced",
        instrumental_preferred=False,
        explanation=msg, notes=msg,
    )

    songs = rec.recommend(strategy, limit=5, task_type="general",
                           user_message=msg)

    # 检查推荐结果是否与特殊名词相关
    related = []
    for s in songs:
        title = s.get("title", "")
        artist = s.get("artist", "")
        sk = s.get("search_keyword", "")
        related.append(f"{title}({sk})")

    # 判断是否有直接标题命中
    noun = None
    for keyword in ["世界杯", "甄嬛传", "泰坦尼克", "千与千寻",
                    "灌篮高手", "三体", "卡农", "致爱丽丝",
                    "流浪地球", "原神", "鬼灭", "久石让", "王者荣耀"]:
        if keyword in msg:
            noun = keyword
            break

    # 检查推荐歌曲中是否有包含该名词的
    has_title_match = any(noun and noun in s.get("title", "")
                          for s in songs) if noun else False
    # 检查 search_keyword 是否相关
    has_kw_match = any(expected_kw and expected_kw in s.get("search_keyword", "")
                       for s in songs) if expected_kw else False

    status = "✓" if (has_title_match or has_kw_match) else "~"
    print(f"\n[{status}] 「{msg}」")
    print(f"  推荐: {', '.join(related[:3])}")
    if noun:
        print(f"  标题直接命中「{noun}」: {'是' if has_title_match else '否'}")
    if expected_kw:
        print(f"  关键词命中「{expected_kw}」: {'是' if has_kw_match else '否'}")

print("\n" + "=" * 70)
print("验证完成（✓=命中, ~=仅通过别名/关键词间接匹配）")
