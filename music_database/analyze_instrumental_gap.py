"""分析当前纯音乐覆盖缺口"""
import json
import os
from collections import Counter

db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "music_database.json")
with open(db_path, "r", encoding="utf-8") as f:
    data = json.load(f)
songs = data["songs"]
total = len(songs)

inst = [s for s in songs if s.get("instrumental")]
print(f"总歌曲数: {total}")
print(f"纯音乐数: {len(inst)}  ({len(inst)/total*100:.1f}%)")
print(f"人声歌曲数: {total - len(inst)}  ({(total-len(inst))/total*100:.1f}%)")
print()

# search_keyword 分类（纯音乐）
kw_inst = Counter()
for s in inst:
    kw = s.get("search_keyword", "")
    if kw:
        kw_inst[kw] += 1
print(f"纯音乐 search_keyword 分类数: {len(kw_inst)}")
print("纯音乐关键词 Top 50:")
for kw, c in kw_inst.most_common(50):
    print(f"  {kw:<30} {c:>4} 首")
print()

# 器乐类型分布
itype = Counter(s.get("instrument_type", "未知") for s in inst)
print("纯音乐 主要乐器分布:")
for t, c in itype.most_common():
    print(f"  {t:<10} {c:>5} 首")
print()

# 纯音乐风格分布
genre_cn = {"classical":"古典","neo-classical":"新古典","minimalist":"极简","ambient":"轻音乐",
            "electronic":"电子","folk":"民谣","indie":"独立","rock":"摇滚","pop":"流行",
            "jazz":"爵士","r&b":"R&B","hip-hop":"嘻哈"}
g_count = Counter(s.get("genre","unknown") for s in inst)
print("纯音乐 风格分布:")
for g, c in g_count.most_common():
    cn = genre_cn.get(g, g)
    print(f"  {cn:<10} {c:>5} 首  ({c/len(inst)*100:.1f}%)")
print()

# 已覆盖和待覆盖的器乐细分关键词
covered_kws = set(kw_inst.keys())
target_instrumental_kws = {
    # 钢琴细分
    "钢琴 独奏 经典", "钢琴 浪漫", "钢琴 安静", "钢琴 悲伤", "钢琴 治愈 安神",
    "钢琴 流行曲", "动漫钢琴", "钢琴 爵士", "钢琴 极简", "钢琴 四手联弹",
    "古典钢琴 奏鸣曲", "钢琴协奏曲", "前奏曲 钢琴", "赋格 钢琴",
    # 吉他细分
    "指弹吉他 经典", "弗拉门戈吉他", "古典吉他 组曲", "吉他 独奏 轻音乐",
    "吉他 布鲁斯", "12弦吉他", "吉他 指弹 风", "木吉他 民谣", "夏威夷吉他",
    # 小提琴/弦乐
    "小提琴 独奏 经典", "小提琴协奏曲", "小提琴 奏鸣曲", "大提琴 独奏",
    "大提琴 无伴奏组曲", "弦乐合奏 纯音乐", "中提琴 独奏", "低音提琴 独奏",
    "竖琴 独奏", "弦乐八重奏", "钢琴三重奏", "钢琴五重奏",
    # 民乐
    "古筝 独奏 经典", "古筝 渔舟唱晚", "古琴 流水", "琵琶 独奏 十面埋伏",
    "二胡 独奏 二泉映月", "笛子 独奏 姑苏行", "唢呐 独奏 百鸟朝凤",
    "笙 独奏", "箫 独奏", "扬琴 独奏", "三弦 独奏", "板胡 独奏",
    "马头琴 独奏", "冬不拉 独奏", "葫芦丝 独奏", "巴乌 独奏",
    "京胡 独奏", "高胡 独奏", "月琴 独奏", "柳琴 独奏",
    "民乐合奏 春节序曲", "民乐合奏 金蛇狂舞", "广东音乐 步步高",
    "江南丝竹 紫竹调", "河北吹歌", "西安鼓乐",
    # 管弦乐/交响
    "交响组曲", "交响诗", "序曲 管弦乐", "间奏曲 管弦乐",
    "进行曲 交响", "圆舞曲 交响", "夜曲 管弦乐", "交响叙事曲",
    "芭蕾舞剧 配乐 纯音乐", "歌剧 序曲", "轻歌剧 序曲",
    "铜管五重奏", "木管五重奏", "管风琴 独奏",
    # 管乐
    "萨克斯 独奏", "萨克斯 爵士 即兴", "小号 独奏", "长号 独奏",
    "圆号 独奏", "大号 独奏", "长笛 独奏", "单簧管 独奏",
    "双簧管 独奏", "巴松管 独奏", "短笛 独奏",
    # 手风琴/口琴
    "手风琴 独奏", "巴扬 手风琴", "口琴 布鲁斯", "十孔口琴",
    "复音口琴", "半音阶口琴",
    # 打击乐
    "定音鼓 协奏曲", "木琴 独奏", "马林巴 独奏", "钢片琴 独奏",
    "钟琴 独奏", "军鼓 独奏", "架子鼓 独奏",
    # 电子纯音乐
    "Chillout 纯音乐", "Ambient 氛围电子 纯音乐", "Downtempo 缓拍 纯音乐",
    "Lo-Fi Hip Hop 纯音乐", "Chillwave 纯音乐", "Synthwave 合成器波 纯音乐",
    "蒸汽波 纯音乐 纯 instrumental", "Trance 纯音乐", "House 纯音乐 无 vocal",
    "Techno 纯音乐", "Drum & Bass 纯音乐", "Dubstep 纯音乐",
    "Future Bass 纯音乐", "Trap 纯音乐", "Hardstyle 纯音乐",
    "Progressive House 纯音乐", "Deep House 纯音乐",
    # 新世纪/自然
    "自然纯音乐 森林", "自然纯音乐 海浪", "自然纯音乐 雨声",
    "自然纯音乐 鸟鸣", "自然纯音乐 流水", "自然纯音乐 雷电",
    "自然纯音乐 壁炉 柴火声", "自然纯音乐 咖啡馆 环境",
    "Spa 纯音乐 水疗", "Reiki 灵气 纯音乐",
    "Tibetan Singing Bowls 颂钵 纯音乐", "水晶钵 纯音乐",
    # 场景专用纯音乐
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
    "婚礼 纯音乐 管风琴", "葬礼 纯音乐 哀乐 进行曲",
    "生日 纯音乐 欢快", "圣诞 纯音乐 铃儿响叮当",
    "新年 纯音乐 喜气洋洋", "春节 纯音乐 喜洋洋",
    "中秋 纯音乐 月光", "情人节 纯音乐 浪漫",
    # 影视/游戏/动漫 纯音乐
    "电影配乐 纯音乐 史诗", "电影配乐 纯音乐 悬疑",
    "电影配乐 纯音乐 爱情", "纪录片配乐 纯音乐 自然",
    "动漫OST 纯音乐 战斗", "动漫OST 纯音乐 悲伤",
    "动漫OST 纯音乐 日常", "Ghibli 久石让 纯音乐",
    "游戏BGM 纯音乐 RPG地图", "游戏BGM 纯音乐 战斗热血",
    "游戏BGM 纯音乐 解谜", "游戏BGM 纯音乐 结局",
    # 特殊调谐/频率
    "432Hz 纯音乐 调音", "432Hz 冥想", "528Hz DNA修复 纯音乐",
    "396Hz 消除恐惧 纯音乐", "639Hz 人际关系 纯音乐",
    "741Hz 表达 纯音乐", "852Hz 直觉 纯音乐",
    "963Hz 松果体 激活 纯音乐",
    "双耳节拍 Alpha波 纯音乐", "双耳节拍 Theta波 纯音乐",
    "双耳节拍 Delta波 睡眠 纯音乐", "双耳节拍 Beta波 专注 纯音乐",
    "双耳节拍 Gamma波 超觉 纯音乐",
    "等时脉冲 冥想 纯音乐",
    # 爵士纯音乐
    "爵士三重奏 钢琴 贝斯 鼓", "爵士四重奏 萨克斯",
    "冷爵士 纯音乐 Cool Jazz", "比波普 纯音乐 Bebop",
    "硬波普 纯音乐 Hard Bop", "Modal Jazz 调式爵士 纯音乐",
    "Free Jazz 自由爵士 纯音乐", "Fusion 融合爵士 纯音乐",
    "Smooth Jazz 柔顺爵士 纯音乐", "Acid Jazz 酸爵士 纯音乐",
    "Latin Jazz 拉丁爵士 纯音乐", "Bossa Nova 纯音乐 爵士 吉他",
    # 世界音乐纯音乐
    "印度西塔琴 纯音乐", "印度塔布拉鼓 纯音乐",
    "印度笛子班苏里 纯音乐", "印度萨罗德琴 纯音乐",
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
    # 电影/作曲家 作品
    "Hans Zimmer 纯音乐 电影配乐", "Ennio Morricone 纯音乐 电影配乐",
    "John Williams 纯音乐 电影配乐", "Joe Hisaishi 久石让 纯音乐",
    "Ryuichi Sakamoto 坂本龙一 纯音乐", "Yiruma 李闰珉 纯音乐",
    "Ludovico Einaudi 纯音乐钢琴", "Brian Crain 纯音乐钢琴",
    "George Winston 纯音乐钢琴 四季",
    "Kevin Kern 纯音乐钢琴", "David Lanz 纯音乐钢琴",
    "2Cellos 提琴双杰 纯音乐大提琴", "The Piano Guys 纯音乐",
    "Lindsey Stirling 纯音乐小提琴 电子",
    "David Garrett 纯音乐小提琴 摇滚",
}
missing = target_instrumental_kws - covered_kws
print(f"目标纯音乐关键词: {len(target_instrumental_kws)}")
print(f"已覆盖: {len(target_instrumental_kws & covered_kws)}")
print(f"待补充: {len(missing)} 个关键词")
print("待补充关键词示例 (前50):")
for kw in sorted(list(missing))[:50]:
    print(f"  - {kw}")
