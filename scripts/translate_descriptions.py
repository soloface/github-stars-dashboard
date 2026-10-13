#!/usr/bin/env python3
"""Translate repo descriptions into Chinese in data/stars.json.

A description is handled in this order:

* Empty -> ``description_zh`` is ``""``.
* Mostly Chinese (``chinese_ratio`` >= ``ZH_RATIO``, which is 0.5) -> copied
  as-is, with no network call. Each Han ideograph (U+4E00–U+9FFF and
  U+3400–U+4DBF) is one unit, and each ASCII letter/digit word
  (``[A-Za-z0-9]+``, so ``Opus5.5`` is ``Opus5`` and ``5``) is one unit.
  Punctuation, whitespace, emoji, and other symbols are ignored. The ratio
  is Han units over Han units plus words, or 0.0 when there are no units.
  ``contains_chinese`` is still available but is not used to decide.
* Bilingual text -> ``extract_chinese_segment`` keeps one continuous Chinese
  run when that run is reliable (``looks_chinese`` and at least four
  ideographs). A Chinese clause that names English products
  ("面向 Gemini、…的增强套件", a parenthetical "基于JavaScript/…的组件") still
  counts. A long English sentence joined only by a space
  ("…comfortable 一个CodexApp…", "使用Deno… Use Deno…") is split off.
  Alternating Chinese and English, or a Chinese run shorter than four
  ideographs ("English / 中文.", "Lark/飞书"), is not extracted.
* Otherwise the text is translated. On failure (exception, empty result, the
  original text, or a result with no Chinese) ``description_zh`` is left
  untouched, so the next run retries. ``translate`` returns ``None`` on
  failure instead of echoing the source. The pause between requests is
  ``_sleep`` (``time.sleep``), and it runs only when a translation was
  actually attempted.

Entries that already have a non-empty ``description_zh`` are skipped. Pass
``--recheck-mixed`` to also redo entries whose stored value is a copy of a
description that is not mostly Chinese (the old "any Han character counts as
done" path). Real translations (``description_zh`` differs from
``description``) and mostly-Chinese originals are left alone.

``--only a/b,c/d`` limits the run to those ``full_name`` values.
``--dry-run`` prints each planned change (full_name, old value, new value,
source ``extracted`` or ``needs-translation``) and does not translate or
write the file.

Only the standard library is used. Run::

    python3 scripts/translate_descriptions.py
    python3 scripts/translate_descriptions.py --recheck-mixed --dry-run
"""
import argparse
import json
import os
import re
import time
import unicodedata
import urllib.parse
import urllib.request

TRANSLATE_URL = "https://translate.googleapis.com/translate_a/single"
USER_AGENT = "Stars-Dashboard/2.0"

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_FILE = os.path.join(ROOT, "data", "stars.json")

# Han units / (Han units + ASCII words). At or above this, the description
# is already Chinese.
ZH_RATIO = 0.5
# A glued-on English sentence has to be at least this long before we treat
# the boundary as a real language switch (and before a segment is "too English"
# to use the relaxed Chinese test).
_ASCII_SIDE_MIN = 20
# After ASCII words are removed, this fraction of the remainder must be
# ideographs or Chinese punctuation.
_RELAXED_RATIO = 0.8
_RELAXED_MIN_HANZI = 4

# Updated by translate_descriptions(); callers that only need the repos can
# ignore it. Keys: updated, failed, unchanged.
stats = {"updated": 0, "failed": 0, "unchanged": 0}

# Replaced in tests so the suite does not actually pause.
_sleep = time.sleep

_ASCII_WORD_RE = re.compile(r"[A-Za-z0-9]+")
# Group 1: split after. Group 2: separator span. Group 3: split before.
_SPLIT_RE = re.compile(
    r"(\. |! |\? |[。！？；])"
    r"|((?: / )|(?: · )|(?: \| )|(?: - )|·|—)"
    r"|([（(])"
)
_URL_RE = re.compile(r"https?://|www\.", re.IGNORECASE)


def _is_hanzi(ch):
    code = ord(ch)
    return (0x4E00 <= code <= 0x9FFF) or (0x3400 <= code <= 0x4DBF)


def hanzi_count(text):
    """Number of CJK ideographs, including Extension A."""
    return sum(1 for ch in text if _is_hanzi(ch))


def chinese_ratio(text):
    """Return the Chinese share of ``text`` as Han units over all units.

    Each Han ideograph in U+4E00–U+9FFF or U+3400–U+4DBF counts as one unit.
    Each maximal ASCII letter/digit word (``[A-Za-z0-9]+``) counts as one
    unit, so ``Opus5.5`` is two words (``Opus5`` and ``5``). Punctuation,
    whitespace, emoji, and other symbols do not count. The ratio is
    ``hanzi / (hanzi + words)``. Text with no units is ``0.0``.

    ``is_mostly_chinese`` is this ratio ``>= ZH_RATIO`` (0.5).
    """
    if not text:
        return 0.0
    hanzi = hanzi_count(text)
    words = len(_ASCII_WORD_RE.findall(text))
    total = hanzi + words
    if total == 0:
        return 0.0
    return hanzi / total


def is_mostly_chinese(text):
    """True when ``chinese_ratio(text) >= ZH_RATIO``."""
    return chinese_ratio(text) >= ZH_RATIO


def contains_chinese(text):
    """True if ``text`` contains any CJK Unified Ideograph (U+4E00..U+9FFF).

    Decision logic uses ``is_mostly_chinese`` / ``looks_chinese`` instead.
    This helper stays for callers and tests that only need "any ideograph".
    """
    return any("一" <= ch <= "鿿" for ch in text)


def _is_cjk_punct(ch):
    """Chinese punctuation, not the em dash / middle dot used in English prose."""
    code = ord(ch)
    if 0x3000 <= code <= 0x303F:
        return True
    if 0xFF01 <= code <= 0xFF0F or 0xFF1A <= code <= 0xFF20:
        return True
    if 0xFF3B <= code <= 0xFF40 or 0xFF5B <= code <= 0xFF65:
        return True
    return ch == "…"


def _is_emoji(ch):
    if unicodedata.category(ch) == "So":
        return True
    return 0x1F000 <= ord(ch) <= 0x1FAFF


def _relaxed_zh(text):
    """True when dropping ASCII words leaves a Chinese remainder.

    Used for clauses like "面向 Gemini、AI Studio、…的增强套件", where the
    ideograph ratio is under 50% but the skeleton is Chinese punctuation
    and ideographs. Requires at least four ideographs and a remainder that
    is >= 80% ideograph or Chinese punctuation.
    """
    if hanzi_count(text) < _RELAXED_MIN_HANZI:
        return False
    stripped = _ASCII_WORD_RE.sub("", text)
    non_ws = [ch for ch in stripped if not ch.isspace()]
    if not non_ws:
        return False
    good = sum(1 for ch in non_ws if _is_hanzi(ch) or _is_cjk_punct(ch))
    return good / len(non_ws) >= _RELAXED_RATIO


def looks_chinese(text):
    """Mostly Chinese, or Chinese once embedded ASCII words are ignored."""
    if not text:
        return False
    if is_mostly_chinese(text):
        return True
    return _relaxed_zh(text)


def _has_long_ascii_clause(text, limit=_ASCII_SIDE_MIN):
    """True when a run of non-Chinese text is long enough to be a sentence."""
    run = 0
    has_letter = False
    best = 0
    best_letter = False
    for ch in text:
        if _is_hanzi(ch) or _is_cjk_punct(ch):
            if run > best:
                best, best_letter = run, has_letter
            run = 0
            has_letter = False
        else:
            run += 1
            if ch.isascii() and ch.isalpha():
                has_letter = True
    if run > best:
        best, best_letter = run, has_letter
    return best >= limit and best_letter


def _contains_cjk_punct(text):
    return any(_is_cjk_punct(ch) for ch in text)


def _is_ascii_alnum(ch):
    return ch.isascii() and ch.isalnum()


def _en_zh_boundary(text):
    """Index where a leading English sentence gives way to Chinese.

    The index sits on the first ideograph. If that ideograph is glued to an
    ASCII word ("CodexApp中文"), the index moves back to the start of the word
    so the word stays with the Chinese side. No move when Chinese comes first
    ("一个CodexApp", "让 AI Agent").
    """
    idx = next((i for i, ch in enumerate(text) if _is_hanzi(ch)), None)
    if idx is None or text[:idx].strip() == "":
        return None
    pos = idx
    if pos > 0 and _is_ascii_alnum(text[pos - 1]):
        while pos > 0 and _is_ascii_alnum(text[pos - 1]):
            pos -= 1
    return pos


def _zh_en_boundary(text):
    """Index just after the last ideograph or Chinese punctuation mark."""
    last = None
    for i, ch in enumerate(text):
        if _is_hanzi(ch) or _is_cjk_punct(ch):
            last = i
    if last is None:
        return None
    return last + 1


def _split_cuts(text):
    cuts = {0, len(text)}
    for match in _SPLIT_RE.finditer(text):
        if match.group(3):
            cuts.add(match.start())
        elif match.group(2):
            cuts.add(match.start())
            cuts.add(match.end())
        else:
            cuts.add(match.end())
    for i, ch in enumerate(text):
        if _is_emoji(ch):
            cuts.add(i)
            cuts.add(i + 1)
    return sorted(cuts)


# Edge characters stripped from a fragment. Chinese sentence enders stay.
_EDGE_KEEP = set("。！？")


def _is_edge_junk(ch):
    if ch in _EDGE_KEEP:
        return False
    if ch.isspace():
        return True
    if ch in "/·|—-–～()（）[]【】":
        return True
    if _is_emoji(ch):
        return True
    return unicodedata.category(ch) in ("Cf", "Mn", "Me")


def _clean_fragment(text):
    chars = list(text)
    while chars and _is_edge_junk(chars[0]):
        chars.pop(0)
    while chars and _is_edge_junk(chars[-1]):
        chars.pop()
    return "".join(chars).strip()


def _is_neutral(cleaned):
    """Symbols, digits, or a URL: no language, so it does not break a run."""
    if not cleaned:
        return True
    has_hanzi = False
    has_letter = False
    for ch in cleaned:
        if _is_hanzi(ch):
            has_hanzi = True
        elif unicodedata.category(ch).startswith("L"):
            has_letter = True
    if not has_hanzi and not has_letter:
        return True
    if not has_hanzi and _URL_RE.search(cleaned):
        return True
    return False


def _is_parenthetical(raw):
    stripped = raw.strip()
    return stripped.startswith("(") or stripped.startswith("（")


def _label_segment(raw):
    cleaned = _clean_fragment(raw)
    if _is_neutral(cleaned):
        return "neutral"
    # A long ASCII run means an English sentence was not split off yet, even
    # when the unit ratio is already >= ZH_RATIO. The boundary fallback
    # splits that blob; labeling it "zh" here would hide the Chinese run.
    if is_mostly_chinese(cleaned) and not _has_long_ascii_clause(cleaned):
        return "zh"
    # Relaxed labeling is for a Chinese clause with English tokens in it, not
    # for a full English sentence that happens to contain one Chinese comma.
    # Parentheticals ("(基于JavaScript/…的组件)") are clauses even without
    # enumeration punctuation. A long ASCII run means the English side was
    # not split off yet; the boundary fallback handles that.
    if _relaxed_zh(cleaned) and (
        _is_parenthetical(raw)
        or (_contains_cjk_punct(cleaned) and not _has_long_ascii_clause(cleaned))
    ):
        return "zh"
    return "en"


def _strip_edge_parens(text):
    """Drop a wrapping pair, or one unmatched parenthesis at either end."""
    pairs = {"(": ")", "（": "）"}
    close_to_open = {")": "(", "）": "（"}

    def wraps(value):
        if len(value) < 2 or value[0] not in pairs:
            return False
        want = pairs[value[0]]
        depth = 0
        for i, ch in enumerate(value):
            if ch == value[0]:
                depth += 1
            elif ch == want:
                depth -= 1
                if depth == 0:
                    return i == len(value) - 1
        return False

    value = text.strip()
    while wraps(value):
        value = value[1:-1].strip()
    if value[:1] in pairs:
        want = pairs[value[0]]
        depth = 0
        matched = False
        for ch in value:
            if ch == value[0]:
                depth += 1
            elif ch == want:
                depth -= 1
                if depth == 0:
                    matched = True
                    break
        if not matched:
            value = value[1:].strip()
    if value[-1:] in close_to_open:
        open_ch = close_to_open[value[-1]]
        close_ch = value[-1]
        depth = 0
        balanced = False
        for i, ch in enumerate(value):
            if ch == open_ch:
                depth += 1
            elif ch == close_ch:
                if depth == 0:
                    break
                depth -= 1
                if depth == 0 and i == len(value) - 1:
                    balanced = True
        if not balanced:
            value = value[:-1].strip()
    return value


def _clean_result(text):
    value = text.strip()
    changed = True
    while value and changed:
        changed = False
        if _is_edge_junk(value[0]) and value[0] not in "()（）":
            value = value[1:]
            changed = True
        if value and _is_edge_junk(value[-1]) and value[-1] not in "()（）":
            value = value[:-1]
            changed = True
        stripped = value.strip()
        if stripped != value:
            value = stripped
            changed = True
    return _strip_edge_parens(value).strip()


def _acceptable_zh(text):
    return bool(text) and looks_chinese(text) and hanzi_count(text) >= _RELAXED_MIN_HANZI


def _boundary_fallback(text):
    """Split a two-language string that has no interior separator.

    English then Chinese: prefix has no ideographs and is at least 20
    characters, suffix is mostly Chinese. Chinese then English: the mirror.
    """
    pos = _en_zh_boundary(text)
    if (
        pos is not None
        and chinese_ratio(text[:pos]) == 0
        and len(text[:pos]) >= _ASCII_SIDE_MIN
        and is_mostly_chinese(text[pos:])
    ):
        return _clean_result(text[pos:])
    end = _zh_en_boundary(text)
    if (
        end is not None
        and is_mostly_chinese(text[:end])
        and chinese_ratio(text[end:]) == 0
        and len(text[end:]) >= _ASCII_SIDE_MIN
    ):
        return _clean_result(text[:end])
    return None


def extract_chinese_segment(text):
    """Return the Chinese run of a bilingual description, or None.

    Segments are cut on sentence-ending punctuation, on `` / `` `` · `` `` | ``
    `` - `` ``—`` and parentheses, and around emoji. Each segment is Chinese,
    English, or neutral (symbols, digits, URLs). Neutral segments do not break
    a run. All Chinese segments must form one contiguous run, and at least one
    English segment must exist; otherwise the text is not a single bilingual
    pair (for example Chinese and English alternating). The returned slice is
    the original substring covering that run, trimmed, and it must look
    Chinese and contain at least four ideographs.
    """
    if not text:
        return None
    cuts = _split_cuts(text)
    spans = [
        (cuts[i], cuts[i + 1])
        for i in range(len(cuts) - 1)
        if cuts[i] != cuts[i + 1]
    ]
    labeled = []
    for start, end in spans:
        raw = text[start:end]
        labeled.append((_label_segment(raw), start, end))
    zh_at = [i for i, item in enumerate(labeled) if item[0] == "zh"]
    en_at = [i for i, item in enumerate(labeled) if item[0] == "en"]
    if zh_at and en_at:
        first, last = zh_at[0], zh_at[-1]
        if any(labeled[i][0] == "en" for i in range(first, last + 1)):
            return None
        result = _clean_result(text[labeled[first][1]:labeled[last][2]])
        if _acceptable_zh(result):
            return result
        return None
    if not zh_at:
        fallback = _boundary_fallback(text)
        if _acceptable_zh(fallback):
            return fallback
    return None


def translate(text, opener=urllib.request.urlopen):
    """Translate ``text`` (English) to simplified Chinese.

    * Empty text -> "".
    * Mostly-Chinese text -> returned unchanged, no network call.
    * On any network or parse error -> None (not the original text).
    """
    if not text:
        return ""
    if is_mostly_chinese(text):
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
        translated = "".join(seg[0] for seg in data[0] if seg and seg[0])
    except Exception:
        return None
    return translated or None


def resolve_zh(desc, translate_fn):
    """Return ``(zh, ok)`` for one description.

    ``ok`` is False when a translation was required and failed. ``zh`` is then
    None and the caller must not write ``description_zh``.
    """
    if not desc:
        return ("", True)
    if is_mostly_chinese(desc):
        return (desc, True)
    segment = extract_chinese_segment(desc)
    if segment:
        return (segment, True)
    try:
        result = translate_fn(desc)
    except Exception:
        return (None, False)
    if not result or result == desc or chinese_ratio(result) == 0:
        return (None, False)
    return (result, True)


def _selected(repo, recheck_mixed, only_set):
    if only_set is not None and repo.get("full_name") not in only_set:
        return False
    existing = repo.get("description_zh")
    if not existing:
        return True
    desc = repo.get("description") or ""
    # Only the old "copy the mixed/English description" fallback is reopened.
    return bool(recheck_mixed and existing == desc and not is_mostly_chinese(desc))


def translate_descriptions(repos, translate_fn=translate, recheck_mixed=False, only=None):
    """Set ``description_zh`` on each repo in ``repos`` (in place).

    * Non-empty ``description_zh`` is kept, unless ``recheck_mixed`` and the
      stored value is a copy of a description that is not mostly Chinese.
    * ``only`` is an optional collection of ``full_name`` values; anything
      else is left untouched.
    * A failed translation does not create or replace ``description_zh``.
    * ``_sleep(0.3)`` runs only after ``translate_fn`` was actually called.

    Returns ``repos``. Counts for this call are in the module-level ``stats``
    dict (``updated``, ``failed``, ``unchanged``).
    """
    stats["updated"] = 0
    stats["failed"] = 0
    stats["unchanged"] = 0
    only_set = None if only is None else set(only)
    for repo in repos:
        if not _selected(repo, recheck_mixed, only_set):
            stats["unchanged"] += 1
            continue
        desc = repo.get("description") or ""
        had_field = "description_zh" in repo
        called = {"n": 0}

        def wrapped(text, _bucket=called):
            _bucket["n"] += 1
            return translate_fn(text)

        zh, ok = resolve_zh(desc, wrapped)
        if called["n"]:
            _sleep(0.3)
        if not ok:
            stats["failed"] += 1
            continue
        if had_field and repo.get("description_zh") == zh:
            stats["unchanged"] += 1
            continue
        repo["description_zh"] = zh
        stats["updated"] += 1
    return repos


def _dump_like(repos, trailing_newline):
    text = json.dumps(repos, indent=2, ensure_ascii=False)
    if trailing_newline:
        text += "\n"
    return text


def process_file(path, translate_fn=translate, recheck_mixed=False, only=None):
    """Read ``path``, translate descriptions, write back. Returns the repos.

    The file is opened as UTF-8. It is rewritten only when some entry changed,
    using ``json.dump``'s ``indent=2, ensure_ascii=False`` layout. A trailing
    newline is kept if and only if the file already ended with one.
    """
    with open(path, encoding="utf-8") as handle:
        raw = handle.read()
    repos = json.loads(raw)
    translate_descriptions(
        repos, translate_fn=translate_fn, recheck_mixed=recheck_mixed, only=only
    )
    if stats["updated"] == 0:
        return repos
    text = _dump_like(repos, raw.endswith("\n"))
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)
    return repos


def _plan(desc):
    """Decide a dry-run outcome without calling the network.

    Returns ``(new_value, source)``. ``new_value`` is None and source is
    ``needs-translation`` when a translator would have to run.
    """
    if not desc:
        return "", "as-is"
    if is_mostly_chinese(desc):
        return desc, "as-is"
    segment = extract_chinese_segment(desc)
    if segment:
        return segment, "extracted"
    return None, "needs-translation"


def _print_plan(full_name, old, new, source):
    old_text = "(missing)" if old is None else old
    new_text = "(needs-translation)" if new is None else new
    print("source: {}".format(source))
    print("full_name: {}".format(full_name))
    print("old: {}".format(old_text))
    print("new: {}".format(new_text))
    print()


def dry_run(path, recheck_mixed=False, only=None):
    """Print planned changes. Does not translate and does not write ``path``."""
    with open(path, encoding="utf-8") as handle:
        repos = json.load(handle)
    only_set = None if only is None else set(only)
    extracted = 0
    needs = 0
    for repo in repos:
        if not _selected(repo, recheck_mixed, only_set):
            continue
        desc = repo.get("description") or ""
        new, source = _plan(desc)
        old = repo.get("description_zh") if "description_zh" in repo else None
        if source != "needs-translation" and old == new:
            continue
        if source == "needs-translation":
            needs += 1
        elif source == "extracted":
            extracted += 1
        _print_plan(repo.get("full_name", ""), old, new, source)
    print(
        "dry-run: extracted={} needs-translation={} (file not written)".format(
            extracted, needs
        )
    )


def main(argv=None):
    """CLI entry. No arguments matches the CI run (fill in missing translations)."""
    parser = argparse.ArgumentParser(
        description="Fill description_zh in data/stars.json."
    )
    parser.add_argument(
        "--recheck-mixed",
        action="store_true",
        help=(
            "Also redo entries whose description_zh is a copy of a description "
            "that is not mostly Chinese"
        ),
    )
    parser.add_argument(
        "--only",
        default=None,
        help='Comma-separated full_name values to process, e.g. "a/b,c/d"',
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print planned changes; do not translate and do not write the file",
    )
    args = parser.parse_args(argv)
    only = None
    if args.only is not None:
        only = {part.strip() for part in args.only.split(",") if part.strip()}
    if args.dry_run:
        dry_run(DATA_FILE, recheck_mixed=args.recheck_mixed, only=only)
        return
    repos = process_file(
        DATA_FILE, recheck_mixed=args.recheck_mixed, only=only
    )
    print(
        "updated={updated} failed={failed} unchanged={unchanged} ({n} repos) -> {path}".format(
            n=len(repos), path=DATA_FILE, **stats
        )
    )


if __name__ == "__main__":
    main()
