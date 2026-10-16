# -*- coding: utf-8 -*-
"""
打包 MeloMind 项目用于云服务器部署。
生成 melomind_deploy.zip，包含所有必要文件，排除临时文件和缓存。
"""
import os
import zipfile
import sys

PROJECT = os.path.dirname(os.path.abspath(__file__))
OUTPUT = os.path.join(PROJECT, "melomind_deploy.zip")

# 需要包含的文件（相对于 PROJECT 目录）
INCLUDE_FILES = {
    # backend
    "backend/server.py",
    "backend/recommender.py",
    "backend/local_music_db.py",
    "backend/auth.py",
    "backend/favorites.py",
    "backend/history.py",
    "backend/llm_engine.py",
    "backend/models.py",
    "backend/special_noun_detector.py",
    "backend/audio_preview.py",
    "backend/music_strategy.py",
    "backend/music_relevance.py",
    "backend/qqmusic_source.py",
    "backend/lyrics_lang.json",
    "backend/llm_config.json",
    # 数据文件（运行时用户数据，不打包，避免覆盖服务器数据）
    # users.json / favorites.json / history.json 由服务器端自动初始化
    # 部署密钥（远程更新接口鉴权用）
    "backend/deploy_token.txt",
    # frontend
    "frontend/index.html",
    "frontend/app.js",
    "frontend/style.css",
    # music_database
    "music_database/music_database.json",
    "music_database/event_keywords.json",
    # 部署脚本
    "deploy.sh",
}

# 自动生成部署密钥（仅首次）
TOKEN_FILE = os.path.join(PROJECT, "backend", "deploy_token.txt")
if not os.path.exists(TOKEN_FILE):
    import secrets
    with open(TOKEN_FILE, "w", encoding="utf-8") as f:
        f.write(secrets.token_urlsafe(24) + "\n")
    print("已生成部署密钥: backend/deploy_token.txt")

def main():
    # 支持增量打包：python pack_for_deploy.py backend/recommender.py ...
    # （默认仍然打包 INCLUDE_FILES 全量；只传部分文件时用于快速更新代码）
    include = set(sys.argv[1:]) if len(sys.argv) > 1 else INCLUDE_FILES
    if len(sys.argv) > 1:
        print("增量打包", len(include), "个文件（不包含曲库）")

    # 检查所有文件是否存在
    missing = []
    for f in include:
        full = os.path.join(PROJECT, f)
        if not os.path.exists(full):
            missing.append(f)

    if missing:
        print("以下文件不存在，请检查：")
        for f in missing:
            print(f"  {f}")
        # 不退出，继续打包存在的文件

    # 需要转换换行符为 LF 的文件（Linux 脚本）
    LF_FILES = {".sh"}

    # 打包
    count = 0
    total_size = 0
    with zipfile.ZipFile(OUTPUT, 'w', zipfile.ZIP_DEFLATED) as zf:
        for rel_path in sorted(include):
            full_path = os.path.join(PROJECT, rel_path)
            if os.path.exists(full_path):
                arcname = os.path.join("melomind", rel_path)
                ext = os.path.splitext(rel_path)[1].lower()

                if ext in LF_FILES:
                    # 读取内容，转换 CRLF -> LF
                    with open(full_path, 'r', encoding='utf-8') as f:
                        content = f.read()
                    content = content.replace('\r\n', '\n').replace('\r', '\n')
                    zf.writestr(arcname, content)
                    size = len(content.encode('utf-8'))
                else:
                    size = os.path.getsize(full_path)
                    zf.write(full_path, arcname)

                count += 1
                total_size += size
                print(f"  + {rel_path} ({size/1024:.1f} KB)")
            else:
                print(f"  - 跳过（不存在）: {rel_path}")

    print()
    print(f"打包完成: {OUTPUT}")
    print(f"  文件数: {count}")
    print(f"  总大小: {total_size/1024/1024:.1f} MB")
    print(f"  ZIP 大小: {os.path.getsize(OUTPUT)/1024/1024:.1f} MB")

if __name__ == "__main__":
    main()
