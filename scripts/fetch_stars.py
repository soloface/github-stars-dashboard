#!/usr/bin/env python3
"""Fetch GitHub starred repos for a user and dump them to data/stars.json.

Extracted from .github/workflows/fetch-stars.yml (first heredoc) with two fixes:
  * Authorization uses ``Bearer`` (OAuth 2.0) instead of the deprecated
    ``token`` prefix.
  * The output path resolves to ``<repo-root>/data/stars.json`` via ``__file__``
    so the script works whether it is run from the repo root
    (``python3 scripts/fetch_stars.py``) or from inside ``scripts/``.

Uses only the Python standard library. Run locally:
    GH_TOKEN=<token> python3 scripts/fetch_stars.py
"""
import json
import os
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
        except Exception as exc:  # pragma: no cover - network path
            print("Error on page {}: {}".format(page, exc))
            break
    return all_items


def main():
    token = os.environ.get("GH_TOKEN", "")
    items = fetch_all_starred(token)
    output = [transform_repo(item) for item in items]
    print("Fetched {} starred repos".format(len(output)))

    os.makedirs(os.path.dirname(DATA_FILE), exist_ok=True)
    with open(DATA_FILE, "w") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
    print("Saved {} repos to {}".format(len(output), DATA_FILE))


if __name__ == "__main__":
    main()
