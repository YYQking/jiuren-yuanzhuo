import json
import tempfile
import threading
import unittest
from threading import Event
from datetime import datetime, timezone
from pathlib import Path

from brainstorm.hotspots import HotspotCache, HotspotFeed, HotspotItem, HotspotProvider, default_hotspot_feeds
from brainstorm.config import DEFAULT_RSS_FEEDS


RSS = '''<?xml version="1.0" encoding="UTF-8"?>
<rss><channel>
  <item><title>社区养老服务迎来新政策</title><description>国内政策正在调整，服务覆盖面扩大</description><link>https://example.test/policy</link><pubDate>Sun, 11 Oct 2026 10:00:00 GMT</pubDate></item>
  <item><title>全球科技公司发布养老助手</title><description>国际科技团队推出新的辅助工具</description><link>https://example.test/tech</link><pubDate>Sun, 11 Oct 2026 09:00:00 GMT</pubDate></item>
  <item><title>城市公共服务预算保持稳定</title><description>社会服务与商业投资持续观察</description><link>https://example.test/general</link><pubDate>Sun, 11 Oct 2026 08:00:00 GMT</pubDate></item>
</channel></rss>'''.encode("utf-8")
RSS_INT = RSS.replace("社区养老服务迎来新政策".encode(), "全球养老服务迎来新趋势".encode()).replace(b"https://example.test/policy", b"https://example.test/global")


class HotspotTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.cache = HotspotCache(Path(self._tmp.name) / "hotspots.json")

    def tearDown(self):
        self._tmp.cleanup()

    def test_fetch_classifies_regions_and_prioritizes_topic_matches(self):
        feeds = [
            HotspotFeed("https://example.test/domestic?q={query}", "国内主题", "domestic", "政策", related=True),
            HotspotFeed("https://example.test/world.xml", "国际社会", "international", "科技"),
        ]
        provider = HotspotProvider(
            feeds,
            transport=lambda url, _timeout: RSS if "domestic" in url else RSS_INT,
            cache=self.cache,
        )

        result = provider.fetch("社区养老")

        self.assertTrue(result.success)
        self.assertFalse(result.used_cache)
        self.assertEqual(result.items[0].title, "社区养老服务迎来新政策")
        self.assertEqual({item.region for item in result.items}, {"domestic", "international"})
        self.assertEqual(result.items[0].category, "政策")
        self.assertTrue(result.items[0].related)
        self.assertEqual(result.items[0].credibility, "未核验")

    def test_filter_and_balanced_selection_do_not_invent_missing_region(self):
        feeds = [HotspotFeed("https://example.test/domestic", "国内", "domestic", "社会")]
        provider = HotspotProvider(feeds, transport=lambda _url, _timeout: RSS, max_items=10, cache=self.cache)

        result = provider.fetch("社区养老")

        self.assertEqual(len(result.for_region("domestic")), 3)
        self.assertEqual(result.for_region("international"), [])
        self.assertEqual({item.region for item in result.display_items("all")}, {"domestic"})

    def test_duplicate_articles_are_merged_with_coverage_count(self):
        feeds = [
            HotspotFeed("https://example.test/a", "国内", "domestic", "社会"),
            HotspotFeed("https://example.test/b", "国内", "domestic", "社会"),
        ]
        provider = HotspotProvider(feeds, transport=lambda _url, _timeout: RSS, cache=self.cache)

        result = provider.fetch("社区养老")

        policy = next(item for item in result.items if item.title == "社区养老服务迎来新政策")
        self.assertEqual(policy.coverage_count, 2)

    def test_failed_refresh_returns_last_successful_cache(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "hotspots.json"
            cache = HotspotCache(path)
            working = HotspotProvider(
                [HotspotFeed("https://example.test/feed", "国内", "domestic", "社会")],
                transport=lambda _url, _timeout: RSS,
                cache=cache,
            )
            first = working.fetch("社区养老")
            self.assertTrue(first.success)
            failed = HotspotProvider(
                [HotspotFeed("https://example.test/feed", "国内", "domestic", "社会")],
                transport=lambda _url, _timeout: (_ for _ in ()).throw(OSError("offline")),
                cache=cache,
            ).fetch("社区养老")

            self.assertFalse(failed.success)
            self.assertTrue(failed.used_cache)
            self.assertEqual(len(failed.items), len(first.items))
            self.assertIsNotNone(failed.last_success_at)
            self.assertIn("缓存", failed.message)

    def test_corrupt_cache_falls_back_to_empty_state(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "hotspots.json"
            path.write_text("not json", encoding="utf-8")
            provider = HotspotProvider(
                [HotspotFeed("https://example.test/feed", "国内", "domestic", "社会")],
                transport=lambda _url, _timeout: (_ for _ in ()).throw(OSError("offline")),
                cache=HotspotCache(path),
            )

            result = provider.fetch("社区养老")

            self.assertEqual(result.items, [])
            self.assertFalse(result.used_cache)
            self.assertIn("失败", result.message)

    def test_default_topic_search_covers_domestic_and_international_sources(self):
        feeds = default_hotspot_feeds(DEFAULT_RSS_FEEDS)
        topic_feeds = [feed for feed in feeds if feed.related]

        self.assertEqual({feed.region for feed in topic_feeds}, {"domestic", "international"})

    def test_custom_topic_feed_does_not_add_another_edition(self):
        custom = (DEFAULT_RSS_FEEDS[0],)
        self.assertEqual([feed.url for feed in default_hotspot_feeds(custom)], list(custom))

    def test_invalid_cached_region_is_discarded(self):
        self.cache.path.write_text(json.dumps({"schema_version": 1, "items": [
            {"title": "损坏的地区分类", "region": "unknown"}
        ]}), encoding="utf-8")
        items, _stamp = self.cache.load(topic="")
        self.assertEqual(items, [])

    def test_overflowing_cached_count_is_discarded_without_exception(self):
        self.cache.path.write_text('{"schema_version":1,"items":[{"title":"bad count","region":"domestic","coverage_count":1e999}]}', encoding="utf-8")
        self.assertEqual(self.cache.load(topic="")[0], [])

    def test_region_interleave_skips_unrecognized_cached_regions(self):
        import subprocess
        import sys
        checked = subprocess.run([sys.executable, "-c",
            "from brainstorm.hotspots import HotspotItem, HotspotFetchResult; "
            "items = HotspotFetchResult([HotspotItem('domestic', region='domestic'), HotspotItem('invalid', region='unknown')]).display_items(); "
            "print([item.title for item in items])"], capture_output=True, text=True, timeout=2)
        self.assertEqual(checked.stdout.strip(), "['domestic']")

    def test_cancelled_slow_cache_commit_cannot_overwrite_newer_topic(self):
        entered = threading.Event()
        release = threading.Event()

        class SlowCache(HotspotCache):
            def save(self, items, saved_at=None, *, topic=""):
                if topic == "old":
                    entered.set()
                    release.wait(3)
                return super().save(items, saved_at, topic=topic)

            def save_if_current(self, items, saved_at, generation, *, topic="", cancel_event=None):
                if topic == "old":
                    entered.set()
                    release.wait(3)
                return super().save_if_current(items, saved_at, generation, topic=topic, cancel_event=cancel_event)

        cache = SlowCache(Path(self._tmp.name) / "slow-cache.json")

        def transport(url, _timeout):
            title = "new topic update" if "new" in url else "old topic update"
            return (f"<rss><channel><item><title>{title}</title>"
                    f"<link>https://example.test/{title.split()[0]}</link></item></channel></rss>").encode()

        provider = HotspotProvider([HotspotFeed("https://example.test/feed?q={query}", "source", "domestic", "社会", related=True)],
                                   transport=transport, cache=cache)
        older = []
        old_thread = threading.Thread(target=lambda: older.append(provider.fetch("old")), daemon=True)
        old_thread.start()
        self.assertTrue(entered.wait(2))
        newer = provider.fetch("new")
        self.assertTrue(newer.success)
        release.set()
        old_thread.join(3)
        self.assertFalse(old_thread.is_alive())
        payload = json.loads(cache.path.read_text(encoding="utf-8"))
        self.assertEqual(payload["topic"], "new")

    def test_item_limit_keeps_domestic_and_international_coverage_balanced(self):
        def rss(prefix):
            entries = "".join(
                f"<item><title>{prefix} report {index}</title><description>current headline</description>"
                f"<link>https://{prefix}.test/{index}</link></item>"
                for index in range(6)
            )
            return f"<rss><channel>{entries}</channel></rss>".encode()

        feeds = [
            HotspotFeed("https://domestic.test/feed", "国内媒体", "domestic", "社会"),
            HotspotFeed("https://international.test/feed", "国际媒体", "international", "科技"),
        ]
        provider = HotspotProvider(
            feeds,
            max_items=6,
            transport=lambda url, _timeout: rss("domestic" if "domestic" in url else "international"),
            cache=self.cache,
        )

        result = provider.fetch("")
        regions = [item.region for item in result.display_items("all")]

        self.assertEqual(regions.count("domestic"), 3)
        self.assertEqual(regions.count("international"), 3)
        self.assertEqual(regions[:4], ["domestic", "international", "domestic", "international"])

    def test_cache_write_error_does_not_discard_live_feed_results(self):
        class BrokenCache:
            def save(self, *_args, **_kwargs):
                raise OSError("cache unavailable")

            def load(self):
                return [], None

        provider = HotspotProvider(
            [HotspotFeed("https://example.test/feed", "国内", "domestic", "社会")],
            transport=lambda _url, _timeout: RSS,
            cache=BrokenCache(),
        )

        result = provider.fetch("社区养老")

        self.assertTrue(result.success)
        self.assertTrue(result.items)
        self.assertIn("缓存", result.message)

    def test_single_item_limit_is_respected_with_two_regions(self):
        provider = HotspotProvider([], max_items=1, cache=self.cache)
        selected = provider._balanced_limit([
            HotspotItem("国内新闻", region="domestic", related=True),
            HotspotItem("国际新闻", region="international", related=True),
            HotspotItem("国际广场", region="international"),
        ])
        self.assertEqual(len(selected), 1)

    def test_default_feeds_include_domestic_general_sections(self):
        feeds = default_hotspot_feeds(DEFAULT_RSS_FEEDS)
        general = [feed for feed in feeds if feed.region == "domestic" and not feed.related]
        self.assertTrue(general)
        self.assertTrue({"社会", "科技", "商业", "政策", "科学"} <= {feed.category for feed in general})

    def test_default_domestic_route_maps_world_feed_to_international(self):
        feeds = default_hotspot_feeds(DEFAULT_RSS_FEEDS)
        world = next(feed for feed in feeds if "chinanews.com.cn/rss/world.xml" in feed.url)
        self.assertEqual(world.region, "international")
        self.assertEqual(world.publisher, "中国新闻网·国际")

    def test_empty_topic_never_marks_articles_related(self):
        provider = HotspotProvider(
            [HotspotFeed("https://example.test/feed?q={query}", "主题检索", "domestic", "社会", related=True)],
            transport=lambda _url, _timeout: RSS,
            cache=self.cache,
        )
        self.assertFalse(any(item.related for item in provider.fetch("").items))

    def test_changed_topic_reclassifies_cached_related_items(self):
        working = HotspotProvider(
            [HotspotFeed("https://example.test/feed", "国内", "domestic", "社会", related=True)],
            transport=lambda _url, _timeout: RSS,
            cache=self.cache,
        )
        working.fetch("社区养老")
        working._transport = lambda _url, _timeout: (_ for _ in ()).throw(OSError("offline"))
        result = working.fetch("火星探测")
        self.assertTrue(result.used_cache)
        self.assertFalse(any(item.related for item in result.items))

    def test_partial_failure_preserves_cached_articles_and_timestamp(self):
        feeds = [
            HotspotFeed("https://example.test/domestic", "国内", "domestic", "政策"),
            HotspotFeed("https://example.test/world", "国际", "international", "科技"),
        ]
        working = HotspotProvider(feeds, transport=lambda url, _timeout: RSS if "domestic" in url else RSS_INT, cache=self.cache)
        first = working.fetch("社区养老")

        def partial(url, _timeout):
            if "world" in url:
                raise OSError("unavailable")
            return RSS

        working._transport = partial
        result = working.fetch("社区养老")
        self.assertTrue(result.used_cache)
        self.assertFalse(result.success)
        self.assertEqual(result.last_success_at, first.last_success_at)
        self.assertTrue(result.for_region("international"))

    def test_pre_cancelled_refresh_never_reads_feeds_or_writes_cache(self):
        reads = []
        provider = HotspotProvider(
            [HotspotFeed("https://example.test/feed", "国内", "domestic", "社会")],
            transport=lambda url, _timeout: reads.append(url) or RSS,
            cache=self.cache,
        )
        cancelled = Event()
        cancelled.set()
        result = provider.fetch("社区养老", cancel_event=cancelled)
        self.assertFalse(result.attempted)
        self.assertEqual(reads, [])
        self.assertFalse(self.cache.path.exists())

    def test_refresh_timeout_stops_queued_workers_after_return(self):
        started = []
        entered = threading.Event()
        release = threading.Event()

        def transport(url, _timeout):
            started.append(url)
            if len(started) >= 5:
                entered.set()
            release.wait(5)
            return RSS

        feeds = [HotspotFeed(f"https://example.test/feed-{index}", "来源", "domestic", "社会")
                 for index in range(6)]
        provider = HotspotProvider(feeds, timeout=0.1, cache=self.cache, transport=transport)

        provider.fetch("")
        self.assertTrue(entered.is_set())
        release.set()
        # Give workers enough time to leave their blocked transport call.
        threading.Event().wait(0.1)
        self.assertEqual(len(started), 5)

    def test_google_source_publisher_and_html_summary_are_plain_text(self):
        rss = RSS.replace(b"<link>https://example.test/policy</link>",
                          b"<source>Actual Publisher</source><link>https://example.test/policy</link>")
        provider = HotspotProvider(
            [HotspotFeed("https://example.test/feed", "聚合器", "domestic", "社会")],
            transport=lambda _url, _timeout: rss,
            cache=self.cache,
        )
        self.assertEqual(provider.fetch("社区养老").items[0].publisher, "Actual Publisher")


if __name__ == "__main__":
    unittest.main()
