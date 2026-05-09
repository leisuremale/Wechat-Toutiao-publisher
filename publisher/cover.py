"""Cover image rendering. Templates loaded from themes/covers/*.json."""
import json, os, tempfile
from html import escape

DEFAULT_OUTPUT = os.path.join(tempfile.gettempdir(), "wap_cover_hq.png")
BUNDLED_DIR = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "themes", "covers")
)

CSS_TEMPLATE = """
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{
    width: {width}px; height: {height}px; overflow: hidden;
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


def load_templates(extra_dir: str = None) -> dict:
    """Load *.json from bundled dir, then optional extra_dir (overrides bundled)."""
    templates = {}
    for d in (BUNDLED_DIR, extra_dir):
        if not d or not os.path.isdir(d):
            continue
        for f in sorted(os.listdir(d)):
            if not f.endswith(".json"):
                continue
            with open(os.path.join(d, f), encoding="utf-8") as fh:
                templates[os.path.splitext(f)[0]] = json.load(fh)
    return templates


def render(title, template="literary", author="墨言",
           output=DEFAULT_OUTPUT, width=900, height=500,
           extra_templates_dir=None, subtitle="墨 言 书 评"):
    templates = load_templates(extra_templates_dir)
    if template not in templates:
        raise ValueError(
            f"unknown cover template '{template}'; available: {sorted(templates)}"
        )
    t = templates[template]
    css = CSS_TEMPLATE.format(width=width, height=height, **t)

    safe_title = escape(title)
    safe_author = escape(author)
    safe_sub = escape(subtitle)

    decor = t.get("decor", "")
    if decor in ("top", "left", "bottom"):
        decor_html = f"<div class='decor-line {decor}'></div>"
    elif decor == "box":
        decor_html = "<div class='decor-box'></div>"
    else:
        decor_html = ""

    html = (
        "<!DOCTYPE html><html><head><meta charset='utf-8'>"
        f"<style>{css}</style></head><body>"
        f"<div class='container'>{decor_html}"
        f"<div class='title'>{safe_title}</div>"
        f"<div class='subtitle'>{safe_sub}</div>"
        f"<div class='author-tag'>@{safe_author}</div>"
        "</div></body></html>"
    )

    from playwright.sync_api import sync_playwright  # lazy: only required at render time
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": width, "height": height})
        page.set_content(html)
        page.screenshot(path=output, full_page=False)
        browser.close()

    return output
