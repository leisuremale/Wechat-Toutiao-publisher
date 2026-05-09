"""Toutiao auto-publish via Playwright persistent context.

Toutiao has no public API. We drive the official editor in a persistent
browser profile. First-time setup requires manual QR-code login via
`python -m publisher --login-toutiao` (opens a headed browser).

The user_data_dir contains LOGIN COOKIES — treat as a secret. Do not
commit it. Recommended location: a dir outside the repo, mode 700.

Selectors default to the most common DOM patterns; mp.toutiao.com changes
periodically, so any selector can be overridden in pipeline-config.json
under `toutiao.selectors`. If selectors fail, the pipeline falls back to
writing the rendered HTML to disk (existing semi-auto behavior).
"""
import os
from contextlib import contextmanager

PUBLISH_URL = "https://mp.toutiao.com/profile_v4/graphic/publish"
HOME_URL = "https://mp.toutiao.com/"

DEFAULT_SELECTORS = {
    "title": "input[placeholder*='标题'], textarea[placeholder*='标题']",
    "editor": "div[contenteditable='true']",
    "cover_button": "text=封面",
    "cover_input": "input[type='file']",
    "save_draft": "text=存草稿",
}


@contextmanager
def _browser(user_data_dir, headless=True, slow_mo=0):
    from playwright.sync_api import sync_playwright  # lazy
    os.makedirs(user_data_dir, exist_ok=True)
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            user_data_dir=user_data_dir,
            headless=headless,
            slow_mo=slow_mo,
            viewport={"width": 1366, "height": 900},
        )
        try:
            yield ctx
        finally:
            ctx.close()


def login_interactive(user_data_dir):
    """Open headed browser, navigate to home, wait for user to scan QR.
    Press Enter in the launching terminal when login is complete."""
    print(f"Opening browser; persistent profile: {user_data_dir}")
    print("Scan QR in the browser to log in, then press Enter here.")
    with _browser(user_data_dir, headless=False, slow_mo=50) as ctx:
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.goto(HOME_URL, wait_until="domcontentloaded")
        try:
            input(">>> Press Enter when logged in to save the session... ")
        except EOFError:
            pass


def is_logged_in(user_data_dir, timeout_ms=10000) -> bool:
    """Quick health check: navigate to home and look for login redirect."""
    try:
        with _browser(user_data_dir, headless=True) as ctx:
            page = ctx.new_page()
            page.set_default_timeout(timeout_ms)
            page.goto(HOME_URL, wait_until="domcontentloaded")
            page.wait_for_timeout(1500)
            return "login" not in page.url.lower() and "passport" not in page.url.lower()
    except Exception:
        return False


def publish_draft(html, title, cover_path, user_data_dir,
                  selectors=None, timeout_ms=60000,
                  screenshot_dir=None, headless=True) -> dict:
    """Save a draft on mp.toutiao.com. Returns {ok, draft_url?, error?, screenshot?, step}.

    Saves a DRAFT (not publish) — final review remains human-in-the-loop.
    """
    sel = {**DEFAULT_SELECTORS, **(selectors or {})}
    result = {
        "ok": False, "draft_url": None, "error": None,
        "screenshot": None, "step": "init", "warnings": [],
    }

    try:
        with _browser(user_data_dir, headless=headless) as ctx:
            page = ctx.new_page()
            page.set_default_timeout(timeout_ms)

            result["step"] = "navigate"
            page.goto(PUBLISH_URL, wait_until="domcontentloaded")
            page.wait_for_timeout(2000)
            url_lower = page.url.lower()
            if "login" in url_lower or "passport" in url_lower:
                result["error"] = "not logged in (run: python -m publisher --login-toutiao)"
                return result

            result["step"] = "fill_title"
            page.locator(sel["title"]).first.fill(title)

            result["step"] = "inject_body"
            page.locator(sel["editor"]).first.click()
            outcome = page.evaluate(
                """([selector, html]) => {
                    const el = document.querySelector(selector);
                    if (!el) return 'editor-not-found';
                    el.focus();
                    try {
                        if (document.execCommand && document.execCommand('insertHTML', false, html)) {
                            return 'execCommand';
                        }
                    } catch (e) {}
                    el.innerHTML = html;
                    el.dispatchEvent(new Event('input', { bubbles: true }));
                    return 'innerHTML';
                }""",
                [sel["editor"], html],
            )
            if outcome == "editor-not-found":
                result["error"] = f"editor selector not found: {sel['editor']}"
                return result

            if cover_path and os.path.exists(cover_path):
                result["step"] = "upload_cover"
                try:
                    page.locator(sel["cover_button"]).first.click(timeout=10000)
                    page.wait_for_timeout(500)
                    page.locator(sel["cover_input"]).first.set_input_files(cover_path)
                    page.wait_for_timeout(2000)
                except Exception as e:
                    result["warnings"].append(f"cover upload skipped: {e}")

            result["step"] = "save_draft"
            page.locator(sel["save_draft"]).first.click()
            page.wait_for_timeout(3000)

            if screenshot_dir:
                os.makedirs(screenshot_dir, exist_ok=True)
                shot = os.path.join(screenshot_dir, "toutiao_draft.png")
                page.screenshot(path=shot, full_page=True)
                result["screenshot"] = shot

            result["draft_url"] = page.url
            result["ok"] = True
            result["step"] = "done"
            return result

    except Exception as e:
        result["error"] = f"toutiao publish [{result['step']}]: {e}"
        return result
