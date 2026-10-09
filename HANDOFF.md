# 交接说明 — github-stars-dashboard

> 交接时间：2026-10-09。交出方：Claude Code（Claude Opus 5.5）。接手方：用户的 Grok bot「Github」。
> 当前状态：所有已开发功能均已上线，`main` 与线上一致，没有进行中的分支或未合并的 PR。下面第 2 节有 3 个问题在等用户决定。

## 1. 接手第一步

1. 读 `README.md`：功能、本地运行、测试命令、数据同步、分类维护方法都在里面。完成标准：能在本地起服务并跑通两套测试。
2. 读 `AGENTS.md` 第 3 节「查不到的约定和坑」：合并 `main` 即上线、机器人每 4 小时提交数据、改 css/js 要同步改 `?v=` 版本号等。完成标准：开分支、改样式、合并前知道各自要注意什么。
3. 和用户确认 `AGENTS.md` 第 1、2 节的分工是否沿用。那两节是为「Claude Code 主代理 + Sonnet 子代理」写的；换成 Grok bot 负责后，由用户决定改成什么分工，然后更新这两节。完成标准：`AGENTS.md` 描述的角色和实际负责人一致。
4. 拿第 2 节的问题去问用户，按用户的决定处理。

## 2. 等用户决定的问题

### 2.1 平板宽度下侧栏底部折行（小，影响外观）

- **现象**：窗口约 800px 宽时，侧栏底部的「最近收藏 2026-10-09」会折成两行。
- **位置**：`css/style.css` 中的 `.side-foot` 和 `.foot-meta`；文字由 `js/app.js` 写入 `#updated`。
- **建议**：给 `.foot-meta` 加 `white-space: nowrap`，空间不够时用省略号截断，或者窄屏时只显示日期。

### 2.2 鼠标悬停简介时看不到英文原文（线上原本就有）

- **现象**：简介有中英两版时，代码给简介加了 `title` 提示（`js/app.js` 中构造 `tip` 的地方），但鼠标悬停时提示不出现，列表和卡片都一样。
- **原因**：为了让整行 / 整张卡片可点击，`css/style.css` 里 `.name::after` 是一个铺满整行的透明层（`position: absolute; inset: 0; z-index: 1`），盖住了简介，鼠标悬停时拿到的是链接而不是简介。
- **可选方案**（需要用户选）：
  - **A**：把简介层级提到链接之上。悬停能看到原文，但点简介文字不再跳转到仓库。
  - **B**：在有原文的简介旁加一个小「原文」图标按钮，悬停或点击时显示原文；整行点击行为不变。
  - **C**：保持现状，用户需要原文时用侧栏的「中文 / 英文原文」切换。

### 2.3 8 个「待确认」仓库需要复核分类

这些仓库没有描述或描述看不出用途，初稿分类是猜的（`source: "seed"`，带 `needs_review: true`）。页面侧栏底部点「待确认」可以筛出它们。

| 仓库 | 当前暂定分类 | 依据 |
|---|---|---|
| `mcncarl/yichen-skills` | Agent Skills › 工程方法与通用 | 无描述，仅凭名字 |
| `Pluviobyte/rnskill` | Agent Skills › 工程方法与通用 | 描述只有「AI Agent Skills 集合」 |
| `jd-opensource/JoyAI-VL-Interaction` | 设计与多媒体创作 › 视频生成与剪辑 | 实时视频语言交互模型，分类不贴切 |
| `voyager-crew/voyager` | Agent 平台与应用 › 自主代理应用 | 实际是 AI 聊天网站的浏览器增强扩展 |
| `luolin-ai/openclawWeComzh` | Agent 平台与应用 › OpenClaw / Hermes 生态 | 名字和描述不一致 |
| `mursor1985/LIVE` | 影音娱乐 › 直播与流媒体 | 无描述，仅凭名字 |
| `block/buzz` | 其他 / 待确认 | 描述只有「蜂巢思维交流平台」 |
| `appsail/Gemini-in-Chrome` | 其他 / 待确认 | 无描述 |

- **处理方法**：确认分类后，在 `data/category_assignments.json` 里改该仓库的 `primary` / `secondary`，把 `source` 改为 `"manual"` 并删除 `needs_review`。分类 id 见 `data/categories.json`。
- **以后的新星标**：同步时会被关键词规则自动归类并标「待确认」（`source: "rule"`），按同样方法定期复核。

## 3. 已知的小问题（交接时未安排处理）

- **手机顶部工具栏偏高**：手机端顶部工具栏约 62px，比设计的 56px 高，原因是切换按钮要保证 44px 触控尺寸。
- **链接不带 `view` 时沿用本地偏好**：URL 里没有 `view` 参数时，使用访客本地保存的视图（列表 / 卡片）。这和「按分类分组」的行为一致，是有意保留的。
- **同步保护没有跳过开关**：`scripts/fetch_stars.py` 在新拉取的仓库数不到上次一半时拒绝写入，没有提供跳过的环境变量。确实大量取消星标时的处理方法见 README「数据同步」。
- **已取消星标仓库的人工归类会一直保留**：`seed` / `manual` 记录不会自动删除。页面不显示这些记录，文件会慢慢变大，但影响很小。

## 4. 背景资料

- **最近三个 PR**：#3（新界面 + 分类索引 + 安全同步）、#4（Actions 升级到 v7）、#5（行高放大 + 卡片视图 + AGENTS.md）。具体改动和验证记录见 PR 描述。
- **决策记录**：
  - 分类体系和规则：`docs/superpowers/specs/2026-10-09-category-index-design.md`
  - 界面基线：`docs/superpowers/reviews/2026-10-09-ui-review.md`
- **线上地址**：<https://soloface.github.io/github-stars-dashboard/>

## 5. 下一步

把第 2 节的三个问题（2.1、2.2 选 A/B/C、2.3 的 8 个仓库）发给用户确认。
