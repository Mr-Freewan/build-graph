<p align="center">
  <img src="../docs/media/banner.jpg" alt="build-graph" width="840">
</p>

<p align="center">
  <b>Deutsch</b> |
  <a href="../README.md">English</a> |
  <a href="README.es.md">Español</a> |
  <a href="README.fr.md">Français</a> |
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
  <a href="#für-ki-agenten-entwickelt"><img src="https://img.shields.io/badge/LLM--Agent-friendly-blueviolet" alt="LLM-Agent friendly"></a>
  <a href="../CONTRIBUTING.md"><img src="https://img.shields.io/badge/PRs-welcome-brightgreen" alt="PRs Welcome"></a>
</p>

<p align="center">
  <a href="https://mr-freewan.github.io/build-graph/"><img src="https://img.shields.io/badge/demo-online-blueviolet?style=for-the-badge&logo=googlechrome&logoColor=white" alt="Live demo"></a>
  <a href="https://codespaces.new/Mr-Freewan/build-graph"><img src="https://github.com/codespaces/badge.svg" alt="Open in GitHub Codespaces"></a>
</p>

> **Architekturgedächtnis für Refactorings.** Überblick über den
> Auswirkungsradius von Änderungen in Code, Dokumentation und Git — auf einer
> interaktiven Karte, die sowohl Sie als auch Ihr KI-Agent lesen. Ein Satz
> leichtgewichtiger Werkzeuge und eine einfache, aber sehr funktionale UI als
> eigenständige HTML-Datei, die sich „so wie sie ist“ weitergeben lässt.
> Leichtgewichtig und privat.

`build-graph` zeichnet einen **interaktiven Graphen in einer einzigen
HTML-Datei**, der fünf Ebenen verbindet, die kein anderes Werkzeug vereint:

- **Code → Code** — Python-Importe (AST-basiert, `TYPE_CHECKING`-bewusst)
- **Code ↔ Dokumentation** — welche Markdown-Dateien welche Quelldateien erwähnen
- **Git-Drift** — Overlay für added / modified / renamed / deleted plus
  Geisterknoten für Dateien, die es nicht mehr gibt
- **Heatmap der Dateiänderungen** — spürt die heißesten Änderungs-Brennpunkte
  samt potenzieller Fehlerquellen auf und hilft, sie zu entschärfen
- **Testabdeckungs-Karte** — liest die `coverage.xml` des Projekts und zeigt die
  Testabdeckung auf einen Blick, hebt die am wenigsten abgedeckten Dateien hervor

…und exportiert dieselbe Karte als **kompaktes, tokensparsames JSON**, das für
den Kontext eines LLM-Agenten gedacht ist.

Und das alles mit **null Abhängigkeiten**: reine Python-Standardbibliothek,
`pip install` zieht nichts Zusätzliches nach. Der einzige Fremdcode ist D3.js im
Browser, per CDN mit SRI-Pinning eingebunden oder mit `--no-cdn` vollständig
eingebettet für völlige Autonomie.

![Kräfte-Layout pendelt sich auf einem echten Projekt ein — 1070 Knoten / 6279 Kanten, dunkles Theme](../docs/media/hero.gif)

**[▶ Live-Demo](https://mr-freewan.github.io/build-graph/)** — der Graph genau
dieses Repositorys (Dogfood), mit einem synthetischen `--mock-git`-Overlay, damit
auch der Git- und der Coverage-Modus anklickbar sind.
**[📖 UI-Leitfaden](guide.de.md)** — eine kompakte Schritt-für-Schritt-Beschreibung
der Kernfunktionen.

## Installation

```bash
pip install graph-build        # oder: uv tool install graph-build
```

Direkt von GitHub installieren:

```bash
pip install git+https://github.com/Mr-Freewan/build-graph.git

# oder aus einem Klon:
git clone https://github.com/Mr-Freewan/build-graph.git
pip install ./build-graph
```

> Die PyPI-Distribution heißt `graph-build` (der direkte Name ist vergeben); die
> Namen der installierten Befehle bleiben gleich: `build-graph`,
> `find-related-docs`, `verify-doc-links`.

## Schnellstart

```bash
cd your-project
build-graph                    # Autodiscovery, keine Konfiguration nötig → docs/graph.html
build-graph --compact          # + docs/graph-compact.json für KI-Agenten
build-graph --init             # optional: die erkannte Struktur in graph.toml festschreiben
```

Zwei Begleit-Tools — `find-related-docs` (umgekehrte Suche: Code → Docs) und
`verify-doc-links` (Prüfung auf tote Links für CI) — kommen im selben Paket; siehe
[CLI-Werkzeuge](#cli-werkzeuge).

## Warum nicht andere Tools?

- **pydeps / Import Linter** — nur Importe; keine Dokumentationsebene, kein
  Git-Drift.
- **lychee & Co.** — prüfen tote URLs; keine Karte, keine Code-Ebene.
- **Obsidian-Graphansicht** — nur Notizen; sieht Ihren Code nicht.
- **Repomix / Gitingest** — packen den *Text* des Repositorys für LLMs;
  build-graph liefert die *Struktur*: ~2 % der Tokens, die der Rohtext kosten
  würde (siehe [die Zahlen](#was-es-an-kontext-kostet)).
- **Graphify / Understand-Anything** — Knowledge-Graph-Tools, die schwerere
  Abhängigkeits-Stacks nachziehen und für die Analyse auf ein
  nicht-deterministisches LLM setzen; build-graph ist deterministisch und
  abhängigkeitsfrei und ergänzt die Git- und Doc-Sync-Ebenen, die keinem von
  beiden zur Verfügung stehen.

## Für KI-Agenten entwickelt

`--compact` schreibt einen selbstdokumentierenden JSON-Snapshot (eingebettete
Legende, indizierte Knoten, dreibuchstabige Typcodes), den Agenten nutzen für:

1. **Auswirkungsradius** — eingehende Importe der Datei, die Sie ändern wollen,
   ganz ohne grep.
2. **Dokumentations-Routing** — welches ADR / welches Referenzdokument *vor* der
   Bearbeitung einer Datei zu lesen ist.
3. **Dreischichtiger Doc-Sync** — der Graph zeigt (1) was dokumentiert ist,
   (2) was dokumentiert sein sollte, es aber nicht ist, und (3) was dokumentiert
   ist, aber nicht mehr existiert (Geisterknoten = Veraltungs-Detektor).

Fügen Sie `build-graph --compact` einem pre-commit-Hook oder einem CI-Schritt
hinzu, damit die Karte für jede Agenten-Sitzung aktuell bleibt.

### Das kompakte Format

`--compact` schreibt `graph-compact.json` (Schema v2): Knoten als indiziertes
Array, Kanten als Zeilen `[Quell-Index, Ziel-Index, Typ, [Zeilennummern]]`,
dreibuchstabige Codes für jede Kategorie und jeden Kantentyp. Der Schlüssel
`legend` bettet die vollständige Dekodierungstabelle ein — ein Agent braucht kein
externes Schema, die Datei erklärt sich selbst:

```jsonc
{
  "v": "2.0",
  "legend": { "...": "was jedes Feld und jeder Code unten bedeutet" },
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

`p` — Pfad, `t` — Kategorie, `d` — Grad, `s` — Git-Status (entfällt, wenn
sauber). Kantentypen: `c2c` Importe, `c2d` Doc-Erwähnungen, `d2d` Doc-Links,
`dcs` Docstring-Referenzen, `typ` nur `TYPE_CHECKING`, `ren` Git-Umbenennungen.
Gelöschte, aber noch erwähnte Dateien fahren als Geisterknoten mit (`"G": 1`).

### Was es an Kontext kostet

Echte Zahlen aus einem Produktions-Repository — 1.070 zugeordnete Dateien, 6.279
Kanten (Tokens ≈ Bytes / 4, die übliche grobe Schätzung):

| Was Sie in den Kontext legen         |  Größe | ≈ Tokens   |
|--------------------------------------|-------:|-----------:|
| Die zugeordneten Dateien selbst      |  15 MB | ~3.700.000 |
| `--json` (ausführlicher Snapshot)    | 1,6 MB |   ~410.000 |
| **`--compact`**                      | **0,33 MB** | **~80.000** |

Die gesamte Architektur — jeder Import, jede Doc-Erwähnung, jede veraltete
Referenz — landet in ~2 % dessen, was der Rohtext kosten würde, und passt mit
Spielraum zum Arbeiten in eine einzige Sitzung mit 200-k-Kontext. Ohne die Karte
entdeckt ein Agent diese Struktur jede Sitzung neu: Dutzende spekulative greps
und Datei-Lesevorgänge, die vergleichbar viele Tokens verbrennen — *pro Frage*,
nicht einmalig. Bei kleinen Projekten ist die Karte fast gratis — der kompakte
Snapshot genau dieses Repositorys ist 4 KB ≈ ~1.000 Tokens groß.

<details>
<summary>Vertrauen Sie diesen Zahlen nicht blind — messen Sie Ihr eigenes Repository</summary>

```bash
$ build-graph --root . --bench

Context cost on this repo (tokens ~= bytes / 4):

  What you put in context            Size      ~Tokens  vs corpus
  raw corpus (1070 files)         14.3 MB    3,757,913     100.0%
  --json export (schema v1)        1.5 MB      397,419      10.6%
  --compact export (schema v2)   311.4 KB       79,729      2.1%
```

`--bench` misst nur — es schreibt keine Dateien.

</details>

### Ein Prompt für den Anfang

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

**Mehr Vorlagen:** [Prompts für KI-Agenten](agent-prompts.de.md) — fertige
Prompts für Auswirkungsradius, dreischichtigen Doc-Sync, Geister-Erkennung und
die Jagd auf toten Code.

## Der interaktive Graph

- **Canvas-Renderer** — flüssig bei 1000+ Knoten / 6000+ Kanten (vorgewärmtes
  Layout, Viewport-Culling, Label-LOD).
- **6 Kantentypen** — doc→doc, code→doc, code→code, nur-Typ (`TYPE_CHECKING`),
  Docstring-Erwähnungen, Git-Umbenennungen.
- **Git-Overlay** — Statusfarben + Geisterknoten + Umbenennungskanten;
  `--mock-git` für eine synthetische Demo.
- **Graph-Diff** — `--diff-base REF` vergleicht den Arbeitsbaum mit einem
  Git-Ref: Dateistatus speist das Git-Overlay, neue Abhängigkeitskanten
  erscheinen grün, entfernte rot (gestrichelt), mit Zählern in der Legende. Mit
  `--diff-head REF` vergleichen Sie stattdessen zwei bestimmte Refs.
- **Heat-Overlay** — Knotenfarbe nach Git-Commit-Häufigkeit (Verlauf
  blau→rot), standardmäßig die gesamte Historie oder die letzten N Tage mit
  `--heat-days N`. Ein min-edits-Schieberegler in der Legende blendet alles aus,
  was kälter als der gewählte Schwellenwert ist — die Kanten folgen. Schließt
  sich mit dem Git-Overlay gegenseitig aus (beide färben Knoten um, also ist nur
  eines aktiv); anders als der Git-Modus ist es additiv: die Node-types-Ebene
  bleibt darunter sichtbar und nutzbar.
- **Coverage-Overlay** — Knotenfarbe nach Testzeilen-Abdeckung (Verlauf
  grün→rot — hier geht es um das Finden schlecht abgedeckter Dateien, daher liest
  es sich umgekehrt zu Heat) aus einer Cobertura-`coverage.xml` (`--coverage PATH`,
  z. B. `pytest --cov=your_pkg --cov-report=xml`). Ein max-coverage-Schieberegler
  blendet alles aus, was *mehr* als die gewählte Obergrenze abgedeckt ist, und
  isoliert die am schlechtesten abgedeckten Dateien, je weiter Sie ihn senken;
  beim Einschalten werden zudem in der Legende alle Node types außer Code
  automatisch ausgeblendet (mit einem Klick wieder da). Schließt sich ebenfalls
  mit Git und Heat aus. Aus — und die Schaltfläche verborgen —, wenn kein Bericht
  angegeben ist.
- **Knoten-Tooltip** — fahren Sie über einen beliebigen Knoten, um Name und Pfad
  zu sehen; im Heat- oder Coverage-Modus zusätzlich die Anzahl der Änderungen
  bzw. den Abdeckungs-Prozentsatz hinter der Farbe. Kanten-Tooltips schalten sich
  ab, solange einer dieser Modi aktiv ist.
- **Analysehilfen** — Kandidaten für toten Code, Import-Zyklus-Detektor
  (Tarjan-SCC über Laufzeit-Importe; `TYPE_CHECKING`-Kanten zählen nicht),
  Waisen-Ring, kürzester Pfad zwischen zwei Knoten (Shift+Klick), Typ isolieren,
  Ausschluss nach Name. Die bloße Erwähnung einer gleichnamigen Datei in einem
  Doc (`config.py` mit Dutzenden Treffern, ohne Pfad) wird einem einzigen Knoten
  der Kategorie `ambiguous` zugeschrieben, statt auf alle Kandidaten zu streuen.
- **Teilen** — URL-kodierte Ansichten (Copy link), Mermaid-Export des
  fokussierten Teilgraphen, vollständiger/kompakter JSON-Export.
- **Komfort** — 10 UI-Sprachen, dunkles/helles Theme, tonal abgestimmte
  pastellene/gesättigte Paletten, verschiebbare Glaspaneele, IDE-Deep-Links
  (VS Code / Cursor / PyCharm), eingebautes FAQ (`?`).

Alles landet in **einer eigenständigen HTML-Datei** — hängen Sie sie an einen PR,
schicken Sie sie im Chat, öffnen Sie sie offline.

## Konfiguration (optional)

Autodiscovery klassifiziert jede versionierte Datei nach Art (Code /
Dokumentation / Konfiguration / Locale) × Speicherort, erkennt Ihr Paket und Ihr
Docs-Layout und erzeugt deterministische Farben. Eine `graph.toml` ist nur ein
Override:

```bash
build-graph --init           # graph.toml erzeugen, die aktuelle Struktur festschreiben
build-graph --init --diff    # Drift melden (neue Ordner, veraltete Pins), nichts ändern
build-graph --init --merge   # Abdeckung neuer Ordner ergänzen, Ihre Änderungen behalten
```

Das kommentierte Format siehe in [`graph.example.toml`](../graph.example.toml)
(`[docs]`-Kategorien, `[[code]]`-Verzeichnisse, `[[rules]]`, `[scan]`-Ausschlüsse,
`[dead_code]`-Ausnahmen, Farb-Pins).

Zwei optionale Klartext-Begleiter, beide werden im Projektstamm gesucht:

- `known-brokens.txt` — Whitelist für Falschmeldungen von `verify-doc-links`
  (ein exakter Pfad pro Zeile).
- `exclude-dirs.txt` — Skip-Liste von Verzeichnisnamen, nur genutzt, wenn Git
  nicht verfügbar ist (mit Git ist `.gitignore` die Quelle der Wahrheit).

## CLI-Referenz (build-graph)

| Flag | Wirkung |
|---|---|
| `--root PATH` | zu scannender Projektstamm (Standard: cwd) |
| `--config PATH` | Ort der graph.toml (Standard: `<root>/graph.toml`) |
| `--output PATH` | HTML-Ausgabe (Standard: `docs/graph.html` oder `[output].path`) |
| `--scope full\|package` | ganzes Repo (Standard) oder nur Paket+Tests+Docs |
| `--json` / `--compact` | ausführliche / agentenorientierte JSON-Snapshots |
| `--docs-only` / `--no-tests` | die Knotenmenge beschneiden |
| `--no-cdn` | vollständig offline: D3.js inline einbetten (SHA-256-geprüft) und den externen Font-Link weglassen |
| `--mock-git` | synthetisches Git-Overlay für Demos/Tests |
| `--diff-base REF` | Ref-Diff-Build: Status + Kantenänderungen gegenüber einem Git-Ref (head = Arbeitsbaum, sofern nicht `--diff-head` gesetzt) |
| `--diff-head REF` | mit `--diff-base`: gegen diesen Ref statt gegen den Arbeitsbaum vergleichen |
| `--heat-days N` | das Heat-Overlay auf die letzten N Tage beschränken (Standard: gesamte Historie) |
| `--coverage PATH` | das Coverage-Overlay aus einer Cobertura-`coverage.xml` aktivieren |
| `--init [--diff\|--merge\|--force]` | Konfigurations-Lebenszyklus (siehe oben) |

## CLI-Werkzeuge

`find-related-docs` und `verify-doc-links` nutzen denselben Referenz-Scanner, aus
dem der Graph gebaut wird — was die Karte als Kante Code↔Docs zeichnet, ist genau
das, was sie nachschlagen und prüfen. `graph-query` beantwortet Fragen zu einem
bereits erstellten Snapshot.

### find-related-docs

Umgekehrte Suche: welche Docs eine bestimmte Code-Datei erwähnen. Führen Sie es
vor dem Bearbeiten einer Datei aus, um zu wissen, welche Seiten danach zu
aktualisieren sind, oder binden Sie `--git-added` in einen pre-commit-Hook ein,
damit undokumentierte Änderungen markiert werden, bevor sie einfließen.

<details>
<summary>Flags &amp; Beispiele</summary>

```bash
find-related-docs src/mypkg/core/access.py   # eine Datei (bloßer Dateiname geht auch)
find-related-docs --git-added -v             # pre-commit: gestagete Dateien, mit Doc-Zeilennummern
find-related-docs --git-modified             # Arbeitsbaum: gestagete + ungestagete Änderungen
```

| Flag | Wirkung |
|---|---|
| `path` | zu suchende Datei oder Verzeichnis (ein bloßer Dateiname wird projektweit gesucht) |
| `--docs-dir PATH` | Dokumentationsverzeichnis (Standard: `docs`) |
| `--exclude DIRNAME` | einen Ordnernamen irgendwo unter dem Docs-Verzeichnis überspringen (wiederholbar) |
| `--git-added` | alle gestageten Dateien prüfen; warnt auch vor gelöschten Dateien, die noch in Docs erwähnt sind |
| `--git-modified` | alle geänderten Dateien prüfen (gestaget + ungestaget) |
| `-v` / `--verbose` | `docs/<file>.md:<line>` für jede Erwähnung ausgeben |

</details>

### verify-doc-links

Prüft, dass jede Dateireferenz in Ihren `.md`-Dateien auf eine echte Datei zeigt.
Die Exit-Codes machen es zu einem CI-Gate zum Einstecken:

<details>
<summary>Flags &amp; Beispiele</summary>

| Exit | Bedeutung |
|---|---|
| `0` | alle Referenzen gültig |
| `1` | defekte Referenzen gefunden |
| `2` | Zielpfad ungültig (nicht gefunden oder keine `.md`-Datei) |

```bash
verify-doc-links                     # ganzes docs/ gegen den Projektstamm
verify-doc-links docs/reference -v   # ein Teilbaum, mit den betreffenden Zeilen
```

```yaml
# CI-Schritt (GitHub Actions)
- run: pip install graph-build
- run: verify-doc-links --root .
```

| Flag | Wirkung |
|---|---|
| `path` | zu prüfende `.md`-Datei oder Verzeichnis (Standard: `docs`) |
| `--root PATH` | Projektstamm, gegen den die Referenzen aufgelöst werden (Standard: cwd) |
| `--known-brokens PATH` | Whitelist-Datei (Standard: `<root>/known-brokens.txt`) |
| `-v` / `--verbose` | die betreffenden Zeilen zeigen |

Neben `known-brokens.txt` lassen sich Falschmeldungen inline mit
HTML-Kommentaren stummschalten (im gerenderten Markdown unsichtbar):
`<!-- broken-link-ok -->` in derselben Zeile, `<!-- broken-links-ok-start -->` /
`<!-- broken-links-ok-end -->` um einen Block oder `<!-- ignore-ref: path/to/file.py -->`
irgendwo in der Datei.

</details>

### graph-query

Stellen Sie dem Graphen Fragen, ohne einen Browser zu öffnen. Arbeitet mit dem
JSON, das `--json` oder `--compact` schreibt (automatisch erkannt; Standard:
`docs/graph-compact.json`):

<details>
<summary>Flags &amp; Beispiele</summary>

```bash
graph-query blast-radius app/core.py   # transitive Importeure + jedes Doc, das sie erwähnt
graph-query hubs --top 15              # meistverbundene Dateien, Aufschlüsselung in/out
graph-query stale-docs --check         # Docs, die älter als der beschriebene Code sind (CI-Gate: exit 1)
graph-query orphans --type code        # Dateien ganz ohne Kanten
```

| Befehl | Beantwortet |
|---|---|
| `blast-radius <path>` | „was bricht, wenn ich diese Datei anfasse“ — transitive eingehende Importe (`--depth`, `--edges` zum Feinjustieren), plus betroffene Docs |
| `hubs` | „wo ist der Schwerpunkt“ — Top-Knoten nach ein+aus-Kanten (`--top N`) |
| `stale-docs` | „welche Docs hinken dem Code hinterher“ — vergleicht die letzten Commit-Zeiten (ein `git log`-Durchlauf; mtime-Fallback), `--check` für CI |
| `orphans` | „was mit nichts verbunden ist“ — Knoten mit Grad 0, nach Kategorie filterbar |

Jeder Befehl akzeptiert `--json` für maschinenlesbare Ausgabe — leiten Sie sie an
`jq` weiter oder geben Sie sie einem Agenten.

</details>

## Bekannte Einschränkungen

Statische Analyse hat natürliche Grenzen — der Graph ist eine referenzielle
Karte, keine semantische:

- Dynamische Importe werden nur für literale / durch Top-Level-Konstanten
  gesetzte Modulnamen aufgelöst (f-Strings, Dict-Lookups, bedingtes Rebinding
  werden übersprungen).
- `eval` / `exec` und DI-per-String sind unsichtbar. `[project.scripts]` /
  `[project.gui-scripts]`-Einstiegspunkte in `pyproject.toml` werden gelesen,
  aber nur, um diese Module von der Tot-Code-Markierung auszunehmen — Kanten
  erzeugen sie nicht.
- Markdown-Templating (`{{ ref }}`, Jekyll/Hugo-Shortcodes) wird nicht geparst.
- Links lösen sich zu ganzen Dateien auf — Abschnitts-Anker (`file.md#part`)
  bilden auf den Datei-Knoten ab.
- Code→Code-Kanten sind vorerst nur Python (die Markdown-/Doc-Ebenen sind
  sprachunabhängig).
- Ein Repo pro Graph; Symlinks werden als physische Pfade behandelt.

## Lizenz

[MIT](../LICENSE) © Yuriy Totyshev
