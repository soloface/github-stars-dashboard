// Pure-logic contract tests for the Phase 3 frontend features.
//
// The dashboard's DOM/CSS wiring lives in js/app.js (browser-only), but the
// behavior that actually matters — sort direction, topic AND-filtering, the
// "+N" fold, avatar fallback, theme resolution, sort-direction toggling — is
// pure data-in/data-out logic. We extract it into js/logic.js and pin it here
// so it is covered by TDD (Phase 3 design doc R3: "TDD：先写测试用例覆盖
// sort+filter 组合，再实现").
//
// Run:  node --test tests/test_logic.mjs
//       (Node >= 18 built-in test runner; zero dependencies)
import { test } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import GSD from '../js/logic.js';

const sample = [
  { full_name: 'a/high', stargazers_count: 300, topics: ['x'], starred_at: '2026-01-01T00:00:00Z', language: 'Go' },
  { full_name: 'b/low', stargazers_count: 100, topics: ['x', 'y'], starred_at: '2026-03-01T00:00:00Z', language: 'Go' },
  { full_name: 'c/mid', stargazers_count: 200, topics: ['y', 'z'], starred_at: '2026-02-01T00:00:00Z', language: 'Go' },
];

// ---------------------------------------------------------------------------
// sortRepos
// ---------------------------------------------------------------------------
test('sortRepos: stars default direction is descending (default behavior unchanged)', () => {
  const out = GSD.sortRepos(sample, 'stars');
  assert.deepEqual(out.map(r => r.full_name), ['a/high', 'c/mid', 'b/low']);
});

test('sortRepos: asc flips stars to ascending', () => {
  const out = GSD.sortRepos(sample, 'stars', 'asc');
  assert.deepEqual(out.map(r => r.full_name), ['b/low', 'c/mid', 'a/high']);
});

test('sortRepos: date desc = newest first', () => {
  const out = GSD.sortRepos(sample, 'starred_at', 'desc');
  assert.deepEqual(out.map(r => r.full_name), ['b/low', 'c/mid', 'a/high']); // Mar, Feb, Jan
});

test('sortRepos: date asc = oldest first', () => {
  const out = GSD.sortRepos(sample, 'starred_at', 'asc');
  assert.deepEqual(out.map(r => r.full_name), ['a/high', 'c/mid', 'b/low']); // Jan, Feb, Mar
});

test('sortRepos: does not mutate the input array', () => {
  const before = sample.map(r => r.full_name);
  GSD.sortRepos(sample, 'stars');
  assert.deepEqual(sample.map(r => r.full_name), before);
});

// ---------------------------------------------------------------------------
// filterByTopics — multi-select AND logic (acceptance §5.4 3.2 ③)
// ---------------------------------------------------------------------------
test('filterByTopics: returns everything when no topic is active', () => {
  assert.equal(GSD.filterByTopics(sample, new Set()).length, 3);
  assert.equal(GSD.filterByTopics(sample, null).length, 3);
});

test('filterByTopics: single active topic keeps repos that have it', () => {
  const out = GSD.filterByTopics(sample, new Set(['x']));
  assert.deepEqual(out.map(r => r.full_name), ['a/high', 'b/low']);
});

test('filterByTopics: multiple active topics use AND (intersection)', () => {
  // only b/low has both x AND y
  const out = GSD.filterByTopics(sample, new Set(['x', 'y']));
  assert.deepEqual(out.map(r => r.full_name), ['b/low']);
});

test('filterByTopics: AND excludes a repo missing any one selected topic', () => {
  // no repo has both x AND z
  const out = GSD.filterByTopics(sample, new Set(['x', 'z']));
  assert.deepEqual(out.map(r => r.full_name), []);
});

// ---------------------------------------------------------------------------
// truncateTopics — top-3 + "+N" fold (acceptance §5.4 3.2 ①)
// ---------------------------------------------------------------------------
test('truncateTopics: shows first 3, counts the remainder', () => {
  const r = GSD.truncateTopics(['a', 'b', 'c', 'd', 'e']);
  assert.deepEqual(r.shown, ['a', 'b', 'c']);
  assert.equal(r.extra, 2);
});

test('truncateTopics: extra is 0 when within the limit', () => {
  assert.equal(GSD.truncateTopics(['a', 'b']).extra, 0);
  assert.equal(GSD.truncateTopics(['a', 'b', 'c']).extra, 0);
  assert.equal(GSD.truncateTopics([]).extra, 0);
});

// ---------------------------------------------------------------------------
// renderTopicsHtml
// ---------------------------------------------------------------------------
test('renderTopicsHtml: one tag per shown topic', () => {
  const html = GSD.renderTopicsHtml(['rss', 'python']);
  assert.equal((html.match(/data-topic=/g) || []).length, 2);
  assert.match(html, /class="topic-tags"/);
});

test('renderTopicsHtml: folds beyond 3 into +N and still shows only 3 tags', () => {
  const html = GSD.renderTopicsHtml(['a', 'b', 'c', 'd', 'e', 'f']);
  assert.match(html, /\+3/);
  assert.equal((html.match(/data-topic=/g) || []).length, 3);
});

test('renderTopicsHtml: marks active topics with the active class', () => {
  const html = GSD.renderTopicsHtml(['rss', 'python'], new Set(['rss']));
  assert.match(html, /class="topic-tag active" data-topic="rss"/);
  assert.match(html, /data-topic="python"/);
  assert.doesNotMatch(html, /class="topic-tag active" data-topic="python"/);
});

test('renderTopicsHtml: escapes HTML metacharacters in topic names', () => {
  const html = GSD.renderTopicsHtml(['a<b>&"x']);
  assert.match(html, /data-topic="a&lt;b&gt;&amp;&quot;x"/);
});

// ---------------------------------------------------------------------------
// renderAvatarHtml (acceptance §5.4 3.4)
// ---------------------------------------------------------------------------
test('renderAvatarHtml: empty string when there is no avatar', () => {
  assert.equal(GSD.renderAvatarHtml(null), '');
  assert.equal(GSD.renderAvatarHtml(undefined), '');
  assert.equal(GSD.renderAvatarHtml(''), '');
});

test('renderAvatarHtml: lazy 20x20 img with onerror fallback when present', () => {
  const html = GSD.renderAvatarHtml('https://avatars.githubusercontent.com/u/1?v=4');
  assert.match(html, /class="avatar"/);
  assert.match(html, /width="20"/);
  assert.match(html, /height="20"/);
  assert.match(html, /loading="lazy"/);
  assert.match(html, /onerror=/);
  assert.match(html, /src="https:\/\/avatars/);
});

// ---------------------------------------------------------------------------
// resolveTheme (acceptance §5.4 3.1)
// ---------------------------------------------------------------------------
test('resolveTheme: explicit saved choice always wins', () => {
  assert.equal(GSD.resolveTheme('dark', true), 'dark');
  assert.equal(GSD.resolveTheme('dark', false), 'dark');
  assert.equal(GSD.resolveTheme('light', true), 'light');
  assert.equal(GSD.resolveTheme('light', false), 'light');
});

test('resolveTheme: follows OS preference when nothing is saved', () => {
  assert.equal(GSD.resolveTheme(null, true), 'dark');
  assert.equal(GSD.resolveTheme(undefined, false), 'light');
});

// ---------------------------------------------------------------------------
// nextSortDir (acceptance §5.4 3.5 ②④)
// ---------------------------------------------------------------------------
test('nextSortDir: clicking the active sort key again flips the direction', () => {
  assert.equal(GSD.nextSortDir('stars', 'stars', 'desc'), 'asc');
  assert.equal(GSD.nextSortDir('stars', 'stars', 'asc'), 'desc');
});

test('nextSortDir: switching sort key resets to default descending', () => {
  assert.equal(GSD.nextSortDir('stars', 'starred_at', 'asc'), 'desc');
  assert.equal(GSD.nextSortDir('starred_at', 'stars', 'desc'), 'desc');
});

// ---------------------------------------------------------------------------
// Integration on real data/stars.json (no DOM)
// ---------------------------------------------------------------------------
test('integration: real data — AND filter narrows, tags fold, avatars render', () => {
  const data = JSON.parse(fs.readFileSync(new URL('../data/stars.json', import.meta.url)));
  const rsshub = data.find(r => r.full_name === 'DIYgod/RSSHub');
  assert.ok(rsshub, 'fixture repo present');
  assert.ok(rsshub.topics.includes('rss'));

  const filtered = GSD.filterByTopics(data, new Set(['rss', 'python']));
  assert.ok(filtered.every(r => r.topics.includes('rss') && r.topics.includes('python')),
    'every surviving repo must contain ALL active topics (AND)');
  assert.ok(filtered.length < data.length, 'AND filter must narrow the set');

  // RSSHub has many topics -> exactly 3 tags + a +N fold
  const html = GSD.renderTopicsHtml(rsshub.topics, new Set());
  assert.equal((html.match(/data-topic=/g) || []).length, 3);
  assert.match(html, /\+\d+/);

  // avatars are present in the dataset and render to an <img>
  const withAvatar = data.find(r => r.owner_avatar);
  assert.match(GSD.renderAvatarHtml(withAvatar.owner_avatar), /class="avatar"/);
});

// ===========================================================================
// Functional category index (docs/superpowers/specs/2026-10-09-category-index-design.md §2, §4)
// ===========================================================================
const taxonomy = [
  { id: 'ai-coding', name: 'AI 编码代理', children: [
    { id: 'ai-coding/agents', name: '编码代理 CLI' },
    { id: 'ai-coding/clients', name: '客户端与工作台' },
  ] },
  { id: 'mcp', name: 'MCP 与工具接入', children: [
    { id: 'mcp/servers', name: 'MCP 服务器' },
  ] },
  { id: 'resources', name: '资源合集', children: [] },
  { id: 'other', name: '其他 / 待确认' },
];

const catRepos = [
  { full_name: 'o/cli' },
  { full_name: 'o/client' },
  { full_name: 'o/server' },
  { full_name: 'o/awesome' },
  { full_name: 'o/missing' },
  { full_name: 'o/bogus' },
  { full_name: 'o/review' },
];

const assignments = {
  'o/cli': { primary: 'ai-coding/agents', secondary: [], source: 'seed' },
  'o/client': { primary: 'ai-coding/clients', secondary: ['mcp/servers'], source: 'seed' },
  'o/server': { primary: 'mcp/servers', secondary: ['nope/unknown', 'mcp/servers'], source: 'llm' },
  'o/awesome': { primary: 'resources', secondary: ['ai-coding/agents'], source: 'seed' },
  'o/bogus': { primary: 'other/unsorted', secondary: [], source: 'rule' },
  'o/review': { primary: 'mcp/servers', secondary: [], source: 'llm', needs_review: true },
};

const catMap = GSD.resolveCategories(catRepos, taxonomy, assignments, {
  'o/cli': { primary: 'mcp/servers', secondary: ['ai-coding/agents'] },
});

// ---------------------------------------------------------------------------
// resolveCategories
// ---------------------------------------------------------------------------
test('resolveCategories: overrides win over assignments', () => {
  assert.deepEqual(catMap['o/cli'], {
    primary: 'mcp/servers', secondary: ['ai-coding/agents'], source: 'override', needsReview: false, unassigned: false,
  });
});

test('resolveCategories: missing assignment resolves to other + unassigned', () => {
  assert.equal(catMap['o/missing'].primary, 'other');
  assert.equal(catMap['o/missing'].unassigned, true);
  assert.deepEqual(catMap['o/missing'].secondary, []);
});

test('resolveCategories: primary id not in taxonomy resolves to other + unassigned', () => {
  assert.equal(catMap['o/bogus'].primary, 'other');
  assert.equal(catMap['o/bogus'].unassigned, true);
});

test('resolveCategories: drops unknown and duplicate secondary ids', () => {
  assert.deepEqual(catMap['o/server'].secondary, []);
  assert.deepEqual(catMap['o/client'].secondary, ['mcp/servers']);
});

test('resolveCategories: rule-sourced assignments always need review and keep their source', () => {
  const m = GSD.resolveCategories([{ full_name: 'r/1' }, { full_name: 'r/2' }], taxonomy, {
    'r/1': { primary: 'mcp/servers', secondary: [], source: 'rule' },
    'r/2': { primary: 'other', secondary: [], source: 'rule', needs_review: true },
  }, {});
  assert.equal(m['r/1'].needsReview, true);
  assert.equal(m['r/1'].source, 'rule');
  assert.equal(m['r/2'].primary, 'other');
  assert.equal(m['r/2'].needsReview, true);
  assert.equal(m['r/2'].unassigned, false);
  assert.equal(catMap['o/missing'].source, null);
});

test('resolveCategories: needs_review flag is surfaced; top-level ids are valid primaries', () => {
  assert.equal(catMap['o/review'].needsReview, true);
  assert.equal(catMap['o/review'].unassigned, false);
  assert.equal(catMap['o/awesome'].primary, 'resources');
  assert.equal(catMap['o/awesome'].unassigned, false);
});

test('resolveCategories: an invalid override falls back to the assignment', () => {
  const m = GSD.resolveCategories([{ full_name: 'o/client' }], taxonomy, assignments,
    { 'o/client': { primary: 'zzz' } });
  assert.equal(m['o/client'].primary, 'ai-coding/clients');
});

test('resolveCategories: tolerates null assignments/overrides', () => {
  const m = GSD.resolveCategories([{ full_name: 'x/y' }], taxonomy, null, null);
  assert.equal(m['x/y'].primary, 'other');
  assert.equal(m['x/y'].unassigned, true);
});

test('resolveCategories: malformed entries never throw and are normalized', () => {
  const names = ['m/1', 'm/2', 'm/3', 'm/4', 'm/5', 'm/6'];
  const m = GSD.resolveCategories(names.map(full_name => ({ full_name })), taxonomy, {
    'm/1': { primary: 'mcp/servers', secondary: 'ai-coding/agents', source: 'seed' },
    'm/2': { primary: 'mcp/servers', secondary: null, source: 42 },
    'm/3': { primary: ['mcp/servers'], secondary: [], source: 'seed' },
    'm/4': null,
    'm/5': 'mcp/servers',
    'm/6': { primary: 'mcp/servers', secondary: [['resources'], 42, null, {}, 'resources'], source: 'seed' },
  }, {
    'm/2': { primary: { id: 'resources' }, secondary: 'x' },
    'm/4': 'resources',
    'm/6': { primary: 'resources', secondary: { 0: 'mcp/servers' } },
  });
  assert.deepEqual(m['m/1'], {
    primary: 'mcp/servers', secondary: [], source: 'seed', needsReview: false, unassigned: false,
  });
  assert.equal(m['m/2'].primary, 'mcp/servers');
  assert.deepEqual(m['m/2'].secondary, []);
  assert.equal(m['m/2'].source, null);
  for (const name of ['m/3', 'm/4', 'm/5']) {
    assert.equal(m[name].primary, 'other', name);
    assert.equal(m[name].unassigned, true, name);
  }
  assert.equal(m['m/6'].primary, 'resources');
  assert.equal(m['m/6'].source, 'override');
  assert.deepEqual(m['m/6'].secondary, []);
});

test('resolveCategories: non-object containers and malformed taxonomy children are ignored', () => {
  const m = GSD.resolveCategories([{ full_name: 'x/y' }], taxonomy, 'oops', ['x/y']);
  assert.equal(m['x/y'].unassigned, true);
  const odd = [{ id: 'a', name: 'A', children: 'nope' }, { id: 'other', name: '其他', children: {} }];
  const n = GSD.resolveCategories([{ full_name: 'x/y' }], odd, { 'x/y': { primary: 'a', secondary: [] } }, {});
  assert.equal(n['x/y'].primary, 'a');
});

// ---------------------------------------------------------------------------
// categoryAncestors / categoryPath
// ---------------------------------------------------------------------------
test('categoryAncestors: child -> [child, top]; top -> [top]; unknown -> []', () => {
  assert.deepEqual(GSD.categoryAncestors('ai-coding/clients', taxonomy), ['ai-coding/clients', 'ai-coding']);
  assert.deepEqual(GSD.categoryAncestors('resources', taxonomy), ['resources']);
  assert.deepEqual(GSD.categoryAncestors('nope', taxonomy), []);
});

test('categoryPath: returns top-level and child names', () => {
  assert.deepEqual(GSD.categoryPath('ai-coding/clients', taxonomy), ['AI 编码代理', '客户端与工作台']);
  assert.deepEqual(GSD.categoryPath('resources', taxonomy), ['资源合集']);
  assert.deepEqual(GSD.categoryPath('nope', taxonomy), []);
});

// ---------------------------------------------------------------------------
// matchesCategories
// ---------------------------------------------------------------------------
test('matchesCategories: empty selection matches everything', () => {
  assert.equal(GSD.matchesCategories(catMap['o/cli'], new Set(), taxonomy), true);
  assert.equal(GSD.matchesCategories(catMap['o/cli'], null, taxonomy), true);
});

test('matchesCategories: top-level selection matches its children via primary', () => {
  assert.equal(GSD.matchesCategories(catMap['o/client'], new Set(['ai-coding']), taxonomy), true);
  assert.equal(GSD.matchesCategories(catMap['o/server'], new Set(['ai-coding']), taxonomy), false);
});

test('matchesCategories: secondary categories count as a match', () => {
  // o/client is primary ai-coding/clients, secondary mcp/servers
  assert.equal(GSD.matchesCategories(catMap['o/client'], new Set(['mcp/servers']), taxonomy), true);
  assert.equal(GSD.matchesCategories(catMap['o/client'], new Set(['mcp']), taxonomy), true);
  // o/awesome: primary resources, secondary ai-coding/agents
  assert.equal(GSD.matchesCategories(catMap['o/awesome'], new Set(['ai-coding']), taxonomy), true);
});

test('matchesCategories: child selection does not match siblings', () => {
  assert.equal(GSD.matchesCategories(catMap['o/client'], new Set(['ai-coding/agents']), taxonomy), false);
});

test('matchesCategories: multiple selected categories are OR-ed', () => {
  const sel = new Set(['resources', 'ai-coding/agents']);
  const hits = catRepos.filter(r => GSD.matchesCategories(catMap[r.full_name], sel, taxonomy)).map(r => r.full_name);
  assert.deepEqual(hits, ['o/cli', 'o/awesome']);
});

test('matchesCategories: the review pseudo-category matches needs_review or unassigned repos', () => {
  assert.equal(GSD.REVIEW_CATEGORY, 'review');
  const sel = new Set(['review']);
  const hits = catRepos.filter(r => GSD.matchesCategories(catMap[r.full_name], sel, taxonomy)).map(r => r.full_name);
  // o/missing (unassigned), o/bogus (invalid id -> unassigned), o/review (needs_review)
  assert.deepEqual(hits, ['o/missing', 'o/bogus', 'o/review']);
});

test('matchesCategories: review is OR-ed with real categories', () => {
  const sel = new Set(['review', 'resources']);
  const hits = catRepos.filter(r => GSD.matchesCategories(catMap[r.full_name], sel, taxonomy)).map(r => r.full_name);
  assert.deepEqual(hits, ['o/awesome', 'o/missing', 'o/bogus', 'o/review']);
});

// ---------------------------------------------------------------------------
// toggleCategory
// ---------------------------------------------------------------------------
test('toggleCategory: adds and removes ids without mutating the input', () => {
  const s0 = new Set();
  const s1 = GSD.toggleCategory(s0, 'mcp', taxonomy);
  assert.deepEqual([...s1], ['mcp']);
  assert.equal(s0.size, 0);
  assert.deepEqual([...GSD.toggleCategory(s1, 'mcp', taxonomy)], []);
});

test('toggleCategory: selecting a top-level absorbs its selected children', () => {
  const s = GSD.toggleCategory(new Set(['ai-coding/agents', 'mcp']), 'ai-coding', taxonomy);
  assert.deepEqual([...s].sort(), ['ai-coding', 'mcp']);
});

test('toggleCategory: selecting a child of a selected top-level narrows to the child', () => {
  const s = GSD.toggleCategory(new Set(['ai-coding']), 'ai-coding/clients', taxonomy);
  assert.deepEqual([...s], ['ai-coding/clients']);
});

// ---------------------------------------------------------------------------
// countCategories
// ---------------------------------------------------------------------------
test('countCategories: counts primary + secondary, once per repo per category', () => {
  const c = GSD.countCategories(catRepos, catMap, taxonomy);
  // o/cli(over: mcp/servers + ai-coding/agents), o/client(ai-coding/clients + mcp/servers), o/awesome(resources + ai-coding/agents)
  assert.equal(c['ai-coding'], 3);
  assert.equal(c['ai-coding/agents'], 2);
  assert.equal(c['ai-coding/clients'], 1);
  // o/cli, o/client, o/server, o/review
  assert.equal(c['mcp'], 4);
  assert.equal(c['mcp/servers'], 4);
  assert.equal(c['resources'], 1);
  assert.equal(c['other'], 2);
  assert.equal(c['review'], 3);
});

test('countCategories: every taxonomy id is present, zero when unused', () => {
  const c = GSD.countCategories([], catMap, taxonomy);
  assert.deepEqual(Object.keys(c).sort(), [
    'ai-coding', 'ai-coding/agents', 'ai-coding/clients', 'mcp', 'mcp/servers', 'other', 'resources', 'review',
  ]);
  assert.ok(Object.values(c).every(n => n === 0));
});

// ---------------------------------------------------------------------------
// groupByPrimary
// ---------------------------------------------------------------------------
test('groupByPrimary: sections follow taxonomy order and skip empty ones', () => {
  const g = GSD.groupByPrimary(catRepos, catMap, taxonomy);
  assert.deepEqual(g.map(s => s.id), ['ai-coding/clients', 'mcp/servers', 'resources', 'other']);
  assert.deepEqual(g[0].path, ['AI 编码代理', '客户端与工作台']);
  assert.deepEqual(g[2].path, ['资源合集']);
});

test('groupByPrimary: each repo appears exactly once, keeping input order within a section', () => {
  const g = GSD.groupByPrimary(catRepos, catMap, taxonomy);
  const all = g.flatMap(s => s.items.map(r => r.full_name));
  assert.equal(all.length, catRepos.length);
  assert.equal(new Set(all).size, catRepos.length);
  assert.deepEqual(g[1].items.map(r => r.full_name), ['o/cli', 'o/server', 'o/review']);
});

test('groupByPrimary: a top-level primary section precedes its children', () => {
  const m = { 'a/1': { primary: 'ai-coding/agents', secondary: [] }, 'a/2': { primary: 'ai-coding', secondary: [] } };
  const g = GSD.groupByPrimary([{ full_name: 'a/1' }, { full_name: 'a/2' }], m, taxonomy);
  assert.deepEqual(g.map(s => s.id), ['ai-coding', 'ai-coding/agents']);
});

// ---------------------------------------------------------------------------
// parseHashState / buildHashState
// ---------------------------------------------------------------------------
test('buildHashState: omits defaults and keeps ids readable', () => {
  assert.equal(GSD.buildHashState({ cat: [], topic: [], q: '', sort: 'stars', dir: 'desc', group: false }), '');
  assert.equal(
    GSD.buildHashState({ cat: new Set(['ai-coding/clients', 'mcp']), lang: 'Go', topic: ['mcp'], q: 'agent',
      sort: 'starred_at', dir: 'asc', group: true }),
    'cat=ai-coding/clients,mcp&lang=Go&topic=mcp&q=agent&sort=starred_at&dir=asc&group=1');
});

test('parseHashState: reads every field', () => {
  const s = GSD.parseHashState('#cat=ai-coding/clients,mcp&lang=Go&topic=mcp&q=agent&sort=stars&dir=desc&group=1');
  assert.deepEqual(s, {
    cat: ['ai-coding/clients', 'mcp'], lang: 'Go', topic: ['mcp'], q: 'agent', sort: 'stars', dir: 'desc', group: true,
  });
});

test('parseHashState: unspecified fields are null/empty so callers apply defaults', () => {
  assert.deepEqual(GSD.parseHashState(''), { cat: [], lang: null, topic: [], q: '', sort: null, dir: null, group: null });
  assert.equal(GSD.parseHashState('#group=0').group, false);
});

test('hash state round-trips through build -> parse, including awkward characters', () => {
  const state = { cat: ['mcp'], lang: 'C++', topic: ['a,b', 'c'], q: '中文 & x=1', sort: 'pushed_at', dir: 'asc', group: true };
  const back = GSD.parseHashState('#' + GSD.buildHashState(state));
  assert.deepEqual(back, state);
});

test('parseHashState: ignores junk keys, invalid values and malformed encoding', () => {
  const s = GSD.parseHashState('#foo=bar&sort=hacker&dir=sideways&group=maybe&q=%E0%A4&=x&cat=&topic=,,');
  assert.deepEqual(s, { cat: [], lang: null, topic: [], q: '', sort: null, dir: null, group: null });
});

test('hash state carries the review pseudo-category like any other category', () => {
  const h = GSD.buildHashState({ cat: ['mcp', 'review'] });
  assert.equal(h, 'cat=mcp,review');
  assert.deepEqual(GSD.parseHashState('#' + h, { cat: ['mcp', 'review'] }).cat, ['mcp', 'review']);
});

test('parseHashState: drops values not in the known sets when provided', () => {
  const s = GSD.parseHashState('#cat=mcp,nope,mcp&lang=Cobol&topic=rss,zzz', {
    cat: ['mcp', 'ai-coding'], lang: new Set(['Go']), topic: ['rss'],
  });
  assert.deepEqual(s.cat, ['mcp']);
  assert.equal(s.lang, null);
  assert.deepEqual(s.topic, ['rss']);
});

// ---------------------------------------------------------------------------
// searchHaystack / matchesQuery
// ---------------------------------------------------------------------------
test('search: matches name, zh/en description, topics, language and category names', () => {
  const repo = { full_name: 'Acme/Rocket', description: 'Fast thing', description_zh: '很快的东西',
    language: 'Rust', topics: ['launcher'] };
  const hay = GSD.searchHaystack(repo, catMap['o/client'], taxonomy);
  for (const q of ['rocket', 'FAST', '很快', 'launcher', 'rust', '客户端', 'AI 编码', 'mcp 服务器']) {
    assert.equal(GSD.matchesQuery(hay, q), true, q);
  }
  assert.equal(GSD.matchesQuery(hay, 'rocket nope'), false, 'all terms must match');
  assert.equal(GSD.matchesQuery(hay, '   '), true, 'blank query matches');
});

test('search: works without category info', () => {
  const hay = GSD.searchHaystack({ full_name: 'a/b', topics: null }, null, null);
  assert.equal(GSD.matchesQuery(hay, 'a/b'), true);
});

// ---------------------------------------------------------------------------
// Integration on real category data
// ---------------------------------------------------------------------------
test('integration: real category data resolves every repo and groups each exactly once', () => {
  const read = f => JSON.parse(fs.readFileSync(new URL('../data/' + f, import.meta.url)));
  const data = read('stars.json');
  const tax = read('categories.json').taxonomy;
  const map = GSD.resolveCategories(data, tax, read('category_assignments.json'), read('category_overrides.json'));
  assert.equal(Object.keys(map).length, data.length);
  for (const r of data) assert.ok(GSD.categoryAncestors(map[r.full_name].primary, tax).length, r.full_name);
  const groups = GSD.groupByPrimary(data, map, tax);
  assert.equal(groups.reduce((n, g) => n + g.items.length, 0), data.length);
  const counts = GSD.countCategories(data, map, tax);
  const topSum = tax.reduce((n, t) => n + counts[t.id], 0);
  assert.ok(topSum >= data.length, 'secondary hits can only add to top-level totals');
});
