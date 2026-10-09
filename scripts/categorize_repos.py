#!/usr/bin/env python3
"""Assign each starred repo a category in data/category_assignments.json.

Runs on each sync run after scripts/translate_descriptions.py. Rule-based only (no LLM,
no network): every assignable category in data/categories.json carries a
``keywords`` list that is matched against the repo's topics, name and
description (English + ``description_zh``).

Per repo in data/stars.json:

1. Listed in data/category_overrides.json -> assignment left as-is (the
   frontend applies overrides itself).
2. Existing ``seed``/``manual`` assignment -> categories kept; only
   ``desc_hash`` is refreshed when the description changed. Unknown category
   ids are never "repaired" by the rules: unknown secondary ids are dropped,
   an unknown primary is kept and flagged ``needs_review`` (the frontend shows
   it as unassigned), and both print a warning.
3. Existing ``rule`` assignment -> kept while ``desc_hash`` is unchanged,
   re-classified otherwise.
4. No assignment (or a ``rule``/malformed one with unknown category ids) ->
   classified by the rules and flagged ``needs_review``; no confident match ->
   ``other``.

For repos that are no longer in stars.json, ``rule`` assignments are dropped
while ``seed``/``manual`` ones are kept, so a partial fetch cannot erase human
judgment. Overrides with unknown category ids print a warning; the overrides
file itself is never modified. The file is rewritten atomically (sorted,
deterministic) only when its content changes. Missing or malformed inputs
print a warning and exit 0 without touching anything, so this step can never
break the sync run. Warnings are also printed to stdout as GitHub Actions
``::warning`` annotations so they show up in the run summary.

Run locally:
    python3 scripts/categorize_repos.py
"""
import hashlib
import json
import os
import re
import sys
from collections import OrderedDict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(ROOT, "data")

OTHER = "other"
HUMAN_SOURCES = ("seed", "manual")
TOPIC_WEIGHT = 3       # keyword equals one of the repo topics
NAME_WEIGHT = 2        # keyword appears in the repo name
TEXT_WEIGHT = 1        # keyword appears in a description or inside a topic
THRESHOLD = 3          # minimum score for a primary category
MIN_LEAD = 1.5         # primary score must be >= MIN_LEAD x runner-up score
SECONDARY_RATIO = 0.5  # secondary score must be >= this x primary score
MAX_SECONDARY = 2


def desc_hash(description):
    """First 12 hex chars of sha256 over the UTF-8 description (None == "")."""
    return hashlib.sha256((description or "").encode("utf-8")).hexdigest()[:12]


def contains_chinese(text):
    """True if ``text`` contains any CJK Unified Ideograph (U+4E00..U+9FFF)."""
    return any("一" <= ch <= "鿿" for ch in text)


def load_rules(categories):
    """Map each assignable category id to its lowercase keyword list.

    Assignable ids are the children of each top-level category, or the
    top-level id itself when it has no children (e.g. ``resources``,
    ``other``). Order follows the taxonomy and is used to break score ties.
    Raises ValueError when the taxonomy is malformed.
    """
    taxonomy = categories.get("taxonomy") if isinstance(categories, dict) else None
    if not isinstance(taxonomy, list) or not taxonomy:
        raise ValueError("categories.json has no taxonomy list")
    rules = OrderedDict()
    for top in taxonomy:
        if not isinstance(top, dict) or not isinstance(top.get("id"), str):
            raise ValueError("taxonomy entry without an id: %r" % (top,))
        children = top.get("children") or []
        for cat in children or [top]:
            if not isinstance(cat, dict) or not isinstance(cat.get("id"), str):
                raise ValueError("category without an id under %r" % top["id"])
            keywords = cat.get("keywords", [])
            if not isinstance(keywords, list) or not all(isinstance(k, str) for k in keywords):
                raise ValueError("keywords of %r must be a list of strings" % cat["id"])
            rules[cat["id"]] = [k.strip().lower() for k in keywords if k.strip()]
    if OTHER not in rules:
        raise ValueError("taxonomy has no %r category" % OTHER)
    return rules


def _term_pattern(term):
    """Regex for an ASCII term: word-boundary-ish, with spaces, dots, hyphens
    and underscores interchangeable (``claude md`` ~ ``CLAUDE.md``) and an
    optional plural suffix."""
    parts = [re.escape(p) for p in re.split(r"[\s._-]+", term) if p]
    return re.compile(r"(?<![a-z0-9])" + r"[\s._-]+".join(parts) + r"(?:s|es)?(?![a-z0-9])")


def _name_text(full_name):
    """Repo name (without owner), lowercased, as written and split on camelCase.

    ``OpenClaw-Chat-Gateway`` -> ``"openclaw chat gateway open claw chat gateway"``
    so both ``openclaw`` and ``chat gateway`` can match.
    """
    name = full_name.split("/")[-1]
    split = re.sub(r"([a-z0-9])([A-Z])|([A-Z])([A-Z][a-z])", r"\1\3 \2\4", name)
    return re.sub(r"[\s_.-]+", " ", name + " " + split).lower()


def score(repo, rules):
    """Return ``{category_id: score}`` for categories with a positive score.

    Each keyword adds up its evidence across fields: an exact topic match
    (TOPIC_WEIGHT, or TEXT_WEIGHT for a partial one such as ``plugin`` in
    ``claude-code-plugin``), the repo name (NAME_WEIGHT) and the description
    or ``description_zh`` (TEXT_WEIGHT). ASCII terms match on word
    boundaries; CJK terms match as substrings.
    """
    topics = [str(t).lower() for t in repo.get("topics") or []]
    name = _name_text(repo.get("full_name", ""))
    text = " ".join([repo.get("description") or "", repo.get("description_zh") or ""]).lower()
    scores = {}
    for cat_id, keywords in rules.items():
        total = 0
        for term in keywords:
            if contains_chinese(term):
                total += NAME_WEIGHT if term in name else 0
                total += TEXT_WEIGHT if term in text else 0
                continue
            pattern = _term_pattern(term)
            if any(pattern.fullmatch(t) for t in topics):
                total += TOPIC_WEIGHT
            elif any(pattern.search(t) for t in topics):
                total += TEXT_WEIGHT
            total += NAME_WEIGHT if pattern.search(name) else 0
            total += TEXT_WEIGHT if pattern.search(text) else 0
        if total:
            scores[cat_id] = total
    return scores


def classify(repo, rules, threshold=THRESHOLD):
    """Pick ``{primary, secondary}`` for ``repo`` from the keyword scores.

    The best category must reach ``threshold`` and clearly beat the runner-up
    (at least MIN_LEAD times its score); an ambiguous or weak match goes to
    ``other`` rather than to a confident-looking wrong guess. Up to
    MAX_SECONDARY further categories that reach ``threshold`` and
    SECONDARY_RATIO of the primary score become secondary.
    """
    order = list(rules)
    scores = score(repo, rules)
    ranked = sorted(scores, key=lambda c: (-scores[c], order.index(c)))
    if not ranked or scores[ranked[0]] < threshold:
        return {"primary": OTHER, "secondary": []}
    primary = ranked[0]
    if len(ranked) > 1 and scores[primary] < MIN_LEAD * scores[ranked[1]]:
        return {"primary": OTHER, "secondary": []}
    floor = max(threshold, SECONDARY_RATIO * scores[primary])
    secondary = [c for c in ranked[1:] if c != OTHER and scores[c] >= floor]
    return {"primary": primary, "secondary": secondary[:MAX_SECONDARY]}


def warn(message):
    """Print ``message`` as a GitHub Actions warning annotation (stdout)."""
    message = str(message).replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")
    print("::warning title=categorize_repos::%s" % message)


def _known(cat_id, valid_ids):
    """True if ``cat_id`` is a string in ``valid_ids`` (never raises on junk)."""
    return isinstance(cat_id, str) and cat_id in valid_ids


def _is_valid(entry, valid_ids):
    """True if ``entry`` is a well-formed assignment using only known ids."""
    return (
        isinstance(entry, dict)
        and _known(entry.get("primary"), valid_ids)
        and isinstance(entry.get("secondary"), list)
        and all(_known(c, valid_ids) for c in entry["secondary"])
        and isinstance(entry.get("source"), str)
        and isinstance(entry.get("desc_hash"), str)
    )


def update_assignments(repos, assignments, overrides, rules, classify_fn=classify):
    """Return ``(new_assignments, stats)`` without mutating the inputs.

    ``stats`` counts ``kept``, ``new_rule``, ``new_other``, ``dropped`` (rule
    entries of repos no longer starred) and ``unstarred`` (human entries of
    repos no longer starred, kept). Unknown ids in human entries are warned
    about on stdout.
    """
    out = {}
    stats = {"kept": 0, "new_rule": 0, "new_other": 0, "dropped": 0, "unstarred": 0}
    for repo in repos:
        name = repo["full_name"]
        current = desc_hash(repo.get("description"))
        old = assignments.get(name)
        if name in overrides:
            if old is not None:
                out[name] = old
                stats["kept"] += 1
            continue
        if _is_valid(old, rules):
            if old["source"] in HUMAN_SOURCES:
                out[name] = dict(old, desc_hash=current)
                stats["kept"] += 1
                continue
            if old["desc_hash"] == current:
                out[name] = old
                stats["kept"] += 1
                continue
        elif (isinstance(old, dict) and old.get("source") in HUMAN_SOURCES
              and isinstance(old.get("primary"), str)):
            # Human judgment with stale ids: keep it, never re-classify.
            secondary = old.get("secondary") if isinstance(old.get("secondary"), list) else []
            for cat_id in secondary:
                if not _known(cat_id, rules):
                    warn("%s: dropped unknown or non-assignable secondary category id %r"
                         % (name, cat_id))
            fixed = dict(old, secondary=[c for c in secondary if _known(c, rules)],
                         desc_hash=current)
            if old["primary"] not in rules:
                warn("%s: unknown or non-assignable primary category id %r, "
                     "kept and flagged needs_review" % (name, old["primary"]))
                fixed["needs_review"] = True
            out[name] = fixed
            stats["kept"] += 1
            continue
        result = classify_fn(repo, rules)
        out[name] = {
            "primary": result["primary"],
            "secondary": list(result["secondary"]),
            "source": "rule",
            "desc_hash": current,
            "needs_review": True,
        }
        stats["new_other" if result["primary"] == OTHER else "new_rule"] += 1
    for name, old in assignments.items():
        if name in out:
            continue
        if isinstance(old, dict) and old.get("source") in HUMAN_SOURCES:
            out[name] = old
            stats["unstarred"] += 1
        else:
            stats["dropped"] += 1
    return out, stats


def render(assignments):
    """Serialize deterministically: case-insensitive key order, trailing newline."""
    ordered = OrderedDict(
        (k, assignments[k]) for k in sorted(assignments, key=lambda k: (k.lower(), k))
    )
    return json.dumps(ordered, ensure_ascii=False, indent=2) + "\n"


def _load(path, kind, default=None):
    """Read JSON at ``path``; return ``default`` if missing and a default is given.

    Raises ValueError (with a readable message) when the content is unusable.
    """
    if default is not None and not os.path.exists(path):
        return default
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError) as exc:
        raise ValueError("cannot read %s: %s" % (path, exc))
    if not isinstance(data, kind):
        raise ValueError("%s must contain a JSON %s" % (path, kind.__name__))
    return data


def main(data_dir=DATA_DIR):
    """Update ``category_assignments.json`` in ``data_dir``. Always returns 0."""
    out_path = os.path.join(data_dir, "category_assignments.json")
    try:
        rules = load_rules(_load(os.path.join(data_dir, "categories.json"), dict))
        assignments = _load(out_path, dict)
        overrides = _load(os.path.join(data_dir, "category_overrides.json"), dict, {})
        repos = _load(os.path.join(data_dir, "stars.json"), list)
        if not repos:
            raise ValueError("stars.json is empty")
        for name, override in overrides.items():
            ids = [override.get("primary")] if isinstance(override, dict) else [None]
            if isinstance(override, dict) and isinstance(override.get("secondary"), list):
                ids += override["secondary"]
            for cat_id in ids:
                if not _known(cat_id, rules):
                    warn("override %s: unknown or non-assignable category id %r" % (name, cat_id))
        new, stats = update_assignments(repos, assignments, overrides, rules)
        text = render(new)
        with open(out_path, encoding="utf-8") as f:
            changed = f.read() != text
        if changed:
            tmp_path = out_path + ".tmp"
            try:
                with open(tmp_path, "w", encoding="utf-8") as f:
                    f.write(text)
                os.replace(tmp_path, out_path)
            except BaseException:
                if os.path.exists(tmp_path):
                    os.remove(tmp_path)
                raise
    except Exception as exc:  # never break the sync run
        message = "categorize_repos skipped, nothing changed: %s" % exc
        print("warning: %s" % message, file=sys.stderr)
        warn(message)
        return 0
    print("Categories: kept {kept}, new-rule {new_rule}, new-other {new_other}, "
          "dropped {dropped}, kept-unstarred {unstarred} -> {path}{note}".format(
              path=out_path, note="" if changed else " (unchanged)", **stats))
    return 0


if __name__ == "__main__":
    sys.exit(main())
