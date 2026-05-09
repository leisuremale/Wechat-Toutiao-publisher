# Wechat-Toutiao-Publisher

> 一键将 Obsidian Markdown 排版发布到微信公众号 + 头条号。JSON 驱动，cron 自动化，零手动排版。

[![wenyan](https://img.shields.io/badge/powered_by-wenyan-v2.0.8-blue)](https://github.com/caol64/wenyan)
[![platform](https://img.shields.io/badge/platform-WeChat_%7C_Toutiao-green)]()
[![automation](https://img.shields.io/badge/automation-cron_%2B_JSON-orange)]()

## 亮点

### 一条命令完成 6 步

```bash
python -m publisher
# → {"success": true, "wechat_media_id": "...", "toutiao_draft_url": "...", ...}
```

```
① 取文章 → ② 生成封面 → ③ 预处理（图片+frontmatter）
→ ④ 微信发布 → ⑤ 头条渲染 + 自动建草稿 → ⑥ 归档
```

### 双平台全自动

| 平台 | 模式 | 实现 |
|------|------|------|
| 微信公众号 | wenyan publish → 草稿箱 | 全自动（API） |
| 头条号 | Playwright 模拟登录 → 建草稿 | 全自动（首次扫码后免登录） |
| 头条号（兜底） | wenyan render → HTML 文件 | 半自动粘贴 |

> 全自动只**保存草稿**，最终发布保留人工审核（避免风控、避免错发）。

### 重试 + 续跑

- 微信发布默认 3 次指数退避；遇到 `40001 invalid credential` 等致命错误立即放弃
- Toutiao 自动发布只在 `save_draft` **之前**的步骤可重试，之后绝不重试以避免重复草稿
- 已成功发到微信的文章会写 sidecar JSON 到 `<queue_dir>/.state/`；下次 cron 直接跳过 step 4，绝不会向草稿箱重复推送同一文章

### 4 套 HTML/CSS 封面模板，JSON 配置

模板存在 `themes/covers/*.json`，加新模板不改代码：

```json
// themes/covers/literary.json
{ "name": "文学", "bg": "#f5f0e8", "accent": "#8b4513", "decor": "top", ... }
```

| 模板 | 风格 | 适合 |
|------|------|------|
| `literary` | 暖米色 + 衬线字体 + 装饰线 | 文学书评 |
| `dark` | 深蓝 + 红色点缀 + 无衬线 | 深度思考 |
| `fresh` | 浅绿 + 细线 + 留白 | 清新随笔 |
| `bold` | 纯白 + 橙色边框 | 观点鲜明 |

### Obsidian 原生工作流

`![[图片名.png]]` 自动转换 + 上传到微信 CDN，不需要手动处理路径。Vault 索引一次构建，多图查询 O(1)。

```markdown
![[村上春树.jpg]]           # vault 内自动搜索
![[assets/封面.png]]        # 相对路径
![](/absolute/path/img.jpg) # 标准 Markdown
```

### 正文配图（书封 + 金句卡）

文章不再只有封面，正文里也有视觉锚点：

- **书封**：从 frontmatter `book:` 或标题 `《...》` 自动抽书名 → 当当 / 豆瓣 / Google Books 抓封面 → 缓存 → 插到文章顶部
- **手动覆盖**：frontmatter 加 `cover_url:` 即用指定图（URL / 绝对路径 / vault 相对路径），免去搜索失败
- **金句卡**：扫 markdown 里的 `> 引用块`，每段渲染成 900x500 视觉卡片（Playwright + HTML/CSS 模板），插在引用之后保留可访问性。`max_per_article` 防止全是卡片劣化阅读节奏

```json
"illustrate": {
  "book_cover": { "enabled": true, "sources": ["dangdang", "douban", "google_books"] },
  "quote_cards": { "enabled": true, "template": "classic", "max_per_article": 4 }
}
```

豆瓣最近反爬严，**当当作为主源**更稳定。诊断哪个源能用：

```bash
python -m publisher --test-cover "百年孤独"
# {"book": "百年孤独", "results": [
#   {"source": "dangdang", "ok": true,  "url": "..."},
#   {"source": "douban",   "ok": false, "url": null},
#   ...
# ]}
```

封面找不到时，frontmatter 写死 URL 兜底：

```yaml
---
book: 百年孤独
cover_url: https://img3m0.ddimg.cn/46/30/29819440-1_b_1762827510.jpg
---
```

模板存在 `themes/quotes/*.json`（`classic` / `dark` / `minimal`），加新模板不改代码。

### Schema 校验 + 滚动日志 + 通知钩子

- 启动期校验 `pipeline-config.json`，缺字段直接报清晰错误：
  ```
  ValueError: config: missing required 'wechat.author'
  ```
- 配置 `log.dir` → 按天切分日志，保留 14 天
- 配置 `notify.webhook_url` / `notify.osascript` → 失败推手机

## 架构

```
Wechat-Toutiao-publisher/
├── pipeline-config.json     # 所有配置
├── SKILL.md                 # AI Agent 触发规则（openclaw）
├── README.md                # 本文件
├── SETUP-OPENCLAW.md        # 部署到一台新 Mac
├── publisher/               # Python 包（核心）
│   ├── __main__.py          # `python -m publisher` 入口
│   ├── config.py            # dataclass schema + 启动期验证
│   ├── pipeline.py          # 6 步编排 + retry + resume
│   ├── cover.py             # 封面渲染（playwright 懒加载）
│   ├── preprocess.py        # Obsidian ![[..]] + frontmatter
│   ├── wenyan.py            # wenyan CLI 薄封装
│   ├── toutiao.py           # 头条 Playwright 自动化
│   ├── retry.py             # 退避 + 致命错误黑名单
│   ├── state.py             # 续跑 sidecar
│   ├── illustrate.py        # 书封 + 金句卡（正文配图）
│   ├── notify.py            # webhook + osascript
│   └── log.py               # 滚动文件日志
├── scripts/
│   ├── publish-pipeline.py  # 转发到 publisher（cron 兼容）
│   ├── generate-cover.py    # 同上
│   ├── preprocess-article.py
│   └── wenyan-wrapper.sh    # Keychain 凭据注入
└── themes/
    ├── mo-ping.css          # 排版主题
    ├── covers/              # 封面模板（JSON）
    │   ├── literary.json
    │   ├── dark.json
    │   ├── fresh.json
    │   └── bold.json
    └── quotes/              # 金句卡模板（JSON）
        ├── classic.json
        ├── dark.json
        └── minimal.json
```

## 快速开始

> 部署到一台新 Mac 走这里：[SETUP-OPENCLAW.md](./SETUP-OPENCLAW.md)。

### 依赖

```bash
npm install -g @wenyan-md/cli
pip3 install playwright
python3 -m playwright install chromium
```

### 凭据 + wrapper

```bash
security add-generic-password -s "md2wechat-appid"  -a "md2wechat" -w "wx..."
security add-generic-password -s "md2wechat-secret" -a "md2wechat" -w "..."
ln -sf "$(pwd)/scripts/wenyan-wrapper.sh" ~/.local/bin/wenyan
```

### 配置文件

```bash
cp pipeline-config.example.json pipeline-config.json
$EDITOR pipeline-config.json     # 改成本机路径
```

`pipeline-config.json` 已在 `.gitignore` 中，不会被误提交。example 文件展示所有可选字段（`null` 即「使用默认」）。最小可用：

```json
{
  "obsidian_vault": "/Users/you/Library/Mobile Documents/iCloud~md~obsidian/Documents/Vault",
  "queue_dir": "AI写作/待发文章",
  "published_dir": "AI写作/已发布文章",
  "toutiao_dir": "/Users/you/output/头条待发",
  "wechat": { "theme_css": "themes/mo-ping.css", "author": "墨言" },
  "cover": { "template": "literary" }
}
```

### 运行

```bash
python -m publisher                           # 主入口
python -m publisher --config /path/to.json    # 指定配置
python -m publisher --login-toutiao           # 头条首次扫码（headed）
python -m publisher --check-toutiao           # 检查头条登录态

# 兼容旧调用（cron 任务无需改动）
python3 scripts/publish-pipeline.py
```

## 配置参考

### 必填

```json
{
  "obsidian_vault": "...",
  "queue_dir": "...",
  "published_dir": "...",
  "toutiao_dir": "...",
  "wechat": { "theme_css": "...", "author": "..." },
  "cover": { "template": "literary" }
}
```

启动期 schema 缺字段会立即抛 `ValueError: config: missing required '<path>'`。

### 可选

```json
{
  "wenyan_bin": "/custom/path/to/wenyan",

  "cover": {
    "template": "literary",
    "width": 900,
    "height": 500,
    "templates_dir": "/extra/covers",
    "subtitle": "墨 言 书 评"
  },

  "toutiao": {
    "auto": false,
    "user_data_dir": "/Users/you/.openclaw/toutiao-profile",
    "headless": true,
    "screenshot_dir": "/Users/you/.openclaw/toutiao-shots",
    "timeout_ms": 60000,
    "selectors": {
      "title": "input[placeholder*='标题']",
      "editor": "div[contenteditable='true']",
      "cover_button": "text=封面",
      "cover_input": "input[type='file']",
      "save_draft": "text=存草稿"
    }
  },

  "retry": {
    "wechat_attempts": 3,
    "toutiao_attempts": 2,
    "base_delay": 2.0,
    "max_delay": 30.0
  },

  "notify": {
    "webhook_url": "https://api.day.app/<key>/...",
    "osascript": true
  },

  "log": {
    "dir": "/var/log/publisher",
    "level": "INFO"
  },

  "illustrate": {
    "book_cover": {
      "enabled": true,
      "sources": ["dangdang", "douban", "google_books"],
      "cache_dir": null,
      "timeout": 10
    },
    "quote_cards": {
      "enabled": true,
      "template": "classic",
      "templates_dir": null,
      "min_chars": 15,
      "max_per_article": 4
    }
  }
}
```

## 头条全自动 vs 半自动

### 半自动（默认，零配置）

不配 `toutiao.auto`，pipeline 把 wenyan 渲染好的 HTML 写到 `toutiao_dir/<title>.html`。打开 https://mp.toutiao.com → 文章 → 新建 → 复制粘贴。

### 全自动

```json
{ "toutiao": { "auto": true, "user_data_dir": "/Users/you/.openclaw/toutiao-profile" } }
```

> `user_data_dir` 包含登录 cookie，**严禁入库**。建议放仓库外、`chmod 700`。

首次扫码（需要图形终端）：

```bash
python -m publisher --login-toutiao
```

健康检查（cron 跑前可用，过期 exit 1）：

```bash
python -m publisher --check-toutiao
# {"logged_in": true}
```

DOM 选择器配置在 `toutiao.selectors`，mp.toutiao.com 改版时修配置而不是改代码。

## 失败恢复

### Sidecar 续跑

成功的步骤会写 `<queue_dir>/.state/<article>.json`：

```json
{
  "version": 1,
  "wechat_published": true,
  "wechat_media_id": "abc123",
  "toutiao_drafted": true,
  "toutiao_draft_url": "https://mp.toutiao.com/...",
  "updated_at": "2026-05-09T10:30:00+00:00"
}
```

下次 cron 看到 sidecar 会**跳过已完成的步骤**。归档成功后 sidecar 自动删除。

手动重跑同一篇：删除对应的 `.state/<article>.json` 即可。

### 重试策略

| 步骤 | 重试 | 致命模式（不重试） |
|------|------|-------------------|
| cover / preprocess / toutiao render | 否 | — |
| WeChat publish | 默认 3 次（2s → 4s 退避） | `40001 invalid credential`、`40013 invalid appid` |
| Toutiao auto-publish | 默认 2 次 | `not logged in`、`selector not found`；**`save_draft` 之后绝不重试** |

## Cron 定时

```bash
openclaw cron add --agent mo-ping --name "wechat-publish" \
  --cron "30 10 * * *" --tz Asia/Shanghai \
  --message "cd /path/to/Wechat-Toutiao-publisher && python -m publisher"
```

## 故障排查

| 现象 | 处理 |
|------|------|
| `config: missing required '<key>'` | schema 校验报错，按提示补字段 |
| `40164: invalid ip` | `curl -s4 ifconfig.me` → 加微信公众号 IP 白名单。retry 会自动重试 3 次 |
| `40001: invalid credential` | 删 `~/.config/wenyan-md/token.json`；致命模式，不会重试 |
| 头条 `not logged in` | `python -m publisher --login-toutiao` 重新扫码 |
| 头条 `selector not found` | mp.toutiao.com DOM 改了。inspect 当前页面，自定义 selector 写到 `toutiao.selectors` |
| 队列为空 | `{"success": true, "message": "HEARTBEAT_OK: queue empty"}`，正常 |
| cron 重跑同一文章 | 不会重发到微信（sidecar 跳过 step 4）；头条会重试 |
| 想强制重发 | 删除 `<queue_dir>/.state/<article>.json` |
| Playwright 启动慢 | 一天一次发布忽略；每次 ~2-3s 冷启 chromium |

## 依赖项目

- [wenyan（文颜）](https://github.com/caol64/wenyan) — 多平台 Markdown 排版发布
- [Playwright](https://playwright.dev) — 封面渲染 + 头条自动化
- macOS Keychain — 凭据管理

## 部署

部署到一台新 Mac？看 [SETUP-OPENCLAW.md](./SETUP-OPENCLAW.md)。

## License

MIT
