"""Characterization + contract tests for scripts/fetch_stars.py.

Stdlib unittest only (no pytest) to keep the project zero-dependency.
Run:  python3 -m unittest tests.test_fetch_stars -v
"""
import json
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from scripts import fetch_stars  # noqa: E402  (import after sys.path setup)


class FakeResponse:
    """Minimal stand-in for urllib's HTTPResponse used by the paginator.

    Mirrors the real interface: a context manager with ``read()`` and
    ``headers`` (a mapping supporting ``.get``).
    """

    def __init__(self, payload, link=""):
        self._payload = payload
        self.headers = {"Link": link} if link else {}

    def read(self):
        return self._payload

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class BuildHeadersTest(unittest.TestCase):
    def test_uses_bearer_not_deprecated_token_prefix(self):
        h = fetch_stars.build_headers("abc123")
        self.assertEqual(h["Authorization"], "Bearer abc123")
        self.assertFalse(h["Authorization"].startswith("token"))

    def test_includes_accept_and_user_agent(self):
        h = fetch_stars.build_headers("x")
        self.assertIn("vnd.github", h["Accept"])
        self.assertTrue(h["User-Agent"])

    def test_empty_token_omits_authorization_header(self):
        # GitHub answers 401 to a bare "Bearer " header, so with no token we
        # must omit Authorization entirely for the public endpoint to work
        # when run locally without GH_TOKEN.
        h = fetch_stars.build_headers("")
        self.assertNotIn("Authorization", h)


class StarredUrlTest(unittest.TestCase):
    def test_targets_soloface_starred_endpoint(self):
        self.assertIn("/users/soloface/starred", fetch_stars.starred_url(1))

    def test_requests_per_page_100(self):
        self.assertIn("per_page=100", fetch_stars.starred_url(1))

    def test_increments_page_param(self):
        self.assertIn("page=3", fetch_stars.starred_url(3))

    def test_uses_github_api_host(self):
        self.assertTrue(fetch_stars.starred_url(1).startswith("https://api.github.com/"))

    def test_token_never_leaks_into_query_string(self):
        qs = fetch_stars.starred_url(1).split("?", 1)[-1].lower()
        self.assertNotIn("token", qs)


def _sample_item():
    return {
        "starred_at": "2024-01-01T00:00:00Z",
        "repo": {
            "full_name": "owner/name",
            "html_url": "https://github.com/owner/name",
            "description": "A repo",
            "stargazers_count": 42,
            "forks_count": 7,
            "language": "Python",
            "created_at": "2020-01-01T00:00:00Z",
            "pushed_at": "2024-01-01T00:00:00Z",
            "topics": ["a", "b"],
            "owner": {"avatar_url": "https://avatar"},
        },
    }


class TransformRepoTest(unittest.TestCase):
    def test_maps_every_output_field(self):
        out = fetch_stars.transform_repo(_sample_item())
        self.assertEqual(out["full_name"], "owner/name")
        self.assertEqual(out["html_url"], "https://github.com/owner/name")
        self.assertEqual(out["description"], "A repo")
        self.assertEqual(out["stargazers_count"], 42)
        self.assertEqual(out["forks_count"], 7)
        self.assertEqual(out["language"], "Python")
        self.assertEqual(out["starred_at"], "2024-01-01T00:00:00Z")
        self.assertEqual(out["created_at"], "2020-01-01T00:00:00Z")
        self.assertEqual(out["pushed_at"], "2024-01-01T00:00:00Z")
        self.assertEqual(out["topics"], ["a", "b"])
        self.assertEqual(out["owner_avatar"], "https://avatar")

    def test_defaults_when_repo_fields_missing(self):
        out = fetch_stars.transform_repo({"repo": {}})
        self.assertEqual(out["full_name"], "")
        self.assertEqual(out["description"], "")
        self.assertEqual(out["stargazers_count"], 0)
        self.assertEqual(out["topics"], [])

    def test_handles_item_without_repo_key(self):
        out = fetch_stars.transform_repo({"starred_at": "x"})
        self.assertEqual(out["starred_at"], "x")
        self.assertEqual(out["full_name"], "")


class FetchAllStarredTest(unittest.TestCase):
    @staticmethod
    def _resp(items, link=""):
        return FakeResponse(json.dumps(items).encode(), link)

    def test_paginates_following_next_link(self):
        link1 = '<https://api.github.com/users/soloface/starred?page=2>; rel="next"'

        def fake_urlopen(req):
            url = req.full_url
            if "page=2" in url:
                return self._resp([{"starred_at": "b", "repo": {"full_name": "b/b"}}], "")
            return self._resp([{"starred_at": "a", "repo": {"full_name": "a/a"}}], link1)

        result = fetch_stars.fetch_all_starred("tok", urlopen=fake_urlopen, _sleep=lambda _: None)
        self.assertEqual([r["repo"]["full_name"] for r in result], ["a/a", "b/b"])

    def test_stops_on_empty_page(self):
        def fake_urlopen(req):
            return self._resp([], "")
        self.assertEqual(fetch_stars.fetch_all_starred("tok", urlopen=fake_urlopen, _sleep=lambda _: None), [])

    def test_stops_when_no_next_link(self):
        def fake_urlopen(req):
            return self._resp([{"starred_at": "a", "repo": {"full_name": "a/a"}}], "")
        result = fetch_stars.fetch_all_starred("tok", urlopen=fake_urlopen, _sleep=lambda _: None)
        self.assertEqual(len(result), 1)


class DataPathTest(unittest.TestCase):
    def test_data_file_resolves_under_repo_root_regardless_of_cwd(self):
        # Script lives in scripts/ but output must always land at <repo>/data/stars.json
        expected = os.path.normpath(os.path.join(ROOT, "data", "stars.json"))
        self.assertEqual(os.path.normpath(fetch_stars.DATA_FILE), expected)


if __name__ == "__main__":
    unittest.main()
