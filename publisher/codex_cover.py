"""Codex AI-generated cover images for WeChat article cards.

Uses Codex CLI's built-in `image_gen` tool to create atmospheric background
images, then overlays title text using Pillow for crisp typography.

Design principles:
- Each article gets a unique cover (no repeats)
- Style varies by book genre/mood (4 style families × random variations)
- Book-themed background + precise title overlay = best of both worlds
  (Codex for artistic expression, Pillow for clean text)
- Cached by article title hash; re-generating same title reuses cache
- Falls back to Playwright HTML/CSS cover if Codex fails

Usage:
    from .codex_cover import generate_cover
    path = generate_cover(title="《百年孤独》", subtitle="乐之读书评",
                          author="墨言", output="/tmp/cover.png")
"""
from __future__ import annotations
import copy, hashlib, json, os, random, re, shutil, subprocess, time
from pathlib import Path
from typing import Optional

# ── Paths ────────────────────────────────────────────────────
CODEX_BIN = "/Applications/Codex.app/Contents/Resources/codex"
CODEX_HOME = os.path.expanduser("~/.codex")
CODEX_GENERATED = os.path.join(CODEX_HOME, "generated_images")

# ── Style families ───────────────────────────────────────────
# Each family has a visual style description + color palette + mood words.
# Styles are selected randomly per article for variety.

STYLE_FAMILIES = {
    "ink": {
        "name": "水墨意境",
        "description": (
            "Chinese ink wash painting (水墨画) style blended with modern photography. "
            "Soft brush-like textures, muted grays with subtle ink blacks, negative space "
            "composition. Elegant, contemplative, timeless."
        ),
        "palette": "monochromatic grays and blacks with one muted accent color (vermilion red, celadon green, or indigo blue)",
        "mood": "contemplative, elegant, timeless, serene",
        "lighting": "soft diffused natural light, misty atmosphere",
    },
    "literary": {
        "name": "文学生活",
        "description": (
            "Warm library or study room scene with natural daylight. Old leather-bound books, "
            "wooden shelves, reading nook with soft fabrics. Photorealistic editorial style "
            "with natural textures and warm tones."
        ),
        "palette": "warm amber, deep brown, cream, forest green, soft gold",
        "mood": "intimate, scholarly, warm, nostalgic",
        "lighting": "golden hour sunlight through windows, soft shadows, dust motes in light beams",
    },
    "abstract": {
        "name": "抽象意境",
        "description": (
            "Abstract artistic composition evoking the emotional core of literature. "
            "Layered textures, paint strokes, paper grain. Like a modern art book cover. "
            "Stylized with rich textures and deliberate imperfections."
        ),
        "palette": "varied by mood — melancholic (deep blues, purples), passionate (crimson, gold), peaceful (sage, ivory)",
        "mood": "evocative, artistic, layered, mysterious",
        "lighting": "dramatic chiaroscuro or soft gradient with texture overlay",
    },
}

# ── Prompt builder ────────────────────────────────────────────
def _pick_style(title: str) -> dict:
    """Pick a style family for this article. Deterministic by title hash
    so the same title always gets the same family, but each article varies."""
    h = hashlib.sha256(title.encode()).digest()[0]
    families = list(STYLE_FAMILIES.values())
    idx = h % len(families)
    return families[idx]


def _extract_book_name(title: str) -> str:
    """Extract the book name from a title like '《百年孤独》：孤独的宿命'."""
    m = re.search(r'《([^》]+)》', title)
    if m:
        return m.group(1)
    # Try the part before colon
    parts = title.split("：", 1)
    return parts[0].strip()


def _build_cover_prompt(title: str, subtitle: str) -> str:
    """Build a Codex image_gen prompt for the cover background.

    The prompt generates only the background — title text is overlaid later
    by Pillow for perfect typography.

    Key constraint: the center 1:1 square area must work as a standalone
    composition, because WeChat auto-crops the center for forwarding cards
    and the official account homepage.
    """
    book = _extract_book_name(title)
    style = _pick_style(title)

    safe_zone = (
        "CRITICAL — SAFE ZONE REQUIREMENT: The center 1:1 square area of this "
        "900×500 landscape image MUST be a complete, self-contained composition. "
        "This center square will be cropped out and used independently as a "
        "1:1 card on WeChat forwarding/homepage. Important visual elements "
        "(the focal point, key textures, atmospheric details) should be "
        "concentrated WITHIN this center square. The left and right 200px "
        "margins (beyond the center 500×500) can be complementary but less "
        "essential — they are decorative framing that may be cropped away. "
        "The center square should feel like a complete image on its own."
    )

    layout_hint = (
        "A semi-transparent dark horizontal strip will be placed across the "
        "center for text readability — the background in this zone should be "
        "visually interesting but not too busy or high-contrast. "
        "The most active decorative elements should be at the top and bottom "
        "edges, framing rather than competing with the center text area."
    )

    prompt = (
        f"Use case: stylized-concept\n"
        f"Asset type: book review cover background, 900x500 landscape, for WeChat article card\n"
        f"Primary request: Create an atmospheric background image for a book review of "
        f"\"{book}\". {style['description']} {safe_zone}\n"
        f"Style: {style['name']} ({style['description']})\n"
        f"Color palette: {style['palette']}\n"
        f"Mood: {style['mood']}\n"
        f"Lighting: {style['lighting']}\n"
        f"Composition: {layout_hint}\n"
        f"Technical: 900x500 pixels, no text in the image (text will be added later). "
        f"No watermarks, no logos, no QR codes."
    )
    return prompt


def _find_codex() -> Optional[str]:
    """Find the Codex binary."""
    if os.path.exists(CODEX_BIN):
        return CODEX_BIN
    # Try PATH
    try:
        result = subprocess.run(["which", "codex"], capture_output=True, text=True, timeout=5)
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception:
        pass
    return None


def _list_generated_before() -> set:
    """Snapshot of existing generated images before running codex."""
    existing = set()
    if not os.path.isdir(CODEX_GENERATED):
        return existing
    for root, dirs, files in os.walk(CODEX_GENERATED):
        for f in files:
            if f.endswith((".png", ".jpg", ".webp")):
                existing.add(os.path.join(root, f))
    return existing


def _find_new_images(before: set) -> list:
    """Find newly generated images after codex run. Returns newest first."""
    after = set()
    if not os.path.isdir(CODEX_GENERATED):
        return []
    for root, dirs, files in os.walk(CODEX_GENERATED):
        for f in files:
            if f.endswith((".png", ".jpg", ".webp")):
                path = os.path.join(root, f)
                if path not in before:
                    after.add(path)
    # Sort by modification time, newest first
    return sorted(after, key=os.path.getmtime, reverse=True)


def _cache_path(title: str, cache_dir: str) -> str:
    h = hashlib.sha256(title.encode()).hexdigest()[:16]
    return os.path.join(cache_dir, f"codex_cover_{h}_bg.png")


def _clean_title(title: str) -> str:
    """Strip numeric prefix from title for display (e.g., '309《...》' → '《...》')."""
    return re.sub(r'^\d+\s*', '', title).strip()


def _parse_title_display(display_title: str) -> tuple:
    """Parse a cleaned title into (book_name, taglines).

    Book name = the 《...》 part (enlarged, always on its own line).
    Taglines = the rest, split by Chinese/English commas into separate lines.

    When there is no 《》, the entire title is split by commas into
    tagline_lines and book_part is empty — so non-book titles display
    as centered multi-line text.

    Examples:
        '《不二》每一个在找答案的人，都在走一条没走完的路'
        → ('《不二》', ['每一个在找答案的人', '都在走一条没走完的路'])
        '想拒绝却说不出口，怕得罪人，怎么破？'
        → ('', ['想拒绝却说不出口', '怕得罪人', '怎么破？'])
    """
    book_part = ""
    rest_part = ""
    m = re.search(r'《([^》]+)》', display_title)
    if m:
        book_part = f"《{m.group(1)}》"
        rest_part = display_title[m.end():].strip()
    else:
        # No book name — treat the whole title as taglines split by commas
        rest_part = display_title

    tagline_lines = []
    if rest_part:
        # Split by Chinese comma or English comma, keep non-empty parts
        parts = re.split(r'[，,]', rest_part)
        tagline_lines = [p.strip() for p in parts if p.strip()]

    return book_part, tagline_lines


def _overlay_title(bg_path: str, title: str, subtitle: str,
                   author: str, output: str) -> str:
    """Overlay title text on the generated background using Pillow.

    Produces a 900×500 (2.35:1) WeChat article card. The center area
    (500×500) is designed to work as the WeChat 1:1 crop for forwarding
    cards and the official account homepage.

    Layout:
        《书名》         ← Songti serif, enlarged, centered
        标签行1,        ← split at commas
        标签行2         ← centered
        乐之读           ← STHeiti Light, thinner style, no "书评"
    """
    from PIL import Image, ImageDraw, ImageFont

    # Clean the title for display (strip number prefix like '309')
    display_title = _clean_title(title)

    img = Image.open(bg_path).convert("RGBA")
    target_w, target_h = 900, 500
    img = img.resize((target_w, target_h), Image.LANCZOS)
    draw = ImageDraw.Draw(img)

    # ── Font loading ──
    # Title: 宋体 (Songti) — classic serif, literary feel
    songti_path = "/System/Library/Fonts/Supplemental/Songti.ttc"
    # Subtitle: STHeiti Light — lighter weight, distinguishes from title
    heiti_path = "/System/Library/Fonts/STHeiti Light.ttc"
    # Fallback: PingFang (sans-serif)
    pingfang_path = "/System/Library/Fonts/PingFang.ttc"

    title_font = tagline_font = sub_font = None
    _title_path = _sub_path = None

    # ── Title font: Songti (serif, distinctive) ──
    if os.path.exists(songti_path):
        try:
            title_font = ImageFont.truetype(songti_path, 48)
            tagline_font = ImageFont.truetype(songti_path, 26)
            _title_path = songti_path
        except Exception:
            pass
    if title_font is None and os.path.exists(pingfang_path):
        try:
            title_font = ImageFont.truetype(pingfang_path, 48)
            tagline_font = ImageFont.truetype(pingfang_path, 26)
            _title_path = pingfang_path
        except Exception:
            pass

    # ── Subtitle font: STHeiti Light (thinner, contrasts with title) ──
    if os.path.exists(heiti_path):
        try:
            sub_font = ImageFont.truetype(heiti_path, 20)
            _sub_path = heiti_path
        except Exception:
            pass
    if sub_font is None and os.path.exists(pingfang_path):
        try:
            sub_font = ImageFont.truetype(pingfang_path, 20)
            _sub_path = pingfang_path
        except Exception:
            pass
    if sub_font is None and title_font is not None:
        sub_font = title_font

    if title_font is None:
        title_font = tagline_font = sub_font = ImageFont.load_default()

    # ── Parse title into book name + taglines ──
    book_part, tagline_lines = _parse_title_display(display_title)

    # If tagline lines are too long, wrap them
    max_tagline_width = target_w - 120
    wrapped_taglines = []
    for line in tagline_lines:
        bbox = draw.textbbox((0, 0), line, font=tagline_font)
        if bbox[2] - bbox[0] <= max_tagline_width:
            wrapped_taglines.append(line)
        else:
            wrapped = _wrap_text(line, tagline_font, max_tagline_width, draw)
            wrapped_taglines.extend(wrapped.split("\n"))

    # ── Semi-transparent overlay strip ──
    overlay = Image.new("RGBA", (target_w, target_h), (0, 0, 0, 0))
    overlay_draw = ImageDraw.Draw(overlay)

    strip_center = target_h // 2
    strip_half = 80
    for y in range(strip_center - strip_half, strip_center + strip_half):
        dist = abs(y - strip_center)
        alpha = max(0, int(180 * (1 - dist / strip_half)))
        overlay_draw.line([(0, y), (target_w, y)], fill=(0, 0, 0, alpha))

    img = Image.alpha_composite(img, overlay)
    draw = ImageDraw.Draw(img)

    # ── Calculate text block height & starting Y ──
    book_line_h = 64       # was 52 — more breathing room
    tagline_line_h = 38    # was 30 — more line spacing
    # When there's no book name (non-《》 titles), use a larger font for taglines
    tagline_font_size = 26 if book_part else 32
    if not book_part and _title_path:
        try:
            tagline_font = ImageFont.truetype(_title_path, tagline_font_size)
        except Exception:
            pass
    gap_book_to_taglines = 24 if (book_part and tagline_lines) else 0    # was 18
    gap_to_subtitle = 28   # was 20
    sub_height = 34         # was 26
    line_gap_after_sub = 36 # was 28

    total_h = book_line_h if book_part else 0
    if tagline_lines:
        total_h += gap_book_to_taglines + len(wrapped_taglines) * tagline_line_h
    total_h += gap_to_subtitle + sub_height + line_gap_after_sub

    start_y = target_h // 2 - total_h // 2

    current_y = start_y

    # ── Book name: enlarged, centered ──
    if book_part:
        book_color = (255, 255, 255, 240)
        bbox = draw.textbbox((0, 0), book_part, font=title_font)
        bw = bbox[2] - bbox[0]
        bx = (target_w - bw) // 2
        draw.text((bx + 2, current_y + 2), book_part, font=title_font, fill=(0, 0, 0, 80))
        draw.text((bx, current_y), book_part, font=title_font, fill=book_color)
        current_y += book_line_h + gap_book_to_taglines

    # ── Tagline lines: centered, split at commas ──
    tagline_color = (255, 255, 255, 200)
    if tagline_lines:
        for line in wrapped_taglines:
            bbox = draw.textbbox((0, 0), line, font=tagline_font)
            tw = bbox[2] - bbox[0]
            tx = (target_w - tw) // 2
            draw.text((tx + 1, current_y + 1), line, font=tagline_font, fill=(0, 0, 0, 60))
            draw.text((tx, current_y), line, font=tagline_font, fill=tagline_color)
            current_y += tagline_line_h

    # ── Subtitle ──
    sub_color = (255, 255, 255, 180)
    sub_y = current_y + gap_to_subtitle
    draw.text((target_w // 2, sub_y), subtitle, font=sub_font,
              fill=sub_color, anchor="mt")

    # ── Thin decorative line ──
    line_y = sub_y + line_gap_after_sub
    line_w = 60
    line_x = (target_w - line_w) // 2
    draw.line([(line_x, line_y), (line_x + line_w, line_y)],
              fill=(255, 255, 255, 100), width=1)

    img = img.convert("RGB")
    img.save(output, "PNG", quality=95)
    return output


def _wrap_text(text: str, font, max_width: int, draw) -> str:
    """Wrap Chinese text to fit within max_width pixels."""
    # For Chinese text, each character is roughly equal width
    result = []
    current_line = ""
    for char in text:
        test = current_line + char
        bbox = draw.textbbox((0, 0), test, font=font)
        if bbox[2] - bbox[0] > max_width and current_line:
            result.append(current_line)
            current_line = char
        else:
            current_line = test
    if current_line:
        result.append(current_line)
    return "\n".join(result)


# ── Main API ─────────────────────────────────────────────────
def generate_cover(title: str, subtitle: str = "乐之读",
                   author: str = "墨言", output: Optional[str] = None,
                   cache_dir: Optional[str] = None,
                   logger=None) -> Optional[dict]:
    """Generate Codex AI cover images for a WeChat article.

    Produces two sizes from the same background:
    - 'wide': 900×500 (2.35:1) for WeChat message list card
    - 'square': 500×500 (1:1) for forwarding cards / official account homepage

    Args:
        title: Article title (e.g. '309《...》' → displayed as '《...》')
        subtitle: Publication subtitle
        author: Author name
        output: Output directory or prefix for saving images
        cache_dir: Cache directory for reuse

    Returns:
        Path to generated cover image, or None if generation failed.
    """
    output = output or os.path.join(os.path.expanduser("~"), "tmp", "wap_cover_codex.png")
    cache_dir = cache_dir or os.path.join(os.path.expanduser("~"), "tmp", "wap_codex_covers")
    os.makedirs(cache_dir, exist_ok=True)

    # Cache uses original title (with number prefix) for keying
    bg_cache = _cache_path(title, cache_dir)
    final_cache = bg_cache.replace("_bg.png", ".png")

    if os.path.exists(final_cache) and os.path.getsize(final_cache) > 0:
        if logger:
            logger.info(f"codex_cover: cache hit for '{title[:40]}...'")
        shutil.copy2(final_cache, output)
        return output

    codex = _find_codex()
    if not codex:
        if logger:
            logger.warning("codex_cover: Codex binary not found")
        return None

    # Build prompt using clean title (without number prefix)
    prompt = _build_cover_prompt(title, subtitle)

    if logger:
        style = _pick_style(title)
        logger.info(f"codex_cover: style={style['name']}, title='{title[:40]}...'")

    before = _list_generated_before()

    try:
        # Run codex exec with the prompt
        env = os.environ.copy()
        env["CODEX_HOME"] = CODEX_HOME
        if not (env.get("https_proxy") or env.get("HTTPS_PROXY")):
            env["https_proxy"] = "http://127.0.0.1:7890"
            env["http_proxy"] = "http://127.0.0.1:7890"
            if logger:
                logger.debug("codex_cover: no proxy env, using ClashX default 127.0.0.1:7890")

        proc = subprocess.run(
            [codex, "exec", "--model", "gpt-5.5", "-"],
            input=prompt,
            capture_output=True,
            text=True,
            timeout=180,
            cwd=os.path.expanduser("~/.openclaw/dashboard"),
            env=env,
        )
        if logger:
            stderr_tail = (proc.stderr or "")[-200:]
            stdout_tail = (proc.stdout or "")[-200:]
            logger.debug(f"codex_cover: exit={proc.returncode} stderr={stderr_tail}")

        time.sleep(2)
        new_images = _find_new_images(before)

        if new_images:
            bg_path = new_images[0]
            if logger:
                logger.info(f"codex_cover: generated {os.path.basename(bg_path)} ({os.path.getsize(bg_path)} bytes)")

            # Overlay title text on the background
            _overlay_title(bg_path, title, subtitle, author, final_cache)
            shutil.copy2(final_cache, output)
            return output
        else:
            if logger:
                logger.warning("codex_cover: no new images found after generation")
            return None

    except subprocess.TimeoutExpired:
        if logger:
            logger.warning("codex_cover: timeout (180s)")
        return None
    except Exception as e:
        if logger:
            logger.warning(f"codex_cover: {e}")
        return None


def test_generation(title: str = "《百年孤独》：孤独是一种宿命",
                    subtitle: str = "墨 言 书 评") -> Optional[str]:
    """Quick test: generate a cover and return the path."""
    return generate_cover(title=title, subtitle=subtitle)
