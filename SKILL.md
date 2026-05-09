---
name: Wechat-Toutiao-publisher
description: |
  一键将 Obsidian Markdown 排版并发布到微信公众号草稿箱 + 头条号草稿。
  当用户要求「发到公众号」「推送草稿」「发布文章」「同步到头条」或类似意图时触发。
  6 步全自动管道：取文章 → 封面 → 预处理 → 微信草稿 → 头条草稿 → 归档。
  支持 cron 定时；网络失败自动重试；已发文章绝不重复推送（sidecar 续跑）。
---

# Wechat-Toutiao-publisher

发布到微信公众号 + 头条号。基于 [wenyan](https://github.com/caol64/wenyan) + Playwright，
JSON 配置驱动，cron 自动化。

## 触发命令

模型只需执行一条命令：

```
python3 skills/Wechat-Toutiao-publisher/scripts/publish-pipeline.py
```

等价的：

```
python -m publisher --config skills/Wechat-Toutiao-publisher/pipeline-config.json
```

脚本读取 `pipeline-config.json`，自动完成 6 步并输出一行 JSON：

```
① find_article → ② generate_cover → ③ preprocess
→ ④ publish_wechat → ⑤ render_toutiao + publish_toutiao → ⑥ archive
```

## 输出 JSON（模型解析这个就够了）

```json
{
  "success": true,
  "step": "done",
  "article": "/path/article.md",
  "title": "文章标题",
  "wechat_media_id": "abc123",
  "toutiao_html": "/path/article.html",
  "toutiao_draft_url": "https://mp.toutiao.com/...",
  "toutiao_screenshot": "/path/toutiao_draft.png",
  "resumed": false,
  "warnings": [],
  "error": null
}
```

| 字段 | 说明 |
|---|---|
| `success` | 总开关。微信失败 = false；头条失败仅进 warnings 不拖垮整体 |
| `wechat_media_id` | 微信草稿箱 ID |
| `toutiao_draft_url` | 头条草稿页 URL（仅 `toutiao.auto=true` 时有值） |
| `toutiao_html` | 兜底 HTML（半自动模式下用户手动粘贴） |
| `resumed=true` | 本文之前部分步骤已完成，本次跳过；不是异常 |
| `warnings[]` | 非致命降级（最常见：头条登录态过期、selector 失效） |
| `error` | 非 null 即整体失败，按下表回报 |

## 错误回报对照表

| `error` 包含 | 给用户的处置建议 |
|---|---|
| `40164: invalid ip` | 在微信公众平台后台加 cron 主机 IP 白名单（已自动重试 3 次未通过） |
| `40001: invalid credential` | 删 `~/.config/wenyan-md/token.json` 后重跑（凭据致命错误，不会自动重试） |
| `not logged in` | 头条登录态过期，需要在带屏幕的 Mac 跑 `python -m publisher --login-toutiao` |
| `selector not found` | 头条编辑器 DOM 改了，需要更新 `pipeline-config.json` 的 `toutiao.selectors` |
| `config: missing required ...` | 配置文件缺字段，按提示补；schema 校验在启动期 |
| `HEARTBEAT_OK: queue empty` | 队列为空（success=true，正常情况，无需处置） |

## 续跑机制（模型背景知识）

`<queue_dir>/.state/<article>.json` 是 sidecar：成功发到微信后写入 `wechat_published=true` + `media_id`。下次 cron 看到 sidecar **会跳过 step 4**，**绝不向草稿箱重复推送同一文章**。归档成功后 sidecar 自动删除。

用户问「为什么这篇没发」「为什么 cron 跑了但什么都没做」时：
- 检查 `<queue_dir>/.state/` 看是否有半完成的状态
- 看返回 JSON 的 `resumed` 字段
- 想强制重发同一篇：删除对应 `.state/<article>.json`

## 重试策略（模型背景知识）

| 步骤 | 重试 | 致命模式（立即放弃） |
|---|---|---|
| WeChat publish | 默认 3 次（2s → 4s 退避） | `40001`、`40013`、`invalid credential/appid` |
| Toutiao auto | 默认 2 次，**仅 `save_draft` 之前** | `not logged in`、`selector not found` |
| cover / preprocess / toutiao render | 不重试 | — |

## 配置（pipeline-config.json）

集中管理路径、主题、封面、自动化开关、重试参数、通知。

首次部署：

```bash
cp pipeline-config.example.json pipeline-config.json
$EDITOR pipeline-config.json
```

详细字段说明见 [README.md](./README.md) 「配置参考」章节。

## 主题与封面模板

排版主题（`wechat.theme_css`，传给 wenyan）：自定义 `themes/mo-ping.css`，或用 wenyan 内置的 `default / orangeheart / rainbow / lapis / pie / maize / purple / phycat`。

封面模板（`cover.template`，存在 `themes/covers/*.json`）：

| ID | 风格 |
|----|------|
| `literary` | 暖米色 + 衬线字体 |
| `dark` | 深蓝 + 红色点缀 |
| `fresh` | 浅绿 + 细线 |
| `bold` | 纯白 + 橙色边框 |

加新模板：往 `themes/covers/<name>.json` 写一份，不用改代码。

## 插图

Obsidian `![[图片名.png]]` 自动转标准 Markdown，并由 wenyan 上传微信 CDN。vault 索引一次构建。

## Cron 管理

```bash
openclaw cron list              # 查看所有任务
openclaw cron disable <id>      # 暂停
openclaw cron enable <id>       # 恢复
openclaw cron run <id>          # 立即触发一次（手动测试）
```

## 头条登录维护（管理操作，非发布流程）

```bash
python -m publisher --check-toutiao    # 健康检查 → {"logged_in": true|false}
python -m publisher --login-toutiao    # 首次扫码或重登（需图形终端）
```

模型不应在常规发布流程中调用这两个命令。仅当用户问「头条登录还在吗」或 `error` 含 `not logged in` 时建议用户手动跑。
