# Wechat-Toutiao-Publisher

> 把 Obsidian  vault 变成自动化内容发布引擎 —— 写 Markdown，剩下的交给 pipeline。

[![wenyan](https://img.shields.io/badge/render-wenyan_v2.0.8-blue)](https://github.com/caol64/wenyan)
[![platform](https://img.shields.io/badge/publish-WeChat_%7C_Toutiao-green)]()
[![automation](https://img.shields.io/badge/run-cron_%2B_JSON-orange)]()
[![license](https://img.shields.io/badge/license-MIT-lightgrey)]()

---

## 与其他方案对比

市面上的「Markdown 转公众号」工具很多，但大多只解决"排版"这一个环节。真正的内容发布链条是：写 → 配图 → 排版 → 发布 → 归档。每一步断裂，你就多一次手动操作。

| 能力 | wenyan CLI | md2wechat | markdown-here | wechat-article-formatter | **本项目** |
|------|:--:|:--:|:--:|:--:|:--:|
| Markdown → 微信 | ✅ | ✅ | ✅ | ✅ | ✅ |
| CSS 主题定制 | ✅ | ❌ | ❌ | 内建 | ✅ + 自定义 |
| Obsidian `![[...]]` 原生支持 | ❌ | ❌ | ❌ | ❌ | ✅ vault 内搜索 |
| 自动化队列 → 发布 → 归档 | ❌ | ❌ | ❌ | ❌ | ✅ cron 一条命令 |
| 微信 + 头条双平台 | 半自动 | ❌ | ❌ | ❌ | ✅ 全自动 |
| 头条号 Playwright 自动发 | ❌ | ❌ | ❌ | ❌ | ✅ 扫码一次免登 |
| 正文配图（书封 + 摄影图） | ❌ | ❌ | ❌ | ❌ | ✅ Pexels + 当当 + 豆瓣 |
| 金句 `"..."` → 引用块自动转换 | ❌ | ❌ | ❌ | ❌ | ✅ 智能收窄 |
| 续跑 · 永不重复发 | ❌ | ❌ | ❌ | ❌ | ✅ sidecar JSON |
| 重试 + 致命错误识别 | ❌ | ❌ | ❌ | ❌ | ✅ 3 次指数退避 |
| Schema 校验启动报错 | ❌ | ❌ | ❌ | ❌ | ✅ 缺字段清晰提示 |
| macOS Keychain 凭据 | ❌ | ❌ | ❌ | ❌ | ✅ 不落盘 |
| 失败推手机（Bark / 系统通知） | ❌ | ❌ | ❌ | ❌ | ✅ |
| 部署到第二台 Mac | 重装 | 重装 | 重装 | 重装 | ✅ rsync + 两条命令 |

### 一句话：它不止是「排版工具」，而是从 Obsidian 草稿到双平台草稿箱的**全自动内容管线**。

---

## 一条命令，六步走完

```bash
python -m publisher
# → {"success": true, "wechat_media_id": "...", "stock_images": 3, ...}
```

```
① 取文章 → ② 封面渲染 → ③ 正文配图（书封 + 主题摄影 + 引号转引用块）
→ ④ 微信发布 → ⑤ 头条渲染 → ⑥ 归档
```

输入是 Obsidian 里的一篇 `.md`，输出是微信草稿箱一条待审草稿 + 头条待发 HTML + 源文件自动归档。整个过程不需要打开浏览器、不需要复制粘贴、不需要调整格式。

---

## 正文配图：文章不再是一堵字墙

三套独立的配图子系统，按需开关，互不干扰：

| 子系统 | 做什么 | 如何触发 |
|--------|--------|----------|
| 📖 书封 | 自动搜书名 → 抓封面图 → 插文首 | frontmatter `book:` 或标题 `《...》` |
| 📸 主题摄影 | Pexels / Wikimedia 搜图 → 按 H2 章节插入 | frontmatter `image_keywords:` 或默认意境词库 |
| 💬 引号转引用块 | `"金句"` → `> 金句`（≤4 行短引用自动识别，长段落不误转） | 自动 |

```yaml
---
book: 百年孤独
image_keywords:
  - latin america
  - magical realism
---
```

三句话配好图，不用离开 Obsidian。书封优先从当当搜索（比豆瓣稳定），支持 `cover_url:` 手动兜底。摄影图 Pexels API key 存在 macOS Keychain，配置文件里不落盘。

---

## 排版：微信里的「出版级」阅读体验

基于 wenyan v2.0.8 渲染引擎 + 自定义 `mo-ping.css`：

- 正文 15px 左对齐，段间距 16px，左右缩进 16px
- 引用块左侧 3px 竖线，仅比文字高出 1px，贴合不突兀
- 分隔线上下 32px 留白，视觉节奏舒适
- 配图段前 16px 间距，与正文段落统一
- PingFang SC / Microsoft YaHei 字体栈

`themes/mo-ping.css` 可以直接改，下一个 cron 周期自动生效，不改代码。

---

## 健壮性：不是「跑一次看命」

### 续跑 + 防重复

每篇处理中的文章有 `<queue>/.state/<article>.json` sidecar：

```json
{
  "wechat_published": true,
  "wechat_media_id": "abc123",
  "toutiao_drafted": true,
  "toutiao_draft_url": "https://mp.toutiao.com/..."
}
```

cron 下次跑看到 sidecar 自动跳过已完成步骤。**同一篇文章绝不会被推两次到微信草稿箱。**

### 重试策略

| 步骤 | 重试次数 | 退避 | 致命错误（不重试） |
|------|:--:|------|------|
| 微信发布 | 3 | 2s → 4s 指数 | `40001` 凭证失效、`40013` appid 错误 |
| 头条自动发 | 2 | 同上 | 未登录、选择器失效；`save_draft` 之后绝不重试 |

### Schema 启动校验

`pipeline-config.json` 缺字段不会跑到一半炸 —— 启动时直接报：

```
ValueError: config: missing required 'wechat.author'
```

### 双保险凭据

微信 AppID/Secret → macOS Keychain；Pexels API key → Keychain。配置文件里只有 `null`，代码运行时从 Keychain 读取。

---

## 双平台

| 平台 | 方式 | 状态 |
|------|------|:--:|
| 微信公众号 | wenyan API → 草稿箱 | 全自动 |
| 头条号 | Playwright 模拟登录 → 建草稿 | 扫码一次后全自动 |
| 头条号（兜底） | wenyan render → HTML | 手动粘贴 |

所有草稿**仅保存不发布**，最终发布保留人工审核环节 —— 避免风控，避免错发。

---

## 结构

```
Wechat-Toutiao-publisher/
├── pipeline-config.json          # 唯一配置文件（gitignored）
├── publisher/                    # Python 包
│   ├── pipeline.py               # 6 步编排 + 续跑 + 重试
│   ├── illustrate.py             # 书封 + 金句卡 + 引号规范化
│   ├── stockimg.py               # Pexels + Wikimedia 摄影配图
│   ├── cover.py                  # HTML/CSS 封面渲染（Playwright）
│   ├── toutiao.py                # 头条 Playwright 自动化
│   ├── wenyan.py                 # wenyan CLI 薄封装
│   ├── preprocess.py             # Obsidian ![[...]] 转换
│   ├── config.py                 # dataclass schema + 启动校验
│   ├── state.py                  # 续跑 sidecar
│   ├── retry.py                  # 退避 + 致命错误黑名单
│   ├── notify.py                 # webhook + macOS 通知
│   └── log.py                    # 按天切分 + 14 天保留
├── themes/
│   ├── mo-ping.css               # 排版主题
│   ├── covers/                   # 4 套封面模板（JSON）
│   └── quotes/                   # 3 套金句卡模板（JSON）
└── scripts/                      # 兼容旧 cron + wenyan wrapper
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

## 配置速览

所有配置在 `pipeline-config.json`（已 gitignored），缺字段启动时报错。完整模板见 `pipeline-config.example.json`。

必填：obsidian_vault / queue_dir / published_dir / toutiao_dir / wechat / cover

关键可选：

```json
{
  "illustrate": {
    "book_cover":   { "enabled": true,  "sources": ["dangdang", "douban"] },
    "quote_cards":  { "enabled": false },
    "stock_images": { "enabled": true,  "source": "pexels", "fallback": "wikimedia",
                      "count_per_article": 3, "license_attribution": false }
  },
  "toutiao": { "auto": false },
  "retry":   { "wechat_attempts": 3, "base_delay": 2.0 },
  "notify":  { "webhook_url": null, "osascript": true }
}
```

Pexels API key 存在 macOS Keychain（`security add-generic-password -s "pexels-api-key" ...`），配置里保持 `"api_key": null`。

## 日常命令

```bash
python -m publisher                          # 发队列中下一篇
python -m publisher --login-toutiao          # 头条首次扫码
python -m publisher --check-toutiao          # 检查登录态
python -m publisher --test-cover "百年孤独"   # 测书封源
python -m publisher --test-stockimg "library" # 测摄影图源
```

## 故障排查

| 现象 | 一招解决 |
|------|----------|
| `40164: invalid ip` | `curl -s ifconfig.me` → 加微信 IP 白名单 |
| `40001: invalid credential` | 删 `~/.config/wenyan-md/token.json` |
| 头条 `not logged in` | `--login-toutiao` 重扫 |
| 文章被重复发 | 不会（sidecar 防重）；要强制重发就删 `.state/` |
| 队列空 | `HEARTBEAT_OK`，正常 |

## Cron

```bash
openclaw cron add --agent mo-ping --name "wechat-publish" \
  --cron "30 10 * * *" --tz Asia/Shanghai \
  --message "cd /path/to/Wechat-Toutiao-publisher && python -m publisher"
```

## 部署到新 Mac

→ [SETUP-OPENCLAW.md](./SETUP-OPENCLAW.md)

## License

MIT

