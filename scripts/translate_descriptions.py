#!/usr/bin/env python3
"""Translate English repo descriptions into Chinese in data/stars.json.

Extracted from .github/workflows/fetch-stars.yml (second heredoc) with one fix:
the ``deep-translator`` pip dependency is replaced by a direct call to the
Google Translate free endpoint using only the standard library
(``urllib`` + ``json``). Descriptions that already contain Chinese, or repos
that already carry a ``description_zh``, are left untouched so the script is
idempotent and safe to re-run.

Run locally:
    python3 scripts/translate_descriptions.py
"""
import json
import os
import time
import urllib.parse
import urllib.request

TRANSLATE_URL = "https://translate.googleapis.com/translate_a/single"
USER_AGENT = "Stars-Dashboard/2.0"

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_FILE = os.path.join(ROOT, "data", "stars.json")


def contains_chinese(text):
    """True if ``text`` contains any CJK Unified Ideograph (U+4E00..U+9FFF)."""
    return any("一" <= ch <= "鿿" for ch in text)


def translate(text, opener=urllib.request.urlopen):
    """Translate ``text`` (English) to simplified Chinese.

    * Empty text -> "".
    * Already-Chinese text -> returned unchanged (no network call).
    * On any network/parse error -> the original text (graceful fallback).
    """
    if not text:
        return ""
    if contains_chinese(text):
        return text

    url = (
        TRANSLATE_URL
        + "?client=gtx&sl=en&tl=zh-CN&dt=t&q="
        + urllib.parse.quote(text)
    )
    try:
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with opener(req) as resp:
            data = json.loads(resp.read())
        return "".join(seg[0] for seg in data[0] if seg and seg[0])
    except Exception:
        return text


def translate_descriptions(repos, translate_fn=translate):
    """Set ``description_zh`` on each repo in ``repos`` (in place).

    * Repos with a non-empty ``description_zh`` are skipped (idempotent).
    * Empty descriptions -> "".
    * Already-Chinese descriptions are kept as-is.
    * Otherwise the description is passed to ``translate_fn``.
    """
    for repo in repos:
        if repo.get("description_zh"):
            continue
        desc = repo.get("description", "")
        if not desc:
            repo["description_zh"] = ""
        elif contains_chinese(desc):
            repo["description_zh"] = desc
        else:
            repo["description_zh"] = translate_fn(desc)
            time.sleep(0.3)  # be gentle to the free endpoint
    return repos


def process_file(path, translate_fn=translate):
    """Read ``path``, translate descriptions, write back. Returns the repos."""
    with open(path) as f:
        repos = json.load(f)
    translate_descriptions(repos, translate_fn=translate_fn)
    with open(path, "w") as f:
        json.dump(repos, f, indent=2, ensure_ascii=False)
    return repos


def main():
    count = process_file(DATA_FILE)
    print("Translated descriptions for {} repos -> {}".format(len(count), DATA_FILE))


if __name__ == "__main__":
    main()
