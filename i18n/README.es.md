<p align="center">
  <img src="../docs/media/banner.jpg" alt="build-graph" width="840">
</p>

<p align="center">
  <a href="README.de.md">Deutsch</a> |
  <a href="../README.md">English</a> |
  <b>Español</b> |
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
  <a href="#diseñado-para-agentes-de-ia"><img src="https://img.shields.io/badge/LLM--Agent-friendly-blueviolet" alt="LLM-Agent friendly"></a>
  <a href="../CONTRIBUTING.md"><img src="https://img.shields.io/badge/PRs-welcome-brightgreen" alt="PRs Welcome"></a>
</p>

<p align="center">
  <a href="https://mr-freewan.github.io/build-graph/"><img src="https://img.shields.io/badge/demo-online-blueviolet?style=for-the-badge&logo=googlechrome&logoColor=white" alt="Live demo"></a>
  <a href="https://codespaces.new/Mr-Freewan/build-graph"><img src="https://github.com/codespaces/badge.svg" alt="Open in GitHub Codespaces"></a>
</p>

> **Memoria arquitectónica para tus refactorizaciones.** Una vista del radio de
> impacto de tus cambios en código, documentación y git — en un único mapa
> interactivo que leéis tanto tú como tu agente de IA. Un conjunto de utilidades
> ligeras y una interfaz sencilla pero muy funcional en forma de documento HTML
> autónomo que se puede compartir «tal cual». Ligereza y privacidad.

`build-graph` dibuja un **grafo interactivo en un solo archivo HTML** que conecta
cinco capas que ninguna otra herramienta combina:

- **código → código** — importaciones de Python (basadas en AST, con conciencia
  de `TYPE_CHECKING`)
- **código ↔ documentación** — qué archivos markdown mencionan qué fuentes
- **desviación de git** — capa de added / modified / renamed / deleted más nodos
  fantasma para archivos que ya no existen
- **mapa de calor de cambios** — permite localizar y atenuar los puntos calientes
  de cambios, junto con las probables fuentes de errores
- **mapa de cobertura de tests** — lee el `coverage.xml` del proyecto y muestra la
  cobertura de un vistazo, resaltando los archivos menos cubiertos

…y exporta el mismo mapa como un **JSON compacto y eficiente en tokens**, pensado
para el contexto de un agente LLM.

Y todo ello con **cero dependencias**: pura biblioteca estándar de Python,
`pip install` no arrastra nada más. El único código de terceros es D3.js en el
navegador, cargado desde CDN con fijación SRI o totalmente incrustado con
`--no-cdn` para una autonomía completa.

![El layout de fuerzas se estabiliza en un proyecto real — 1070 nodos / 6279 aristas, tema oscuro](../docs/media/hero.gif)

**[▶ Demo en vivo](https://mr-freewan.github.io/build-graph/)** — el grafo de este
mismo repositorio (dogfood), con una capa sintética `--mock-git` para que los
modos Git y de cobertura también sean interactivos.
**[📖 Guía de la interfaz](guide.es.md)** — un recorrido conciso, paso a paso, por
las funciones principales.

## Instalación

```bash
pip install graph-build        # o: uv tool install graph-build
```

Instala directamente desde GitHub:

```bash
pip install git+https://github.com/Mr-Freewan/build-graph.git

# o desde un clon:
git clone https://github.com/Mr-Freewan/build-graph.git
pip install ./build-graph
```

> La distribución en PyPI se llama `graph-build` (el nombre directo está tomado);
> los nombres de los comandos instalados no cambian: `build-graph`,
> `find-related-docs`, `verify-doc-links`.

## Inicio rápido

```bash
cd your-project
build-graph                    # autodescubrimiento, sin configuración → docs/graph.html
build-graph --compact          # + docs/graph-compact.json para agentes de IA
build-graph --init             # opcional: fijar la estructura detectada en graph.toml
```

Dos herramientas complementarias — `find-related-docs` (búsqueda inversa: código →
docs) y `verify-doc-links` (verificación de enlaces rotos para CI) — vienen en el
mismo paquete; consulta [Herramientas CLI](#herramientas-cli).

## ¿Por qué no otras herramientas?

- **pydeps / Import Linter** — solo importaciones; sin capa de documentación, sin
  desviación de git.
- **lychee y similares** — comprueban URLs muertas; sin mapa, sin capa de código.
- **Vista de grafo de Obsidian** — solo notas; no ve tu código.
- **Repomix / Gitingest** — empaquetan el *texto* del repositorio para LLMs;
  build-graph aporta la *estructura*: ~2 % de los tokens que costaría el texto
  bruto (ver [las cifras](#cuánto-cuesta-en-contexto)).
- **Graphify / Understand-Anything** — herramientas de grafo de conocimiento que
  arrastran pilas de dependencias más pesadas y se apoyan en un LLM no
  determinista para el análisis; build-graph es determinista y sin dependencias,
  y añade las capas de git y de doc-sync que ninguna de las dos tiene.

## Diseñado para agentes de IA

`--compact` escribe una instantánea JSON autodocumentada (leyenda incrustada,
nodos indexados, códigos de tipo de tres letras) que los agentes usan para:

1. **Radio de impacto** — las importaciones entrantes del archivo que vas a
   cambiar, sin grep.
2. **Enrutamiento de documentación** — qué ADR / documento de referencia leer
   *antes* de editar un archivo.
3. **Doc-sync de tres capas** — el grafo muestra (1) qué está documentado, (2) qué
   debería estarlo pero no lo está, y (3) qué está documentado pero ya no existe
   (nodos fantasma = detector de obsolescencia).

Añade `build-graph --compact` a un hook de pre-commit o a un paso de CI para que
el mapa siga fresco en cada sesión del agente.

### El formato compacto

`--compact` escribe `graph-compact.json` (esquema v2): los nodos como un array
indexado, las aristas como filas `[índice_origen, índice_destino, tipo,
[números_de_línea]]`, códigos de tres letras para cada categoría y tipo de arista.
La clave `legend` incrusta la tabla de decodificación completa — un agente no
necesita esquema externo, el archivo se explica solo:

```jsonc
{
  "v": "2.0",
  "legend": { "...": "qué significa cada campo y código a continuación" },
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

`p` — ruta, `t` — categoría, `d` — grado, `s` — estado de git (se omite cuando
está limpio). Tipos de arista: `c2c` importaciones, `c2d` menciones en docs, `d2d`
enlaces entre docs, `dcs` referencias de docstring, `typ` solo `TYPE_CHECKING`,
`ren` renombrados de git. Los archivos eliminados pero aún mencionados viajan como
nodos fantasma (`"G": 1`).

### Cuánto cuesta en contexto

Cifras reales de un repositorio en producción — 1070 archivos mapeados, 6279
aristas (tokens ≈ bytes / 4, la estimación aproximada habitual):

| Lo que pones en el contexto          | Tamaño | ≈ Tokens   |
|--------------------------------------|-------:|-----------:|
| Los propios archivos mapeados        |  15 MB | ~3 700 000 |
| `--json` (instantánea detallada)     | 1,6 MB |   ~410 000 |
| **`--compact`**                      | **0,33 MB** | **~80 000** |

Toda la arquitectura — cada importación, cada mención en docs, cada referencia
obsoleta — cabe en ~2 % de lo que costaría el texto bruto, y entra en una sola
sesión de contexto de 200 k con margen para trabajar. Sin el mapa, un agente
redescubre esta estructura en cada sesión: docenas de greps especulativos y
lecturas de archivos que queman una cantidad comparable de tokens *por pregunta*,
no una sola vez. En proyectos pequeños el mapa es casi gratis — la instantánea
compacta de este mismo repositorio ocupa 4 KB ≈ ~1000 tokens.

<details>
<summary>No te fíes de estas cifras — mide tu propio repositorio</summary>

```bash
$ build-graph --root . --bench

Context cost on this repo (tokens ~= bytes / 4):

  What you put in context            Size      ~Tokens  vs corpus
  raw corpus (1070 files)         14.3 MB    3,757,913     100.0%
  --json export (schema v1)        1.5 MB      397,419      10.6%
  --compact export (schema v2)   311.4 KB       79,729      2.1%
```

`--bench` solo mide — no escribe ningún archivo.

</details>

### Un prompt para empezar

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

**Más recetas:** [Prompts para agentes de IA](agent-prompts.es.md) — prompts
listos para radio de impacto, doc-sync de tres capas, detección de fantasmas y
caza de código muerto.

## El grafo interactivo

- **Renderizador Canvas** — fluido con más de 1000 nodos / 6000 aristas (layout
  precalentado, descarte por viewport, LOD de etiquetas).
- **6 tipos de arista** — doc→doc, code→doc, code→code, solo-tipo
  (`TYPE_CHECKING`), menciones de docstring, renombrados de git.
- **Capa Git** — colores de estado + nodos fantasma + aristas de renombrado;
  `--mock-git` para una demo sintética.
- **Diff del grafo** — `--diff-base REF` compara el árbol de trabajo con un ref de
  git: los estados de archivo alimentan la capa Git, las nuevas aristas de
  dependencia salen en verde y las eliminadas en rojo (a trazos), con contadores
  en la leyenda. Añade `--diff-head REF` para comparar dos refs concretos en su
  lugar.
- **Capa Heat** — color de nodo por frecuencia de commits de git (gradiente
  azul→rojo), toda la historia por defecto o los últimos N días con
  `--heat-days N`. Un deslizador min-edits en la leyenda oculta todo lo más frío
  que el umbral elegido — las aristas siguen. Se excluye mutuamente con la capa
  Git (ambas recolorean nodos, así que solo una está activa a la vez); a
  diferencia del modo Git, es aditiva: la capa Node types sigue visible y usable
  debajo.
- **Capa Coverage** — color de nodo por cobertura de líneas de test (gradiente
  verde→rojo — esta va de encontrar archivos mal cubiertos, así que se lee al
  revés que Heat) desde un `coverage.xml` de Cobertura (`--coverage PATH`, p. ej.
  `pytest --cov=your_pkg --cov-report=xml`). Un deslizador max-coverage oculta todo
  lo cubierto *por encima* del techo elegido, aislando los archivos peor cubiertos
  a medida que lo bajas; al activarla también se ocultan automáticamente en la
  leyenda todos los Node types salvo el código (vuelven con un clic). También se
  excluye mutuamente con Git y Heat. Apagada — y su botón oculto — cuando no se da
  ningún informe.
- **Tooltip de nodo** — pasa el ratón sobre cualquier nodo para ver su nombre y
  ruta; en modo Heat o Coverage, además el número de cambios o el porcentaje de
  cobertura tras el color. Los tooltips de arista se desactivan mientras cualquiera
  de esos modos está activo.
- **Ayudas de análisis** — candidatos a código muerto, detector de ciclos de
  importación (Tarjan SCC sobre importaciones en tiempo de ejecución; las aristas
  `TYPE_CHECKING` no cuentan), anillo de huérfanos, camino más corto entre dos
  nodos (Shift+clic), aislar un tipo, excluir por nombre. La mera mención en un doc
  de un archivo homónimo (`config.py` con decenas de coincidencias, sin ruta) se
  atribuye a un único nodo de categoría `ambiguous`, en vez de dispersarse a todos
  los candidatos.
- **Compartir** — vistas codificadas en la URL (Copy link), exportación a Mermaid
  del subgrafo enfocado, exportación de JSON completo/compacto.
- **Comodidad** — 10 idiomas de interfaz, temas oscuro/claro, paletas
  pastel/saturada afinadas por tono, paneles de vidrio arrastrables, enlaces
  profundos a IDE (VS Code / Cursor / PyCharm), FAQ integrado (`?`).

Todo cabe en **un único archivo HTML autónomo** — adjúntalo a un PR, envíalo por
chat, ábrelo sin conexión.

## Configuración (opcional)

El autodescubrimiento clasifica cada archivo versionado por tipo (código /
documentación / configuración / locale) × ubicación, detecta tu paquete y la
disposición de tus docs, y genera colores deterministas. Un `graph.toml` es solo
un override:

```bash
build-graph --init           # generar graph.toml fijando la estructura actual
build-graph --init --diff    # informar de la desviación (carpetas nuevas, pines obsoletos), sin cambiar nada
build-graph --init --merge   # añadir cobertura de carpetas nuevas, conservando tus ediciones
```

Consulta el formato anotado en [`graph.example.toml`](../graph.example.toml)
(categorías `[docs]`, directorios `[[code]]`, `[[rules]]`, exclusiones `[scan]`,
exenciones `[dead_code]`, pines de color).

Dos complementos opcionales de texto plano, ambos buscados en la raíz del
proyecto:

- `known-brokens.txt` — lista blanca para los falsos positivos de
  `verify-doc-links` (una ruta exacta por línea).
- `exclude-dirs.txt` — lista de nombres de directorio a omitir, usada solo cuando
  git no está disponible (con git, `.gitignore` es la fuente de verdad).

## Referencia de CLI (build-graph)

| Flag | Efecto |
|---|---|
| `--root PATH` | raíz del proyecto a escanear (por defecto: cwd) |
| `--config PATH` | ubicación de graph.toml (por defecto: `<root>/graph.toml`) |
| `--output PATH` | salida HTML (por defecto: `docs/graph.html` o `[output].path`) |
| `--scope full\|package` | todo el repo (por defecto) o solo paquete+tests+docs |
| `--json` / `--compact` | instantáneas JSON detallada / orientada al agente |
| `--docs-only` / `--no-tests` | recortar el conjunto de nodos |
| `--no-cdn` | salida totalmente offline: incrustar D3.js inline (verificado con SHA-256) y quitar el enlace externo a la fuente |
| `--mock-git` | capa git sintética para demos/pruebas |
| `--diff-base REF` | build de ref-diff: estados + cambios de aristas frente a un ref de git (head = árbol de trabajo salvo que se fije `--diff-head`) |
| `--diff-head REF` | con `--diff-base`: comparar contra este ref en vez del árbol de trabajo |
| `--heat-days N` | restringir la capa Heat a los últimos N días (por defecto: toda la historia) |
| `--coverage PATH` | activar la capa Coverage desde un `coverage.xml` de Cobertura |
| `--init [--diff\|--merge\|--force]` | ciclo de vida de la configuración (ver arriba) |

## Herramientas CLI

`find-related-docs` y `verify-doc-links` usan el mismo escáner de referencias con
el que se construye el grafo — lo que el mapa dibuja como arista código↔docs es
exactamente lo que ellos buscan y verifican. `graph-query` responde preguntas
sobre una instantánea ya construida.

### find-related-docs

Búsqueda inversa: qué docs mencionan un archivo de código dado. Ejecútalo antes de
editar un archivo para saber qué páginas habrá que actualizar después, o conecta
`--git-added` a un hook de pre-commit para que los cambios sin documentar se
marquen antes de que entren.

<details>
<summary>Flags y ejemplos</summary>

```bash
find-related-docs src/mypkg/core/access.py   # un archivo (el nombre a secas también vale)
find-related-docs --git-added -v             # pre-commit: archivos en stage, con números de línea de los docs
find-related-docs --git-modified             # árbol de trabajo: cambios en stage + sin stage
```

| Flag | Efecto |
|---|---|
| `path` | archivo o directorio a buscar (un nombre a secas se busca en todo el proyecto) |
| `--docs-dir PATH` | directorio de documentación (por defecto: `docs`) |
| `--exclude DIRNAME` | omitir un nombre de carpeta en cualquier punto bajo el directorio de docs (repetible) |
| `--git-added` | comprobar todos los archivos en stage; también avisa de archivos eliminados aún mencionados en docs |
| `--git-modified` | comprobar todos los archivos modificados (en stage + sin stage) |
| `-v` / `--verbose` | imprimir `docs/<file>.md:<line>` por cada mención |

</details>

### verify-doc-links

Comprueba que cada referencia de archivo en tus `.md` apunta a un archivo real.
Los códigos de salida lo convierten en un gate de CI listo para usar:

<details>
<summary>Flags y ejemplos</summary>

| Salida | Significado |
|---|---|
| `0` | todas las referencias válidas |
| `1` | referencias rotas encontradas |
| `2` | ruta de destino inválida (no encontrada o no es un `.md`) |

```bash
verify-doc-links                     # todo docs/ contra la raíz del proyecto
verify-doc-links docs/reference -v   # un subárbol, con las líneas problemáticas
```

```yaml
# Paso de CI (GitHub Actions)
- run: pip install graph-build
- run: verify-doc-links --root .
```

| Flag | Efecto |
|---|---|
| `path` | `.md` o directorio a comprobar (por defecto: `docs`) |
| `--root PATH` | raíz del proyecto contra la que se resuelven las referencias (por defecto: cwd) |
| `--known-brokens PATH` | archivo de lista blanca (por defecto: `<root>/known-brokens.txt`) |
| `-v` / `--verbose` | mostrar las líneas problemáticas |

Además de `known-brokens.txt`, los falsos positivos se pueden silenciar en línea
con comentarios HTML (invisibles en el Markdown renderizado):
`<!-- broken-link-ok -->` en la misma línea, `<!-- broken-links-ok-start -->` /
`<!-- broken-links-ok-end -->` alrededor de un bloque, o
`<!-- ignore-ref: path/to/file.py -->` en cualquier parte del archivo.

</details>

### graph-query

Hazle preguntas al grafo sin abrir un navegador. Funciona sobre el JSON que
escribe `--json` o `--compact` (autodetectado; por defecto
`docs/graph-compact.json`):

<details>
<summary>Flags y ejemplos</summary>

```bash
graph-query blast-radius app/core.py   # importadores transitivos + cada doc que los menciona
graph-query hubs --top 15              # archivos más conectados, desglose in/out
graph-query stale-docs --check         # docs más viejos que el código que describen (gate de CI: exit 1)
graph-query orphans --type code        # archivos sin ninguna arista
```

| Comando | Responde |
|---|---|
| `blast-radius <path>` | «qué se rompe si toco este archivo» — importaciones entrantes transitivas (`--depth`, `--edges` para ajustar), más los docs afectados |
| `hubs` | «dónde está el centro de gravedad» — nodos top por aristas entrada+salida (`--top N`) |
| `stale-docs` | «qué docs van por detrás del código» — compara las últimas fechas de commit (una pasada de `git log`; fallback a mtime), `--check` para CI |
| `orphans` | «qué no está conectado a nada» — nodos de grado 0, filtrables por categoría |

Cada comando acepta `--json` para salida legible por máquina — canalízala a `jq`
o pásasela a un agente.

</details>

## Limitaciones conocidas

El análisis estático tiene fronteras naturales — el grafo es un mapa referencial,
no semántico:

- Las importaciones dinámicas se resuelven solo para nombres de módulo literales /
  fijados por constantes de nivel superior (f-strings, búsquedas en dict, rebinding
  condicional se omiten).
- `eval` / `exec` y la DI por cadena son invisibles. Los puntos de entrada
  `[project.scripts]` / `[project.gui-scripts]` de `pyproject.toml` se leen, pero
  solo para eximir esos módulos del marcado como código muerto — no crean aristas.
- El templating de Markdown (`{{ ref }}`, shortcodes de Jekyll/Hugo) no se
  analiza.
- Los enlaces se resuelven a archivos enteros — los anclajes de sección
  (`file.md#part`) mapean al nodo de archivo.
- Las aristas código→código son, por ahora, solo de Python (las capas de
  markdown/docs son independientes del lenguaje).
- Un repo por grafo; los symlinks se tratan como rutas físicas.

## Licencia

[MIT](../LICENSE) © Yuriy Totyshev
