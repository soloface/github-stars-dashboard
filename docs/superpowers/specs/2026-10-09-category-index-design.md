# 功能分类索引 — 设计草案（2026-10-09）

> 状态：分类体系已定，待确认 8 个❓条目。已定：界面基于 A 方案（原型 `design/a.html` 保留在本地 `loft/ui-redesign` 分支，不进 main）；归类方式 = 关键词规则自动归类 + 手工修正（不接入 LLM，见第 3 节）；两级分类，且一级分类下主分类 ≥ 3 个才拆二级（2026-10-09 确认）。
> 初始归类已写入 `data/category_assignments.json`（147 个仓库，source = seed）。

## 1. 为什么不用 topic 直接分类

- 147 个仓库中 42 个没有任何 topic；632 个 topic 里 475 个只出现一次。
- 7 条关键词规则试归类：44 个匹配不上，命中的又大量重叠。
- 结论：需要一套自定义的固定分类体系，topic 只作为归类时的参考信息。

## 2. 数据模型

| 文件 | 维护方式 | 内容 |
|---|---|---|
| `data/categories.json` | 手工 | 两级分类表：`id`（如 `ai-coding/clients`）、中文名、一句说明（用于 tooltip）、规则关键词 `keywords` |
| `data/category_assignments.json` | 流水线自动写入并提交；复核时手工更新 | `{full_name: {primary, secondary[], source: "seed"\|"manual"\|"rule", desc_hash, needs_review?}}` |
| `data/category_overrides.json` | 手工 | `{full_name: {primary, secondary[]}}`，优先级最高，流水线不会覆盖 |
| `data/stars.json` | 流水线 | 每个仓库新增 `category`（主分类 id）和 `categories`（主 + 次） |

需要单独的 assignments 缓存文件，是因为 `fetch_stars.py` 每次同步都会重新生成 `stars.json`，派生字段不会保留下来。

**每个仓库**：1 个主分类 + 最多 2 个次分类。筛选时主次都算命中；分组展示时只按主分类出现一次。

## 3. 流水线（已定：关键词规则 + 手工修正，不接入 LLM）

> 决策记录（2026-10-09）：原计划用 GitHub Models，但 [GitHub Models 已于 2026-07-30 全面停服](https://github.blog/changelog/2026-07-30-github-models-is-now-retired/)。备选是 Claude API（需配置 secret）或 Azure AI Foundry；用户选择不依赖任何外部服务：新仓库先由关键词规则归类并标「待确认」，待确认积累多了再由人（或请 AI 助手在本地）统一复核。

新增 `scripts/categorize_repos.py`，放在翻译步骤之后：

1. 读取 `categories.json`（每个可归类 id 带 `keywords`）、`category_assignments.json`、`category_overrides.json`。
2. 已有归类且来源是 `seed` / `manual` 的保留分类，只更新 `desc_hash`；来源是 `rule` 且简介没变的保留，简介变了重跑规则。
3. 新仓库跑关键词规则（topic 精确匹配权重最高，其次仓库名、中英文简介），得到主分类 + 最多 2 个次分类，标记 `source: "rule"`、`needs_review: true`；没有分类达到阈值就归到 `other` 并标待确认。
4. 已取消星标的仓库：规则归类的记录删除，人工归类（seed / manual）保留；分类表删除 id 时，人工归类只去掉失效次分类，主分类失效则标记待确认。overrides 由前端直接叠加，脚本只校验并告警，不改动。
5. 任何输入文件缺失或格式错误时只打印警告、不改文件、正常退出，保证星标同步不受影响。

**复核流程**：页面分类树底部有「待确认」筛选。复核时把结论写回 `category_assignments.json`，来源改为 `manual` 并去掉 `needs_review`；需要永久锁定的个别结论写进 `category_overrides.json`。

## 4. A 方案中的界面

- **侧栏「分类」**：放在「语言」上方。一级分类一行，带数量和比例条，可展开二级分类；点一级分类等于选中它下面全部二级分类。多选时分类之间是"或"，和语言、主题、搜索之间是"且"。
- **主区「按分类分组」开关**：列表按主分类分段，段标题吸顶显示「AI 编码代理 › 客户端与工作台 · 12」。点侧栏分类时，分组模式下跳到对应段落，非分组模式下筛选。
- **每行显示主分类标签**：点击即按该分类筛选；次分类放在 tooltip 中。
- **深链接**：`#cat=ai-coding/clients`，可分享。
- **搜索**：同时匹配分类名。
- **待确认标记**：`other/unsorted` 和规则兜底的条目在分类区底部单独列出，方便手工修正。

## 5. 分类定稿（147 个仓库）

11 个一级分类 + 「其他 / 待确认」，29 个二级分类；「资源合集」和「其他」不分二级，assignment 直接用一级 id。`⟂` 后是次分类，❓ 表示信息不足、需要确认（8 个）。

| 一级分类 | 主分类数 | 二级分类（主分类数 / 含次分类总数） |
|---|---|---|
| AI 编码代理 | **23** | 编码代理 CLI 8/8 · 客户端与工作台 11/13 · 插件与增强 4/6 |
| Agent Skills 与提示词 | **22** | 工程方法与通用 9/11 · 设计与前端 4/5 · 内容创作与办公 7/14 · 角色与智能体定义 2/2 |
| MCP 与工具接入 | **9** | MCP 服务器 2/5 · 面向代理的 CLI 与接口 4/4 · 代码理解与知识图谱 3/3 |
| Agent 平台与应用 | **21** | 框架与运行时 5/8 · 自主代理应用 7/9 · OpenClaw / Hermes 生态 9/12 |
| 模型接入与网关 | **12** | API 中转与聚合 7/7 · 模型路由与切换 3/4 · 模型目录与价格 2/2 |
| 设计与多媒体创作 | **22** | 视频生成与剪辑 13/14 · 设计与图像生成 4/6 · 语音与音频 3/3 · 内容发布 2/2 |
| 前端与 UI 组件 | **7** | 组件库与模板 4/4 · 图表与流程编辑 3/4 |
| 知识、搜索与数据 | **7** | 知识库与搜索 4/10 · 舆情与情报分析 3/3 |
| 运维、网络与安全 | **9** | 服务器运维与部署 4/4 · 终端与远程连接 3/4 · 网络与安全 2/4 |
| 影音娱乐 | **7** | 直播与流媒体 4/4 · 音乐与下载 3/3 |
| 资源合集 | **6** | （不分二级） |
| 其他 / 待确认 | **2** | （不分二级） |

### AI 编码代理
- **编码代理 CLI**（8）：`deepseek-ai/deepseek-harness` ⟂ 框架与运行时；`anomalyco/opencode`；`anthropics/claude-code`；`earendil-works/pi` ⟂ 框架与运行时；`google-gemini/gemini-cli`；`can1357/oh-my-pi`；`QwenLM/qwen-code`；`xai-org/grok-build`
- **客户端与工作台**（11）：`stablyai/orca`；`anywhere-labs/dsh-desktop`；`slopus/happy`；`YishenTu/claudian`；`EKKOLearnAI/ekko-studio` ⟂ 自主代理应用；`op7418/CodePilot`；`KunAgent/Kun` ⟂ 自主代理应用；`borawong/AiMaMi`；`freestylefly/wesight`；`AITabby/codexsplit` ⟂ 模型路由与切换；`xichan96/dinotty` ⟂ 终端与远程连接
- **插件与增强**（4）：`Yeachan-Heo/oh-my-claudecode`；`BigPizzaV3/CodexPlusPlus`；`jarrodwatts/claude-hud`；`Gan-Xing/CodexBridge`

### Agent Skills 与提示词
- **工程方法与通用**（9）：`obra/superpowers`；`mattpocock/skills`；`affaan-m/ECC` ⟂ 插件与增强；`multica-ai/andrej-karpathy-skills`；`DietrichGebert/ponytail`；`mcncarl/yichen-skills` ❓；`Pluviobyte/rnskill` ❓；`provencher/codex-skills`；`soloface/project-gov-skill`
- **设计与前端**（4）：`VoltAgent/awesome-design-md` ⟂ 资源合集；`Nutlope/hallmark`；`alchaincyf/huashu-design` ⟂ 设计与图像生成；`jakubkrehel/skills`
- **内容创作与办公**（7）：`kepano/obsidian-skills`；`op7418/Humanizer-zh`；`chuspeeism/dashi-ppt-skill`；`axtonliu/axton-obsidian-visual-skills`；`nexu-io/codex-slides` ⟂ 插件与增强；`redfox-data/redfox-community`；`mujingquan835/dashiai-ppt-skill`
- **角色与智能体定义**（2）：`msitarzewski/agency-agents`；`jnMetaCode/agency-agents-zh`

### MCP 与工具接入
- **MCP 服务器**（2）：`ahujasid/mcp-for-blender` ⟂ 设计与图像生成；`jacob-bd/gemini-notebook-mcp-cli` ⟂ 知识库与搜索
- **面向代理的 CLI 与接口**（4）：`Panniantong/Agent-Reach` ⟂ 知识库与搜索；`HKUDS/CLI-Anything`；`teng-lin/notebooklm-py` ⟂ 知识库与搜索；`larksuite/cli`
- **代码理解与知识图谱**（3）：`Egonex-AI/Understand-Anything` ⟂ 工程方法与通用；`colbymchenry/codegraph`；`DeusData/codebase-memory-mcp` ⟂ MCP 服务器

### Agent 平台与应用
- **框架与运行时**（5）：`NousResearch/hermes-agent` ⟂ OpenClaw / Hermes 生态；`bytedance/deer-flow`；`tinyhumansai/openhuman`；`TokenRhythm/opensquilla`；`octos-org/octos`
- **自主代理应用**（7）：`multica-ai/multica`；`78/xiaozhi-esp32` ⟂ MCP 服务器；`browser-use/jev-ultrafast`；`voyager-crew/voyager` ❓；`CopilotKit/OpenBot`；`OpenMinis/OpenMinis`；`milind-soni/OpenMausBot`
- **OpenClaw / Hermes 生态**（9）：`nesquena/hermes-webui`；`CortexReach/memory-lancedb-pro` ⟂ 知识库与搜索；`larksuite/openclaw-lark`；`uzairansaruzi/hermex`；`win4r/ClawTeam-OpenClaw`；`win4r/openclaw-a2a-gateway`；`liandu2024/OpenClaw-Chat-Gateway`；`win4r/openclaw-workspace` ⟂ 工程方法与通用；`luolin-ai/openclawWeComzh` ❓

### 模型接入与网关
- **API 中转与聚合**（7）：`diegosouzapw/OmniRoute`；`router-for-me/CLIProxyAPI`；`QuantumNous/new-api`；`Wei-Shaw/sub2api`；`chenyme/grok2api`；`james-6-23/codex2api`；`tech-shrimp/deno-api-proxy` ⟂ 网络与安全
- **模型路由与切换**（3）：`farion1231/cc-switch` ⟂ 客户端与工作台；`yetone/magpie` ⟂ 客户端与工作台；`duolahypercho/codex-router`
- **模型目录与价格**（2）：`anomalyco/models.dev`；`bytedoger/awesome-OpenPrice`

### 设计与多媒体创作
- **视频生成与剪辑**（13）：`OpenCut-app/OpenCut`；`calesthio/OpenMontage` ⟂ 内容创作与办公；`remotion-dev/remotion`；`heygen-com/hyperframes`；`palmier-io/palmier-pro`；`Vincentwei1021/anything2explainer` ⟂ 内容创作与办公；`0xsline/OpenChatCut`；`jd-opensource/JoyAI-VL-Interaction` ❓；`feitangyuan/onetake` ⟂ 内容创作与办公；`alchaincyf/huashu-art-motion` ⟂ 内容创作与办公；`lemomo-ai/lemo-opuscar` ⟂ 内容创作与办公；`soCzech/TransNetV2`；`nutllwhy/seedance-tvc-director` ⟂ 内容创作与办公
- **设计与图像生成**（4）：`nexu-io/open-design` ⟂ 设计与前端；`JCodesMore/ai-website-cloner-template`；`DayuanJiang/next-ai-draw-io` ⟂ 图表与流程编辑；`freestylefly/awesome-gpt-image-2` ⟂ 资源合集
- **语音与音频**（3）：`jamiepine/voicebox`；`chidiwilliams/buzz`；`jhj0517/Whisper-WebUI`
- **内容发布**（2）：`yikart/AiToEarn`；`fxyadela/write-then-publish`

### 前端与 UI 组件
- **组件库与模板**（4）：`heroui-inc/heroui`；`satnaing/shadcn-admin`；`DavidHDev/canvas-ui`；`appica-dev/appica-ui`
- **图表与流程编辑**（3）：`xyflow/xyflow`；`antvis/X6`；`alibaba/butterfly`

### 知识、搜索与数据
- **知识库与搜索**（4）：`DIYgod/RSSHub`；`searxng/searxng`；`Tencent/WeKnora`；`electkismet/eltdx` ⟂ MCP 服务器
- **舆情与情报分析**（3）：`sansan0/TrendRadar` ⟂ 知识库与搜索；`666ghj/BettaFish` ⟂ 框架与运行时；`simplifaisoul/osiris`

### 运维、网络与安全
- **服务器运维与部署**（4）：`oblien/openship`；`nezhahq/nezha`；`av/harbor`；`kejilion/KPanel`
- **终端与远程连接**（3）：`ohmyzsh/ohmyzsh`；`binaricat/Netcatty`；`TurboVNC/turbovnc`
- **网络与安全**（2）：`usestrix/strix`；`liandu2024/Open-Box`

### 影音娱乐
- **直播与流媒体**（4）：`ZLMediaKit/ZLMediaKit`；`YanG-1989/m3u`；`mursor1985/LIVE` ❓；`FanchangWang/allinone_format`
- **音乐与下载**（3）：`algerkong/AlgerMusicPlayer`；`alexta69/metube`；`foamzou/melody`

### 资源合集
- **资源合集**（6）：`sindresorhus/awesome`；`public-apis/public-apis` ⟂ 知识库与搜索；`VoltAgent/awesome-openclaw-skills` ⟂ OpenClaw / Hermes 生态；`imthenachoman/How-To-Secure-A-Linux-Server` ⟂ 网络与安全；`hesamsheikh/awesome-openclaw-usecases` ⟂ OpenClaw / Hermes 生态；`zhuyansen/awesome-claude-video-skills` ⟂ 视频生成与剪辑、内容创作与办公

### 其他 / 待确认
- **其他 / 待确认**（2）：`block/buzz` ❓；`appsail/Gemini-in-Chrome` ❓


## 6. 已决定：合并过薄的二级分类

规则：一级分类下的主分类数 ≥ 3 时才拆二级。相对初稿的合并：

| 初稿 | 定稿 |
|---|---|
| OpenClaw 生态 + Hermes 生态 | 「OpenClaw / Hermes 生态」 |
| 设计与图表生成 + 图像生成 | 「设计与图像生成」 |
| 知识库与 RAG + 搜索与资讯聚合 + 数据源与接口 | 「知识库与搜索」 |
| 网络与代理 + 安全 | 「网络与安全」 |
| 音乐 + 视频下载 | 「音乐与下载」 |
| Awesome 列表 + 指南与教程 | 「资源合集」不分二级 |

二级分类从 37 个减少到 29 个，每个二级分类的主分类数至少为 2。
