"""测试 LLM 引擎语言偏好识别 + 推荐器语言过滤"""
import json
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from llm_engine import LLMEngine
from models import Analysis, MusicStrategy
from recommender import MusicRecommender

ok = True

# [1] fallback 语言偏好识别
e = LLMEngine()
print(f"[0] api_key 配置: {'已配置' if e.api_key else '未配置(走关键词模式)'}")

cases = [
    ("复习时想听英文歌", "english", "study-exam"),
    ("跑步，来点中文歌", "chinese", "workout-running"),
    ("写代码焦虑", "no_preference", "coding-deep"),
    ("睡前听华语歌放松", "chinese", "relax-winddown"),
]
for msg, exp_lang, exp_task in cases:
    raw = e.analyze_user_state(msg)
    lang = raw.get("language_preference")
    task = raw.get("task_type")
    mark_lang = "OK " if lang == exp_lang else "FAIL"
    mark_task = "OK " if task == exp_task else "FAIL"
    if lang != exp_lang or task != exp_task:
        ok = False
    print(f"[1] {mark_lang} lang={lang} {mark_task} task={task} <- {msg!r}")

# [2] 推荐器语言过滤效果
if e.api_key:
    print("[2] LLM 已启用，跳过 fallback 推荐测试（会真实调用 API）")
else:
    eng = MusicRecommender()

    strategy = MusicStrategy(genres=[], energy_level=5, tempo_range="",
                             instrumental_preferred=False, mood_target="calm",
                             explanation="test")

    for pref in ("english", "chinese"):
        songs = eng.recommend(strategy, task_type="study-reading",
                              user_message="复习", language_preference=pref)
        titles = [s["title"] for s in songs]

        def lang_of(d):
            if d.get("instrumental"):
                return "instrumental"
            text = (d.get("title") or "") + " " + (d.get("artist") or "")
            return "chinese" if any("\u4e00" <= c <= "\u9fff" or "\u3040" <= c <= "\u30ff" for c in text) \
                else "english"

        hit = sum(1 for s in songs if lang_of(s) in (pref, "instrumental"))
        mark = "OK " if hit >= len(songs) * 0.7 else "FAIL"
        if hit < len(songs) * 0.7:
            ok = False
        print(f"[2] {mark} {pref}: {hit}/{len(songs)} 首符合语言预期")
        print(f"    样例: {titles[:4]}")

print("\n===", "ALL PASS" if ok else "SOME FAILED", "===")
sys.exit(0 if ok else 1)
