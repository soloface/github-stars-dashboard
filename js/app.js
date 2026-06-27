// ============================================================
// Data & State
// ============================================================
const PER_PAGE = 12;
let repos = [];
let filtered = [];
let activeLangs = new Set();
let activeTopics = new Set();
let currentSort = 'stars';
let sortDir = 'desc'; // 'asc' | 'desc' — default keeps prior behavior (stars desc, dates newest-first)
let currentPage = 1;
let searchTerm = '';

const langColors = {
  TypeScript: '#3178c6', Python: '#3572A9', JavaScript: '#f1e05a',
  Shell: '#89e051', Go: '#00ADD8', Rust: '#dea584',
  'C++': '#f34b7d', HTML: '#e34c26', Vue: '#41b883', PHP: '#4F5D95',
};

// ============================================================
// Fetch Data
// ============================================================
async function loadData() {
  try {
    const resp = await fetch('data/stars.json');
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    repos = await resp.json();
    buildLangFilters();
    applyAll();
    document.getElementById('syncTime').textContent =
      '已同步 ' + new Date().toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' });
  } catch (e) {
    document.getElementById('repoGrid').innerHTML =
      '<div class="state-msg"><h3>⚠ DATA LOAD FAILED</h3><p class="mono">' + e.message + '</p><p style="margin-top:12px"><button class="sort-btn" onclick="loadData()">RETRY</button></p></div>';
  }
}

// ============================================================
// Language Filters
// ============================================================
function buildLangFilters() {
  const counts = {};
  repos.forEach(r => { if (r.language) counts[r.language] = (counts[r.language] || 0) + 1; });
  const sorted = Object.entries(counts).sort((a, b) => b[1] - a[1]);
  const container = document.getElementById('langFilters');
  sorted.forEach(([lang, count]) => {
    const cls = lang.toLowerCase().replace('++', 'pp').replace('#', 'sharp').replace(/\s+/g, '_');
    const colorClass = langColors[lang] ? lang.toLowerCase().replace('++', 'pp').replace(/\s+/g, '') : 'other';
    const btn = document.createElement('button');
    btn.className = 'lang-toggle ' + colorClass;
    btn.dataset.lang = lang;
    btn.textContent = lang + ' ' + count;
    btn.addEventListener('click', () => toggleLang(lang, btn));
    container.appendChild(btn);
  });
  document.getElementById('filterAll').addEventListener('click', () => {
    activeLangs.clear();
    container.querySelectorAll('.lang-toggle').forEach(b => b.classList.remove('active'));
    applyAll();
  });
}

function toggleLang(lang, btn) {
  if (activeLangs.has(lang)) {
    activeLangs.delete(lang);
    btn.classList.remove('active');
  } else {
    activeLangs.add(lang);
    btn.classList.add('active');
  }
  currentPage = 1;
  applyAll();
}

// ============================================================
// Filtering, Sorting, Pagination
// ============================================================
function applyAll() {
  // Filter by language + search term
  filtered = repos.filter(r => {
    if (activeLangs.size > 0 && !activeLangs.has(r.language)) return false;
    if (searchTerm) {
      const q = searchTerm.toLowerCase();
      const descText = (r.description_zh || r.description || '').toLowerCase();
      return r.full_name.toLowerCase().includes(q) || descText.includes(q);
    }
    return true;
  });

  // Filter by topics (multi-select AND) — pure logic in GSD.filterByTopics
  filtered = GSD.filterByTopics(filtered, activeTopics);

  // Sort — direction-aware (default desc). Pure logic in GSD.sortRepos.
  filtered = GSD.sortRepos(filtered, currentSort, sortDir);

  // Update stats
  const totalPages = Math.ceil(filtered.length / PER_PAGE) || 1;
  if (currentPage > totalPages) currentPage = totalPages;

  document.getElementById('totalCount').textContent = repos.length;
  document.getElementById('resultsBadge').textContent = filtered.length + ' repos';

  // Top 5 languages in stats panel
  const langCounts = {};
  filtered.forEach(r => { if (r.language) langCounts[r.language] = (langCounts[r.language] || 0) + 1; });
  const topLangs = Object.entries(langCounts).sort((a, b) => b[1] - a[1]).slice(0, 5);
  const dotsEl = document.getElementById('langDots');
  dotsEl.innerHTML = topLangs.map(([l, c]) => {
    const cls = l.toLowerCase().replace('++', 'pp').replace(/\s+/g, '');
    return '<span class="lang-dot ' + (langColors[l] ? cls : 'other') + '">' + l + ' ' + c + '</span>';
  }).join('');

  // Render cards
  const start = (currentPage - 1) * PER_PAGE;
  const page = filtered.slice(start, start + PER_PAGE);
  renderCards(page);
  renderPagination(totalPages);
}

// ============================================================
// Card Rendering
// ============================================================
function renderCards(items) {
  const grid = document.getElementById('repoGrid');
  if (items.length === 0) {
    grid.innerHTML = '<div class="state-msg"><h3>No matching repos</h3><p class="mono">Try adjusting your search or filters.</p></div>';
    return;
  }

  grid.innerHTML = items.map(r => {
    const name = r.full_name;
    const parts = name.split('/');
    const owner = parts[0];
    const repo = parts.slice(1).join('/');
    const desc = r.description_zh || r.description || '暂无简介';
    const stars = formatNum(r.stargazers_count || 0);
    const forks = formatNum(r.forks_count || 0);
    const lang = r.language;
    const langClass = lang ? lang.toLowerCase().replace('++', 'pp').replace(/\s+/g, '') : '';
    const starredDate = r.starred_at ? new Date(r.starred_at).toLocaleDateString('en-CA') : '';
    const updatedDate = r.pushed_at ? timeAgo(r.pushed_at) : '';
    const langClassResolved = langColors[lang] ? langClass : 'other';

    const topicHtml = (r.topics && r.topics.length)
      ? GSD.renderTopicsHtml(r.topics, activeTopics)
      : '';

    return '<div class="repo-card">' +
      '<div class="card-header">' +
        '<a class="card-name" href="' + escHtml(r.html_url) + '" target="_blank" rel="noopener">' +
          GSD.renderAvatarHtml(r.owner_avatar) +
          '<span class="card-owner">' + escHtml(owner) + '</span> / ' + escHtml(repo) +
        '</a>' +
      '</div>' +
      '<p class="card-desc">' + escHtml(desc) + '</p>' +
      topicHtml +
      '<div class="card-meta">' +
        '<span class="meta-item meta-stars">★ ' + stars + '</span>' +
        '<span class="meta-item meta-forks">⑂ ' + forks + '</span>' +
        (lang ? '<span class="meta-item meta-lang ' + langClassResolved + '">' + escHtml(lang) + '</span>' : '') +
        '<span class="card-date">' + escHtml(updatedDate) + '</span>' +
      '</div>' +
    '</div>';
  }).join('');
}

// ============================================================
// Pagination Rendering
// ============================================================
function renderPagination(totalPages) {
  const el = document.getElementById('pagination');
  if (totalPages <= 1) { el.innerHTML = ''; return; }

  let html = '';
  html += '<button class="page-btn" data-page="' + (currentPage - 1) + '"' + (currentPage === 1 ? ' disabled' : '') + '>‹</button>';

  for (let i = 1; i <= totalPages; i++) {
    if (totalPages > 7) {
      if (i === 1 || i === totalPages || (i >= currentPage - 1 && i <= currentPage + 1)) {
        html += '<button class="page-btn' + (i === currentPage ? ' active' : '') + '" data-page="' + i + '">' + i + '</button>';
      } else if (i === currentPage - 2 || i === currentPage + 2) {
        html += '<button class="page-btn" disabled>…</button>';
      }
    } else {
      html += '<button class="page-btn' + (i === currentPage ? ' active' : '') + '" data-page="' + i + '">' + i + '</button>';
    }
  }

  html += '<button class="page-btn" data-page="' + (currentPage + 1) + '"' + (currentPage === totalPages ? ' disabled' : '') + '>›</button>';
  el.innerHTML = html;

  el.querySelectorAll('.page-btn[data-page]').forEach(btn => {
    btn.addEventListener('click', () => {
      const p = parseInt(btn.dataset.page);
      if (p >= 1 && p <= totalPages) {
        currentPage = p;
        applyAll();
        window.scrollTo({ top: document.querySelector('.repo-grid').offsetTop - 20, behavior: 'smooth' });
      }
    });
  });
}

// ============================================================
// Sort direction (▲/▼) — reflect current sort key + direction
// ============================================================
function updateSortButtons() {
  document.querySelectorAll('.sort-btn').forEach(b => {
    const isActive = b.dataset.sort === currentSort;
    b.classList.toggle('active', isActive);
    b.classList.toggle('asc', isActive && sortDir === 'asc');
  });
}

// ============================================================
// Theme (Dark mode) — init / toggle / persist / follow OS
// ============================================================
function initTheme() {
  const saved = localStorage.getItem('theme');
  const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
  document.documentElement.setAttribute('data-theme', GSD.resolveTheme(saved, prefersDark));
}

function toggleTheme() {
  const current = document.documentElement.getAttribute('data-theme');
  const next = current === 'dark' ? 'light' : 'dark';
  document.documentElement.setAttribute('data-theme', next);
  localStorage.setItem('theme', next);
}

// ============================================================
// Event Listeners
// ============================================================
document.querySelectorAll('.sort-btn').forEach(btn => {
  btn.addEventListener('click', () => {
    const clicked = btn.dataset.sort;
    // Same key → flip direction; different key → reset to default desc.
    sortDir = GSD.nextSortDir(currentSort, clicked, sortDir);
    currentSort = clicked;
    updateSortButtons();
    currentPage = 1;
    applyAll();
  });
});

document.getElementById('themeToggle').addEventListener('click', toggleTheme);

// Follow OS theme changes only while the user hasn't made an explicit choice.
window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', (e) => {
  if (!localStorage.getItem('theme')) {
    document.documentElement.setAttribute('data-theme', GSD.resolveTheme(null, e.matches));
  }
});

// Topic tag click — toggle membership in the activeTopics AND-filter.
// Delegated on the stable #repoGrid so it survives re-renders.
document.getElementById('repoGrid').addEventListener('click', (e) => {
  const tag = e.target.closest('.topic-tag');
  if (!tag || !tag.dataset.topic) return; // ignore the non-interactive "+N"
  const topic = tag.dataset.topic;
  if (activeTopics.has(topic)) activeTopics.delete(topic);
  else activeTopics.add(topic);
  currentPage = 1;
  applyAll();
});

let debounceTimer;
document.getElementById('searchInput').addEventListener('input', (e) => {
  clearTimeout(debounceTimer);
  debounceTimer = setTimeout(() => {
    searchTerm = e.target.value.trim();
    currentPage = 1;
    applyAll();
  }, 200);
});

// ============================================================
// Utilities
// ============================================================
function formatNum(n) {
  if (n >= 100000) return (n / 1000).toFixed(0) + 'k';
  if (n >= 10000) return (n / 1000).toFixed(1) + 'k';
  if (n >= 1000) return (n / 1000).toFixed(1) + 'k';
  return String(n);
}

function timeAgo(dateStr) {
  const diff = Date.now() - new Date(dateStr).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 60) return mins + 'm ago';
  const hours = Math.floor(mins / 60);
  if (hours < 24) return hours + 'h ago';
  const days = Math.floor(hours / 24);
  if (days < 7) return days + 'd ago';
  if (days < 30) return Math.floor(days / 7) + 'w ago';
  return Math.floor(days / 30) + 'mo ago';
}

function escHtml(s) {
  const d = document.createElement('div');
  d.textContent = s;
  return d.innerHTML;
}

// ============================================================
// Init
// ============================================================
initTheme();
updateSortButtons();
loadData();
