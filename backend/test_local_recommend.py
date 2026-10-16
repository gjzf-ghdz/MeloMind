"""测试本地数据库选歌功能"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import recommender
from models import MusicStrategy

r = recommender.MusicRecommender()

def show(label, songs):
    print(f"=== {label} ===")
    for s in songs:
        kw = s.get("search_keyword", "")
        print(f"  {s['title']} - {s['artist']} | kw={kw} | E={s['energy']}")
    print()

# 测试1: 世界杯特殊名词
s1 = MusicStrategy(genres=['pop','rock'], energy_level=9, mood_target='festive',
                   instrumental_preferred=False, explanation='世界杯')
songs1 = r.recommend(s1, limit=5, task_type='entertainment-worldcup',
                     user_message='我在看世界杯')
show("世界杯第一次推荐", songs1)

# 测试2: 同样提示词再推荐一次（应不同）
songs2 = r.recommend(s1, limit=5, task_type='entertainment-worldcup',
                     user_message='我在看世界杯')
show("世界杯第二次推荐（应不同）", songs2)

# 测试3: 王者荣耀（别名）
s3 = MusicStrategy(genres=['electronic','rock'], energy_level=8,
                   mood_target='energetic', instrumental_preferred=False,
                   explanation='游戏')
songs3 = r.recommend(s3, limit=5, task_type='entertainment-gaming',
                     user_message='我在打王者荣耀')
show("王者荣耀测试（别名→游戏）", songs3)

# 测试4: 久石让（直接扫描）
s4 = MusicStrategy(genres=['classical','neo-classical'], energy_level=3,
                   mood_target='calm', instrumental_preferred=True,
                   explanation='钢琴')
songs4 = r.recommend(s4, limit=5, task_type='relax',
                     user_message='我想听久石让的钢琴曲')
show("久石让测试（直接扫描）", songs4)

# 测试5: 奥运会
s5 = MusicStrategy(genres=['pop','classical'], energy_level=7,
                   mood_target='hopeful', instrumental_preferred=False,
                   explanation='奥运')
songs5 = r.recommend(s5, limit=5, task_type='entertainment-olympics',
                     user_message='我在看奥运会')
show("奥运会测试", songs5)

# 验证随机性
ids1 = set(s['id'] for s in songs1)
ids2 = set(s['id'] for s in songs2)
overlap = ids1 & ids2
print(f"两次推荐重叠: {len(overlap)}/{len(ids1)} 首 (应有差异)")
