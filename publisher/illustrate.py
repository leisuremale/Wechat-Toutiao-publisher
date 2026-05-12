"""Inline imagery for articles: book covers (top) + quote cards (inline).

Two independent features, both best-effort (failures only log warnings):

1. Book cover — extract book name from frontmatter `book:` or 《...》 in title,
   fetch cover image from Douban (then Google Books as fallback), insert at
   the top of the article body. Cached by sha256(name) so re-reviewing the
   same book is free.

2. Quote cards — find markdown blockquotes (skipping code blocks), render
   each as a 900x500 image card via Playwright + HTML/CSS templates from
   `themes/quotes/*.json`. Append after each blockquote (text remains
   accessible). Capped at `max_per_article` to preserve reading rhythm.
"""
from __future__ import annotations
import hashlib, json, os, re
import urllib.parse, urllib.request
from html import escape
from typing import Optional

# ── Attachment helpers ──────────────────────────────────────────
# Vault-relative path for cached images so Obsidian can display them.
ATTACHMENT_SUBDIR = "7-存档区/attachment"


def _copy_to_attachment(src_path: str, vault: str, prefix: str,
                          note_dir: str = "") -> tuple:
    """Copy src_path to vault/ATTACHMENT_SUBDIR/, return (obsidian_rel_path, abs_path).

    Obsidian resolves relative paths from the note's own directory.
    note_dir is used to compute the correct number of ../ segments.
    """
    if not src_path or not os.path.exists(src_path):
        return "", src_path or ""
    attachment_dir = os.path.join(vault, ATTACHMENT_SUBDIR)
    os.makedirs(attachment_dir, exist_ok=True)
    ext = os.path.splitext(src_path)[1] or ".jpg"
    sha = hashlib.sha256(src_path.encode()).hexdigest()[:12]
    filename = f"{prefix}-{sha}{ext}"
    dest = os.path.join(attachment_dir, filename)
    if not os.path.exists(dest):
        import shutil
        shutil.copy2(src_path, dest)
    if note_dir:
        obsidian_rel = os.path.relpath(dest, note_dir)
    else:
        obsidian_rel = f"{ATTACHMENT_SUBDIR}/{filename}"
    return obsidian_rel, dest


# ── Templates ────────────────────────────────────────────────
BUNDLED_QUOTES_DIR = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "themes", "quotes")
)

QUOTE_CSS_TEMPLATE = """
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{
    width: {width}px; height: {height}px; overflow: hidden;
    font-family: {font};
    background: {bg};
    display: flex; align-items: center; justify-content: center;
    padding: 60px 100px;
}}
.quote {{ position: relative; max-width: {inner_width}px; }}
.mark {{
    position: absolute; top: -50px; left: -30px;
    font-family: 'Times New Roman', Georgia, serif;
    font-size: 120px; color: {accent}; opacity: 0.35;
    line-height: 1; user-select: none;
}}
.text {{
    position: relative; z-index: 1;
    font-size: {fontsize}px; color: {text};
    line-height: 1.7; letter-spacing: 1.5px;
    word-break: break-word; white-space: pre-line;
}}
.author {{
    margin-top: 36px; font-size: 17px;
    color: {sub}; letter-spacing: 3px; text-align: right;
}}
"""


def load_quote_templates(extra_dir: Optional[str] = None) -> dict:
    """Load *.json from bundled themes/quotes/ then optional extra_dir (overrides)."""
    templates = {}
    for d in (BUNDLED_QUOTES_DIR, extra_dir):
        if not d or not os.path.isdir(d):
            continue
        for f in sorted(os.listdir(d)):
            if not f.endswith(".json"):
                continue
            with open(os.path.join(d, f), encoding="utf-8") as fh:
                templates[os.path.splitext(f)[0]] = json.load(fh)
    return templates


def _adaptive_fontsize(n_chars: int) -> int:
    """Pick a font size that keeps long quotes readable."""
    if n_chars < 30: return 44
    if n_chars < 60: return 36
    if n_chars < 100: return 28
    if n_chars < 160: return 24
    return 20


def render_quote_card(text: str, author: str = "", template: str = "classic",
                      output: Optional[str] = None, width: int = 900,
                      height: int = 500, extra_templates_dir: Optional[str] = None) -> str:
    """Render a quote as a 900x500 image. Returns output path."""
    templates = load_quote_templates(extra_templates_dir)
    if template not in templates:
        raise ValueError(
            f"unknown quote template '{template}'; available: {sorted(templates)}"
        )
    t = templates[template]

    css = QUOTE_CSS_TEMPLATE.format(
        width=width, height=height,
        fontsize=_adaptive_fontsize(len(text)),
        inner_width=width - 200,
        **t,
    )

    safe_text = escape(text)
    safe_author = escape(author) if author else ""
    author_html = f"<div class='author'>—— {safe_author}</div>" if safe_author else ""

    html = (
        "<!DOCTYPE html><html><head><meta charset='utf-8'>"
        f"<style>{css}</style></head><body>"
        "<div class='quote'>"
        "<div class='mark'>“</div>"
        f"<div class='text'>{safe_text}</div>"
        f"{author_html}"
        "</div></body></html>"
    )

    from playwright.sync_api import sync_playwright  # lazy
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": width, "height": height})
        page.set_content(html)
        page.screenshot(path=output, full_page=False)
        browser.close()

    return output


# ── Markdown parsing ─────────────────────────────────────────
QUOTE_LINE_RE = re.compile(r"^>\s?(.*)$")
FENCE_RE = re.compile(r"^```")
FRONTMATTER_BLOCK_RE = re.compile(r"\A---\r?\n(.*?)\r?\n---\r?\n?", re.DOTALL)
BOOK_FIELD_RE = re.compile(r"(?m)^book:\s*(.+)$")
BOOK_NAME_RE = re.compile(r"《([^》]+)》")

# ── Chinese quote → blockquote normalisation ───────────────────
_CHINESE_QUOTE_LINE = re.compile(r'^(\s*)(["“])(.*?)(["”])(\s*)$')
_LEADING_QUOTE = re.compile(r'^(\s*)(["“])(.*)')
_TRAILING_QUOTE = re.compile(r'(.*?)(["”])(\s*)$')


def normalize_quotes(content: str) -> str:
    """Convert short Chinese-quoted passages into markdown blockquotes.

    Only ≤4 lines, no paragraph breaks.  Longer spans are editorial
    narration and left untouched.
    """
    MAX_QUOTE_LINES = 4
    lines = content.split("\n")
    out: list = []
    in_quote = False
    quote_buf: list = []
    in_fence = False

    def _flush_quote(convert: bool):
        nonlocal quote_buf
        if not quote_buf:
            return
        if not convert or len(quote_buf) > MAX_QUOTE_LINES:
            out.extend(quote_buf)
        else:
            first = quote_buf[0]
            last = quote_buf[-1]
            fm = _LEADING_QUOTE.match(first)
            if fm:
                first = fm.group(1) + fm.group(3)
            else:
                first = first.lstrip("“\"")
            quote_buf[0] = first
            lm = _TRAILING_QUOTE.match(last)
            if lm:
                last = lm.group(1) + lm.group(3)
            else:
                last = last.rstrip("”\"")
            quote_buf[-1] = last
            out.append("\n".join(f"> {l}" for l in quote_buf))
        quote_buf = []

    for line in lines:
        if FENCE_RE.match(line):
            _flush_quote(convert=False)
            in_fence = not in_fence
            out.append(line)
            continue
        if in_fence:
            out.append(line)
            continue
        if QUOTE_LINE_RE.match(line):
            out.append(line)
            continue

        sm = _CHINESE_QUOTE_LINE.match(line)
        if sm:
            inner = sm.group(3).strip()
            if inner:
                out.append(f"> {inner}")
                continue

        has_open = bool(_LEADING_QUOTE.match(line))
        has_close = bool(_TRAILING_QUOTE.match(line))

        if in_quote and line.strip() == "":
            _flush_quote(convert=False)
            in_quote = False
            out.append(line)
            continue

        if has_open and not has_close:
            in_quote = True
            quote_buf.append(line)
        elif has_close and in_quote:
            quote_buf.append(line)
            valid = len(quote_buf) <= MAX_QUOTE_LINES
            _flush_quote(convert=valid)
            in_quote = False
        elif in_quote:
            quote_buf.append(line)
        else:
            out.append(line)

    _flush_quote(convert=False)
    return "\n".join(out)


def find_blockquotes(content: str) -> list:
    """Return [{'start_line', 'end_line', 'text'}] for non-code blockquotes."""
    lines = content.split("\n")
    blocks = []
    cur_lines: Optional[list] = None
    cur_start = -1
    in_code = False

    def _flush(end_line: int):
        nonlocal cur_lines, cur_start
        if cur_lines is not None:
            text = "\n".join(cur_lines).strip()
            if text:
                blocks.append({
                    "start_line": cur_start, "end_line": end_line, "text": text,
                })
            cur_lines = None

    for i, line in enumerate(lines):
        if FENCE_RE.match(line):
            in_code = not in_code
            _flush(i - 1)
            continue
        if in_code:
            _flush(i - 1)
            continue
        m = QUOTE_LINE_RE.match(line)
        if m:
            if cur_lines is None:
                cur_start = i
                cur_lines = []
            cur_lines.append(m.group(1))
        else:
            _flush(i - 1)
    _flush(len(lines) - 1)
    return blocks


def insert_quote_cards(content: str, render_fn, max_count: int,
                       min_chars: int) -> tuple:
    """Insert image refs after eligible blockquotes.

    `render_fn(text, idx)` returns image path or raises (caught and skipped).
    Returns (new_content, [inserted_paths]).
    """
    blocks = find_blockquotes(content)
    candidates = [b for b in blocks if len(b["text"]) >= min_chars][:max_count]
    if not candidates:
        return content, []

    rendered = []
    for i, b in enumerate(candidates):
        try:
            path = render_fn(b["text"], i)
            if path:
                rendered.append((b, path))
        except Exception:
            continue

    if not rendered:
        return content, []

    lines = content.split("\n")
    # Reverse order to preserve line indices during insertion
    for b, path in sorted(rendered, key=lambda x: x[0]["end_line"], reverse=True):
        lines.insert(b["end_line"] + 1, "")
        lines.insert(b["end_line"] + 2, f"![]({path})")
    return "\n".join(lines), [p for _, p in rendered]


# ── Book cover fetching ──────────────────────────────────────
COVER_URL_FIELD_RE = re.compile(r"(?m)^cover_url:\s*(.+)$")

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_5) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}


def extract_book_meta(title: str, content: str) -> dict:
    """Returns {'name', 'cover_url'} from frontmatter / title / first H1."""
    meta = {"name": None, "cover_url": None}
    m = FRONTMATTER_BLOCK_RE.match(content)
    body = content
    if m:
        fm = m.group(1)
        bm = BOOK_FIELD_RE.search(fm)
        if bm:
            meta["name"] = bm.group(1).strip().strip("\"'")
        cm = COVER_URL_FIELD_RE.search(fm)
        if cm:
            meta["cover_url"] = cm.group(1).strip().strip("\"'")
        body = content[m.end():]

    if not meta["name"]:
        tm = BOOK_NAME_RE.search(title or "")
        if tm:
            meta["name"] = tm.group(1).strip()
    if not meta["name"]:
        for line in body.split("\n"):
            s = line.strip()
            if s.startswith("# "):
                hm = BOOK_NAME_RE.search(s)
                if hm:
                    meta["name"] = hm.group(1).strip()
                break
    return meta


def extract_book_name(title: str, content: str) -> Optional[str]:
    """Backward-compat wrapper. Returns just the name field."""
    return extract_book_meta(title, content)["name"]


def _http_get(url: str, timeout: int = 10) -> Optional[bytes]:
    try:
        req = urllib.request.Request(url, headers=DEFAULT_HEADERS)
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read()
    except Exception:
        return None


def _try_dangdang(name: str, timeout: int = 10) -> Optional[str]:
    """Search dangdang.com book listings. Pattern observed 2026-05.

    Cover URLs follow `//img{N}m{N}.ddimg.cn/<dir>/<dir>/<id>-<n>_b_<ts>.jpg`.
    The `_b_` size token reliably distinguishes product covers from QR codes
    and promotional banners (which use /doc/ paths).
    """
    q = urllib.parse.quote(name)
    url = f"http://search.dangdang.com/?key={q}&act=input"
    data = _http_get(url, timeout)
    if not data:
        return None
    html = data.decode("utf-8", errors="ignore")
    m = re.search(
        r"//img\d?m?\d*\.ddimg\.cn/\d+/\d+/[^\"'\s]+_(?:b|d|m)_[^\"'\s]+\.(?:jpg|jpeg|webp)",
        html,
    )
    if not m:
        return None
    cover = m.group(0)
    return "http:" + cover if cover.startswith("//") else cover


def _try_douban(name: str, timeout: int = 10) -> Optional[str]:
    q = urllib.parse.quote(name)
    url = f"https://book.douban.com/subject_search?search_text={q}&cat=1001"
    data = _http_get(url, timeout)
    if not data:
        return None
    html = data.decode("utf-8", errors="ignore")
    m = re.search(
        r"https://img\d*\.doubanio\.com/view/subject/[ml]/public/[^\"'\s]+\.(?:jpg|webp|png)",
        html,
    )
    return m.group(0) if m else None


def _try_google_books(name: str, timeout: int = 10) -> Optional[str]:
    q = urllib.parse.quote(name)
    url = f"https://www.googleapis.com/books/v1/volumes?q={q}&maxResults=1"
    data = _http_get(url, timeout)
    if not data:
        return None
    try:
        obj = json.loads(data)
    except json.JSONDecodeError:
        return None
    items = obj.get("items", [])
    if not items:
        return None
    img_links = items[0].get("volumeInfo", {}).get("imageLinks", {})
    return img_links.get("thumbnail") or img_links.get("smallThumbnail")


SOURCES = {
    "dangdang": _try_dangdang,
    "douban": _try_douban,
    "google_books": _try_google_books,
}


def resolve_cover_override(value: str, vault: Optional[str],
                           cache_dir: str, timeout: int = 10) -> Optional[str]:
    """Resolve a manual `cover_url:` value to a local file path.

    Accepts: http(s) URL (downloaded to cache), absolute path (used directly
    if exists), or relative path (resolved against vault root).
    """
    if not value:
        return None
    if value.startswith(("http://", "https://")):
        os.makedirs(cache_dir, exist_ok=True)
        h = hashlib.sha256(value.encode()).hexdigest()[:16]
        path = os.path.join(cache_dir, f"override_{h}.jpg")
        if os.path.exists(path) and os.path.getsize(path) > 0:
            return path
        data = _http_get(value, timeout)
        if not data:
            return None
        with open(path, "wb") as f:
            f.write(data)
        return path
    if os.path.isabs(value):
        return value if os.path.exists(value) else None
    if vault:
        candidate = os.path.join(vault, value)
        if os.path.exists(candidate):
            return candidate
    return None


def _cache_path(name: str, cache_dir: str) -> str:
    h = hashlib.sha256(name.encode("utf-8")).hexdigest()[:16]
    return os.path.join(cache_dir, f"{h}.jpg")


def fetch_book_cover(book_name: str, cache_dir: str,
                     sources=("douban", "google_books"),
                     timeout: int = 10, logger=None) -> Optional[str]:
    """Search configured sources, download to cache_dir, return local path or None."""
    if not book_name:
        return None
    os.makedirs(cache_dir, exist_ok=True)
    cached = _cache_path(book_name, cache_dir)
    if os.path.exists(cached) and os.path.getsize(cached) > 0:
        return cached

    for src in sources:
        fn = SOURCES.get(src)
        if not fn:
            continue
        try:
            cover_url = fn(book_name, timeout)
        except Exception as e:
            if logger:
                logger.warning(f"book_cover[{src}] error: {e}")
            continue
        if not cover_url:
            continue
        data = _http_get(cover_url, timeout)
        if not data:
            continue
        with open(cached, "wb") as f:
            f.write(data)
        if logger:
            logger.info(f"book_cover[{src}] ok: '{book_name}' -> {cached}")
        return cached
    return None


def insert_book_cover(content: str, cover_path: str) -> str:
    """Insert the cover as the first body line (after frontmatter, if any).

    cover_path is vault-relative (e.g. '7-存档区/attachment/cover.jpg').
    """
    m = FRONTMATTER_BLOCK_RE.match(content)
    if m:
        head = content[:m.end()]
        tail = content[m.end():].lstrip("\n")
        return f"{head}\n![书封]({cover_path})\n\n{tail}"
    return f"![书封]({cover_path})\n\n{content}"


# ── Top-level coordinator ────────────────────────────────────
def illustrate(content: str, title: str, cfg, tempdir: str,
               vault: Optional[str] = None, article_path: Optional[str] = None,
               logger=None) -> dict:
    """Apply book_cover + quote_cards per cfg.illustrate.

    article_path is used to compute vault-relative paths for inserted images.
    Returns {'content', 'book_cover', 'quote_cards', 'warnings'}. Never raises.
    """
    result = {
        "content": content, "book_cover": None,
        "quote_cards": [], "stock_images": [], "warnings": [],
    }
    ill_cfg = cfg.illustrate

    note_dir = os.path.dirname(os.path.abspath(article_path)) if article_path else ""

    # Book cover: 1) frontmatter `cover_url:` override → 2) auto-search by name
    if ill_cfg.book_cover.enabled:
        meta = extract_book_meta(title, content)
        cache_dir = (ill_cfg.book_cover.cache_dir
                     or os.path.join(tempdir, "wap_book_covers"))
        cover_path = None

        if meta["cover_url"]:
            cover_path = resolve_cover_override(
                meta["cover_url"], vault, cache_dir,
                timeout=ill_cfg.book_cover.timeout,
            )
            if cover_path and logger:
                logger.info(f"book_cover[override]: {meta['cover_url']} -> {cover_path}")
            elif logger:
                logger.warning(f"book_cover[override]: failed to resolve {meta['cover_url']!r}")

        if not cover_path and meta["name"]:
            cover_path = fetch_book_cover(
                meta["name"], cache_dir,
                sources=tuple(ill_cfg.book_cover.sources),
                timeout=ill_cfg.book_cover.timeout,
                logger=logger,
            )

        if cover_path and vault:
            # Copy from temp cache → vault attachment dir, use vault-relative path
            rel_path, abs_copy = _copy_to_attachment(cover_path, vault, "wap-cover", note_dir)
            result["content"] = insert_book_cover(result["content"], rel_path)
            result["book_cover"] = abs_copy
        elif cover_path:
            result["content"] = insert_book_cover(result["content"], cover_path)
            result["book_cover"] = cover_path
        elif not meta["name"] and not meta["cover_url"]:
            result["warnings"].append("book_cover: no book name or cover_url detected")
        else:
            target = meta["cover_url"] or meta["name"]
            result["warnings"].append(f"book_cover: not found for {target!r}")

    # Stock images (theme-matched photos at H2 anchors)
    if ill_cfg.stock_images.enabled:
        from . import stockimg  # lazy: keep illustrate self-contained for tests

        # Resolve Pexels API key: config > macOS Keychain
        import copy
        si_cfg = copy.copy(ill_cfg.stock_images)
        if not si_cfg.api_key and si_cfg.source == "pexels":
            import subprocess
            try:
                out = subprocess.run(
                    ["security", "find-generic-password",
                     "-s", "pexels-api-key", "-a", "md2wechat", "-w"],
                    capture_output=True, text=True, timeout=5,
                )
                if out.returncode == 0 and out.stdout.strip():
                    si_cfg.api_key = out.stdout.strip()
            except Exception:
                pass

        cache_dir = (ill_cfg.stock_images.cache_dir
                     or os.path.join(tempdir, "wap_stock_images"))
        si_result = stockimg.add_stock_images(
            result["content"], si_cfg, cache_dir,
            note_dir=note_dir, vault=vault, logger=logger,
        )
        result["content"] = si_result["content"]
        result["stock_images"] = si_result["images"]
        for w in si_result["warnings"]:
            result["warnings"].append(f"stock_images: {w}")
        if logger and si_result["images"]:
            logger.info(f"stock_images: inserted {len(si_result['images'])}")
    else:
        result["stock_images"] = []

    # Normalize Chinese quotes → blockquotes before extraction
    result["content"] = normalize_quotes(result["content"])

    # Quote cards
    if ill_cfg.quote_cards.enabled:
        out_dir = os.path.join(tempdir, "wap_quote_cards")
        os.makedirs(out_dir, exist_ok=True)

        def _render(text, idx):
            output = os.path.join(out_dir, f"quote_{idx:02d}.png")
            return render_quote_card(
                text, author="",
                template=ill_cfg.quote_cards.template,
                output=output,
                extra_templates_dir=ill_cfg.quote_cards.templates_dir,
            )

        try:
            new_content, paths = insert_quote_cards(
                result["content"], _render,
                max_count=ill_cfg.quote_cards.max_per_article,
                min_chars=ill_cfg.quote_cards.min_chars,
            )
        except Exception as e:
            result["warnings"].append(f"quote_cards: render failed: {e}")
            return result
        result["content"] = new_content
        result["quote_cards"] = paths
        if not paths:
            result["warnings"].append("quote_cards: no eligible blockquotes")

    return result

