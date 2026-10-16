"""测试：游戏关键词扩充效果 + 最长关键词优先匹配"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.chdir(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

# 1. JSON 语法校验
cfg = json.load(open("music_database/event_keywords.json", encoding="utf-8"))
print("[1] JSON OK, alias_map size:", len(cfg["user_alias_map"]))

# 2. LLM 识别
from llm_engine import LLMEngine

e = LLMEngine()
cases = [
    ("我在打三角洲行动", "entertainment-gaming"),
    ("和朋友开黑打排位", "entertainment-gaming"),
    ("星穹铁道新版本抽卡", "entertainment-gaming"),
    ("晚上无畏契约上分", "entertainment-gaming"),
    ("通关艾尔登法环DLC", "entertainment-gaming"),
    ("周末在家玩幻兽帕鲁", "entertainment-gaming"),
    ("新卡池歪了非酋一天", "entertainment-gaming"),
    ("刺客信条影发售了", "entertainment-gaming"),
    ("地铁跑酷冲分", "entertainment-gaming"),
    ("写代码焦虑", "coding-deep"),
    ("看世界杯", "entertainment-worldcup"),
    ("复习考试", "study-exam"),
    ("去健身房撸铁", "workout-strength"),
]
ok = True
for msg, expect in cases:
    task, _, _ = e._match_task(msg.lower())
    mark = "OK " if task == expect else "FAIL"
    if task != expect:
        ok = False
    print(f"[2] {mark} {msg!r} -> {task} (expect {expect})")

# 3. 特殊名词检测
from local_music_db import LocalMusicDatabase
from special_noun_detector import SpecialNounDetector

db = LocalMusicDatabase()
det = SpecialNounDetector(db)
for msg in ["我在打三角洲行动", "和朋友开黑", "打王者荣耀", "周末开荒幻兽帕鲁", "写报告"]:
    hits = det.detect(msg)
    print(f"[3] {msg!r} -> hits: {hits[:5]}")

# 4. gaming tag 歌曲数
ids = db._task_index.get("gaming", [])
print("[4] gaming tag songs:", len(ids))

print("\nALL PASS" if ok else "\nSOME FAILED")
