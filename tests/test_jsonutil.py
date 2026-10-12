import unittest

from brainstorm.jsonutil import load_json_object, strip_code_fence


class JsonUtilTests(unittest.TestCase):
    def test_strip_code_fence_removes_language_tag_and_trailing_fence(self):
        self.assertEqual(strip_code_fence('```json\n{"a":1}\n```'), '{"a":1}')

    def test_strip_code_fence_leaves_plain_text_alone(self):
        self.assertEqual(strip_code_fence('  {"a":1}  '), '{"a":1}')

    def test_load_json_object_parses_fenced_object(self):
        self.assertEqual(load_json_object('```json\n{"a": 1}\n```'), {"a": 1})

    def test_load_json_object_rejects_non_object(self):
        with self.assertRaises(ValueError):
            load_json_object('[1, 2]')

    def test_load_json_object_rejects_malformed_json(self):
        with self.assertRaises(ValueError):
            load_json_object('{"a": ')


if __name__ == "__main__":
    unittest.main()
