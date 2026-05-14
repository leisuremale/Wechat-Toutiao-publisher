"""Obsidian article preprocessing: image conversion + frontmatter normalization."""
import datetime, os, re, sys

FRONTMATTER_RE = re.compile(r"\A---\r?\n(.*?)\r?\n---\r?\n?", re.DOTALL)

# Tags that indicate an article has NOT yet been published
UNPUBLISHED_TAG_REPLACEMENTS = {
    "微信未发": "微信已发",
    "微信待发": "微信已发",
    "公众号未发": "公众号已发",
}

# Matches tags in three formats:
# 1. YAML list:  tags:\n  - tag1\n  - tag2
# 2. YAML flow:  tags: [tag1, tag2]
# 3. Inline:     tags: tag1 tag2
TAGS_BLOCK_RE = re.compile(
    r"(?m)^tags:\s*((?:\n[ \t]+-\s+.+)+|\[[^\]]+\]|.*?)\s*$"
)


def _get_field_value(fm, field):
    """Read a scalar field value from YAML frontmatter string.
    Supports `field: value`, `field: "value"`, and single-line flow."""
    pattern = re.compile(rf"(?m)^{field}:\s*(\S.*?)\s*$")
    m = pattern.search(fm)
    if m:
        return m.group(1).strip().strip('"\'')
    return None


def update_publish_status(content):
    """Replace '未发' tags with '已发' and add publish date if missing.

    Handles YAML list, flow, and inline tag formats.
    Also adds date_published if not already set.
    Returns (new_content, changed).
    """
    m = FRONTMATTER_RE.match(content)
    if not m:
        return content, False

    fm = m.group(1)
    body = content[m.end():]
    changed = False

    # 1. Replace 未发 → 已发 in tags field
    tm = TAGS_BLOCK_RE.search(fm)
    if tm:
        tags_block = tm.group(0)
        new_block = tags_block
        for old, new in UNPUBLISHED_TAG_REPLACEMENTS.items():
            if old in new_block:
                new_block = new_block.replace(old, new)
                changed = True
        if changed:
            fm = fm.replace(tags_block, new_block)

    # 2. Add date_published if not present
    if _get_field_value(fm, "date_published") is None:
        today = datetime.date.today().isoformat()
        fm = fm.rstrip() + f"\ndate_published: {today}"
        changed = True

    if not changed:
        return content, False

    return f"---\n{fm.strip()}\n---\n{body.lstrip()}", True


def build_image_index(vault):
    """Walk vault once → {filename: full_path}. First-match wins."""
    index = {}
    for root, dirs, files in os.walk(vault):
        dirs[:] = [d for d in dirs if not d.startswith(".")]
        for f in files:
            if f not in index:
                index[f] = os.path.join(root, f)
    return index


def convert_obsidian_images(content, note_dir, image_index, logger=None):
    def replace_img(m):
        inner = m.group(1).strip()
        name = inner.split("|", 1)[0]
        alt = name.rsplit(".", 1)[0] if "." in name else name

        local = os.path.join(note_dir, name)
        if os.path.exists(local):
            return f"![{alt}]({local})"

        found = image_index.get(name)
        if found and os.path.exists(found):
            return f"![{alt}]({found})"

        msg = f"image not found in vault: {name}"
        if logger:
            logger.warning(msg)
        else:
            print(f"  ⚠️  {msg}", file=sys.stderr)
        return f"<!-- IMG NOT FOUND: {name} -->"

    return re.sub(r"!\[\[([^\]]+)\]\]", replace_img, content)


def _has_field(fm_text, field):
    return re.search(rf"(?m)^{re.escape(field)}:\s", fm_text) is not None


def ensure_frontmatter(content, title, cover, author="墨言"):
    if content.startswith("﻿"):
        content = content[1:]

    m = FRONTMATTER_RE.match(content)
    if m:
        fm = m.group(1).rstrip()
        body = content[m.end():]

        if not _has_field(fm, "title"):
            fm += f"\ntitle: {title}"
        if cover and not _has_field(fm, "cover"):
            fm += f"\ncover: {cover}"
        if not _has_field(fm, "author"):
            fm += f"\nauthor: {author}"

        return f"---\n{fm.strip()}\n---\n{body.lstrip()}"

    fm = f"title: {title}"
    if cover:
        fm += f"\ncover: {cover}"
    fm += f"\nauthor: {author}"
    return f"---\n{fm}\n---\n\n{content.strip()}\n"


def preprocess_article(md_path, vault, title, cover, author="墨言", logger=None):
    """In-place preprocess of md_path. Returns final content string."""
    with open(md_path, encoding="utf-8") as f:
        content = f.read()

    note_dir = os.path.dirname(os.path.abspath(md_path))
    image_index = build_image_index(vault)
    content = convert_obsidian_images(content, note_dir, image_index, logger)
    content = ensure_frontmatter(content, title, cover, author)

    with open(md_path, "w", encoding="utf-8") as f:
        f.write(content)
    return content
