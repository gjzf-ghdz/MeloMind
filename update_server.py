# -*- coding: utf-8 -*-
"""MeloMind 一键更新服务器脚本（HTTP 部署接口版，无需 SSH）
流程: 本地打包 -> POST zip 到 /api/deploy -> 等服务重启 -> 验证
"""
import subprocess
import sys
import os
import time
import urllib.request

SERVER = "http://47.99.92.14:8000"
HERE = os.path.dirname(os.path.abspath(__file__))


def main():
    # 1. 本地打包（会自动生成/复用 deploy_token.txt）
    print("[1/4] 本地打包...")
    r = subprocess.run([sys.executable, "pack_for_deploy.py"] + sys.argv[1:], cwd=HERE)
    if r.returncode != 0:
        print("打包失败")
        sys.exit(1)

    zip_path = os.path.join(HERE, "melomind_deploy.zip")
    token_file = os.path.join(HERE, "backend", "deploy_token.txt")
    with open(token_file, "r", encoding="utf-8") as f:
        token = f.read().strip()
    if not token:
        print("deploy_token.txt 为空")
        sys.exit(1)

    # 2. 上传部署包
    print()
    print("[2/4] 上传部署包到服务器...")
    with open(zip_path, "rb") as f:
        zip_data = f.read()
    req = urllib.request.Request(
        f"{SERVER}/api/deploy",
        data=zip_data,
        headers={"Content-Type": "application/zip",
                 "X-Deploy-Token": token},
        method="POST")
    try:
        resp = urllib.request.urlopen(req, timeout=900)
        print("  服务器响应:", resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        print(f"  部署失败 HTTP {e.code}: {e.read().decode('utf-8', 'ignore')}")
        if e.code == 403:
            print("  提示: 服务器尚未部署新版 server.py（含 /api/deploy 接口），"
                  "或密钥不一致")
        sys.exit(1)
    except Exception as e:
        print(f"  上传失败: {e}")
        sys.exit(1)

    # 3. 等待服务重启完成（大库冷启动加载需 2-4 分钟，最长等 6 分钟）
    print()
    print("[3/4] 等待服务重启（加载 20 万首曲库约需 2-4 分钟）...")
    time.sleep(10)
    recovered = False
    for i in range(70):
        try:
            urllib.request.urlopen(f"{SERVER}/", timeout=5)
            print("  服务已恢复")
            recovered = True
            break
        except Exception:
            if i % 6 == 5:
                print(f"  仍在加载中... 已等 {(i+1)*5} 秒")
            time.sleep(5)
    if not recovered:
        print("  警告: 服务未在 6 分钟内恢复，请到阿里云 Workbench 执行:")
        print("  sudo systemctl status melomind  和  journalctl -u melomind -n 30 --no-pager")
        sys.exit(1)

    # 4. 验证
    print()
    print("[4/4] 验证更新...")
    try:
        resp = urllib.request.urlopen(f"{SERVER}/", timeout=15)
        body = resp.read()
        ok = b"MeloMind" in body
        print("  验证通过，网址已是最新版本" if ok else "  返回内容异常")
    except Exception as e:
        print(f"  访问异常: {e}")

    print()
    print(f"全部完成! 公网网址: {SERVER}")


if __name__ == "__main__":
    main()
