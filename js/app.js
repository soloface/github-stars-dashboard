// ============================================================
// Browser UI for github-stars-dashboard ("A · 索引" layout).
// ------------------------------------------------------------
// Owns state, rendering and events. All DOM-free logic (sorting, filtering,
// category resolution, URL hash state, search) lives in js/logic.js and is
// reached through the global `GSD`. Every data value that reaches innerHTML
// goes through GSD.escapeHtml.
// ============================================================
(function () {
  'use strict';

  var esc = GSD.escapeHtml;
  // Owner-only: the static page cannot trigger a workflow itself, so this opens
  // the Actions page where the repo owner clicks "Run workflow".
  var SYNC_URL = 'https://github.com/soloface/github-stars-dashboard/actions/workflows/fetch-stars.yml';
  var $ = function (sel) { return document.querySelector(sel); };
  var root = document.documentElement;

  // [sort key, sidebar label, date-column label]
  var SORTS = [
    ['stars', '星标数', '收藏于'],
    ['starred_at', '收藏时间', '收藏于'],
    ['created_at', '创建时间', '创建于'],
    ['pushed_at', '最近推送', '推送于'],
  ];
  var LANG_COLORS = {
    TypeScript: '#3178c6', Python: '#3572a5', JavaScript: '#f1e05a', Go: '#00add8', Shell: '#89e051',
    Rust: '#dea584', Swift: '#f05138', C: '#8a8f99', 'C++': '#f34b7d', Markdown: '#4a76b8', CSS: '#663399',
    HTML: '#e34c26', PHP: '#4f5d95', Vue: '#41b883',
  };
  var NONE = '__none__';            // language key for repos without a language
  var REVIEW = GSD.REVIEW_CATEGORY; // pseudo-category: classification needs a human look
  var LANG_TOP = 7;
  var TOPIC_TOP = 15;
  var DARK = matchMedia('(prefers-color-scheme: dark)');
  var MOBILE = matchMedia('(max-width: 767px)');
  var REDUCED_MOTION = matchMedia('(prefers-reduced-motion: reduce)');

  var S = {
    q: '', sort: 'stars', dir: 'desc', lang: null, topics: new Set(), cats: new Set(),
    group: false, view: 'list', en: false, moreLang: false, expanded: new Set(),
  };
  var ALL = [];    // repos, each with a precomputed search haystack `_hay`
  var TAX = null;  // taxonomy array; null when category data is unavailable
  var CATS = {};   // full_name -> resolved category (GSD.resolveCategories)
  var firstPaint = true;

  // localStorage can throw (privacy modes, disabled storage); treat as empty.
  function storageGet(key) {
    try { return localStorage.getItem(key); } catch (e) { return null; }
  }
  function storageSet(key, value) {
    try { localStorage.setItem(key, value); } catch (e) { /* preference simply isn't persisted */ }
  }

  root.dataset.theme = GSD.resolveTheme(storageGet('theme'), DARK.matches);
  S.group = storageGet('groupByCategory') === '1';
  S.view = GSD.resolveViewMode(null, storageGet('viewMode'));

  // ---------- formatting helpers ----------
  function icon(id, size) {
    var s = size || 14;
    return '<svg width="' + s + '" height="' + s + '" aria-hidden="true"><use href="#i-' + id + '"/></svg>';
  }
  function safeUrl(u) { return /^https:\/\//i.test(u || '') ? u : ''; }
  function langKey(r) { return r.language || NONE; }
  function langName(k) { return k === NONE ? '无语言' : k; }
  function langColor(k) { return k === NONE ? 'var(--text-3)' : (LANG_COLORS[k] || '#9aa1ab'); }
  function langDot(k) {
    return k === NONE ? '<span class="dot none"></span>' : '<span class="dot" style="background:' + langColor(k) + '"></span>';
  }
  function fmtNum(n) {
    n = Number(n) || 0;
    if (n >= 10000) return (n / 10000).toFixed(n >= 100000 ? 0 : 1).replace(/\.0$/, '') + ' 万';
    return n.toLocaleString('en-US');
  }
  function relTime(iso) {
    var t = new Date(iso).getTime();
    if (!iso || isNaN(t)) return '—';
    var d = (Date.now() - t) / 1000;
    if (d < 60) return '刚刚';
    if (d < 3600) return Math.floor(d / 60) + ' 分钟前';
    if (d < 86400) return Math.floor(d / 3600) + ' 小时前';
    if (d < 86400 * 30) return Math.floor(d / 86400) + ' 天前';
    if (d < 86400 * 365) return Math.floor(d / 86400 / 30) + ' 个月前';
    return Math.floor(d / 86400 / 365) + ' 年前';
  }
  function absDate(iso) {
    var d = new Date(iso);
    if (!iso || isNaN(d.getTime())) return '';
    var p = function (x) { return String(x).padStart(2, '0'); };
    return d.getFullYear() + '-' + p(d.getMonth() + 1) + '-' + p(d.getDate()) + ' ' + p(d.getHours()) + ':' + p(d.getMinutes());
  }
  // Escapes `text` and wraps every search-term hit in <mark>.
  function hl(text) {
    text = String(text || '');
    var terms = GSD.searchTerms(S.q);
    if (!terms.length) return esc(text);
    var re = new RegExp(terms.map(function (x) { return x.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'); }).join('|'), 'gi');
    var out = '';
    var i = 0;
    var m;
    while ((m = re.exec(text))) {
      out += esc(text.slice(i, m.index)) + '<mark>' + esc(m[0]) + '</mark>';
      i = m.index + m[0].length;
    }
    return out + esc(text.slice(i));
  }
  function sortMeta(k) { return SORTS.filter(function (s) { return s[0] === k; })[0]; }
  function dirLabel() { return S.dir === 'desc' ? '降序' : '升序'; }
  // The date column follows the sort key; the stars sort shows the starred date.
  function dateKey() { return S.sort === 'stars' ? 'starred_at' : S.sort; }

  // ---------- categories ----------
  function taxIndex() { return GSD.indexTaxonomy(TAX); }
  function catLabel(id) { return id === REVIEW ? '待确认' : GSD.categoryPath(id, TAX).join(' › '); }
  function reviewReason(cat) {
    if (cat.unassigned) return '未归类：没有有效的分类数据';
    if (cat.source === 'rule') return '规则自动归类，待人工确认';
    return '初稿待确认';
  }
  // Expands the parent of a selected child so the selection is visible.
  function revealCategory(id) {
    var node = TAX && taxIndex().byId[id];
    if (node && node.parent) S.expanded.add(node.parent);
  }

  // ---------- filtering ----------
  function compute() {
    var byQuery = ALL.filter(function (r) { return GSD.matchesQuery(r._hay, S.q); });
    var byTopic = GSD.filterByTopics(byQuery, S.topics);
    var catOK = function (r) { return !TAX || GSD.matchesCategories(CATS[r.full_name], S.cats, TAX); };
    var langOK = function (r) { return S.lang === null || langKey(r) === S.lang; };
    // Each facet counts under all OTHER active filters.
    var forLang = byTopic.filter(catOK);
    var forCat = byTopic.filter(langOK);
    var results = forLang.filter(langOK);
    var langCounts = {};
    var topicCounts = {};
    forLang.forEach(function (r) { var k = langKey(r); langCounts[k] = (langCounts[k] || 0) + 1; });
    results.forEach(function (r) {
      (r.topics || []).forEach(function (t) { topicCounts[t] = (topicCounts[t] || 0) + 1; });
    });
    return {
      results: GSD.sortRepos(results, S.sort, S.dir),
      langCounts: langCounts,
      topicCounts: topicCounts,
      catCounts: TAX ? GSD.countCategories(forCat, CATS, TAX) : null,
    };
  }

  function activeFilterCount() {
    return (S.q.trim() ? 1 : 0) + (S.lang ? 1 : 0) + S.topics.size + S.cats.size;
  }

  // ---------- sidebar facets ----------
  function renderSortFacet() {
    var h = '<div class="group"><h2 class="group-h">排序</h2>';
    SORTS.forEach(function (s) {
      var on = S.sort === s[0];
      h += '<button class="opt" type="button" data-act="sort" data-key="' + s[0] + '" data-fkey="sort-' + s[0] + '" aria-pressed="' + on + '"' +
        (on ? ' aria-label="' + s[1] + '，当前' + dirLabel() + '，再次点击切换方向"' : '') + '>' +
        '<span class="radio" aria-hidden="true"></span><span class="lbl">' + s[1] + '</span>' +
        (on ? '<span class="dir">' + icon(S.dir === 'desc' ? 'down' : 'up', 12) + dirLabel() + '</span>' : '') + '</button>';
    });
    return h + '</div>';
  }

  function catOption(id, name, title, count, extraClass, bar) {
    var on = S.cats.has(id);
    var node = taxIndex().byId[id];
    var implied = !on && node && node.parent && S.cats.has(node.parent);
    return '<button class="opt cat' + (extraClass ? ' ' + extraClass : '') + (count ? '' : ' zero') + (implied ? ' implied' : '') +
      '" type="button" data-act="cat" data-cat="' + esc(id) + '" data-fkey="cat-' + esc(id) + '" aria-pressed="' + on + '"' +
      (title ? ' title="' + esc(title) + '"' : '') + '>' +
      '<span class="lbl">' + esc(name) + '</span><span class="cnt num">' + count + '</span>' +
      (bar == null ? '' : '<span class="bar" aria-hidden="true"><i style="width:' + bar.toFixed(1) + '%"></i></span>') +
      '</button>';
  }

  function renderCategoryFacet(counts) {
    var idx = taxIndex();
    var max = Math.max.apply(null, idx.tops.map(function (id) { return counts[id]; }).concat([1]));
    var h = '<div class="group"><h2 class="group-h">分类<small>多选 · 满足其一</small></h2><ul class="tree">';
    idx.tops.forEach(function (id) {
      var node = idx.byId[id];
      var open = S.expanded.has(id);
      var subId = 'sub-' + id;
      h += '<li><div class="node">';
      h += node.children.length
        ? '<button class="twisty" type="button" data-act="expand" data-cat="' + esc(id) + '" data-fkey="exp-' + esc(id) +
          '" aria-expanded="' + open + '" aria-controls="' + esc(subId) + '" aria-label="' + esc(node.name) + ' 的子分类">' + icon('chev', 12) + '</button>'
        : '<span class="twisty" aria-hidden="true"></span>';
      h += catOption(id, node.name, node.description, counts[id], 'top', counts[id] / max * 100) + '</div>';
      if (node.children.length) {
        h += '<ul class="sub" id="' + esc(subId) + '"' + (open ? '' : ' hidden') + '>';
        node.children.forEach(function (cid) {
          var child = idx.byId[cid];
          h += '<li>' + catOption(cid, child.name, child.description, counts[cid], '', null) + '</li>';
        });
        h += '</ul>';
      }
      h += '</li>';
    });
    h += '<li class="review-opt">' + catOption(REVIEW, '待确认', '规则自动归类或未归类、需要人工确认的仓库', counts[REVIEW], '', null) + '</li>';
    return h + '</ul></div>';
  }

  function renderLangFacet(counts) {
    var langs = Object.keys(counts).filter(function (k) { return k !== NONE; })
      .sort(function (a, b) { return counts[b] - counts[a] || a.localeCompare(b); });
    if (S.lang && S.lang !== NONE && langs.indexOf(S.lang) === -1) langs.push(S.lang);
    var max = Math.max.apply(null, langs.map(function (k) { return counts[k] || 0; }).concat([counts[NONE] || 0, 1]));
    var top = langs.slice(0, LANG_TOP);
    var tail = langs.slice(LANG_TOP);
    if (!S.moreLang && S.lang && tail.indexOf(S.lang) !== -1) top.push(S.lang);
    var shown = S.moreLang ? langs : top;
    if (counts[NONE] || S.lang === NONE) shown = shown.concat([NONE]);
    var h = '<div class="group"><h2 class="group-h">语言<small>' + langs.length + ' 种</small></h2>';
    shown.forEach(function (k) {
      var n = counts[k] || 0;
      h += '<button class="opt lang" type="button" data-act="lang" data-lang="' + esc(k) + '" data-fkey="lang-' + esc(k) + '" aria-pressed="' + (S.lang === k) + '">' +
        langDot(k) + '<span class="lbl">' + esc(langName(k)) + '</span><span class="cnt num">' + n + '</span>' +
        '<span class="bar" aria-hidden="true"><i style="width:' + (n / max * 100).toFixed(1) + '%;background:' + langColor(k) + '"></i></span></button>';
    });
    var hidden = tail.filter(function (k) { return shown.indexOf(k) === -1; }).length;
    if (tail.length) {
      h += '<button class="more" type="button" data-act="more-lang" data-fkey="more-lang" aria-expanded="' + S.moreLang + '">' +
        (S.moreLang ? '收起' : '更多 ' + hidden + ' 种') + icon('chev', 12) + '</button>';
    }
    return h + '</div>';
  }

  function renderTopicFacet(counts) {
    var active = Array.from(S.topics);
    var popular = Object.keys(counts).filter(function (t) { return !S.topics.has(t); })
      .sort(function (a, b) { return counts[b] - counts[a] || a.localeCompare(b); }).slice(0, TOPIC_TOP);
    var h = '<div class="group"><h2 class="group-h">热门主题<small>多选 · 同时满足</small></h2><div class="tg">';
    active.concat(popular).forEach(function (t) {
      h += '<button class="tchip" type="button" data-act="topic" data-topic="' + esc(t) + '" data-fkey="topic-' + esc(t) + '" aria-pressed="' + S.topics.has(t) + '">' +
        esc(t) + '<span class="cnt num">' + (counts[t] || 0) + '</span></button>';
    });
    if (!active.length && !popular.length) h += '<span class="hint">当前结果没有主题标签</span>';
    return h + '</div></div>';
  }

  function renderFacets(c) {
    var h = '<div class="sheet-h"><h2>筛选与排序</h2><button class="icon-btn" type="button" data-act="close-sheet" data-fkey="sheet-close" aria-label="关闭">' + icon('x', 16) + '</button></div>';
    h += renderSortFacet();
    if (TAX) h += renderCategoryFacet(c.catCounts);
    h += renderLangFacet(c.langCounts);
    h += renderTopicFacet(c.topicCounts);
    h += '<div class="group"><h2 class="group-h" id="descLangH">描述语言</h2><div class="seg" role="group" aria-labelledby="descLangH">' +
      '<button type="button" data-act="en" data-v="0" data-fkey="en0" aria-pressed="' + !S.en + '">中文</button>' +
      '<button type="button" data-act="en" data-v="1" data-fkey="en1" aria-pressed="' + S.en + '">英文原文</button></div></div>';
    h += '<div class="sheet-f"><button class="btn primary" type="button" data-act="close-sheet" data-fkey="sheet-done">显示 ' + c.results.length + ' 个结果</button>' +
      '<p class="sheet-meta">' + esc($('#updated').textContent) + ' · <a href="' + SYNC_URL + '" target="_blank" rel="noopener">手动同步</a></p></div>';
    $('#facets').innerHTML = h;
  }

  // ---------- filter bar ----------
  function filterChip(label, value, act, data) {
    return '<span class="fchip"><span class="k">' + label + '</span><span class="v">' + esc(value) + '</span>' +
      '<button type="button" data-act="' + act + '" data-v="' + esc(data) + '" data-fkey="' + act + '-' + esc(data) + '" aria-label="移除' + label + '筛选：' + esc(value) + '">' +
      icon('x', 12) + '</button></span>';
  }

  function renderFilterbar(c) {
    var n = c.results.length;
    var chips = '';
    if (S.q.trim()) chips += filterChip('搜索', '“' + S.q.trim() + '”', 'rm-q', '');
    S.cats.forEach(function (id) { chips += filterChip('分类', catLabel(id), 'rm-cat', id); });
    if (S.lang) chips += filterChip('语言', langName(S.lang), 'rm-lang', '');
    S.topics.forEach(function (t) { chips += filterChip('主题', t, 'rm-topic', t); });
    var count = '<span class="count"><b class="num">' + n + '</b>' + (chips ? ' / ' + ALL.length + ' 个仓库' : ' 个仓库') + '</span>';
    $('#filterState').innerHTML = count + (chips
      ? chips + '<button class="clear" type="button" data-act="clear" data-fkey="clear">清除全部</button>'
      : '<span class="hint">按' + sortMeta(S.sort)[1] + dirLabel() + '排列 · 按 <kbd class="num">/</kbd> 搜索</span>');
    $('#liveCount').textContent = chips ? '筛选出 ' + n + ' 个仓库' : '共 ' + n + ' 个仓库';

    var badge = $('#filterBadge');
    var active = activeFilterCount();
    badge.hidden = !active;
    badge.textContent = active;

    var toggle = $('#groupToggle');
    toggle.hidden = !TAX;
    toggle.setAttribute('aria-pressed', String(S.group && !!TAX));
    document.querySelectorAll('#viewToggle button').forEach(function (b) {
      b.setAttribute('aria-pressed', String(b.dataset.v === S.view));
    });
  }

  // ---------- list ----------
  function sortHeader(key, label, cls) {
    var on = S.sort === key || (key === 'date' && S.sort !== 'stars');
    var k = key === 'date' ? dateKey() : key;
    return '<span class="hc r ' + cls + '">' +
      '<button class="ch" type="button" data-act="sort" data-key="' + k + '" data-fkey="col-' + key + '" aria-pressed="' + on + '" aria-label="按' + sortMeta(k)[1] + '排序' +
      (on ? '，当前' + dirLabel() : '') + '">' + label + (on ? icon(S.dir === 'desc' ? 'down' : 'up', 12) : '') + '</button></span>';
  }

  function renderCols() {
    // Card view has no columns; sorting stays available in the sidebar.
    $('#cols').hidden = S.view === 'card';
    $('#cols').innerHTML = '<div class="cols-row">' +
      '<span class="hc">仓库</span>' +
      '<span class="hc c-lang">语言</span>' +
      sortHeader('stars', icon('star', 12) + '星标', 'c-star') +
      '<span class="hc r c-fork">' + icon('fork', 12) + '分叉</span>' +
      sortHeader('date', sortMeta(dateKey())[2], 'c-date') +
      '</div>';
  }

  function categoryChip(r) {
    var cat = TAX && CATS[r.full_name];
    if (!cat) return '';
    var path = GSD.categoryPath(cat.primary, TAX);
    var title = '主分类：' + path.join(' › ');
    if (cat.secondary.length) title += '\n次分类：' + cat.secondary.map(catLabel).join('、');
    var h = '<button class="cchip" type="button" data-act="cat" data-cat="' + esc(cat.primary) + '" data-fkey="rcat-' + esc(r.full_name) + '" aria-pressed="' + S.cats.has(cat.primary) + '"' +
      ' title="' + esc(title) + '" aria-label="按分类 ' + esc(path.join(' › ')) + ' 筛选"><span>' + hl(path[path.length - 1]) + '</span></button>';
    if (cat.needsReview || cat.unassigned) {
      var reason = reviewReason(cat);
      h += '<span class="flag" title="' + esc(reason) + '" aria-label="待确认：' + esc(reason) + '">待确认</span>';
    }
    return h;
  }

  // HTML fragments shared by list rows and cards. `cls` maps each stat to the
  // class names of the current layout (list columns vs. card footer).
  function repoParts(r, cls) {
    var parts = r.full_name.split('/');
    var dk = dateKey();
    var zh = r.description_zh || r.description || '';
    var en = r.description || '';
    var desc = S.en ? (en || zh) : zh;
    var alt = S.en ? zh : en;
    var tip = alt && alt !== desc ? ' title="' + esc((S.en ? '中文：' : '原文：') + alt) + '"' : '';
    var topics = (r.topics || []).slice().sort(function (a, b) { return S.topics.has(b) - S.topics.has(a); });
    var lk = langKey(r);
    var avatar = safeUrl(r.owner_avatar);
    return {
      avatar: avatar ? '<img class="av" src="' + esc(avatar) + '" alt="" width="40" height="40" loading="lazy" onerror="this.style.visibility=\'hidden\'">' : '<span class="av" aria-hidden="true"></span>',
      name: '<a class="name" href="' + esc(safeUrl(r.html_url) || '#') + '" target="_blank" rel="noopener">' + hl(parts[0]) + ' / <b>' + hl(parts.slice(1).join('/')) + '</b></a>',
      cat: categoryChip(r),
      topics: topics.length ? '<span class="topics">' + topics.slice(0, 3).map(function (t) {
        return '<button class="topic" type="button" data-act="topic" data-topic="' + esc(t) + '" data-fkey="rtopic-' + esc(r.full_name + ':' + t) + '" aria-pressed="' + S.topics.has(t) + '" aria-label="按主题 ' + esc(t) + ' 筛选">' + hl(t) + '</button>';
      }).join('') + (topics.length > 3 ? '<span class="topic-more num">+' + (topics.length - 3) + '</span>' : '') + '</span>' : '',
      desc: desc ? '<p class="desc"' + tip + '>' + hl(desc) + '</p>' : '<p class="desc empty">暂无描述</p>',
      lang: '<span class="' + cls.lang + '">' + langDot(lk) + '<span' + (lk === NONE ? ' class="muted"' : '') + '>' + esc(langName(lk)) + '</span></span>',
      star: '<span class="c-num' + (cls.star ? ' ' + cls.star : '') + ' num" title="' + (Number(r.stargazers_count) || 0).toLocaleString('en-US') + ' 星标">' +
        '<svg class="star" width="13" height="13" aria-hidden="true"><use href="#i-star"/></svg>' + fmtNum(r.stargazers_count) + '</span>',
      fork: '<span class="c-num' + (cls.fork ? ' ' + cls.fork : '') + ' fork num" title="' + (Number(r.forks_count) || 0).toLocaleString('en-US') + ' 分叉">' +
        '<svg class="ic" width="13" height="13" aria-hidden="true"><use href="#i-fork"/></svg>' + fmtNum(r.forks_count) + '</span>',
      // Cards have no column header, so they carry the date label inline.
      date: '<time class="' + cls.date + ' num" datetime="' + esc(r[dk]) + '" title="' + sortMeta(dk)[2] + ' ' + absDate(r[dk]) + '">' +
        (cls.dateLabel ? sortMeta(dk)[2] + ' ' : '') + relTime(r[dk]) + '</time>',
    };
  }

  var ROW_CLS = { lang: 'c-lang', star: 'c-star', fork: 'c-fork', date: 'c-date', dateLabel: false };
  var CARD_CLS = { lang: 'card-lang', date: 'card-date', dateLabel: true };

  function rowHtml(r) {
    var p = repoParts(r, ROW_CLS);
    return '<li class="row">' + p.avatar +
      '<div class="cell-main"><div class="l1">' + p.name + p.cat + p.topics + '</div>' + p.desc + '</div>' +
      p.lang + p.star + p.fork + p.date +
    '</li>';
  }

  function cardHtml(r) {
    var p = repoParts(r, CARD_CLS);
    return '<li class="card">' +
      '<div class="card-h">' + p.avatar + '<div class="card-id">' + p.name + (p.cat ? '<div class="card-cat">' + p.cat + '</div>' : '') + '</div></div>' +
      p.desc + p.topics +
      '<div class="card-f">' + p.lang + p.star + p.fork + p.date + '</div>' +
    '</li>';
  }

  function renderList(results) {
    var box = $('#results');
    if (!results.length) {
      box.innerHTML = '<div class="empty-state"><h2>没有匹配的仓库</h2>试试更短的关键词，或移除部分筛选条件。<br>' +
        '<button class="btn" type="button" data-act="clear">清除全部筛选</button></div>';
      return;
    }
    var card = S.view === 'card';
    var item = card ? cardHtml : rowHtml;
    var listOpen = card ? '<ul class="cards"' : '<ul class="list"';
    if (S.group && TAX) {
      box.innerHTML = GSD.groupByPrimary(results, CATS, TAX).map(function (sec) {
        var crumbs = sec.path.map(function (name, i) {
          return i < sec.path.length - 1 ? '<span class="crumb">' + esc(name) + '</span><span class="sep" aria-hidden="true">›</span>' : esc(name);
        }).join('');
        return '<section class="sec" data-sec="' + esc(sec.id) + '" aria-label="' + esc(sec.path.join(' › ')) + '">' +
          '<h2 class="sec-h">' + crumbs + '<span class="n num">· ' + sec.items.length + '</span></h2>' +
          listOpen + '>' + sec.items.map(item).join('') + '</ul></section>';
      }).join('');
    } else {
      box.innerHTML = listOpen + ' aria-label="仓库列表">' + results.map(item).join('') + '</ul>';
    }
    box.classList.toggle('rows-in', firstPaint);
    firstPaint = false;
  }

  // ---------- URL hash ----------
  function hashFromState() {
    return GSD.buildHashState({
      cat: S.cats, lang: S.lang, topic: S.topics, q: S.q.trim(), sort: S.sort, dir: S.dir, group: S.group && !!TAX,
      view: S.view,
    });
  }
  function syncHash() {
    var h = hashFromState();
    if ((h ? '#' + h : '') === location.hash) return;
    history.replaceState(null, '', h ? '#' + h : location.pathname + location.search);
  }
  function applyHash() {
    var known = {
      cat: TAX ? Object.keys(taxIndex().byId).concat([REVIEW]) : [],
      lang: ALL.map(langKey),
      topic: ALL.reduce(function (acc, r) { return acc.concat(r.topics || []); }, []),
    };
    var h = GSD.parseHashState(location.hash, known);
    S.cats = new Set(h.cat);
    S.cats.forEach(revealCategory);
    S.lang = h.lang;
    S.topics = new Set(h.topic);
    S.q = h.q;
    $('#q').value = h.q;
    S.sort = h.sort || 'stars';
    S.dir = h.dir || 'desc';
    if (h.group !== null) S.group = h.group;
    S.view = GSD.resolveViewMode(h.view, S.view);
  }

  // ---------- render ----------
  function render() {
    var active = document.activeElement;
    var fkey = active && active.dataset && active.dataset.fkey;
    var c = compute();
    $('#main').dataset.view = S.view;
    renderFacets(c);
    renderFilterbar(c);
    renderCols();
    renderList(c.results);
    syncHash();
    if (fkey) {
      var el = document.querySelector('[data-fkey="' + CSS.escape(fkey) + '"]');
      if (el) el.focus();
    }
  }

  // Group / view toggles only: animate the results swap with a View Transition.
  // Falls back to a plain render when unsupported or when the user prefers reduced motion.
  function switchWithTransition() {
    if (!document.startViewTransition || REDUCED_MOTION.matches) { render(); return; }
    document.startViewTransition(render);
  }

  // In grouped mode, jump to the first section under the chosen category.
  function scrollToSection(id) {
    var secs = document.querySelectorAll('.sec');
    for (var i = 0; i < secs.length; i++) {
      if (GSD.categoryAncestors(secs[i].dataset.sec, TAX).indexOf(id) !== -1) {
        secs[i].scrollIntoView({ block: 'start', behavior: REDUCED_MOTION.matches ? 'auto' : 'smooth' });
        return;
      }
    }
  }

  // ---------- theme ----------
  function paintTheme() {
    var dark = root.dataset.theme === 'dark';
    var label = dark ? '切换到浅色主题' : '切换到深色主题';
    document.querySelectorAll('.js-theme').forEach(function (b) {
      b.innerHTML = icon(dark ? 'sun' : 'moon', 16);
      b.setAttribute('aria-label', label);
      b.title = label;
    });
  }
  DARK.addEventListener('change', function (e) {
    if (storageGet('theme')) return;
    root.dataset.theme = GSD.resolveTheme(null, e.matches);
    paintTheme();
  });

  // ---------- mobile filter sheet ----------
  var sheetTrigger = null;
  function sheetOpen() { return document.body.classList.contains('sheet'); }
  function openSheet(trigger) {
    var facets = $('#facets');
    sheetTrigger = trigger;
    document.body.classList.add('sheet');
    facets.setAttribute('role', 'dialog');
    facets.setAttribute('aria-modal', 'true');
    trigger.setAttribute('aria-expanded', 'true');
    // Wait one frame so the sheet is visible (and therefore focusable).
    requestAnimationFrame(function () {
      var close = facets.querySelector('.sheet-h button');
      if (close) close.focus();
    });
  }
  function closeSheet() {
    if (!sheetOpen()) return;
    var facets = $('#facets');
    document.body.classList.remove('sheet');
    facets.setAttribute('role', 'region');
    facets.removeAttribute('aria-modal');
    if (sheetTrigger) {
      sheetTrigger.setAttribute('aria-expanded', 'false');
      sheetTrigger.focus();
    }
  }
  function trapFocus(e) {
    var focusables = Array.prototype.filter.call(
      $('#facets').querySelectorAll('button, [href], input, [tabindex]:not([tabindex="-1"])'),
      function (el) { return !el.disabled && el.getClientRects().length; });
    if (!focusables.length) return;
    var first = focusables[0];
    var last = focusables[focusables.length - 1];
    var inside = $('#facets').contains(document.activeElement);
    if (e.shiftKey && (document.activeElement === first || !inside)) { e.preventDefault(); last.focus(); }
    else if (!e.shiftKey && (document.activeElement === last || !inside)) { e.preventDefault(); first.focus(); }
  }
  MOBILE.addEventListener('change', function (e) { if (!e.matches) closeSheet(); });

  // Sticky section headers sit below the sticky mobile top bar.
  if (window.ResizeObserver) {
    new ResizeObserver(function () {
      root.style.setProperty('--bar-h', $('.side').offsetHeight + 'px');
    }).observe($('.side'));
  }

  // ---------- events ----------
  function clearFilters() {
    S.q = '';
    $('#q').value = '';
    S.lang = null;
    S.topics.clear();
    S.cats.clear();
  }

  document.addEventListener('click', function (e) {
    var el = e.target.closest('[data-act]');
    if (!el) return;
    var act = el.dataset.act;
    var scrollTo = null;
    if (act === 'topic') {
      var t = el.dataset.topic;
      if (S.topics.has(t)) S.topics.delete(t); else S.topics.add(t);
    } else if (act === 'cat') {
      var id = el.dataset.cat;
      S.cats = GSD.toggleCategory(S.cats, id, TAX);
      if (S.cats.has(id)) { revealCategory(id); scrollTo = id; }
    } else if (act === 'expand') {
      var key = el.dataset.cat;
      if (S.expanded.has(key)) S.expanded.delete(key); else S.expanded.add(key);
    } else if (act === 'sort') {
      var k = el.dataset.key;
      S.dir = GSD.nextSortDir(S.sort, k, S.dir);
      S.sort = k;
    } else if (act === 'lang') {
      S.lang = S.lang === el.dataset.lang ? null : el.dataset.lang;
    } else if (act === 'more-lang') {
      S.moreLang = !S.moreLang;
    } else if (act === 'en') {
      S.en = el.dataset.v === '1';
    } else if (act === 'group') {
      S.group = !S.group;
      storageSet('groupByCategory', S.group ? '1' : '0');
      switchWithTransition(); return;
    } else if (act === 'view') {
      if (S.view === el.dataset.v) return;
      S.view = GSD.resolveViewMode(el.dataset.v, S.view);
      storageSet('viewMode', S.view);
      switchWithTransition(); return;
    } else if (act === 'rm-q') {
      S.q = '';
      $('#q').value = '';
    } else if (act === 'rm-cat') {
      S.cats.delete(el.dataset.v);
    } else if (act === 'rm-lang') {
      S.lang = null;
    } else if (act === 'rm-topic') {
      S.topics.delete(el.dataset.v);
    } else if (act === 'clear') {
      clearFilters();
    } else if (act === 'theme') {
      root.dataset.theme = root.dataset.theme === 'dark' ? 'light' : 'dark';
      storageSet('theme', root.dataset.theme);
      paintTheme();
      return;
    } else if (act === 'open-sheet') {
      openSheet(el);
      return;
    } else if (act === 'close-sheet') {
      closeSheet();
      return;
    } else if (act === 'retry') {
      load();
      return;
    }
    render();
    if (scrollTo && S.group && TAX) scrollToSection(scrollTo);
  });

  $('#q').addEventListener('input', function (e) { S.q = e.target.value; render(); });

  document.addEventListener('keydown', function (e) {
    var tag = (e.target.tagName || '').toLowerCase();
    var typing = tag === 'input' || tag === 'textarea' || e.target.isContentEditable;
    if (e.key === 'Tab' && sheetOpen()) {
      trapFocus(e);
    } else if (e.key === '/' && !typing && !sheetOpen() && !e.metaKey && !e.ctrlKey && !e.altKey) {
      e.preventDefault();
      $('#q').focus();
      $('#q').select();
    } else if (e.key === 'Escape') {
      if (sheetOpen()) {
        closeSheet();
      } else if (e.target.id === 'q') {
        if (S.q) { S.q = ''; e.target.value = ''; render(); } else e.target.blur();
      }
    }
  });

  window.addEventListener('hashchange', function () {
    applyHash();
    render();
  });

  // ---------- data ----------
  function getJSON(url) {
    return fetch(url, { cache: 'no-cache' }).then(function (r) {
      if (!r.ok) throw new Error('HTTP ' + r.status);
      return r.json();
    });
  }

  function load() {
    $('#results').innerHTML = S.view === 'card'
      ? '<ul class="cards" aria-hidden="true">' + Array(7).join('<li class="skel-card"></li>') + '</ul>'
      : '<ul class="list" aria-hidden="true">' + Array(9).join('<li class="skel"></li>') + '</ul>';
    // All four files load in parallel. The page works without category data;
    // overrides alone are optional (missing/broken -> no overrides).
    var stars = getJSON('data/stars.json');
    var categories = Promise.all([
      getJSON('data/categories.json'),
      getJSON('data/category_assignments.json'),
      getJSON('data/category_overrides.json').catch(function (err) {
        console.error('category_overrides.json unavailable, ignoring overrides:', err);
        return {};
      }),
    ]).catch(function (err) {
      console.error('Category data unavailable, categories disabled:', err);
      return null;
    });

    Promise.all([stars, categories]).then(function (res) {
      var data = Array.isArray(res[0]) ? res[0] : [];
      var cat = res[1];
      try {
        TAX = cat && cat[0] && Array.isArray(cat[0].taxonomy) && cat[0].taxonomy.length ? cat[0].taxonomy : null;
        CATS = TAX ? GSD.resolveCategories(data, TAX, cat[1], cat[2]) : {};
      } catch (err) {
        // Bad category data only disables categories; repos still render.
        console.error('Category resolution failed, categories disabled:', err);
        TAX = null;
        CATS = {};
      }
      ALL = data.map(function (r) {
        r._hay = GSD.searchHaystack(r, CATS[r.full_name], TAX);
        return r;
      });
      var latest = ALL.reduce(function (m, r) { return r.starred_at && r.starred_at > m ? r.starred_at : m; }, '');
      $('#brandSub').innerHTML = '共 <b class="num">' + ALL.length + '</b> 个星标仓库';
      $('#updated').textContent = latest ? '最近收藏 ' + latest.slice(0, 10) : '';
      $('#updated').title = latest ? '最近一次收藏：' + absDate(latest) : '';
      applyHash();
      render();
    }).catch(function (err) {
      console.error('Failed to load stars data:', err);
      $('#results').innerHTML = '<div class="empty-state"><h2>数据加载失败</h2>请检查网络后重试。<br>' +
        '<button class="btn" type="button" data-act="retry">重试</button></div>';
    });
  }

  paintTheme();
  load();
})();
