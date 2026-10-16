# -*- coding: utf-8 -*-
"""端到端验证：语言偏好过滤修复（english 必须推英文歌，chinese 必须推中文歌）"""
import sys, os, re
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from recommender import MusicRecommender
from models import MusicStrategy

CJK = re.compile(r"[\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")

def lang_of(d):
    if d.get("instrumental"):
        return "instrumental"
    text = f"{d.get('title') or ''} {d.get('artist') or ''}"
    return "chinese" if CJK.search(text) else "english"

eng = MusicRecommender()
print(f"曲库已加载\n")

def strategy():
    return MusicStrategy(genres=[], energy_level=5, tempo_range="",
                         instrumental_preferred=False, mood_target="calm",
                         explanation="verify")

cases = [
    # (描述, 用户消息, task_type, 语言偏好)
    ("用户原话复现: 我喜欢听英文歌", "我喜欢听英文歌", "study-reading", "english"),
    ("工作+英文歌", "工作了，来点英文歌", "work-focus", "english"),
    ("运动+英文歌", "跑步健身，听英文歌", "workout-running", "english"),
    ("放松+英文歌", "放松一下，想听英文歌", "relax-winddown", "english"),
    ("游戏+英文歌", "打游戏来点英文歌", "entertainment-gaming", "english"),
    ("中文偏好对照", "我想听中文歌放松", "relax-winddown", "chinese"),
    ("中文歌+学习", "复习高数，来点中文歌", "study-exam", "chinese"),
    ("无语言偏好(不硬滤)", "随便推荐点音乐", "general", "no_preference"),
]

ok = True
for desc, msg, task, lang_pref in cases:
    hits = {"english": 0, "chinese": 0, "instrumental": 0}
    samples = []
    for _ in range(3):  # 每个场景跑3次，检验随机稳定性
        songs = eng.recommend(strategy(), task_type=task, user_message=msg,
                              language_preference=lang_pref,
                              language_explicit=lang_pref != "no_preference",
                              limit=8)
        for s in songs:
            hits[lang_of(s)] += 1
        samples = songs
    total = sum(hits.values())
    if lang_pref in ("english", "chinese"):
        good = hits[lang_pref]
        bad = hits["chinese" if lang_pref == "english" else "english"]
        rate = good / max(1, total)
        mark = "OK  " if rate >= 0.85 else "FAIL"
        if rate < 0.85:
            ok = False
        print(f"[{mark}] {desc}")
        print(f"      符合={good} 不符合={bad} 纯音乐={hits['instrumental']} "
              f"命中率={rate:.0%}")
    else:
        print(f"[INFO] {desc}: 中文={hits['chinese']} 英文={hits['english']} "
              f"纯音乐={hits['instrumental']}")
    for s in samples[:4]:
        print(f"      样例: [{lang_of(s):11s}] 《{s.get('title')}》 - {s.get('artist')}")
    print()

print("===", "ALL PASS" if ok else "SOME FAILED", "===")
sys.exit(0 if ok else 1)
