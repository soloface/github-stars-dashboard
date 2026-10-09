"""Tests for scripts/categorize_repos.py.

Stdlib unittest only. The pure functions are exercised with in-memory data;
``main`` is exercised against a temporary data directory. Run:
    python3 -m unittest tests.test_categorize_repos -v
"""
import contextlib
import io
import json
import os
import sys
import tempfile
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from scripts import categorize_repos as cr  # noqa: E402

CATEGORIES = {
    "version": 1,
    "taxonomy": [
        {
            "id": "ai-coding",
            "name": "AI 编码代理",
            "description": "",
            "children": [
                {"id": "ai-coding/agents", "name": "CLI", "description": "",
                 "keywords": ["coding agent", "terminal"]},
                {"id": "ai-coding/addons", "name": "插件", "description": "",
                 "keywords": ["plugin", "statusline", "插件"]},
            ],
        },
        {
            "id": "creative",
            "name": "创作",
            "description": "",
            "children": [
                {"id": "creative/video", "name": "视频", "description": "",
                 "keywords": ["video", "video editor", "视频"]},
            ],
        },
        {"id": "resources", "name": "资源", "description": "", "children": [],
         "keywords": ["awesome", "awesome list"]},
        {"id": "other", "name": "其他", "description": "", "children": []},
    ],
}


def repo(full_name, description="", topics=(), description_zh=None):
    return {
        "full_name": full_name,
        "description": description,
        "description_zh": description if description_zh is None else description_zh,
        "topics": list(topics),
    }


def entry(primary, secondary=(), source="seed", desc="", **extra):
    out = {
        "primary": primary,
        "secondary": list(secondary),
        "source": source,
        "desc_hash": cr.desc_hash(desc),
    }
    out.update(extra)
    return out


RULES = cr.load_rules(CATEGORIES)


class DescHashTest(unittest.TestCase):
    def test_matches_seed_scheme(self):
        # sha256 of the UTF-8 description, first 12 hex chars; None == "".
        self.assertEqual(cr.desc_hash(""), "e3b0c44298fc")
        self.assertEqual(cr.desc_hash(None), cr.desc_hash(""))
        self.assertEqual(len(cr.desc_hash("视频")), 12)


class LoadRulesTest(unittest.TestCase):
    def test_assignable_ids_are_children_and_leaf_top_levels(self):
        self.assertEqual(
            list(RULES),
            ["ai-coding/agents", "ai-coding/addons", "creative/video", "resources", "other"],
        )
        self.assertEqual(RULES["other"], [])
        self.assertIn("statusline", RULES["ai-coding/addons"])

    def test_malformed_taxonomy_raises(self):
        no_other = {"taxonomy": [{"id": "resources", "children": []}]}
        for bad in ({}, {"taxonomy": "x"}, {"taxonomy": [{"name": "no id"}]}, [], no_other):
            with self.assertRaises(ValueError):
                cr.load_rules(bad)


class ScoreTest(unittest.TestCase):
    def test_exact_topic_weighs_more_than_text(self):
        by_topic = cr.score(repo("a/x", topics=["video"]), RULES)
        by_text = cr.score(repo("a/x", "make a video"), RULES)
        self.assertGreater(by_topic["creative/video"], by_text["creative/video"])

    def test_ascii_terms_use_word_boundaries(self):
        # Plurals are tolerated, but "video" must not fire inside "videographers".
        self.assertNotIn("creative/video", cr.score(repo("a/x", "for videographers"), RULES))
        self.assertIn("ai-coding/addons", cr.score(repo("a/x", "a handy plugin"), RULES))
        self.assertIn("ai-coding/addons", cr.score(repo("a/x", "many plugins"), RULES))

    def test_multi_word_terms_match_hyphens_and_spaces(self):
        self.assertIn("ai-coding/agents", cr.score(repo("a/x", topics=["coding-agent"]), RULES))
        self.assertIn("ai-coding/agents", cr.score(repo("a/x", "the coding agent"), RULES))

    def test_cjk_terms_use_substring_on_description_zh(self):
        s = cr.score(repo("a/x", "Edit clips", description_zh="剪辑视频的工具"), RULES)
        self.assertIn("creative/video", s)

    def test_repo_name_is_split_on_case_and_separators(self):
        self.assertIn("creative/video", cr.score(repo("a/OpenVideoCut"), RULES))
        self.assertIn("resources", cr.score(repo("a/awesome-things"), RULES))


class ClassifyTest(unittest.TestCase):
    def test_below_threshold_falls_back_to_other(self):
        self.assertEqual(cr.classify(repo("a/x", "something unrelated"), RULES),
                         {"primary": "other", "secondary": []})

    def test_picks_highest_scoring_primary(self):
        r = repo("a/x", "A video editor", topics=["video", "video-editor"])
        self.assertEqual(cr.classify(r, RULES)["primary"], "creative/video")

    def test_secondary_is_distinct_capped_and_excludes_primary(self):
        rules = cr.load_rules({"taxonomy": [
            {"id": cid, "children": [], "keywords": [cid]}
            for cid in ("alpha", "beta", "gamma", "delta")] + [{"id": "other", "children": []}]})
        r = repo("a/alpha", "alpha beta gamma delta", topics=["alpha", "beta", "gamma", "delta"])
        # alpha = topic 3 + name 2 + text 1 = 6; the others 4 each.
        self.assertEqual(cr.classify(r, rules), {"primary": "alpha", "secondary": ["beta", "gamma"]})

    def test_ambiguous_lead_falls_back_to_other(self):
        # video 4 (topic + text) vs addons 3 (topic): no clear winner.
        r = repo("a/x", "video", topics=["video", "plugin"])
        self.assertEqual(cr.score(r, RULES), {"creative/video": 4, "ai-coding/addons": 3})
        self.assertEqual(cr.classify(r, RULES)["primary"], "other")

    def test_weak_secondary_is_dropped(self):
        r = repo("a/x", "A video editor with a plugin", topics=["video", "video-editor"])
        self.assertEqual(cr.classify(r, RULES)["secondary"], [])


class UpdateAssignmentsTest(unittest.TestCase):
    def run_update(self, repos, assignments, overrides=None):
        return cr.update_assignments(repos, assignments, overrides or {}, RULES)

    def test_1_override_leaves_existing_assignment_untouched(self):
        old = entry("creative/video", source="rule", desc="old desc", needs_review=True)
        out, stats = self.run_update(
            [repo("a/x", "a new description")], {"a/x": old},
            {"a/x": {"primary": "resources", "secondary": []}})
        self.assertEqual(out, {"a/x": old})
        self.assertEqual(stats["kept"], 1)

    def test_1_override_without_assignment_creates_nothing(self):
        out, _ = self.run_update([repo("a/x", "video")], {},
                                 {"a/x": {"primary": "resources", "secondary": []}})
        self.assertEqual(out, {})

    def test_2_human_sources_survive_description_change(self):
        for source in ("seed", "manual"):
            old = entry("resources", ["creative/video"], source=source, desc="old")
            out, stats = self.run_update([repo("a/x", "a terminal coding agent")], {"a/x": old})
            self.assertEqual(out["a/x"]["primary"], "resources")
            self.assertEqual(out["a/x"]["secondary"], ["creative/video"])
            self.assertEqual(out["a/x"]["source"], source)
            self.assertEqual(out["a/x"]["desc_hash"], cr.desc_hash("a terminal coding agent"))
            self.assertEqual(stats["kept"], 1)
            # input is not mutated
            self.assertEqual(old["desc_hash"], cr.desc_hash("old"))

    def test_2_human_entry_keeps_needs_review_flag(self):
        old = entry("other", source="seed", desc="d", needs_review=True)
        out, _ = self.run_update([repo("a/x", "d")], {"a/x": old})
        self.assertEqual(out["a/x"], old)

    def test_3_rule_entry_unchanged_hash_is_kept(self):
        old = entry("resources", source="rule", desc="video editor", needs_review=True)
        out, stats = self.run_update([repo("a/x", "video editor")], {"a/x": old})
        self.assertEqual(out["a/x"], old)
        self.assertEqual(stats["kept"], 1)

    def test_3_rule_entry_changed_hash_is_reclassified(self):
        old = entry("resources", source="rule", desc="old", needs_review=True)
        r = repo("a/x", "A video editor", topics=["video"])
        out, stats = self.run_update([r], {"a/x": old})
        self.assertEqual(out["a/x"]["primary"], "creative/video")
        self.assertEqual(out["a/x"]["desc_hash"], cr.desc_hash("A video editor"))
        self.assertEqual(stats["new_rule"], 1)

    def test_4_new_repo_gets_rule_entry(self):
        r = repo("a/x", "A video editor", topics=["video"])
        out, stats = self.run_update([r], {})
        self.assertEqual(out["a/x"], {
            "primary": "creative/video",
            "secondary": [],
            "source": "rule",
            "desc_hash": cr.desc_hash("A video editor"),
            "needs_review": True,
        })
        self.assertEqual(stats, {"kept": 0, "new_rule": 1, "new_other": 0, "dropped": 0,
                                 "unstarred": 0})

    def test_4_new_repo_without_signal_goes_to_other(self):
        out, stats = self.run_update([repo("a/x", "")], {})
        self.assertEqual(out["a/x"]["primary"], "other")
        self.assertEqual(out["a/x"]["secondary"], [])
        self.assertTrue(out["a/x"]["needs_review"])
        self.assertEqual(stats["new_other"], 1)

    def run_quiet(self, repos, assignments):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            out, stats = self.run_update(repos, assignments)
        return out, stats, buf.getvalue()

    def test_drops_rule_entries_of_repos_no_longer_starred(self):
        assignments = {"a/gone": entry("resources", source="rule"), "a/bad": "not a dict",
                       "a/x": entry("resources")}
        out, stats = self.run_update([repo("a/x")], assignments)
        self.assertEqual(list(out), ["a/x"])
        self.assertEqual(stats["dropped"], 2)
        self.assertEqual(stats["unstarred"], 0)

    def test_keeps_human_entries_of_repos_no_longer_starred(self):
        # A partial or shrunken stars.json must not erase human judgment.
        assignments = {"a/seed": entry("resources"), "a/manual": entry("other", source="manual"),
                       "a/x": entry("resources")}
        out, stats = self.run_update([repo("a/x")], assignments)
        self.assertEqual(out, assignments)
        self.assertEqual(stats["dropped"], 0)
        self.assertEqual(stats["unstarred"], 2)

    def test_invalid_rule_or_malformed_entries_are_repaired_by_rules(self):
        r = repo("a/x", "A video editor", topics=["video"])
        cases = [
            entry("gone/category", source="rule", desc="A video editor"),
            entry("resources", ["gone/category"], source="rule", desc="A video editor"),
            entry("ai-coding", source="rule", desc="A video editor"),  # parent id, not assignable
            {"primary": "resources"},  # malformed entry
            entry(["resources"], [{"x": 1}], source="rule"),  # unhashable ids
            {"source": "seed", "secondary": [], "desc_hash": ""},  # human entry without a primary
            "not a dict",
        ]
        for old in cases:
            out, stats = self.run_update([r], {"a/x": old})
            self.assertEqual(out["a/x"]["primary"], "creative/video", old)
            self.assertEqual(out["a/x"]["source"], "rule")
            self.assertEqual(stats["new_rule"], 1)

    def test_human_unknown_secondary_is_dropped_without_reclassifying(self):
        r = repo("a/x", "A video editor", topics=["video"])
        for source in ("seed", "manual"):
            old = entry("resources", ["gone/category", ["junk"], "creative/video"], source=source,
                        desc="old")
            out, stats, log = self.run_quiet([r], {"a/x": old})
            self.assertEqual(out["a/x"], dict(old, secondary=["creative/video"],
                                              desc_hash=cr.desc_hash("A video editor")))
            self.assertEqual(stats["kept"], 1)
            self.assertEqual(stats["new_rule"], 0)
            self.assertIn("::warning title=categorize_repos::", log)
            self.assertIn("a/x", log)
            self.assertIn("gone/category", log)

    def test_human_unknown_primary_is_kept_and_flagged_for_review(self):
        r = repo("a/x", "A video editor", topics=["video"])
        for source in ("seed", "manual"):
            old = entry("gone/category", ["creative/video"], source=source, desc="A video editor")
            out, stats, log = self.run_quiet([r], {"a/x": old})
            self.assertEqual(out["a/x"], dict(old, needs_review=True))
            self.assertEqual(stats["kept"], 1)
            self.assertEqual(stats["new_rule"], 0)
            self.assertNotIn("needs_review", old)  # input is not mutated
            self.assertIn("::warning title=categorize_repos::", log)
            self.assertIn("a/x", log)
            self.assertIn("gone/category", log)

    def test_classifier_is_injectable(self):
        out, _ = cr.update_assignments(
            [repo("a/x")], {}, {}, RULES,
            classify_fn=lambda r, rules: {"primary": "resources", "secondary": []})
        self.assertEqual(out["a/x"]["primary"], "resources")


class RenderTest(unittest.TestCase):
    def test_sorted_case_insensitively_with_trailing_newline(self):
        text = cr.render({"b/z": entry("resources"), "A/y": entry("resources"),
                          "a/x": entry("other")})
        self.assertTrue(text.endswith("}\n"))
        self.assertEqual(list(json.loads(text)), ["a/x", "A/y", "b/z"])

    def test_keeps_non_ascii(self):
        self.assertIn("视频", cr.render({"视频/x": entry("resources")}))


class MainTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = self.tmp.name
        self.stars = [repo("a/x", "A video editor", topics=["video"]),
                      repo("b/y", "seeded", topics=[])]
        self.assignments = {"b/y": entry("resources", desc="seeded"),
                            "c/gone": entry("resources", source="rule"),
                            "d/unstarred": entry("other", source="manual")}
        self.write("stars.json", self.stars)
        self.write("categories.json", CATEGORIES)
        self.write("category_assignments.json", self.assignments)
        self.write("category_overrides.json", {})

    def tearDown(self):
        self.tmp.cleanup()

    def path(self, name):
        return os.path.join(self.dir, name)

    def write(self, name, data):
        with open(self.path(name), "w", encoding="utf-8") as f:
            f.write(data if isinstance(data, str) else json.dumps(data))

    def read(self, name):
        with open(self.path(name), encoding="utf-8") as f:
            return f.read()

    def run_main(self):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = cr.main(self.dir)
        return code, buf.getvalue()

    def test_writes_updates_and_prints_summary(self):
        code, out = self.run_main()
        self.assertEqual(code, 0)
        data = json.loads(self.read("category_assignments.json"))
        self.assertEqual(list(data), ["a/x", "b/y", "d/unstarred"])
        self.assertEqual(data["a/x"]["primary"], "creative/video")
        self.assertEqual(data["b/y"], self.assignments["b/y"])
        self.assertEqual(data["d/unstarred"], self.assignments["d/unstarred"])
        self.assertEqual(out.count("\n"), 1)
        for word in ("kept 1", "new-rule 1", "new-other 0", "dropped 1", "kept-unstarred 1"):
            self.assertIn(word, out)

    def test_output_is_deterministic_and_not_rewritten_when_unchanged(self):
        self.run_main()
        first = self.read("category_assignments.json")
        mtime = os.stat(self.path("category_assignments.json")).st_mtime_ns
        os.utime(self.path("category_assignments.json"), ns=(1, 1))
        self.run_main()
        self.assertEqual(self.read("category_assignments.json"), first)
        self.assertEqual(os.stat(self.path("category_assignments.json")).st_mtime_ns, 1)
        self.assertNotEqual(mtime, 1)

    def test_unknown_override_ids_warn_without_touching_overrides(self):
        self.write("category_overrides.json", {
            "a/x": {"primary": "gone/primary", "secondary": ["resources", "gone/secondary"]},
            "b/y": {"primary": "resources", "secondary": [["junk"]]},
        })
        before = self.read("category_overrides.json")
        code, out = self.run_main()
        self.assertEqual(code, 0)
        warnings = [ln for ln in out.splitlines() if ln.startswith("::warning title=categorize_repos::")]
        self.assertEqual(len(warnings), 3, out)
        self.assertTrue(any("a/x" in w and "gone/primary" in w for w in warnings), warnings)
        self.assertTrue(any("a/x" in w and "gone/secondary" in w for w in warnings), warnings)
        self.assertEqual(self.read("category_overrides.json"), before)

    def test_failed_write_keeps_old_file_and_leaves_no_temp_file(self):
        before = self.read("category_assignments.json")
        err = io.StringIO()
        with mock.patch.object(cr.os, "replace", side_effect=OSError("disk full")), \
                contextlib.redirect_stderr(err):
            code, out = self.run_main()
        self.assertEqual(code, 0)
        self.assertIn("::warning title=categorize_repos::", out)
        self.assertEqual(self.read("category_assignments.json"), before)
        self.assertEqual(sorted(os.listdir(self.dir)), sorted(
            ["stars.json", "categories.json", "category_assignments.json", "category_overrides.json"]))

    def test_missing_overrides_file_is_treated_as_empty(self):
        os.remove(self.path("category_overrides.json"))
        code, _ = self.run_main()
        self.assertEqual(code, 0)
        self.assertIn("a/x", json.loads(self.read("category_assignments.json")))

    def assert_untouched_on_bad_input(self, name, content):
        if content is None:
            os.remove(self.path(name))
        else:
            self.write(name, content)
        before = self.read("category_assignments.json") if os.path.exists(
            self.path("category_assignments.json")) else None
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            code, out = self.run_main()
        self.assertEqual(code, 0)
        self.assertIn("warning", err.getvalue().lower())
        # GitHub Actions annotation so the skip shows up in the run summary.
        self.assertIn("::warning title=categorize_repos::", out)
        after = self.read("category_assignments.json") if os.path.exists(
            self.path("category_assignments.json")) else None
        self.assertEqual(after, before)

    def test_malformed_categories_changes_nothing(self):
        self.assert_untouched_on_bad_input("categories.json", "{not json")

    def test_invalid_taxonomy_changes_nothing(self):
        self.assert_untouched_on_bad_input("categories.json", {"taxonomy": "x"})

    def test_missing_categories_changes_nothing(self):
        self.assert_untouched_on_bad_input("categories.json", None)

    def test_malformed_assignments_changes_nothing(self):
        self.assert_untouched_on_bad_input("category_assignments.json", "[1, 2")

    def test_non_object_assignments_changes_nothing(self):
        self.assert_untouched_on_bad_input("category_assignments.json", [1, 2])

    def test_missing_assignments_changes_nothing(self):
        self.assert_untouched_on_bad_input("category_assignments.json", None)

    def test_malformed_overrides_changes_nothing(self):
        self.assert_untouched_on_bad_input("category_overrides.json", "nope")

    def test_malformed_stars_changes_nothing(self):
        self.assert_untouched_on_bad_input("stars.json", {"not": "a list"})

    def test_empty_stars_changes_nothing(self):
        # An empty fetch must never wipe every assignment.
        self.assert_untouched_on_bad_input("stars.json", [])


class RealDataTest(unittest.TestCase):
    """The shipped data files must load and the seed must survive a run."""

    def test_shipped_categories_have_keywords_for_every_assignable_id(self):
        with open(os.path.join(ROOT, "data", "categories.json"), encoding="utf-8") as f:
            rules = cr.load_rules(json.load(f))
        for cat_id, keywords in rules.items():
            if cat_id != "other":
                self.assertTrue(keywords, cat_id)
                for kw in keywords:
                    self.assertEqual(kw, kw.lower(), kw)

    def test_seed_entries_survive_update_unchanged(self):
        def load(name):
            with open(os.path.join(ROOT, "data", name), encoding="utf-8") as f:
                return json.load(f)
        repos = load("stars.json")
        assignments = load("category_assignments.json")
        rules = cr.load_rules(load("categories.json"))
        out, _ = cr.update_assignments(repos, assignments, {}, rules)
        # stars.json is refreshed every sync run, so only the human judgment is pinned
        # (desc_hash may legitimately move with the description).
        for name, old in assignments.items():
            if old.get("source") == "seed" and name in out:
                for key in ("primary", "secondary", "source"):
                    self.assertEqual(out[name][key], old[key], name)


if __name__ == "__main__":
    unittest.main()
