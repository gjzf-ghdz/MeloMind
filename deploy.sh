#!/bin/bash
# MeloMind 云服务器一键部署脚本
# 在服务器上用 root 运行: sudo bash deploy.sh
set -e

INSTALL_DIR=/opt/melomind
SERVICE_NAME=melomind

echo "=========================================="
echo "  MeloMind 服务器部署脚本"
echo "=========================================="
echo

# 1. 检查是否 root
if [ "$EUID" -ne 0 ]; then
    echo "请使用 root 或 sudo 运行此脚本:"
    echo "  sudo bash deploy.sh"
    exit 1
fi

# 2. 检查/安装 Python3
echo "[1/5] 检查 Python3..."
if ! command -v python3 &> /dev/null; then
    echo "  安装 Python3..."
    apt-get update -qq
    apt-get install -y -qq python3
fi
echo "  Python3: $(python3 --version)"

# 3. 解压或复制文件
echo "[2/5] 部署文件..."
mkdir -p /opt
if [ -f "melomind_deploy.zip" ]; then
    echo "  解压 melomind_deploy.zip..."
    apt-get install -y -qq unzip 2>/dev/null || true
    unzip -o melomind_deploy.zip -d /opt/
    echo "  文件已解压到 $INSTALL_DIR"
elif [ -d "melomind" ]; then
    echo "  复制 melomind 目录..."
    cp -r melomind /opt/
    echo "  文件已复制到 $INSTALL_DIR"
else
    echo "  错误: 未找到 melomind_deploy.zip 或 melomind 目录"
    echo "  请先上传项目文件到当前目录"
    exit 1
fi

# 4. 初始化数据文件
echo "[3/5] 初始化数据文件..."
mkdir -p $INSTALL_DIR/backend
touch $INSTALL_DIR/backend/users.json
touch $INSTALL_DIR/backend/favorites.json
touch $INSTALL_DIR/backend/history.json

[ -s $INSTALL_DIR/backend/users.json ] || echo '{"users":[]}' > $INSTALL_DIR/backend/users.json
[ -s $INSTALL_DIR/backend/favorites.json ] || echo '{}' > $INSTALL_DIR/backend/favorites.json
[ -s $INSTALL_DIR/backend/history.json ] || echo '{}' > $INSTALL_DIR/backend/history.json

echo "  数据文件就绪"

# 5. 配置 systemd 服务（开机自启 + 崩溃自动重启）
echo "[4/5] 配置开机自启服务..."
cat > /etc/systemd/system/$SERVICE_NAME.service << 'UNIT'
[Unit]
Description=MeloMind Adaptive Music Recommender
After=network.target

[Service]
Type=simple
WorkingDirectory=/opt/melomind/backend
ExecStart=/usr/bin/python3 -u server.py
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
UNIT

systemctl daemon-reload
systemctl enable $SERVICE_NAME
systemctl restart $SERVICE_NAME

# 6. 验证服务
echo "[5/5] 启动服务..."
sleep 3
if systemctl is-active --quiet $SERVICE_NAME; then
    echo "  服务运行中"
else
    echo "  服务启动失败！查看日志："
    journalctl -u $SERVICE_NAME -n 20 --no-pager
    exit 1
fi

# 7. 获取公网 IP
PUBLIC_IP=$(curl -s --max-time 5 ifconfig.me 2>/dev/null || curl -s --max-time 5 ip.sb 2>/dev/null || echo "你的服务器公网IP")

echo
echo "=========================================="
echo "  部署完成！"
echo
echo "  访问地址: http://$PUBLIC_IP:8000"
echo
echo "  服务管理命令:"
echo "    查看状态: systemctl status melomind"
echo "    重启服务: sudo systemctl restart melomind"
echo "    查看日志: journalctl -u melomind -f"
echo "    停止服务: sudo systemctl stop melomind"
echo
echo "  数据备份:"
echo "    用户数据: /opt/melomind/backend/users.json"
echo "    收藏数据: /opt/melomind/backend/favorites.json"
echo "    历史数据: /opt/melomind/backend/history.json"
echo "=========================================="
