"""LLM 对话理解引擎 - 细粒度任务状态 + 情绪状态识别
支持任何 OpenAI 兼容 API（智谱 GLM / DeepSeek / 通义等），默认走关键词匹配 fallback
"""
import json
import os
import re
import urllib.request
from typing import Optional, Any


VALID_LANG_PREFS = ("chinese", "english", "japanese", "korean", "other",
                    "no_preference")

# 智谱 GLM OpenAI 兼容端点；其他服务商改 base_url 即可
DEFAULT_BASE_URL = "https://open.bigmodel.cn/api/paas/v4"
DEFAULT_MODEL = "glm-4-flash"


SYSTEM_PROMPT = """你是一个自适应音乐推荐系统的 AI 分析师。你的核心目标是：从用户的一句话里，**精准地**识别出他们正在做什么、心情如何。音乐推荐的好坏完全取决于你这一步分类准不准。

## 最重要的规则（务必遵守）

🚫 禁止输出 `neutral-ordinary`。情绪栏不允许出现"平常 / 无特定情绪"这类空答案。
❌ 绝对不要轻易用 `general`（日常事务）作为任务。几乎所有人类活动都能归类到下面的大类，`general` 只留给"完全不知道用户在干嘛"的情况。
✅ **只要用户没明说情绪，就必须从任务状态、时段、场景里推出一个最合理的情绪**，写清推断依据。比如"加班"→疲惫，"赶PPT"→焦虑，"跑步"→亢奋，"冥想"→宁静，"写代码"→专注，"早上出门"→清爽有期待。
✅ 当用户只说了心情、没说在干嘛——**优先给情绪分细子类**，不要只停留在 happy/anxious/sad。比如"紧张"→anxious-tension，"脑子累"→tired-mental，"好激动"→happy-excited。

## 允许的任务大类与子类（覆盖了绝大多数人类场景）

- coding: coding-deep(深度编码) coding-debug(调试排错) coding-review(代码审查) coding-learn(学习新技术)
- work: work-office(办公室工作) work-ppt(文档汇报/做PPT) work-meeting(会议讨论) work-overtime(加班赶工) work-creative(设计创意)
- writing: writing-creative(创意写作) writing-doc(文档写作)
- study: study-exam(备考) study-vocab(记忆背诵) study-reading(阅读) study-practice(刷题写作业)
- workout: workout-running(跑步) workout-strength(力量训练) workout-yoga(瑜伽拉伸) workout-basketball(打篮球) workout-football(踢足球) workout-walk(散步走路)
- commute: commute-driving(开车) commute-transit(地铁/公交/高铁/飞机/打车)
- relax: relax-meditate(冥想打坐) relax-winddown(休息放松) relax-sleep(睡眠/准备睡/失眠) relax-bath(洗澡按摩)
- creative: creative-brainstorm(头脑风暴) creative-design(创意设计/作图剪辑)
- entertainment: entertainment-worldcup(看世界杯) entertainment-olympics(看奥运会) entertainment-nba(看NBA篮球赛) entertainment-football(看足球赛事) entertainment-tv(追剧/看电影/刷短视频) entertainment-gaming(玩游戏) entertainment-party(派对K歌) entertainment-celebration(生日庆祝) entertainment-social(约会聚餐) entertainment-meal(吃饭/做饭/外卖) entertainment-housework(做家务)

⚠️ 不同的事件级任务必须推荐完全不同的歌曲。例如：
- "看世界杯" → 世界杯主题曲、球迷燃曲（生命之杯、Waka Waka）
- "看NBA" → 篮球音乐、灌篮高手BGM
- "加班" → 疲惫需要提神
- "开车" → 需要保持警觉的音乐
- "散步" → 轻松悠闲

## 允许的情绪大类与子类

- happy: happy-delighted(愉悦) happy-confident(自信) happy-excited(亢奋) happy-festive(欢庆) happy-celebratory(狂欢) happy-social(社交愉悦)
- anxious: anxious-deadline(截止压力/赶工) anxious-exam(考前焦虑/面试) anxious-tension(紧张/心慌/烦躁/焦虑) anxious-overwhelmed(崩溃/压垮/思绪混乱)
- tired: tired-mental(精神疲惫/脑子累) tired-physical(身体疲劳) tired-sleepy(困倦/想睡)
- sad: sad-depressed(情绪低落/难过) sad-frustrated(挫败/搞砸) sad-lonely(孤独/一个人)
- calm: calm-focused(专注/投入) calm-relaxed(放松/惬意) calm-serene(宁静/平和)
- neutral: neutral-steady(心态平稳) neutral-bored(无聊/没意思) neutral-contemplative(发呆/沉思/emo)
- ⚠️ 只有用户**明确**说"还行 / 一般 / 就那样"时才用 neutral-steady；用户没提情绪时要由任务推断，不要用它

## 少样本参考（模糊输入也要精准分类）

用户输入 "我在加班" →
  task: work-overtime(加班赶工)
  emotion: tired-mental(加班疲惫)

用户输入 "赶明天要交的PPT" →
  task: work-ppt(文档汇报)
  emotion: anxious-deadline(截止压力)

用户输入 "躺在床上睡不着" →
  task: relax-sleep(睡眠)
  emotion: tired-mental(身心疲惫又失眠) 或 calm-serene(平静)

用户输入 "周末在家刷抖音" →
  task: entertainment-tv(刷短视频)
  emotion: neutral-relaxed(放松) 或 neutral-bored(有点无聊)

用户输入 "走路回家" →
  task: workout-walk(散步) 或 commute-transit
  emotion: calm-relaxed(放松)

用户输入 "今天心情还ok，就是有点累" →
  task: work-office / study-reading (如果上下文有)
  emotion: tired-physical(身体累) + intensity 4-5

用户输入 "好想开黑啊" →
  task: entertainment-gaming(玩游戏)
  emotion: happy-excited(期待亢奋)

## language_preference

- "chinese"：点名要中文歌 / 华语歌 / 粤语歌
- "english"：点名要英文歌 / 欧美歌 / 外语歌
- "japanese"：点名要日语歌 / 日文歌
- "korean"：点名要韩语歌 / 韩文歌
- "other"：点名要小语种（法语 / 西班牙语 / 俄语等）
- "no_preference"：未提及语言
注意否定式："别推中文歌" → english，"别推英文" → chinese。
注意：用户说"纯音乐 / 轻音乐 / 背景音乐"是曲风诉求，不是语言诉求，
language_preference 仍填 "no_preference"，改由 music_strategy.instrumental_preferred 表达。

## 返回 JSON 字段

{
  "task_type": "大类-子类 或 大类",
  "task_detail": "任务的具体中文描述",
  "task_demand": "该任务对音乐的需求",
  "emotion": "大类-子类 或 大类（禁止 neutral-ordinary）",
  "emotion_detail": "情绪的具体中文描述（用户没明说时，写清是由什么推断出来的）",
  "emotion_intensity": 1-10,
  "emotion_source": "explicit(用户明说) / task_inferred(由任务推断) / context_inferred(由时段场景推断)",
  "need_regulation": true/false,
  "regulation_goal": "具体的调节目标",
  "language_preference": "chinese / english / japanese / korean / other / no_preference",
  "music_strategy": {
    "genres": ["推荐风格1"],
    "energy_level": 1-10,
    "tempo_range": "描述节奏范围",
    "instrumental_preferred": true/false,
    "mood_target": "目标情绪",
    "explanation": "策略解释"
  }
}

只返回 JSON，不要其他内容。"""


class LLMEngine:
    def __init__(self, api_key: Optional[str] = None, base_url: Optional[str] = None):
        cfg = self._load_config()
        self.api_key = api_key or cfg.get("api_key") or os.getenv("OPENAI_API_KEY") or ""
        self.base_url = (base_url or cfg.get("base_url")
                         or os.getenv("OPENAI_BASE_URL") or DEFAULT_BASE_URL).rstrip("/")
        self.model = cfg.get("model") or os.getenv("OPENAI_MODEL") or DEFAULT_MODEL
        self.last_mode = "keyword"  # 最近一次分析的模式：llm / keyword（日志用）

    def _load_config(self) -> dict:
        """优先读取 backend/llm_config.json，其次环境变量"""
        cfg_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "llm_config.json")
        if os.path.exists(cfg_path):
            try:
                with open(cfg_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                print(f"[LLMEngine] 配置读取失败: {e}")
        return {}

    def analyze_user_state(self, user_message: str) -> dict:
        if not self.api_key:
            self.last_mode = "keyword"
            return self._mock_analyze(user_message)
        try:
            result = self._call_llm(user_message)
            self.last_mode = "llm"
            return result
        except Exception as e:
            print(f"[LLMEngine] LLM 调用失败，回退关键词匹配: {e}")
            self.last_mode = "keyword"
            return self._mock_analyze(user_message)

    def _call_llm(self, user_message: str) -> dict:
        """调用 OpenAI 兼容 chat/completions 接口（urllib，无第三方依赖）"""
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_message},
            ],
            "temperature": 0.4,
            "max_tokens": 1200,
        }
        last_err = None
        for attempt in range(2):  # 偶发 JSON 不合法时重试一次
            req = urllib.request.Request(
                self.base_url + "/chat/completions",
                data=json.dumps(payload).encode("utf-8"),
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {self.api_key}",
                },
                method="POST",
            )
            try:
                with urllib.request.urlopen(req, timeout=30) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                content = data["choices"][0]["message"]["content"]
                result = self._extract_json(content)
                return self._validate(result, user_message)
            except (json.JSONDecodeError, KeyError, IndexError) as e:
                last_err = e  # 内容问题：重试
        raise last_err

    @staticmethod
    def _extract_json(text: str) -> dict:
        """从模型回复中提取 JSON（容忍 markdown 代码块包裹）"""
        text = text.strip()
        m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
        if m:
            text = m.group(1)
        return json.loads(text)

    def _validate(self, result: dict, user_message: str) -> dict:
        """校验 LLM 输出，非法字段回退到关键词匹配结果"""
        base = self._mock_analyze(user_message)
        if not isinstance(result, dict):
            return base
        # task_type / emotion 必须存在且含允许的大类，否则整个回退
        allowed_tasks = ("coding", "writing", "study", "workout", "commute",
                         "relax", "creative", "entertainment", "general")
        allowed_emotions = ("happy", "anxious", "tired", "sad", "calm", "neutral")
        task = str(result.get("task_type", "")).strip()
        emo = str(result.get("emotion", "")).strip()
        # 规范化为「大类-子类」两段格式（LLM 偶发输出三段）
        parts = task.split("-")
        if len(parts) > 2:
            task = "-".join(parts[:2])
            result["task_type"] = task
        if task.split("-")[0] not in allowed_tasks or \
                emo.split("-")[0] not in allowed_emotions:
            return base
        # 情绪兜底：LLM 偶尔仍会给出 neutral-ordinary 或光秃秃的 neutral，
        # 这种"无特定情绪"会被前端直接显示出来，用任务/上下文推断结果替换掉
        if emo in ("neutral-ordinary", "neutral") or emo.startswith("neutral-ordinary"):
            result["emotion"] = base["emotion"]
            result["emotion_detail"] = base["emotion_detail"]
            result["emotion_intensity"] = base["emotion_intensity"]
            result["emotion_source"] = base["emotion_source"]
        else:
            src = str(result.get("emotion_source") or "").strip()
            result["emotion_source"] = src if src in (
                "explicit", "task_inferred", "context_inferred") else "explicit"
        lang = str(result.get("language_preference", "no_preference")).strip().lower()
        result["language_preference"] = lang if lang in VALID_LANG_PREFS \
            else base["language_preference"]
        # music_strategy 缺字段时用 mock 补齐
        ms = result.get("music_strategy")
        if not isinstance(ms, dict) or not ms.get("genres"):
            result["music_strategy"] = base["music_strategy"]
        return result

    # ================================================================
    # 以下为关键词匹配 fallback（LLM 未配置/调用失败时使用）
    # ================================================================
    def _detect_language_pref(self, msg: str) -> str:
        """从消息中识别语言偏好（fallback 用），支持否定式（如'别推中文歌'→english）"""
        lang_kw = (
            ("中文歌", "chinese"), ("华语歌", "chinese"), ("国语歌", "chinese"),
            ("粤语歌", "chinese"), ("台语歌", "chinese"), ("闽南语", "chinese"),
            ("英文歌", "english"), ("英语歌", "english"), ("欧美", "english"),
            ("外文歌", "english"), ("外语歌", "english"),
            ("日语歌", "japanese"), ("日文歌", "japanese"), ("日本歌", "japanese"),
            ("日语", "japanese"), ("日文", "japanese"),
            ("韩语歌", "korean"), ("韩文歌", "korean"), ("韩国歌", "korean"),
            ("韩语", "korean"), ("韩文", "korean"),
            ("小语种", "other"), ("法语", "other"), ("德语", "other"),
            ("西班牙语", "other"), ("俄语", "other"), ("意大利语", "other"),
            ("葡萄牙语", "other"), ("泰语", "other"), ("其它语言", "other"),
            ("其他语言", "other"),
            ("华语", "chinese"), ("国语", "chinese"), ("中文", "chinese"),
            ("英文", "english"), ("英语", "english"))
        negations = ("别", "不要", "不想", "少推", "少点", "非", "拒绝")
        low = msg.lower()
        for kw, lang in lang_kw:
            idx = low.find(kw)
            if idx >= 0:
                window = low[max(0, idx - 4):idx]
                if any(n in window for n in negations):
                    return "english" if lang == "chinese" else "chinese"
                return lang
        return "no_preference"


    # ================================================================
    # 细粒度状态词典：关键词 -> (大类, 子类, 中文名, 强度)
    # ================================================================
    EMOTION_GROUPS = {
        "happy": {
            "delighted": (["愉悦", "心情好", "开心", "高兴", "快乐", "爽", "棒", "美好", "delighted", "good mood", "不错", "挺好的", "美滋滋", "开心死了", "太好啦", "乐呵呵"], "愉悦", 7),
            "confident": (["自信", "有把握", "胸有成竹", "势在必得", "能行", "稳了", "没问题", "confident"], "自信", 7),
            "excited": (["兴奋", "亢奋", "激动", "超开心", "燃起来", "嗨", "激动人心", "excited", "thrilled", "好激动", "激动不已", "太燃了"], "亢奋", 8),
            "festive": (["欢庆", "庆祝", "狂欢", "party", "festive", "过节", "喜气洋洋"], "欢庆", 8),
            "celebratory": (["庆祝", "生日快乐", "恭喜", "周年", "纪念", "celebratory", "新婚", "乔迁", "升职", "成功了", "获奖"], "狂欢", 8),
            "social": (["约会", "浪漫", "甜蜜", "心动", "social", "喜欢", "暗恋", "恋爱"], "社交愉悦", 7),
        },
        "anxious": {
            "deadline": (["deadline", "截止", "赶进度", "赶工", "要交", "催", "ddl", "时间不够", "赶不出来", "来不及了", "时间紧", "马上到点"], "截止压力", 8),
            "exam": (["考前", "考试", "测验", "答辩", "面试", "exam", "要面试了", "答辩紧张", "明天考试", "就要考了"], "考前焦虑", 8),
            "tension": (["紧张", "紧绷", "不安", "心烦", "烦", "焦虑", "nervous", "tense", "anxious", "慌", "心慌", "坐立不安", "焦头烂额", "手忙脚乱", "心乱", "忐忑", "七上八下", "提心吊胆", "闹心", "烦躁", "焦躁"], "紧张", 7),
            "overwhelmed": (["思绪乱", "压垮", "崩溃", "乱", "心烦意乱", "overwhelmed", "信息过载", "头大", "脑子转不动", "烧脑", "费脑子", "撑不住了", "要爆炸了", "心力交瘁"], "思绪混乱", 9),
        },
        "tired": {
            "mental": (["用脑过度", "脑子累", "脑子好累", "脑累", "精神累", "心累", "脑力", "mental fatigue", "burnout", "头大", "想不出来", "累脑子", "费脑", "身心俱疲", "精疲力竭", "脑子懵", "累", "有点累", "有点疲惫", "疲惫", "乏力"], "精神疲惫", 7),
            "physical": (["身体累", "体力", "肌肉酸", "腰酸背痛", "physical", "浑身无力", "腿酸", "胳膊酸", "全身累", "累坏了", "体力不支"], "身体疲劳", 7),
            "sleepy": (["困", "想睡", "没睡好", "熬夜", "哈欠", "sleepy", "drowsy", "打瞌睡", "眼皮沉", "睁不开眼", "好困", "困死了", "起不来", "没精神", "萎靡"], "困倦", 6),
        },
        "sad": {
            "depressed": (["低落", "沮丧", "难过", "伤心", "抑郁", "down", "depressed", "心情不好", "闷闷不乐", "愁", "叹气", "唉声叹气", "惆怅", "闷闷的"], "情绪低落", 7),
            "frustrated": (["挫败", "受打击", "失败", "搞砸", "frustrated", "无成就感", "白忙活", "白干了", "白费力气", "努力白费", "心塞", "堵得慌"], "挫败", 7),
            "lonely": (["孤独", "一个人", "没人陪", "lonely", "孤单", "寂寞", "孤零零", "形单影只"], "孤独", 6),
        },
        "calm": {
            "focused": (["专注", "投入", "心流", "集中", "focus", "flow", "concentrated", "沉静", "认真", "沉下心"], "专注", 4),
            "relaxed": (["放松", "轻松", "chill", "relaxed", "解压", "舒坦", "舒服", "自在", "惬意"], "放松", 3),
            "serene": (["宁静", "平和", "平静", "安详", "serene", "peaceful", "安稳", "恬淡", "与世无争"], "安宁", 3),
        },
        "neutral": {
            "bored": (["无聊", "乏味", "提不起劲", "没意思", "bored", "闷", "没劲", "好无聊啊", "闲得慌", "空虚", "百无聊赖", "没劲儿", "没状态"], "无聊", 4),
            # 用户明确说"还行/一般/就那样"时的中性子类（"平常"不再作为情绪输出）
            "steady": (["平常", "一般", "还行", "ordinary", "正常", "还ok", "不咸不淡"], "平稳", 5),
            "relaxed": (["放松观影", "休闲", "看剧", "惬意"], "放松观影", 4),
            "contemplative": (["发呆", "沉思", "想事情", "想想", "琢磨", "回味", "怀念", "忆旧", "感伤", "emo", "文艺"], "沉思", 3),
        },
    }

    TASK_GROUPS = {
        "coding": {
            "deep": (["写代码", "编程", "开发", "coding", "code", "写功能", "写新功能", "实现", "写算法", "重构", "重构代码"], "深度编码"),
            "debug": (["调试", "bug", "报错", "修复", "排错", "debug", "error", "修bug", "打log", "排查"], "调试排错"),
            "review": (["审查", "code review", "review", "看代码", "评审", "CR"], "代码审查"),
            "learn": (["学新技术", "学框架", "看文档", "学习编程", "新语言", "教程", "啃文档", "读源码"], "学习新技术"),
        },
        "writing": {
            "creative": (["写小说", "创作", "写文案", "创意写作", "写故事", "写公众号", "写博客", "写专栏"], "创意写作"),
            "doc": (["写文档", "写报告", "写方案", "写论文", "文档", "报告", "方案", "写总结", "写材料", "写说明书"], "文档写作"),
        },
        "work": {
            "office": (["上班", "工作", "干活", "做事", "办公", "坐班", "工位", "职场"], "办公室工作"),
            "ppt": (["做PPT", "做ppt", "写PPT", "PPT", "ppt", "做汇报", "做方案", "做表格", "Excel", "写邮件", "回邮件", "整理文件", "赶PPT"], "文档与汇报"),
            "meeting": (["开会", "会议", "讨论", "头脑风暴会", "研讨会", "汇报会", "评审会"], "会议讨论"),
            "overtime": (["加班", "熬夜加班", "赶项目", "赶deadline", "通宵加班"], "加班赶工"),
            "creative": (["做设计", "设计图", "UI设计", "平面设计", "产品设计", "做海报", "修图", "P图", "剪视频", "剪辑"], "创意设计"),
        },
        "study": {
            "exam": (["备考", "考试", "复习", "冲刺", "考研", "期末", "期中", "高考", "中考", "模考"], "备考冲刺"),
            "vocab": (["背单词", "记忆", "背诵", "记知识点", "vocab", "背书", "背课文", "背概念"], "记忆背诵"),
            "reading": (["阅读", "看书", "读书", "read", "reading", "看教材", "看讲义", "看论文"], "阅读"),
            "practice": (["刷题", "练习", "做题", "习题", "practice", "写作业", "做作业", "家庭作业"], "刷题练习"),
        },
        "workout": {
            "running": (["跑步", "跑了", "慢跑", "晨跑", "五公里", "十公里", "run", "running", "夜跑", "健跑"], "跑步"),
            "strength": (["力量", "健身", "撸铁", "举铁", "重量训练", "gym", "strength", "器械", "卧推", "深蹲", "硬拉"], "力量训练"),
            "yoga": (["瑜伽", "拉伸", "普拉提", "yoga", "stretch", "柔韧", "拉筋"], "瑜伽拉伸"),
            "basketball": (["打篮球", "投篮", "上篮", "三分球", "运球", "打野球"], "打篮球"),
            "football": (["踢足球", "踢球", "射门", "传球", "跑位"], "踢足球"),
            "walk": (["散步", "走路", "健走", "遛弯", "步行"], "走路散步"),
        },
        "commute": {
            "driving": (["开车", "驾驶", "drive", "driving", "驾车", "通勤开车", "自驾"], "开车通勤"),
            "transit": (["地铁", "公交", "乘车", "通勤", "上班路上", "transit", "坐公交", "坐地铁", "坐高铁", "坐火车", "坐飞机", "高铁上", "飞机上", "等车", "打车", "坐出租"], "公共交通"),
        },
        "relax": {
            "meditate": (["冥想", "打坐", "meditate", "mindfulness", "正念", "禅修"], "冥想"),
            "winddown": (["休息", "放松", "睡前", "躺平", "relax", "休息一下", "歇会儿", "歇会", "眯一会儿", "闭目养神"], "放松休息"),
            "sleep": (["睡觉", "睡了", "准备睡", "上床", "入睡", "失眠", "睡不着", "打个盹", "午睡", "午休", "小憩"], "睡眠"),
            "bath": (["洗澡", "泡澡", "冲澡", "SPA", "汗蒸", "按摩", "推拿"], "洗浴放松"),
        },
        "creative": {
            "brainstorm": (["头脑风暴", "想点子", "策划", "brainstorm", "创意", "灵感枯竭", "想创意", "构思"], "头脑风暴"),
            "design": (["设计", "作图", "UI", "海报", "design", "排版", "平面", "原型", "线框"], "创意设计"),
        },
        "entertainment": {
            "worldcup": (["世界杯", "看世界杯", "世界杯决赛", "world cup", "看球赛 世界杯"], "看世界杯"),
            "olympics": (["奥运", "奥运会", "看奥运", "冬奥", "奥运会比赛"], "看奥运会"),
            "nba": (["nba", "看nba", "cba", "篮球赛", "灌篮高手", "看篮球", "看篮球赛"], "看NBA篮球赛"),
            "football": (["看球", "球赛", "看比赛", "比赛", "决赛", "冠军", "加油", "助威", "进球", "得分", "射门", "看直播", "欧冠", "英超", "西甲", "意甲", "德甲", "欧洲杯", "中超", "f1", "全运会", "决赛圈", "足球", "看足球"], "看足球赛事"),
            "tv": (["看电视", "追剧", "看剧", "刷剧", "看综艺", "看节目", "看电影", "看纪录片", "刷短视频", "刷抖音", "刷B站", "刷b站", "看动漫", "看番"], "看影视刷手机"),
            "gaming": (["打游戏", "玩游戏", "电竞", "lol", "王者荣耀", "吃鸡", "原神", "黑神话",
                        "三角洲行动", "三角洲", "暗区突围", "穿越火线", "使命召唤", "战地", "无畏契约",
                        "apex", "pubg", "绝地求生", "彩虹六号", "逆战", "steam", "switch", "ps5", "xbox",
                        "开黑", "上分", "排位", "峡谷", "五杀", "超神", "双排",
                        "dota", "刀塔", "云顶之弈", "金铲铲", "和平精英", "永劫无间", "蛋仔派对",
                        "星穹铁道", "崩铁", "绝区零", "鸣潮", "塞尔达", "艾尔登法环", "只狼",
                        "荒野大镖客", "赛博朋克", "巫师", "怪物猎人", "宝可梦", "pokemon", "梦幻西游",
                        "光遇", "蛋仔", "文明6", "泰拉瑞亚", "我的世界", "迷你世界", "糖豆人", "双人成行",
                        "ps4", "幻兽帕鲁", "帕鲁", "双影奇境", "小丑牌", "宇宙机器人", "米塔",
                        "潜水员戴夫", "燕云十六声", "渊虚之羽", "剑星", "龙之信条", "浪人崛起",
                        "无限暖暖", "重返未来1999", "旷野之息", "喷射战士", "火焰纹章", "异度之刃",
                        "鬼泣", "猎天使魔女", "真三国无双", "暗黑4", "魔兽",
                        "刺客信条", "孤岛惊魂", "战神", "地平线", "对马岛之魂", "命运2",
                        "全境封锁", "泰坦陨落", "看门狗", "质量效应", "龙腾世纪",
                        "黎明杀机", "消逝的光芒", "恐鬼症", "心灵杀手",
                        "死亡细胞", "空洞骑士", "以撒的结合", "挺进地牢", "元气骑士",
                        "吸血鬼幸存者", "土豆兄弟", "月圆之夜", "哈迪斯", "胡闹厨房",
                        "红色警戒", "红警", "帝国时代", "魔兽争霸", "模拟人生", "天际线",
                        "僵尸毁灭工程", "监狱建筑师",
                        "街头霸王", "街霸", "拳皇", "铁拳", "真人快打", "大乱斗",
                        "剑灵", "冒险岛", "龙之谷", "热血传奇", "永恒之塔",
                        "荒野乱斗", "部落冲突", "皇室战争", "球球大作战", "地铁跑酷",
                        "神庙逃亡", "水果忍者", "愤怒的小鸟", "植物大战僵尸", "猫和老鼠",
                        "香肠派对", "明日之后", "黎明觉醒", "荒野行动", "忍者必须死",
                        "三国杀", "三国志战略版", "率土之滨", "剑与远征", "一念逍遥",
                        "最强蜗牛", "不思议迷宫",
                        "恋与制作人", "光与夜之恋", "未定事件簿", "代号鸢", "如鸢",
                        "战双帕弥什", "碧蓝航线", "少女前线", "深空之眼", "尘白禁区", "白荆回廊",
                        "音游", "节奏大师", "phigros", "arcaea", "喵斯快跑", "太鼓达人", "舞萌",
                        "抽卡", "欧皇", "非酋", "打本", "团本", "公会", "通关", "段位",
                        "空投", "毒圈", "大逃杀", "落地成盒", "单机", "手游", "端游", "网游",
                        "主机游戏"], "玩游戏"),
            "party": (["派对", "party", "舞会", "狂欢", "聚会", "蹦迪", "蹦迪", "ktv", "KTV", "卡拉OK", "K歌"], "派对狂欢"),
            "celebration": (["庆祝", "生日", "周年", "纪念日", "结婚", "庆典", "满月酒", "毕业", "乔迁"], "庆祝时刻"),
            "social": (["约会", "聚餐", "聚会", "社交", "相亲", "跟朋友出去玩", "和朋友吃饭", "家人聚餐", "家庭聚餐"], "社交约会"),
            "meal": (["吃饭", "吃晚饭", "吃午饭", "吃早饭", "吃宵夜", "吃夜宵", "外卖", "点外卖", "做饭", "烹饪", "炒菜", "煮东西", "吃火锅", "吃烧烤", "吃烤肉", "吃快餐", "吃西餐", "吃日料", "吃面", "吃饺子", "吃汉堡"], "用餐"),
            "housework": (["做家务", "打扫卫生", "擦地", "拖地", "洗衣", "晾衣服", "整理房间", "收拾屋子", "做饭", "洗碗", "倒垃圾", "浇花", "遛狗", "喂猫", "打扫", "收拾"], "家务生活"),
        },
    }

    def _match_emotion(self, msg: str) -> Optional[tuple]:
        """返回 (emotion, emotion_detail, intensity)；用户没明说情绪时返回 None

        不再兜底成 neutral-ordinary —— 那种"无特定情绪"的空答案会一直显示在
        "情绪"栏里，改为交给任务状态/时段场景推断（见 _mock_analyze）。
        """
        # 先大类，再子类
        for group, subs in self.EMOTION_GROUPS.items():
            for sub, (keywords, detail, intensity) in subs.items():
                if any(w in msg for w in keywords):
                    return f"{group}-{sub}", detail, intensity
        return None

    def _match_task(self, msg: str) -> tuple:
        """返回 (task_type, task_detail, task_demand)；最长（最具体）关键词优先"""
        best = None  # (kw_len, group, sub, detail)
        for group, subs in self.TASK_GROUPS.items():
            for sub, (keywords, detail) in subs.items():
                for w in keywords:
                    if w in msg and (best is None or len(w) > best[0]):
                        best = (len(w), group, sub, detail)
        if best:
            _, group, sub, detail = best
            return f"{group}-{sub}", detail, self._task_demand(group, sub)
        return "general", "日常事务", "根据情绪匹配音乐"

    def _task_demand(self, group: str, sub: str) -> str:
        demands = {
            "coding": "需要深度专注，减少歌词干扰",
            "work": "需要保持警觉或提神，具体按子类区分",
            "writing": "需要创造性思维，适度背景音乐",
            "study": "需要安静或轻音乐辅助专注",
            "workout": "需要高能量音乐驱动运动节奏",
            "commute": "需要愉悦、节奏感的音乐伴随",
            "relax": "需要舒缓音乐帮助身心放松",
            "creative": "需要开阔思维、激发灵感的音乐",
            "entertainment": "需要高能量、带动气氛的音乐增强快感，事件级需匹配主题曲",
        }
        return demands.get(group, "根据情绪匹配音乐")

    # 任务 → 情绪推断表（情绪为平常时由任务补情绪，覆盖全部任务子类）
    TASK_EMOTION_MAP = {
        # === 编程 ===
        "coding-deep": ("calm-focused", "深度专注", 4),
        "coding-debug": ("anxious-tension", "调试紧张", 7),
        "coding-review": ("calm-focused", "认真审查", 4),
        "coding-learn": ("calm-focused", "学习专注", 4),
        # === 写作 ===
        "writing-creative": ("calm-focused", "创作专注", 5),
        "writing-doc": ("calm-focused", "文档专注", 4),
        # === 工作 ===
        "work-office": ("calm-focused", "办公专注", 4),
        "work-ppt": ("anxious-deadline", "赶PPT焦虑", 7),
        "work-meeting": ("calm-focused", "会议专注", 5),
        "work-overtime": ("tired-mental", "加班疲惫", 7),
        "work-creative": ("calm-focused", "创意工作", 5),
        # === 学习 ===
        "study-exam": ("anxious-exam", "考前焦虑", 8),
        "study-vocab": ("tired-mental", "记忆耗费", 6),
        "study-reading": ("calm-relaxed", "放松阅读", 3),
        "study-practice": ("neutral-bored", "刷题无聊", 5),
        # === 运动 ===
        "workout-running": ("happy-excited", "运动亢奋", 8),
        "workout-strength": ("happy-confident", "自信满满", 8),
        "workout-yoga": ("calm-relaxed", "柔韧舒展", 3),
        "workout-basketball": ("happy-excited", "竞技亢奋", 8),
        "workout-football": ("happy-excited", "竞技亢奋", 8),
        "workout-walk": ("calm-relaxed", "漫步放松", 3),
        # === 通勤 ===
        "commute-driving": ("anxious-tension", "驾驶紧张", 6),
        "commute-transit": ("neutral-bored", "通勤无聊", 4),
        # === 放松 ===
        "relax-meditate": ("calm-serene", "宁静冥想", 3),
        "relax-winddown": ("tired-mental", "疲惫待休", 6),
        "relax-sleep": ("tired-sleepy", "困倦想睡", 6),
        "relax-bath": ("calm-relaxed", "洗浴放松", 3),
        # === 创意 ===
        "creative-brainstorm": ("neutral-bored", "灵感枯竭", 5),
        "creative-design": ("calm-focused", "设计专注", 5),
        # === 娱乐赛事 ===
        "entertainment-worldcup": ("happy-festive", "世界杯亢奋", 9),
        "entertainment-olympics": ("happy-festive", "奥运亢奋", 8),
        "entertainment-nba": ("happy-festive", "观赛亢奋", 8),
        "entertainment-football": ("happy-festive", "观赛亢奋", 8),
        "entertainment-tv": ("neutral-relaxed", "放松观影", 4),
        "entertainment-gaming": ("happy-excited", "游戏亢奋", 8),
        "entertainment-party": ("happy-celebratory", "庆祝狂欢", 8),
        "entertainment-celebration": ("happy-celebratory", "庆祝时刻", 8),
        "entertainment-social": ("happy-social", "愉悦社交", 7),
        "entertainment-meal": ("neutral-relaxed", "用餐放松", 4),
        "entertainment-housework": ("neutral-bored", "家务无聊", 5),
    }

    def _infer_emotion_from_task(self, task_type: str):
        """由任务类型推断合理情绪，返回 (emotion, detail, intensity) 或 None"""
        return self.TASK_EMOTION_MAP.get(task_type)

    # 时段/场景 → 情绪（任务也识别不出来时的兜底推断，保证情绪栏永远有内容）
    CONTEXT_EMOTION = (
        (("凌晨", "深夜", "半夜", "熬夜", "通宵"), ("tired-sleepy", "深夜困倦", 6)),
        (("早上", "早晨", "清晨", "上午", "刚起床", "起床"), ("calm-relaxed", "晨间清爽", 4)),
        (("中午", "午休", "午间"), ("calm-relaxed", "午后慵懒", 4)),
        (("下午", "午后"), ("calm-focused", "午后平稳", 4)),
        (("傍晚", "黄昏", "日落", "夕阳"), ("calm-relaxed", "傍晚松弛", 3)),
        (("晚上", "夜晚", "夜里", "今晚", "睡前"), ("calm-relaxed", "夜晚放松", 3)),
        (("周末", "放假", "假期", "休息日"), ("calm-relaxed", "假日闲适", 3)),
    )

    def _infer_emotion_from_context(self, msg: str) -> tuple:
        """任务与情绪都没识别出来：从时段/场景推断一个合理情绪

        宁可给一个"有依据的推测"，也不要输出"平常-无特定情绪"这种空答案。
        """
        for kws, emo in self.CONTEXT_EMOTION:
            if any(w in msg for w in kws):
                return emo
        return "calm-relaxed", "轻松期待", 4

    def _mock_analyze(self, user_message: str) -> dict:
        msg = user_message.lower()

        task_type, task_detail, task_demand = self._match_task(msg)

        # 情绪三级推断：用户明说 > 由任务状态推断 > 由时段场景推断
        # （用户没提情绪时不写"平常-无特定情绪"，而是推测一个合理状态）
        matched = self._match_emotion(msg)
        if matched:
            emotion, emotion_detail, intensity = matched
            emotion_source = "explicit"
        else:
            inferred = (self._infer_emotion_from_task(task_type)
                        if task_type != "general" else None)
            if inferred:
                emotion, emotion_detail, intensity = inferred
                emotion_source = "task_inferred"
            else:
                emotion, emotion_detail, intensity = self._infer_emotion_from_context(msg)
                emotion_source = "context_inferred"

        # 情绪大类（用于调节判断和策略回退）
        emotion_group = emotion.split("-")[0]
        need_regulation = emotion_group in ("anxious", "tired", "sad")

        regulation_goals = {
            "anxious": "缓解焦虑，恢复到平静专注",
            "tired": "恢复精力，重新变得清醒有动力",
            "sad": "走出低落，重新感受到温暖和力量",
            "happy": "保持好状态，让愉悦延续",
            "calm": "维持平静，不被外界干扰",
            "neutral": "激活状态，找到当下的节奏",
        }

        strategy = self._mock_strategy(task_type, emotion)
        return {
            "task_type": task_type,
            "task_detail": task_detail,
            "task_demand": task_demand,
            "emotion": emotion,
            "emotion_detail": emotion_detail,
            "emotion_intensity": intensity,
            "emotion_source": emotion_source,
            "need_regulation": need_regulation,
            "regulation_goal": regulation_goals.get(emotion_group, "维持平衡"),
            "language_preference": self._detect_language_pref(msg),
            "music_strategy": strategy,
        }

    def _mock_strategy(self, task_type: str, emotion: str) -> dict:
        """细粒度策略表 + 父类回退"""
        strategies = {
            # ===== 编程 =====
            ("coding-deep", "calm-focused"): {"genres":["ambient","minimalist"],"energy":3,"tempo":"70-90 BPM","instrumental":True,"mood":"focused","explanation":"深度编码处于心流，用极简环境音维持不打断"},
            ("coding-debug", "anxious-overwhelmed"): {"genres":["ambient","classical"],"energy":2,"tempo":"50-80 BPM","instrumental":True,"mood":"calm","explanation":"调试遇阻思绪乱，先放慢节奏用镇静音乐理清思路"},
            ("coding-debug", "sad-frustrated"): {"genres":["neo-classical","ambient"],"energy":3,"tempo":"60-85 BPM","instrumental":True,"mood":"hopeful","explanation":"反复失败受挫时，用温暖钢琴曲重建耐心"},
            ("coding-learn", "calm-focused"): {"genres":["classical","ambient"],"energy":3,"tempo":"60-90 BPM","instrumental":True,"mood":"focused","explanation":"学新技术需要吸收信息，轻声古典乐最合适"},
            ("coding-review", "calm-focused"): {"genres":["classical","jazz"],"energy":4,"tempo":"80-110 BPM","instrumental":True,"mood":"alert","explanation":"代码审查需要清醒细致的判断，优雅器乐保持警觉"},
            # ===== 学习 =====
            ("study-exam", "anxious-exam"): {"genres":["classical","ambient"],"energy":2,"tempo":"50-80 BPM","instrumental":True,"mood":"calm","explanation":"考前焦虑最怕火上浇油，用极轻古典乐平稳心绪"},
            ("study-vocab", "tired-mental"): {"genres":["classical","neo-classical"],"energy":4,"tempo":"70-100 BPM","instrumental":True,"mood":"alert","explanation":"背单词脑子累，用轻快巴洛克音乐提升记忆唤醒度"},
            ("study-reading", "calm-relaxed"): {"genres":["ambient","folk"],"energy":3,"tempo":"60-90 BPM","instrumental":True,"mood":"calm","explanation":"阅读时保持安静氛围，低频纯音最舒适"},
            ("study-practice", "neutral-bored"): {"genres":["electronic","classical"],"energy":5,"tempo":"90-115 BPM","instrumental":True,"mood":"energized","explanation":"刷题无聊时用节奏感电子纯音提神"},
            # ===== 运动 =====
            ("workout-running", "tired-physical"): {"genres":["electronic","rock"],"energy":9,"tempo":"140-170 BPM","instrumental":False,"mood":"energetic","explanation":"跑步身体疲惫，用高BPM强节奏音乐卡住步伐节奏"},
            ("workout-strength", "happy-confident"): {"genres":["rock","hip-hop"],"energy":9,"tempo":"120-150 BPM","instrumental":False,"mood":"powerful","explanation":"力量训练自信满满，用厚重强音放大力量感"},
            ("workout-yoga", "anxious-tension"): {"genres":["ambient","neo-classical"],"energy":2,"tempo":"40-70 BPM","instrumental":True,"mood":"peaceful","explanation":"瑜伽拉伸时放慢呼吸，极缓纯音乐配合动作"},
            # ===== 创意 =====
            ("creative-brainstorm", "neutral-bored"): {"genres":["electronic","indie"],"energy":6,"tempo":"100-125 BPM","instrumental":False,"mood":"inspired","explanation":"头脑风暴没灵感，用跳跃感的电子乐激活发散思维"},
            ("creative-design", "anxious-deadline"): {"genres":["electronic","ambient"],"energy":5,"tempo":"90-110 BPM","instrumental":True,"mood":"calm","explanation":"设计赶截止又焦虑，用氛围电子保持冷静不慌乱"},
            # ===== 通勤 =====
            ("commute-driving", "tired-sleepy"): {"genres":["pop","rock"],"energy":7,"tempo":"110-140 BPM","instrumental":False,"mood":"energetic","explanation":"开车困倦危险，用提神音乐保持清醒（安全第一）"},
            ("commute-transit", "neutral-bored"): {"genres":["pop","indie"],"energy":6,"tempo":"100-130 BPM","instrumental":False,"mood":"joyful","explanation":"地铁通勤无聊，欢快音乐把碎片时间变享受"},
            # ===== 放松 =====
            ("relax-meditate", "anxious-overwhelmed"): {"genres":["ambient","neo-classical"],"energy":1,"tempo":"40-60 BPM","instrumental":True,"mood":"peaceful","explanation":"冥想前思绪杂乱，极简环境音引导注意力回到呼吸"},
            ("relax-winddown", "tired-mental"): {"genres":["folk","neo-classical"],"energy":2,"tempo":"50-80 BPM","instrumental":True,"mood":"soothing","explanation":"用脑过度想休息，温暖柔和的纯音是最好的抚慰"},
            # ===== 情绪专项（跨任务） =====
            ("general", "sad-lonely"): {"genres":["neo-classical","folk"],"energy":3,"tempo":"60-85 BPM","instrumental":True,"mood":"warm","explanation":"感到孤独时，温暖绵长的旋律像一位安静陪伴的朋友"},
            ("general", "happy-excited"): {"genres":["pop","electronic"],"energy":7,"tempo":"110-140 BPM","instrumental":False,"mood":"joyful","explanation":"亢奋状态用欢快节奏尽情释放"},
            # ===== 娱乐赛事事件级（不同事件推不同歌） =====
            ("entertainment-worldcup", "happy-festive"): {"genres":["pop","rock","electronic"],"energy":9,"tempo":"130-160 BPM","instrumental":False,"mood":"energetic","explanation":"世界杯来了！用燃曲和主题曲释放球迷热情"},
            ("entertainment-olympics", "happy-festive"): {"genres":["pop","classical","electronic"],"energy":8,"tempo":"120-150 BPM","instrumental":False,"mood":"inspired","explanation":"奥运盛事，恢弘激昂的音乐为健儿加油"},
            ("entertainment-nba", "happy-festive"): {"genres":["hip-hop","rock","electronic"],"energy":9,"tempo":"120-150 BPM","instrumental":False,"mood":"powerful","explanation":"NBA赛场用嘻哈和摇滚强节奏放大对抗感"},
            ("entertainment-football", "happy-festive"): {"genres":["pop","rock","electronic"],"energy":8,"tempo":"120-150 BPM","instrumental":False,"mood":"energetic","explanation":"看足球用高能燃曲和主题曲带起观赛氛围"},
            ("entertainment-tv", "neutral-relaxed"): {"genres":["pop","indie","folk"],"energy":4,"tempo":"80-110 BPM","instrumental":False,"mood":"relaxed","explanation":"追剧放松时刻，轻松音乐陪伴"},
            ("entertainment-gaming", "happy-excited"): {"genres":["electronic","rock","hip-hop"],"energy":8,"tempo":"120-150 BPM","instrumental":False,"mood":"energetic","explanation":"游戏高能时刻，电子乐和游戏BGM激发操作欲"},
            ("entertainment-party", "happy-celebratory"): {"genres":["pop","electronic","hip-hop"],"energy":9,"tempo":"120-150 BPM","instrumental":False,"mood":"festive","explanation":"派对场合用热门节奏让每个人都动起来"},
            ("entertainment-celebration", "happy-celebratory"): {"genres":["pop","electronic"],"energy":8,"tempo":"115-145 BPM","instrumental":False,"mood":"joyful","explanation":"庆祝时刻用欢快节奏分享喜悦"},
            ("entertainment-social", "happy-social"): {"genres":["pop","r&b","indie"],"energy":6,"tempo":"100-130 BPM","instrumental":False,"mood":"romantic","explanation":"社交约会时用轻松浪漫的节奏营造氛围"},
            # ===== 运动子类（不同运动推不同歌） =====
            ("workout-basketball", "happy-excited"): {"genres":["hip-hop","rock","electronic"],"energy":9,"tempo":"120-150 BPM","instrumental":False,"mood":"powerful","explanation":"打篮球需要高能量强节奏驱动爆发力"},
            ("workout-football", "happy-excited"): {"genres":["electronic","rock","pop"],"energy":8,"tempo":"120-145 BPM","instrumental":False,"mood":"energetic","explanation":"踢足球用中高BPM音乐维持跑动节奏"},
            ("workout-walk", "calm-relaxed"): {"genres":["folk","indie","ambient"],"energy":3,"tempo":"70-95 BPM","instrumental":False,"mood":"relaxed","explanation":"散步时用轻松悠闲的音乐陪伴步伐"},
            # ===== 新工作类精确策略 =====
            ("work-overtime", "tired-mental"): {"genres":["electronic","rock","indie"],"energy":6,"tempo":"100-130 BPM","instrumental":False,"mood":"energetic","explanation":"加班疲惫，用提神但不吵的音乐撑住精神"},
            ("work-ppt", "anxious-deadline"): {"genres":["ambient","electronic"],"energy":4,"tempo":"85-105 BPM","instrumental":True,"mood":"alert","explanation":"赶PPT焦虑，用节奏性纯音乐保持清醒"},
            ("work-meeting", "calm-focused"): {"genres":["jazz","classical","ambient"],"energy":3,"tempo":"70-95 BPM","instrumental":True,"mood":"professional","explanation":"会前或会中，低调器乐保持专业氛围"},
            ("relax-sleep", "tired-sleepy"): {"genres":["ambient","neo-classical","folk"],"energy":1,"tempo":"40-65 BPM","instrumental":True,"mood":"sleepy","explanation":"睡前用极缓纯音乐引导放松入眠"},
            ("relax-bath", "calm-relaxed"): {"genres":["neo-classical","ambient","folk"],"energy":2,"tempo":"50-80 BPM","instrumental":True,"mood":"soothing","explanation":"洗浴时用温暖柔和的音乐增加幸福感"},
            ("entertainment-meal", "neutral-relaxed"): {"genres":["jazz","folk","indie"],"energy":3,"tempo":"75-100 BPM","instrumental":False,"mood":"cozy","explanation":"用餐时用舒适不打扰的背景音"},
            ("entertainment-housework", "neutral-bored"): {"genres":["pop","electronic","indie"],"energy":6,"tempo":"105-135 BPM","instrumental":False,"mood":"cheerful","explanation":"做家务无聊，用欢快流行曲让干活变有趣"},
        }

        # 父类回退表（细粒度未命中时使用）
        parent_fallback = {
            ("coding", "anxious"): {"genres":["ambient","classical"],"energy":3,"tempo":"60-90 BPM","instrumental":True,"mood":"calm","explanation":"焦虑时编程需要镇静类纯音乐降低认知负荷"},
            ("coding", "tired"): {"genres":["electronic","indie"],"energy":5,"tempo":"90-110 BPM","instrumental":True,"mood":"energized","explanation":"疲惫时适度提升能量但保持无歌词避免分心"},
            ("coding", "focused"): {"genres":["ambient","minimalist"],"energy":3,"tempo":"70-100 BPM","instrumental":True,"mood":"focused","explanation":"已专注时保持低调环境音乐维持心流"},
            ("coding", "happy"): {"genres":["electronic","indie"],"energy":5,"tempo":"90-110 BPM","instrumental":True,"mood":"happy","explanation":"开心编程时用节奏感纯音乐保持愉悦流速"},
            ("coding", "sad"): {"genres":["neo-classical","ambient"],"energy":3,"tempo":"60-85 BPM","instrumental":True,"mood":"hopeful","explanation":"编程受挫低落时用温暖纯音乐重建信心"},
            ("coding", "neutral"): {"genres":["electronic","ambient"],"energy":4,"tempo":"85-105 BPM","instrumental":True,"mood":"balanced","explanation":"状态平常时用有节奏的纯音乐进入工作节奏"},
            # ===== work 大类回退 =====
            ("work", "anxious"): {"genres":["ambient","electronic"],"energy":4,"tempo":"85-110 BPM","instrumental":True,"mood":"alert","explanation":"工作焦虑时用节奏性纯音乐稳住心绪保持清醒"},
            ("work", "tired"): {"genres":["electronic","rock","indie"],"energy":6,"tempo":"100-135 BPM","instrumental":False,"mood":"energetic","explanation":"工作疲惫时用适度提神的音乐撑住精神"},
            ("work", "focused"): {"genres":["jazz","ambient","classical"],"energy":3,"tempo":"70-100 BPM","instrumental":True,"mood":"professional","explanation":"工作专注时用低调器乐保持专业氛围"},
            ("work", "neutral"): {"genres":["electronic","jazz"],"energy":5,"tempo":"90-115 BPM","instrumental":True,"mood":"balanced","explanation":"日常工作时用不打扰的背景音维持节奏"},
            ("workout", "tired"): {"genres":["electronic","rock","hip-hop"],"energy":9,"tempo":"120-160 BPM","instrumental":True,"mood":"energetic","explanation":"疲惫运动时用高能量强节奏音乐激发活力"},
            ("workout", "happy"): {"genres":["pop","electronic"],"energy":8,"tempo":"120-160 BPM","instrumental":True,"mood":"energetic","explanation":"开心运动时匹配高能量欢快纯音乐增强体验"},
            ("workout", "anxious"): {"genres":["rock","electronic"],"energy":8,"tempo":"120-150 BPM","instrumental":True,"mood":"powerful","explanation":"焦虑运动时用强力纯音乐释放压力"},
            ("workout", "neutral"): {"genres":["electronic","rock"],"energy":8,"tempo":"120-150 BPM","instrumental":True,"mood":"energetic","explanation":"状态平稳时用强节奏音乐带起运动气氛"},
            ("study", "anxious"): {"genres":["classical","ambient"],"energy":2,"tempo":"50-80 BPM","instrumental":True,"mood":"calm","explanation":"焦虑学习时需要极低打扰的平静音乐"},
            ("study", "tired"): {"genres":["classical","neo-classical"],"energy":4,"tempo":"70-100 BPM","instrumental":True,"mood":"alert","explanation":"疲惫学习需要优雅的古典乐保持清醒"},
            ("study", "focused"): {"genres":["classical","ambient"],"energy":3,"tempo":"60-90 BPM","instrumental":True,"mood":"focused","explanation":"已专注时保持轻声古典乐辅助学习"},
            ("study", "neutral"): {"genres":["classical","ambient"],"energy":3,"tempo":"60-90 BPM","instrumental":True,"mood":"calm","explanation":"状态平常时用古典纯音乐营造学习氛围"},
            ("creative", "neutral"): {"genres":["electronic","indie","r&b"],"energy":5,"tempo":"90-120 BPM","instrumental":True,"mood":"inspired","explanation":"创意工作适合有层次感的纯音乐激发灵感"},
            ("creative", "tired"): {"genres":["electronic","indie"],"energy":6,"tempo":"100-120 BPM","instrumental":True,"mood":"energized","explanation":"疲惫创作需要提神但不干扰思维的纯音乐"},
            ("creative", "anxious"): {"genres":["ambient","electronic"],"energy":4,"tempo":"85-105 BPM","instrumental":True,"mood":"calm","explanation":"焦虑创作时用氛围纯音乐稳住心绪再打开思路"},
            ("relax", "anxious"): {"genres":["ambient","neo-classical"],"energy":2,"tempo":"50-80 BPM","instrumental":True,"mood":"peaceful","explanation":"需要深度放松时最轻柔的环境音乐"},
            ("relax", "tired"): {"genres":["folk","neo-classical"],"energy":3,"tempo":"60-90 BPM","instrumental":True,"mood":"soothing","explanation":"疲惫放松时用温暖柔和的音乐抚慰"},
            ("relax", "neutral"): {"genres":["ambient","folk"],"energy":2,"tempo":"50-80 BPM","instrumental":True,"mood":"calm","explanation":"放松休息时用舒缓纯音乐陪伴"},
            ("commute", "happy"): {"genres":["pop","rock"],"energy":6,"tempo":"100-140 BPM","instrumental":True,"mood":"joyful","explanation":"通勤时欢快纯音乐提升日常愉悦感"},
            ("commute", "tired"): {"genres":["pop","rock"],"energy":7,"tempo":"110-150 BPM","instrumental":True,"mood":"energetic","explanation":"疲惫通勤用提神纯音乐唤醒精神"},
            ("commute", "neutral"): {"genres":["pop","indie"],"energy":6,"tempo":"100-130 BPM","instrumental":True,"mood":"joyful","explanation":"通勤路上用轻松纯音乐点亮路程"},
            ("general", "anxious"): {"genres":["ambient","classical"],"energy":3,"tempo":"60-85 BPM","instrumental":True,"mood":"calm","explanation":"焦虑时用镇静纯音乐帮心绪平稳下来"},
            ("general", "tired"): {"genres":["electronic","folk"],"energy":5,"tempo":"90-115 BPM","instrumental":True,"mood":"energized","explanation":"疲惫时用适度节奏的纯音乐恢复精力"},
            ("general", "sad"): {"genres":["neo-classical","folk"],"energy":3,"tempo":"60-85 BPM","instrumental":True,"mood":"warm","explanation":"低落时用温暖绵长的旋律慢慢托起情绪"},
            ("general", "happy"): {"genres":["pop","electronic"],"energy":6,"tempo":"100-130 BPM","instrumental":True,"mood":"joyful","explanation":"好心情时用欢快纯音乐延续愉悦"},
            ("general", "calm"): {"genres":["ambient","classical"],"energy":3,"tempo":"60-90 BPM","instrumental":True,"mood":"calm","explanation":"平静时用舒缓纯音乐保持这份安宁"},
            ("general", "neutral"): {"genres":["pop","electronic"],"energy":5,"tempo":"90-120 BPM","instrumental":True,"mood":"balanced","explanation":"状态平常时用轻快纯音乐找到节奏"},
            # ===== 娱乐父类回退（不同情绪下娱乐的音乐策略） =====
            ("entertainment", "happy"): {"genres":["pop","electronic","rock"],"energy":8,"tempo":"120-155 BPM","instrumental":False,"mood":"festive","explanation":"娱乐时刻用高能量音乐带动气氛，尽情享受"},
            ("entertainment", "anxious"): {"genres":["pop","electronic"],"energy":7,"tempo":"115-140 BPM","instrumental":False,"mood":"energetic","explanation":"紧张时刻用激昂音乐释放压力"},
            ("entertainment", "tired"): {"genres":["pop","electronic"],"energy":7,"tempo":"120-145 BPM","instrumental":False,"mood":"energized","explanation":"累了也要嗨起来，音乐给你充电"},
            ("entertainment", "neutral"): {"genres":["pop","electronic"],"energy":7,"tempo":"115-140 BPM","instrumental":False,"mood":"lively","explanation":"娱乐就要有娱乐的样子，用音乐点燃气氛"},
        }

        # 1) 精确匹配
        if (task_type, emotion) in strategies:
            s = strategies[(task_type, emotion)]
        else:
            t_parent = task_type.split("-")[0] if "-" in task_type else task_type
            e_parent = emotion.split("-")[0] if "-" in emotion else emotion
            s = (strategies.get((t_parent, emotion)) or parent_fallback.get((t_parent, emotion))
                 or strategies.get((task_type, e_parent)) or parent_fallback.get((task_type, e_parent))
                 or strategies.get((t_parent, e_parent)) or parent_fallback.get((t_parent, e_parent))
                 or strategies.get(("general", e_parent)) or parent_fallback.get(("general", e_parent))
                 or {"genres":["pop","electronic"],"energy":5,"tempo":"90-120 BPM","instrumental":True,"mood":"balanced","explanation":"根据当前细粒度状态平衡匹配纯音乐"})

        return {
            "genres": s["genres"],
            "energy_level": s["energy"],
            "tempo_range": s["tempo"],
            "instrumental_preferred": s["instrumental"],
            "mood_target": s["mood"],
            "explanation": s["explanation"],
        }
