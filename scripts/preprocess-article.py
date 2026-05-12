#!/usr/bin/env python3
"""Backward-compat CLI → publisher.preprocess.preprocess_article"""
import argparse, os, sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from publisher.preprocess import preprocess_article


def main():
    p = argparse.ArgumentParser(description="Preprocess Obsidian article in place.")
    p.add_argument("md_path")
    p.add_argument("--title", default="")
    p.add_argument("--cover", default="")
    p.add_argument("--author", default="墨言")
    p.add_argument("--vault", required=True, help="Obsidian vault root for image lookup")
    args = p.parse_args()

    title = args.title or os.path.splitext(os.path.basename(args.md_path))[0]
    preprocess_article(args.md_path, args.vault, title, args.cover, args.author)
    print(f"✅ Preprocessed: {os.path.basename(args.md_path)}")
    print(f"   title: {title}, cover: {args.cover}, author: {args.author}")


if __name__ == "__main__":
    main()
