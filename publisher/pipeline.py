"""6-step pipeline orchestration with retry + resume.

Resume semantics: a sidecar JSON in `<queue_dir>/.state/` records the WeChat
publication once it succeeds. If the pipeline fails at any later step, the
next run picks the same article up, skips WeChat publish (the only
non-idempotent expensive step), and continues. Toutiao auto-publish failures
are non-fatal — they don't block archival.
"""
import os, re, shutil, tempfile, traceback

from .cover import render as render_cover, render_codex
from .illustrate import illustrate as illustrate_content
from .preprocess import preprocess_article, update_publish_status
from .retry import retry, is_likely_transient
from . import state as state_mod
from .wenyan import resolve_bin, publish_wechat, render_toutiao

# Toutiao steps that are safe to retry. After save_draft we may have already
# created a draft on the server — retrying would create duplicates.
_TOUTIAO_RETRY_SAFE = {"init", "navigate", "fill_title", "inject_body", "upload_cover"}


def find_next_article(queue_path):
    if not os.path.isdir(queue_path):
        return None
    files = [
        f for f in os.listdir(queue_path)
        if f.endswith(".md") and not f.startswith(".")
    ]
    if not files:
        return None
    import random
    return os.path.join(queue_path, random.choice(files))


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


def _process_account(cfg, account, logger) -> dict:
    """Process one article from a single account's queue. Returns a result dict."""
    result = {
        "success": False, "step": "init",
        "account": account.name,
        "article": None, "title": None,
        "wechat_media_id": None, "toutiao_html": None,
        "toutiao_draft_url": None, "toutiao_screenshot": None,
        "book_cover": None, "quote_cards": [], "stock_images": [],
        "resumed": False,
        "warnings": [], "error": None,
    }

    staged = None
    article = None
    wechat = account.wechat
    cover = account.cover

    try:
        result["step"] = "find_article"
        article = find_next_article(account.queue_full)
        if not article:
            result["success"] = True
            result["step"] = "done"
            result["message"] = f"HEARTBEAT_OK: {account.name} queue empty"
            logger.info(f"[{account.name}] queue empty")
            return result

        result["article"] = article
        title = os.path.splitext(os.path.basename(article))[0]
        # Strip numeric prefix for WeChat display (e.g. "309《...》" → "《...》")
        title_clean = re.sub(r'^\d+\s*', '', title)
        result["title"] = title_clean

        prior = state_mod.load(article)
        if prior:
            result["resumed"] = True
            logger.info(f"[{account.name}] resuming: {os.path.basename(article)}")
        else:
            logger.info(f"[{account.name}] picked: {os.path.basename(article)}")

        # Stage
        staged_dir = os.path.join(tempfile.gettempdir(), "wap_pipeline")
        os.makedirs(staged_dir, exist_ok=True)
        staged = os.path.join(staged_dir, os.path.basename(article))
        shutil.copy2(article, staged)

        # Step 2: cover
        result["step"] = "generate_cover"
        cover_path = os.path.join(tempfile.gettempdir(), "wap_cover_hq.png")
        if cover.use_codex:
            cover_path = render_codex(
                title=title,
                author=wechat.author,
                output=cover_path,
                subtitle=cover.subtitle,
                logger=logger,
            )
            logger.info(f"[{account.name}] cover (codex): {cover_path}")
        else:
            render_cover(
                title=title,
                template=cover.template,
                author=wechat.author,
                output=cover_path,
                width=900,
                height=500,
                extra_templates_dir=None,
                subtitle=cover.subtitle,
            )
            logger.info(f"[{account.name}] cover: {cover_path}")

        # Step 3: preprocess
        result["step"] = "preprocess"
        content = preprocess_article(
            md_path=staged,
            vault=cfg.obsidian_vault,
            title=title_clean,
            cover=cover_path,
            author="乐之读",
            logger=logger,
        )

        # Step 3a: insert Codex cover as first image (replaces book cover)
        import hashlib
        cover_sha = hashlib.sha256(cover_path.encode()).hexdigest()[:12]
        cover_temp = os.path.join(tempfile.gettempdir(), f"wap-cover-{cover_sha}.png")
        attachment_dir = os.path.join(cfg.obsidian_vault, "7-存档区", "attachment")
        os.makedirs(attachment_dir, exist_ok=True)
        cover_attachment = os.path.join(attachment_dir, f"wap-cover-{cover_sha}.png")
        # Copy to temp for wenyan (no spaces/Chinese in path)
        shutil.copy2(cover_path, cover_temp)
        # Also copy to vault for Obsidian
        if not os.path.exists(cover_attachment) or os.path.getsize(cover_attachment) == 0:
            shutil.copy2(cover_path, cover_attachment)
        # Insert after frontmatter, before first content line
        fm_end = content.find("\n", content.index("---", 4) + 3) + 1
        body = content[fm_end:].strip()
        content = content[:fm_end] + f"\n![封面]({cover_temp})\n\n" + body
        with open(staged, "w", encoding="utf-8") as f:
            f.write(content)
        logger.info(f"[{account.name}] cover inserted as first image")

        # Step 3b: illustrate
        snapshot_path = staged + ".snapshot"
        if prior.get("wechat_published") and os.path.exists(snapshot_path):
            result["step"] = "illustrate"
            shutil.copy2(snapshot_path, staged)
            image_path_map = prior.get("image_path_map") or {}
            logger.info(f"[{account.name}] illustrate: restored from snapshot (resume)")
        elif prior.get("wechat_published"):
            logger.warning(f"[{account.name}] illustrate: snapshot missing on resume")
        if not (prior.get("wechat_published") and os.path.exists(snapshot_path)):
            result["step"] = "illustrate"
            ill = illustrate_content(
                content=content,
                title=title,
                cfg=cfg,
                tempdir=tempfile.gettempdir(),
                vault=cfg.obsidian_vault,
                article_path=article,
                logger=logger,
            )
            if ill["content"] != content:
                with open(staged, "w", encoding="utf-8") as f:
                    f.write(ill["content"])
            result["book_cover"] = ill["book_cover"]
            result["quote_cards"] = ill["quote_cards"]
            result["stock_images"] = ill.get("stock_images", [])
            image_path_map = ill.get("path_map", {})
            # Add Codex cover mapping so Obsidian archive gets vault-relative path
            # compute against publish destination, NOT temp staging dir
            if cover_temp and cover_attachment:
                image_path_map[cover_temp] = os.path.relpath(cover_attachment, account.published_full)
            for w in ill["warnings"]:
                result["warnings"].append(f"illustrate: {w}")
            if ill["book_cover"] or ill["quote_cards"]:
                logger.info(
                    f"[{account.name}] illustrate: book_cover={'yes' if ill['book_cover'] else 'no'}, "
                    f"quote_cards={len(ill['quote_cards'])}"
                )
            shutil.copy2(staged, snapshot_path)

        # Step 4: WeChat publish
        result["step"] = "publish_wechat"
        wenyan_bin = resolve_bin(cfg.wenyan_bin)

        if prior.get("wechat_published") and prior.get("wechat_media_id"):
            result["wechat_media_id"] = prior["wechat_media_id"]
            logger.info(f"[{account.name}] wechat: skip (resumed) media_id={prior['wechat_media_id']}")
        else:
            pub = retry(
                lambda: publish_wechat(wenyan_bin, staged, wechat.theme_css,
                                       account_config=wechat),
                attempts=cfg.retry.wechat_attempts,
                base_delay=cfg.retry.base_delay,
                max_delay=cfg.retry.max_delay,
                retryable=_wechat_retryable,
                logger=logger,
                label=f"publish_wechat[{account.name}]",
            )
            if not pub.get("ok"):
                result["error"] = f"WeChat publish failed: {pub.get('stderr') or (pub.get('stdout') or '')[:200] or pub.get('error')}"
                logger.error(f"[{account.name}] {result['error']}")
                return result
            result["wechat_media_id"] = pub["media_id"]
            state_mod.save(article, {
                "wechat_published": True,
                "wechat_media_id": pub["media_id"],
                "image_path_map": image_path_map,
            })
            logger.info(f"[{account.name}] published media_id={pub['media_id']}")

        # Step 5: Toutiao render
        result["step"] = "render_toutiao"
        os.makedirs(cfg.toutiao_dir, exist_ok=True)
        html_path = os.path.join(cfg.toutiao_dir, title + ".html")
        rt = render_toutiao(wenyan_bin, staged, wechat.theme_css)
        rendered_html = None
        if rt["ok"] and rt["stdout"]:
            rendered_html = rt["stdout"]
            with open(html_path, "w", encoding="utf-8") as f:
                f.write(rendered_html)
            result["toutiao_html"] = html_path
            logger.info(f"[{account.name}] toutiao html: {html_path}")
        else:
            warn = f"Toutiao render failed: {rt['stderr'] or 'empty output'}"
            result["warnings"].append(warn)
            logger.warning(f"[{account.name}] {warn}")

        # Step 5b: Toutiao auto-publish
        if cfg.toutiao.auto and rendered_html:
            result["step"] = "publish_toutiao"
            if prior.get("toutiao_drafted"):
                result["toutiao_draft_url"] = prior.get("toutiao_draft_url")
                logger.info(f"[{account.name}] toutiao: skip (resumed)")
            elif not cfg.toutiao.user_data_dir:
                msg = "toutiao.auto=true but user_data_dir not set; skipping auto-publish"
                result["warnings"].append(msg)
                logger.warning(msg)
            else:
                from .toutiao import publish_draft
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
                    label=f"publish_toutiao[{account.name}]",
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
                    logger.info(f"[{account.name}] toutiao draft saved")
                else:
                    msg = f"toutiao auto-publish failed: {td.get('error')}"
                    result["warnings"].append(msg)
                    logger.warning(f"[{account.name}] {msg}")

        # Rewrite image paths
        if image_path_map:
            result["step"] = "rewrite_image_paths"
            with open(staged, encoding="utf-8") as f:
                staged_content = f.read()
            replaced = 0
            for tmp_path, vault_rel in image_path_map.items():
                if tmp_path in staged_content:
                    staged_content = staged_content.replace(tmp_path, vault_rel)
                    replaced += 1
            if replaced:
                with open(staged, "w", encoding="utf-8") as f:
                    f.write(staged_content)
                logger.info(f"[{account.name}] image_paths: {replaced} rewritten")

        # Update frontmatter
        result["step"] = "update_frontmatter"
        with open(staged, encoding="utf-8") as f:
            staged_content = f.read()
        updated_content, fm_changed = update_publish_status(staged_content)
        if fm_changed:
            with open(staged, "w", encoding="utf-8") as f:
                f.write(updated_content)
            logger.info(f"[{account.name}] frontmatter updated")
        else:
            logger.info(f"[{account.name}] frontmatter: no 未发 tag or already complete")

        # Step 6: archive
        result["step"] = "archive"
        os.makedirs(account.published_full, exist_ok=True)
        dest = os.path.join(account.published_full, os.path.basename(article))
        shutil.move(staged, dest)
        staged = None
        snapshot_path = os.path.join(staged_dir, os.path.basename(article)) + ".snapshot"
        if os.path.exists(snapshot_path):
            os.remove(snapshot_path)
        os.remove(article)
        state_mod.clear(article)
        logger.info(f"[{account.name}] archived: {dest}")

        result["success"] = True
        result["step"] = "done"
        return result

    except Exception as e:
        result["error"] = f"{result['step']}: {e}"
        result["traceback"] = traceback.format_exc()
        logger.exception(f"[{account.name}] pipeline error")
        return result
    finally:
        if staged and os.path.exists(staged):
            try:
                os.remove(staged)
            except OSError:
                pass


def run(cfg, logger):
    """Execute the pipeline for all enabled accounts. Returns a combined result dict."""
    accounts = cfg.enabled_accounts
    logger.info(f"pipeline start: {len(accounts)} account(s) enabled")

    all_results = []
    any_success = False
    errors = []

    for account in accounts:
        result = _process_account(cfg, account, logger)
        all_results.append(result)
        if result["success"]:
            any_success = True
        if result.get("error"):
            errors.append(f"[{account.name}] {result['error']}")

    combined = {
        "success": any_success,
        "accounts": all_results,
        "errors": errors if errors else None,
    }

    # If no accounts at all, report as heartbeat
    if not accounts:
        combined["success"] = True
        combined["message"] = "HEARTBEAT_OK: no enabled accounts"
        logger.info("no enabled accounts")
        return combined

    logger.info(f"pipeline done: {len(all_results)} account(s), {sum(1 for r in all_results if r['success'])} ok")
    return combined
