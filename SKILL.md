---
name: Wechat-Toutiao-publisher
description: |
  使用 wenyan（文颜）将 Markdown 文章排版并发布到微信公众号草稿箱。
  当用户要求「发到公众号」「推送草稿」「发布文章」或类似意图时触发。
  支持 8 套内置主题，自动处理图片上传，通过 frontmatter 管理元数据。
  也可通过 cron 定时自动发布。
---

# Wechat-Toutiao-publisher

使用 [文颜（wenyan）](https://github.com/caol64/wenyan) CLI 一键发布 Markdown 到微信公众号草稿箱。

## 发布方式

### 自动发布（cron）

每天 10:30 自动运行，模型只需执行一条命令：

```
python3 skills/Wechat-Toutiao-publisher/scripts/publish-pipeline.py
```

管道脚本读取 `pipeline-config.json`，自动完成全部步骤并输出 JSON 结果。模型只需解析 JSON 并播报。

### 手动发布

```bash
# 单篇发布
python3 skills/Wechat-Toutiao-publisher/scripts/publish-pipeline.py

# 指定文章
wenyan publish -f article.md -c themes/mo-ping.css
```

## 配置（pipeline-config.json）

所有设置集中在一个 JSON 文件，修改无需改代码：

```json
{
  "obsidian_vault": "...",
  "queue_dir": "4-成品层/4-4 AI/4-4-1 AI写作（墨言）/待发文章",
  "published_dir": "4-成品层/4-4 AI/4-4-1 AI写作（墨言）/已发布文章",
  "toutiao_dir": "output/头条待发",
  "wechat": {
    "theme_css": "themes/mo-ping.css",
    "author": "墨言"
  },
  "cover": {
    "template": "literary"
  }
}
```

修改主题/封面模板/作者等信息，改 JSON 即可，cron 下次自动生效。

## 管道步骤（publish-pipeline.py）

```
① find_article     → 从队列取第一篇 .md
② generate_cover   → HTML/CSS 渲染封面（4 套模板）
③ preprocess       → 转换 Obsidian ![[图片]] 语法 + 补齐 frontmatter
④ publish_wechat   → wenyan 发布到微信草稿箱
⑤ render_toutiao   → wenyan 渲染头条 HTML
⑥ archive          → 移到已发布目录
```

输出 JSON：
```json
{"success": true, "title": "...", "wechat_media_id": "...", "toutiao_html": "..."}
```

## 可用主题

| ID | 风格 |
|----|------|
| `default` | 简洁经典 | `orangeheart` | 暖橙优雅 |
| `rainbow` | 多彩清新 | `lapis` | 极简冷蓝 |
| `pie` | 少数派风格 | `maize` | 柔和玉米色 |
| `purple` | 微紫极简 | `phycat` | 薄荷绿层次 |

## 封面模板

| 模板 | 风格 | 适合 |
|------|------|------|
| `literary` | 暖米色 + 衬线字体 | 文学书评 |
| `dark` | 深蓝 + 红色点缀 | 深度思考 |
| `fresh` | 浅绿 + 细线 | 清新随笔 |
| `bold` | 纯白 + 橙色边框 | 观点鲜明 |

## 插图

Obsidian `![[图片名.png]]` 自动转为标准 Markdown 并上传微信。

## Cron 管理

```bash
openclaw cron list              # 查看
openclaw cron disable <id>     # 暂停
openclaw cron enable <id>      # 恢复
```

## 故障排查

| 问题 | 处理 |
|------|------|
| `40164: invalid ip` | `curl -s4 ifconfig.me` 获取 IP → 加到微信 IP 白名单 |
| `40001: invalid credential` | 删 `~/.config/wenyan-md/token.json` |
| 封面图上传失败 | 检查 frontmatter 或自动生成的 /tmp/wap_cover_hq.png |
| 队列为空 | 正常，返回 HEARTBEAT_OK |
