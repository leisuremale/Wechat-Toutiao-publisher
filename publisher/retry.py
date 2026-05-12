"""Exponential-backoff retry for callables that return result dicts.

Convention: the wrapped callable returns a dict with at least an `ok` key.
A return of `{"ok": True, ...}` ends the loop; otherwise we consult `retryable`.
Exceptions are caught and converted to `{"ok": False, "error": "..."}` so the
next attempt has a chance to recover (and the caller still sees a clean dict).
"""
import time

# Substrings that mean "do not retry" — config or auth problems retrying won't fix.
FATAL_PATTERNS = (
    "40001",                 # WeChat: invalid credential (token reset needed)
    "40013",                 # WeChat: invalid appid
    "invalid credential",
    "invalid appid",
    "not logged in",         # Toutiao session expired
    "selector not found",
    "editor-not-found",
    "editor selector",
    "config:",               # our load_config() prefix
    "no module named",
    "ENOENT",                # file not found — retrying won't fix a missing file
    "no such file",          # same, human-readable variant
)


def is_likely_transient(text: str) -> bool:
    if not text:
        return True
    text_l = text.lower()
    return not any(p.lower() in text_l for p in FATAL_PATTERNS)


def retry(call, attempts=3, base_delay=2.0, max_delay=30.0,
          retryable=None, logger=None, label="op"):
    """Run `call()` up to `attempts` times with exponential backoff.

    `retryable(result_dict) -> bool` decides whether to keep going. Default:
    retry while `not result.get("ok")`. Override to add policy (e.g. don't
    retry once a non-idempotent step has run).
    """
    if retryable is None:
        retryable = lambda r: not (isinstance(r, dict) and r.get("ok"))

    last = None
    for attempt in range(1, attempts + 1):
        try:
            last = call()
        except Exception as e:
            last = {"ok": False, "error": f"{type(e).__name__}: {e}"}

        if not retryable(last):
            return last

        if attempt < attempts:
            delay = min(base_delay * (2 ** (attempt - 1)), max_delay)
            err = (last.get("error") or last.get("stderr") or "")[:160] if isinstance(last, dict) else str(last)
            if logger:
                logger.warning(
                    f"{label} attempt {attempt}/{attempts} failed: {err}; retry in {delay:.1f}s"
                )
            time.sleep(delay)

    return last
