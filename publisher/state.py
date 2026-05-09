"""Sidecar state for resume-after-failure.

Layout: `<queue_dir>/.state/<article-basename>.json`. Hidden from Obsidian's
default file listing (dotfolder), survives across cron runs. Atomic writes
via os.replace.

The state mainly tracks WeChat publication (the most expensive non-idempotent
step). Toutiao auto-publish failures are non-fatal and cheap to retry.
"""
import json, os
from datetime import datetime, timezone

STATE_VERSION = 1


def state_path(article_path: str) -> str:
    queue_dir = os.path.dirname(article_path)
    basename = os.path.basename(article_path)
    return os.path.join(queue_dir, ".state", basename + ".json")


def load(article_path: str) -> dict:
    p = state_path(article_path)
    if not os.path.exists(p):
        return {}
    try:
        with open(p, encoding="utf-8") as f:
            data = json.load(f)
        if data.get("version") != STATE_VERSION:
            return {}
        return data
    except (OSError, json.JSONDecodeError):
        return {}


def save(article_path: str, state: dict) -> None:
    p = state_path(article_path)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    state["version"] = STATE_VERSION
    state["updated_at"] = datetime.now(timezone.utc).isoformat()
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)
    os.replace(tmp, p)


def clear(article_path: str) -> None:
    p = state_path(article_path)
    try:
        os.remove(p)
    except OSError:
        pass
