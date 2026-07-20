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
  <b>Português</b> |
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
  <a href="#projetado-para-agentes-de-ia"><img src="https://img.shields.io/badge/LLM--Agent-friendly-blueviolet" alt="LLM-Agent friendly"></a>
  <a href="../CONTRIBUTING.md"><img src="https://img.shields.io/badge/PRs-welcome-brightgreen" alt="PRs Welcome"></a>
</p>

<p align="center">
  <a href="https://mr-freewan.github.io/build-graph/"><img src="https://img.shields.io/badge/demo-online-blueviolet?style=for-the-badge&logo=googlechrome&logoColor=white" alt="Live demo"></a>
  <a href="https://codespaces.new/Mr-Freewan/build-graph"><img src="https://github.com/codespaces/badge.svg" alt="Open in GitHub Codespaces"></a>
</p>

> **Memória arquitetural para as suas refatorações.** Uma visão do raio de impacto
> das suas mudanças no código, na documentação e no git — num único mapa interativo
> legível tanto por você quanto pelo seu agente de IA. Um conjunto de utilitários
> leves e uma interface simples, mas muito funcional, na forma de um documento HTML
> autônomo que pode ser compartilhado «como está». Leveza e privacidade.

O `build-graph` desenha um **grafo interativo num único arquivo HTML** que conecta
cinco camadas que nenhuma outra ferramenta combina:

- **código → código** — importações de Python (baseadas em AST, cientes de
  `TYPE_CHECKING`)
- **código ↔ documentação** — quais arquivos markdown mencionam quais fontes
- **desvio do git** — camada de added / modified / renamed / deleted mais nós
  fantasma para arquivos que já não existem
- **mapa de calor de mudanças** — permite localizar e atenuar os pontos quentes de
  mudanças, junto com as prováveis fontes de bugs
- **mapa de cobertura de testes** — lê o `coverage.xml` do projeto e mostra a
  cobertura num relance, destacando os arquivos menos cobertos

…e exporta o mesmo mapa como um **JSON compacto e econômico em tokens**, pensado
para o contexto de um agente LLM.

E tudo isso com **zero dependências**: pura biblioteca padrão de Python,
`pip install` não traz mais nada. O único código de terceiros é o D3.js no
navegador, carregado de um CDN com fixação SRI ou totalmente incorporado com
`--no-cdn` para autonomia completa.

![O layout de forças se estabiliza num projeto real — 1070 nós / 6279 arestas, tema escuro](../docs/media/hero.gif)

**[▶ Demonstração ao vivo](https://mr-freewan.github.io/build-graph/)** — o grafo
deste próprio repositório (dogfood), com uma camada sintética `--mock-git` para que
os modos Git e de cobertura também sejam clicáveis.
**[📖 Guia da interface](guide.pt.md)** — um passo a passo conciso das funções
principais.

## Instalação

```bash
pip install graph-build        # ou: uv tool install graph-build
```

Instale diretamente do GitHub:

```bash
pip install git+https://github.com/Mr-Freewan/build-graph.git

# ou a partir de um clone:
git clone https://github.com/Mr-Freewan/build-graph.git
pip install ./build-graph
```

> A distribuição no PyPI se chama `graph-build` (o nome direto está ocupado); os
> nomes dos comandos instalados permanecem os mesmos: `build-graph`,
> `find-related-docs`, `verify-doc-links`.

## Início rápido

```bash
cd your-project
build-graph                    # autodescoberta, sem configuração → docs/graph.html
build-graph --compact          # + docs/graph-compact.json para agentes de IA
build-graph --init             # opcional: fixar a estrutura detectada em graph.toml
```

Duas ferramentas complementares — `find-related-docs` (busca inversa: código →
docs) e `verify-doc-links` (verificação de links quebrados para CI) — vêm no mesmo
pacote; veja [Ferramentas CLI](#ferramentas-cli).

## Por que não outras ferramentas?

- **pydeps / Import Linter** — apenas importações; sem camada de documentação, sem
  desvio do git.
- **lychee e afins** — verificam URLs mortas; sem mapa, sem camada de código.
- **Visão de grafo do Obsidian** — apenas notas; não vê o seu código.
- **Repomix / Gitingest** — empacotam o *texto* do repositório para LLMs;
  o build-graph fornece a *estrutura*: ~2 % dos tokens que o texto bruto custaria
  (veja [os números](#quanto-custa-em-contexto)).
- **Graphify / Understand-Anything** — ferramentas de grafo de conhecimento que
  arrastam pilhas de dependências mais pesadas e se apoiam num LLM não determinístico
  para a análise; o build-graph é determinístico e sem dependências, e acrescenta as
  camadas de git e doc-sync que nenhuma das duas tem.

## Projetado para agentes de IA

O `--compact` escreve um snapshot JSON autodocumentado (legenda incorporada, nós
indexados, códigos de tipo de três letras) que os agentes usam para:

1. **Raio de impacto** — as importações de entrada do arquivo que você vai mudar,
   sem grep.
2. **Roteamento de documentação** — qual ADR / documento de referência ler *antes*
   de editar um arquivo.
3. **Doc-sync de três camadas** — o grafo mostra (1) o que está documentado, (2) o
   que deveria estar mas não está, e (3) o que está documentado mas já não existe
   (nós fantasma = detector de obsolescência).

Adicione `build-graph --compact` a um hook de pre-commit ou a um passo de CI para
que o mapa fique atualizado a cada sessão do agente.

### O formato compacto

O `--compact` escreve `graph-compact.json` (esquema v2): os nós como um array
indexado, as arestas como linhas `[índice_origem, índice_destino, tipo,
[números_de_linha]]`, códigos de três letras para cada categoria e tipo de aresta. A
chave `legend` incorpora a tabela de decodificação completa — um agente não precisa
de esquema externo, o arquivo se explica sozinho:

```jsonc
{
  "v": "2.0",
  "legend": { "...": "o que cada campo e código abaixo significam" },
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

`p` — caminho, `t` — categoria, `d` — grau, `s` — status do git (omitido quando
limpo). Tipos de aresta: `c2c` importações, `c2d` menções em docs, `d2d` links
entre docs, `dcs` referências de docstring, `typ` apenas `TYPE_CHECKING`, `ren`
renomeações do git. Arquivos excluídos mas ainda mencionados viajam como nós
fantasma (`"G": 1`).

### Quanto custa em contexto

Números reais de um repositório em produção — 1.070 arquivos mapeados, 6.279
arestas (tokens ≈ bytes / 4, a estimativa aproximada usual):

| O que você coloca no contexto        | Tamanho | ≈ Tokens   |
|--------------------------------------|--------:|-----------:|
| Os próprios arquivos mapeados        |   15 MB | ~3.700.000 |
| `--json` (snapshot detalhado)        |  1,6 MB |   ~410.000 |
| **`--compact`**                      | **0,33 MB** | **~80.000** |

Toda a arquitetura — cada importação, cada menção em docs, cada referência obsoleta
— cabe em ~2 % do que o texto bruto custaria, e entra numa única sessão de contexto
de 200 k com folga para trabalhar. Sem o mapa, um agente redescobre essa estrutura a
cada sessão: dezenas de greps especulativos e leituras de arquivos que queimam uma
quantidade comparável de tokens *por pergunta*, não uma única vez. Em projetos
pequenos o mapa é quase de graça — o snapshot compacto deste próprio repositório
tem 4 KB ≈ ~1.000 tokens.

<details>
<summary>Não confie nesses números — meça o seu próprio repositório</summary>

```bash
$ build-graph --root . --bench

Context cost on this repo (tokens ~= bytes / 4):

  What you put in context            Size      ~Tokens  vs corpus
  raw corpus (1070 files)         14.3 MB    3,757,913     100.0%
  --json export (schema v1)        1.5 MB      397,419      10.6%
  --compact export (schema v2)   311.4 KB       79,729      2.1%
```

O `--bench` apenas mede — não escreve arquivo algum.

</details>

### Um prompt para começar

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

**Mais receitas:** [Prompts para agentes de IA](agent-prompts.pt.md) — prompts
prontos para raio de impacto, doc-sync de três camadas, detecção de fantasmas e caça
a código morto.

## O grafo interativo

- **Renderizador Canvas** — fluido com mais de 1000 nós / 6000 arestas (layout
  pré-aquecido, culling por viewport, LOD de rótulos).
- **6 tipos de aresta** — doc→doc, code→doc, code→code, apenas-tipo
  (`TYPE_CHECKING`), menções de docstring, renomeações do git.
- **Camada Git** — cores de status + nós fantasma + arestas de renomeação;
  `--mock-git` para uma demo sintética.
- **Diff do grafo** — `--diff-base REF` compara a árvore de trabalho com um ref do
  git: os status dos arquivos alimentam a camada Git, as novas arestas de
  dependência aparecem em verde e as removidas em vermelho (tracejado), com
  contadores na legenda. Adicione `--diff-head REF` para comparar dois refs
  específicos em vez disso.
- **Camada Heat** — cor dos nós por frequência de commits do git (gradiente
  azul→vermelho), todo o histórico por padrão ou os últimos N dias com
  `--heat-days N`. Um deslizador min-edits na legenda oculta tudo o que for mais
  frio que o limiar escolhido — as arestas acompanham. Mutuamente exclusiva com a
  camada Git (ambas recolorem os nós, então apenas uma fica ativa por vez); ao
  contrário do modo Git, é aditiva: a camada Node types continua visível e utilizável
  por baixo.
- **Camada Coverage** — cor dos nós por cobertura de linhas de teste (gradiente
  verde→vermelho — esta serve para encontrar arquivos mal cobertos, por isso lê-se ao
  contrário de Heat) a partir de um `coverage.xml` do Cobertura (`--coverage PATH`,
  p. ex. `pytest --cov=your_pkg --cov-report=xml`). Um deslizador max-coverage oculta
  tudo o que estiver coberto *acima* do teto escolhido, isolando os arquivos pior
  cobertos conforme você o baixa; ativá-la também oculta automaticamente na legenda
  todos os Node types exceto o código (de volta com um clique). Também exclusiva com
  Git e Heat. Desligada — e o seu botão oculto — quando nenhum relatório é fornecido.
- **Tooltip do nó** — passe o mouse sobre qualquer nó para ver seu nome e caminho;
  no modo Heat ou Coverage, também o número de edições ou a porcentagem de cobertura
  por trás da cor. Os tooltips de aresta se desativam enquanto qualquer um desses
  modos estiver ativo.
- **Auxílios de análise** — candidatos a código morto, detector de ciclos de
  importação (Tarjan SCC sobre importações em tempo de execução; as arestas
  `TYPE_CHECKING` não contam), anel de órfãos, caminho mais curto entre dois nós
  (Shift+clique), isolar um tipo, excluir por nome. A mera menção num doc de um
  arquivo homônimo (`config.py` com dezenas de correspondências, sem caminho) é
  atribuída a um único nó da categoria `ambiguous`, em vez de se dispersar por todos
  os candidatos.
- **Compartilhamento** — visões codificadas na URL (Copy link), exportação Mermaid
  do subgrafo em foco, exportação de JSON completo/compacto.
- **Conforto** — 10 idiomas de interface, temas escuro/claro, paletas
  pastel/saturada afinadas por matiz, painéis de vidro arrastáveis, deep links para
  a IDE (VS Code / Cursor / PyCharm), FAQ integrado (`?`).

Tudo cabe em **um único arquivo HTML autônomo** — anexe-o a um PR, envie-o no chat,
abra-o offline.

## Configuração (opcional)

A autodescoberta classifica cada arquivo versionado por natureza (código /
documentação / configuração / locale) × localização, detecta o seu pacote e o layout
dos docs, e gera cores determinísticas. Um `graph.toml` é apenas um override:

```bash
build-graph --init           # gerar graph.toml fixando a estrutura atual
build-graph --init --diff    # relatar o desvio (novas pastas, pins obsoletos), sem mudar nada
build-graph --init --merge   # acrescentar cobertura de novas pastas, mantendo suas edições
```

Veja o formato anotado em [`graph.example.toml`](../graph.example.toml)
(categorias `[docs]`, diretórios `[[code]]`, `[[rules]]`, exclusões `[scan]`,
isenções `[dead_code]`, pins de cor).

Dois complementos opcionais em texto puro, ambos buscados na raiz do projeto:

- `known-brokens.txt` — lista branca para os falsos positivos do `verify-doc-links`
  (um caminho exato por linha).
- `exclude-dirs.txt` — lista de nomes de diretório a pular, usada apenas quando o
  git não está disponível (com git, `.gitignore` é a fonte da verdade).

## Referência da CLI (build-graph)

| Flag | Efeito |
|---|---|
| `--root PATH` | raiz do projeto a escanear (padrão: cwd) |
| `--config PATH` | localização do graph.toml (padrão: `<root>/graph.toml`) |
| `--output PATH` | saída HTML (padrão: `docs/graph.html` ou `[output].path`) |
| `--scope full\|package` | repo inteiro (padrão) ou apenas pacote+testes+docs |
| `--json` / `--compact` | snapshots JSON detalhado / orientado ao agente |
| `--docs-only` / `--no-tests` | reduzir o conjunto de nós |
| `--no-cdn` | saída totalmente offline: incorporar D3.js inline (verificado por SHA-256) e remover o link de fonte externa |
| `--mock-git` | camada git sintética para demos/testes |
| `--diff-base REF` | build de ref-diff: status + mudanças de arestas em relação a um ref do git (head = árvore de trabalho salvo se `--diff-head` for definido) |
| `--diff-head REF` | com `--diff-base`: comparar com este ref em vez da árvore de trabalho |
| `--heat-days N` | restringir a camada Heat aos últimos N dias (padrão: todo o histórico) |
| `--coverage PATH` | ativar a camada Coverage a partir de um `coverage.xml` do Cobertura |
| `--init [--diff\|--merge\|--force]` | ciclo de vida da configuração (veja acima) |

## Ferramentas CLI

`find-related-docs` e `verify-doc-links` usam o mesmo scanner de referências a partir
do qual o grafo é construído — o que o mapa desenha como aresta código↔docs é
exatamente o que eles buscam e verificam. `graph-query` responde a perguntas sobre um
snapshot já construído.

### find-related-docs

Busca inversa: quais docs mencionam um dado arquivo de código. Execute-o antes de
editar um arquivo para saber quais páginas precisarão ser atualizadas depois, ou
conecte `--git-added` a um hook de pre-commit para que mudanças não documentadas
sejam sinalizadas antes de entrarem.

<details>
<summary>Flags e exemplos</summary>

```bash
find-related-docs src/mypkg/core/access.py   # um arquivo (o nome sozinho também funciona)
find-related-docs --git-added -v             # pre-commit: arquivos em stage, com números de linha dos docs
find-related-docs --git-modified             # árvore de trabalho: mudanças em stage + fora do stage
```

| Flag | Efeito |
|---|---|
| `path` | arquivo ou diretório a buscar (um nome sozinho é buscado no projeto inteiro) |
| `--docs-dir PATH` | diretório de documentação (padrão: `docs`) |
| `--exclude DIRNAME` | pular um nome de pasta em qualquer ponto sob o diretório de docs (repetível) |
| `--git-added` | verificar todos os arquivos em stage; também avisa sobre arquivos excluídos ainda mencionados nos docs |
| `--git-modified` | verificar todos os arquivos modificados (em stage + fora do stage) |
| `-v` / `--verbose` | imprimir `docs/<file>.md:<line>` para cada menção |

</details>

### verify-doc-links

Verifica se cada referência a arquivo nos seus `.md` aponta para um arquivo real. Os
códigos de saída o tornam um gate de CI pronto para usar:

<details>
<summary>Flags e exemplos</summary>

| Saída | Significado |
|---|---|
| `0` | todas as referências válidas |
| `1` | referências quebradas encontradas |
| `2` | caminho de destino inválido (não encontrado ou não é `.md`) |

```bash
verify-doc-links                     # todo o docs/ contra a raiz do projeto
verify-doc-links docs/reference -v   # uma subárvore, com as linhas problemáticas
```

```yaml
# Passo de CI (GitHub Actions)
- run: pip install graph-build
- run: verify-doc-links --root .
```

| Flag | Efeito |
|---|---|
| `path` | arquivo `.md` ou diretório a verificar (padrão: `docs`) |
| `--root PATH` | raiz do projeto contra a qual as referências são resolvidas (padrão: cwd) |
| `--known-brokens PATH` | arquivo de lista branca (padrão: `<root>/known-brokens.txt`) |
| `-v` / `--verbose` | mostrar as linhas problemáticas |

Além de `known-brokens.txt`, os falsos positivos podem ser silenciados em linha com
comentários HTML (invisíveis no Markdown renderizado): `<!-- broken-link-ok -->` na
mesma linha, `<!-- broken-links-ok-start -->` / `<!-- broken-links-ok-end -->` ao
redor de um bloco, ou `<!-- ignore-ref: path/to/file.py -->` em qualquer lugar do
arquivo.

</details>

### graph-query

Faça perguntas ao grafo sem abrir um navegador. Funciona sobre o JSON escrito por
`--json` ou `--compact` (detectado automaticamente; padrão
`docs/graph-compact.json`):

<details>
<summary>Flags e exemplos</summary>

```bash
graph-query blast-radius app/core.py   # importadores transitivos + cada doc que os menciona
graph-query hubs --top 15              # arquivos mais conectados, divisão in/out
graph-query stale-docs --check         # docs mais velhos que o código que descrevem (gate de CI: exit 1)
graph-query orphans --type code        # arquivos sem nenhuma aresta
```

| Comando | Responde a |
|---|---|
| `blast-radius <path>` | «o que quebra se eu tocar neste arquivo» — importações de entrada transitivas (`--depth`, `--edges` para ajustar), mais os docs afetados |
| `hubs` | «onde está o centro de gravidade» — nós de topo por arestas entrada+saída (`--top N`) |
| `stale-docs` | «quais docs estão atrasados em relação ao código» — compara as últimas datas de commit (uma passagem de `git log`; fallback para mtime), `--check` para CI |
| `orphans` | «o que não está conectado a nada» — nós de grau 0, filtráveis por categoria |

Cada comando aceita `--json` para saída legível por máquina — canalize-a para `jq`
ou entregue-a a um agente.

</details>

## Limitações conhecidas

A análise estática tem fronteiras naturais — o grafo é um mapa referencial, não
semântico:

- As importações dinâmicas são resolvidas apenas para nomes de módulo literais /
  fixados por constantes de nível superior (f-strings, buscas em dict, rebinding
  condicional são ignorados).
- `eval` / `exec` e a DI por string são invisíveis. Os pontos de entrada
  `[project.scripts]` / `[project.gui-scripts]` do `pyproject.toml` são lidos, mas
  apenas para isentar esses módulos da marcação como código morto — não criam
  arestas.
- O templating de Markdown (`{{ ref }}`, shortcodes de Jekyll/Hugo) não é analisado.
- Os links se resolvem para arquivos inteiros — as âncoras de seção (`file.md#part`)
  mapeiam para o nó do arquivo.
- As arestas código→código são, por enquanto, apenas de Python (as camadas
  markdown/docs são independentes de linguagem).
- Um repo por grafo; os symlinks são tratados como caminhos físicos.

## Licença

[MIT](../LICENSE) © Yuriy Totyshev
