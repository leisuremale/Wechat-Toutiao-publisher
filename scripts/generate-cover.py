#!/usr/bin/env python3
"""generate-cover.py — HTML/CSS 渲染高质量微信公众号封面图 (900x500)"""
import sys, os, argparse
from playwright.sync_api import sync_playwright

TEMPLATES = {
    "literary": {
        "name": "文学",
        "bg": "#f5f0e8",
        "accent": "#8b4513",
        "text": "#2c1810",
        "sub": "#6b4c3b",
        "font": "'Noto Serif SC', 'Songti SC', serif",
        "decor": "top",
    },
    "dark": {
        "name": "深夜",
        "bg": "#1a1a2e",
        "accent": "#e94560",
        "text": "#eee",
        "sub": "#999",
        "font": "'PingFang SC', 'Microsoft YaHei', sans-serif",
        "decor": "left",
    },
    "fresh": {
        "name": "清新",
        "bg": "#f0f7f4",
        "accent": "#2d6a4f",
        "text": "#1b4332",
        "sub": "#40916c",
        "font": "'PingFang SC', 'Microsoft YaHei', sans-serif",
        "decor": "bottom",
    },
    "bold": {
        "name": "醒目",
        "bg": "#ffffff",
        "accent": "#ff6b35",
        "text": "#1a1a1a",
        "sub": "#666",
        "font": "'PingFang SC', 'Microsoft YaHei', sans-serif",
        "decor": "box",
    },
}

CSS = """
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{
    width: 900px; height: 500px; overflow: hidden;
    font-family: {font};
    background: {bg};
    display: flex; align-items: center; justify-content: center;
}}
.container {{ width: 780px; position: relative; }}
.decor-line {{ position: absolute; background: {accent}; }}
.decor-line.top {{ top: -40px; left: 0; width: 60px; height: 4px; }}
.decor-line.left {{ top: 0; left: -40px; width: 4px; height: 80px; }}
.decor-line.bottom {{ bottom: -30px; left: 0; width: 100%; height: 2px; opacity: 0.3; }}
.decor-box {{
    position: absolute; top: -30px; left: -30px;
    width: 100px; height: 100px;
    border: 4px solid {accent}; opacity: 0.4;
}}
.title {{
    font-size: 44px; font-weight: 700; color: {text};
    line-height: 1.3; letter-spacing: 2px;
    max-width: 700px; word-break: break-word;
}}
.subtitle {{
    margin-top: 24px; font-size: 20px; color: {sub};
    letter-spacing: 4px; font-weight: 400;
}}
.author-tag {{
    margin-top: 28px; font-size: 16px; color: {sub};
    letter-spacing: 2px; opacity: 0.7;
}}
"""

def render(title, template="literary", author="墨言", output="/tmp/wap_cover_hq.png"):
    t = TEMPLATES.get(template, TEMPLATES["literary"])
    html = f"<!DOCTYPE html><html><head><meta charset='utf-8'><style>{CSS.format(**t)}</style></head><body>"
    html += f"<div class='container'>"

    if t["decor"] == "top":
        html += "<div class='decor-line top'></div>"
    elif t["decor"] == "left":
        html += "<div class='decor-line left'></div>"
    elif t["decor"] == "bottom":
        html += "<div class='decor-line bottom'></div>"
    elif t["decor"] == "box":
        html += "<div class='decor-box'></div>"

    html += f"<div class='title'>{title}</div>"
    html += f"<div class='subtitle'>墨 言 书 评</div>"
    html += f"<div class='author-tag'>@{author}</div>"
    html += "</div></body></html>"

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 900, "height": 500})
        page.set_content(html)
        page.screenshot(path=output, full_page=False)
        browser.close()

    size_kb = os.path.getsize(output) / 1024
    print(f"✅ [{t['name']}] {output} ({size_kb:.0f}KB)")
    return output

if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Generate high-quality WeChat cover image")
    p.add_argument("title", help="Cover title text")
    p.add_argument("-t", "--template", default="literary",
                   choices=list(TEMPLATES.keys()), help="Template style")
    p.add_argument("-a", "--author", default="墨言", help="Author name")
    p.add_argument("-o", "--output", default="/tmp/wap_cover_hq.png", help="Output path")
    args = p.parse_args()
    render(args.title, args.template, args.author, args.output)
