"""Wenyan CLI invocation wrappers."""
import os, re, shutil, subprocess


def resolve_bin(explicit: str = None) -> str:
    """Pick wenyan binary: explicit > ~/.local/bin/wenyan (wrapper) > PATH."""
    if explicit:
        return os.path.expanduser(explicit)
    wrapper = os.path.expanduser("~/.local/bin/wenyan")
    if os.path.exists(wrapper):
        return wrapper
    return shutil.which("wenyan") or wrapper


def publish_wechat(bin_path, article, theme_css, timeout=120) -> dict:
    r = subprocess.run(
        [bin_path, "publish", "-f", article, "-c", theme_css],
        capture_output=True, text=True, timeout=timeout, check=False,
    )
    out = r.stdout.strip()
    media_id = None
    if r.returncode == 0:
        m = re.search(r"Media ID:\s*(\S+)", out)
        media_id = m.group(1) if m else (out or None)
    return {
        "ok": r.returncode == 0,
        "stdout": out,
        "stderr": r.stderr.strip(),
        "media_id": media_id,
    }


def render_toutiao(bin_path, article, theme_css, timeout=60) -> dict:
    r = subprocess.run(
        [bin_path, "render", "-f", article, "-c", theme_css],
        capture_output=True, text=True, timeout=timeout, check=False,
    )
    return {
        "ok": r.returncode == 0,
        "stdout": r.stdout.strip(),
        "stderr": r.stderr.strip(),
    }
