"""Pipeline configuration: dataclass-based schema with eager validation."""
from __future__ import annotations
import json, os
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class CoverConfig:
    template: str
    width: int = 900
    height: int = 500
    templates_dir: Optional[str] = None
    subtitle: str = "墨 言 书 评"


@dataclass
class WechatConfig:
    theme_css: str
    author: str


@dataclass
class NotifyConfig:
    webhook_url: Optional[str] = None
    osascript: bool = False


@dataclass
class LogConfig:
    dir: Optional[str] = None
    level: str = "INFO"


@dataclass
class ToutiaoConfig:
    auto: bool = False
    user_data_dir: Optional[str] = None
    selectors: dict = field(default_factory=dict)
    headless: bool = True
    screenshot_dir: Optional[str] = None
    timeout_ms: int = 60000


@dataclass
class RetryConfig:
    wechat_attempts: int = 3
    toutiao_attempts: int = 2
    base_delay: float = 2.0
    max_delay: float = 30.0


@dataclass
class BookCoverConfig:
    enabled: bool = True
    sources: list = field(default_factory=lambda: ["douban", "google_books"])
    cache_dir: Optional[str] = None
    timeout: int = 10


@dataclass
class QuoteCardsConfig:
    enabled: bool = True
    template: str = "classic"
    templates_dir: Optional[str] = None
    min_chars: int = 15
    max_per_article: int = 4


@dataclass
class IllustrateConfig:
    book_cover: BookCoverConfig = field(default_factory=BookCoverConfig)
    quote_cards: QuoteCardsConfig = field(default_factory=QuoteCardsConfig)


@dataclass
class PipelineConfig:
    obsidian_vault: str
    queue_dir: str
    published_dir: str
    toutiao_dir: str
    wechat: WechatConfig
    cover: CoverConfig
    wenyan_bin: Optional[str] = None
    notify: NotifyConfig = field(default_factory=NotifyConfig)
    log: LogConfig = field(default_factory=LogConfig)
    toutiao: ToutiaoConfig = field(default_factory=ToutiaoConfig)
    retry: RetryConfig = field(default_factory=RetryConfig)
    illustrate: IllustrateConfig = field(default_factory=IllustrateConfig)

    @property
    def queue_full(self) -> str:
        return os.path.join(self.obsidian_vault, self.queue_dir)

    @property
    def published_full(self) -> str:
        return os.path.join(self.obsidian_vault, self.published_dir)


def _require(d: dict, key: str, ctx: str):
    if key not in d:
        raise ValueError(f"config: missing required '{ctx}.{key}'")
    return d[key]


def load_config(path: str) -> PipelineConfig:
    with open(path, encoding="utf-8") as f:
        raw = json.load(f)

    wechat_raw = _require(raw, "wechat", "config")
    cover_raw = _require(raw, "cover", "config")

    cfg = PipelineConfig(
        obsidian_vault=_require(raw, "obsidian_vault", "config"),
        queue_dir=_require(raw, "queue_dir", "config"),
        published_dir=_require(raw, "published_dir", "config"),
        toutiao_dir=_require(raw, "toutiao_dir", "config"),
        wechat=WechatConfig(
            theme_css=_require(wechat_raw, "theme_css", "wechat"),
            author=_require(wechat_raw, "author", "wechat"),
        ),
        cover=CoverConfig(
            template=_require(cover_raw, "template", "cover"),
            width=cover_raw.get("width", 900),
            height=cover_raw.get("height", 500),
            templates_dir=cover_raw.get("templates_dir"),
            subtitle=cover_raw.get("subtitle", "墨 言 书 评"),
        ),
        wenyan_bin=raw.get("wenyan_bin"),
        notify=NotifyConfig(**raw["notify"]) if raw.get("notify") else NotifyConfig(),
        log=LogConfig(**raw["log"]) if raw.get("log") else LogConfig(),
        toutiao=ToutiaoConfig(**raw["toutiao"]) if raw.get("toutiao") else ToutiaoConfig(),
        retry=RetryConfig(**raw["retry"]) if raw.get("retry") else RetryConfig(),
        illustrate=_load_illustrate(raw.get("illustrate", {})),
    )
    return cfg


def _load_illustrate(raw: dict) -> IllustrateConfig:
    bc = raw.get("book_cover")
    qc = raw.get("quote_cards")
    return IllustrateConfig(
        book_cover=BookCoverConfig(**bc) if bc else BookCoverConfig(),
        quote_cards=QuoteCardsConfig(**qc) if qc else QuoteCardsConfig(),
    )
