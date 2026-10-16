# MeloMind · 音此刻 —— 基于生成式 AI 的自适应音乐推荐系统

> 2026 友安杯 · AI 应用类赛道 · 团队「音此刻」
> 在线体验：http://47.99.92.14:8000

本目录为作品《MeloMind 基于生成式 AI 的自适应音乐推荐系统》的**全部源代码**，
由团队自行开发，**不含任何开发工具、开源软件源与公共类库**：
后端仅依赖 Python 标准库，前端为原生 HTML / CSS / JavaScript，无任何第三方框架或 CDN 资源。

---

## 一、目录结构

```
backend/                    后端服务：23 个 Python 模块（Python 标准库 http.server）
├── server.py               服务入口、路由、静态资源、REST 接口
├── recommender.py          候选池构建、六层递进排序、多样性选择、推荐理由生成
├── local_music_db.py       曲库加载与索引（关键词 / 任务 / 情绪 / 标题 / 意图簇）
├── models.py               数据类、song_language()、infer_instrumental()、语种分组
├── music_relevance.py      相关性打分模型（情绪词族、IDF 特异性、能量与节奏百分位）
├── music_strategy.py       「任务 × 情绪」策略模板库（80 余个精确模板 + 四级回退）
├── special_noun_detector.py 专有名词检测（别名映射、词根还原、泛化词黑名单）
├── llm_engine.py           LLM 状态理解（GLM 接入，离线自动降级为词典引擎）
├── audio_preview.py        Apple iTunes 30 秒官方试听取源与缓存
├── auth.py / favorites.py / history.py   注册登录、收藏夹、搜索历史
├── qqmusic_source.py       QQ 音乐检索与外链生成
├── llm_config.json         LLM 接入配置
├── lyrics_lang.json        歌词语种实测表（11,646 条，语种判定的第一判据）
├── diag_qq.py              数据源连通性诊断
└── _test_*.py / _verify_lang_fix.py / test_local_recommend.py   模块自测脚本

frontend/                   前端：原生单页应用，无第三方库
├── index.html              对话交互、状态面板、音乐参数卡片、歌曲卡片
├── app.js                  推荐请求、渲染、收藏、历史回放、试听播放
└── style.css               暗色沉浸式主题

music_database/             曲库构建管道（可复现整库）
├── build_music_db.py       建库主流程：关键词采集、按 ID 去重、元数据富化
├── crawl_qqmusic_full.py   QQ 音乐全量抓取
├── crawl_genres_massive.py 风格维度增量抓取
├── crawl_instrumental_massive.py  器乐 / 纯音乐维度增量抓取
├── supplement_toplist.py / supplement_instrumental.py  榜单与器乐补充采集
├── dedup_db.py             按歌曲 ID 去重
├── post_process_db.py      能量、BPM、时长、推荐理由等后处理
├── retag_16.py             task_tags 重新标注（最长关键词优先匹配）
├── fix_instrumental_labels.py     纯音乐标记修正
├── analyze_db_coverage.py / analyze_instrumental_gap.py   覆盖率与缺口分析
├── verify_db_quality.py    数据质量核验
├── event_keywords.json     事件类关键词与别名配置
└── README.md               数据管道说明

pack_for_deploy.py          部署打包（支持只传改动文件的增量打包）
update_server.py            一键上传并重启云端服务（POST /api/deploy + 自动验证）
update_server.bat           上述脚本的 Windows 入口
deploy.sh                   服务器端部署脚本（systemd 服务、swap 配置）
start.bat / start_server.bat / restart.bat   本地启动与重启
README.md                   本文件
```

---

## 二、运行环境与启动

```bash
# 环境：仅需 Python 3.10+，无第三方依赖
python --version

# 将曲库放入 music_database/music_database.json（见第四节），然后：
python backend/server.py          # 或双击 start.bat / start_server.bat
# 首次加载 52.8 万首曲库约需 60–90 秒

# 浏览器访问 http://127.0.0.1:8000
```

模块自测（可单独运行，用于复现各项结论）：

```bash
python backend/test_local_recommend.py     # 本地推荐链路
python backend/_test_randomness.py         # 推荐多样性
python backend/_test_special_nouns.py      # 专有名词识别
python backend/_test_noun_filter.py        # 泛化状态词过滤
python backend/_verify_lang_fix.py         # 语种判定
python backend/_test_16_tags.py            # 16 类标签覆盖
python backend/_test_gaming_kw.py          # 游戏类关键词
python backend/_test_llm_lang.py           # LLM 语种理解
```

## 三、部署到云端

```bash
python update_server.py backend/recommender.py frontend/app.js   # 增量部署（不传曲库）
python pack_for_deploy.py                                        # 全量打包
```

`update_server.py` 会调用 `pack_for_deploy.py` 打包，上传到 `POST /api/deploy`，
等待服务重启后自动验证首页可访问。服务器侧由 `deploy.sh` 安装为 systemd 服务，
实现开机自启与崩溃自愈，并配置 4 GB swap 防止大库加载 OOM。

> 注：部署接口使用 `backend/deploy_token.txt` 鉴权。该文件为密钥，不随本目录提供；
> 首次运行 `pack_for_deploy.py` 时若不存在会自动生成新密钥，需与服务器端保持一致。

---

## 四、数据集说明

曲库文件 `music_database/music_database.json`（约 312 MB，527,742 首歌曲元数据）
为项目自有构建数据，**不属于源代码**，因此未包含在本目录中。

如需从零复现整库，可按 `music_database/build_music_db.py` 的流程重新抓取与构建
（详见 `music_database/README.md`）。

**数据口径（撰写材料与核对时以此为准）**：曲库 JSON 中的 `instrumental` 字段为历史标记，
`local_music_db.py` 装载时会用 `models.infer_instrumental()` 逐曲重算，因此
**不要直接读该字段下结论**，应使用运行时口径：

| 板块 | 数量 | 占比 |
|---|---|---|
| 纯音乐 | 86,357 | 16.36% |
| 中文歌 | 147,446 | 27.94% |
| 英文歌 | 255,625 | 48.43% |
| 日韩等其它语言 | 38,314 | 7.26% |

细分：japanese 21,760 / korean 15,756 / other 798。

---

## 五、核心机制

**1. 状态理解：LLM + 规则词典双引擎**
9 大类 40 个子任务、6 大组 23 个情绪子类、180+ 关键词，40 条「任务→情绪」自动推断映射。
有网络时由 GLM 主导理解（提示词内显式禁止兜底输出），无网络时自动降级为纯词典匹配。

**2. 六层递进选歌**

| 层 | 作用 |
|---|---|
| Layer 0 | 歌名精准命中（含日常短语黑名单，避免「我喜欢」被误判为点歌） |
| Layer 1 | 专有名词识别（别名映射 + 词根还原 + 专有名词词库） |
| Layer 2 | 任务标签匹配 |
| Layer 3 | 情绪标签匹配 |
| Layer 4 | 能量 / 风格 / 语言偏好过滤与用户偏好加权 |
| Layer 5 | 融入大众度权重的无放回抽样（优先歌曲占 80% 输出位） |

点名场景执行「关键词优先、情绪兜底」：名词相关度是第一因素，
音乐元素契合度在命中集合内部决定先后顺序。

**3. 语种判定：只看歌词文字体系，不看歌手国籍**
歌名与艺人名都无法证明一首歌用什么语言演唱。现判定顺序为：
① 歌词实测表 `backend/lyrics_lang.json`（最先执行）→ ② 专辑 / 标题 / 艺人名中的假名、谚文特征
→ ③ 艺人级语种推断。歌词实测的做法是：只抓「元数据分不出语种」的曲目，
按 LRC 时间戳解析歌词行并剔除词曲编曲等元信息行，**按去重后的歌词行**统计各文字系统字符数后表决
（重复副歌只算一次），证据不足则不表态、沿用原有判定。
校正后中文板块由 152,820 首调整为 147,446 首，英文 255,625 首、日韩等其它 38,314 首。

**4. 纯音乐独立成板**
先拦人声信号（合唱、和声、翻唱、指定演唱者），再识别器乐作品结构
（作品号 Op./BWV、乐章、曲式与速度术语），并以风格或演奏者佐证，最后才沿用曲库标记。

**5. 30 秒试听**
免密钥接入 Apple 官方接口，只转发 `previewUrl` 官方直链，服务端不下载、不转码、不缓存
任何音频；按文字体系选择商店（华语优先港台），歌手与时长比对保证原唱优先；
无官方片段的曲目回退为外链跳转，不做兜底播放。

**6. AI 音乐提示词引擎**
一键生成涵盖前奏、主歌、副歌、桥段、尾奏、音色选择的六段式专业制作提示词，
可直接用于抖音 AI 音乐人、Suno 等工具，形成「推荐 → 创作」闭环。

---

## 六、本目录的范围说明

**已纳入**：交付系统本身的运行代码、曲库构建管道、云端部署脚本、本地启动脚本、
模块自测脚本，以及语种实测表与事件关键词表这两份随代码部署的配置。

**未纳入**（均非作品源代码，或不属于交付系统本身）：

- 曲库数据 `music_database.json` 与历史备份 —— 数据文件，见第四节。
- `backend/chat_logs.jsonl`、`users.json`、`history.json`、`preview_cache.json` ——
  运行时产生的用户数据，服务端首次启动会自动初始化。
- `backend/deploy_token.txt` —— 部署接口密钥，涉密。
- 参赛文档与 PPT 的生成脚本、开发期诊断记录 —— 开发过程产物，
  且前者依赖 python-docx / python-pptx / lxml 等第三方库，不属于本作品代码。
- 早期内网穿透（cpolar）相关的辅助脚本 —— 已废弃方案，现部署方式为阿里云 + systemd。

---

## 七、许可证与合规

本项目代码与文档采用 **Apache-2.0** 许可证（见仓库根目录 `LICENSE`）。
第三方服务与数据来源声明见 `NOTICE`；完整曲库数据不随仓库分发，建库管道全部开放，可按 `music_database/README.md` 自行复现。
