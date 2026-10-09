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

  // --- Functional category index ----------------------------------------
  // Taxonomy shape (data/categories.json → taxonomy): an ordered array of
  // top-level {id, name, description, children:[{id, name, description}]}.
  // Repos may be assigned to a child id or, for top-levels without children,
  // to the top-level id itself. Unknown/missing assignments fall back to
  // OTHER and are flagged `unassigned`. REVIEW is a pseudo-category that
  // selects every repo whose classification still needs a human look.
  var OTHER = 'other';
  var REVIEW = 'review';
  var indexCache = new WeakMap();

  function own(obj, key) {
    return obj != null && Object.prototype.hasOwnProperty.call(obj, key);
  }

  function toSet(v) {
    if (v instanceof Set) return v;
    return new Set(v || []);
  }

  // Flattens the taxonomy into {tops:[id], byId:{id:{id, name, description, parent, children}}}.
  // Memoized per taxonomy array so callers can pass the raw array everywhere.
  function indexTaxonomy(taxonomy) {
    var list = Array.isArray(taxonomy) ? taxonomy : [];
    if (indexCache.has(list)) return indexCache.get(list);
    var idx = { tops: [], byId: Object.create(null) };
    list.forEach(function (top) {
      if (!top || !top.id) return;
      var kids = (Array.isArray(top.children) ? top.children : []).filter(function (c) { return c && c.id; });
      idx.tops.push(top.id);
      idx.byId[top.id] = {
        id: top.id, name: top.name || top.id, description: top.description || '', parent: null,
        children: kids.map(function (c) { return c.id; }),
      };
      kids.forEach(function (c) {
        idx.byId[c.id] = {
          id: c.id, name: c.name || c.id, description: c.description || '', parent: top.id, children: [],
        };
      });
    });
    if (Array.isArray(taxonomy)) indexCache.set(taxonomy, idx);
    return idx;
  }

  // [id, parentId] for a child, [id] for a top-level, [] for unknown ids.
  function categoryAncestors(id, taxonomy) {
    var node = indexTaxonomy(taxonomy).byId[id];
    if (!node) return [];
    return node.parent ? [id, node.parent] : [id];
  }

  // Display names from top-level down, e.g. ['AI 编码代理', '客户端与工作台'].
  function categoryPath(id, taxonomy) {
    var byId = indexTaxonomy(taxonomy).byId;
    return categoryAncestors(id, taxonomy).reverse().map(function (x) { return byId[x].name; });
  }

  // full_name -> {primary, secondary[], source, needsReview, unassigned}.
  // A valid override wins over the pipeline assignment (source 'override').
  // Rule-based assignments always need review; `source` is null when unassigned.
  // Hand-edited data may be malformed: non-string ids, a non-array secondary
  // or a non-object entry are ignored rather than allowed to throw.
  function resolveCategories(repos, taxonomy, assignments, overrides) {
    var byId = indexTaxonomy(taxonomy).byId;
    var known = function (id) { return typeof id === 'string' && !!byId[id]; };
    var out = {};
    (repos || []).forEach(function (repo) {
      var name = repo.full_name;
      var override = own(overrides, name) ? overrides[name] : null;
      var assigned = own(assignments, name) ? assignments[name] : null;
      var entry = [override, assigned].filter(function (e) { return e && known(e.primary); })[0];
      if (!entry) {
        out[name] = { primary: OTHER, secondary: [], source: null, needsReview: false, unassigned: true };
        return;
      }
      var secondary = [];
      (Array.isArray(entry.secondary) ? entry.secondary : []).forEach(function (id) {
        if (known(id) && id !== entry.primary && secondary.indexOf(id) === -1) secondary.push(id);
      });
      out[name] = {
        primary: entry.primary,
        secondary: secondary,
        source: entry === override ? 'override' : ((typeof entry.source === 'string' && entry.source) || null),
        needsReview: entry === assigned && (entry.needs_review === true || entry.source === 'rule'),
        unassigned: false,
      };
    });
    return out;
  }

  // Every category id the repo belongs to, including implied top-levels and
  // the REVIEW pseudo-category.
  function categoryHits(cat, taxonomy) {
    var hits = new Set();
    if (!cat) return hits;
    if (cat.needsReview || cat.unassigned) hits.add(REVIEW);
    [cat.primary].concat(cat.secondary || []).forEach(function (id) {
      categoryAncestors(id, taxonomy).forEach(function (x) { hits.add(x); });
    });
    return hits;
  }

  // Selected categories are OR-ed; selecting a top-level covers its children.
  function matchesCategories(cat, selection, taxonomy) {
    var sel = toSet(selection);
    if (sel.size === 0) return true;
    var hits = categoryHits(cat, taxonomy);
    var found = false;
    sel.forEach(function (id) { if (hits.has(id)) found = true; });
    return found;
  }

  // Returns a NEW selection with `id` toggled. Selecting a top-level replaces
  // its selected children; selecting a child of a selected top-level narrows
  // the selection to that child.
  function toggleCategory(selection, id, taxonomy) {
    var next = new Set(toSet(selection));
    if (next.has(id)) {
      next.delete(id);
      return next;
    }
    var node = indexTaxonomy(taxonomy).byId[id];
    if (node && node.parent) next.delete(node.parent);
    if (node) node.children.forEach(function (c) { next.delete(c); });
    next.add(id);
    return next;
  }

  // {categoryId: number of items matching that category}, for every id in the
  // taxonomy plus REVIEW (zero when unused).
  function countCategories(items, catMap, taxonomy) {
    var idx = indexTaxonomy(taxonomy);
    var counts = {};
    counts[REVIEW] = 0;
    Object.keys(idx.byId).forEach(function (id) { counts[id] = 0; });
    (items || []).forEach(function (r) {
      categoryHits(catMap && catMap[r.full_name], taxonomy).forEach(function (id) { counts[id] += 1; });
    });
    return counts;
  }

  // Splits items into sections by PRIMARY category, in taxonomy order (a
  // top-level's own section precedes its children). Each item appears once;
  // order within a section follows the input. Empty sections are omitted.
  function groupByPrimary(items, catMap, taxonomy) {
    var idx = indexTaxonomy(taxonomy);
    var buckets = {};
    var unknown = [];
    (items || []).forEach(function (r) {
      var cat = catMap && catMap[r.full_name];
      var id = cat ? cat.primary : OTHER;
      if (!buckets[id]) {
        buckets[id] = [];
        if (!idx.byId[id]) unknown.push(id);
      }
      buckets[id].push(r);
    });
    var order = [];
    idx.tops.forEach(function (top) { order.push(top); order.push.apply(order, idx.byId[top].children); });
    return order.concat(unknown).filter(function (id) { return buckets[id]; }).map(function (id) {
      var path = categoryPath(id, taxonomy);
      return { id: id, path: path.length ? path : [id], items: buckets[id] };
    });
  }

  // --- Shareable URL hash state ----------------------------------------
  // e.g. "cat=ai-coding/clients,mcp&lang=Go&topic=mcp&q=agent&sort=stars&dir=desc&group=1"
  var SORT_KEYS = ['stars', 'starred_at', 'created_at', 'pushed_at'];

  function encodeHashValue(v) {
    return encodeURIComponent(v).replace(/%2F/gi, '/');
  }

  function decodeHashValue(v) {
    try { return decodeURIComponent(v); } catch (e) { return null; }
  }

  // Parses a location.hash. Unspecified or invalid fields come back as
  // null / '' / [] so the caller can apply its own defaults. When `known`
  // ({cat, lang, topic}: arrays or Sets) is given, values outside it are dropped.
  function parseHashState(hash, known) {
    var state = { cat: [], lang: null, topic: [], q: '', sort: null, dir: null, group: null };
    var allowed = {};
    ['cat', 'lang', 'topic'].forEach(function (k) {
      allowed[k] = known && known[k] ? toSet(known[k]) : null;
    });
    var ok = function (k, v) { return v && (!allowed[k] || allowed[k].has(v)); };
    String(hash || '').replace(/^#/, '').split('&').forEach(function (pair) {
      var i = pair.indexOf('=');
      if (i < 1) return;
      var key = pair.slice(0, i);
      var raw = pair.slice(i + 1);
      if (key === 'cat' || key === 'topic') {
        var list = [];
        raw.split(',').forEach(function (part) {
          var v = decodeHashValue(part);
          if (ok(key, v) && list.indexOf(v) === -1) list.push(v);
        });
        state[key] = list;
        return;
      }
      var value = decodeHashValue(raw);
      if (value === null) return;
      if (key === 'lang' && ok('lang', value)) state.lang = value;
      else if (key === 'q') state.q = value;
      else if (key === 'sort' && SORT_KEYS.indexOf(value) !== -1) state.sort = value;
      else if (key === 'dir' && (value === 'asc' || value === 'desc')) state.dir = value;
      else if (key === 'group' && (value === '1' || value === '0')) state.group = value === '1';
    });
    return state;
  }

  // Inverse of parseHashState (without the leading '#'). Defaults are omitted
  // (sort=stars, dir=desc, group off, empty filters) so the plain view has no hash.
  function buildHashState(state) {
    var s = state || {};
    var parts = [];
    var list = function (v) { return Array.from(toSet(v)).map(encodeHashValue).join(','); };
    if (toSet(s.cat).size) parts.push('cat=' + list(s.cat));
    if (s.lang) parts.push('lang=' + encodeHashValue(s.lang));
    if (toSet(s.topic).size) parts.push('topic=' + list(s.topic));
    if (s.q) parts.push('q=' + encodeHashValue(s.q));
    if (s.sort && s.sort !== 'stars') parts.push('sort=' + encodeHashValue(s.sort));
    if (s.dir === 'asc') parts.push('dir=asc');
    if (s.group) parts.push('group=1');
    return parts.join('&');
  }

  // --- Search ------------------------------------------------------------
  function searchTerms(query) {
    return String(query || '').trim().toLowerCase().split(/\s+/).filter(Boolean);
  }

  // Lower-cased text a repo can be found by: name, descriptions (zh + en),
  // language, topics, and the names of its primary/secondary categories.
  function searchHaystack(repo, cat, taxonomy) {
    var parts = [repo.full_name, repo.description, repo.description_zh, repo.language].concat(repo.topics || []);
    if (cat) {
      [cat.primary].concat(cat.secondary || []).forEach(function (id) {
        parts = parts.concat(categoryPath(id, taxonomy));
      });
    }
    return parts.filter(Boolean).join(' ').toLowerCase();
  }

  // Every whitespace-separated term must occur in the haystack.
  function matchesQuery(haystack, query) {
    return searchTerms(query).every(function (t) { return haystack.indexOf(t) !== -1; });
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
    OTHER_CATEGORY: OTHER,
    REVIEW_CATEGORY: REVIEW,
    SORT_KEYS: SORT_KEYS,
    indexTaxonomy: indexTaxonomy,
    categoryAncestors: categoryAncestors,
    categoryPath: categoryPath,
    resolveCategories: resolveCategories,
    matchesCategories: matchesCategories,
    toggleCategory: toggleCategory,
    countCategories: countCategories,
    groupByPrimary: groupByPrimary,
    parseHashState: parseHashState,
    buildHashState: buildHashState,
    searchTerms: searchTerms,
    searchHaystack: searchHaystack,
    matchesQuery: matchesQuery,
  };
});
