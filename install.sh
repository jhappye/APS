#!/bin/bash
set -e

echo "Installing AI中台服务..."

# 创建目录
sudo mkdir -p /opt/ai-platform
sudo mkdir -p /var/log/ai-platform

# 复制文件（排除 .git, __pycache__, .claude 等）
sudo rsync -av --exclude='.git' --exclude='__pycache__' --exclude='*.pyc' --exclude='.claude' . /opt/ai-platform/

# 创建虚拟环境
cd /opt/ai-platform
python3 -m venv venv
./venv/bin/pip install -r requirements.txt

# 安装 systemd 服务
sudo cp systemd/ai-platform.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable ai-platform

echo "Installation complete!"
echo ""
echo "To start the service:"
echo "  sudo systemctl start ai-platform"
echo ""
echo "To check status:"
echo "  sudo systemctl status ai-platform"