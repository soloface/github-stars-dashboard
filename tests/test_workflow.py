"""Contract tests for .github/workflows/fetch-stars.yml.

The workflow is config, but its acceptance criteria (permissions, no inline
Python, delegates to the extracted scripts, no deep-translator) are explicit,
so we pin them as a structural contract test.
Run:  python3 -m unittest tests.test_workflow -v
"""
import os
import unittest

import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORKFLOW = os.path.join(ROOT, ".github", "workflows", "fetch-stars.yml")


def _raw():
    with open(WORKFLOW) as f:
        return f.read()


def _steps():
    doc = yaml.safe_load(_raw())
    job = doc["jobs"][next(iter(doc["jobs"]))]
    return doc, job["steps"]


class WorkflowStructureTest(unittest.TestCase):
    def test_yaml_is_valid_and_has_expected_top_level_keys(self):
        doc, _ = _steps()
        self.assertIn("name", doc)
        self.assertIn("permissions", doc)
        self.assertIn("jobs", doc)
        # PyYAML parses bare `on:` as boolean True (YAML 1.1); GitHub Actions
        # treats it as the trigger key either way, so accept both forms.
        self.assertTrue("on" in doc or True in doc, "trigger key 'on:' missing")

    def test_permissions_grants_contents_write(self):
        doc, _ = _steps()
        self.assertEqual(doc.get("permissions", {}).get("contents"), "write")

    def test_no_inline_python_heredocs(self):
        text = _raw()
        for marker in ("<<", "PYEOF", "TRANS_EOF"):
            self.assertNotIn(marker, text, "inline heredoc marker %r still present" % marker)

    def test_delegates_to_fetch_stars_script(self):
        _, steps = _steps()
        runs = [s.get("run", "") for s in steps if "run" in s]
        self.assertTrue(any("scripts/fetch_stars.py" in r for r in runs), runs)

    def test_delegates_to_translate_script(self):
        _, steps = _steps()
        runs = [s.get("run", "") for s in steps if "run" in s]
        self.assertTrue(any("scripts/translate_descriptions.py" in r for r in runs), runs)

    def test_no_deep_translator_dependency(self):
        text = _raw()
        for banned in ("deep-translator", "pip install", "deep_translator"):
            self.assertNotIn(banned, text)

    def test_uses_checkout_setup_python_and_push(self):
        text = _raw()
        self.assertIn("actions/checkout", text)
        self.assertIn("actions/setup-python", text)
        self.assertIn("git push", text)

    def test_passes_gh_token_to_fetch_step(self):
        # GH_TOKEN must be forwarded to the fetch step env (Bearer used inside the script)
        doc, steps = _steps()
        fetch = next(s for s in steps if s.get("run", "").strip().endswith("scripts/fetch_stars.py")
                     or "scripts/fetch_stars.py" in s.get("run", ""))
        env = fetch.get("env", {})
        self.assertTrue(any("TOKEN" in k for k in env), env)

    def test_workflow_is_simplified(self):
        # Original was 128 lines of inline Python; refactored should be far smaller.
        self.assertLess(_raw().count("\n"), 70)


if __name__ == "__main__":
    unittest.main()
