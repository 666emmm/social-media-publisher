#!/usr/bin/env bash
set -euo pipefail

# ============================================================
# 旧版数据迁移脚本 — Linux / macOS
# ============================================================
#
# 本脚本会调用 scripts/migrate_legacy_data.py，
# 把旧版 Windows 客户端的用户数据迁移到当前项目的 data/ 目录。
#
# 迁移前请先执行 ./start.sh 启动后端（需要 5409 端口可达）。
# 脚本会先备份当前 data/ 到 data.bak.YYYYMMDD_HHMMSS/，再迁移数据。

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# 默认源目录：Linux/macOS 上 LOCALAPPDATA 通常未设置，回退到 ~/.local/share
DEFAULT_SOURCE="${LOCALAPPDATA:-$HOME/.local/share}/Social Auto Upload Web UI"
PROJECT_DATA="$SCRIPT_DIR/data"

cat <<EOF

============================================================
  旧版数据迁移到新版 data/ 目录
============================================================

需要迁移的源目录说明：

  1) 旧版 Windows 客户端的用户数据目录
     路径: $DEFAULT_SOURCE
     包含 cookies/、cookiesFile/、db/、videoFile/ 四个子目录

  2) Github clone 直接启动的项目
     路径: $PROJECT_DATA  (即项目根目录下的 data 目录)

提示：先执行 ./start.sh 启动后端，再运行本脚本。

============================================================

EOF

read -r -p "请输入选项 1 或 2 (1=旧版Windows客户端, 2=项目data目录), 默认 1: " choice
choice="${choice:-1}"

SOURCE=""
case "$choice" in
    1)
        SOURCE="$DEFAULT_SOURCE"
        if [[ ! -d "$SOURCE" ]]; then
            echo
            echo "[错误] 默认目录不存在: $SOURCE"
            echo "请先在 Windows 客户端安装并运行一次旧版程序。"
            exit 1
        fi
        ;;
    2)
        SOURCE="$PROJECT_DATA"
        ;;
    *)
        echo
        echo "[错误] 无效选项: $choice"
        exit 1
        ;;
esac

echo
echo "源目录: $SOURCE"
echo "目标目录: $PROJECT_DATA"
echo
read -r -p "按 Enter 继续，Ctrl+C 取消..."

python3 "$SCRIPT_DIR/scripts/migrate_legacy_data.py" \
    --source "$SOURCE" \
    --target "$PROJECT_DATA" \
    --yes
