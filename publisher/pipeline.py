"""6-step pipeline orchestration with retry + resume.

Resume semantics: a sidecar JSON in `<queue_dir>/.state/` records the WeChat
publication once it succeeds. If the pipeline fails at any later step, the
next run picks the same article up, skips WeChat publish (the only
non-idempotent expensive step), and continues. Toutiao auto-publish failures
are non-fatal — they don't block archival.
"""
import os, shutil, tempfile, traceback

from .cover import render as render_cover
from .illustrate import illustrate as illustrate_content
from .preprocess import preprocess_article
from .retry import retry, is_likely_transient
from . import state as state_mod
from .wenyan import resolve_bin, publish_wechat, render_toutiao

# Toutiao steps that are safe to retry. After save_draft we may have already
# created a draft on the server — retrying would create duplicates.
_TOUTIAO_RETRY_SAFE = {"init", "navigate", "fill_title", "inject_body", "upload_cover"}


def find_next_article(queue_path):
    if not os.path.isdir(queue_path):
        return None
    files = sorted(
        f for f in os.listdir(queue_path)
        if f.endswith(".md") and not f.startswith(".")
    )
    return os.path.join(queue_path, files[0]) if files else None


def _wechat_retryable(r):
    if r.get("ok"):
        return False
    text = (r.get("stderr") or "") + " " + (r.get("stdout") or "")[:200] + " " + (r.get("error") or "")
    return is_likely_transient(text)


def _toutiao_retryable(r):
    if r.get("ok"):
        return False
    if r.get("step") not in _TOUTIAO_RETRY_SAFE:
        return False
    return is_likely_transient(r.get("error") or "")


def run(cfg, logger):
    """Execute the pipeline. Returns a result dict (never raises)."""
    result = {
        "success": False, "step": "init",
        "article": None, "title": None,
        "wechat_media_id": None, "toutiao_html": None,
        "toutiao_draft_url": None, "toutiao_screenshot": None,
        "book_cover": None, "quote_cards": [],
        "resumed": False,
        "warnings": [], "error": None,
    }

    staged = None
    article = None
    try:
        result["step"] = "find_article"
        article = find_next_article(cfg.queue_full)
        if not article:
            result["success"] = True
            result["step"] = "done"
            result["message"] = "HEARTBEAT_OK: queue empty"
            logger.info("queue empty")
            return result

        result["article"] = article
        title = os.path.splitext(os.path.basename(article))[0]
        result["title"] = title

        prior = state_mod.load(article)
        if prior:
            result["resumed"] = True
            logger.info(f"resuming: {os.path.basename(article)} (state={list(prior.keys())})")
        else:
            logger.info(f"picked: {os.path.basename(article)}")

        # Stage (always — staging is cheap and idempotent)
        staged_dir = os.path.join(tempfile.gettempdir(), "wap_pipeline")
        os.makedirs(staged_dir, exist_ok=True)
        staged = os.path.join(staged_dir, os.path.basename(article))
        shutil.copy2(article, staged)

        # Step 2: cover (idempotent)
        result["step"] = "generate_cover"
        cover_path = os.path.join(tempfile.gettempdir(), "wap_cover_hq.png")
        render_cover(
            title=title,
            template=cfg.cover.template,
            author=cfg.wechat.author,
            output=cover_path,
            width=cfg.cover.width,
            height=cfg.cover.height,
            extra_templates_dir=cfg.cover.templates_dir,
            subtitle=cfg.cover.subtitle,
        )
        logger.info(f"cover: {cover_path}")

        # Step 3: preprocess (idempotent on a fresh staged copy)
        result["step"] = "preprocess"
        content = preprocess_article(
            md_path=staged,
            vault=cfg.obsidian_vault,
            title=title,
            cover=cover_path,
            author=cfg.wechat.author,
            logger=logger,
        )

        # Step 3b: illustrate — book cover (top) + quote cards (inline)
        result["step"] = "illustrate"
        ill = illustrate_content(
            content=content,
            title=title,
            cfg=cfg,
            tempdir=tempfile.gettempdir(),
            vault=cfg.obsidian_vault,
            logger=logger,
        )
        if ill["content"] != content:
            with open(staged, "w", encoding="utf-8") as f:
                f.write(ill["content"])
        result["book_cover"] = ill["book_cover"]
        result["quote_cards"] = ill["quote_cards"]
        for w in ill["warnings"]:
            result["warnings"].append(f"illustrate: {w}")
        if ill["book_cover"] or ill["quote_cards"]:
            logger.info(
                f"illustrate: book_cover={'yes' if ill['book_cover'] else 'no'}, "
                f"quote_cards={len(ill['quote_cards'])}"
            )

        # Step 4: WeChat publish — skip if state says already done
        result["step"] = "publish_wechat"
        wenyan_bin = resolve_bin(cfg.wenyan_bin)

        if prior.get("wechat_published") and prior.get("wechat_media_id"):
            result["wechat_media_id"] = prior["wechat_media_id"]
            logger.info(f"wechat: skip (resumed) media_id={prior['wechat_media_id']}")
        else:
            pub = retry(
                lambda: publish_wechat(wenyan_bin, staged, cfg.wechat.theme_css),
                attempts=cfg.retry.wechat_attempts,
                base_delay=cfg.retry.base_delay,
                max_delay=cfg.retry.max_delay,
                retryable=_wechat_retryable,
                logger=logger,
                label="publish_wechat",
            )
            if not pub.get("ok"):
                result["error"] = f"WeChat publish failed: {pub.get('stderr') or (pub.get('stdout') or '')[:200] or pub.get('error')}"
                logger.error(result["error"])
                return result
            result["wechat_media_id"] = pub["media_id"]
            state_mod.save(article, {
                "wechat_published": True,
                "wechat_media_id": pub["media_id"],
            })
            logger.info(f"published media_id={pub['media_id']}")

        # Step 5: Toutiao render (cheap, idempotent — always run)
        result["step"] = "render_toutiao"
        os.makedirs(cfg.toutiao_dir, exist_ok=True)
        html_path = os.path.join(cfg.toutiao_dir, title + ".html")
        rt = render_toutiao(wenyan_bin, staged, cfg.wechat.theme_css)
        rendered_html = None
        if rt["ok"] and rt["stdout"]:
            rendered_html = rt["stdout"]
            with open(html_path, "w", encoding="utf-8") as f:
                f.write(rendered_html)
            result["toutiao_html"] = html_path
            logger.info(f"toutiao html: {html_path}")
        else:
            warn = f"Toutiao render failed: {rt['stderr'] or 'empty output'}"
            result["warnings"].append(warn)
            logger.warning(warn)

        # Step 5b: Toutiao auto-publish — skip if already drafted; retry safe steps only
        if cfg.toutiao.auto and rendered_html:
            result["step"] = "publish_toutiao"
            if prior.get("toutiao_drafted"):
                result["toutiao_draft_url"] = prior.get("toutiao_draft_url")
                logger.info(f"toutiao: skip (resumed) draft_url={prior.get('toutiao_draft_url')}")
            elif not cfg.toutiao.user_data_dir:
                msg = "toutiao.auto=true but user_data_dir not set; skipping auto-publish"
                result["warnings"].append(msg)
                logger.warning(msg)
            else:
                from .toutiao import publish_draft  # lazy
                td = retry(
                    lambda: publish_draft(
                        html=rendered_html,
                        title=title,
                        cover_path=cover_path,
                        user_data_dir=cfg.toutiao.user_data_dir,
                        selectors=cfg.toutiao.selectors,
                        timeout_ms=cfg.toutiao.timeout_ms,
                        screenshot_dir=cfg.toutiao.screenshot_dir,
                        headless=cfg.toutiao.headless,
                    ),
                    attempts=cfg.retry.toutiao_attempts,
                    base_delay=cfg.retry.base_delay,
                    max_delay=cfg.retry.max_delay,
                    retryable=_toutiao_retryable,
                    logger=logger,
                    label="publish_toutiao",
                )
                if td.get("ok"):
                    result["toutiao_draft_url"] = td.get("draft_url")
                    result["toutiao_screenshot"] = td.get("screenshot")
                    for w in td.get("warnings", []):
                        result["warnings"].append(f"toutiao: {w}")
                    state_mod.save(article, {
                        **state_mod.load(article),
                        "toutiao_drafted": True,
                        "toutiao_draft_url": td.get("draft_url"),
                    })
                    logger.info(f"toutiao draft saved: {td.get('draft_url')}")
                else:
                    msg = f"toutiao auto-publish failed: {td.get('error')}"
                    result["warnings"].append(msg)
                    logger.warning(msg)

        # Step 6: archive (state cleared on success)
        result["step"] = "archive"
        os.makedirs(cfg.published_full, exist_ok=True)
        dest = os.path.join(cfg.published_full, os.path.basename(article))
        shutil.move(staged, dest)
        staged = None
        os.remove(article)
        state_mod.clear(article)
        logger.info(f"archived: {dest}")

        result["success"] = True
        result["step"] = "done"
        return result

    except Exception as e:
        result["error"] = f"{result['step']}: {e}"
        result["traceback"] = traceback.format_exc()
        logger.exception("pipeline error")
        return result
    finally:
        if staged and os.path.exists(staged):
            try:
                os.remove(staged)
            except OSError:
                pass
