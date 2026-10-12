"""Opt-in integration configuration with a safe offline default."""
from __future__ import annotations
import os
from dataclasses import dataclass, field

_TRUE = {"1", "true", "yes", "on"}

# Broad, public HTTPS feeds. They are only used when the user enables the
# network checkbox for a discussion; RSS material remains explicitly unverified.
DEFAULT_RSS_FEEDS = (
    "https://news.google.com/rss/search?q={query}&hl=zh-CN&gl=CN&ceid=CN:zh-Hans",
    "https://www.chinanews.com.cn/rss/scroll-news.xml",
    "https://www.chinanews.com.cn/rss/china.xml",
    "https://www.chinanews.com.cn/rss/world.xml",
    "https://www.chinanews.com.cn/rss/finance.xml",
    "https://www.chinanews.com.cn/rss/it.xml",
    "https://www.chinanews.com.cn/rss/society.xml",
)

def _bool(name: str, default: bool = False) -> bool:
    return os.getenv(name, "1" if default else "0").strip().lower() in _TRUE

@dataclass(frozen=True)
class AppConfig:
    mode: str = "auto"
    allow_network: bool = True
    news_enabled: bool = True
    news_feed_urls: tuple[str, ...] = DEFAULT_RSS_FEEDS
    llm_model: str = "claude-opus-5-5"
    llm_provider: str = "anthropic"
    llm_base_url: str = "https://api.openai.com/v1"
    llm_api_key: str = field(default="", repr=False)
    allow_llm: bool = False
    llm_retries: int = 1
    timeout_seconds: float = 6.0
    max_news_items: int = 5

    @classmethod
    def from_environment(cls) -> "AppConfig":
        mode = os.getenv("BRAINSTORM_MODE", "auto").strip().lower()
        if mode not in {"offline", "auto", "llm"}:
            mode = "offline"
        raw_feeds = os.getenv("BRAINSTORM_RSS_FEEDS")
        feeds = tuple(x.strip() for x in raw_feeds.split(",") if x.strip()) if raw_feeds is not None else DEFAULT_RSS_FEEDS
        try:
            timeout = max(3.0, min(float(os.getenv("BRAINSTORM_TIMEOUT", "6")), 30.0))
        except (TypeError, ValueError):
            timeout = 6.0
        try:
            max_items = max(1, min(int(os.getenv("BRAINSTORM_MAX_NEWS", "5")), 20))
        except (TypeError, ValueError):
            max_items = 5
        try:
            retries = max(0, min(int(os.getenv("BRAINSTORM_LLM_RETRIES", "1")), 3))
        except (TypeError, ValueError):
            retries = 1
        key = os.getenv("BRAINSTORM_LLM_API_KEY") or os.getenv("ANTHROPIC_API_KEY") or ""
        network = _bool("BRAINSTORM_ALLOW_NETWORK", default=True)
        model = os.getenv("BRAINSTORM_LLM_MODEL", "claude-opus-5-5").strip() or "claude-opus-5-5"
        provider = os.getenv("BRAINSTORM_LLM_PROVIDER", "anthropic").strip().lower() or "anthropic"
        if provider not in {"anthropic", "openai"}:
            provider = "anthropic"
        if provider == 'openai':
            key = os.getenv('BRAINSTORM_LLM_API_KEY') or os.getenv('OPENAI_API_KEY') or ''
            model = os.getenv('BRAINSTORM_LLM_MODEL', '').strip()
        base_url = os.getenv("BRAINSTORM_LLM_BASE_URL", "https://api.openai.com/v1").strip().rstrip("/")
        if not base_url:
            base_url = "https://api.openai.com/v1"
        return cls(
            mode=mode,
            allow_network=network,
            news_enabled=network and bool(feeds),
            news_feed_urls=feeds,
            llm_model=model,
            llm_provider=provider,
            llm_base_url=base_url,
            llm_api_key=key,
            allow_llm=_bool("BRAINSTORM_ALLOW_LLM"),
            llm_retries=retries,
            timeout_seconds=timeout,
            max_news_items=max_items,
        )
