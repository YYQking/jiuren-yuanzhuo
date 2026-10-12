import json
import random
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from brainstorm.hotspots import HotspotCache
from brainstorm.model_hotspots import ModelHotspotProvider, build_hotspot_prompt


def payload(items):
    return json.dumps({"items": items}, ensure_ascii=False)


def entry(title, region="domestic", summary="一句话摘要", category="社会", related=False, url="",
          when="2026年10月", source="新华社"):
    return {"title": title, "region": region, "summary": summary,
            "category": category, "related": related, "url": url,
            "when": when, "source": source}


class ModelHotspotProviderTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.cache = HotspotCache(Path(self._tmp.name) / "hotspots.json")

    def tearDown(self):
        self._tmp.cleanup()

    def provider(self, reply, **kwargs):
        calls = []

        def complete(prompt, cancel_event=None):
            calls.append(prompt)
            if isinstance(reply, Exception):
                raise reply
            return reply

        provider = ModelHotspotProvider(complete, cache=self.cache,
                                        rng=random.Random(0), **kwargs)
        return provider, calls

    def test_items_are_labelled_as_unverified_model_output(self):
        provider, _ = self.provider(payload([entry("某地暴雨预警"), entry("海外选举结果", region="international")]))
        result = provider.fetch("")
        self.assertTrue(result.success)
        self.assertEqual(len(result.items), 2)
        for item in result.items:
            self.assertEqual(item.publisher, "模型生成")
            self.assertIn("未核验", item.credibility)
        self.assertIn("未核验", result.message)

    def test_model_authored_urls_are_never_kept(self):
        provider, _ = self.provider(payload([entry("编造的新闻", url="https://example.invalid/fake")]))
        result = provider.fetch("")
        self.assertEqual(result.items[0].url, "")

    def test_selection_is_capped_by_max_items(self):
        items = [entry(f"热点{index}") for index in range(10)]
        provider, _ = self.provider(payload(items), max_items=4)
        result = provider.fetch("")
        self.assertEqual(len(result.items), 4)

    def test_empty_topic_never_marks_items_related(self):
        provider, _ = self.provider(payload([entry("某热点", related=True)]))
        result = provider.fetch("")
        self.assertFalse(result.items[0].related)

    def test_topic_reaches_the_model_and_can_mark_related_items(self):
        provider, calls = self.provider(payload([entry("社区养老新政", related=True)]))
        result = provider.fetch("社区养老")
        self.assertIn("社区养老", calls[0])
        self.assertTrue(result.items[0].related)

    def test_unknown_region_falls_back_to_international(self):
        provider, _ = self.provider(payload([entry("来源不明", region="mars")]))
        self.assertEqual(provider.fetch("").items[0].region, "international")

    def test_entries_without_a_title_are_skipped(self):
        provider, _ = self.provider(payload([{"region": "domestic"}, entry("有效标题")]))
        result = provider.fetch("")
        self.assertEqual([item.title for item in result.items], ["有效标题"])

    def test_model_failure_reuses_the_cache(self):
        stamp = datetime.now(timezone.utc)
        self.cache.save([entry_to_item()], stamp, topic="")
        provider, _ = self.provider(RuntimeError("network down"))
        result = provider.fetch("")
        self.assertTrue(result.used_cache)
        self.assertEqual(len(result.items), 1)
        self.assertIn("失败", result.message)

    def test_model_failure_without_cache_is_an_honest_error(self):
        provider, _ = self.provider(RuntimeError("network down"))
        result = provider.fetch("")
        self.assertFalse(result.success)
        self.assertFalse(result.items)
        self.assertIn("失败", result.message)

    def test_malformed_model_output_does_not_crash(self):
        provider, _ = self.provider("这不是 JSON")
        result = provider.fetch("")
        self.assertFalse(result.success)
        self.assertFalse(result.items)

    def test_successful_fetch_is_cached_for_the_next_open(self):
        provider, _ = self.provider(payload([entry("某地新政")]))
        provider.fetch("")
        cached, stamp = self.cache.load(topic="")
        self.assertEqual(len(cached), 1)
        self.assertIsNotNone(stamp)

    def test_prompt_forbids_invented_links_and_asks_for_both_regions(self):
        prompt = build_hotspot_prompt(24, "")
        self.assertIn("domestic", prompt)
        self.assertIn("international", prompt)
        self.assertIn("不要", prompt)

    def test_prompt_asks_for_interesting_and_varied_items(self):
        prompt = build_hotspot_prompt(30, "")
        self.assertIn("有意思", prompt)
        self.assertIn("避免", prompt)
        self.assertIn("30", prompt)

    def test_prompt_requires_time_and_source_per_item(self):
        prompt = build_hotspot_prompt(30, "")
        self.assertIn("when", prompt)
        self.assertIn("source", prompt)
        self.assertIn("优先挑最近", prompt)
        # 旧的可以来，但不许把旧事说成当下热点
        self.assertIn("绝不能把旧事说成当下热点", prompt)

    def test_time_and_source_are_kept_in_the_display_note(self):
        provider, _ = self.provider(payload([
            entry("某地新政", when="2024年4月", source="新华社"),
        ]))
        item = provider.fetch("").items[0]
        self.assertIn("2024年4月", item.time_note)
        self.assertIn("新华社", item.time_note)
        self.assertIn("模型自述", item.time_note)

    def test_missing_time_and_source_say_so_instead_of_guessing(self):
        provider, _ = self.provider(payload([entry("某地新政", when="", source="")]))
        note = provider.fetch("").items[0].time_note
        self.assertIn("时间不确定", note)
        self.assertIn("来源不确定", note)

    def test_time_note_survives_the_cache(self):
        provider, _ = self.provider(payload([entry("某地新政", when="2026年10月", source="路透社")]))
        provider.fetch("")
        cached, _ = self.cache.load(topic="")
        self.assertIn("路透社", cached[0].time_note)

    def test_default_selection_is_ten_items(self):
        items = [entry(f"热点{index}") for index in range(30)]
        provider, _ = self.provider(payload(items))
        self.assertEqual(provider.max_items, 10)
        self.assertEqual(provider.pool_size, 30)
        self.assertEqual(len(provider.fetch("").items), 10)


def entry_to_item():
    from brainstorm.hotspots import HotspotItem

    return HotspotItem(title="缓存里的旧热点", publisher="模型生成", region="domestic")


if __name__ == "__main__":
    unittest.main()
