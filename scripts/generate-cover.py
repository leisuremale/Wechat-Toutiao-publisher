#!/usr/bin/env python3
"""Backward-compat CLI → publisher.cover.render"""
import argparse, os, sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from publisher.cover import DEFAULT_OUTPUT, load_templates, render


def main():
    available = sorted(load_templates().keys())
    p = argparse.ArgumentParser(description="Generate WeChat cover image")
    p.add_argument("title", help="Cover title text")
    p.add_argument("-t", "--template", default="literary",
                   choices=available or None,
                   help=f"Template (available: {available})")
    p.add_argument("-a", "--author", default="墨言")
    p.add_argument("-o", "--output", default=DEFAULT_OUTPUT)
    p.add_argument("--templates-dir", default=None,
                   help="Extra templates directory (overrides bundled)")
    args = p.parse_args()

    out = render(
        args.title, args.template, args.author, args.output,
        extra_templates_dir=args.templates_dir,
    )
    size_kb = os.path.getsize(out) / 1024
    print(f"✅ {out} ({size_kb:.0f}KB)")


if __name__ == "__main__":
    main()
