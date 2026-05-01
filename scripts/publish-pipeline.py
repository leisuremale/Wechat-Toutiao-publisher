#!/usr/bin/env python3
"""publish-pipeline.py — 一键发布管道：取文章 → 预处理 → 封面 → 微信发布 → 头条渲染 → 归档
用法: python3 publish-pipeline.py [--config pipeline-config.json] [--json]
输出: JSON 结果，包含 success, wechat_media_id, toutiao_html 等字段
"""
import sys, os, json, subprocess, re

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SKILL_DIR = os.path.dirname(SCRIPT_DIR)
DEFAULT_CONFIG = os.path.join(SKILL_DIR, "pipeline-config.json")

def load_config(path):
    with open(path) as f:
        return json.load(f)

def find_next_article(queue_path):
    """Return the first .md file in queue, or None."""
    if not os.path.isdir(queue_path):
        return None
    files = sorted([
        f for f in os.listdir(queue_path)
        if f.endswith('.md') and not f.startswith('.')
    ])
    if not files:
        return None
    return os.path.join(queue_path, files[0])

def run(cmd, timeout=120):
    """Run a command, return (success, stdout)."""
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)
    return r.returncode == 0, r.stdout.strip(), r.stderr.strip()

def main():
    config_path = DEFAULT_CONFIG
    args = sys.argv[1:]
    i = 0
    while i < len(args):
        if args[i] == '--config' and i+1 < len(args):
            config_path = args[i+1]; i += 2
        else:
            i += 1

    cfg = load_config(config_path)
    vault = cfg["obsidian_vault"]

    result = {
        "success": False,
        "step": "init",
        "article": None,
        "title": None,
        "wechat_media_id": None,
        "toutiao_html": None,
        "error": None,
    }

    try:
        # ── Step 1: Find article ──
        result["step"] = "find_article"
        queue_full = os.path.join(vault, cfg["queue_dir"])
        article = find_next_article(queue_full)
        if not article:
            result["success"] = True
            result["step"] = "done"
            result["message"] = "HEARTBEAT_OK: queue empty"
            print(json.dumps(result, ensure_ascii=False))
            return 0

        result["article"] = article
        result["title"] = os.path.splitext(os.path.basename(article))[0]

        # ── Step 2: Generate cover ──
        result["step"] = "generate_cover"
        cover_tpl = cfg["cover"]["template"]
        cover_path = "/tmp/wap_cover_hq.png"
        ok, out, err = run(
            f'python3 {SCRIPT_DIR}/generate-cover.py "{result["title"]}" -t {cover_tpl} -a "{cfg["wechat"]["author"]}" -o {cover_path}',
            timeout=30
        )
        if not ok:
            result["error"] = f"Cover generation failed: {err}"
            print(json.dumps(result, ensure_ascii=False))
            return 1

        # ── Step 3: Preprocess article ──
        result["step"] = "preprocess"
        ok, out, err = run(
            f'python3 {SCRIPT_DIR}/preprocess-article.py "{article}" --title "{result["title"]}" --cover {cover_path} --author {cfg["wechat"]["author"]}',
            timeout=30
        )
        if not ok:
            result["error"] = f"Preprocess failed: {err}"
            print(json.dumps(result, ensure_ascii=False))
            return 1

        # ── Step 4: Publish to WeChat ──
        result["step"] = "publish_wechat"
        wenyan_bin = os.path.expanduser("~/.local/bin/wenyan")
        theme_css = cfg["wechat"]["theme_css"]
        ok, out, err = run(
            f'{wenyan_bin} publish -f "{article}" -c {theme_css}',
            timeout=120
        )
        if not ok:
            result["error"] = f"WeChat publish failed: {err or out[:200]}"
            print(json.dumps(result, ensure_ascii=False))
            return 1

        # Extract media_id
        m = re.search(r'Media ID:\s*(\S+)', out)
        result["wechat_media_id"] = m.group(1) if m else out.strip()

        # ── Step 5: Render Toutiao HTML ──
        result["step"] = "render_toutiao"
        toutiao_dir = cfg["toutiao_dir"]
        os.makedirs(toutiao_dir, exist_ok=True)
        html_name = result["title"] + ".html"
        html_path = os.path.join(toutiao_dir, html_name)
        ok, out, err = run(
            f'{wenyan_bin} render -f "{article}" -c {theme_css}',
            timeout=60
        )
        if ok and out:
            with open(html_path, 'w') as f:
                f.write(out)
            result["toutiao_html"] = html_path

        # ── Step 6: Archive ──
        result["step"] = "archive"
        published_full = os.path.join(vault, cfg["published_dir"])
        os.makedirs(published_full, exist_ok=True)
        dest = os.path.join(published_full, os.path.basename(article))
        os.rename(article, dest)

        result["success"] = True
        result["step"] = "done"
        print(json.dumps(result, ensure_ascii=False))
        return 0

    except Exception as e:
        result["error"] = f"{result['step']}: {str(e)}"
        print(json.dumps(result, ensure_ascii=False))
        return 1

if __name__ == "__main__":
    sys.exit(main())
