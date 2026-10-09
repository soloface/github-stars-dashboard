#!/usr/bin/env python3
"""Fetch GitHub starred repos for a user and dump them to data/stars.json.

Extracted from .github/workflows/fetch-stars.yml (first heredoc) with two fixes:
  * Authorization uses ``Bearer`` (OAuth 2.0) instead of the deprecated
    ``token`` prefix.
  * The output path resolves to ``<repo-root>/data/stars.json`` via ``__file__``
    so the script works whether it is run from the repo root
    (``python3 scripts/fetch_stars.py``) or from inside ``scripts/``.

Safety: a failed or empty fetch, or one returning fewer than half of the repos
already on file, exits non-zero WITHOUT touching the existing data file, so a
GitHub API hiccup can never publish an empty or truncated dashboard. The file
is written atomically (temp file in the same directory + ``os.replace``).
Translations (``description_zh``) from the previous file are carried over when
the description is unchanged, so the translate step only handles new text.

Uses only the Python standard library. Run locally:
    GH_TOKEN=<token> python3 scripts/fetch_stars.py
"""
import json
import os
import sys
import time
import urllib.request

GITHUB_USER = "soloface"
API_BASE = "https://api.github.com"
PER_PAGE = 100

# Repo root is the parent of the scripts/ directory this file lives in.
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_FILE = os.path.join(ROOT, "data", "stars.json")


def build_headers(token):
    """HTTP headers for the starred API, using Bearer auth.

    When ``token`` is empty we omit ``Authorization`` entirely rather than send
    a bare ``Bearer ``: GitHub answers 401 to that malformed header, which would
    break unauthenticated local runs against the public starred endpoint.
    """
    headers = {
        "Accept": "application/vnd.github.v3.star+json",
        "User-Agent": "Stars-Dashboard/2.0",
    }
    if token:
        headers["Authorization"] = "Bearer {}".format(token)
    return headers


def starred_url(page):
    """Build the starred-repos API URL for a given 1-based page."""
    return "{base}/users/{user}/starred?per_page={per_page}&page={page}".format(
        base=API_BASE, user=GITHUB_USER, per_page=PER_PAGE, page=page
    )


class FetchError(RuntimeError):
    """Raised when the starred list could not be fetched completely."""


def transform_repo(item):
    """Project one API item (``{repo, starred_at}``) onto the stars.json schema."""
    repo = item.get("repo") or item
    return {
        "full_name": repo.get("full_name", ""),
        "html_url": repo.get("html_url", ""),
        "description": repo.get("description") or "",
        "stargazers_count": repo.get("stargazers_count", 0),
        "forks_count": repo.get("forks_count", 0),
        "language": repo.get("language") or "",
        "starred_at": item.get("starred_at", ""),
        "created_at": repo.get("created_at", ""),
        "pushed_at": repo.get("pushed_at", ""),
        "topics": repo.get("topics") or [],
        "owner_avatar": (repo.get("owner") or {}).get("avatar_url", ""),
    }


def fetch_all_starred(token, urlopen=urllib.request.urlopen, _sleep=time.sleep):
    """Page through the starred list until an empty page or a missing next link.

    ``urlopen`` and ``_sleep`` are injected so the pagination logic is testable
    without hitting the network or sleeping.
    """
    headers = build_headers(token)
    all_items = []
    page = 1
    while True:
        req = urllib.request.Request(starred_url(page), headers=headers)
        try:
            with urlopen(req) as resp:
                data = json.loads(resp.read())
                if not data:
                    break
                all_items.extend(data)
                link = resp.headers.get("Link", "")
                if 'rel="next"' not in link:
                    break
                page += 1
                _sleep(0.5)
        except Exception as exc:
            raise FetchError("page {}: {}".format(page, exc)) from exc
    return all_items


def _has_cjk(text):
    return any("\u4e00" <= ch <= "\u9fff" for ch in text)


def carry_over_translations(repos, previous):
    """Copy ``description_zh`` from ``previous`` repos whose description is unchanged.

    A stored translation equal to an English description is the translate
    step's error fallback, so it is not carried over and gets retried.
    """
    old = {r.get("full_name"): r for r in previous if isinstance(r, dict)}
    for repo in repos:
        prev = old.get(repo["full_name"])
        if not prev or prev.get("description") != repo["description"]:
            continue
        zh = prev.get("description_zh")
        if zh and (zh != repo["description"] or _has_cjk(zh)):
            repo["description_zh"] = zh
    return repos


def _load_previous(path):
    try:
        with open(path) as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except (OSError, ValueError):
        return []


def main(data_file=DATA_FILE, fetch=fetch_all_starred):
    """Fetch and save. Returns a process exit code (1 = nothing written)."""
    token = os.environ.get("GH_TOKEN", "")
    try:
        items = fetch(token)
    except FetchError as exc:
        print("Fetch failed, keeping existing data: {}".format(exc))
        return 1
    if not items:
        print("Fetched 0 starred repos; refusing to overwrite existing data")
        return 1
    previous = _load_previous(data_file)
    if len(items) * 2 < len(previous):
        print("Fetched {} starred repos, fewer than half of the {} on file; "
              "refusing to overwrite existing data".format(len(items), len(previous)))
        return 1
    output = [transform_repo(item) for item in items]
    carry_over_translations(output, previous)
    print("Fetched {} starred repos".format(len(output)))

    os.makedirs(os.path.dirname(data_file), exist_ok=True)
    tmp_file = data_file + ".tmp"
    try:
        with open(tmp_file, "w") as f:
            json.dump(output, f, indent=2, ensure_ascii=False)
        os.replace(tmp_file, data_file)
    except BaseException:
        if os.path.exists(tmp_file):
            os.remove(tmp_file)
        raise
    print("Saved {} repos to {}".format(len(output), data_file))
    return 0


if __name__ == "__main__":
    sys.exit(main())
