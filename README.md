# ★ GitHub Stars Dashboard

> 按功能分类索引 GitHub 星标仓库的纯静态看板。
> A purely static dashboard that indexes your GitHub starred repos by functional category.

**中文** · [English](#english)

- 在线预览 / Live demo：<https://soloface.github.io/github-stars-dashboard/>
- 源码 / Source：<https://github.com/soloface/github-stars-dashboard>

---

## ✨ 功能特性

- **功能分类索引**：两级分类（如「AI 编码代理 › 客户端与工作台」），侧栏分类树带数量；可「按分类分组」浏览，每个仓库显示主分类标签
- **待确认**：规则自动归类或信息不足的仓库带「待确认」标记，侧栏可一键筛出
- **列表 / 卡片两种视图**：右上角切换。列表视图一行看全仓库名、中文简介、主题、语言、星数、Fork 数，点表头排序；卡片视图以网格展示，适合浏览。选择会被记住
- **排序与筛选**：按星数 / 收藏时间 / 创建时间 / 最近推送排序，可切换升降序；按分类、语言、主题筛选，条件可单独移除或一键清除
- **搜索**：匹配名称、中英文简介、主题和分类名；按 `/` 聚焦，`Esc` 清空
- **可分享链接**：筛选与视图状态写在 URL 里（如 `#cat=mcp&group=1&view=card`）
- **中文 / 英文原文**：简介默认显示中文翻译，可切换原文
- **Dark mode**：跟随系统，也可手动切换并记住选择
- **响应式**：桌面侧栏 + 列表；手机端顶部搜索 + 底部筛选面板
- **自动同步**：GitHub Actions 每 4 小时同步一次星标，也可手动触发

## 🛠 技术栈

- **前端**：原生 HTML / CSS / JavaScript，零框架、零构建步骤，不依赖外部字体或 CDN
- **数据采集**：Python 标准库脚本调用 GitHub API
- **自动化**：GitHub Actions（定时 + 手动触发）
- **部署**：GitHub Pages（`main` 分支根目录）

## 🚀 本地运行

```bash
git clone https://github.com/soloface/github-stars-dashboard.git
cd github-stars-dashboard
python3 -m http.server 8000   # 然后访问 http://localhost:8000
```

> 页面通过 `fetch` 读取 `data/*.json`，需要用本地服务器打开，直接双击 `index.html` 会读不到数据。

运行测试：

```bash
python3 -m unittest discover -s tests   # 数据脚本与工作流
node --test tests/test_logic.mjs         # 前端纯逻辑
```

## 🔄 数据同步

`.github/workflows/fetch-stars.yml` 每 4 小时运行一次（GitHub 的定时任务可能会延迟）：

1. `scripts/fetch_stars.py` 拉取星标仓库，生成 `data/stars.json`；简介没变的仓库沿用上次的中文翻译。拉取失败、结果为空或数量不到上次一半时不覆盖现有数据，本次运行标记为失败
2. `scripts/translate_descriptions.py` 只翻译新增或改动过的英文简介（写入 `description_zh`）
3. `scripts/categorize_repos.py` 用关键词规则给新仓库归类，并标记「待确认」；已归类的仓库保持不变；取消星标后，规则归类的记录被移除，人工归类（seed / manual）保留
4. GitHub Actions bot 提交 `data/stars.json` 和 `data/category_assignments.json` 并触发 GitHub Pages 重新部署。星数、Fork 数几乎每次都会变，所以大多数运行都会提交；完全没有变化时不提交

**手动同步**：页面侧栏底部（手机端在「筛选」面板底部）的「手动同步」会打开 [Actions 页面](https://github.com/soloface/github-stars-dashboard/actions/workflows/fetch-stars.yml)，点 **Run workflow** 即可（仅仓库所有者可用）。也可以用命令行：

```bash
gh workflow run fetch-stars.yml -R soloface/github-stars-dashboard
```

> 如果一次取消了超过一半的星标，保护机制会让同步失败。这时先提交删除 `data/stars.json`，再手动触发一次同步即可。

工作流只使用内置 `GITHUB_TOKEN`（`permissions: contents: write`），无需额外密钥。

## 🗂 分类维护

| 文件 | 作用 |
|---|---|
| `data/categories.json` | 两级分类表：id、中文名、说明、规则关键词 `keywords` |
| `data/category_assignments.json` | 每个仓库的主分类 + 最多 2 个次分类；`source` 为 `seed`（初稿）、`manual`（人工复核）或 `rule`（规则自动） |
| `data/category_overrides.json` | 手工修正，优先级最高，页面直接叠加，流水线不会改动 |

- **复核待确认**：在页面上筛「待确认」，把结论写回 `category_assignments.json`，`source` 改为 `manual` 并删除 `needs_review`
- **永久锁定某个仓库的分类**：写进 `category_overrides.json`，例如 `{"owner/repo": {"primary": "mcp/servers", "secondary": []}}`
- **增删分类**：编辑 `categories.json`。被删除的 id：规则归类的仓库会重新按规则归类；人工归类的仓库会去掉失效的次分类，主分类失效时标记「待确认」等你处理，不会被覆盖

设计说明见 `docs/superpowers/specs/2026-10-09-category-index-design.md`。

## 📁 项目结构

```
github-stars-dashboard/
├── index.html                         # 页面骨架（lang="zh-CN"）
├── css/style.css                      # 样式（含 Dark mode）
├── js/
│   ├── logic.js                       # 纯逻辑：排序 / 筛选 / 分类 / URL 状态（可在 Node 中测试）
│   └── app.js                         # 加载数据、渲染与交互
├── data/
│   ├── stars.json                     # 星标数据（Actions 生成）
│   ├── categories.json                # 分类表
│   ├── category_assignments.json      # 归类结果（Actions 更新）
│   └── category_overrides.json        # 手工修正
├── scripts/
│   ├── fetch_stars.py                 # GitHub API 数据拉取
│   ├── translate_descriptions.py      # 简介中文翻译
│   └── categorize_repos.py            # 关键词规则归类
├── tests/                             # unittest + node:test
└── .github/workflows/fetch-stars.yml  # 定时同步
```

---

<a name="english"></a>
## English

A purely static dashboard that indexes your GitHub starred repositories by functional category. No frameworks, no build step, no external fonts or CDNs — just HTML, CSS and JavaScript, kept fresh by GitHub Actions and served by GitHub Pages.

### Features

- **Category index**: two-level functional categories in a sidebar tree with counts, an optional "group by category" view, and a primary-category chip on every row
- **Needs review**: rule-classified or unclear repos are flagged and can be filtered in one click
- **List and card views**, switchable top-right: a dense sortable list with a date column that follows the sort key, or a card grid for browsing; the choice is remembered
- **Sort & filter**: by stars / starred / created / pushed (asc or desc); filter by category, language and topic; removable filter chips
- **Search** across name, Chinese and English descriptions, topics and category names (`/` to focus, `Esc` to clear)
- **Shareable URLs**: filter and view state live in the hash, e.g. `#cat=mcp&group=1&view=card`
- **Dark mode** following the OS, with a persisted manual toggle
- **Responsive**: sidebar on desktop, bottom filter sheet on mobile
- **Auto sync** every 4 hours, plus manual runs

### Run locally

```bash
git clone https://github.com/soloface/github-stars-dashboard.git
cd github-stars-dashboard
python3 -m http.server 8000   # then open http://localhost:8000
```

Tests: `python3 -m unittest discover -s tests` and `node --test tests/test_logic.mjs`.

### Data pipeline

Every 4 hours (schedules may be delayed by GitHub) the workflow fetches starred repos into `data/stars.json` (reusing previous translations for unchanged descriptions; a failed, empty or less-than-half-size fetch never overwrites existing data), translates new English descriptions, classifies new repos with keyword rules (flagged for review), and commits `data/stars.json` plus `data/category_assignments.json`, which triggers a GitHub Pages deployment. Star and fork counts change almost every run, so most runs commit; runs with no change commit nothing. Trigger it manually from the [Actions page](https://github.com/soloface/github-stars-dashboard/actions/workflows/fetch-stars.yml) or with `gh workflow run fetch-stars.yml`. Only the built-in `GITHUB_TOKEN` is used.

### Categories

`data/categories.json` defines the taxonomy and rule keywords, `data/category_assignments.json` stores each repo's primary + up to two secondary categories (`seed`, `manual` or `rule`), and `data/category_overrides.json` holds manual corrections that always win.

## License

个人星标展示项目 / Personal starred-repos showcase.
