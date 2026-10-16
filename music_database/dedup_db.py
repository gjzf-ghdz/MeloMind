"""检查并清理音乐数据库中的重复歌曲"""
import json
import os
import sys
from collections import defaultdict


def find_duplicates(songs):
    """多维度查重：songmid、标题+歌手、标题"""
    by_id = defaultdict(list)
    by_title_artist = defaultdict(list)
    by_title = defaultdict(list)

    for i, s in enumerate(songs):
        sid = (s.get("id") or "").strip()
        title = (s.get("title") or "").strip()
        artist = (s.get("artist") or "").strip()

        if sid:
            by_id[sid].append(i)
        if title and artist:
            by_title_artist[f"{title}|{artist}"].append(i)
        if title:
            by_title[title.lower()].append(i)

    dups = []
    seen_indices = set()

    # 1. songmid 完全相同
    for key, indices in by_id.items():
        if len(indices) > 1:
            for idx in indices[1:]:  # 保留第一个
                if idx not in seen_indices:
                    dups.append((idx, f"songmid重复: {key}"))
                    seen_indices.add(idx)

    # 2. 标题+歌手完全相同
    for key, indices in by_title_artist.items():
        if len(indices) > 1:
            for idx in indices[1:]:
                if idx not in seen_indices:
                    dups.append((idx, f"标题+歌手重复: {key}"))
                    seen_indices.add(idx)

    # 3. 标题相同（忽略大小写）
    for key, indices in by_title.items():
        if len(indices) > 1:
            # 只标记标题完全相同的为疑似重复，保留第一个
            for idx in indices[1:]:
                if idx not in seen_indices:
                    dups.append((idx, f"标题重复: {key}"))
                    seen_indices.add(idx)

    return dups, seen_indices


def main():
    db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           "music_database.json")
    if not os.path.exists(db_path):
        print(f"数据库不存在: {db_path}")
        return

    with open(db_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    songs = data.get("songs", [])
    print(f"{'='*60}")
    print(f"数据库查重报告")
    print(f"{'='*60}")
    print(f"原始歌曲数: {len(songs)}")
    print()

    dups, dup_indices = find_duplicates(songs)
    print(f"发现重复: {len(dups)} 首")
    print()

    if dups:
        print("重复详情（前20条）:")
        for idx, reason in dups[:20]:
            s = songs[idx]
            print(f"  [{idx}] {s.get('title','')} - {s.get('artist','')} ({reason})")
        if len(dups) > 20:
            print(f"  ... 还有 {len(dups)-20} 条")

    # 去重
    keep_indices = [i for i in range(len(songs)) if i not in dup_indices]
    deduped = [songs[i] for i in keep_indices]

    print(f"\n{'='*60}")
    print(f"去重后歌曲数: {len(deduped)}")
    print(f"删除: {len(songs) - len(deduped)} 首")
    print(f"{'='*60}")

    # 保存
    data["songs"] = deduped
    data["total_songs"] = len(deduped)
    data["deduplicated"] = True

    with open(db_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"\n数据库已保存: {db_path}")

    # 去重后统计
    print(f"\n去重后统计:")
    genre_dist = defaultdict(int)
    for s in deduped:
        g = s.get("genre", "unknown")
        genre_dist[g] += 1
    genre_cn = {"classical": "古典", "pop": "流行", "rock": "摇滚",
                "electronic": "电子", "folk": "民谣", "r&b": "R&B",
                "hip-hop": "嘻哈", "jazz": "爵士", "ambient": "轻音乐",
                "neo-classical": "新古典", "minimalist": "极简", "indie": "独立"}
    for g, c in sorted(genre_dist.items(), key=lambda x: -x[1]):
        cn = genre_cn.get(g, g)
        print(f"  {cn:<10} {c:>5} 首")


if __name__ == "__main__":
    main()
