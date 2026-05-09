"""CLI entry point: python -m publisher [--config path]"""
import argparse, json, os, sys

from .config import load_config
from .log import get_logger
from .notify import notify
from . import pipeline

DEFAULT_CONFIG = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "pipeline-config.json",
)


def main():
    p = argparse.ArgumentParser(description="WeChat + Toutiao publish pipeline")
    p.add_argument("--config", default=DEFAULT_CONFIG)
    p.add_argument("--login-toutiao", action="store_true",
                   help="Open headed browser for first-time Toutiao QR-code login")
    p.add_argument("--check-toutiao", action="store_true",
                   help="Check whether the saved Toutiao session is still valid")
    p.add_argument("--test-cover", metavar="BOOK_NAME",
                   help="Diagnose: try fetching a book cover from each configured source")
    p.add_argument("--test-stockimg", metavar="KEYWORD",
                   help="Diagnose: try fetching a topical photo from configured stock-image sources")
    args = p.parse_args()

    cfg = load_config(args.config)
    logger = get_logger(cfg.log.dir, cfg.log.level)

    if args.test_cover:
        from .illustrate import SOURCES
        results = []
        for src_name in cfg.illustrate.book_cover.sources:
            fn = SOURCES.get(src_name)
            if not fn:
                results.append({"source": src_name, "ok": False,
                                "error": "unknown source"})
                continue
            try:
                url = fn(args.test_cover, timeout=cfg.illustrate.book_cover.timeout)
                results.append({"source": src_name, "ok": bool(url), "url": url})
            except Exception as e:
                results.append({"source": src_name, "ok": False,
                                "error": f"{type(e).__name__}: {e}"})
        report = {"book": args.test_cover, "results": results}
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0 if any(r.get("ok") for r in results) else 1

    if args.test_stockimg:
        from .stockimg import SOURCES as STOCK_SOURCES
        si_cfg = cfg.illustrate.stock_images
        sources = [s for s in (si_cfg.source, si_cfg.fallback)
                   if s and s in STOCK_SOURCES]
        results = []
        for src_name in sources:
            try:
                photos = STOCK_SOURCES[src_name](
                    args.test_stockimg, si_cfg.api_key, 3, si_cfg.timeout,
                )
                results.append({
                    "source": src_name,
                    "ok": bool(photos),
                    "count": len(photos),
                    "first": photos[0] if photos else None,
                })
            except Exception as e:
                results.append({"source": src_name, "ok": False,
                                "error": f"{type(e).__name__}: {e}"})
        report = {"keyword": args.test_stockimg, "results": results}
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0 if any(r.get("ok") for r in results) else 1

    if args.login_toutiao or args.check_toutiao:
        if not cfg.toutiao.user_data_dir:
            print("error: pipeline-config.json must set toutiao.user_data_dir first",
                  file=sys.stderr)
            return 2
        from .toutiao import login_interactive, is_logged_in
        if args.login_toutiao:
            login_interactive(cfg.toutiao.user_data_dir)
            print(json.dumps({"ok": True, "user_data_dir": cfg.toutiao.user_data_dir},
                             ensure_ascii=False))
            return 0
        ok = is_logged_in(cfg.toutiao.user_data_dir)
        print(json.dumps({"logged_in": ok}, ensure_ascii=False))
        return 0 if ok else 1

    result = pipeline.run(cfg, logger)
    notify(cfg.notify, result, logger)

    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["success"] else 1


if __name__ == "__main__":
    sys.exit(main())
