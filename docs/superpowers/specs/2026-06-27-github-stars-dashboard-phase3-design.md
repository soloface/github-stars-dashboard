# github-stars-dashboard Phase 3 设计文档

> **Status**: DRAFT → 待审批 | **Date**: 2026-06-27 | **Author**: Coding 软件架构师 (Hermes, DeepSeek V4 Pro)
> **基于**: spec.md §6（SOL-77）、Phase 1 产物实文件审计

---

## 1. 现状审计（Phase 1 产物，逐个功能对照）

| # | 功能 | 优先级 | 数据层 | UI 层 | 结论 |
|---|------|:---:|--------|-------|:---:|
| 3.1 | Dark mode | P1 | — | ❌ 无 `prefers-color-scheme`、无 `[data-theme]`、无 toggle | ❌ 完全缺失 |
| 3.2 | Topics 标签展示+筛选 | P1 | ✅ `stars.json` 有 `topics` 字段（`fetch_stars.py` L64 收集） | ❌ JS `renderCards()` 不渲染 topics | ❌ 数据已有，UI 缺失 |
| 3.3 | README（中英双语） | P1 | — | — | ❌ 文件不存在 |
| 3.4 | Owner avatar | P2 | ✅ `stars.json` 有 `owner_avatar`（`fetch_stars.py` L65 收集） | ❌ JS `renderCards()` 不渲染 `<img>` | ⚠️ 数据已有，UI 缺失 |
| 3.5 | 排序升降序 | P2 | — | ❌ JS `applyAll()` sort 固定方向，无 `sortDir` 状态、无 toggle | ❌ 完全缺失 |
| 3.6 | `lang="zh-CN"` | P2 | — | ❌ `index.html` L2 现为 `lang="en"` | ❌ 一行改动 |

### 详细说明

#### 3.1 Dark Mode — 现状

```css
/* css/style.css L4 — 当前只有 :root 定义 light token */
:root {
  --bg: #e0e5ec;
  --panel: #f0f2f5;
  --shadow-dark: #babecc;
  --shadow-light: #ffffff;
  --text-primary: #2d3436;
  ...
}
```

缺失：
- 无 `@media (prefers-color-scheme: dark)` 块
- 无 `[data-theme="dark"]` 选择器覆盖
- `index.html` 无 theme toggle 按钮
- `js/app.js` 无 `localStorage` 主题持久化

#### 3.2 Topics — 现状

```javascript
// scripts/fetch_stars.py L64 — 数据已采集
"topics": repo.get("topics") or [],

// js/app.js renderCards() L133-161 — 零 topics 相关代码
// card 渲染中没有任何 topics 标签
```

`stars.json` 示例：RSSHub 有 18 个 topics（bilibili, douban, rss, telegram, twitter...），BettaFish 有 5 个 topics（agent-framework, data-analysis...）。

#### 3.4 Owner Avatar — 现状

```javascript
// js/app.js renderCards() L149 — card-header 只有文本
'<a class="card-name" href="...">' +
  '<span class="card-owner">' + escHtml(owner) + '</span> / ' + escHtml(repo) +
'</a>'

// owner_avatar 存在但未使用
// data 示例: "owner_avatar": "https://avatars.githubusercontent.com/u/8266075?v=4"
```

#### 3.5 排序方向 — 现状

```javascript
// js/app.js L89-96 — applyAll() sort 固定方向
filtered.sort((a, b) => {
  switch (currentSort) {
    case 'stars': return (b.stargazers_count || 0) - (a.stargazers_count || 0);  // 固定降序
    case 'starred_at': return new Date(b.starred_at || 0) - new Date(a.starred_at || 0); // 固定最新在前
    ...
  }
});
// 无 sortDir 变量，无升序降序切换
```

---

## 2. 工作量与风险评估

| # | 功能 | 涉及文件 | 预估行数 | 类型 | 风险 | 理由 |
|---|------|----------|:---:|------|:---:|------|
| 3.1 | Dark mode | `css/style.css` + `index.html` + `js/app.js` | +135 | 前端 | 🟢 低 | 纯 CSS 变量覆盖，neumorphism 反转值 spec.md §7 已给定 |
| 3.2 | Topics 标签+筛选 | `css/style.css` + `js/app.js` | +50 | 前端 | 🟢 低 | 复用 language filter 模式，数据已就绪 |
| 3.3 | README | `README.md`（新建） | ~100 | 文档 | 🟢 零 | 纯文档，不涉及代码 |
| 3.4 | Owner avatar | `css/style.css` + `js/app.js` | +15 | 前端 | 🟢 极低 | 一个 `<img>` 标签 + 圆角样式 |
| 3.5 | 排序升降序 | `js/app.js` + `css/style.css` | +25 | 前端 | 🟡 低 | 影响 sort 逻辑，需验证默认方向不变 |
| 3.6 | `lang="zh-CN"` | `index.html` | 1 | 前端 | 🟢 零 | 一个属性修改 |

**总预估增量**：~326 行（前端 ~225 行 + 文档 ~100 行）

**结论**：6 个功能全是前端工作，后端（Python 脚本）零改动，数据层已完备。

---

## 3. 目标架构

### 3.1 目录结构（Phase 3 后）

```
github-stars-dashboard/
├── index.html                        (~75 行，+14：dark mode toggle + lang 修正)
├── css/
│   └── style.css                     (~860 行，+164：dark mode 变量覆盖 + topics 标签 + avatar 圆角 + sort 箭头)
├── js/
│   └── app.js                        (~310 行，+55：theme 管理 + topics 渲染/筛选 + sortDir + avatar 渲染)
├── scripts/
│   ├── fetch_stars.py                (不变)
│   └── translate_descriptions.py     (不变)
├── data/
│   └── stars.json                    (不变)
├── .github/workflows/
│   └── fetch-stars.yml               (不变)
├── README.md                         (新建，~100 行，中英双语)
├── docs/
│   └── superpowers/specs/
│       ├── ...phase1-design.md
│       └── 2026-06-27-github-stars-dashboard-phase3-design.md  (本文件)
└── tests/                            (不变)
```

### 3.2 模块职责表（仅列出 Phase 3 变更的模块）

| 模块 | 当前行数 | 目标行数 | Phase 3 增量 | 职责 |
|------|:---:|:---:|:---:|------|
| `index.html` | 61 | ~75 | +14 | + theme toggle 按钮、lang 修正 |
| `css/style.css` | 696 | ~860 | +164 | + `[data-theme="dark"]` 块、`.topic-tag`、`.sort-arrow`、`img.avatar` |
| `js/app.js` | 255 | ~310 | +55 | + theme init/toggle/persist、topics state+render+filter、sortDir、avatar `<img>` |
| `README.md` | — | ~100 | +100 | 中英双语项目介绍 |

### 3.3 数据流（不变）

Phase 3 不改变任何数据流。所有新功能基于现有 `stars.json` 字段实现，fetch 和 translate 脚本零改动。

---

## 4. 详细设计方案

### 4.1 Dark Mode（3.1）

**CSS 策略**：在 `:root` 下方追加 `[data-theme="dark"]` 选择器块，覆盖所有颜色/阴影 token。spec.md §7 已给出 neumorphism 深色映射值。

```css
/* 新增：style.css 追加 ~140 行 */
[data-theme="dark"] {
  --bg: #1a1d23;
  --panel: #2a2d35;
  --recessed: #14161a;
  --text-primary: #e4e6eb;
  --text-secondary: #a0a4ae;
  --text-muted: #6b7080;
  --shadow-dark: #0d0f12;
  --shadow-light: #3a3d45;
  --shadow-deep: #080a0d;
  --shadow-card: 8px 8px 16px var(--shadow-dark), -8px -8px 16px var(--shadow-light);
  --shadow-floating: 12px 12px 24px var(--shadow-dark), -12px -12px 24px var(--shadow-light);
  --shadow-pressed: inset 6px 6px 12px var(--shadow-dark), inset -6px -6px 12px var(--shadow-light);
  --shadow-recessed: inset 4px 4px 8px var(--shadow-dark), inset -4px -4px 8px var(--shadow-light);
  --shadow-led-green: 0 0 12px 3px rgba(34,197,94,0.7);
  --shadow-led-accent: 0 0 12px 3px rgba(255,71,87,0.7);
}
/* prefers-color-scheme 自动跟随（无手动设置时） */
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) {
    --bg: #1a1d23;
    --panel: #2a2d35;
    --recessed: #14161a;
    --text-primary: #e4e6eb;
    --text-secondary: #a0a4ae;
    --text-muted: #6b7080;
    --shadow-dark: #0d0f12;
    --shadow-light: #3a3d45;
    --shadow-deep: #080a0d;
    --shadow-card: 8px 8px 16px var(--shadow-dark), -8px -8px 16px var(--shadow-light);
    --shadow-floating: 12px 12px 24px var(--shadow-dark), -12px -12px 24px var(--shadow-light);
    --shadow-pressed: inset 6px 6px 12px var(--shadow-dark), inset -6px -6px 12px var(--shadow-light);
    --shadow-recessed: inset 4px 4px 8px var(--shadow-dark), inset -4px -4px 8px var(--shadow-light);
    --shadow-led-green: 0 0 12px 3px rgba(34,197,94,0.7);
    --shadow-led-accent: 0 0 12px 3px rgba(255,71,87,0.7);
  }
}
/* Stats panel 在 dark mode 下颜色调整 */
[data-theme="dark"] .stats-panel {
  background: linear-gradient(135deg, #1a1d23, #14161a);
}
```

**HTML 策略**：topbar 区域新增 toggle 按钮。

```html
<!-- index.html topbar-left 内新增 ~8 行 -->
<button class="theme-toggle" id="themeToggle" aria-label="切换暗色模式" title="切换暗色模式">
  <svg><!-- 太阳/月亮图标 --></svg>
</button>
```

**JS 策略**：新增 theme 管理模块。

```javascript
// js/app.js 新增 ~40 行
function initTheme() {
  const saved = localStorage.getItem('theme');
  const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
  if (saved === 'dark' || (!saved && prefersDark)) {
    document.documentElement.setAttribute('data-theme', 'dark');
  }
}
function toggleTheme() {
  const current = document.documentElement.getAttribute('data-theme');
  const next = current === 'dark' ? 'light' : 'dark';
  document.documentElement.setAttribute('data-theme', next);
  localStorage.setItem('theme', next);
}
// 监听系统主题变化
window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', (e) => {
  if (!localStorage.getItem('theme')) {
    document.documentElement.setAttribute('data-theme', e.matches ? 'dark' : 'light');
  }
});
```

### 4.2 Topics 标签展示+筛选（3.2）

**CSS 策略**：新增 topic tag 样式（~20 行），复用 neumorphism 风格。

```css
/* 新增：style.css 追加 ~20 行 */
.topic-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  margin-top: 4px;
}
.topic-tag {
  padding: 3px 8px;
  border-radius: var(--radius-sm);
  background: var(--recessed);
  box-shadow: var(--shadow-recessed);
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.55rem;
  color: var(--text-muted);
  cursor: pointer;
  transition: all 150ms var(--mech-easing);
  text-transform: lowercase;
}
.topic-tag:hover { color: var(--accent); }
.topic-tag.active {
  background: var(--accent);
  color: var(--accent-foreground);
  box-shadow: inset 2px 2px 4px rgba(0,0,0,0.2);
}
```

**JS 策略**：新增 topics state + render + filter（~30 行）。

```javascript
// js/app.js 新增 state
let activeTopics = new Set();

// renderCards() 内 card 追加
'<div class="topic-tags">' +
  (r.topics || []).slice(0, 3).map(t => 
    '<span class="topic-tag' + (activeTopics.has(t) ? ' active' : '') + '" data-topic="' + escHtml(t) + '">' + escHtml(t) + '</span>'
  ).join('') +
  (r.topics && r.topics.length > 3 ? '<span class="topic-tag topic-more">+' + (r.topics.length - 3) + '</span>' : '') +
'</div>'

// applyAll() filter 内追加
if (activeTopics.size > 0 && !(r.topics || []).some(t => activeTopics.has(t))) return false;

// 点击事件委托
grid.addEventListener('click', (e) => {
  if (e.target.classList.contains('topic-tag')) {
    const topic = e.target.dataset.topic;
    if (!topic) return;
    if (activeTopics.has(topic)) activeTopics.delete(topic);
    else activeTopics.add(topic);
    currentPage = 1;
    applyAll();
  }
});
```

### 4.3 README 中英双语（3.3）

新建 `README.md`，包含：
- 项目简介（中/英）
- 功能列表
- 技术栈（纯静态 HTML/CSS/JS + GitHub Actions + Pages）
- 本地运行说明
- 数据更新机制

### 4.4 Owner Avatar（3.4）

**CSS 策略**：新增 avatar 样式（~5 行）。

```css
/* 新增 */
.avatar {
  width: 20px; height: 20px;
  border-radius: var(--radius-full);
  vertical-align: middle;
  margin-right: 2px;
  box-shadow: 2px 2px 4px var(--shadow-dark);
}
```

**JS 策略**：card-header 内插入 `<img>`（~5 行）。

```javascript
// renderCards() 内 card-header 改动
'<a class="card-name" href="...">' +
  (r.owner_avatar 
    ? '<img class="avatar" src="' + escHtml(r.owner_avatar) + '" alt="" width="20" height="20" loading="lazy">' 
    : '') +
  '<span class="card-owner">' + escHtml(owner) + '</span> / ' + escHtml(repo) +
'</a>'
```

### 4.5 排序升降序（3.5）

**JS 策略**：新增 `sortDir` state + toggle 逻辑（~15 行）。

```javascript
// js/app.js 新增
let sortDir = 'desc'; // 'asc' | 'desc'

// sort 逻辑改动——对调 a/b 实现翻转
filtered.sort((a, b) => {
  const [a2, b2] = sortDir === 'asc' ? [a, b] : [b, a];
  switch (currentSort) { /* 不变 */ }
});

// 事件监听：同按钮再次点击时翻转
btn.addEventListener('click', () => {
  if (currentSort === btn.dataset.sort) {
    sortDir = sortDir === 'asc' ? 'desc' : 'asc';
  } else {
    sortDir = 'desc'; // 切换排序键时重置为降序
  }
  currentSort = btn.dataset.sort;
  // ...更新 active
});
```

**CSS 策略**：sort 按钮箭头指示器（~10 行）。

```css
/* 新增 */
.sort-btn::after {
  content: ' ▼';
  font-size: 0.55rem;
  opacity: 0;
  transition: opacity 150ms;
}
.sort-btn.active::after { opacity: 1; }
.sort-btn.asc::after { content: ' ▲'; }
```

### 4.6 `lang="zh-CN"`（3.6）

```html
<!-- index.html L2 改动 -->
- <html lang="en">
+ <html lang="zh-CN">
```

---

## 5. 实施计划（角色分配 + 执行顺序 + 验收标准）

### 5.1 角色分配

| 角色 | Agent | 负责 |
|------|-------|------|
| 前端开发 | Claude Code + GLM-5.2 | 3.1 Dark mode + 3.2 Topics + 3.4 Avatar + 3.5 Sort + 3.6 lang |
| DevOps | Claude Code + GLM-5.2 | 3.3 README + 最终集成验证 |

**注意**：Phase 3 无后端改动，后端 Agent 本轮不参与。

### 5.2 执行顺序

```
Phase 3 执行 DAG
================
T3.6 (lang) ──┐
              ├── 无依赖，可并行 ──▶ T3.3 (README)
T3.4 (avatar)─┘
              │
T3.1 (dark mode) ──────────────────▶ 所有功能完成后：集成验证
              │
T3.5 (sort) ──┤
              │
T3.2 (topics)─┘

关键依赖说明：
- T3.6 (lang) 与任何功能无冲突，先行执行
- T3.4 (avatar) 独立于其他功能
- T3.1 (dark mode) 在 CSS 文件尾追加，与其他 CSS 追加无冲突
- T3.5 (sort) 修改 applyAll() 排序逻辑，需确保与 T3.2 topics filter 兼容
- T3.2 (topics) 修改 renderCards() 和 applyAll()，需确保与 T3.4/T3.5 兼容
```

### 5.3 任务拆分

#### 前端任务（`Coding 前端开发`）

```
T3.6: lang="zh-CN"                 1 文件,  1 行,  1 min
T3.4: Owner avatar                 2 文件, 15 行,  5 min
T3.1: Dark mode                    3 文件,135 行, 20 min
T3.5: Sort ascending/descending    2 文件, 25 行, 10 min
T3.2: Topics tags + filter         2 文件, 50 行, 15 min
                                    ────────────────
                                    总计 ~226 行, ~51 min
```

#### DevOps 任务（`Coding DevOps`）

```
T3.3: README.md 中英双语            1 文件,100 行, 15 min
集成验证：功能+回归+截图对比         1 文件,  —  , 15 min
                                    ────────────────
                                    总计 ~100 行, ~30 min
```

### 5.4 验收标准

#### 前端验收

| 功能 | 验收标准 |
|------|----------|
| 3.1 Dark mode | ① 页面加载时尊重 `prefers-color-scheme`；② 点击 toggle 切换并 localStorage 持久化；③ 所有元素（card, button, input, pagination, stats panel）深色下视觉正确；④ 刷新后恢复上次选择 |
| 3.2 Topics | ① card 内显示 top 3 个 topic 标签（>3 时用 "+N" 折叠）；② 点击 topic 标签筛选；③ 多选 AND 逻辑；④ 再次点击取消；⑤ 筛选结果数 badge 正确更新 |
| 3.4 Avatar | ① card-header 显示圆形 owner avatar（20×20）；② 无 avatar 数据的 repo 不显示破损图；③ 图片 lazy loading |
| 3.5 Sort | ① 默认排序方向不变（stars 降序，时间最新在前）；② 同按钮点第二次翻转方向；③ 按钮显示 ▲/▼ 指示器；④ 切换排序键时重置为默认方向 |
| 3.6 lang | ① `<html lang="zh-CN">`，W3C validator 无警告 |

#### DevOps 验收

| 功能 | 验收标准 |
|------|----------|
| 3.3 README | ① `README.md` 存在；② 包含中英双语；③ 包含项目简介、功能、技术栈、本地运行说明 |
| 集成验证 | ① 打开 `index.html`，所有功能正常；② Console 无 JS 报错；③ 移动端 375px 响应式正常；④ 视觉截图与 Phase 1 对比，非 dark mode 下布局一致 |

---

## 6. 风险和排除项

### 风险

| # | 风险 | 应对 |
|---|------|------|
| R1 | Dark mode neumorphism 阴影反转后视觉效果不佳 | spec.md §7 已给定色值，若效果不佳可微调（调 `shadow-light` 亮度） |
| R2 | Topics 数量多时 card 高度膨胀 | 限制显示前 3 个 + "+N more" 折叠，hover/click 展开 |
| R3 | Sort 方向切换与 Topics/Lang 筛选并发时行为错乱 | TDD：先写测试用例覆盖 sort+filter 组合，再实现 |
| R4 | `owner_avatar` 字段加载失败时页面出现破损图 | 用 `onerror` 回退隐藏，CSS 备用纯色圆形占位 |

### 排除项

- ❌ 不引入 Tailwind/Bootstrap 等第三方 CSS 框架
- ❌ 不修改数据采集脚本（`fetch_stars.py`、`translate_descriptions.py`）
- ❌ 不修改 CI/CD workflow
- ❌ Topics 标签不做动画（保持 neumorphism 克制风格）
- ❌ Dark mode 不做渐变过渡动画（CSS 变量瞬时切换）

---

## 7. P2 功能纳入决策

| 功能 | 边际收益 | 边际成本 | 建议 |
|------|:---:|:---:|:---:|
| 3.4 Owner avatar | 高（视觉辨识度显著提升） | 极低（15 行） | ✅ 纳入 |
| 3.5 排序升降序 | 中（实用性提升，但非核心） | 低（25 行） | ✅ 纳入 |
| 3.6 `lang="zh-CN"` | 低（SEO/可访问性微改进） | 零（1 行） | ✅ 纳入 |

**决策**：三个 P2 功能边际成本极低（合计 41 行），建议全部纳入 Phase 3。如审批者不同意，可单独移除任一 P2 功能，不影响其他功能独立性。

---

*2026-06-27 | Coding 软件架构师 | SOL-83*
