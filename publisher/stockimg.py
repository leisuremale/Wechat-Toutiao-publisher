"""Theme-matched stock images: Pexels (primary) → Wikimedia Commons (fallback).

Searches a configured pool of aesthetic keywords (or per-article overrides via
frontmatter `image_keywords:`), distributes 2-3 images at H2 section anchors
(falls back to evenly-spaced paragraph breaks for unsectioned articles), and
appends an attribution block.

Pexels needs a free API key (https://www.pexels.com/api/). Wikimedia needs no
auth. Both licenses permit free commercial use; attribution is best practice.

Failures degrade to warnings — never blocks publish.
"""
from __future__ import annotations
import hashlib, json, os, random, re
import urllib.parse, urllib.request
from typing import Optional

DEFAULT_KEYWORDS = [
    "library", "books", "reading", "vintage", "candlelight",
    "writing", "manuscript", "old paper", "quiet", "bookshelf",
    "literature", "ink", "fountain pen", "study room",
]

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_5) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"
    ),
    "Accept": "*/*",
    "Accept-Language": "en-US,en;q=0.9",
}

H2_RE = re.compile(r"^##\s+")
FENCE_RE = re.compile(r"^```")
FRONTMATTER_BLOCK_RE = re.compile(r"\A---\r?\n(.*?)\r?\n---\r?\n?", re.DOTALL)
INLINE_KEYWORDS_RE = re.compile(r"(?m)^image_keywords:\s*\[(.*?)\]")
BLOCK_KEYWORDS_RE = re.compile(r"(?m)^image_keywords:\s*\n((?:[ \t]*-\s*.+\n?)+)")


# ── Keyword selection ────────────────────────────────────────
def parse_image_keywords(content: str) -> list:
    """Parse `image_keywords:` from frontmatter (inline or YAML list)."""
    m = FRONTMATTER_BLOCK_RE.match(content)
    if not m:
        return []
    fm = m.group(1)
    inline = INLINE_KEYWORDS_RE.search(fm)
    if inline:
        return [s.strip().strip("\"'") for s in inline.group(1).split(",") if s.strip()]
    block = BLOCK_KEYWORDS_RE.search(fm)
    if block:
        return [
            line.strip().lstrip("-").strip().strip("\"'")
            for line in block.group(1).split("\n")
            if line.strip()
        ]
    return []


def select_keywords(content: str, default_pool: list, count: int) -> list:
    """Pick keywords for image search.

    Frontmatter `image_keywords:` wins; falls back to random sample from pool.
    If frontmatter is shorter than count, top up from pool.
    """
    explicit = parse_image_keywords(content)
    if explicit and len(explicit) >= count:
        return explicit[:count]
    pool = default_pool or DEFAULT_KEYWORDS
    pool = list(pool)
    random.shuffle(pool)
    needed = count - len(explicit)
    return explicit + pool[:needed]


# ── Anchor selection ─────────────────────────────────────────
def _frontmatter_end_line(content: str) -> int:
    m = FRONTMATTER_BLOCK_RE.match(content)
    return content[:m.end()].count("\n") if m else 0


def find_h2_anchors(content: str) -> list:
    """Line indices for H2 headings outside code blocks."""
    lines = content.split("\n")
    anchors, in_code = [], False
    for i, line in enumerate(lines):
        if FENCE_RE.match(line):
            in_code = not in_code
            continue
        if in_code:
            continue
        if H2_RE.match(line):
            anchors.append(i)
    return anchors


def find_paragraph_anchors(content: str, n: int) -> list:
    """N evenly-spaced paragraph-break line indices in the body."""
    if n <= 0:
        return []
    lines = content.split("\n")
    fm_end = _frontmatter_end_line(content)
    in_code = False
    breaks = []
    for i in range(fm_end, len(lines)):
        line = lines[i]
        if FENCE_RE.match(line):
            in_code = not in_code
            continue
        if in_code:
            continue
        if line.strip() == "":
            breaks.append(i)
    if len(breaks) < 2:
        return []
    step = len(breaks) / (n + 1)
    picks = [breaks[int(step * (i + 1))] for i in range(n)]
    return sorted(set(picks))


def pick_anchors(content: str, n: int) -> list:
    """N insertion line indices. Prefer H2 (skip first to leave book-cover area
    clean); top up from paragraph breaks when too few H2s."""
    h2 = find_h2_anchors(content)
    candidates = h2[1:] if len(h2) > 1 else h2
    if len(candidates) >= n:
        step = max(1, len(candidates) // n)
        return sorted({candidates[min(step * i, len(candidates) - 1)] for i in range(n)})
    used = list(candidates)
    remaining = n - len(used)
    para = find_paragraph_anchors(content, remaining)
    return sorted(set(used + para))


# ── HTTP ─────────────────────────────────────────────────────
def _http_get(url: str, timeout: int = 15,
              extra_headers: Optional[dict] = None) -> Optional[bytes]:
    headers = dict(DEFAULT_HEADERS)
    if extra_headers:
        headers.update(extra_headers)
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read()
    except Exception:
        return None


# ── Pexels ───────────────────────────────────────────────────
def search_pexels(keyword: str, api_key: Optional[str] = None,
                  count: int = 5, timeout: int = 15) -> list:
    """Returns [{id, url, photographer, page_url, license_url, source}]."""
    if not api_key:
        return []
    url = (f"https://api.pexels.com/v1/search?"
           f"query={urllib.parse.quote(keyword)}&per_page={count}&orientation=landscape")
    data = _http_get(url, timeout, extra_headers={"Authorization": api_key})
    if not data:
        return []
    try:
        obj = json.loads(data)
    except json.JSONDecodeError:
        return []
    out = []
    for p in obj.get("photos", []):
        src = p.get("src", {})
        img_url = src.get("large") or src.get("original")
        if not img_url:
            continue
        out.append({
            "id": f"pexels:{p['id']}",
            "url": img_url,
            "photographer": p.get("photographer", "Pexels"),
            "page_url": p.get("url", ""),
            "license_name": "Pexels License",
            "source": "Pexels",
        })
    return out


# ── Wikimedia Commons ────────────────────────────────────────
def search_wikimedia(keyword: str, api_key: Optional[str] = None,
                     count: int = 5, timeout: int = 15) -> list:
    """No API key needed. Returns same dict shape as search_pexels."""
    params = {
        "action": "query", "format": "json",
        "generator": "search", "gsrsearch": keyword,
        "gsrnamespace": "6", "gsrlimit": str(count),
        "prop": "imageinfo",
        "iiprop": "url|extmetadata|mime",
        "iiurlwidth": "1200",
    }
    url = f"https://commons.wikimedia.org/w/api.php?{urllib.parse.urlencode(params)}"
    data = _http_get(url, timeout)
    if not data:
        return []
    try:
        obj = json.loads(data)
    except json.JSONDecodeError:
        return []
    pages = obj.get("query", {}).get("pages", {})
    out = []
    for page_id, page in pages.items():
        ii_list = page.get("imageinfo", [])
        if not ii_list:
            continue
        ii = ii_list[0]
        # Filter: WeChat accepts JPEG/PNG/WebP, not SVG/GIF
        mime = ii.get("mime", "")
        if mime not in ("image/jpeg", "image/png", "image/webp"):
            continue
        thumb = ii.get("thumburl") or ii.get("url")
        if not thumb:
            continue
        meta = ii.get("extmetadata", {})
        artist_raw = meta.get("Artist", {}).get("value", "Wikimedia")
        artist = re.sub(r"<[^>]+>", "", artist_raw).strip()[:80] or "Wikimedia"
        license_name = meta.get("LicenseShortName", {}).get("value", "")
        title = page.get("title", "")
        out.append({
            "id": f"wikimedia:{page_id}",
            "url": thumb,
            "photographer": artist,
            "page_url": f"https://commons.wikimedia.org/wiki/{urllib.parse.quote(title)}",
            "license_name": license_name,
            "source": "Wikimedia Commons",
        })
    return out


SOURCES = {
    "pexels": search_pexels,
    "wikimedia": search_wikimedia,
}


# ── Download with cache ──────────────────────────────────────
def download_image(photo: dict, cache_dir: str, timeout: int = 15) -> Optional[str]:
    """Download photo['url'] to cache, return local path or None."""
    os.makedirs(cache_dir, exist_ok=True)
    h = hashlib.sha256(photo["id"].encode()).hexdigest()[:16]
    path = os.path.join(cache_dir, f"{h}.jpg")
    if os.path.exists(path) and os.path.getsize(path) > 0:
        return path
    data = _http_get(photo["url"], timeout)
    if not data:
        return None
    with open(path, "wb") as f:
        f.write(data)
    return path


# ── Insertion + attribution ──────────────────────────────────
def insert_images(content: str, image_paths: list, anchors: list) -> str:
    """Insert markdown image refs after each anchor line. Reverse-iter to
    preserve indices.

    image_paths are vault-relative (e.g. '7-存档区/attachment/wap-stock-abc123.jpg').
    """
    if not image_paths or not anchors:
        return content
    pairs = list(zip(sorted(anchors[:len(image_paths)], reverse=True),
                     reversed(image_paths)))
    lines = content.split("\n")
    for line_idx, path in pairs:
        lines.insert(line_idx + 1, "")
        lines.insert(line_idx + 2, f"![]({path})")
        lines.insert(line_idx + 3, "")
    return "\n".join(lines)


def build_attribution(images: list) -> str:
    """Markdown blockquote section listing image sources."""
    if not images:
        return ""
    lines = ["", "---", "", "> **图片来源**", ">"]
    for img in images:
        m = img["meta"]
        license_str = f" · {m['license_name']}" if m.get("license_name") else ""
        photographer = m.get("photographer", "Unknown")
        source = m.get("source", "")
        if m.get("page_url"):
            lines.append(f"> - [{photographer} · {source}]({m['page_url']}){license_str}")
        else:
            lines.append(f"> - {photographer} · {source}{license_str}")
    return "\n".join(lines)


# ── Coordinator ──────────────────────────────────────────────
def compute_image_count(content: str, cfg) -> int:
    """Number of images for this article: bounded by config + char count."""
    chars = len(content)
    by_length = chars // max(1, cfg.min_chars_per_image)
    return min(cfg.count_per_article, by_length)


def fetch_topical_images(content: str, cfg, cache_dir: str,
                         logger=None) -> dict:
    """Search → download → return {'images': [{path, meta}], 'warnings': [...]}."""
    result = {"images": [], "warnings": []}

    n_target = compute_image_count(content, cfg)
    if n_target == 0:
        return result

    keywords = select_keywords(content, cfg.default_keywords, n_target)
    if not keywords:
        result["warnings"].append("no keywords")
        return result

    # Build search source order: primary first, then fallback (deduped)
    sources_order = []
    for s in (cfg.source, cfg.fallback):
        if s and s not in sources_order and s in SOURCES:
            sources_order.append(s)

    if cfg.source == "pexels" and not cfg.api_key:
        result["warnings"].append("pexels source requires api_key (using fallback only)")
        sources_order = [s for s in sources_order if s != "pexels"]

    if not sources_order:
        result["warnings"].append("no usable image source configured")
        return result

    used_ids = set()
    for kw in keywords:
        photo = None
        for src_name in sources_order:
            try:
                results = SOURCES[src_name](kw, cfg.api_key, 5, cfg.timeout)
            except Exception as e:
                if logger:
                    logger.warning(f"stock_images[{src_name}/{kw}]: {e}")
                continue
            for p in results:
                if p["id"] not in used_ids:
                    photo = p
                    break
            if photo:
                if logger:
                    logger.info(f"stock_images[{src_name}/{kw}] -> {photo['id']}")
                break
        if not photo:
            result["warnings"].append(f"no result for keyword '{kw}'")
            continue
        local = download_image(photo, cache_dir, cfg.timeout)
        if not local:
            result["warnings"].append(f"download failed: {photo['id']}")
            continue
        result["images"].append({"path": local, "meta": photo})
        used_ids.add(photo["id"])
        if len(result["images"]) >= n_target:
            break

    return result


def add_stock_images(content: str, cfg, cache_dir: str,
                    note_dir: str = "", vault: str = "",
                    logger=None) -> dict:
    """Top-level: fetch + insert + attribute. Returns {content, images, path_map, warnings}.

    path_map: {markdown_path: vault_relative_path} for post-publish path rewriting.
    """
    result = {"content": content, "images": [], "path_map": {}, "warnings": []}

    if not cfg.enabled:
        return result

    fetched = fetch_topical_images(content, cfg, cache_dir, logger)
    result["warnings"].extend(fetched["warnings"])

    if not fetched["images"]:
        return result

    # Use downloaded cache paths directly (cache_dir is in /tmp, no spaces).
    # Also copy to vault attachment dir for Obsidian display; record mapping
    # so pipeline can rewrite paths after WeChat publish.
    image_paths = []
    abs_copy_paths = []
    if vault and note_dir:
        attachment_dir = os.path.join(vault, "7-存档区/attachment")
        os.makedirs(attachment_dir, exist_ok=True)
        import shutil
        for img in fetched["images"]:
            src = img["path"]
            if src and os.path.exists(src):
                # Use cache_dir path for markdown (no spaces, safe for wenyan)
                image_paths.append(src)
                # Also copy to vault for Obsidian (side effect)
                ext = os.path.splitext(src)[1] or ".jpg"
                sha = hashlib.sha256(src.encode()).hexdigest()[:12]
                filename = f"wap-stock-{sha}{ext}"
                dest = os.path.join(attachment_dir, filename)
                if not os.path.exists(dest):
                    shutil.copy2(src, dest)
                abs_copy_paths.append(dest)
                # Record mapping for post-publish path rewrite
                vault_rel = os.path.relpath(dest, note_dir)
                result["path_map"][src] = vault_rel
            else:
                image_paths.append(src)
                abs_copy_paths.append(src)
    else:
        image_paths = [img["path"] for img in fetched["images"]]
        abs_copy_paths = image_paths

    anchors = pick_anchors(content, len(image_paths))
    if not anchors:
        result["warnings"].append("no insertion anchors (article too short or no sections)")
        return result

    new_content = insert_images(content, image_paths, anchors)
    if cfg.license_attribution:
        new_content += build_attribution(fetched["images"])

    result["content"] = new_content
    result["images"] = abs_copy_paths
    return result

