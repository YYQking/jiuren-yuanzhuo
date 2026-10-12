import json
import tempfile
import unittest
from pathlib import Path

from brainstorm.engine import MockDiscussionProvider
from brainstorm.models import DiscussionSession, Utterance, ViewpointKind
from brainstorm.playback import DiscussionPlayback, PlaybackState
from brainstorm.storage import SCHEMA_VERSION, SessionStore, session_from_dict, session_to_dict
from brainstorm.export import export_markdown
from brainstorm.roles import DEFAULT_ROLES


class PersistencePlaybackTests(unittest.TestCase):
    def setUp(self):
        self.session = MockDiscussionProvider().discuss("测试主题", DEFAULT_ROLES[:2])

    def test_round_trip_preserves_metadata_and_interjection(self):
        self.session.utterances.append(Utterance("user", "用户", "补充观点", ViewpointKind.ASSUMPTION, "用户插话", simulated=False))
        restored = session_from_dict(session_to_dict(self.session))
        self.assertEqual(restored.topic, self.session.topic)
        self.assertEqual(restored.utterances[-1].content, "补充观点")
        self.assertFalse(restored.utterances[-1].simulated)

    def test_new_discussion_metadata_round_trips(self):
        item = self.session.utterances[1]
        self.assertTrue(item.event_id)
        restored = session_from_dict(session_to_dict(self.session))
        self.assertEqual(restored.utterances[1].event_id, item.event_id)
        self.assertEqual(restored.discussion_state.active_thread, self.session.discussion_state.active_thread)

    def test_legacy_utterance_defaults_to_safe_event_metadata(self):
        restored = session_from_dict({
            "schema_version": SCHEMA_VERSION,
            "topic": "旧记录",
            "created_at": "2030-01-01T12:00:00",
            "utterances": [{
                "speaker_id": "moderator", "speaker_name": "主持人",
                "content": "开场", "kind": "总结", "phase": "开场",
            }],
        })
        self.assertEqual(restored.utterances[0].sequence, 0)
        self.assertEqual(restored.utterances[0].verification, "unverified")
        self.assertEqual(restored.phase, "开题")

    def test_mixed_content_sources_survive_history_and_export(self):
        from dataclasses import replace
        self.session.effective_provider = "anthropic"
        self.session.utterances[1] = replace(self.session.utterances[1], origin="model")
        self.session.utterances.append(Utterance("trend", "趋势研究者", "离线补充", ViewpointKind.RISK, "补充", origin="offline"))
        restored = session_from_dict(session_to_dict(self.session))
        self.assertEqual(restored.utterances[1].origin, "model")
        self.assertEqual(restored.utterances[-1].origin, "offline")
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "mixed.md"
            export_markdown(restored, output)
            text = output.read_text(encoding="utf-8")
            self.assertIn("模型生成", text)
            self.assertIn("离线模拟", text)

    def test_discussion_state_and_event_metadata_export(self):
        MockDiscussionProvider().extend(self.session, 1)
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "state.md"
            export_markdown(self.session, output)
            text = output.read_text(encoding="utf-8")
            self.assertIn("未解决分歧", text)
            self.assertIn("立场轨迹", text)
            self.assertIn("回应意图", text)

    def test_store_save_is_valid_and_ignores_corrupt_history(self):
        with tempfile.TemporaryDirectory() as directory:
            store = SessionStore(Path(directory))
            path = store.save(self.session)
            (Path(directory) / "broken.json").write_text("{not json", encoding="utf-8")
            self.assertEqual(store.load(path).topic, "测试主题")
            self.assertEqual(len(store.list_sessions()), 1)
            self.assertFalse(list(Path(directory).glob("*.tmp")))

    def test_playback_completion_and_restart(self):
        playback = DiscussionPlayback()
        first = playback.start(self.session)
        self.assertIs(first, self.session.utterances[0])
        while playback.state != PlaybackState.COMPLETED:
            playback.advance()
        self.assertIsNone(playback.current)
        self.assertIs(playback.restart(), self.session.utterances[0])
        self.assertEqual(playback.state, PlaybackState.PLAYING)

    def test_live_playback_waits_for_explicit_finish(self):
        playback = DiscussionPlayback(live=True)
        self.assertIs(playback.start(self.session), self.session.utterances[0])
        while playback.index < len(self.session.utterances) - 1:
            playback.advance()
        self.assertEqual(playback.advance(), self.session.utterances[-1])
        self.assertEqual(playback.state, PlaybackState.PLAYING)
        self.assertIs(playback.finish(), self.session.utterances[-1])
        self.assertEqual(playback.state, PlaybackState.COMPLETED)

    def test_v2_metadata_defaults_and_source_round_trip(self):
        legacy = {
            "schema_version": 2,
            "topic": "旧主题",
            "source": {"title": "旧线索", "note": "摘要"},
            "utterances": [],
            "opportunity": None,
            "created_at": "2030-01-01T12:00:00",
        }
        restored = session_from_dict(legacy)
        self.assertEqual(restored.topic, "旧主题")
        self.assertEqual(restored.source.title, "旧线索")
        self.assertEqual(restored.effective_provider, "mock")
        self.assertFalse(restored.network_used)

    def test_source_metadata_round_trip(self):
        from datetime import datetime
        from brainstorm.models import TrendSource

        source = TrendSource(
            "RSS 线索",
            "https://feed.test/a",
            "摘要",
            source_type="rss",
            fetched_at=datetime(2030, 1, 1, 12, 0),
            published_at=datetime(2030, 1, 1, 11, 0),
        )
        self.session.sources = [source]
        self.session.source = source
        restored = session_from_dict(session_to_dict(self.session))
        self.assertEqual(restored.sources[0].source_type, "rss")
        self.assertEqual(restored.sources[0].published_at.year, 2030)

    def test_invalid_session_has_clear_error(self):
        with self.assertRaises(ValueError):
            session_from_dict({"topic": " "})

    def test_v3_metadata_defaults_to_safe_values(self):
        restored = session_from_dict({
            "schema_version": 3,
            "topic": "旧版本",
            "created_at": "2030-01-01T12:00:00",
            "utterances": [],
        })
        self.assertEqual(restored.request_mode, "offline")
        self.assertEqual(restored.news_provider, "offline")
        self.assertEqual(restored.generation_status, "offline")
        self.assertFalse(restored.news_attempted)

    def test_legacy_migration_adds_explicit_news_metadata(self):
        restored = session_from_dict({
            "schema_version": 2,
            "topic": "迁移主题",
            "created_at": "2030-01-01T12:00:00",
            "utterances": [],
        })
        self.assertEqual(restored.news_provider, "offline")
        self.assertFalse(restored.news_attempted)
        self.assertTrue(restored.news_success)
        self.assertFalse(restored.news_matched)
        self.assertEqual(session_to_dict(restored)["schema_version"], SCHEMA_VERSION)

    def test_news_metadata_round_trip_and_markdown_export(self):
        self.session.news_attempted = True
        self.session.news_success = False
        self.session.news_matched = True
        self.session.news_partial_failure = True
        self.session.network_used = False
        restored = session_from_dict(session_to_dict(self.session))
        self.assertTrue(restored.news_attempted)
        self.assertFalse(restored.news_success)
        self.assertTrue(restored.news_matched)
        self.assertTrue(restored.news_partial_failure)
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "session.md"
            export_markdown(restored, output)
            text = output.read_text(encoding="utf-8")
            self.assertIn("RSS 尝试：是", text)
            self.assertIn("RSS 部分失败：是", text)

    def test_future_schema_is_rejected_explicitly(self):
        with self.assertRaisesRegex(ValueError, "unsupported schema"):
            session_from_dict({
                "schema_version": SCHEMA_VERSION + 1,
                "topic": "未来主题",
                "created_at": "2030-01-01T12:00:00",
                "utterances": [],
            })

    def test_invalid_utterance_kind_has_clear_migration_error(self):
        with self.assertRaisesRegex(ValueError, "utterance kind"):
            session_from_dict({
                "schema_version": 3,
                "topic": "旧版本",
                "created_at": "2030-01-01T12:00:00",
                "utterances": [{"speaker_id": "r", "speaker_name": "角色", "content": "内容", "kind": "未知", "phase": "观点"}],
            })

    def test_invalid_created_at_has_clear_migration_error(self):
        with self.assertRaisesRegex(ValueError, "created_at"):
            session_from_dict({"schema_version": 2, "topic": "旧版本", "created_at": "not-a-date", "utterances": []})

    def test_incomplete_opportunity_has_clear_migration_error(self):
        with self.assertRaisesRegex(ValueError, "opportunity"):
            session_from_dict({"topic": "旧版本", "opportunity": {"title": "只有标题"}, "utterances": []})


if __name__ == "__main__":
    unittest.main()
