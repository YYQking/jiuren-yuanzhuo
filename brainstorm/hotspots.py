"""Social hotspot feeds with honest provenance and a separate local cache."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from html import unescape
import json
import math
import os
from pathlib import Path
from queue import Empty, Queue
import re
import tempfile
from threading import Event, Lock, Thread
import time
from typing import Callable, Iterable
from urllib.parse import quote, urljoin
from urllib.request import Request, urlopen
import xml.etree.ElementTree as ET

from .config import DEFAULT_RSS_FEEDS
from .news import RssNewsProvider


@dataclass(frozen=True)
class HotspotFeed:
    url: str
    publisher: str
    region: str
    category: str
    related: bool = False



@dataclass(frozen=True)
class HotspotItem:
    title: str
    url: str = ""
    summary: str = ""
    publisher: str = ""
    region: str = "international"
    category: str = "社会"
    published_at: datetime | None = None
    fetched_at: datetime | None = None
    credibility: str = "未核验"
    rank: int | None = None
    coverage_count: int = 1
    related: bool = False
    cached: bool = False
    time_note: str = ""


@dataclass(frozen=True)
class HotspotFetchResult:
    items: list[HotspotItem]
    attempted: bool = False
    success: bool = True
    used_cache: bool = False
    message: str = "未使用网络"
    fetched_at: datetime | None = None
    last_success_at: datetime | None = None

    def for_region(self, region: str) -> list[HotspotItem]:
        if region not in {"domestic", "international"}:
            return list(self.items)
        return [item for item in self.items if item.region == region]

    def display_items(self, region: str = "all") -> list[HotspotItem]:
        """Keep related stories prominent, then interleave regions when possible."""
        items = self.for_region(region)
        related = [item for item in items if item.related]
        general = [item for item in items if not item.related]
        if region != "all":
            return related + general
        return self._interleave(related) + self._interleave(general)

    @staticmethod
    def _interleave(items: list[HotspotItem]) -> list[HotspotItem]:
        buckets: dict[str, list[HotspotItem]] = defaultdict(list)
        for item in items:
            if item.region in {"domestic", "international"}:
                buckets[item.region].append(item)
        regions = [key for key in ("domestic", "international") if key in buckets]
        result: list[HotspotItem] = []
        while any(buckets.values()):
            for region in regions:
                if buckets[region]:
                    result.append(buckets[region].pop(0))
        return result


class HotspotCache:
    """Atomic JSON cache kept apart from discussion history files."""

    def __init__(self, path: Path | None = None) -> None:
        self._commit_lock = Lock()
        self._generation = 0
        if path is not None:
            self.path = path
        else:
            try:
                base = Path.home()
            except RuntimeError:
                base = Path(os.environ.get("LOCALAPPDATA") or os.environ.get("USERPROFILE") or Path.cwd())
            self.path = base / "九人圆桌" / "hotspots.json"

    def begin_refresh(self) -> int:
        with self._commit_lock:
            self._generation += 1
            return self._generation

    def save(self, items: Iterable[HotspotItem], saved_at: datetime | None = None, *, topic: str = "") -> datetime | None:
        return self.save_if_current(items, saved_at, self.begin_refresh(), topic=topic)

    def save_if_current(self, items: Iterable[HotspotItem], saved_at: datetime | None, generation: int,
                        *, topic: str = "", cancel_event: Event | None = None) -> datetime | None:
        stamp = saved_at or datetime.now(timezone.utc)
        payload = {
            "schema_version": 1,
            "saved_at": stamp.isoformat(),
            "topic": topic,
            "items": [_item_to_dict(item) for item in items],
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary = tempfile.mkstemp(dir=self.path.parent, prefix="hotspots-", suffix=".tmp")
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, ensure_ascii=False, indent=2)
                handle.flush()
                os.fsync(handle.fileno())
            with self._commit_lock:
                if generation != self._generation or (cancel_event is not None and cancel_event.is_set()):
                    return None
                os.replace(temporary, self.path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
        return stamp

    def load(self, *, topic: str | None = None) -> tuple[list[HotspotItem], datetime | None]:
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(payload, dict) or payload.get("schema_version") != 1 or not isinstance(payload.get("items"), list):
                return [], None
            saved_at = _parse_datetime(payload.get("saved_at"))
            items = [_item_from_dict(item) for item in payload["items"]
                     if isinstance(item, dict) and item.get("region") in {"domestic", "international"}]
            if topic is not None:
                same_topic = bool(topic) and topic == payload.get("topic")
                items = [replace(item, related=(item.related and same_topic) or _topic_matches(topic, item.title, item.summary), cached=True) for item in items]
            return items, saved_at
        except (OSError, ValueError, TypeError, OverflowError, json.JSONDecodeError, KeyError):
            return [], None


class HotspotProvider:
    def __init__(
        self,
        feeds: Iterable[HotspotFeed],
        timeout: float = 10.0,
        max_items: int = 24,
        transport: Callable[[str, float], bytes] | None = None,
        cache: HotspotCache | None = None,
    ) -> None:
        self.feeds = tuple(feeds)
        self.timeout = max(0.1, min(timeout, 60.0))
        self.max_items = max(1, max_items)
        self._transport = transport or self._read_url
        self.cache = cache or HotspotCache()

    @staticmethod
    def _read_url(url: str, timeout: float) -> bytes:
        request = Request(url, headers={"User-Agent": "NineRoundtable/1.0"})
        with urlopen(request, timeout=timeout) as response:
            return response.read(768 * 1024)

    def cached(self, topic: str, message: str = "已加载缓存") -> HotspotFetchResult:
        items, stamp = self.cache.load(topic=topic)
        return HotspotFetchResult(items, used_cache=bool(items), message=message, last_success_at=stamp)

    def fetch(self, topic: str, *, cancel_event: Event | None = None) -> HotspotFetchResult:
        topic = topic.strip()
        cancelled = cancel_event or Event()
        if cancelled.is_set():
            return HotspotFetchResult([], success=False, message="刷新已取消")
        if not self.feeds:
            return HotspotFetchResult([], message="未配置热点 feed")
        generation = self.cache.begin_refresh() if isinstance(self.cache, HotspotCache) else None
        fetched_at = datetime.now(timezone.utc)
        items: list[HotspotItem] = []
        failures: list[str] = []
        successes = 0
        active_feeds = [feed for feed in self.feeds if topic or not feed.related]
        for entries, failure in self._fetch_all(active_feeds, topic, fetched_at, cancelled):
            if failure:
                failures.append(failure)
                continue
            successes += 1
            items.extend(entries)
        if cancelled.is_set():
            return HotspotFetchResult([], attempted=bool(active_feeds), success=False, message="刷新已取消")
        items = self._dedupe(items)
        items.sort(key=self._sort_key, reverse=True)
        if failures:
            cached, last_success = self.cache.load(topic=topic)
            if cached:
                # Keep freshly fetched items, but never lose saved items just
                # because another source failed during this refresh.
                fresh_urls = {item.url for item in items if item.url}
                fresh_titles = {item.title.casefold() for item in items}
                items += [item for item in cached if item.url not in fresh_urls and item.title.casefold() not in fresh_titles]
                items.sort(key=self._sort_key, reverse=True)
                return HotspotFetchResult(self._balanced_limit(items), True, False, True,
                    "部分来源刷新失败，保留上次成功结果（缓存）" if successes else "刷新失败，已保留上次成功结果（缓存）",
                    fetched_at, last_success)
        if not items and successes:
            cached, last_success = self.cache.load(topic=topic)
            if cached:
                return HotspotFetchResult(cached, True, True, True,
                    "本次来源没有新结果，保留上次成功内容（缓存）", fetched_at, last_success)
        items = self._balanced_limit(items)
        if successes and not failures:
            try:
                if generation is not None:
                    saved_at = self.cache.save_if_current(items, fetched_at, generation,
                        topic=topic, cancel_event=cancelled)
                    if saved_at is None:
                        return HotspotFetchResult([], attempted=True, success=False, message="刷新已取消或由新请求替代")
                else:
                    saved_at = self.cache.save(items, fetched_at, topic=topic)
            except (OSError, ValueError, TypeError):
                saved_at = None
                cache_warning = "；本次结果未能写入缓存"
            else:
                cache_warning = ""
            message = "热点已更新；内容来自公开 RSS，均未核验"
            message += cache_warning
            if not items:
                message = "公开来源已响应，但暂时没有可显示的新闻" + cache_warning
            return HotspotFetchResult(items, bool(active_feeds), True, False, message, fetched_at, saved_at)
        if items:
            return HotspotFetchResult(items, True, False, False,
                f"已获取部分新闻；{len(failures)} 个来源失败，未核验", fetched_at)
        return HotspotFetchResult([], True, False, False, f"热点刷新失败；{len(failures)} 个来源不可用", fetched_at)

    def _fetch_all(self, feeds: list[HotspotFeed], topic: str, stamp: datetime, cancelled: Event):
        """Bound the refresh and allow cancellation without waiting on sockets."""
        jobs = Queue()
        results = Queue()
        worker_stop = Event()
        for index, feed in enumerate(feeds):
            jobs.put((index, feed))

        def run_feed_worker():
            while not cancelled.is_set() and not worker_stop.is_set():
                try:
                    index, feed = jobs.get_nowait()
                except Empty:
                    return
                query = f"{topic} when:2d" if topic else ""
                url = feed.url.replace("{query}", quote(query, safe=""))
                try:
                    entries, failure = self._fetch_feed(url, feed, topic, stamp)
                except Exception as exc:
                    entries, failure = [], type(exc).__name__
                results.put((index, entries, failure))

        for _ in range(min(5, len(feeds))):
            Thread(target=run_feed_worker, daemon=True).start()
        # Bound a refresh to one connection window. Working sources are
        # collected as they finish; slow sources fall back to the cache.
        deadline = time.monotonic() + self.timeout + 1
        collected = {}
        while len(collected) < len(feeds) and not cancelled.is_set():
            if time.monotonic() >= deadline:
                break
            try:
                index, entries, failure = results.get(timeout=0.1)
                collected[index] = (entries, failure)
            except Empty:
                continue
        # Stop workers from claiming queued feeds after the bounded refresh
        # has returned. In-flight transports may still finish on their own,
        # but no additional network request should begin.
        worker_stop.set()
        return [collected.get(index, ([], "TimeoutError")) for index in range(len(feeds))]

    def _balanced_limit(self, items: list[HotspotItem]) -> list[HotspotItem]:
        groups = {region: [item for item in items if item.region == region] for region in ("domestic", "international")}
        quotas = {"domestic": (self.max_items + 1) // 2, "international": self.max_items // 2}
        chosen: list[HotspotItem] = []
        for region, group in groups.items():
            quota = quotas[region]
            if quota <= 0:
                continue
            related = [item for item in group if item.related]
            general = [item for item in group if not item.related]
            reserved = min(len(related), max(1, quota // 3)) if general else quota
            selected = related[:reserved] + general[:max(0, quota - reserved)]
            selected += [item for item in group if item not in selected][:max(0, quota - len(selected))]
            chosen.extend(selected)
        chosen += [item for item in items if item not in chosen][:max(0, self.max_items - len(chosen))]
        chosen.sort(key=self._sort_key, reverse=True)
        return chosen[:self.max_items]

    def _fetch_feed(
        self, url: str, feed: HotspotFeed, topic: str, fetched_at: datetime
    ) -> tuple[list[HotspotItem], str]:
        if not url.lower().startswith("https://"):
            return [], f"拒绝非 HTTPS feed: {url}"
        try:
            root = ET.fromstring(self._transport(url, self.timeout))
        except (OSError, ET.ParseError, ValueError, TimeoutError) as exc:
            return [], f"{url}: {type(exc).__name__}"
        items: list[HotspotItem] = []
        for entry in root.iter():
            if entry.tag.rsplit("}", 1)[-1].lower() not in {"item", "entry"}:
                continue
            fields = {
                child.tag.rsplit("}", 1)[-1].lower(): "".join(child.itertext()).strip()
                for child in entry
            }
            title = _clean_text(fields.get("title", ""))
            if not title:
                continue
            note = _clean_text(fields.get("description") or fields.get("summary", ""))
            link_candidates = []
            for child in entry:
                if child.tag.rsplit("}", 1)[-1].lower() == "link":
                    candidate = (child.attrib.get("href") or child.text or "").strip()
                    if candidate:
                        link_candidates.append((child.attrib.get("rel", "alternate").lower(), candidate))
            link = next((candidate for rel, candidate in link_candidates if rel == "alternate"), "")
            link = link or (link_candidates[0][1] if link_candidates else fields.get("link", ""))
            link = urljoin(url, link) if link else ""
            related = bool(topic) and (feed.related or _topic_matches(topic, title, note))
            items.append(HotspotItem(
                title=title[:240],
                url=link,
                summary=note[:1000],
                publisher=_clean_text(fields.get("source") or fields.get("author") or feed.publisher),
                region=feed.region if feed.region in {"domestic", "international"} else "international",
                category=feed.category or "社会",
                published_at=_parse_datetime(fields.get("published") or fields.get("updated") or fields.get("pubdate") or fields.get("date")),
                fetched_at=fetched_at,
                related=related,
            ))
        return items, ""

    @staticmethod
    def _dedupe(items: list[HotspotItem]) -> list[HotspotItem]:
        merged: dict[tuple[str, str], HotspotItem] = {}
        for item in items:
            key = (item.url.casefold(), item.title.casefold())
            existing = merged.get(key)
            if existing is None:
                merged[key] = item
            else:
                merged[key] = replace(
                    existing,
                    coverage_count=existing.coverage_count + 1,
                    related=existing.related or item.related,
                    summary=existing.summary or item.summary,
                    publisher=existing.publisher or item.publisher,
                )
        return list(merged.values())

    @staticmethod
    def _sort_key(item: HotspotItem) -> tuple[int, datetime, int]:
        published = item.published_at or datetime.min.replace(tzinfo=timezone.utc)
        if published.tzinfo is None:
            published = published.replace(tzinfo=timezone.utc)
        return (1 if item.related else 0, published.astimezone(timezone.utc), item.coverage_count)


def _item_to_dict(item: HotspotItem) -> dict[str, object]:
    data = asdict(item)
    for key in ("published_at", "fetched_at"):
        value = data.get(key)
        if isinstance(value, datetime):
            data[key] = value.isoformat()
    return data


def _item_from_dict(data: dict[str, object]) -> HotspotItem:
    values = dict(data)
    values["published_at"] = _parse_datetime(values.get("published_at"))
    values["fetched_at"] = _parse_datetime(values.get("fetched_at"))
    return HotspotItem(
        title=str(values.get("title", "")),
        url=str(values.get("url", "")),
        summary=str(values.get("summary", "")),
        publisher=str(values.get("publisher", "")),
        region=str(values.get("region", "international")),
        category=str(values.get("category", "社会")),
        published_at=values["published_at"],
        fetched_at=values["fetched_at"],
        credibility=str(values.get("credibility", "未核验")),
        rank=int(values["rank"]) if values.get("rank") is not None else None,
        coverage_count=max(1, int(values.get("coverage_count", 1))),
        related=bool(values.get("related", False)),
        cached=bool(values.get("cached", False)),
        time_note=str(values.get("time_note", "")),
    )


def _parse_datetime(value: object) -> datetime | None:
    if not value:
        return None
    text = str(value)
    try:
        parsed = parsedate_to_datetime(text)
    except (TypeError, ValueError, OverflowError):
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except (TypeError, ValueError, OverflowError):
            return None
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=timezone.utc)


def _clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", unescape(value or ""))).strip()


def _topic_matches(topic: str, title: str, note: str) -> bool:
    return bool(topic.strip()) and RssNewsProvider._topic_matches(topic, title, note)


def default_hotspot_feeds(urls: Iterable[str]) -> list[HotspotFeed]:
    """Map the configured public feeds to the hotspot page's honest buckets."""
    urls = tuple(urls)
    feeds: list[HotspotFeed] = []
    for url in urls:
        lowered = url.casefold()
        if "news.google.com" in lowered:
            region = "domestic" if "ceid=cn:" in lowered else "international"
            publisher = "Google News"
        elif "zh-cn" in lowered or "ceid=cn" in lowered:
            region = "domestic"
            publisher = "Google News"
        elif "chinanews.com.cn" in lowered and "world" in lowered:
            region = "international"
            publisher = "中国新闻网·国际"
        elif "chinanews.com.cn" in lowered:
            region = "domestic"
            publisher = "中国新闻网"
        else:
            region = "international"
            publisher = "公开 RSS"
        category = "科技" if "tech" in lowered else "商业" if "business" in lowered else "科学" if "science" in lowered else "社会"
        related = "{query}" in url
        feeds.append(HotspotFeed(url, publisher, region, category, related=related))
        if urls == DEFAULT_RSS_FEEDS and related and region == "domestic" and "news.google.com" in lowered:
            international_url = url.replace("hl=zh-CN", "hl=en-US").replace("gl=CN", "gl=US").replace("ceid=CN:zh-Hans", "ceid=US:en")
            feeds.append(HotspotFeed(international_url, "Google News International", "international", category, related=True))
    if urls == DEFAULT_RSS_FEEDS:
        locale = "&hl=zh-CN&gl=CN&ceid=CN:zh-Hans"
        feeds.append(HotspotFeed("https://news.google.com/rss?hl=zh-CN&gl=CN&ceid=CN:zh-Hans", "Google News 国内栏目", "domestic", "社会"))
        for category, query in (("科技", "科技"), ("商业", "经济 商业"), ("政策", "政策"), ("科学", "科学 研究")):
            feeds.append(HotspotFeed("https://news.google.com/rss/search?q=" + quote(query + " when:2d") + locale,
                "Google News 国内栏目", "domestic", category))
    return feeds
