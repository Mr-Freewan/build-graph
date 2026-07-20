<p align="center">
  <img src="../docs/media/banner.jpg" alt="build-graph" width="840">
</p>

<p align="center">
  <a href="README.de.md">Deutsch</a> |
  <a href="../README.md">English</a> |
  <a href="README.es.md">Español</a> |
  <b>Français</b> |
  <a href="README.it.md">Italiano</a> |
  <a href="README.ja.md">日本語</a> |
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
  <a href="#conçu-pour-les-agents-ia"><img src="https://img.shields.io/badge/LLM--Agent-friendly-blueviolet" alt="LLM-Agent friendly"></a>
  <a href="../CONTRIBUTING.md"><img src="https://img.shields.io/badge/PRs-welcome-brightgreen" alt="PRs Welcome"></a>
</p>

<p align="center">
  <a href="https://mr-freewan.github.io/build-graph/"><img src="https://img.shields.io/badge/demo-online-blueviolet?style=for-the-badge&logo=googlechrome&logoColor=white" alt="Live demo"></a>
  <a href="https://codespaces.new/Mr-Freewan/build-graph"><img src="https://github.com/codespaces/badge.svg" alt="Open in GitHub Codespaces"></a>
</p>

> **Mémoire architecturale pour vos refactorisations.** Un aperçu du rayon
> d'impact de vos changements sur le code, la documentation et git — sur une
> seule carte interactive que vous et votre agent IA pouvez lire. Un ensemble
> d'utilitaires légers et une interface simple mais très fonctionnelle sous la
> forme d'un document HTML autonome que l'on peut partager « tel quel ». Légèreté
> et confidentialité.

`build-graph` dessine un **graphe interactif dans un seul fichier HTML** qui relie
cinq couches qu'aucun autre outil ne combine :

- **code → code** — imports Python (basés sur l'AST, conscients de
  `TYPE_CHECKING`)
- **code ↔ documentation** — quels fichiers markdown mentionnent quelles sources
- **dérive git** — calque added / modified / renamed / deleted plus des nœuds
  fantômes pour les fichiers qui n'existent plus
- **carte de chaleur des modifications** — permet de repérer et d'apaiser les
  points chauds de changements, ainsi que les sources probables de bugs
- **carte de couverture des tests** — lit le `coverage.xml` du projet et montre la
  couverture d'un coup d'œil, en mettant en évidence les fichiers les moins
  couverts

…et exporte la même carte sous forme de **JSON compact et économe en tokens**,
conçu pour le contexte d'un agent LLM.

Et tout cela avec **zéro dépendance** : pure bibliothèque standard de Python,
`pip install` n'entraîne rien d'autre. Le seul code tiers est D3.js dans le
navigateur, chargé depuis un CDN avec épinglage SRI ou entièrement intégré avec
`--no-cdn` pour une autonomie complète.

![La disposition à forces se stabilise sur un projet réel — 1070 nœuds / 6279 arêtes, thème sombre](../docs/media/hero.gif)

**[▶ Démo en direct](https://mr-freewan.github.io/build-graph/)** — le graphe de
ce dépôt même (dogfood), avec un calque synthétique `--mock-git` pour que les
modes Git et couverture soient aussi cliquables.
**[📖 Guide de l'interface](guide.fr.md)** — une visite guidée concise, étape par
étape, des fonctions principales.

## Installation

```bash
pip install graph-build        # ou : uv tool install graph-build
```

Installez directement depuis GitHub :

```bash
pip install git+https://github.com/Mr-Freewan/build-graph.git

# ou depuis un clone :
git clone https://github.com/Mr-Freewan/build-graph.git
pip install ./build-graph
```

> La distribution PyPI s'appelle `graph-build` (le nom direct est pris) ; les
> noms des commandes installées restent les mêmes : `build-graph`,
> `find-related-docs`, `verify-doc-links`.

## Démarrage rapide

```bash
cd your-project
build-graph                    # autodécouverte, aucune configuration → docs/graph.html
build-graph --compact          # + docs/graph-compact.json pour les agents IA
build-graph --init             # optionnel : figer la structure détectée dans graph.toml
```

Deux outils compagnons — `find-related-docs` (recherche inverse : code → docs) et
`verify-doc-links` (contrôle des liens morts pour la CI) — sont livrés dans le même
paquet ; voir [Outils CLI](#outils-cli).

## Pourquoi pas d'autres outils ?

- **pydeps / Import Linter** — imports uniquement ; pas de couche documentation,
  pas de dérive git.
- **lychee et consorts** — vérifient les URL mortes ; pas de carte, pas de couche
  code.
- **Vue graphe d'Obsidian** — notes uniquement ; ne voit pas votre code.
- **Repomix / Gitingest** — empaquettent le *texte* du dépôt pour les LLM ;
  build-graph fournit la *structure* : ~2 % des tokens que coûterait le texte brut
  (voir [les chiffres](#ce-que-ça-coûte-en-contexte)).
- **Graphify / Understand-Anything** — outils de graphe de connaissances qui
  entraînent des piles de dépendances plus lourdes et s'appuient sur un LLM non
  déterministe pour l'analyse ; build-graph est déterministe et sans dépendance,
  et ajoute les couches git et doc-sync que ni l'un ni l'autre n'ont.

## Conçu pour les agents IA

`--compact` écrit un instantané JSON auto-documenté (légende intégrée, nœuds
indexés, codes de type à trois lettres) que les agents utilisent pour :

1. **Rayon d'impact** — les imports entrants du fichier que vous allez changer,
   sans grep.
2. **Routage de la documentation** — quel ADR / document de référence lire *avant*
   d'éditer un fichier.
3. **Doc-sync à trois couches** — le graphe montre (1) ce qui est documenté,
   (2) ce qui devrait l'être mais ne l'est pas, et (3) ce qui est documenté mais
   n'existe plus (nœuds fantômes = détecteur d'obsolescence).

Ajoutez `build-graph --compact` à un hook de pre-commit ou à une étape de CI pour
que la carte reste fraîche à chaque session d'agent.

### Le format compact

`--compact` écrit `graph-compact.json` (schéma v2) : les nœuds sous forme de
tableau indexé, les arêtes sous forme de lignes `[index_source, index_cible, type,
[numéros_de_ligne]]`, des codes à trois lettres pour chaque catégorie et type
d'arête. La clé `legend` intègre la table de décodage complète — un agent n'a
besoin d'aucun schéma externe, le fichier s'explique tout seul :

```jsonc
{
  "v": "2.0",
  "legend": { "...": "ce que signifie chaque champ et code ci-dessous" },
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

`p` — chemin, `t` — catégorie, `d` — degré, `s` — statut git (omis lorsque
propre). Types d'arête : `c2c` imports, `c2d` mentions dans les docs, `d2d` liens
entre docs, `dcs` références de docstring, `typ` `TYPE_CHECKING` uniquement, `ren`
renommages git. Les fichiers supprimés mais encore mentionnés voyagent comme des
nœuds fantômes (`"G": 1`).

### Ce que ça coûte en contexte

Chiffres réels d'un dépôt en production — 1 070 fichiers cartographiés, 6 279
arêtes (tokens ≈ octets / 4, l'estimation approximative habituelle) :

| Ce que vous mettez dans le contexte  | Taille | ≈ Tokens   |
|--------------------------------------|-------:|-----------:|
| Les fichiers cartographiés eux-mêmes |  15 MB | ~3 700 000 |
| `--json` (instantané détaillé)       | 1,6 MB |   ~410 000 |
| **`--compact`**                      | **0,33 MB** | **~80 000** |

Toute l'architecture — chaque import, chaque mention dans les docs, chaque
référence obsolète — tient dans ~2 % de ce que coûterait le texte brut, et entre
dans une seule session de contexte de 200 k avec de la marge pour travailler. Sans
la carte, un agent redécouvre cette structure à chaque session : des dizaines de
greps spéculatifs et de lectures de fichiers qui brûlent une quantité comparable
de tokens *par question*, et non une seule fois. Sur les petits projets, la carte
est presque gratuite — l'instantané compact de ce dépôt même pèse 4 Ko ≈ ~1 000
tokens.

<details>
<summary>Ne croyez pas ces chiffres sur parole — mesurez votre propre dépôt</summary>

```bash
$ build-graph --root . --bench

Context cost on this repo (tokens ~= bytes / 4):

  What you put in context            Size      ~Tokens  vs corpus
  raw corpus (1070 files)         14.3 MB    3,757,913     100.0%
  --json export (schema v1)        1.5 MB      397,419      10.6%
  --compact export (schema v2)   311.4 KB       79,729      2.1%
```

`--bench` ne fait que mesurer — il n'écrit aucun fichier.

</details>

### Un prompt pour démarrer

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

**Plus de recettes :** [Prompts pour agents IA](agent-prompts.fr.md) — des prompts
prêts à l'emploi pour le rayon d'impact, le doc-sync à trois couches, la détection
de fantômes et la chasse au code mort.

## Le graphe interactif

- **Rendu Canvas** — fluide à 1000+ nœuds / 6000+ arêtes (disposition
  préchauffée, culling par viewport, LOD des étiquettes).
- **6 types d'arête** — doc→doc, code→doc, code→code, type seul
  (`TYPE_CHECKING`), mentions de docstring, renommages git.
- **Calque Git** — couleurs de statut + nœuds fantômes + arêtes de renommage ;
  `--mock-git` pour une démo synthétique.
- **Diff de graphe** — `--diff-base REF` compare l'arbre de travail à une réf
  git : les statuts de fichiers alimentent le calque Git, les nouvelles arêtes de
  dépendance apparaissent en vert et les supprimées en rouge (pointillés), avec des
  compteurs dans la légende. Ajoutez `--diff-head REF` pour comparer deux réfs
  précises à la place.
- **Calque Heat** — couleur des nœuds selon la fréquence des commits git (dégradé
  bleu→rouge), tout l'historique par défaut ou les N derniers jours avec
  `--heat-days N`. Un curseur min-edits dans la légende masque tout ce qui est plus
  froid que le seuil choisi — les arêtes suivent. Mutuellement exclusif avec le
  calque Git (les deux recolorent les nœuds, un seul est donc actif à la fois) ;
  contrairement au mode Git, il est additif : la couche Node types reste visible et
  utilisable en dessous.
- **Calque Coverage** — couleur des nœuds selon la couverture de lignes de test
  (dégradé vert→rouge — celui-ci sert à trouver les fichiers mal couverts, il se
  lit donc à l'inverse de Heat) depuis un `coverage.xml` Cobertura (`--coverage
  PATH`, p. ex. `pytest --cov=your_pkg --cov-report=xml`). Un curseur max-coverage
  masque tout ce qui est couvert *au-delà* du plafond choisi, isolant les fichiers
  les moins bien couverts à mesure que vous le baissez ; l'activer masque aussi
  automatiquement dans la légende tous les Node types sauf le code (de retour en un
  clic). Également exclusif avec Git et Heat. Désactivé — et son bouton caché —
  lorsqu'aucun rapport n'est fourni.
- **Info-bulle de nœud** — survolez n'importe quel nœud pour voir son nom et son
  chemin ; en mode Heat ou Coverage, aussi le nombre de modifications ou le
  pourcentage de couverture derrière la couleur. Les info-bulles d'arête se
  désactivent tant que l'un de ces modes est actif.
- **Aides à l'analyse** — candidats au code mort, détecteur de cycles d'import
  (Tarjan SCC sur les imports d'exécution ; les arêtes `TYPE_CHECKING` ne comptent
  pas), anneau des orphelins, plus court chemin entre deux nœuds (Shift+clic),
  isoler un type, exclure par nom. La simple mention dans un doc d'un fichier
  homonyme (`config.py` avec des dizaines de correspondances, sans chemin) est
  attribuée à un unique nœud de catégorie `ambiguous`, au lieu de se disperser sur
  tous les candidats.
- **Partage** — vues encodées dans l'URL (Copy link), export Mermaid du
  sous-graphe ciblé, export JSON complet/compact.
- **Confort** — 10 langues d'interface, thèmes sombre/clair, palettes
  pastel/saturée accordées en teinte, panneaux de verre déplaçables, liens
  profonds vers l'IDE (VS Code / Cursor / PyCharm), FAQ intégrée (`?`).

Tout tient dans **un seul fichier HTML autonome** — joignez-le à une PR, envoyez-le
en chat, ouvrez-le hors ligne.

## Configuration (facultatif)

L'autodécouverte classe chaque fichier versionné par nature (code / documentation /
configuration / locale) × emplacement, détecte votre paquet et la disposition de
vos docs, et génère des couleurs déterministes. Un `graph.toml` n'est qu'un
override :

```bash
build-graph --init           # générer graph.toml en figeant la structure actuelle
build-graph --init --diff    # signaler la dérive (nouveaux dossiers, épingles obsolètes), ne rien changer
build-graph --init --merge   # ajouter la couverture des nouveaux dossiers, garder vos modifications
```

Voir le format annoté dans [`graph.example.toml`](../graph.example.toml)
(catégories `[docs]`, répertoires `[[code]]`, `[[rules]]`, exclusions `[scan]`,
exemptions `[dead_code]`, épingles de couleur).

Deux compagnons texte facultatifs, tous deux cherchés à la racine du projet :

- `known-brokens.txt` — liste blanche pour les faux positifs de `verify-doc-links`
  (un chemin exact par ligne).
- `exclude-dirs.txt` — liste de noms de répertoires à ignorer, utilisée uniquement
  quand git est indisponible (avec git, `.gitignore` est la source de vérité).

## Référence CLI (build-graph)

| Option | Effet |
|---|---|
| `--root PATH` | racine du projet à scanner (par défaut : cwd) |
| `--config PATH` | emplacement de graph.toml (par défaut : `<root>/graph.toml`) |
| `--output PATH` | sortie HTML (par défaut : `docs/graph.html` ou `[output].path`) |
| `--scope full\|package` | tout le dépôt (par défaut) ou seulement paquet+tests+docs |
| `--json` / `--compact` | instantanés JSON détaillé / orienté agent |
| `--docs-only` / `--no-tests` | réduire l'ensemble des nœuds |
| `--no-cdn` | sortie entièrement hors ligne : intégrer D3.js inline (vérifié SHA-256) et retirer le lien de police externe |
| `--mock-git` | calque git synthétique pour démos/tests |
| `--diff-base REF` | build ref-diff : statuts + changements d'arêtes par rapport à une réf git (head = arbre de travail sauf si `--diff-head` est défini) |
| `--diff-head REF` | avec `--diff-base` : comparer à cette réf au lieu de l'arbre de travail |
| `--heat-days N` | restreindre le calque Heat aux N derniers jours (par défaut : tout l'historique) |
| `--coverage PATH` | activer le calque Coverage depuis un `coverage.xml` Cobertura |
| `--init [--diff\|--merge\|--force]` | cycle de vie de la configuration (voir ci-dessus) |

## Outils CLI

`find-related-docs` et `verify-doc-links` utilisent le même scanner de références à
partir duquel le graphe est construit — ce que la carte dessine comme arête
code↔docs est exactement ce qu'ils recherchent et vérifient. `graph-query` répond
aux questions sur un instantané déjà construit.

### find-related-docs

Recherche inverse : quels docs mentionnent un fichier de code donné. Exécutez-le
avant d'éditer un fichier pour savoir quelles pages devront être mises à jour
ensuite, ou branchez `--git-added` sur un hook de pre-commit pour que les
changements non documentés soient signalés avant d'être intégrés.

<details>
<summary>Options &amp; exemples</summary>

```bash
find-related-docs src/mypkg/core/access.py   # un fichier (un nom seul fonctionne aussi)
find-related-docs --git-added -v             # pre-commit : fichiers indexés, avec numéros de ligne des docs
find-related-docs --git-modified             # arbre de travail : modifications indexées + non indexées
```

| Option | Effet |
|---|---|
| `path` | fichier ou répertoire à rechercher (un nom seul est cherché dans tout le projet) |
| `--docs-dir PATH` | répertoire de documentation (par défaut : `docs`) |
| `--exclude DIRNAME` | ignorer un nom de dossier n'importe où sous le répertoire des docs (répétable) |
| `--git-added` | vérifier tous les fichiers indexés ; avertit aussi des fichiers supprimés encore mentionnés dans les docs |
| `--git-modified` | vérifier tous les fichiers modifiés (indexés + non indexés) |
| `-v` / `--verbose` | imprimer `docs/<file>.md:<line>` pour chaque mention |

</details>

### verify-doc-links

Vérifie que chaque référence de fichier dans vos `.md` pointe vers un fichier réel.
Les codes de sortie en font un gate de CI prêt à l'emploi :

<details>
<summary>Options &amp; exemples</summary>

| Sortie | Signification |
|---|---|
| `0` | toutes les références valides |
| `1` | références cassées trouvées |
| `2` | chemin cible invalide (introuvable ou pas un `.md`) |

```bash
verify-doc-links                     # tout docs/ contre la racine du projet
verify-doc-links docs/reference -v   # un sous-arbre, avec les lignes en cause
```

```yaml
# Étape de CI (GitHub Actions)
- run: pip install graph-build
- run: verify-doc-links --root .
```

| Option | Effet |
|---|---|
| `path` | fichier `.md` ou répertoire à vérifier (par défaut : `docs`) |
| `--root PATH` | racine du projet contre laquelle les références sont résolues (par défaut : cwd) |
| `--known-brokens PATH` | fichier de liste blanche (par défaut : `<root>/known-brokens.txt`) |
| `-v` / `--verbose` | montrer les lignes en cause |

Outre `known-brokens.txt`, les faux positifs peuvent être réduits au silence en
ligne avec des commentaires HTML (invisibles dans le Markdown rendu) :
`<!-- broken-link-ok -->` sur la même ligne, `<!-- broken-links-ok-start -->` /
`<!-- broken-links-ok-end -->` autour d'un bloc, ou
`<!-- ignore-ref: path/to/file.py -->` n'importe où dans le fichier.

</details>

### graph-query

Posez des questions au graphe sans ouvrir de navigateur. Fonctionne sur le JSON
écrit par `--json` ou `--compact` (détecté automatiquement ; par défaut
`docs/graph-compact.json`) :

<details>
<summary>Options &amp; exemples</summary>

```bash
graph-query blast-radius app/core.py   # importateurs transitifs + chaque doc qui les mentionne
graph-query hubs --top 15              # fichiers les plus connectés, répartition in/out
graph-query stale-docs --check         # docs plus vieux que le code qu'ils décrivent (gate CI : exit 1)
graph-query orphans --type code        # fichiers sans aucune arête
```

| Commande | Répond à |
|---|---|
| `blast-radius <path>` | « qu'est-ce qui casse si je touche ce fichier » — imports entrants transitifs (`--depth`, `--edges` pour ajuster), plus les docs affectés |
| `hubs` | « où est le centre de gravité » — nœuds top par arêtes entrée+sortie (`--top N`) |
| `stale-docs` | « quels docs sont en retard sur le code » — compare les dernières dates de commit (une passe de `git log` ; fallback mtime), `--check` pour la CI |
| `orphans` | « qu'est-ce qui n'est connecté à rien » — nœuds de degré 0, filtrables par catégorie |

Chaque commande accepte `--json` pour une sortie lisible par machine — dirigez-la
vers `jq` ou donnez-la à un agent.

</details>

## Limitations connues

L'analyse statique a des frontières naturelles — le graphe est une carte
référentielle, pas sémantique :

- Les imports dynamiques ne sont résolus que pour les noms de module littéraux /
  fixés par des constantes de niveau supérieur (f-strings, recherches dans un dict,
  rebinding conditionnel sont ignorés).
- `eval` / `exec` et la DI par chaîne sont invisibles. Les points d'entrée
  `[project.scripts]` / `[project.gui-scripts]` de `pyproject.toml` sont lus, mais
  seulement pour exempter ces modules du marquage code mort — ils ne créent pas
  d'arêtes.
- Le templating Markdown (`{{ ref }}`, shortcodes Jekyll/Hugo) n'est pas analysé.
- Les liens se résolvent vers des fichiers entiers — les ancres de section
  (`file.md#part`) pointent vers le nœud du fichier.
- Les arêtes code→code sont pour l'instant uniquement Python (les couches
  markdown/docs sont indépendantes du langage).
- Un dépôt par graphe ; les liens symboliques sont traités comme des chemins
  physiques.

## Licence

[MIT](../LICENSE) © Yuriy Totyshev
