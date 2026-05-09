"""Logging setup: stderr always; rotating file when log dir configured."""
import logging, os, sys
from logging.handlers import TimedRotatingFileHandler


def get_logger(log_dir: str = None, level: str = "INFO") -> logging.Logger:
    logger = logging.getLogger("publisher")
    if logger.handlers:
        return logger

    logger.setLevel(getattr(logging, level.upper(), logging.INFO))
    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")

    stderr = logging.StreamHandler(sys.stderr)
    stderr.setFormatter(fmt)
    logger.addHandler(stderr)

    if log_dir:
        os.makedirs(log_dir, exist_ok=True)
        fh = TimedRotatingFileHandler(
            os.path.join(log_dir, "publish.log"),
            when="midnight", backupCount=14, encoding="utf-8",
        )
        fh.setFormatter(fmt)
        logger.addHandler(fh)

    return logger
