"""Best-effort failure/success notifications. Never raises."""
import json, subprocess, urllib.request


def _osa_escape(s: str) -> str:
    return s.replace("\\", "\\\\").replace('"', '\\"')


def notify(cfg, payload: dict, logger):
    """Fire configured notification channels. Errors are logged, not raised."""
    try:
        if cfg.webhook_url:
            data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            req = urllib.request.Request(
                cfg.webhook_url, data=data,
                headers={"Content-Type": "application/json"},
            )
            urllib.request.urlopen(req, timeout=10).close()

        if cfg.osascript and not payload.get("success"):
            title = _osa_escape(payload.get("title") or payload.get("step") or "publish")
            err = _osa_escape(str(payload.get("error", "failed")))
            subprocess.run(
                ["osascript", "-e",
                 f'display notification "{err}" with title "Publish failed: {title}"'],
                timeout=5, check=False,
            )
    except Exception as e:
        logger.warning(f"notify failed: {e}")
