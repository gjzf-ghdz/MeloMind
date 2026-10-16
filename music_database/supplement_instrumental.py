"""
补充爬取纯音乐歌曲 - 扩充音乐数据库中的纯音乐覆盖

运行方式：python supplement_instrumental.py
输出：在现有 music_database.json 基础上追加新歌曲

策略：
- 使用大量纯音乐相关关键词批量搜索
- 与现有数据库去重（按 songmid）
- 新歌曲自动推断元数据并合并
"""
import json
import os
import sys
import time
import random

# 确保能导入 backend 模块
_BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend"))
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if _SCRIPT_DIR not in sys.path:
    sys.path.insert(0, _SCRIPT_DIR)

from qqmusic_source import QQMusicSource
from models import Song, infer_instrument_type
from build_music_db import enrich_song_metadata


# ============================================================
# 纯音乐专项搜索关键词（覆盖各种器乐、场景、风格）
# ============================================================
INSTRUMENTAL_KEYWORDS = [
    # 1. 钢琴类（细分）
    "钢琴纯音乐", "钢琴独奏", "钢琴轻音乐", "钢琴伴奏", "钢琴曲 纯音乐",
    "新古典钢琴", "治愈钢琴", "浪漫钢琴", "简约钢琴", "钢琴 协奏",

    # 2. 吉他类（细分）
    "吉他纯音乐", "木吉他", "指弹吉他", "古典吉他", "民谣吉他 纯音乐",
    "原声吉他", "不插电", "acoustic",

    # 3. 弦乐类
    "小提琴", "小提琴纯音乐", "弦乐四重奏", "大提琴", "弦乐合奏",
    "弦乐 纯音乐",

    # 4. 管弦乐/交响
    "交响乐", "管弦乐", "纯音乐 交响", "史诗 纯音乐",
    "电影配乐", "影视 纯音乐", "OST 纯音乐",

    # 5. 民乐/国风
    "古筝", "古琴", "笛子", "二胡", "琵琶",
    "中国风 纯音乐", "国风 纯音乐", "民乐",

    # 6. 电子/氛围
    "电子纯音乐", "氛围音乐", "环境音乐", "electronic instrumental",
    "chill out", "lounge", "downtempo", "new age",

    # 7. 自然/白噪音
    "自然音效", "森林 鸟鸣", "海浪 纯音乐", "雨声 白噪音",
    "咖啡馆 环境音", "夜晚 虫鸣",

    # 8. 场景纯音乐
    "学习 纯音乐", "工作 背景音", "睡眠 纯音乐", "冥想 纯音乐",
    "瑜伽 轻音乐", "阅读 背景音", "发呆 纯音乐",

    # 9. 著名器乐演奏家/作曲家
    "久石让", "坂本龙一", "Yiruma", "理查德克莱德曼", "马克西姆",
    "李闰珉", "巫启贤 钢琴", "Brian Crain", "Ludovico Einaudi",

    # 10. 经典纯音乐作品
    "卡农", "致爱丽丝", "月光奏鸣曲", "悲怆奏鸣曲", "摇篮曲",
    "梦中的婚礼", "水边的阿狄丽娜", "童年", "天空之城",
    "summer 久石让", "river flows in you",

    # 11. 情绪纯音乐
    "治愈 纯音乐", "伤感 钢琴", "励志 纯音乐", "温暖 纯音乐",
    "热血 纯音乐", "史诗 纯音乐", "梦幻 纯音乐",

    # 12. 节日/季节纯音乐
    "圣诞 纯音乐", "新年 纯音乐", "春天 纯音乐", "秋天 纯音乐",
    "夜晚 纯音乐", "黄昏 纯音乐", "清晨 纯音乐",
]


def load_existing_db(db_path: str) -> dict:
    """加载现有数据库"""
    if not os.path.exists(db_path):
        print(f"数据库文件不存在，将创建新数据库: {db_path}")
        return {"version": 2, "source": "QQ Music (y.qq.com)",
                "total_songs": 0, "stats": {}, "songs": []}
    with open(db_path, "r", encoding="utf-8") as f:
        return json.load(f)


def supplement(db_path: str, keywords: list, per_keyword: int = 50):
    """补充爬取纯音乐歌曲"""
    data = load_existing_db(db_path)
    existing_songs = {s["id"]: s for s in data.get("songs", []) if "id" in s}
    print(f"现有数据库: {len(existing_songs)} 首歌曲")
    print(f"本次将搜索 {len(keywords)} 个纯音乐关键词，每个 {per_keyword} 首")
    print("=" * 60)

    qq = QQMusicSource()
    new_count = 0
    dup_count = 0
    fail_count = 0

    for i, kw in enumerate(keywords):
        print(f"[{i+1}/{len(keywords)}] 搜索: {kw} ... ", end="", flush=True)
        try:
            songs = qq.search(kw, limit=per_keyword)
            kw_new = 0
            for song in songs:
                if not song.id:
                    continue
                if song.id in existing_songs:
                    dup_count += 1
                    continue
                enriched = enrich_song_metadata(song, kw)
                # 强制标记为纯音乐（因为是纯音乐专项搜索）
                enriched["instrumental"] = True
                # 重新推断乐器类型
                genre = enriched.get("genre", "pop")
                enriched["instrument_type"] = infer_instrument_type(genre)
                existing_songs[song.id] = enriched
                kw_new += 1
                new_count += 1
            print(f"+{kw_new} 首 (累计新增 {new_count})")
        except Exception as e:
            fail_count += 1
            print(f"失败: {e}")

        # 节流
        time.sleep(1.0 + random.uniform(0.2, 0.5))

    print("\n" + "=" * 60)
    print(f"爬取完成！")
    print(f"  新增歌曲: {new_count} 首")
    print(f"  重复跳过: {dup_count} 首")
    print(f"  失败关键词: {fail_count} 个")
    print(f"  数据库总量: {len(existing_songs)} 首")

    # 保存
    data["songs"] = list(existing_songs.values())
    data["total_songs"] = len(existing_songs)
    data["version"] = 2
    data["supplemented"] = True
    data["source"] = "QQ Music (y.qq.com)"

    with open(db_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"\n数据库已保存: {db_path}")


def main():
    import argparse
    parser = argparse.ArgumentParser(description="补充爬取纯音乐歌曲")
    parser.add_argument("--output", "-o", default=None, help="数据库文件路径")
    parser.add_argument("--per", "-p", type=int, default=50, help="每个关键词搜索数量")
    parser.add_argument("--max", "-m", type=int, default=None,
                        help="最多处理多少个关键词（默认全部）")
    parser.add_argument("--list", "-l", action="store_true",
                        help="仅列出关键词不执行")
    args = parser.parse_args()

    db_path = args.output or os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "music_database.json")

    if args.list:
        print(f"共 {len(INSTRUMENTAL_KEYWORDS)} 个纯音乐搜索关键词：")
        for i, kw in enumerate(INSTRUMENTAL_KEYWORDS, 1):
            print(f"  {i:>3}. {kw}")
        return

    kws = INSTRUMENTAL_KEYWORDS
    if args.max:
        kws = kws[:args.max]

    supplement(db_path, kws, per_keyword=args.per)


if __name__ == "__main__":
    main()
