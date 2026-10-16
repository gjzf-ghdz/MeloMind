"""音乐策略生成器 - 细粒度状态策略 + 父类回退"""
from models import MusicStrategy, Analysis


class MusicStrategyGenerator:
    def __init__(self):
        self.templates = {
            # ========== 编程细粒度 ==========
            ("coding-debug", "anxious-overwhelmed"): MusicStrategy(
                genres=["ambient", "classical"], energy_level=2,
                tempo_range="50-80 BPM", instrumental_preferred=True,
                mood_target="calm", priority="calm_first",
                notes="调试遇阻思绪乱，先降噪再找bug",
                explanation="用镇静纯音乐把大脑从慌乱中拉回来，分步排查",
                session_advice="先离开键盘3分钟，深呼吸+听一段安静纯音，然后按错误信息逐条排查，把大问题拆成小步骤",
            ),
            ("coding-debug", "sad-frustrated"): MusicStrategy(
                genres=["neo-classical", "ambient"], energy_level=3,
                tempo_range="60-85 BPM", instrumental_preferred=True,
                mood_target="hopeful", priority="rebuild_confidence",
                notes="反复失败受挫时，用温暖钢琴曲重建耐心",
                explanation="温暖旋律缓和挫败感，重新找回解决问题的信心",
                session_advice="记住每次报错都是进步，先修复一个最小问题找回手感，音乐陪你慢慢来",
            ),
            ("coding-deep", "calm-focused"): MusicStrategy(
                genres=["ambient", "minimalist"], energy_level=3,
                tempo_range="70-90 BPM", instrumental_preferred=True,
                mood_target="focused", priority="maintain_flow",
                notes="深度编码处于心流，极简环境音维持状态",
                explanation="低干扰环境音保护你的心流不被打破",
                session_advice="心流很珍贵，尽量不切换任务和音乐，专注写完这个功能再休息",
            ),
            ("coding-learn", "calm-focused"): MusicStrategy(
                genres=["classical", "ambient"], energy_level=3,
                tempo_range="60-90 BPM", instrumental_preferred=True,
                mood_target="focused", priority="absorb_info",
                notes="学新技术需要吸收信息，轻声古典乐最合适",
                explanation="古典纯音辅助信息吸收，不抢占注意力",
                session_advice="边听边做笔记，把新技术要点用自己的话写一遍，25分钟一个番茄钟",
            ),
            ("coding-review", "calm-focused"): MusicStrategy(
                genres=["classical", "jazz"], energy_level=4,
                tempo_range="80-110 BPM", instrumental_preferred=True,
                mood_target="alert", priority="sharp_mind",
                notes="代码审查需要清醒细致，优雅器乐保持警觉",
                explanation="有节奏的器乐让思维保持敏锐，不漏掉细节",
                session_advice="先整体看结构，再逐文件看细节，重点检查边界条件和异常处理",
            ),
            # ========== 学习细粒度 ==========
            ("study-exam", "anxious-exam"): MusicStrategy(
                genres=["classical", "ambient"], energy_level=2,
                tempo_range="50-80 BPM", instrumental_preferred=True,
                mood_target="calm", priority="steady_mind",
                notes="考前焦虑最怕火上浇油，极轻古典乐平稳心绪",
                explanation="极低刺激的古典乐把紧张感降下来，回归复习节奏",
                session_advice="焦虑是对未来的不确定，把它转化为行动：列一个今日复习清单，做完一项划掉一项",
            ),
            ("study-vocab", "tired-mental"): MusicStrategy(
                genres=["classical", "neo-classical"], energy_level=4,
                tempo_range="70-100 BPM", instrumental_preferred=True,
                mood_target="alert", priority="wake_memory",
                notes="背单词脑子累，用轻快巴洛克音乐提升记忆唤醒度",
                explanation="中等节奏器乐激活大脑，提升记忆和注意力",
                session_advice="换一种记忆方式（如抄写+朗读），配合音乐保持节奏，每25分钟休息5分钟",
            ),
            ("study-reading", "calm-relaxed"): MusicStrategy(
                genres=["ambient", "folk"], energy_level=3,
                tempo_range="60-90 BPM", instrumental_preferred=True,
                mood_target="calm", priority="immerse",
                notes="阅读时保持安静氛围，低频纯音最舒适",
                explanation="低频环境音营造沉浸氛围，不打扰文字理解",
                session_advice="给自己设定阅读目标（如20页），读完写下3个要点，保持这种轻松的节奏",
            ),
            ("study-practice", "neutral-bored"): MusicStrategy(
                genres=["electronic", "classical"], energy_level=5,
                tempo_range="90-115 BPM", instrumental_preferred=True,
                mood_target="energetic", priority="break_monotony",
                notes="刷题无聊时用节奏感电子纯音提神",
                explanation="节奏感纯音打破刷题的枯燥感，保持手速和专注",
                session_advice="无聊是因为重复，试试限时刷题（如20分钟10题），把刷题变成游戏",
            ),
            # ========== 运动细粒度 ==========
            ("workout-running", "tired-physical"): MusicStrategy(
                genres=["electronic", "rock"], energy_level=9,
                tempo_range="140-170 BPM", instrumental_preferred=False,
                mood_target="energetic", priority="pace_drive",
                notes="跑步身体疲惫，用高BPM强节奏卡住步伐",
                explanation="高BPM音乐与步频同步，让身体跟随节奏自动跑下去",
                session_advice="别停！把注意力放在音乐节奏上，先降速但保持跑动，音乐会在后半程给你力量",
            ),
            ("workout-strength", "happy-confident"): MusicStrategy(
                genres=["rock", "hip-hop"], energy_level=9,
                tempo_range="120-150 BPM", instrumental_preferred=False,
                mood_target="powerful", priority="power_up",
                notes="力量训练自信满满，用厚重强音放大力量感",
                explanation="强力重音与发力节奏同步，放大每组动作的力量输出",
                session_advice="好状态来了，今天可以挑战一下大重量（注意热身和保护），每组动作配合重音发力",
            ),
            ("workout-yoga", "anxious-tension"): MusicStrategy(
                genres=["ambient", "neo-classical"], energy_level=2,
                tempo_range="40-70 BPM", instrumental_preferred=True,
                mood_target="peaceful", priority="breathe_sync",
                notes="瑜伽拉伸时放慢呼吸，极缓纯音乐配合动作",
                explanation="极缓纯音引导呼吸与动作同步，释放身体紧绷",
                session_advice="跟随音乐节奏呼吸：吸气4秒-呼气6秒，把注意力放在身体的拉伸感上",
            ),
            # ========== 创意细粒度 ==========
            ("creative-brainstorm", "neutral-bored"): MusicStrategy(
                genres=["electronic", "indie"], energy_level=6,
                tempo_range="100-125 BPM", instrumental_preferred=False,
                mood_target="inspired", priority="spark_ideas",
                notes="头脑风暴没灵感，用跳跃感电子乐激活发散思维",
                explanation="跳跃感的电子乐打破思维定式，激发新的联想",
                session_advice="先用5分钟随便写下所有想法（不管好坏），再从中挑选组合，音乐会让联想更活跃",
            ),
            ("creative-design", "anxious-deadline"): MusicStrategy(
                genres=["electronic", "ambient"], energy_level=5,
                tempo_range="90-110 BPM", instrumental_preferred=True,
                mood_target="calm", priority="calm_create",
                notes="设计赶截止又焦虑，用氛围电子保持冷静",
                explanation="氛围电子稳住情绪，同时保持创作节奏不慌乱",
                session_advice="把设计拆成可用的小模块，先完成核心部分再优化细节，避免被截止时间压垮",
            ),
            # ========== 通勤细粒度 ==========
            ("commute-driving", "tired-sleepy"): MusicStrategy(
                genres=["pop", "rock"], energy_level=7,
                tempo_range="110-140 BPM", instrumental_preferred=False,
                mood_target="energetic", priority="stay_alert",
                notes="开车困倦危险，用提神音乐保持清醒（安全第一）",
                explanation="强节奏音乐刺激大脑保持警觉，防止驾驶疲劳",
                session_advice="安全第一：开窗通风+音乐提神+尽快找安全地点休息，不要硬撑",
            ),
            ("commute-transit", "neutral-bored"): MusicStrategy(
                genres=["pop", "indie"], energy_level=6,
                tempo_range="100-130 BPM", instrumental_preferred=False,
                mood_target="joyful", priority="enjoy_transit",
                notes="地铁通勤无聊，欢快音乐把碎片时间变享受",
                explanation="欢快节奏让通勤碎片时间变得轻快有趣",
                session_advice="通勤时间可以听歌+想今天最重要的3件事，或者听一集播客，把碎片时间利用起来",
            ),
            # ========== 放松细粒度 ==========
            ("relax-meditate", "anxious-overwhelmed"): MusicStrategy(
                genres=["ambient", "neo-classical"], energy_level=1,
                tempo_range="40-60 BPM", instrumental_preferred=True,
                mood_target="peaceful", priority="deep_soothe",
                notes="冥想前思绪杂乱，极简环境音引导注意力回到呼吸",
                explanation="极简环境音是冥想的最佳锚点，把飘散的思绪拉回当下",
                session_advice="从5分钟冥想开始：跟随音乐背景音，数呼吸（吸气1-4-呼气5-8），思绪跑了就轻轻拉回来",
            ),
            ("relax-winddown", "tired-mental"): MusicStrategy(
                genres=["folk", "neo-classical"], energy_level=2,
                tempo_range="50-80 BPM", instrumental_preferred=True,
                mood_target="soothing", priority="full_rest",
                notes="用脑过度想休息，温暖柔和的纯音是最好的抚慰",
                explanation="温暖旋律让紧绷的神经慢慢松弛下来",
                session_advice="今天已经很努力了！给自己30分钟完全放空，不碰手机，让音乐陪你把电量充满",
            ),
            # ========== 娱乐赛事事件级（不同事件推不同歌） ==========
            ("entertainment-worldcup", "happy-festive"): MusicStrategy(
                genres=["pop", "rock", "electronic"], energy_level=9,
                tempo_range="130-160 BPM", instrumental_preferred=False,
                mood_target="energetic", priority="event_anthems",
                notes="世界杯来了！用燃曲和主题曲释放球迷热情",
                explanation="高能燃曲与世界杯主题曲同频共振，放大观赛激情",
                session_advice="进球那一刻跟着音乐一起呐喊吧！赛前循环主题曲预热气氛",
            ),
            ("entertainment-olympics", "happy-festive"): MusicStrategy(
                genres=["pop", "classical", "electronic"], energy_level=8,
                tempo_range="120-150 BPM", instrumental_preferred=False,
                mood_target="inspired", priority="event_anthems",
                notes="奥运盛事，恢弘激昂的音乐为健儿加油",
                explanation="恢弘旋律与竞技精神呼应，为每一枚奖屏喝彩",
                session_advice="看决赛时把音乐音量调低些，别盖过解说；颁奖时切回国歌级燃曲",
            ),
            ("entertainment-nba", "happy-festive"): MusicStrategy(
                genres=["hip-hop", "rock", "electronic"], energy_level=9,
                tempo_range="120-150 BPM", instrumental_preferred=False,
                mood_target="powerful", priority="event_anthems",
                notes="NBA赛场用嘻哈和摇滚强节奏放大对抗感",
                explanation="嘻哈强拍与球场对抗感同频，扣篮时刻更燃",
                session_advice="中场休息时用嘻哈循环保持热度，关键时刻切回比赛声音",
            ),
            ("entertainment-football", "happy-festive"): MusicStrategy(
                genres=["pop", "rock", "electronic"], energy_level=8,
                tempo_range="120-150 BPM", instrumental_preferred=False,
                mood_target="energetic", priority="event_anthems",
                notes="看足球用高能燃曲和主题曲带起观赛氛围",
                explanation="高能燃曲匹配球场节奏，让每一次进攻都更有张力",
                session_advice="赛前主题曲预热，进球后切庆祝燃曲欢呼一波",
            ),
            ("entertainment-tv", "neutral-relaxed"): MusicStrategy(
                genres=["pop", "indie", "folk"], energy_level=4,
                tempo_range="80-110 BPM", instrumental_preferred=False,
                mood_target="relaxed", priority="chill_vibe",
                notes="追剧放松时刻，轻松音乐陪伴",
                explanation="轻松旋律不抢戏，铺垫惬意的观剧氛围",
                session_advice="追剧间隙听两首轻音乐放松眼睛，别连续刷太晚",
            ),
            ("entertainment-gaming", "happy-excited"): MusicStrategy(
                genres=["electronic", "rock", "hip-hop"], energy_level=8,
                tempo_range="120-150 BPM", instrumental_preferred=False,
                mood_target="energetic", priority="epic_battle",
                notes="游戏高能时刻，电子乐和游戏BGM激发操作欲",
                explanation="强节奏电子乐与游戏节拍同步，手感更热血",
                session_advice="排位连胜别上头，每局间隙站起来活动一下再战",
            ),
            ("entertainment-party", "happy-celebratory"): MusicStrategy(
                genres=["pop", "electronic", "hip-hop"], energy_level=9,
                tempo_range="120-150 BPM", instrumental_preferred=False,
                mood_target="festive", priority="hype_crowd",
                notes="派对场合用热门节奏让每个人都动起来",
                explanation="热门舞曲节奏带动全场气氛，嗨翻每一刻",
                session_advice="把歌单交给节奏感最强的舞曲串烧，气氛冷了就切下一首",
            ),
            ("entertainment-celebration", "happy-celebratory"): MusicStrategy(
                genres=["pop", "electronic"], energy_level=8,
                tempo_range="115-145 BPM", instrumental_preferred=False,
                mood_target="joyful", priority="hype_crowd",
                notes="庆祝时刻用欢快节奏分享喜悦",
                explanation="欢快节奏放大喜悦感，让庆祝更有仪式感",
                session_advice="生日/跨年先来一首应景歌曲，再切欢快歌单延续气氛",
            ),
            ("entertainment-social", "happy-social"): MusicStrategy(
                genres=["pop", "r&b", "indie"], energy_level=6,
                tempo_range="100-130 BPM", instrumental_preferred=False,
                mood_target="romantic", priority="soft_ambience",
                notes="社交约会时用轻松浪漫的节奏营造氛围",
                explanation="轻柔律动不喧宾夺主，给交谈留出空间",
                session_advice="音量保持在能轻松聊天的程度，R&B和City Pop最合适",
            ),
            # ========== 情绪专项（跨任务） ==========
            ("general", "sad-lonely"): MusicStrategy(
                genres=["neo-classical", "folk"], energy_level=3,
                tempo_range="60-85 BPM", instrumental_preferred=True,
                mood_target="soothing", priority="warm_company",
                notes="感到孤独时，温暖绵长的旋律像安静陪伴的朋友",
                explanation="温暖旋律带来被陪伴的感觉，孤独感慢慢被抚平",
                session_advice="孤独不代表失败，试着给一个朋友发条消息，或者写下此刻的感受，音乐先陪你一会儿",
            ),
            ("general", "happy-excited"): MusicStrategy(
                genres=["pop", "electronic"], energy_level=7,
                tempo_range="110-140 BPM", instrumental_preferred=False,
                mood_target="joyful", priority="ride_the_high",
                notes="亢奋状态用欢快节奏尽情释放",
                explanation="欢快强节奏与高能量情绪同频，把好状态最大化",
                session_advice="情绪高涨时做事效率翻倍，趁现在做最重要/最需要动力的事！",
            ),
            # ===== 通用情绪父类（兜底基准） =====
            ("general", "happy"): MusicStrategy(
                genres=["pop", "electronic", "indie"], energy_level=6,
                tempo_range="105-135 BPM", instrumental_preferred=False,
                mood_target="joyful", priority="ride_the_high",
                notes="好心情配欢快旋律，让愉悦延续",
                explanation="欢快节奏与好心情同频，放大当下的快乐",
                session_advice="好状态要保持，跟着音乐节奏继续做喜欢的事",
            ),
            ("general", "calm"): MusicStrategy(
                genres=["ambient", "folk", "neo-classical"], energy_level=3,
                tempo_range="60-90 BPM", instrumental_preferred=True,
                mood_target="calm", priority="keep_balance",
                notes="平静状态用舒缓纯音乐维持内心节奏",
                explanation="舒缓旋律延续平静心境，不被外界打扰",
                session_advice="难得的平静时光，让音乐陪你保持这份从容",
            ),
            ("general", "anxious"): MusicStrategy(
                genres=["ambient", "classical"], energy_level=2,
                tempo_range="50-80 BPM", instrumental_preferred=True,
                mood_target="calm", priority="calm_first",
                notes="焦虑时优先镇静纯音乐，先稳住情绪",
                explanation="低刺激纯音乐降低紧绷感，让心慢下来",
                session_advice="先深呼吸3次，让音乐把心率带慢，再处理让你焦虑的事",
            ),
            ("general", "tired"): MusicStrategy(
                genres=["folk", "neo-classical"], energy_level=3,
                tempo_range="55-85 BPM", instrumental_preferred=True,
                mood_target="soothing", priority="gentle_rest",
                notes="疲惫时用温暖柔和的音乐轻轻抚慰",
                explanation="温暖旋律给疲惫的自己一点喘息空间",
                session_advice="允许自己休息一会儿，听几首柔歌再出发",
            ),
            ("general", "neutral"): MusicStrategy(
                genres=["pop", "indie"], energy_level=5,
                tempo_range="90-120 BPM", instrumental_preferred=True,
                mood_target="balanced", priority="balanced_match",
                notes="随手听点歌时，用均衡旋律找到当下节奏",
                explanation="不快不慢的旋律为日常时刻找到合适的节奏",
                session_advice="跟着音乐节奏，找到此刻想做的事",
            ),
            # ========== 父类模板（回退基准） ==========
            ("coding", "anxious"): MusicStrategy(
                genres=["ambient", "classical"], energy_level=3,
                tempo_range="60-90 BPM", instrumental_preferred=True,
                mood_target="calm", priority="calm_first",
                notes="焦虑时编程，优先无歌词低频纯音乐稳定情绪",
                explanation="用镇静类纯音乐降低认知负荷",
                session_advice="深呼吸3次，从轻音乐开始，25分钟番茄钟+5分钟休息",
            ),
            ("coding", "tired"): MusicStrategy(
                genres=["electronic", "indie"], energy_level=5,
                tempo_range="90-110 BPM", instrumental_preferred=True,
                mood_target="energetic", priority="energy_boost",
                notes="适度提神但保持无歌词，避免注意力分散",
                explanation="用有节奏感的纯音乐唤醒大脑但不过度刺激",
                session_advice="先喝杯水活动一下，再用中等节奏音乐进入状态",
            ),
            ("coding", "focused"): MusicStrategy(
                genres=["ambient", "minimalist"], energy_level=3,
                tempo_range="70-100 BPM", instrumental_preferred=True,
                mood_target="focused", priority="maintain_flow",
                notes="已进入心流状态，用极简音乐维持",
                explanation="低调环境音乐维持专注不打扰",
                session_advice="保持当前节奏，不要切换音乐打断心流",
            ),
            ("coding", "happy"): MusicStrategy(
                genres=["electronic", "indie"], energy_level=5,
                tempo_range="90-110 BPM", instrumental_preferred=True,
                mood_target="joyful", priority="sustain_mood",
                notes="开心编程，用节奏感纯音乐保持好心情和效率",
                explanation="带节奏感的纯音乐让开心的你写代码更有动力",
                session_advice="好状态保持住，这节奏感能陪你写出好代码",
            ),
            ("coding", "sad"): MusicStrategy(
                genres=["neo-classical", "ambient"], energy_level=3,
                tempo_range="60-85 BPM", instrumental_preferred=True,
                mood_target="hopeful", priority="rebuild_momentum",
                notes="编程受挫低落，用温暖纯音乐重建信心",
                explanation="温暖旋律缓和挫败，重新找回解决问题的动力",
                session_advice="先做一个小任务找回掌控感，再啃难题",
            ),
            ("workout", "tired"): MusicStrategy(
                genres=["electronic", "rock", "hip-hop"], energy_level=9,
                tempo_range="120-160 BPM", instrumental_preferred=True,
                mood_target="energetic", priority="maximum_energy",
                notes="最高能量纯音乐驱动运动，强节奏激发活力",
                explanation="高能量强节奏音乐克服疲惫、激发运动活力",
                session_advice="别勉强！先中能量热身5分钟，再慢慢加大强度",
            ),
            ("workout", "happy"): MusicStrategy(
                genres=["pop", "electronic"], energy_level=8,
                tempo_range="120-160 BPM", instrumental_preferred=True,
                mood_target="energetic", priority="amplify_joy",
                notes="用高能量欢快纯音乐放大快乐体验",
                explanation="高能量纯音乐匹配你的好心情，运动更尽兴",
                session_advice="好状态+好音乐=燃爆，享受这场运动！",
            ),
            ("workout", "anxious"): MusicStrategy(
                genres=["rock", "electronic"], energy_level=8,
                tempo_range="120-150 BPM", instrumental_preferred=True,
                mood_target="powerful", priority="release_tension",
                notes="用强力纯音乐释放焦虑和压力",
                explanation="强力有冲击感的纯音乐帮你释放焦虑",
                session_advice="把焦虑转化为运动的力量，每一下都释放",
            ),
            ("study", "anxious"): MusicStrategy(
                genres=["classical", "ambient"], energy_level=2,
                tempo_range="50-80 BPM", instrumental_preferred=True,
                mood_target="calm", priority="deep_calm",
                notes="极低打扰的古典/环境音乐，先平静再学习",
                explanation="极低打扰的平静音乐帮助恢复专注力",
                session_advice="闭眼听一首古典小品3-5分钟，让思绪平静再开始",
            ),
            ("study", "tired"): MusicStrategy(
                genres=["classical", "neo-classical"], energy_level=4,
                tempo_range="70-100 BPM", instrumental_preferred=True,
                mood_target="alert", priority="gentle_alert",
                notes="优雅古典乐适度提神但不干扰学习",
                explanation="优雅的古典乐让你保持清醒又不过度兴奋",
                session_advice="用轻快巴洛克音乐唤醒学习状态",
            ),
            ("study", "focused"): MusicStrategy(
                genres=["classical", "ambient"], energy_level=3,
                tempo_range="60-90 BPM", instrumental_preferred=True,
                mood_target="focused", priority="background_support",
                notes="已专注时轻声背景乐保持氛围",
                explanation="轻声古典乐维持学习氛围，不打断状态",
                session_advice="保持当前节奏，专注状态是宝贵的",
            ),
            ("creative", "neutral"): MusicStrategy(
                genres=["electronic", "indie", "r&b"], energy_level=5,
                tempo_range="90-120 BPM", instrumental_preferred=True,
                mood_target="inspired", priority="inspire",
                notes="有层次感的纯音乐激发发散思维",
                explanation="层次丰富的电子/独立纯音乐打开创意空间",
                session_advice="让音乐带着思维发散，不要限制自己",
            ),
            ("creative", "tired"): MusicStrategy(
                genres=["electronic", "indie"], energy_level=6,
                tempo_range="100-120 BPM", instrumental_preferred=True,
                mood_target="energetic", priority="wake_creativity",
                notes="提神但不干扰思维的纯音乐",
                explanation="用新颖纯器乐唤醒大脑的创造性区域",
                session_advice="新奇的音乐往往能带来意想不到的灵感",
            ),
            ("relax", "anxious"): MusicStrategy(
                genres=["ambient", "neo-classical"], energy_level=2,
                tempo_range="50-80 BPM", instrumental_preferred=True,
                mood_target="peaceful", priority="deep_soothe",
                notes="最轻柔的环境音乐帮助深度身心放松",
                explanation="轻柔环境/新古典音乐是最有效的放松良药",
                session_advice="找安静角落，戴上耳机，给自己15分钟完全放松",
            ),
            ("relax", "tired"): MusicStrategy(
                genres=["folk", "neo-classical"], energy_level=3,
                tempo_range="60-90 BPM", instrumental_preferred=True,
                mood_target="soothing", priority="warm_comfort",
                notes="温暖柔和的音乐抚慰疲惫身心",
                explanation="温暖柔和的音乐让疲惫的你找到慰藉",
                session_advice="累了就休息，让音乐帮你恢复能量",
            ),
            ("commute", "happy"): MusicStrategy(
                genres=["pop", "rock"], energy_level=6,
                tempo_range="100-140 BPM", instrumental_preferred=True,
                mood_target="joyful", priority="joy_ride",
                notes="经典欢快纯音乐让通勤变成享受",
                explanation="欢快节奏让通勤路上的每一分钟都开心",
                session_advice="音量适中，通勤注意安全哦",
            ),
            ("commute", "tired"): MusicStrategy(
                genres=["pop", "rock"], energy_level=7,
                tempo_range="110-150 BPM", instrumental_preferred=True,
                mood_target="energetic", priority="wake_up_commute",
                notes="强节奏提神纯音乐唤醒精神",
                explanation="提神纯器乐帮你从疲惫中振奋起来",
                session_advice="跟着节奏点头，让身体慢慢醒过来",
            ),
            ("entertainment", "happy"): MusicStrategy(
                genres=["pop", "electronic", "rock"], energy_level=8,
                tempo_range="115-150 BPM", instrumental_preferred=False,
                mood_target="festive", priority="hype_crowd",
                notes="娱乐时刻用欢快燃曲带起气氛",
                explanation="欢快高能的音乐放大娱乐的快乐",
                session_advice="享受此刻，让音乐把气氛拉满",
            ),
            ("entertainment", "neutral"): MusicStrategy(
                genres=["pop", "indie", "r&b"], energy_level=5,
                tempo_range="90-125 BPM", instrumental_preferred=False,
                mood_target="relaxed", priority="chill_vibe",
                notes="轻松旋律陪伴休闲娱乐时光",
                explanation="轻松愉快的音乐为休闲时光增色",
                session_advice="放轻松，音乐和娱乐都很配",
            ),
        }

    def generate(self, analysis: Analysis) -> MusicStrategy:
        task = analysis.task_type or "general"
        emotion = analysis.emotion or "neutral"

        # 1) 精确匹配（含细粒度键）
        if (task, emotion) in self.templates:
            return self.templates[(task, emotion)]

        # 2) 父类提取
        t_parent = task.split("-")[0] if "-" in task else task
        e_parent = emotion.split("-")[0] if "-" in emotion else emotion

        # 3) 子任务+父情绪 / 父任务+子情绪 / 父+父
        for key in ((t_parent, emotion), (task, e_parent), (t_parent, e_parent)):
            if key in self.templates:
                return self.templates[key]

        # 4) 按任务父类兜底
        for (t, e), s in self.templates.items():
            if t == t_parent:
                return s

        # 4.5) 通用情绪兜底（避免跨任务组误命中无关文案）
        for (t, e), s in self.templates.items():
            if t == "general" and e == e_parent:
                return s

        # 4.6) 按情绪父类兜底（最后手段）
        for (t, e), s in self.templates.items():
            if e == e_parent:
                return s

        # 5) 默认
        return MusicStrategy(
            genres=["pop", "electronic"], energy_level=5,
            tempo_range="90-120 BPM", instrumental_preferred=True,
            mood_target="balanced", priority="balanced_match",
            notes="根据当前状态平衡匹配",
            explanation="平衡的音乐陪伴你此刻的状态",
            session_advice="跟随音乐，感受当下，让节奏陪伴你完成此刻",
        )
