"""验证同一提示词每次推荐不同歌曲"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from recommender import MusicRecommender
from models import MusicStrategy

rec = MusicRecommender()
strategy = MusicStrategy(
    genres=["pop"], energy_level=5, mood_target="balanced",
    instrumental_preferred=False,
    explanation="我在学习", notes="我在学习",
)

print("同一提示词「我在学习」推荐 3 次：\n")
all_titles = []
for i in range(3):
    songs = rec.recommend(strategy, limit=8, task_type="study", user_message="我在学习")
    titles = [s["title"] for s in songs]
    all_titles.append(set(titles))
    print(f"  第{i+1}次: {', '.join(titles)}")

# 计算重叠率
overlap_1_2 = len(all_titles[0] & all_titles[1])
overlap_1_3 = len(all_titles[0] & all_titles[2])
overlap_2_3 = len(all_titles[1] & all_titles[2])
total_overlap = overlap_1_2 + overlap_1_3 + overlap_2_3
print(f"\n重叠歌曲数: {total_overlap} / 24 (越小越好)")
print(f"随机性: {'✓ 良好' if total_overlap <= 8 else '✗ 重复过多'}")
