#!/usr/bin/env python3
"""preprocess-article.py — 预处理 Obsidian 文章：转换图片语法、补齐 frontmatter"""
import sys, os, re, json

VAULT = "/Users/lijingyan/Library/Mobile Documents/iCloud~md~obsidian/Documents/Le"

def find_image_in_vault(name):
    """Search vault for an image file by name."""
    for root, dirs, files in os.walk(VAULT):
        # Skip hidden dirs and system dirs
        dirs[:] = [d for d in dirs if not d.startswith('.')]
        if name in files:
            return os.path.join(root, name)
    return None

def convert_obsidian_images(content, note_dir):
    """Convert Obsidian ![[image]] syntax to standard Markdown ![](path)."""
    def replace_img(m):
        full = m.group(0)
        inner = m.group(1).strip()
        # Remove |size suffix: ![[img.png|300]]
        parts = inner.split('|')
        name = parts[0]
        alt = parts[0].rsplit('.', 1)[0] if '.' in parts[0] else parts[0]

        # Try relative to note directory first
        local_path = os.path.join(note_dir, name)
        if os.path.exists(local_path):
            return f'![{alt}]({local_path})'

        # Search entire vault
        found = find_image_in_vault(name)
        if found:
            return f'![{alt}]({found})'

        # Not found — keep as text reference but strip syntax
        print(f"  ⚠️  Image not found in vault: {name}")
        return f'<!-- IMG NOT FOUND: {name} -->'

    # Match ![[image.png]] or ![[image.png|300]]
    content = re.sub(r'!\[\[([^\]]+)\]\]', replace_img, content)
    return content

def ensure_frontmatter(content, title, cover, author="墨言"):
    """Ensure YAML frontmatter exists with required fields."""
    if content.startswith('---'):
        # Has frontmatter — patch missing fields
        end = content.index('---', 3)
        fm = content[3:end].strip()
        body = content[end+3:]

        if 'title:' not in fm:
            fm += f'\ntitle: {title}'
        if 'cover:' not in fm and cover:
            fm += f'\ncover: {cover}'
        if 'author:' not in fm:
            fm += f'\nauthor: {author}'

        return f'---\n{fm.strip()}\n---\n{body.strip()}'
    else:
        # No frontmatter — create one
        fm = f'title: {title}\ncover: {cover}\nauthor: {author}'
        return f'---\n{fm}\n---\n\n{content.strip()}'

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: preprocess-article.py <article.md> [--title TITLE] [--cover COVER] [--author AUTHOR]")
        sys.exit(1)

    md_path = sys.argv[1]
    title = ""
    cover = ""
    author = "墨言"

    args = sys.argv[2:]
    i = 0
    while i < len(args):
        if args[i] == '--title' and i+1 < len(args):
            title = args[i+1]; i += 2
        elif args[i] == '--cover' and i+1 < len(args):
            cover = args[i+1]; i += 2
        elif args[i] == '--author' and i+1 < len(args):
            author = args[i+1]; i += 2
        else:
            i += 1

    note_dir = os.path.dirname(os.path.abspath(md_path))

    with open(md_path) as f:
        content = f.read()

    # Convert Obsidian image syntax
    content = convert_obsidian_images(content, note_dir)

    # Auto-extract title from filename if not provided
    if not title:
        title = os.path.splitext(os.path.basename(md_path))[0]

    # Ensure frontmatter
    content = ensure_frontmatter(content, title, cover, author)

    # Write back
    with open(md_path, 'w') as f:
        f.write(content)

    print(f"✅ Preprocessed: {os.path.basename(md_path)}")
    print(f"   title: {title}, cover: {cover}, author: {author}")
