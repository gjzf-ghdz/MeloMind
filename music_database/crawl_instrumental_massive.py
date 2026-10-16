"""
纯音乐专项大规模补充爬虫 — 覆盖器乐/场景/世界音乐/频率/作曲家
所有搜索结果强制标记为 instrumental=True，并写入对应的 search_keyword
"""
import json
import os
import sys
import time
import random

_BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend"))
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

from qqmusic_source import QQMusicSource
from models import Song, infer_instrument_type
from build_music_db import enrich_song_metadata

QQ = QQMusicSource()

# ============================================================
# 海量纯音乐搜索关键词 (240+)
# 搜索时每个关键词追加"纯音乐"/"instrumental"标记
# ============================================================
INSTRUMENTAL_KEYWORDS = [
    # ===== 1. 钢琴细分 =====
    "钢琴 独奏 经典", "钢琴 浪漫", "钢琴 安静", "钢琴 悲伤", "钢琴 治愈 安神",
    "钢琴 流行曲", "动漫钢琴", "钢琴 爵士", "钢琴 极简", "钢琴 四手联弹",
    "古典钢琴 奏鸣曲", "钢琴协奏曲", "前奏曲 钢琴", "赋格 钢琴",
    # ===== 2. 吉他细分 =====
    "指弹吉他 经典", "弗拉门戈吉他", "古典吉他 组曲", "吉他 独奏 轻音乐",
    "吉他 布鲁斯", "12弦吉他", "吉他 指弹 风", "木吉他 民谣", "夏威夷吉他",
    # ===== 3. 小提琴/弦乐 =====
    "小提琴 独奏 经典", "小提琴协奏曲", "小提琴 奏鸣曲", "大提琴 独奏",
    "大提琴 无伴奏组曲", "弦乐合奏 纯音乐", "中提琴 独奏", "低音提琴 独奏",
    "竖琴 独奏", "弦乐八重奏", "钢琴三重奏", "钢琴五重奏",
    # ===== 4. 中国民乐 =====
    "古筝 独奏 经典", "古筝 渔舟唱晚", "古琴 流水", "琵琶 独奏 十面埋伏",
    "二胡 独奏 二泉映月", "笛子 独奏 姑苏行", "唢呐 独奏 百鸟朝凤",
    "笙 独奏", "箫 独奏", "扬琴 独奏", "三弦 独奏", "板胡 独奏",
    "马头琴 独奏", "冬不拉 独奏", "葫芦丝 独奏", "巴乌 独奏",
    "京胡 独奏", "高胡 独奏", "月琴 独奏", "柳琴 独奏",
    "民乐合奏 春节序曲", "民乐合奏 金蛇狂舞", "广东音乐 步步高",
    "江南丝竹 紫竹调", "河北吹歌", "西安鼓乐",
    # ===== 5. 管弦乐/交响 =====
    "交响组曲", "交响诗", "序曲 管弦乐", "间奏曲 管弦乐",
    "进行曲 交响", "圆舞曲 交响", "夜曲 管弦乐", "交响叙事曲",
    "芭蕾舞剧 配乐 纯音乐", "歌剧 序曲", "轻歌剧 序曲",
    "铜管五重奏", "木管五重奏", "管风琴 独奏",
    # ===== 6. 管乐/木管/铜管 =====
    "萨克斯 独奏 纯音乐", "萨克斯 爵士 即兴", "小号 独奏", "长号 独奏",
    "圆号 独奏", "大号 独奏", "长笛 独奏", "单簧管 独奏",
    "双簧管 独奏", "巴松管 独奏", "短笛 独奏",
    # ===== 7. 手风琴/口琴 =====
    "手风琴 独奏", "巴扬 手风琴", "口琴 布鲁斯", "十孔口琴",
    "复音口琴", "半音阶口琴",
    # ===== 8. 打击乐 =====
    "定音鼓 协奏曲", "木琴 独奏", "马林巴 独奏", "钢片琴 独奏",
    "钟琴 独奏", "军鼓 独奏", "架子鼓 独奏",
    # ===== 9. 电子纯音乐 =====
    "Chillout 纯音乐", "Ambient 氛围电子 纯音乐", "Downtempo 缓拍 纯音乐",
    "Lo-Fi Hip Hop 纯音乐", "Chillwave 纯音乐", "Synthwave 合成器波 纯音乐",
    "蒸汽波 纯音乐", "Trance 纯音乐", "House 纯音乐 无 vocal",
    "Techno 纯音乐", "Drum & Bass 纯音乐", "Dubstep 纯音乐",
    "Future Bass 纯音乐", "Trap 纯音乐", "Hardstyle 纯音乐",
    "Progressive House 纯音乐", "Deep House 纯音乐",
    # ===== 10. 新世纪/自然/水疗 =====
    "自然纯音乐 森林", "自然纯音乐 海浪", "自然纯音乐 雨声",
    "自然纯音乐 鸟鸣", "自然纯音乐 流水", "自然纯音乐 雷电",
    "自然纯音乐 壁炉 柴火声", "自然纯音乐 咖啡馆 环境",
    "Spa 纯音乐 水疗", "Reiki 灵气 纯音乐",
    "Tibetan Singing Bowls 颂钵 纯音乐", "水晶钵 纯音乐",
    # ===== 11. 场景纯音乐 =====
    "学习 专注 纯音乐 无歌词", "深度工作 白噪音 纯音乐",
    "编程 纯音乐 环境", "阅读 纯音乐 安静",
    "考试 复习 纯音乐 阿尔法波", "记忆 巴洛克 纯音乐",
    "助眠 纯音乐 432Hz", "助眠 纯音乐 528Hz",
    "睡前 摇篮曲 纯音乐", "午睡 纯音乐 轻松",
    "瑜伽 热身 纯音乐", "瑜伽 拉伸 纯音乐",
    "太极 纯音乐", "八段锦 纯音乐",
    "普拉提 纯音乐", "禅修 纯音乐 木鱼 钟声",
    "茶道 纯音乐", "香道 纯音乐", "古琴 禅意",
    "咖啡 纯音乐 爵士 巴萨诺瓦", "餐厅 纯音乐 背景音乐",
    "商店 纯音乐 轻音乐", "商场 纯音乐 背景",
    "婚礼 纯音乐 钢琴曲", "婚礼 纯音乐 小提琴",
    "婚礼 纯音乐 管风琴", "生日 纯音乐 欢快",
    "圣诞 纯音乐 铃儿响叮当", "新年 纯音乐 喜气洋洋",
    "春节 纯音乐 喜洋洋", "中秋 纯音乐 月光",
    "情人节 纯音乐 浪漫", "生日歌 纯音乐",
    # ===== 12. 影视游戏动漫 纯音乐 =====
    "电影配乐 纯音乐 史诗", "电影配乐 纯音乐 悬疑",
    "电影配乐 纯音乐 爱情", "纪录片配乐 纯音乐 自然",
    "动漫OST 纯音乐 战斗", "动漫OST 纯音乐 悲伤",
    "动漫OST 纯音乐 日常", "Ghibli 久石让 纯音乐",
    "游戏BGM 纯音乐 RPG地图", "游戏BGM 纯音乐 战斗热血",
    "游戏BGM 纯音乐 解谜", "游戏BGM 纯音乐 结局",
    # ===== 13. 特殊频率/脑波 =====
    "432Hz 纯音乐 调音", "432Hz 冥想", "528Hz DNA修复 纯音乐",
    "396Hz 消除恐惧 纯音乐", "639Hz 人际关系 纯音乐",
    "741Hz 表达 纯音乐", "852Hz 直觉 纯音乐",
    "963Hz 松果体 激活 纯音乐",
    "双耳节拍 Alpha波 纯音乐", "双耳节拍 Theta波 纯音乐",
    "双耳节拍 Delta波 睡眠 纯音乐", "双耳节拍 Beta波 专注 纯音乐",
    "双耳节拍 Gamma波 超觉 纯音乐", "等时脉冲 冥想 纯音乐",
    # ===== 14. 爵士纯音乐 =====
    "爵士三重奏 钢琴 贝斯 鼓", "爵士四重奏 萨克斯",
    "冷爵士 纯音乐 Cool Jazz", "比波普 纯音乐 Bebop",
    "硬波普 纯音乐 Hard Bop", "Modal Jazz 调式爵士 纯音乐",
    "Free Jazz 自由爵士 纯音乐", "Fusion 融合爵士 纯音乐",
    "Smooth Jazz 柔顺爵士 纯音乐", "Acid Jazz 酸爵士 纯音乐",
    "Latin Jazz 拉丁爵士 纯音乐", "Bossa Nova 纯音乐 爵士 吉他",
    # ===== 15. 世界音乐纯音乐 =====
    "印度西塔琴 纯音乐", "印度塔布拉鼓 纯音乐",
    "印度班苏里笛子 纯音乐", "印度萨罗德琴 纯音乐",
    "阿拉伯乌德琴 纯音乐", "波斯 Santoor 扬琴 纯音乐",
    "土耳其 卡龙琴 纯音乐", "希腊 Bouzouki 布祖基 纯音乐",
    "爱尔兰 锡哨 纯音乐", "爱尔兰 风笛 纯音乐",
    "苏格兰 高地风笛 纯音乐", "西班牙 弗拉门戈 吉他 纯音乐",
    "阿根廷 探戈 纯音乐 班多钮", "巴西 桑巴 纯音乐 打击乐",
    "古巴 伦巴 纯音乐", "墨西哥 马里亚奇 纯音乐",
    "美国 蓝草 纯音乐 班卓琴", "夏威夷 尤克里里 纯音乐",
    "非洲 鼓乐 纯音乐 金贝鼓", "非洲 Kalimba 卡林巴琴 拇指琴",
    "日本 尺八 纯音乐", "日本 三味线 纯音乐",
    "日本 筝 纯音乐", "日本 太鼓 纯音乐",
    "韩国 伽倻琴 纯音乐", "越南 独弦琴 纯音乐",
    "蒙古 呼麦 纯音乐 长调",
    # ===== 16. 作曲家/演奏家 纯音乐作品 =====
    "Hans Zimmer 纯音乐 电影配乐", "Ennio Morricone 纯音乐 电影配乐",
    "John Williams 纯音乐 电影配乐", "Joe Hisaishi 久石让 纯音乐",
    "Ryuichi Sakamoto 坂本龙一 纯音乐", "Yiruma 李闰珉 纯音乐",
    "Ludovico Einaudi 纯音乐钢琴", "Brian Crain 纯音乐钢琴",
    "George Winston 纯音乐钢琴 四季",
    "Kevin Kern 纯音乐钢琴", "David Lanz 纯音乐钢琴",
    "2Cellos 提琴双杰 纯音乐大提琴", "The Piano Guys 纯音乐",
    "Lindsey Stirling 纯音乐小提琴 电子",
    "David Garrett 纯音乐小提琴 摇滚",
    # ===== 17. 摇滚/金属纯音乐 =====
    "摇滚 纯音乐 吉他solo", "金属 纯音乐 吉他riff",
    "后摇 Post-Rock 纯音乐", "迷幻摇滚 纯音乐",
    "前卫摇滚 纯音乐", "激流金属 纯音乐",
    "交响金属 纯音乐", "哥特金属 纯音乐",
    # ===== 18. 宗教/仪式纯音乐 =====
    "格里高利圣咏 纯音乐 合唱伴奏", "佛教 梵呗 纯音乐 诵经 背景",
    "道教 纯音乐 仙乐", "教堂 管风琴 前奏曲 弥撒",
]

# 每个搜索词附带附加后缀（轮询使用）
INSTRUMENTAL_SUFFIXES = [
    " 纯音乐", " instrumental", " 无歌词",
    " 轻音乐", " 背景音", " BGM",
    " 钢琴版", " 吉他版", " 小提琴版",
    " 伴奏", " 纯享版", " 翻奏",
]


def load_db(db_path):
    if not os.path.exists(db_path):
        return {"songs": [], "total_songs": 0}
    with open(db_path, "r", encoding="utf-8") as f:
        return json.load(f)


def merge_songs(db, new_songs):
    if "_songs_dict" not in db:
        db["_songs_dict"] = {s["id"]: s for s in db.get("songs", []) if s.get("id")}
    before = len(db["_songs_dict"])
    for s in new_songs:
        if s["id"] not in db["_songs_dict"]:
            db["_songs_dict"][s["id"]] = s
    return len(db["_songs_dict"]) - before


def save_db(db, db_path):
    db["songs"] = list(db["_songs_dict"].values())
    db["total_songs"] = len(db["songs"])
    db["version"] = 2
    if "_songs_dict" in db:
        del db["_songs_dict"]
    with open(db_path, "w", encoding="utf-8") as f:
        json.dump(db, f, ensure_ascii=False, indent=2)


def search_with_instrumental_suffix(base_kw, limit=50):
    """对每个关键词，轮询多个 instrumental 后缀进行搜索，强制标记 instrumental=True"""
    all_songs = []
    seen_ids = set()
    suffixes_used = set()

    # 先用 base_kw + "纯音乐"
    for suf in [" 纯音乐", " instrumental", " 轻音乐", " BGM", " 无歌词", " 钢琴版"]:
        if len(all_songs) >= limit * 2:
            break
        search_kw = f"{base_kw}{suf}"
        try:
            results = QQ.search(search_kw, limit=max(30, limit // 2))
        except Exception as e:
            print(f"  [搜索失败] {search_kw}: {e}")
            continue
        for song in results:
            if not song.id or song.id in seen_ids:
                continue
            seen_ids.add(song.id)
            suffixes_used.add(suf)
            enriched = enrich_song_metadata(song, base_kw)
            # 强制纯音乐标记
            enriched["instrumental"] = True
            # 重新推断乐器类型
            enriched["instrument_type"] = infer_instrument_type(enriched.get("genre", "pop"))
            all_songs.append(enriched)
            if len(all_songs) >= limit * 2:
                break
        time.sleep(0.5 + random.uniform(0.2, 0.4))

    # 如果太少，再搜 base_kw 本身 + 纯音乐筛选（标题包含"纯音乐/钢琴/吉他"等词）
    if len(all_songs) < limit:
        try:
            results = QQ.search(base_kw, limit=limit * 2)
        except Exception as e:
            print(f"  [搜索失败] base {base_kw}: {e}")
            results = []
        instrumental_hints = ["纯音乐", "纯享版", "钢琴版", "吉他版", "小提琴版",
                             "instrumental", "伴奏", "背景音", "轻音乐",
                             "钢琴曲", "吉他曲", "笛", "箫", "古筝", "二胡",
                             "琵琶", "BGM", "纯奏"]
        for song in results:
            if not song.id or song.id in seen_ids:
                continue
            title_lower = (song.title or "").lower()
            # 仅保留标题中暗示纯音乐的
            if any(h.lower() in title_lower for h in instrumental_hints):
                seen_ids.add(song.id)
                enriched = enrich_song_metadata(song, base_kw)
                enriched["instrumental"] = True
                enriched["instrument_type"] = infer_instrument_type(enriched.get("genre", "pop"))
                all_songs.append(enriched)

    return all_songs


def main():
    import argparse
    parser = argparse.ArgumentParser(description="纯音乐专项大规模补充爬取")
    parser.add_argument("--per", type=int, default=40, help="每个关键词目标数量")
    parser.add_argument("--max", type=int, default=None, help="最多处理多少关键词")
    parser.add_argument("--output", default=None, help="数据库路径")
    parser.add_argument("--list", action="store_true")
    args = parser.parse_args()

    db_path = args.output or os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "music_database.json")

    if args.list:
        print(f"共 {len(INSTRUMENTAL_KEYWORDS)} 个纯音乐专项关键词：")
        for i, kw in enumerate(INSTRUMENTAL_KEYWORDS, 1):
            print(f"  {i:>3}. {kw}")
        return

    db = load_db(db_path)
    db["_songs_dict"] = {s["id"]: s for s in db.get("songs", []) if s.get("id")}
    initial_total = len(db["_songs_dict"])
    initial_inst = sum(1 for s in db["_songs_dict"].values() if s.get("instrumental"))

    print(f"初始数据库: {initial_total} 首 (纯音乐 {initial_inst} 首)")
    print(f"每个关键词目标: {args.per} 首 纯音乐")
    print(f"关键词总数: {len(INSTRUMENTAL_KEYWORDS)}")
    print("=" * 60)

    kws = INSTRUMENTAL_KEYWORDS
    if args.max:
        kws = kws[:args.max]

    total_added = 0
    total_inst_added = 0

    for i, kw in enumerate(kws):
        print(f"  [{i+1}/{len(kws)}] {kw}... ", end="", flush=True)
        songs = search_with_instrumental_suffix(kw, limit=args.per)
        added = merge_songs(db, songs)
        # 统计新增纯音乐数（都是 instrumental=True）
        total_added += added
        total_inst_added += added
        print(f"+{added} 首 (累计新增 {total_added})")
        time.sleep(0.8 + random.uniform(0.3, 0.6))

    # 保存
    final_inst = sum(1 for s in db["_songs_dict"].values() if s.get("instrumental"))
    final_total = len(db["_songs_dict"])

    print(f"\n{'='*60}")
    print(f"爬取完成!")
    print(f"  初始: 总计 {initial_total} 首 / 纯音乐 {initial_inst} 首 ({initial_inst/initial_total*100:.1f}%)")
    print(f"  新增: {total_added} 首 (全部纯音乐)")
    print(f"  最终: 总计 {final_total} 首 / 纯音乐 {final_inst} 首 ({final_inst/final_total*100:.1f}%)")
    print(f"{'='*60}")
    save_db(db, db_path)
    print(f"数据库已保存: {db_path}")


if __name__ == "__main__":
    main()
