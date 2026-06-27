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
