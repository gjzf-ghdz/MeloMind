"""
音乐数据库使用说明文档

========================================
  MeloMind 音乐数据库模块使用说明
========================================

## 模块概述

`music_database` 是 MeloMind 项目的独立音乐数据库模块，负责从 QQ 音乐
抓取歌曲数据并构建包含风格、能量、情绪、乐器等元数据的结构化音乐数据库。

## 文件位置
  music_database/music_database.json       # 数据库文件（爬取+后处理后生成）

## 脚本说明
  build_music_db.py      # 数据库构建脚本：从 QQ 音乐爬取歌曲并推断元数据
  post_process_db.py     # 后处理脚本：精细化推断风格/能量/情绪等字段
  verify_db_quality.py   # 数据库质量验证脚本

## 数据库字段说明

每条记录包含以下字段：

  - id:              QQ音乐 songmid（唯一标识）
  - title:           歌曲名
  - artist:          艺术家/歌手
  - album:           专辑名
  - genre:           风格（classical/pop/rock/electronic/folk/r&b/hip-hop/jazz/ambient等）
  - duration_sec:    时长（秒）
  - tempo_bpm:       节奏（BPM，40-200）
  - instrumental:    是否纯音乐（true/false）
  - instrument_type: 主要乐器（钢琴/吉他/合成器/电吉他/萨克斯/贝斯/鼓机等）
  - energy:          能量等级（1-10：1最舒缓，10最劲爆）
  - mood_tags:       情绪标签（数组：calm/energetic/joyful/sad/hopeful/dreamy等）
  - task_tags:       任务标签（数组：study/workout/relax/entertainment等）
  - external_url:    QQ音乐跳转链接
  - cover_url:       专辑封面URL
  - source:          数据来源（"qqmusic"）
  - search_keyword:  搜索关键词（用于追溯）
  - reason:          推荐理由

## 编程访问示例

import json

# 加载数据库
with open('music_database/music_database.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

songs = data['songs']  # list of song dicts

# 按风格筛选
rock_songs = [s for s in songs if s['genre'] == 'rock']

# 按能量筛选（高能量）
high_energy = [s for s in songs if s['energy'] >= 8]

# 按情绪筛选（平静）
calm_songs = [s for s in songs if 'calm' in s['mood_tags']]

# 按任务筛选（学习用）
study_songs = [s for s in songs if 'study' in s['task_tags']]

# 按关键词搜索
keyword = '世界杯'
worldcup = [s for s in songs if keyword in s.get('search_keyword', '')]

## 构建/重建数据库

# 1. 查看可用搜索关键词
python music_database/build_music_db.py --list

# 2. 重新爬取（在项目根目录运行）
python music_database/build_music_db.py -k 50 -o music_database/music_database.json

# 3. 精细化后处理
python music_database/post_process_db.py music_database/music_database.json

# 4. 验证数据库质量
python music_database/verify_db_quality.py

## 关键词列表
共 77 个搜索关键词，覆盖：
  - 情绪类：安静、舒缓、劲爆、欢快、悲伤、励志、梦幻、节奏、力量...
  - 事件类：世界杯、奥运会、NBA、足球、电视剧、游戏、派对...
  - 风格类：古典、摇滚、电子、民谣、嘻哈、爵士...
  - 场景类：学习、运动、放松、开车、通勤、瑜伽、冥想...
  - 歌手类：周杰伦、林俊杰、陈奕迅...

## 注意事项
  - 数据来自QQ音乐公开搜索接口，实际歌曲版权归原公司所有
  - 风格/能量/情绪/乐器等字段为本地推断结果，仅供推荐系统使用
  - 部分关键词可能返回0条结果（如"奥运主题曲"），属正常现象
  - 数据库定期更新可运行 build_music_db.py 重新爬取
  - 本模块依赖 backend 目录下的 qqmusic_source.py 和 models.py