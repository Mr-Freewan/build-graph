<p align="center">
  <img src="../docs/media/banner.jpg" alt="build-graph" width="840">
</p>

<p align="center">
  <a href="README.de.md">Deutsch</a> |
  <a href="../README.md">English</a> |
  <a href="README.es.md">Español</a> |
  <a href="README.fr.md">Français</a> |
  <a href="README.it.md">Italiano</a> |
  <b>日本語</b> |
  <a href="README.ko.md">한국어</a> |
  <a href="README.pt.md">Português</a> |
  <a href="README.ru.md">Русский</a> |
  <a href="README.zh.md">中文</a>
</p>

<p align="center">
  <a href="https://github.com/Mr-Freewan/build-graph/actions/workflows/ci.yml"><img src="https://github.com/Mr-Freewan/build-graph/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <a href="https://pypi.org/project/graph-build/"><img src="https://img.shields.io/pypi/v/graph-build" alt="PyPI"></a>
  <img src="https://img.shields.io/badge/python-3.11%2B-blue" alt="Python 3.11+">
  <img src="https://img.shields.io/badge/dependencies-0-brightgreen" alt="Zero dependencies">
  <a href="../LICENSE"><img src="https://img.shields.io/badge/license-MIT-green" alt="License: MIT"></a>
  <a href="https://github.com/astral-sh/ruff"><img src="https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json" alt="Ruff"></a>
  <a href="#ai-エージェント向けの設計"><img src="https://img.shields.io/badge/LLM--Agent-friendly-blueviolet" alt="LLM-Agent friendly"></a>
  <a href="../CONTRIBUTING.md"><img src="https://img.shields.io/badge/PRs-welcome-brightgreen" alt="PRs Welcome"></a>
</p>

<p align="center">
  <a href="https://mr-freewan.github.io/build-graph/"><img src="https://img.shields.io/badge/demo-online-blueviolet?style=for-the-badge&logo=googlechrome&logoColor=white" alt="Live demo"></a>
  <a href="https://codespaces.new/Mr-Freewan/build-graph"><img src="https://github.com/codespaces/badge.svg" alt="Open in GitHub Codespaces"></a>
</p>

> **リファクタリングのためのアーキテクチャ記憶。** コード・ドキュメント・git
> にまたがる変更の影響範囲を、あなたと AI エージェントの両方が読める 1 枚の
> インタラクティブなマップで俯瞰できます。軽量なユーティリティ群と、シンプル
> ながら非常に機能的な UI を、そのまま共有できる自己完結型の HTML
> ドキュメントとして提供します。軽量で、プライベート。

`build-graph` は、他のどのツールも組み合わせない 5 つのレイヤーを結ぶ **単一
HTML ファイルのインタラクティブなグラフ** を描画します:

- **コード → コード** — Python のインポート（AST ベース、`TYPE_CHECKING`
  対応）
- **コード ↔ ドキュメント** — どの markdown ファイルがどのソースを言及している
  か
- **git ドリフト** — added / modified / renamed / deleted のオーバーレイと、
  もう存在しないファイルのゴーストノード
- **ファイル変更のヒートマップ** — 変更が集中するホットスポットと、潜在的な
  バグの発生源を突き止めて手当てできます
- **テストカバレッジのマップ** — プロジェクトの `coverage.xml` を読み込み、
  カバレッジを一目で示し、最もカバーされていないファイルを強調します

…そして同じマップを、LLM エージェントのコンテキストに投入するための **コンパクト
でトークン効率の良い JSON** としてエクスポートします。

しかもそのすべてが **依存ゼロ**。純粋な Python 標準ライブラリのみで、
`pip install` は他に何も引き込みません。唯一のサードパーティコードはブラウザ上の
D3.js で、SRI ピン留めした CDN から読み込むか、`--no-cdn` で完全に埋め込んで
完全なオフライン化ができます。

![力学レイアウトが実際のプロジェクトで安定する様子 — 1070 ノード / 6279 エッジ、ダークテーマ](../docs/media/hero.gif)

**[▶ ライブデモ](https://mr-freewan.github.io/build-graph/)** — まさにこの
リポジトリのグラフ（ドッグフーディング）です。合成の `--mock-git`
オーバーレイ付きなので、Git モードとカバレッジモードもクリックできます。
**[📖 UI ガイド](guide.ja.md)** — 主要機能を 1 つずつたどる簡潔な
ウォークスルー。

## インストール

```bash
pip install graph-build        # または: uv tool install graph-build
```

GitHub から直接インストール:

```bash
pip install git+https://github.com/Mr-Freewan/build-graph.git

# またはクローンから:
git clone https://github.com/Mr-Freewan/build-graph.git
pip install ./build-graph
```

> PyPI 上の配布名は `graph-build` です（直接の名前は使用済み）。インストール
> されるコマンド名はそのまま変わりません: `build-graph`、`find-related-docs`、
> `verify-doc-links`。

## クイックスタート

```bash
cd your-project
build-graph                    # 自動検出、設定不要 → docs/graph.html
build-graph --compact          # + AI エージェント向けの docs/graph-compact.json
build-graph --init             # 任意: 検出した構造を graph.toml に固定
```

2 つのコンパニオン CLI — `find-related-docs`（逆引き: コード → ドキュメント）と
`verify-doc-links`（CI 向けのリンク切れチェック）— は同じパッケージに含まれます。
[CLI ツール](#cli-ツール) を参照してください。

## なぜ他のツールではないのか

- **pydeps / Import Linter** — インポートのみ。ドキュメント層も git ドリフトも
  ない。
- **lychee など** — デッド URL をチェックするだけ。マップもコード層もない。
- **Obsidian のグラフビュー** — ノートのみ。あなたのコードは見えない。
- **Repomix / Gitingest** — リポジトリの *テキスト* を LLM 向けに固める。
  build-graph は *構造* を渡す: 生テキストにかかるトークンの約 2 %
  （[数字](#コンテキストでのコスト) を参照）。
- **Graphify / Understand-Anything** — より重い依存スタックを引き込み、分析を
  非決定的な LLM に頼るナレッジグラフ系ツール。build-graph は決定的で依存ゼロ、
  さらにどちらも持たない git 層と doc-sync 層を備えます。

## AI エージェント向けの設計

`--compact` は自己記述的な JSON スナップショット（埋め込みの凡例、インデックス
化されたノード、3 文字のタイプコード）を書き出します。エージェントはこれを次の
用途に使います:

1. **影響範囲** — これから変更するファイルへの受信インポートを、grep なしで。
2. **ドキュメントのルーティング** — ファイルを編集する *前* に読むべき ADR /
   リファレンス文書。
3. **3 層の doc-sync** — グラフは (1) 何が文書化されているか、(2) 文書化される
   べきだが未対応のもの、(3) 文書化されているがもう存在しないもの（ゴーストノード
   = 陳腐化検出器）を示します。

`build-graph --compact` を pre-commit フックや CI ステップに加えると、
エージェントのセッションごとにマップが最新に保たれます。

### コンパクトフォーマット

`--compact` は `graph-compact.json`（スキーマ v2）を書き出します: ノードは
インデックス配列、エッジは `[ソース索引, ターゲット索引, タイプ, [行番号]]` の
行、各カテゴリとエッジタイプに 3 文字コード。`legend` キーは完全なデコード表を
埋め込むため、エージェントに外部スキーマは不要で、ファイルが自らを説明します:

```jsonc
{
  "v": "2.0",
  "legend": { "...": "以下の各フィールドとコードの意味" },
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

`p` — パス、`t` — カテゴリ、`d` — 次数、`s` — git ステータス（クリーンなときは
省略）。エッジタイプ: `c2c` インポート、`c2d` ドキュメント言及、`d2d` ドキュメント
リンク、`dcs` docstring 参照、`typ` `TYPE_CHECKING` のみ、`ren` git リネーム。
削除されたが依然として言及されているファイルは、ゴーストノードとして同行します
（`"G": 1`）。

### コンテキストでのコスト

本番リポジトリの実数値 — マッピング済み 1,070 ファイル、6,279 エッジ
（トークン ≈ バイト / 4、いつもの粗い見積もり）:

| コンテキストに入れるもの             |   サイズ | ≈ トークン |
|--------------------------------------|---------:|-----------:|
| マッピングされたファイルそのもの     |   15 MB | ~3,700,000 |
| `--json`（詳細スナップショット）     |  1.6 MB |   ~410,000 |
| **`--compact`**                      | **0.33 MB** | **~80,000** |

アーキテクチャ全体 — すべてのインポート、すべてのドキュメント言及、すべての
陳腐化した参照 — が、生テキストにかかるコストの約 2 % に収まり、作業の余裕を
残して 200k コンテキストの 1 セッションに収まります。マップがなければ、
エージェントは毎セッションこの構造を再発見します: 数十の投機的な grep と
ファイル読み込みが、1 回きりではなく *質問ごとに* 同程度のトークンを燃やします。
小さなプロジェクトではマップはほぼ無料です — このリポジトリのコンパクト
スナップショットは 4 KB ≈ 約 1,000 トークンです。

<details>
<summary>これらの数字を鵜呑みにせず — 自分のリポジトリで測ってください</summary>

```bash
$ build-graph --root . --bench

Context cost on this repo (tokens ~= bytes / 4):

  What you put in context            Size      ~Tokens  vs corpus
  raw corpus (1070 files)         14.3 MB    3,757,913     100.0%
  --json export (schema v1)        1.5 MB      397,419      10.6%
  --compact export (schema v2)   311.4 KB       79,729      2.1%
```

`--bench` は測定するだけ — ファイルは一切書き込みません。

</details>

### 出発点となるプロンプト

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

**さらにレシピ:** [AI エージェント向けプロンプト](agent-prompts.ja.md) —
影響範囲、3 層の doc-sync、ゴースト検出、デッドコード狩りのためのすぐ使える
プロンプト集。

## インタラクティブなグラフ

- **Canvas レンダラー** — 1000+ ノード / 6000+ エッジでも滑らか（事前ウォーム
  アップしたレイアウト、ビューポートカリング、ラベル LOD）。
- **6 種類のエッジ** — doc→doc、code→doc、code→code、タイプのみ
  （`TYPE_CHECKING`）、docstring 言及、git リネーム。
- **Git オーバーレイ** — ステータス色 + ゴーストノード + リネームエッジ。
  合成デモ用の `--mock-git`。
- **グラフ diff** — `--diff-base REF` は作業ツリーを git 参照と比較します: ファイル
  ステータスが Git オーバーレイに反映され、新しい依存エッジは緑、削除された
  エッジは赤（破線）で、凡例にカウンターが出ます。`--diff-head REF` を加えると、
  代わりに 2 つの特定の参照を比較します。
- **Heat オーバーレイ** — git コミット頻度によるノード色（青→赤のグラデーション）。
  既定では全履歴、`--heat-days N` で直近 N 日に限定。凡例の min-edits スライダーは
  選んだしきい値より冷たいものをすべて隠し、エッジも追随します。Git オーバーレイと
  相互排他（どちらもノードを塗り替えるため同時にはひとつだけ）。Git モードと違い
  加算的で、下地の Node types 層は見えたまま使えます。
- **Coverage オーバーレイ** — テスト行カバレッジによるノード色（緑→赤の
  グラデーション — こちらはカバレッジの低いファイルを見つけるためで、Heat とは
  逆に読みます）。Cobertura の `coverage.xml` から（`--coverage PATH`、例:
  `pytest --cov=your_pkg --cov-report=xml`）。max-coverage スライダーは選んだ上限
  *より多く* カバーされたものを隠し、下げるほど最もカバレッジの低いファイルを
  分離します。有効化すると凡例でコード以外の Node types も自動的に隠れます
  （クリックひとつで戻ります）。これも Git と Heat と相互排他。レポートが与え
  られないときはオフで、ボタンも隠れます。
- **ノードのツールチップ** — 任意のノードにホバーすると名前とパスが表示されます。
  Heat または Coverage モードでは、色の背後にある編集回数やカバレッジ率も。
  これらのモードが有効な間、エッジのツールチップは無効になります。
- **分析補助** — デッドコード候補、インポート循環検出器（ランタイムインポート上の
  Tarjan SCC。`TYPE_CHECKING` エッジは数えません）、孤立ノードのリング、2 ノード間の
  最短経路（Shift+クリック）、タイプの分離、名前による除外。同名ファイルへの
  ドキュメント内の裸の言及（パスなしで `config.py` が数十件一致）は、すべての
  候補に散らばらせず、`ambiguous` カテゴリの単一ノードに帰属させます。
- **共有** — URL エンコードされたビュー（Copy link）、フォーカス中のサブグラフの
  Mermaid エクスポート、完全 / コンパクト JSON エクスポート。
- **快適さ** — 10 の UI 言語、ダーク / ライトのテーマ、色相を揃えた
  パステル / 彩度の高いパレット、ドラッグ可能なガラスパネル、IDE ディープリンク
  （VS Code / Cursor / PyCharm）、組み込みの FAQ（`?`）。

すべてが **単一の自己完結型 HTML ファイル** に収まります — PR に添付し、チャットで
送り、オフラインで開けます。

## 設定（任意）

自動検出は、バージョン管理された各ファイルを種類（コード / ドキュメント / 設定 /
ロケール）× 場所で分類し、パッケージとドキュメントのレイアウトを検出し、決定的な
色を生成します。`graph.toml` はオーバーライドにすぎません:

```bash
build-graph --init           # 現在の構造を固定した graph.toml を生成
build-graph --init --diff    # ドリフト（新規フォルダ、陳腐化したピン）を報告し、何も変えない
build-graph --init --merge   # 新規フォルダのカバレッジを追加し、あなたの編集は保持
```

注釈付きの形式は [`graph.example.toml`](../graph.example.toml) を参照してください
（`[docs]` カテゴリ、`[[code]]` ディレクトリ、`[[rules]]`、`[scan]` 除外、
`[dead_code]` 免除、色ピン）。

任意のプレーンテキストのコンパニオンが 2 つ、どちらもプロジェクトルートで
探されます:

- `known-brokens.txt` — `verify-doc-links` の誤検知のホワイトリスト
  （1 行に 1 つの正確なパス）。
- `exclude-dirs.txt` — スキップするディレクトリ名のリスト。git が使えない場合のみ
  使用されます（git があれば `.gitignore` が真実の源）。

## CLI リファレンス（build-graph）

| フラグ | 効果 |
|---|---|
| `--root PATH` | スキャンするプロジェクトルート（既定: cwd） |
| `--config PATH` | graph.toml の場所（既定: `<root>/graph.toml`） |
| `--output PATH` | HTML 出力（既定: `docs/graph.html` または `[output].path`） |
| `--scope full\|package` | リポジトリ全体（既定）またはパッケージ+テスト+ドキュメントのみ |
| `--json` / `--compact` | 詳細 / エージェント向けの JSON スナップショット |
| `--docs-only` / `--no-tests` | ノード集合を絞る |
| `--no-cdn` | 完全オフライン出力: D3.js をインライン埋め込み（SHA-256 検証）し、外部フォントリンクを外す |
| `--mock-git` | デモ / テスト用の合成 git オーバーレイ |
| `--diff-base REF` | ref-diff ビルド: git 参照に対するステータス + エッジ変化（`--diff-head` がなければ head = 作業ツリー） |
| `--diff-head REF` | `--diff-base` と併用: 作業ツリーではなくこの参照と比較 |
| `--heat-days N` | Heat オーバーレイを直近 N 日に限定（既定: 全履歴） |
| `--coverage PATH` | Cobertura の `coverage.xml` から Coverage オーバーレイを有効化 |
| `--init [--diff\|--merge\|--force]` | 設定のライフサイクル（上記参照） |

## CLI ツール

`find-related-docs` と `verify-doc-links` は、グラフを構築するのと同じ参照
スキャナーを使います — マップがコード↔ドキュメントのエッジとして描くものが、
まさに両者が調べて検証するものです。`graph-query` は、すでに構築された
スナップショットに対する問いに答えます。

### find-related-docs

逆引き: あるコードファイルを、どのドキュメントが言及しているか。ファイルを編集
する前に実行すれば、あとでどのページを更新すべきかがわかります。あるいは
`--git-added` を pre-commit フックに組み込めば、未文書化の変更が取り込まれる前に
フラグされます。

<details>
<summary>フラグと例</summary>

```bash
find-related-docs src/mypkg/core/access.py   # 1 ファイル（裸のファイル名でも可）
find-related-docs --git-added -v             # pre-commit: ステージ済みファイル、ドキュメントの行番号付き
find-related-docs --git-modified             # 作業ツリー: ステージ済み + 未ステージの変更
```

| フラグ | 効果 |
|---|---|
| `path` | 検索するファイルまたはディレクトリ（裸のファイル名はプロジェクト全体で検索） |
| `--docs-dir PATH` | ドキュメントディレクトリ（既定: `docs`） |
| `--exclude DIRNAME` | ドキュメントディレクトリ配下のどこかにあるフォルダ名をスキップ（繰り返し可） |
| `--git-added` | ステージ済みファイルをすべてチェック。ドキュメントに残る削除済みファイルも警告 |
| `--git-modified` | 変更されたファイルをすべてチェック（ステージ済み + 未ステージ） |
| `-v` / `--verbose` | 各言及について `docs/<file>.md:<line>` を出力 |

</details>

### verify-doc-links

`.md` ファイル内のすべてのファイル参照が実在するファイルを指すかを検証します。
終了コードにより、そのまま CI ゲートとして使えます:

<details>
<summary>フラグと例</summary>

| 終了 | 意味 |
|---|---|
| `0` | すべての参照が有効 |
| `1` | リンク切れが見つかった |
| `2` | ターゲットパスが無効（見つからない、または `.md` でない） |

```bash
verify-doc-links                     # docs/ 全体をプロジェクトルートに対して
verify-doc-links docs/reference -v   # 1 つのサブツリー、該当行付き
```

```yaml
# CI ステップ（GitHub Actions）
- run: pip install graph-build
- run: verify-doc-links --root .
```

| フラグ | 効果 |
|---|---|
| `path` | チェックする `.md` ファイルまたはディレクトリ（既定: `docs`） |
| `--root PATH` | 参照を解決するプロジェクトルート（既定: cwd） |
| `--known-brokens PATH` | ホワイトリストファイル（既定: `<root>/known-brokens.txt`） |
| `-v` / `--verbose` | 該当行を表示 |

`known-brokens.txt` のほか、誤検知は HTML コメント（レンダリング後の Markdown
では不可視）でインラインに抑制できます: 同じ行に `<!-- broken-link-ok -->`、
ブロックを囲む `<!-- broken-links-ok-start -->` / `<!-- broken-links-ok-end -->`、
またはファイル内のどこかに `<!-- ignore-ref: path/to/file.py -->`。

</details>

### graph-query

ブラウザを開かずにグラフへ問い合わせます。`--json` または `--compact` が書き出す
JSON 上で動作します（自動検出。既定: `docs/graph-compact.json`）:

<details>
<summary>フラグと例</summary>

```bash
graph-query blast-radius app/core.py   # 推移的なインポート元 + それらを言及する各ドキュメント
graph-query hubs --top 15              # 最も接続の多いファイル、in/out の内訳
graph-query stale-docs --check         # 記述対象のコードより古いドキュメント（CI ゲート: exit 1）
graph-query orphans --type code        # エッジが 1 本もないファイル
```

| コマンド | 答えること |
|---|---|
| `blast-radius <path>` | 「このファイルを触ると何が壊れるか」— 推移的な受信インポート（`--depth`、`--edges` で調整）、および影響を受けるドキュメント |
| `hubs` | 「重心はどこか」— in+out エッジ順のトップノード（`--top N`） |
| `stale-docs` | 「どのドキュメントがコードに遅れているか」— 最終コミット時刻を比較（`git log` 1 パス。mtime フォールバック）、CI 用の `--check` |
| `orphans` | 「何にも接続していないもの」— 次数 0 のノード、カテゴリで絞り込み可 |

各コマンドは機械可読な出力用に `--json` を受け付けます — `jq` にパイプするか、
エージェントに渡してください。

</details>

## 既知の制限

静的解析には自然な境界があります — グラフは参照的なマップであり、意味論的な
ものではありません:

- 動的インポートは、リテラル / トップレベル定数で設定されたモジュール名に対して
  のみ解決されます（f-string、辞書ルックアップ、条件付き再束縛はスキップ）。
- `eval` / `exec` や文字列による DI は見えません。`pyproject.toml` の
  `[project.scripts]` / `[project.gui-scripts]` エントリポイントは読まれますが、
  それらのモジュールをデッドコード判定から除外するためだけで、エッジは作りません。
- Markdown のテンプレート化（`{{ ref }}`、Jekyll/Hugo のショートコード）は
  解析されません。
- リンクはファイル全体に解決されます — セクションアンカー（`file.md#part`）は
  ファイルノードにマップされます。
- code→code エッジは今のところ Python のみです（markdown / ドキュメント層は
  言語非依存）。
- グラフ 1 つにつきリポジトリ 1 つ。シンボリックリンクは物理パスとして扱われます。

## ライセンス

[MIT](../LICENSE) © Yuriy Totyshev
