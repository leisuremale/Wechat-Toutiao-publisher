#!/bin/bash
# render-toutiao.sh — 将 Markdown 渲染为头条号兼容 HTML，复制到剪贴板
set -euo pipefail

if [ $# -lt 1 ]; then
    echo "用法: $0 <article.md> [theme]"
    echo "  theme: 默认 mo-ping，可选 phycat|pie|lapis|orangeheart|purple|maize|rainbow|default"
    exit 1
fi

ARTICLE="$1"
THEME="${2:-mo-ping}"

# 如果是内置主题，用 -t；否则用 -c 加载自定义 CSS
if [ "$THEME" = "mo-ping" ]; then
    THEME_ARG="-c /Users/lijingyan/.openclaw/workspace-mo-ping/skills/Wechat-Toutiao-publisher/themes/mo-ping.css"
else
    THEME_ARG="-t $THEME"
fi

echo "🎨 渲染中（主题: $THEME）..."
HTML=$(~/.local/bin/wenyan render -f "$ARTICLE" $THEME_ARG 2>&1)

if [ -z "$HTML" ]; then
    echo "❌ 渲染失败"
    exit 1
fi

# 复制到剪贴板
echo "$HTML" | pbcopy
echo "✅ HTML 已复制到剪贴板（$(echo "$HTML" | wc -c | tr -d ' ') bytes）"
echo "📋 打开 https://mp.toutiao.com → 文章 → 新建 → 粘贴即可"
