# ★ GitHub Stars Dashboard

> 用 Neumorphism（工业拟物）风格展示 GitHub 星标仓库的纯静态看板。
> A purely static dashboard that showcases your GitHub starred repos in a Neumorphism (industrial skeuomorphism) style.

**中文** · [English](#english)

- 在线预览 / Live demo：<https://soloface.github.io/github-stars-dashboard/>
- 源码 / Source：<https://github.com/soloface/github-stars-dashboard>

---

## ✨ 功能特性

- **星标项目卡片**：以拟物风格卡片展示你的 GitHub 星标仓库，含星数、Fork 数、语言、更新时间
- **排序与筛选**：按星数 / 点星时间 / 发布时间 / 更新时间排序；按编程语言筛选；关键词搜索
- **Topics 标签**：每张卡片展示仓库主题标签，点击即可筛选（AND 多选）
- **Owner 头像**：卡片头部展示仓库拥有者头像
- **升降序切换**：再次点击同一排序按钮可在升序 / 降序间切换
- **Dark mode**：跟随系统 `prefers-color-scheme`，支持手动切换并 `localStorage` 持久化
- **响应式布局**：适配 1440px 桌面到 375px 移动端
- **每日自动更新**：GitHub Actions 每日拉取最新星标数据

## 🛠 技术栈

- **前端**：原生 HTML / CSS / JavaScript，零框架、零构建步骤
- **数据采集**：Python 脚本调用 GitHub API（Bearer 鉴权）
- **自动化**：GitHub Actions（每日定时 + 手动触发）
- **部署**：GitHub Pages

## 🚀 本地运行

```bash
git clone https://github.com/soloface/github-stars-dashboard.git
cd github-stars-dashboard
```

任选其一 / choose one：

```bash
# 方式一：启动本地静态服务器（推荐，避免 file:// 下 fetch 受限）
python3 -m http.server 8000
# 然后浏览器访问 http://localhost:8000

# 方式二：直接打开
open index.html        # macOS
xdg-open index.html    # Linux
```

## 🔄 数据更新机制

数据由 GitHub Actions 自动维护，流程如下：

1. **每日 UTC 00:00**（cron `0 0 * * *`）定时触发，亦支持手动 `workflow_dispatch`
2. `scripts/fetch_stars.py` 调用 GitHub API 拉取星标仓库，生成 `data/stars.json`
3. `scripts/translate_descriptions.py` 将英文简介翻译为中文（写入 `description_zh`）
4. GitHub Actions bot 提交并推送 `data/stars.json`
5. 推送触发 **GitHub Pages** 自动重新部署

> 配置说明：工作流使用内置 `GITHUB_TOKEN`（已声明 `permissions: contents: write` 以允许推送），无需额外密钥。

## 📁 项目结构

```
github-stars-dashboard/
├── index.html                         # 页面骨架（lang="zh-CN"）
├── css/style.css                      # 拟物风格样式 + Dark mode 变量
├── js/app.js                          # 加载 / 筛选 / 排序 / 分页 / 渲染
├── data/stars.json                    # 星标数据（由 Actions 生成）
├── scripts/
│   ├── fetch_stars.py                 # GitHub API 数据拉取
│   └── translate_descriptions.py      # 简介中文翻译
└── .github/workflows/fetch-stars.yml  # 每日自动化编排
```

---

<a name="english"></a>
## English

A purely static dashboard that showcases your GitHub starred repositories in a **Neumorphism** (industrial skeuomorphism) style. No frameworks, no build step — just HTML, CSS and JavaScript, kept fresh by GitHub Actions and served by GitHub Pages.

### Features

- **Starred-repo cards** with stars, forks, language and last-updated time
- **Sort & filter**: by stars / starred time / created time / pushed time; filter by language; keyword search
- **Topics tags**: each card shows topic tags; click to filter (AND logic)
- **Owner avatar** in the card header
- **Sort direction toggle**: click the same sort button again to flip asc/desc
- **Dark mode**: follows `prefers-color-scheme`, with a manual toggle persisted in `localStorage`
- **Responsive**: from 1440px desktop down to 375px mobile
- **Daily auto-update** via GitHub Actions

### Run locally

```bash
git clone https://github.com/soloface/github-stars-dashboard.git
cd github-stars-dashboard
python3 -m http.server 8000   # then open http://localhost:8000
# or simply: open index.html
```

### Data pipeline

Every day at UTC 00:00 (cron `0 0 * * *`, also manually triggerable via `workflow_dispatch`), GitHub Actions runs `scripts/fetch_stars.py` to pull starred repos from the GitHub API into `data/stars.json`, then `scripts/translate_descriptions.py` to add Chinese descriptions (`description_zh`). The bot commits and pushes the JSON, and the push triggers an automatic **GitHub Pages** deployment. The workflow uses the built-in `GITHUB_TOKEN` (`permissions: contents: write`) — no extra secrets required.

## License

个人星标展示项目 / Personal starred-repos showcase.
