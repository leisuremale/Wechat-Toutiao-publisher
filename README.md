# Wechat-Toutiao-Publisher

> 一键将 Obsidian Markdown 排版发布到微信公众号 + 头条号。JSON 驱动，cron 自动化，零手动排版。

[![wenyan](https://img.shields.io/badge/powered_by-wenyan-v2.0.8-blue)](https://github.com/caol64/wenyan)
[![platform](https://img.shields.io/badge/platform-WeChat_%7C_Toutiao-green)]()
[![automation](https://img.shields.io/badge/automation-cron_%2B_JSON-orange)]()

## 亮点

### 🤖 一条命令，全自动管道

传统的 AI Agent 发布流程：模型要理解 7 步自然语言指令，逐步执行，容易跳步或出错。

本 Skill 的做法：**一个 Python 脚本完成全部 6 步**，输出结构化 JSON。模型只需调一条命令、解析一个 JSON、播报结果。

```
python3 scripts/publish-pipeline.py
# → {"success": true, "wechat_media_id": "...", "toutiao_html": "..."}
```

```
① 取文章 → ② 生成封面 → ③ 预处理（图片+frontmatter）
→ ④ 微信发布 → ⑤ 头条渲染 → ⑥ 归档
```

### 🎨 4 套 HTML/CSS 封面模板

不是简陋的 PIL 纯色大字，而是 **Playwright + Chromium 渲染的 HTML/CSS 封面**。专业设计感，900×500 高清输出。

| 模板 | 效果 | 适合 |
|------|------|------|
| `literary` | 暖米色底 + 衬线字体 + 装饰线 | 文学书评 |
| `dark` | 深蓝底 + 红色点缀 + 无衬线 | 深度思考 |
| `fresh` | 浅绿底 + 细线 + 留白 | 清新随笔 |
| `bold` | 纯白底 + 橙色边框 | 观点鲜明 |

### 📝 Obsidian 原生工作流

在 Obsidian 里写 `![[图片名.png]]` 嵌入图片，发布时自动转换为微信兼容格式并上传到微信 CDN。不需要手动处理图片路径。

```markdown
![[村上春树.jpg]]           # vault 内自动搜索
![[assets/封面.png]]        # 相对路径
![](/absolute/path/img.jpg) # 标准 Markdown
```

### ⚙️ JSON 配置，修改零代码

所有设置集中在 `pipeline-config.json`：

```json
{
  "cover": { "template": "literary" },
  "wechat": { "theme_css": "themes/mo-ping.css", "author": "墨言" },
  "queue_dir": ".../待发文章",
  "published_dir": ".../已发布文章"
}
```

改封面模板？改 `"template": "dark"` 就行。换排版主题？改 `"theme_css"` 路径。cron 下次自动生效。

### 📊 双平台覆盖

| 平台 | 方式 | 自动化 |
|------|------|--------|
| 微信公众号 | wenyan publish → 草稿箱 | ✅ 全自动 |
| 头条号 | wenyan render → HTML 文件 | ⚠️ 半自动（30 秒粘贴） |

> 头条号没有开放 API，无法全自动发布。但生成的 HTML 完全兼容头条编辑器，打开复制粘贴即可。

### 🕐 Cron 定时发布

每天 10:30 自动从 Obsidian 待发文章目录取第一篇，发布到微信草稿箱 + 渲染头条 HTML + 归档。

```bash
openclaw cron add --agent mo-ping --name "wechat-publish" \
  --cron "30 10 * * *" --tz Asia/Shanghai \
  --message "python3 .../publish-pipeline.py | 解析 JSON | 播报"
```

## 快速开始

### 依赖

```bash
npm install -g @wenyan-md/cli      # wenyan 排版引擎
pip3 install playwright             # 封面渲染
python3 -m playwright install chromium
```

### 配置凭据

微信 AppID/Secret 存入 macOS Keychain（或设置环境变量 `WECHAT_APP_ID` / `WECHAT_APP_SECRET`）：

```bash
security add-generic-password -s "md2wechat-appid" -a "md2wechat" -w "wx..."
security add-generic-password -s "md2wechat-secret" -a "md2wechat" -w "..."
```

Wrapper 脚本 `~/.local/bin/wenyan` 自动从 Keychain 注入凭据。

### 发布

```bash
# 自动管道（从队列取第一篇）
python3 scripts/publish-pipeline.py

# 手动单篇
~/.local/bin/wenyan publish -f article.md -c themes/mo-ping.css
```

### 封面生成

```bash
python3 scripts/generate-cover.py "文章标题" -t literary -o cover.png
```

## 目录结构

```
Wechat-Toutiao-publisher/
├── pipeline-config.json        # 所有配置
├── SKILL.md                    # AI Agent 触发规则
├── README.md                   # 本文件
├── scripts/
│   ├── publish-pipeline.py     # ★ 一键管道（6 步合一）
│   ├── generate-cover.py       # HTML/CSS 封面生成
│   └── preprocess-article.py   # Obsidian 图片转换 + frontmatter
└── themes/
    └── mo-ping.css             # 墨评自定义排版主题
```

## 依赖项目

- [wenyan（文颜）](https://github.com/caol64/wenyan) — 多平台 Markdown 排版发布工具
- [Playwright](https://playwright.dev) — 封面 HTML/CSS 渲染
- macOS Keychain — 凭据管理

## License

MIT
