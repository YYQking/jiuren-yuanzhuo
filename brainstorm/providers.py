"""Provider selection with explicit network and model-consent gates."""

from __future__ import annotations

import importlib.util
from dataclasses import dataclass

from .config import AppConfig
from .engine import DiscussionProvider, MockDiscussionProvider
from .llm import AnthropicDiscussionProvider, OpenAICompatibleDiscussionProvider
from .news import NewsProvider, OfflineNewsProvider, RssNewsProvider


@dataclass(frozen=True)
class IntegrationStatus:
    requested_mode: str = "offline"
    effective_mode: str = "offline"
    discussion_provider: str = "mock"
    news_provider: str = "offline"
    network_allowed: bool = False
    network_used: bool = False
    fallback_reason: str = ""
    model_name: str = ""
    model_provider: str = ""

    @property
    def mode(self) -> str:
        """Compatibility alias for older UI and callers."""
        return self.effective_mode

    def describe(self) -> str:
        if self.fallback_reason:
            return self.fallback_reason
        if self.discussion_provider in {"anthropic", "openai-compatible"}:
            return f"真实模型 {self.model_name}；观点与来源仍需核验"
        return "离线模拟；未使用网络" if not self.network_used else "RSS 已获取；来源仍未核验"


def _anthropic_available() -> bool:
    """Check availability without importing the optional SDK."""
    return importlib.util.find_spec("anthropic") is not None


def resolve_providers(config: AppConfig | None = None) -> tuple[DiscussionProvider, NewsProvider, IntegrationStatus]:
    """Resolve both providers from one explicit, honest configuration boundary.

    A configured key alone never enables model traffic. Real generation requires
    model mode, network consent, LLM consent, a key, the optional SDK, and a model
    name. RSS selection remains independent from model selection.
    """
    config = config or AppConfig.from_environment()
    requested = config.mode
    # Offline is a hard boundary: neither RSS nor model selection may escape it.
    if requested == "offline":
        status = IntegrationStatus(network_allowed=False)
        return MockDiscussionProvider(), OfflineNewsProvider(), status
    news_enabled = config.allow_network and config.news_enabled and bool(config.news_feed_urls)
    news: NewsProvider = (
        RssNewsProvider(config.news_feed_urls, config.timeout_seconds, config.max_news_items)
        if news_enabled else OfflineNewsProvider()
    )

    model_requested = requested in {"auto", "llm"}
    model_ready = (
        model_requested
        and config.allow_network
        and config.allow_llm
        and bool(config.llm_api_key)
        and bool(config.llm_model)
        and config.llm_provider == "anthropic"
        and _anthropic_available()
    )
    openai_ready = (
        model_requested and config.allow_network and config.allow_llm
        and bool(config.llm_api_key) and bool(config.llm_model)
        and config.llm_provider == "openai"
    )
    if openai_ready:
        provider = OpenAICompatibleDiscussionProvider(
            api_key=config.llm_api_key, model=config.llm_model,
            base_url=config.llm_base_url, timeout=60.0,
            max_retries=config.llm_retries,
        )
        status = IntegrationStatus(
            requested_mode=requested, effective_mode="llm",
            discussion_provider="openai-compatible",
            news_provider="rss" if news_enabled else "offline",
            network_allowed=config.allow_network, model_name=config.llm_model,
            model_provider="openai",
        )
        return provider, news, status
    if model_ready:
        provider: DiscussionProvider = AnthropicDiscussionProvider(
            api_key=config.llm_api_key,
            model=config.llm_model,
            timeout=config.timeout_seconds,
            max_retries=config.llm_retries,
        )
        status = IntegrationStatus(
            requested_mode=requested,
            effective_mode="llm",
            discussion_provider="anthropic",
            news_provider="rss" if news_enabled else "offline",
            network_allowed=config.allow_network,
            model_name=config.llm_model,
            model_provider="anthropic",
        )
        return provider, news, status

    reasons: list[str] = []
    if requested == "llm":
        if not config.allow_network:
            reasons.append("未允许联网")
        if not config.allow_llm:
            reasons.append("未允许真实模型")
        if not config.llm_api_key:
            reasons.append("未配置 API Key")
        if not config.llm_model:
            reasons.append("未配置模型")
        if config.llm_provider == "anthropic" and not _anthropic_available():
            reasons.append("未安装模型 SDK")
        if config.llm_provider == "openai" and not config.llm_base_url:
            reasons.append("未配置接口地址")
        reason = "真实模型不可用（" + "、".join(reasons) + "）；已安全回退到离线模拟"
    elif requested == "auto" and config.allow_llm and config.llm_api_key and config.allow_network:
        reason = "真实模型依赖未就绪；已安全回退到离线模拟"
    elif requested != "offline":
        reason = "未允许真实模型；使用离线模拟"
    else:
        reason = ""
    if not news_enabled and requested != "offline" and config.allow_network:
        reason = reason or "未配置 RSS；使用离线素材"

    status = IntegrationStatus(
        requested_mode=requested,
        effective_mode="offline",
        discussion_provider="mock",
        news_provider="rss" if news_enabled else "offline",
        network_allowed=config.allow_network,
        fallback_reason=reason,
        model_name="",
        model_provider="",
    )
    return MockDiscussionProvider(), news, status
