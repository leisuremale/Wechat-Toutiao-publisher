# 部署到另一台 Mac (openclaw)

把 Wechat-Toutiao-publisher 装到一台新 Mac，从零到 cron 自动跑。约 30 分钟。

## 前置

- macOS 13+
- 已登录 iCloud（Obsidian vault 同步用）
- openclaw 已安装：`openclaw --version` 能跑
- Node 18+ 与 Python 3.10+
- 微信公众号 AppID + AppSecret
- 头条号账号（用于扫码）

---

## 1. 克隆到 openclaw skills 目录

```bash
mkdir -p ~/.openclaw/workspace-mo-ping/skills
cd ~/.openclaw/workspace-mo-ping/skills
git clone https://github.com/leisuremale/Wechat-Toutiao-publisher.git
cd Wechat-Toutiao-publisher
```

> 路径里 `mo-ping` 是 openclaw agent 名，按你的 agent 改。

## 2. 装系统依赖

```bash
# Node + wenyan CLI
brew install node
npm install -g @wenyan-md/cli
wenyan --version           # 验证

# Python + Playwright Chromium
pip3 install --user playwright
python3 -m playwright install chromium
```

## 3. 写微信凭据到 Keychain

```bash
security add-generic-password -s "md2wechat-appid"  -a "md2wechat" -w "wx你的AppID"
security add-generic-password -s "md2wechat-secret" -a "md2wechat" -w "你的AppSecret"

# 验证（输出 wx... 开头）
security find-generic-password -s "md2wechat-appid" -a "md2wechat" -w
```

## 4. 链接 wenyan-wrapper

让 wenyan 自动从 Keychain 读凭据：

```bash
mkdir -p ~/.local/bin
chmod +x scripts/wenyan-wrapper.sh
ln -sf "$(pwd)/scripts/wenyan-wrapper.sh" ~/.local/bin/wenyan

# 验证：wrapper 应该跑真 wenyan，不是死循环
~/.local/bin/wenyan --version
```

确保 `~/.local/bin` 在 npm global 路径**之前**：

```bash
echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.zshrc
source ~/.zshrc
which wenyan               # 应输出 ~/.local/bin/wenyan
```

或在 `pipeline-config.json` 里显式写 `"wenyan_bin": "/Users/你/.local/bin/wenyan"`。

## 5. 写 pipeline-config.json

```bash
cp pipeline-config.example.json pipeline-config.json
$EDITOR pipeline-config.json
```

`pipeline-config.json` 已在 `.gitignore`，本机改的路径不会被 commit。example 里展示了所有可选字段，`null` 表示「用默认」。

按这台机器实际路径改。最小可用版本：

```json
{
  "obsidian_vault": "/Users/你/Library/Mobile Documents/iCloud~md~obsidian/Documents/你的Vault",
  "queue_dir": "AI写作/待发文章",
  "published_dir": "AI写作/已发布文章",
  "toutiao_dir": "/Users/你/.openclaw/workspace-mo-ping/output/头条待发",
  "wechat": {
    "theme_css": "/Users/你/.openclaw/workspace-mo-ping/skills/Wechat-Toutiao-publisher/themes/mo-ping.css",
    "author": "墨言"
  },
  "cover": { "template": "literary" },
  "log": {
    "dir": "/Users/你/.openclaw/workspace-mo-ping/logs/publisher",
    "level": "INFO"
  },
  "notify": { "osascript": true }
}
```

立即跑 schema 校验（不会真发，只解析）：

```bash
python3 -c "
import sys; sys.path.insert(0, '.')
from publisher.config import load_config
cfg = load_config('pipeline-config.json')
print('vault:', cfg.obsidian_vault)
print('queue:', cfg.queue_full)
print('wenyan_bin:', cfg.wenyan_bin or 'auto')
"
```

报 `config: missing required '<key>'` 就按提示补。

## 6. 测试单跑（先不开头条自动）

放一篇测试文章到队列：

```bash
VAULT="/Users/你/Library/Mobile Documents/iCloud~md~obsidian/Documents/你的Vault"
QUEUE="$VAULT/AI写作/待发文章"
mkdir -p "$QUEUE"
cat > "$QUEUE/test-$(date +%s).md" <<'EOF'
# 测试标题

这是一篇测试文章。
EOF
```

跑一次：

```bash
python -m publisher --config pipeline-config.json
```

期望输出（一行 JSON）：

```json
{"success": true, "wechat_media_id": "...", "toutiao_html": "...", "resumed": false, ...}
```

打开微信公众平台 → 草稿箱，应该能看到刚推的草稿。同时检查：
- `published_dir` 里多了归档文件
- `toutiao_dir` 里多了 `.html`
- `<queue_dir>/.state/` 不存在或为空（成功后自动清）

## 7.（可选）配置头条全自动

需要图形终端做扫码（无屏 server 先在另一台 Mac 扫完再 rsync profile）。

修改配置加 `toutiao` 块：

```json
{
  "toutiao": {
    "auto": true,
    "user_data_dir": "/Users/你/.openclaw/toutiao-profile",
    "screenshot_dir": "/Users/你/.openclaw/toutiao-shots",
    "headless": true,
    "timeout_ms": 60000
  }
}
```

> `user_data_dir` 路径**不要放仓库内**，里面是登录 cookie。

```bash
chmod 700 ~/.openclaw            # 限权
mkdir -p ~/.openclaw/toutiao-shots
```

首次扫码（headed 浏览器会弹出来）：

```bash
python -m publisher --login-toutiao
# 用头条 App 扫码登录 → 回终端按 Enter 保存
```

健康检查：

```bash
python -m publisher --check-toutiao
# {"logged_in": true}
```

下次 pipeline 跑会自动建头条草稿。selectors 失败时看 `screenshot_dir` 里的截图，需要时把自定义 selector 写到 `toutiao.selectors`。

## 8. 注册 openclaw cron

```bash
openclaw cron add \
  --agent mo-ping \
  --name "wechat-publish" \
  --cron "30 10 * * *" \
  --tz Asia/Shanghai \
  --message "cd /Users/你/.openclaw/workspace-mo-ping/skills/Wechat-Toutiao-publisher && python -m publisher"
```

验证：

```bash
openclaw cron list           # 看到任务
openclaw cron run <id>       # 手动触发
```

## 9.（可选）失败通知到手机

iOS 用 [Bark](https://github.com/Finb/Bark) 注册 token，写到配置：

```json
{
  "notify": {
    "webhook_url": "https://api.day.app/你的key/publish",
    "osascript": true
  }
}
```

测试：故意改坏 frontmatter 或断网，跑 pipeline，应收到推送。

---

## 验证清单

- [ ] `wenyan --version` 输出版本号
- [ ] `which wenyan` 是 `~/.local/bin/wenyan`（wrapper），不是 npm 全局
- [ ] `security find-generic-password -s md2wechat-appid -a md2wechat` 能取到值
- [ ] `python3 -m playwright install chromium` 报 already installed
- [ ] 队列空时 `python -m publisher` 返回 `HEARTBEAT_OK`
- [ ] 测试文章能成功归档到 `published_dir`
- [ ] `toutiao.auto=true` 时 `--check-toutiao` 输出 `logged_in: true`
- [ ] `openclaw cron list` 看到任务且 enabled

---

## 常见坑

### `which wenyan` 显示 npm 全局而不是 wrapper

PATH 顺序问题。`~/.zshrc` 加：

```bash
export PATH="$HOME/.local/bin:$PATH"
```

或在 `pipeline-config.json` 显式：

```json
{ "wenyan_bin": "/Users/你/.local/bin/wenyan" }
```

### Playwright 报 `Executable doesn't exist`

```bash
python3 -m playwright install chromium
```

cron 用户独立安装：

```bash
sudo -u <cron_user> python3 -m playwright install chromium
```

### iCloud 路径里的 `Mobile Documents/iCloud~md~obsidian/...` 不存在

iCloud Drive 没启用或 Obsidian 还没同步过来。Obsidian 打开 vault 一次，等同步完成。

### 微信 `40164: invalid ip`

cron 主机出口 IP 不在公众号白名单。`curl -s4 ifconfig.me` 拿 IP，加到微信公众平台 → 开发 → 基本配置 → IP 白名单。retry 会自动重试 3 次，但白名单不补永远过不了。

### cron 跑成功但 macOS 没弹通知

`osascript` 需要 GUI session，cron 子进程没有。改 launchd UserAgent 或用 webhook 推手机。

### 头条登录态过期

只能重扫。建议每周一次跑 `--check-toutiao`，false 就 `--login-toutiao`。

### 同一文章被发了两次（不应该发生）

检查 `<queue_dir>/.state/<article>.json` 是否存在。sidecar 写入应该让 step 4 跳过。如果你在 step 4 成功后立即手动删了 sidecar，下次会重发——这是设计预期。

---

## 拷贝到第二台 Mac 的快捷方式

第一台已经装好，第二台想完全复刻：

```bash
# 1. 重写 keychain entries（手动跑 security 命令，凭据不能 rsync）
# 2. rsync 仓库（排除运行时垃圾）
rsync -av --exclude='.state' --exclude='__pycache__' --exclude='*.pyc' \
  ~/.openclaw/workspace-mo-ping/skills/Wechat-Toutiao-publisher \
  newmac:~/.openclaw/workspace-mo-ping/skills/

# 3. 拷头条 profile（有效期内可省去再扫码）
rsync -av --chmod=700 ~/.openclaw/toutiao-profile newmac:~/.openclaw/

# 4. newmac 上从「2. 装系统依赖」开始重做（npm wenyan + playwright）
```

## 升级到新版本

```bash
cd ~/.openclaw/workspace-mo-ping/skills/Wechat-Toutiao-publisher
git pull
python -m publisher --check-toutiao   # 冒烟
```

新版加的所有 schema 字段都是可选，`pipeline-config.json` 不用改。如果哪天加了致命字段，启动时 `ValueError` 立即报。
