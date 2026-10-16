# -*- coding: utf-8 -*-
"""
全库重新判定 人声/纯音乐 标签。

背景：QQ音乐源对所有搜索结果硬编码 instrumental=True，
旧版 build_music_db 仅对"世界杯/派对/舞曲"少数关键词改回人声，
导致歌手名搜索（Taylor Swift/周杰伦等）抓到的人声歌曲被误标为纯音乐。

本脚本基于统一函数 detect_instrumental(title, album, search_keyword)
对全库重新标注，并同步刷新推荐理由 reason。
"""
import json
import os
import sys

# 复用 build_music_db 中的统一判定与理由生成
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from build_music_db import detect_instrumental, generate_reason

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       "music_database.json")


def main():
    print(f"读取: {DB_PATH}")
    with open(DB_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
    songs = data.get("songs", [])
    print(f"共 {len(songs)} 首歌曲待重新判定\n")

    before_inst = sum(1 for s in songs if s.get("instrumental"))
    changed_to_vocal = 0
    changed_to_inst = 0
    no_kw = 0

    for s in songs:
        title = s.get("title", "") or ""
        album = s.get("album", "") or ""
        kw = s.get("search_keyword", "") or ""
        if not kw:
            no_kw += 1
        old = bool(s.get("instrumental"))
        new = detect_instrumental(title, album, kw)
        if new != old:
            if new:
                changed_to_inst += 1
            else:
                changed_to_vocal += 1
            s["instrumental"] = new
            # 同步刷新推荐理由（reason 内含"纯音乐/人声"字样）
            try:
                mood = (s.get("mood_tags") or ["balanced"])[0]
                s["reason"] = generate_reason(
                    title, s.get("artist", ""), s.get("genre", "pop"),
                    int(s.get("energy", 5) or 5), mood, new,
                    int(s.get("duration_sec", 240) or 240), kw or "推荐")
            except Exception:
                pass

    after_inst = sum(1 for s in songs if s.get("instrumental"))

    print("=" * 50)
    print(f"判定前 纯音乐: {before_inst} ({100*before_inst//len(songs)}%)")
    print(f"判定后 纯音乐: {after_inst} ({100*after_inst//len(songs)}%)")
    print(f"  纯音乐→人声: {changed_to_vocal}")
    print(f"  人声→纯音乐: {changed_to_inst}")
    if no_kw:
        print(f"  (无 search_keyword 字段: {no_kw} 首，按标题信号判定)")

    # 人声歌曲语言分布（判定后）
    cn = en = 0
    for s in songs:
        if s.get("instrumental"):
            continue
        text = f"{s.get('title','')}{s.get('artist','')}{s.get('album','')}"
        has_cjk = any('\u4e00' <= ch <= '\u9fff' or '\u3040' <= ch <= '\u30ff'
                      or '\uac00' <= ch <= '\ud7af' for ch in text)
        if has_cjk:
            cn += 1
        else:
            en += 1
    print(f"\n人声歌曲: {cn + en} 首")
    print(f"  含中日韩字符: {cn}")
    print(f"  拉丁字符(英文等): {en}")

    print(f"\n写回: {DB_PATH}")
    with open(DB_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
    print("完成")


if __name__ == "__main__":
    main()
