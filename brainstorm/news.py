"""Opt-in, status-aware RSS seam; the default provider never opens a socket."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Protocol
from urllib.parse import quote, urljoin
from urllib.request import Request, urlopen
import xml.etree.ElementTree as ET
import re

from .models import TrendSource


@dataclass(frozen=True)
class NewsFetchResult:
    sources: list[TrendSource]
    attempted: bool = False
    success: bool = True
    message: str = "未使用网络"
    matched: bool = False
    partial_failure: bool = False


class NewsProvider(Protocol):
    def fetch(self, topic: str) -> list[TrendSource]:
        ...

    def fetch_with_status(self, topic: str) -> NewsFetchResult:
        ...


class OfflineNewsProvider:
    def fetch(self, topic: str) -> list[TrendSource]:
        return []

    def fetch_with_status(self, topic: str) -> NewsFetchResult:
        return NewsFetchResult([], message="未允许联网；未获取 RSS")


class RssNewsProvider:
    def __init__(
        self,
        urls: Iterable[str],
        timeout: float = 10.0,
        max_items: int = 5,
        transport: Callable[[str, float], bytes] | None = None,
    ) -> None:
        self.urls = tuple(urls)
        self.timeout = timeout
        self.max_items = max(1, max_items)
        self._transport = transport or self._read_url

    @staticmethod
    def _read_url(url: str, timeout: float) -> bytes:
        request = Request(url, headers={"User-Agent": "NineRoundtable/1.0"})
        with urlopen(request, timeout=timeout) as response:
            return response.read(512 * 1024)

    def fetch(self, topic: str) -> list[TrendSource]:
        return self.fetch_with_status(topic).sources

    def fetch_with_status(self, topic: str) -> NewsFetchResult:
        if not self.urls:
            return NewsFetchResult([], message="未配置 RSS feed", matched=False)
        results: list[TrendSource] = []
        seen: set[tuple[str, str]] = set()
        failures: list[str] = []
        expanded_urls = [url.replace("{query}", quote(topic.strip(), safe="")) for url in self.urls]
        with ThreadPoolExecutor(max_workers=min(5, len(expanded_urls))) as pool:
            fetched = {
                pool.submit(self._fetch_feed, url, topic): url
                for url in expanded_urls
            }
            feed_results = [future.result() for future in as_completed(fetched)]
        for url, entries, failure in feed_results:
            if failure:
                failures.append(failure)
                continue
            for title, note, link, published_at in entries:
                key = (title.casefold(), link.casefold())
                if key in seen:
                    continue
                seen.add(key)
                results.append(TrendSource(title=title[:240], url=link, note=note[:1000], credibility="未核验", source_type="rss", fetched_at=datetime.now(timezone.utc), published_at=published_at))
        results.sort(key=self._sort_key, reverse=True)
        results = results[: self.max_items]
        if results and failures:
            return NewsFetchResult(results, True, False, f"RSS 已获取；部分 feed 失败（{len(failures)}）；来源仍未核验", True, True)
        if results:
            return NewsFetchResult(results, True, True, "RSS 已获取；来源仍未核验", True, False)
        if failures:
            return NewsFetchResult([], True, False, f"RSS 获取失败；{len(failures)} 个 feed 失败", False, False)
        return NewsFetchResult([], True, True, "RSS 未找到匹配素材", False, False)

    def _fetch_feed(self, url: str, topic: str) -> tuple[str, list[tuple[str, str, str, datetime | None]], str]:
        if not url.lower().startswith("https://"):
            return url, [], f"拒绝非 HTTPS feed: {url}"
        try:
            root = ET.fromstring(self._transport(url, self.timeout))
        except (OSError, ET.ParseError, ValueError, TimeoutError) as exc:
            return url, [], f"{url}: {type(exc).__name__}"
        entries: list[tuple[str, str, str, datetime | None]] = []
        for item in root.iter():
            if item.tag.rsplit("}", 1)[-1].lower() not in {"item", "entry"}:
                continue
            fields = {child.tag.rsplit("}", 1)[-1].lower(): (child.text or "").strip() for child in item}
            title = fields.get("title", "")
            note = fields.get("description") or fields.get("summary", "")
            if not title or not self._topic_matches(topic, title, note):
                continue
            link_candidates = []
            for child in item:
                if child.tag.rsplit("}", 1)[-1].lower() == "link":
                    candidate = (child.attrib.get("href") or child.text or "").strip()
                    if candidate:
                        link_candidates.append((child.attrib.get("rel", "alternate").lower(), candidate))
            link = next((candidate for rel, candidate in link_candidates if rel == "alternate"), "")
            link = link or (link_candidates[0][1] if link_candidates else fields.get("link", ""))
            link = urljoin(url, link) if link else ""
            published = fields.get("published") or fields.get("updated") or fields.get("pubdate") or fields.get("date")
            entries.append((title, note, link, self._parse_datetime(published)))
        return url, entries, ""

    @classmethod
    def _topic_matches(cls, topic: str, title: str, note: str) -> bool:
        """Match a topic against an RSS item without requiring one exact phrase.

        Chinese topics are commonly written without spaces while an article may
        put the relevant terms in its title and summary separately.  We keep a
        conservative two-character term matcher for that case, while retaining
        exact and word-token matching for English or mixed topics.
        """
        normalized_topic = re.sub(r"\s+", "", topic or "").casefold()
        haystack = re.sub(r"\s+", "", f"{title}\n{note}").casefold()
        if not normalized_topic:
            return True
        if normalized_topic in haystack:
            return True
        terms = cls._topic_terms(topic)
        if not terms:
            return False
        hits = sum(1 for term in terms if term.casefold() in haystack)
        if len(terms) == 1:
            return hits == 1
        # Require at least two independent Chinese terms, but cap the burden
        # for long natural-language prompts where an article can be relevant
        # without repeating every word from the prompt.
        required = min(3, max(2, (len(terms) + 2) // 3))
        return hits >= required

    @staticmethod
    def _topic_terms(topic: str) -> list[str]:
        terms: list[str] = []
        for token in re.findall(r"[A-Za-z0-9][A-Za-z0-9_-]*|[\u4e00-\u9fff]+", topic or ""):
            if re.fullmatch(r"[\u4e00-\u9fff]+", token):
                if len(token) <= 2:
                    terms.append(token)
                else:
                    # Pairing preserves useful terms such as 社区、养老、服务
                    # while avoiding a dependency on a Chinese segmenter.
                    terms.extend(token[index:index + 2] for index in range(0, len(token) - 1, 2))
                    if len(token) % 2:
                        terms.append(token[-2:])
            else:
                terms.append(token)
        return list(dict.fromkeys(term for term in terms if term))

    @staticmethod
    def _sort_key(item: TrendSource) -> tuple[int, datetime]:
        published = item.published_at
        if published is None:
            return (0, datetime.min.replace(tzinfo=timezone.utc))
        if published.tzinfo is None:
            published = published.replace(tzinfo=timezone.utc)
        return (1, published.astimezone(timezone.utc))

    @staticmethod
    def _parse_datetime(value: str) -> datetime | None:
        if not value:
            return None
        try:
            return parsedate_to_datetime(value)
        except (TypeError, ValueError, OverflowError):
            try:
                parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            except (TypeError, ValueError, OverflowError):
                return None
            return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=timezone.utc)
