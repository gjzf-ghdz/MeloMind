# -*- coding: utf-8 -*-
"""离线验证特殊名词过滤器：泛化词必须剔除，专有名词必须保留"""
import sys, io, os
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "backend"))

from special_noun_detector import _is_generic_keyword, SpecialNounDetector

# (关键词, 是否泛化词)
CASES = [
    # —— 必须判定为泛化词（True）——
    ("健身", True), ("健身音乐", True), ("工作BGM", True), ("工作 bgm", True),
    ("学习专注音乐", True), ("睡眠轻音乐", True), ("跑步必备", True),
    ("放松治愈纯音乐", True), ("钢琴曲", True), ("纯音乐", True), ("轻音乐", True),
    ("lofi beats", True), ("study music", True), ("workout music", True),
    ("电子舞曲", True), ("摇滚", True), ("游戏", True), ("篮球", True),
    ("90年代经典歌曲", True), ("开车必备音乐", True), ("瑜伽 轻音乐", True),
    ("冥想 纯音乐", True), ("chill beats", True), ("sleep music", True),
    ("背景音乐", True), ("治愈钢琴", True), ("专注学习歌单", True),
    ("派对舞曲", True),  # 派对+舞曲都是泛化场景/类别词
    # —— 必须保留为专有名词（False）——
    ("周杰伦", False), ("Taylor Swift", False), ("林俊杰", False), ("邓紫棋", False),
    ("世界杯", False), ("世界杯主题曲", False), ("王者荣耀", False), ("原神", False),
    ("甄嬛传", False), ("流浪地球", False), ("久石让", False), ("Yiruma", False),
    ("Hans Zimmer 纯音乐 电影配乐", False), ("卡农", False), ("天空之城", False),
    ("鬼灭之刃", False), ("NBA", False), ("欧冠", False), ("waka waka", False),
    ("五月天", False), ("苏打绿", False), ("Eminem", False), ("BLACKPINK", False),
    ("健身环", False),  # 游戏名（Ring Fit）
    ("中国好声音", False),
]

fails = []
for kw, expect_generic in CASES:
    got = _is_generic_keyword(kw)
    tag = "泛化" if got else "专有"
    ok = (got == expect_generic)
    if not ok:
        fails.append((kw, expect_generic, got))
    print(f"{'✅' if ok else '❌'} {kw!r:40} -> {tag}")

print()
# 别名层（无 DB 也应工作）
d = SpecialNounDetector(local_db=None)
a1 = d.detect("我在打王者荣耀，来点歌", "gaming")
a2 = d.detect("我在健身，来点歌", "workout-strength")
a3 = d.detect("看甄嬛传的时候听什么", "entertainment-tv")
print(f"别名检测: 王者荣耀 -> {a1}")
print(f"别名检测: 健身(应空) -> {a2}")
print(f"别名检测: 甄嬛传 -> {a3}")

print()
if fails:
    print(f"❌ {len(fails)} 个用例不符:", fails)
    sys.exit(1)
print("✅ 全部用例符合预期")
