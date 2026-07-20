<p align="center">
  <img src="../docs/media/banner.jpg" alt="build-graph" width="840">
</p>

<p align="center">
  <a href="README.de.md">Deutsch</a> |
  <a href="../README.md">English</a> |
  <a href="README.es.md">Español</a> |
  <a href="README.fr.md">Français</a> |
  <a href="README.it.md">Italiano</a> |
  <a href="README.ja.md">日本語</a> |
  <a href="README.ko.md">한국어</a> |
  <a href="README.pt.md">Português</a> |
  <a href="README.ru.md">Русский</a> |
  <b>中文</b>
</p>

<p align="center">
  <a href="https://github.com/Mr-Freewan/build-graph/actions/workflows/ci.yml"><img src="https://github.com/Mr-Freewan/build-graph/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <a href="https://pypi.org/project/graph-build/"><img src="https://img.shields.io/pypi/v/graph-build" alt="PyPI"></a>
  <img src="https://img.shields.io/badge/python-3.11%2B-blue" alt="Python 3.11+">
  <img src="https://img.shields.io/badge/dependencies-0-brightgreen" alt="Zero dependencies">
  <a href="../LICENSE"><img src="https://img.shields.io/badge/license-MIT-green" alt="License: MIT"></a>
  <a href="https://github.com/astral-sh/ruff"><img src="https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json" alt="Ruff"></a>
  <a href="#为-ai-智能体而设计"><img src="https://img.shields.io/badge/LLM--Agent-friendly-blueviolet" alt="LLM-Agent friendly"></a>
  <a href="../CONTRIBUTING.md"><img src="https://img.shields.io/badge/PRs-welcome-brightgreen" alt="PRs Welcome"></a>
</p>

<p align="center">
  <a href="https://mr-freewan.github.io/build-graph/"><img src="https://img.shields.io/badge/demo-online-blueviolet?style=for-the-badge&logo=googlechrome&logoColor=white" alt="Live demo"></a>
  <a href="https://codespaces.new/Mr-Freewan/build-graph"><img src="https://github.com/codespaces/badge.svg" alt="Open in GitHub Codespaces"></a>
</p>

> **为重构而生的架构记忆。** 在代码、文档和 git 之间纵览你的变更影响范围 ——
> 在一张你和你的 AI 智能体都能读懂的交互式地图上。一套轻量工具，加上简单却
> 十分实用的 UI，以可「照原样」分享的自包含 HTML 文档形式提供。轻量，且私密。

`build-graph` 渲染一张连接五个层次的 **单文件交互式 HTML 图谱**，这五层是其他
任何工具都不曾结合的:

- **代码 → 代码** — Python 导入（基于 AST，感知 `TYPE_CHECKING`）
- **代码 ↔ 文档** — 哪些 markdown 文件提到了哪些源文件
- **git 漂移** — added / modified / renamed / deleted 的叠加层，外加为已不存在
  的文件保留的幽灵节点
- **文件改动热力图** — 帮你找出改动最频繁的热点，以及潜在的 bug 来源并加以
  收敛
- **测试覆盖率地图** — 读取项目的 `coverage.xml`，一目了然地展示测试覆盖率，
  突出覆盖率最低的文件

……并把同一张地图导出为 **紧凑、省 token 的 JSON**，专为投入 LLM 智能体的上下文
而设计。

而这一切都是 **零依赖** 的: 纯 Python 标准库，`pip install` 不会额外拉取任何
东西。唯一的第三方代码是浏览器中的 D3.js，通过带 SRI 固定的 CDN 加载，或用
`--no-cdn` 完全内嵌以实现完全离线。

![力导向布局在真实项目上稳定下来 —— 1070 个节点 / 6279 条边，深色主题](../docs/media/hero.gif)

**[▶ 在线演示](https://mr-freewan.github.io/build-graph/)** —— 正是这个仓库的
图谱（自食其狗粮），带有合成的 `--mock-git` 叠加层，因此 Git 模式和覆盖率模式
也可点击。
**[📖 UI 指南](guide.zh.md)** —— 逐一介绍核心功能的简明讲解。

## 安装

```bash
pip install graph-build        # 或: uv tool install graph-build
```

直接从 GitHub 安装:

```bash
pip install git+https://github.com/Mr-Freewan/build-graph.git

# 或从克隆安装:
git clone https://github.com/Mr-Freewan/build-graph.git
pip install ./build-graph
```

> PyPI 上的发行名为 `graph-build`（直接的名字已被占用）；安装后的命令名保持
> 不变: `build-graph`、`find-related-docs`、`verify-doc-links`。

## 快速开始

```bash
cd your-project
build-graph                    # 自动发现，无需配置 → docs/graph.html
build-graph --compact          # + 供 AI 智能体使用的 docs/graph-compact.json
build-graph --init             # 可选: 将发现的结构固定到 graph.toml
```

两个配套 CLI —— `find-related-docs`（反向查找: 代码 → 文档）和
`verify-doc-links`（面向 CI 的坏链检查）—— 随同一个包提供；参见
[CLI 工具](#cli-工具)。

## 为什么不用其他工具

- **pydeps / Import Linter** —— 只有导入；没有文档层，没有 git 漂移。
- **lychee 之类** —— 检查死链 URL；没有地图，没有代码层。
- **Obsidian 图谱视图** —— 只有笔记；看不到你的代码。
- **Repomix / Gitingest** —— 把仓库的 *文本* 打包给 LLM；build-graph 给出
  *结构*: 约为原始文本所需 token 的 2 %（见[数字](#上下文成本)）。
- **Graphify / Understand-Anything** —— 会拉入更重的依赖栈、并依赖非确定性
  LLM 做分析的知识图谱工具；build-graph 是确定性的、零依赖的，还多出这两者都
  没有的 git 层与 doc-sync 层。

## 为 AI 智能体而设计

`--compact` 写出一个自描述的 JSON 快照（内嵌图例、带索引的节点、三字母类型
代码），智能体用它来:

1. **影响范围** —— 你即将改动的文件的入向导入，无需 grep。
2. **文档路由** —— 在编辑某文件 *之前* 应先读哪个 ADR / 参考文档。
3. **三层 doc-sync** —— 图谱展示 (1) 什么已被记录、(2) 什么应当记录却尚未
   记录、(3) 什么已被记录却不再存在（幽灵节点 = 陈旧检测器）。

把 `build-graph --compact` 加入 pre-commit 钩子或 CI 步骤，即可让地图在每次
智能体会话中保持最新。

### 紧凑格式

`--compact` 写出 `graph-compact.json`（schema v2）: 节点为带索引的数组，边为
`[源索引, 目标索引, 类型, [行号]]` 行，每个类别与边类型都用三字母代码。`legend`
键内嵌完整的解码表 —— 智能体无需外部 schema，文件自我说明:

```jsonc
{
  "v": "2.0",
  "legend": { "...": "下面每个字段和代码的含义" },
  "stats": { "nodes": 1070, "ghosts": 0, "edges": 6279 },
  "n": [
    { "p": "smm_bot_async/core/security/access.py", "t": "cor", "d": 56 },
    { "p": "docs/explanation/adr/0009-parser-framework.md", "t": "adr",
      "d": 11, "s": "mod" }
  ],
  "e": [
    [ 1, 75, "d2d", [186] ]
  ]
}
```

`p` —— 路径，`t` —— 类别，`d` —— 度数，`s` —— git 状态（干净时省略）。边类型:
`c2c` 导入、`c2d` 文档提及、`d2d` 文档链接、`dcs` docstring 引用、`typ` 仅
`TYPE_CHECKING`、`ren` git 重命名。已删除但仍被提及的文件会作为幽灵节点随行
（`"G": 1`）。

### 上下文成本

来自一个生产仓库的真实数字 —— 1,070 个已映射文件、6,279 条边（token ≈
字节 / 4，常用的粗略估算）:

| 你放进上下文的内容                   |    大小 | ≈ token    |
|--------------------------------------|--------:|-----------:|
| 已映射文件本身                       |   15 MB | ~3,700,000 |
| `--json`（详细快照）                 |  1.6 MB |   ~410,000 |
| **`--compact`**                      | **0.33 MB** | **~80,000** |

整套架构 —— 每一条导入、每一次文档提及、每一处陈旧引用 —— 都落在原始文本成本
的约 2 % 之内，并能带着余量装进一次 200k 上下文的会话。没有这张地图，智能体
每次会话都要重新发现这套结构: 数十次投机式的 grep 与文件读取，*每个问题* 都要
烧掉相当数量的 token，而非一次性完成。在小项目上地图几乎是免费的 —— 正是这个
仓库的紧凑快照仅 4 KB ≈ 约 1,000 token。

<details>
<summary>别轻信这些数字 —— 在你自己的仓库上测量</summary>

```bash
$ build-graph --root . --bench

Context cost on this repo (tokens ~= bytes / 4):

  What you put in context            Size      ~Tokens  vs corpus
  raw corpus (1070 files)         14.3 MB    3,757,913     100.0%
  --json export (schema v1)        1.5 MB      397,419      10.6%
  --compact export (schema v2)   311.4 KB       79,729      2.1%
```

`--bench` 只做测量 —— 不写任何文件。

</details>

### 一个起步提示词

```text
graph-compact.json is a dependency map of this repository: nodes are
files, edges are imports and documentation mentions. Read the embedded
"legend" key first — it explains every field and code.

Using the map (before any grep):
1. Lay of the land: the 10 highest-degree hubs, grouped by category,
   with one line each on why they're central.
2. I'm about to modify <path/to/file.py>. List the blast radius:
   direct and 2-hop incoming importers, plus every doc that mentions
   the file — and tell me which of those docs to read first.
3. Anything suspicious: ghost nodes (docs pointing at deleted files),
   zero-degree modules, docs nothing links to.

Verify any surprising claim against the actual source before acting.
```

**更多配方:** [面向 AI 智能体的提示词](agent-prompts.zh.md) —— 针对影响范围、
三层 doc-sync、幽灵检测与死代码狩猎的即用提示词。

## 交互式图谱

- **Canvas 渲染器** —— 在 1000+ 节点 / 6000+ 边下依然流畅（预热布局、视口
  剔除、标签 LOD）。
- **6 种边类型** —— doc→doc、code→doc、code→code、仅类型（`TYPE_CHECKING`）、
  docstring 提及、git 重命名。
- **Git 叠加层** —— 状态颜色 + 幽灵节点 + 重命名边；`--mock-git` 用于合成演示。
- **图谱 diff** —— `--diff-base REF` 将工作树与某个 git 引用比较: 文件状态注入
  Git 叠加层，新增依赖边显示为绿色，删除的显示为红色（虚线），并在图例中带
  计数。加上 `--diff-head REF` 则改为比较两个特定引用。
- **Heat 叠加层** —— 按 git 提交频率给节点着色（蓝→红渐变），默认整段历史，或
  用 `--heat-days N` 限定最近 N 天。图例中的 min-edits 滑块会隐藏一切比所选阈值
  更「冷」的内容 —— 边随之淡出。与 Git 叠加层互斥（二者都会给节点重新着色，故
  同一时刻只开一个）；与 Git 模式不同，它是叠加式的: 下方的 Node types 层保持
  可见可用。
- **Coverage 叠加层** —— 按测试行覆盖率给节点着色（绿→红渐变 —— 这个是为了
  找出覆盖不佳的文件，因此读法与 Heat 相反），来自 Cobertura 的 `coverage.xml`
  （`--coverage PATH`，例如 `pytest --cov=your_pkg --cov-report=xml`）。max-coverage
  滑块隐藏一切覆盖率 *高于* 所选上限的内容，随着你下调而分离出覆盖最差的
  文件；开启时还会在图例中自动隐藏除代码外的所有 Node types（一键即可恢复）。
  它也与 Git、Heat 互斥。未提供报告时关闭，且按钮隐藏。
- **节点工具提示** —— 悬停任意节点即可看到其名称与路径；在 Heat 或 Coverage
  模式下，还会显示颜色背后的改动次数或覆盖率百分比。这些模式激活时，边的工具
  提示会关闭。
- **分析辅助** —— 死代码候选、导入环检测器（对运行时导入做 Tarjan SCC；
  `TYPE_CHECKING` 边不计）、孤立节点环、两节点间的最短路径（Shift+点击）、
  隔离某类型、按名称排除。文档中对同名文件的裸提及（`config.py` 有数十处匹配、
  无路径）会归属到单一的 `ambiguous` 类别节点，而非散布到所有候选。
- **分享** —— URL 编码的视图（Copy link）、聚焦子图的 Mermaid 导出、完整 /
  紧凑 JSON 导出。
- **舒适性** —— 10 种 UI 语言、深 / 浅主题、色相对齐的柔和 / 高饱和调色板、
  可拖拽的玻璃面板、IDE 深链接（VS Code / Cursor / PyCharm）、内置 FAQ（`?`）。

一切都装进 **单个自包含 HTML 文件** —— 附到 PR、在聊天里发送、离线打开。

## 配置（可选）

自动发现按种类（代码 / 文档 / 配置 / 语言环境）× 位置对每个受版本控制的文件
分类，检测你的包与文档布局，并生成确定性的颜色。`graph.toml` 只是一个覆盖:

```bash
build-graph --init           # 生成 graph.toml，固定当前结构
build-graph --init --diff    # 报告漂移（新文件夹、陈旧固定项），不做任何更改
build-graph --init --merge   # 为新文件夹补充覆盖，保留你的编辑
```

带注释的格式见 [`graph.example.toml`](../graph.example.toml)（`[docs]` 类别、
`[[code]]` 目录、`[[rules]]`、`[scan]` 排除、`[dead_code]` 豁免、颜色固定）。

两个可选的纯文本配套文件，都在项目根目录查找:

- `known-brokens.txt` —— `verify-doc-links` 误报的白名单（每行一个精确路径）。
- `exclude-dirs.txt` —— 要跳过的目录名列表，仅在 git 不可用时使用（有 git 时，
  `.gitignore` 才是事实来源）。

## CLI 参考（build-graph）

| 标志 | 作用 |
|---|---|
| `--root PATH` | 要扫描的项目根（默认: cwd） |
| `--config PATH` | graph.toml 位置（默认: `<root>/graph.toml`） |
| `--output PATH` | HTML 输出（默认: `docs/graph.html` 或 `[output].path`） |
| `--scope full\|package` | 整个仓库（默认）或仅包+测试+文档 |
| `--json` / `--compact` | 详细 / 面向智能体的 JSON 快照 |
| `--docs-only` / `--no-tests` | 缩减节点集合 |
| `--no-cdn` | 完全离线输出: 内联嵌入 D3.js（经 SHA-256 校验）并去掉外部字体链接 |
| `--mock-git` | 用于演示 / 测试的合成 git 叠加层 |
| `--diff-base REF` | ref-diff 构建: 相对某 git 引用的状态 + 边变化（未设 `--diff-head` 时 head = 工作树） |
| `--diff-head REF` | 与 `--diff-base` 并用: 与此引用比较，而非工作树 |
| `--heat-days N` | 将 Heat 叠加层限定为最近 N 天（默认: 整段历史） |
| `--coverage PATH` | 从 Cobertura 的 `coverage.xml` 启用 Coverage 叠加层 |
| `--init [--diff\|--merge\|--force]` | 配置生命周期（见上） |

## CLI 工具

`find-related-docs` 与 `verify-doc-links` 使用的正是构建图谱所用的同一个引用
扫描器 —— 地图画作代码↔文档边的东西，正是它们所查找并校验的。`graph-query`
回答关于已构建快照的问题。

### find-related-docs

反向查找: 哪些文档提到了某个给定的代码文件。在编辑某文件前运行它，即可知道
之后需要更新哪些页面；或把 `--git-added` 接入 pre-commit 钩子，让未记录的
改动在落地前被标记。

<details>
<summary>标志与示例</summary>

```bash
find-related-docs src/mypkg/core/access.py   # 单个文件（裸文件名也可）
find-related-docs --git-added -v             # pre-commit: 暂存文件，带文档行号
find-related-docs --git-modified             # 工作树: 暂存 + 未暂存的改动
```

| 标志 | 作用 |
|---|---|
| `path` | 要查找的文件或目录（裸文件名会在全项目搜索） |
| `--docs-dir PATH` | 文档目录（默认: `docs`） |
| `--exclude DIRNAME` | 跳过文档目录下任意位置的某个文件夹名（可重复） |
| `--git-added` | 检查所有暂存文件；也会对文档中仍被提及的已删除文件发出警告 |
| `--git-modified` | 检查所有已修改文件（暂存 + 未暂存） |
| `-v` / `--verbose` | 为每处提及打印 `docs/<file>.md:<line>` |

</details>

### verify-doc-links

校验你的 `.md` 文件中每一处文件引用都指向真实存在的文件。退出码使其成为可
即插即用的 CI 门禁:

<details>
<summary>标志与示例</summary>

| 退出 | 含义 |
|---|---|
| `0` | 所有引用有效 |
| `1` | 发现坏引用 |
| `2` | 目标路径无效（未找到，或不是 `.md`） |

```bash
verify-doc-links                     # 整个 docs/ 相对项目根
verify-doc-links docs/reference -v   # 单个子树，带问题行
```

```yaml
# CI 步骤（GitHub Actions）
- run: pip install graph-build
- run: verify-doc-links --root .
```

| 标志 | 作用 |
|---|---|
| `path` | 要检查的 `.md` 文件或目录（默认: `docs`） |
| `--root PATH` | 解析引用所依据的项目根（默认: cwd） |
| `--known-brokens PATH` | 白名单文件（默认: `<root>/known-brokens.txt`） |
| `-v` / `--verbose` | 显示问题行 |

除 `known-brokens.txt` 外，误报还可用 HTML 注释（在渲染后的 Markdown 中不可见）
就地静默: 同一行的 `<!-- broken-link-ok -->`、围住一段的
`<!-- broken-links-ok-start -->` / `<!-- broken-links-ok-end -->`，或文件中任意处
的 `<!-- ignore-ref: path/to/file.py -->`。

</details>

### graph-query

无需打开浏览器即可向图谱提问。作用于 `--json` 或 `--compact` 写出的 JSON
（自动检测；默认 `docs/graph-compact.json`）:

<details>
<summary>标志与示例</summary>

```bash
graph-query blast-radius app/core.py   # 传递性导入者 + 提到它们的每个文档
graph-query hubs --top 15              # 连接最多的文件，in/out 拆分
graph-query stale-docs --check         # 比其所描述代码更旧的文档（CI 门禁: exit 1）
graph-query orphans --type code        # 完全没有边的文件
```

| 命令 | 回答 |
|---|---|
| `blast-radius <path>` | 「碰这个文件会坏什么」—— 传递性的入向导入（用 `--depth`、`--edges` 调节），外加受影响的文档 |
| `hubs` | 「重心在哪」—— 按入+出边排序的顶端节点（`--top N`） |
| `stale-docs` | 「哪些文档落后于代码」—— 比较最后提交时间（一次 `git log`；回退到 mtime），CI 用 `--check` |
| `orphans` | 「什么都没连上的东西」—— 度数为 0 的节点，可按类别过滤 |

每个命令都接受 `--json` 以输出机器可读结果 —— 用管道传给 `jq`，或交给
智能体。

</details>

## 已知限制

静态分析有天然的边界 —— 图谱是一张引用性的地图，而非语义地图:

- 动态导入仅对字面量 / 由顶层常量设定的模块名解析（f-string、字典查找、
  条件性重新绑定会被跳过）。
- `eval` / `exec` 和按字符串的依赖注入不可见。`pyproject.toml` 里的
  `[project.scripts]` / `[project.gui-scripts]` 入口点会被读取，但仅用于把这些
  模块从死代码标记中豁免 —— 并不创建边。
- Markdown 模板化（`{{ ref }}`、Jekyll/Hugo 短代码）不会被解析。
- 链接解析到整个文件 —— 章节锚点（`file.md#part`）映射到文件节点。
- code→code 边目前仅限 Python（markdown / 文档层与语言无关）。
- 一个仓库对应一张图谱；符号链接按物理路径处理。

## 许可证

[MIT](../LICENSE) © Yuriy Totyshev
