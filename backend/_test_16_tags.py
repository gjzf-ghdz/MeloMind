"""验证 16 种任务标签的推荐效果"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from recommender import MusicRecommender
from models import MusicStrategy

# (task_type, user_message, 期望 task_tag 包含)
TESTS = [
    ("coding", "我在写代码", "coding"),
    ("coding-deep", "深度编码心流", "coding"),
    ("study", "我在学习", "study"),
    ("study-reading", "我在看书阅读", "reading"),
    ("workout", "我要运动健身", "workout"),
    ("workout-running", "我去跑步", "workout"),
    ("workout-yoga", "我做瑜伽拉伸", "meditation"),
    ("commute", "我在通勤路上", "commute"),
    ("commute-driving", "我在开车驾驶", "commute"),
    ("relax", "我想放松休息", "relax"),
    ("relax-meditate", "我要冥想呼吸", "meditation"),
    ("creative", "我需要创意灵感", "creative"),
    ("entertainment-worldcup", "我在看世界杯", None),  # 特殊名词
    ("entertainment-gaming", "我在玩王者荣耀", "gaming"),
    ("entertainment-social", "我在约会社交", "social"),
    ("entertainment-celebration", "我要庆祝生日", "celebration"),
    ("sleep", "我要睡觉了", "sleep"),
    ("focus", "我需要专注", "focus"),
    ("travel", "我在旅行途中", "travel"),
    ("general", "随便听听", "general"),
]

rec = MusicRecommender()

print("=" * 70)
print("16 种任务标签推荐验证")
print("=" * 70)

for task_type, msg, expected_tag in TESTS:
    strategy = MusicStrategy(
        genres=["pop"],
        energy_level=5,
        mood_target="balanced",
        instrumental_preferred=False,
        explanation=msg,
        notes=msg,
    )

    songs = rec.recommend(strategy, limit=5, task_type=task_type, user_message=msg)

    # 统计 task_tags
    tag_counts = {}
    for s in songs:
        for t in s.get("task_tags", []):
            tag_counts[t] = tag_counts.get(t, 0) + 1

    top_tags = sorted(tag_counts.items(), key=lambda x: -x[1])[:3]

    print(f"\n[{task_type}] 「{msg}」")
    print(f"  推荐 {len(songs)} 首, top tags: {top_tags}")
    for s in songs[:3]:
        print(f"    - {s['title']} | {s['artist']} | tags={s.get('task_tags')} | E={s.get('energy')}")

    if expected_tag:
        has_tag = any(expected_tag in (s.get("task_tags") or []) for s in songs)
        status = "✓" if has_tag else "✗"
        print(f"  {status} 期望标签 '{expected_tag}' {'命中' if has_tag else '未命中'}")

print("\n" + "=" * 70)
print("验证完成")
