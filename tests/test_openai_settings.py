import json
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from brainstorm.config import AppConfig
from brainstorm.llm import OpenAICompatibleDiscussionProvider, GenerationCancelled, ProviderFailure, TurnSpec
from brainstorm.providers import resolve_providers
from brainstorm.ai_settings import AISettingsStore, endpoint_url


class OpenAISettingsTests(unittest.TestCase):
    def test_settings_key_is_encrypted_and_round_trips(self):
        with tempfile.TemporaryDirectory() as root:
            store = AISettingsStore(Path(root) / 'settings.json')
            config = AppConfig(llm_provider='openai', llm_model='test', llm_api_key='secret-regression-key', allow_llm=True)
            store.save(config)
            self.assertNotIn('secret-regression-key', store.path.read_text(encoding='utf-8'))
            loaded = store.load(AppConfig())
            self.assertEqual(loaded.llm_api_key, config.llm_api_key)
            self.assertEqual(loaded.llm_model, 'test')
            self.assertTrue(loaded.allow_llm)

    def test_corrupt_settings_fall_back(self):
        with tempfile.TemporaryDirectory() as root:
            store = AISettingsStore(Path(root) / 'settings.json')
            store.path.write_text('broken', encoding='utf-8')
            config = AppConfig()
            self.assertEqual(store.load(config), config)

    def test_endpoint_accepts_full_path_and_rejects_insecure_remote(self):
        self.assertEqual(endpoint_url('https://example.test/v1/'), 'https://example.test/v1/chat/completions')
        self.assertEqual(endpoint_url('https://example.test/v1/chat/completions'), 'https://example.test/v1/chat/completions')
        for url in ['http://example.test/v1', 'file:///test', 'https://key@example.test/v1']:
            with self.assertRaises(ValueError):
                endpoint_url(url)

    def test_resolver_selects_openai_without_sdk_and_preserves_offline(self):
        config = AppConfig(llm_provider='openai', llm_api_key='test', llm_model='test', allow_llm=True)
        provider, _, status = resolve_providers(config)
        self.assertIsInstance(provider, OpenAICompatibleDiscussionProvider)
        self.assertEqual(provider.timeout, 60)
        self.assertIn('真实模型', status.describe())
        from dataclasses import replace
        provider, _, status = resolve_providers(replace(config, mode='offline'))
        self.assertEqual(status.discussion_provider, 'mock')

    def test_http_wire_format_and_error_and_cancel(self):
        captured = []
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_args): pass
            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                captured.append((self.path, self.headers['Authorization'], body))
                if body['model'] == 'failure':
                    self.send_response(401)
                    self.end_headers()
                    return
                payload = json.dumps({'choices': [{'message': {'content': json.dumps({'content': '本地接口生成观点', 'kind': '假设'}, ensure_ascii=False)}}], 'usage': {'prompt_tokens': 10, 'completion_tokens': 20}}).encode()
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)
        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            provider = OpenAICompatibleDiscussionProvider(api_key='local-test-key', model='test', base_url=f'http://127.0.0.1:{server.server_port}/v1', max_retries=0)
            partials = []
            result = provider.generate_turn('主题', [], [], [], TurnSpec('moderator', '主持人', '开场'), on_partial=partials.append)
            self.assertEqual(result.utterance.content, '本地接口生成观点')
            self.assertEqual(result.usage.output_tokens, 20)
            self.assertTrue(partials)
            self.assertEqual(captured[0][0], '/v1/chat/completions')
            self.assertEqual(captured[0][1], 'Bearer local-test-key')
            self.assertEqual(captured[0][2]['messages'][0]['role'], 'system')
            provider.model = 'failure'
            with self.assertRaises(ProviderFailure) as context:
                provider.generate_turn('主题', [], [], [], TurnSpec('moderator', '主持人', '开场'))
            self.assertNotIn('local-test-key', str(context.exception))
            event = threading.Event()
            event.set()
            before = len(captured)
            with self.assertRaises(GenerationCancelled):
                provider.generate_turn('主题', [], [], [], TurnSpec('moderator', '主持人', '开场'), cancel_event=event)
            self.assertEqual(len(captured), before)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(2)
