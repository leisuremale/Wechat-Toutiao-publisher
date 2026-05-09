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
    args = p.parse_args()

    cfg = load_config(args.config)
    logger = get_logger(cfg.log.dir, cfg.log.level)

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
