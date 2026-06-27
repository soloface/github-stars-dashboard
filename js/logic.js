// ============================================================
// Pure frontend logic for github-stars-dashboard (Phase 3).
// ------------------------------------------------------------
// DOM-free, deterministic, and dependency-free so it can be unit-tested in
// Node (tests/test_logic.mjs) and consumed by js/app.js in the browser.
//
// Consumed in the browser as the global `GSD` (loaded via <script> before
// app.js) and in Node as `module.exports` (default import in the .mjs test).
// ============================================================
(function (root, factory) {
  var api = factory();
  if (typeof module === 'object' && module && module.exports) {
    module.exports = api;
  } else {
    root.GSD = api;
  }
})(typeof self !== 'undefined' ? self : globalThis, function () {
  'use strict';

  // Escapes HTML metacharacters; safe for both text content and quoted
  // attribute values (covers &, <, >, ", ').
  function escapeHtml(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }

  // --- Sorting -----------------------------------------------------------
  // Returns a NEW sorted array. Default direction is 'desc' so existing
  // behavior is unchanged (stars: most first; dates: newest first).
  function sortRepos(items, sortKey, sortDir) {
    var dir = sortDir === 'asc' ? 'asc' : 'desc';
    var key = sortKey || 'stars';
    var arr = (items || []).slice();
    arr.sort(function (a, b) {
      var av, bv;
      if (key === 'stars') {
        av = Number(a.stargazers_count) || 0;
        bv = Number(b.stargazers_count) || 0;
      } else {
        av = new Date(a[key] || 0).getTime();
        bv = new Date(b[key] || 0).getTime();
      }
      return dir === 'asc' ? av - bv : bv - av;
    });
    return arr;
  }

  // --- Topic filtering (multi-select AND) -------------------------------
  // A repo matches only when it contains EVERY active topic.
  function matchesAllTopics(repoTopics, activeTopics) {
    if (!activeTopics || activeTopics.size === 0) return true;
    var topics = repoTopics || [];
    var it = activeTopics.forEach ? activeTopics : new Set(activeTopics);
    var all = true;
    it.forEach(function (t) { if (all && topics.indexOf(t) === -1) all = false; });
    return all;
  }

  function filterByTopics(items, activeTopics) {
    if (!activeTopics || activeTopics.size === 0) return (items || []).slice();
    return (items || []).filter(function (r) {
      return matchesAllTopics(r.topics, activeTopics);
    });
  }

  // --- Topic truncation (top-N + remainder) -----------------------------
  function truncateTopics(topics, max) {
    var list = topics || [];
    var limit = max == null ? 3 : max;
    return { shown: list.slice(0, limit), extra: Math.max(0, list.length - limit) };
  }

  // --- Rendering helpers (return HTML strings) --------------------------
  function renderTopicsHtml(topics, activeTopics, max) {
    var t = truncateTopics(topics, max);
    var active = activeTopics || new Set();
    var tags = t.shown.map(function (name) {
      return '<span class="topic-tag' + (active.has(name) ? ' active' : '') +
        '" data-topic="' + escapeHtml(name) + '">' + escapeHtml(name) + '</span>';
    });
    if (t.extra > 0) {
      tags.push('<span class="topic-tag topic-more">+' + t.extra + '</span>');
    }
    return '<div class="topic-tags">' + tags.join('') + '</div>';
  }

  function renderAvatarHtml(ownerAvatar) {
    if (!ownerAvatar) return '';
    return '<img class="avatar" src="' + escapeHtml(ownerAvatar) +
      '" alt="" width="20" height="20" loading="lazy" onerror="this.remove()">';
  }

  // --- Theme resolution -------------------------------------------------
  // Saved explicit choice wins; otherwise follow the OS preference.
  function resolveTheme(saved, prefersDark) {
    if (saved === 'dark' || saved === 'light') return saved;
    return prefersDark ? 'dark' : 'light';
  }

  // --- Sort-direction toggling -----------------------------------------
  // Same key clicked again -> flip. Different key -> reset to 'desc'.
  function nextSortDir(currentSort, clickedSort, currentDir) {
    if (clickedSort && currentSort && clickedSort === currentSort) {
      return currentDir === 'asc' ? 'desc' : 'asc';
    }
    return 'desc';
  }

  return {
    escapeHtml: escapeHtml,
    sortRepos: sortRepos,
    matchesAllTopics: matchesAllTopics,
    filterByTopics: filterByTopics,
    truncateTopics: truncateTopics,
    renderTopicsHtml: renderTopicsHtml,
    renderAvatarHtml: renderAvatarHtml,
    resolveTheme: resolveTheme,
    nextSortDir: nextSortDir,
  };
});
