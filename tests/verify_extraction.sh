#!/usr/bin/env bash
# =============================================================================
# SOL-79 — Characterization test for CSS/JS extraction (pure refactor).
#
# Guarantees the extraction is behavior-preserving:
#   1. css/style.css is BYTE-IDENTICAL to the original inline <style> content
#   2. js/app.js   is BYTE-IDENTICAL to the original inline <script> content
#   3. index.html references both external files, has NO inline <style>/<script>
#      blocks, and preserves the full DOM skeleton + meta tags
#
# Golden source: index.html as committed at git HEAD (working copy verified
# clean before refactor — HEAD is the authoritative pre-refactor reference).
# =============================================================================
set -uo pipefail

REPO="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO" || exit 2

pass=0; fail=0
ok()  { echo "  PASS  $1"; pass=$((pass + 1)); }
err() { echo "  FAIL  $1"; fail=$((fail + 1)); }

ORIG="$(mktemp)"
trap 'rm -f "$ORIG" /tmp/__sol79_css /tmp/__sol79_js' EXIT
git show HEAD:index.html > "$ORIG" 2>/dev/null || { echo "FATAL: cannot read git HEAD:index.html"; exit 2; }

echo "== SOL-79 extraction characterization =="

# --- TEST 1: css/style.css byte-identical to original inline <style> ----------
if [ -s css/style.css ]; then
  # Inline <style> body = lines strictly between '<style>' and '</style>' tags.
  awk '/^<style>$/{f=1;next} /^<\/style>$/{f=0} f' "$ORIG" > /tmp/__sol79_css
  if diff -q /tmp/__sol79_css css/style.css >/dev/null; then
    ok "css/style.css byte-identical to inline <style> ($(wc -l < css/style.css | tr -d ' ') lines)"
  else
    err "css/style.css differs from original inline <style>"; diff /tmp/__sol79_css css/style.css | head -30
  fi
else
  err "css/style.css missing or empty"
fi

# --- TEST 2: js/app.js byte-identical to original inline <script> -------------
if [ -s js/app.js ]; then
  awk '/^<script>$/{f=1;next} /^<\/script>$/{f=0} f' "$ORIG" > /tmp/__sol79_js
  if diff -q /tmp/__sol79_js js/app.js >/dev/null; then
    ok "js/app.js byte-identical to inline <script> ($(wc -l < js/app.js | tr -d ' ') lines)"
  else
    err "js/app.js differs from original inline <script>"; diff /tmp/__sol79_js js/app.js | head -30
  fi
else
  err "js/app.js missing or empty"
fi

# --- TEST 3: index.html references externals, no inline blocks, skeleton ------
if [ -s index.html ]; then
  grep -q '<link rel="stylesheet" href="css/style.css">' index.html \
    && ok "index.html links css/style.css" \
    || err "missing <link rel=stylesheet href=css/style.css>"
  grep -q '<script src="js/app.js" defer></script>' index.html \
    && ok "index.html loads js/app.js (defer)" \
    || err "missing <script src=js/app.js defer>"
  if grep -qE '^<style>$|^<script>$' index.html; then
    err "inline <style>/<script> block still present"
  else
    ok "no inline <style>/<script> blocks remain"
  fi

  dom_ok=1
  for id in repoGrid pagination statsPanel searchInput resultsBadge langFilters filterAll syncTime totalCount langDots; do
    grep -q "id=\"$id\"" index.html || { err "DOM id=$id missing"; dom_ok=0; }
  done
  for cls in container topbar stats-panel controls repo-grid pagination footer spinner; do
    grep -q "class=\"$cls\"" index.html || { err "DOM class=$cls missing"; dom_ok=0; }
  done
  [ $dom_ok -eq 1 ] && ok "DOM skeleton (all ids + classes) preserved"

  grep -q '<meta charset="UTF-8">' index.html && ok "<meta charset> preserved" || err "charset meta missing"
  grep -q 'name="viewport"'      index.html && ok "viewport meta preserved"   || err "viewport meta missing"
  grep -q '<title>'              index.html && ok "<title> preserved"          || err "<title> missing"
  echo "  info  index.html = $(wc -l < index.html | tr -d ' ') lines"
else
  err "index.html missing or empty"
fi

echo "== result: $pass passed, $fail failed =="
[ "$fail" -eq 0 ]
