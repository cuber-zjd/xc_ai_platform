#!/bin/bash
# OnlyOffice 中文字体安装脚本
# 在服务器 192.168.14.44 上执行此脚本

# 创建字体目录
mkdir -p ./data/onlyoffice/fonts

echo "=== OnlyOffice 中文字体安装 ==="

# 方法 1: 从系统复制常用中文字体 (如果服务器是 Ubuntu/Debian)
echo "正在安装字体包..."
sudo apt-get update
sudo apt-get install -y fonts-wqy-microhei fonts-wqy-zenhei fonts-noto-cjk fonts-noto-cjk-extra

# 复制系统字体到 OnlyOffice 字体目录
echo "正在复制字体文件..."
cp -r /usr/share/fonts/truetype/wqy ./data/onlyoffice/fonts/ 2>/dev/null || true
cp -r /usr/share/fonts/opentype/noto ./data/onlyoffice/fonts/ 2>/dev/null || true
cp -r /usr/share/fonts/truetype/noto ./data/onlyoffice/fonts/ 2>/dev/null || true

# 方法 2: 从 Windows 复制常用字体 (如果你有 Windows 字体)
# 将以下字体复制到 ./data/onlyoffice/fonts/ 目录:
# - simsun.ttc (宋体)
# - simhei.ttf (黑体)
# - simkai.ttf (楷体)
# - simfang.ttf (仿宋)
# - msyh.ttc (微软雅黑)
# - msyhbd.ttc (微软雅黑 Bold)

echo "=== 重新生成 OnlyOffice 字体缓存 ==="
# 在 OnlyOffice 容器内执行字体刷新
docker exec ai_platform_onlyoffice /bin/bash -c "
    # 更新字体缓存
    fc-cache -f -v
    
    # 重新生成 OnlyOffice 字体列表
    cd /var/www/onlyoffice/documentserver/server/tools
    ./allfontsgen
    ./allthemesgen
"

echo "=== 重启 OnlyOffice 服务 ==="
docker-compose restart onlyoffice

echo "完成! 请等待 1-2 分钟让 OnlyOffice 完全启动。"
