#!/bin/bash
# publish-next.sh — 从队列目录取第一篇 .md，用 wenyan 发布，成功后移到已发布目录
set -euo pipefail

VAULT="/Users/lijingyan/Library/Mobile Documents/iCloud~md~obsidian/Documents/Le"
BASE_DIR="$VAULT/4-成品层/4-4 AI/4-4-1 AI写作（墨言）"
QUEUE_DIR="${QUEUE_DIR:-$BASE_DIR/待发文章}"
PUBLISHED_DIR="${PUBLISHED_DIR:-$BASE_DIR/已发布文章}"
THEME="${THEME:-default}"

# 找第一篇 .md
NEXT=$(find "$QUEUE_DIR" -maxdepth 1 -name "*.md" -type f | sort | head -1)

if [ -z "$NEXT" ]; then
    echo "HEARTBEAT_OK: 队列为空，无待发布文章"
    exit 0
fi

echo "📝 发布: $(basename "$NEXT")"

# 发布
wenyan publish -f "$NEXT" -t "$THEME" 2>&1

if [ $? -eq 0 ]; then
    mv "$NEXT" "$PUBLISHED_DIR/"
    echo "✅ 已发布并归档: $(basename "$NEXT")"
else
    echo "❌ 发布失败: $(basename "$NEXT")"
    exit 1
fi
