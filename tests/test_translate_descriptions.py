"""Tests for scripts/translate_descriptions.py.

Stdlib unittest only. Network is stubbed via an injected ``opener`` so no real
Google request is made. Run:  python3 -m unittest tests.test_translate_descriptions -v
"""
import ast
import inspect
import json
import os
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from scripts import translate_descriptions as td  # noqa: E402


class FakeResp:
    def __init__(self, payload):
        self._payload = payload

    def read(self):
        return self._payload

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def google_response(*segments):
    """Build a payload shaped like the translate.googleapis.com reply."""
    return json.dumps([[list(seg) for seg in segments]]).encode()


class ContainsChineseTest(unittest.TestCase):
    def test_true_for_chinese(self):
        self.assertTrue(td.contains_chinese("一个仓库"))

    def test_false_for_english(self):
        self.assertFalse(td.contains_chinese("A repository"))

    def test_true_for_mixed(self):
        self.assertTrue(td.contains_chinese("hello 世界"))


class TranslateTest(unittest.TestCase):
    def test_parses_google_response(self):
        payload = google_response(["你好世界", "hello world", None, None, 10])
        out = td.translate("hello world", opener=lambda req: FakeResp(payload))
        self.assertEqual(out, "你好世界")

    def test_skips_chinese_input_without_network_call(self):
        def explode(req):
            raise AssertionError("opener must not be called for Chinese input")
        self.assertEqual(td.translate("已是中文", opener=explode), "已是中文")

    def test_empty_returns_empty(self):
        self.assertEqual(td.translate("", opener=lambda req: FakeResp(b"[]")), "")

    def test_falls_back_to_original_on_network_error(self):
        def boom(req):
            raise RuntimeError("network down")
        self.assertEqual(td.translate("hello", opener=boom), "hello")

    def test_falls_back_to_original_on_bad_payload(self):
        self.assertEqual(td.translate("hello", opener=lambda req: FakeResp(b"not json")), "hello")


class DependencyTest(unittest.TestCase):
    def test_uses_only_stdlib_no_translator_package(self):
        src = inspect.getsource(td)
        for banned in ("deep_translator", "googletrans", "import requests", "from requests"):
            self.assertNotIn(banned, src)
        # HTTP must be done through the stdlib urllib, not a third-party client.
        self.assertIn("urllib", src)
        # every imported top-level module must resolve as a builtin/stdlib import
        tree = ast.parse(src)
        names = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names.update(a.name.split(".")[0] for a in node.names)
            elif isinstance(node, ast.ImportFrom):
                if node.module and node.level == 0:
                    names.add(node.module.split(".")[0])
        third_party = {"deep_translator", "googletrans", "requests", "httpx", "aiohttp"}
        self.assertFalse(names & third_party, "third-party deps found: %s" % (names & third_party))


class TranslateDescriptionsTest(unittest.TestCase):
    def _fake_translator(self):
        calls = []

        def fn(text):
            calls.append(text)
            return "译文:" + text

        fn.calls = calls
        return fn

    def test_populates_missing_description_zh(self):
        fn = self._fake_translator()
        repos = [{"description": "A repo"}, {"description": "Another"}]
        td.translate_descriptions(repos, translate_fn=fn)
        self.assertEqual(repos[0]["description_zh"], "译文:A repo")
        self.assertEqual(repos[1]["description_zh"], "译文:Another")

    def test_preserves_existing_translation(self):
        fn = self._fake_translator()
        repos = [{"description": "A repo", "description_zh": "已有译文"}]
        td.translate_descriptions(repos, translate_fn=fn)
        self.assertEqual(repos[0]["description_zh"], "已有译文")
        self.assertEqual(fn.calls, [], "must not re-translate when description_zh already set")

    def test_empty_description_yields_empty_translation(self):
        fn = self._fake_translator()
        repos = [{"description": ""}]
        td.translate_descriptions(repos, translate_fn=fn)
        self.assertEqual(repos[0]["description_zh"], "")

    def test_chinese_description_is_kept_as_is(self):
        fn = self._fake_translator()
        repos = [{"description": "中文简介"}]
        td.translate_descriptions(repos, translate_fn=fn)
        self.assertEqual(repos[0]["description_zh"], "中文简介")

    def test_file_round_trip(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "stars.json")
            with open(path, "w") as f:
                json.dump([{"description": "hello"}, {"description": "中文"}], f)
            td.process_file(path, translate_fn=lambda t: "Z:" + t if t and not td.contains_chinese(t) else t)
            with open(path) as f:
                result = json.load(f)
            self.assertEqual(result[0]["description_zh"], "Z:hello")
            self.assertEqual(result[1]["description_zh"], "中文")


class DataPathTest(unittest.TestCase):
    def test_data_file_resolves_under_repo_root(self):
        expected = os.path.normpath(os.path.join(ROOT, "data", "stars.json"))
        self.assertEqual(os.path.normpath(td.DATA_FILE), expected)


if __name__ == "__main__":
    unittest.main()
