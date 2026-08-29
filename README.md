<div align="center">

<img src="docs/assets/logo.svg" width="128" height="128" alt="DocFuse logo"/>

# DocFuse / CorpusOne

**Outil portable Windows d'assemblage de documents vers un corpus unique destiné à un LLM.**
*Portable Windows tool that fuses documents into a single corpus for an LLM.*

[![License: Apache-2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](./LICENSE)
[![Version](https://img.shields.io/badge/version-0.1.5_beta-orange.svg)](./CHANGELOG.md)
[![Python](https://img.shields.io/badge/python-3.11%20|%203.12%20|%203.13-blue.svg)](./pyproject.toml)
[![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20Linux%20%7C%20macOS-lightgrey.svg)](#-compatibilité--compatibility)
[![Tests](https://img.shields.io/badge/tests-471%20passed%20%7C%2039%20skipped-success.svg)](./tests)
[![Type check](https://img.shields.io/badge/mypy--strict-passing-success.svg)](./pyproject.toml)
[![Lint](https://img.shields.io/badge/ruff-passing-success.svg)](./pyproject.toml)
[![No network](https://img.shields.io/badge/network-none-success.svg)](./tests/test_acceptance.py)
[![No GPL/AGPL](https://img.shields.io/badge/license-GPL%2FAGPL%20free-success.svg)](./tests/test_acceptance.py)
[![i18n](https://img.shields.io/badge/i18n-FR%20%7C%20EN-blue.svg)](./src/docfuse/i18n/)

[🇫🇷 Français](#-français) · [🇬🇧 English](#-english)

</div>

---

> [!IMPORTANT]
> **Sécurité.** DocFuse lit et parse des fichiers dans des formats variés
> (PDF, DOCX, PPTX, etc.). Comme tout parser, ses extracteurs peuvent être
> exposés à des fichiers malformés voire malveillants. Ne lancez pas
> DocFuse sur des sources non fiables sans surveillance. Pour signaler une
> vulnérabilité : voir [SECURITY.md](./SECURITY.md).

---

## 🇫🇷 Français

### Pourquoi DocFuse ?

Donner un dossier entier à un LLM, c'est fastidieux : ouvrir chaque PDF/DOCX,
copier-coller le texte, perdre les tableaux et la structure. **DocFuse**
extrait automatiquement le texte de 13 formats bureautiques et le concatène
en un seul fichier **Markdown** (lisible par tous les LLMs) ou **PDF** (pour
archivage), avec une estimation du nombre de tokens par fichier et un
contrôle de plafond pour ne pas dépasser la fenêtre de contexte.

### Caractéristiques

- **Portable Windows** : un seul `CorpusOne.exe` autoportant, aucune DLL
  externe, aucune installation, aucun droit administrateur. Fonctionne depuis
  une clé USB ou un partage réseau.
- **Hors-ligne strict** : aucune connexion réseau, vérifié par test
  automatisé.
- **Multi-format** : PDF, DOCX, PPTX, XLSX, RTF, HTML, Markdown, CSV/TSV,
  ODT/ODS/ODP, XML/JSON/YAML/INI, EML, MHTML, et une soixantaine
  d'extensions de fichiers de développement (`.py`, `.js`/`.ts`, `.sh`,
  `.sql`, `.css`, `.java`, `.c`/`.cpp`, `.go`, `.rs`, etc.).
- **Compteur de contexte générique** : estimation tokens
  (`octets UTF-8 / 4`) + marge configurable (15 % par défaut).
- **Moteurs de comptage précis en option** : tokens réels de Mistral ou
  d'OpenAI (`--tokenizer-engine {mistral,openai}`), calculé localement,
  sans réseau.
- **Contrôle de plafond** : blocage si un fichier OU le total dépasse le
  plafond (128 000 tokens par défaut).
- **Détection d'images et de scans**, avec **OCR optionnel des PDF
  scannés** (Tesseract) : reconnaissance automatique si un moteur est
  disponible, jamais bloquant sinon. `CorpusOne.exe` n'embarque pas
  Tesseract (taille inchangée) ; une variante distincte, `CorpusOne-OCR.exe`,
  l'embarque pour un usage sans aucune installation.
- **Rapport d'exécution** : liste tous les fichiers (traités, ignorés,
  erreurs), exporté en Markdown et JSON.
- **GUI CustomTkinter + CLI argparse + glisser-déposer** (drag-and-drop).
- **i18n complet** : français (défaut) et anglais.
- **Licence Apache 2.0**, dépendances compatibles uniquement
  (MIT/BSD/Apache/ISC/MPL/Python) — pas de GPL/AGPL.

### Capture d'écran

<p align="center">
  <img src="docs/assets/screenshots/gui-tokenizer-mistral-result.png" width="640" alt="Fenêtre DocFuse après analyse : liste des fichiers avec tokens réels calculés par le moteur Mistral"/>
</p>

<p align="center"><sub>Analyse terminée avec le moteur de comptage précis (Mistral) — voir le <a href="docs/guide-utilisateur.md#4-le-compteur-de-contexte">guide utilisateur</a> pour le détail.</sub></p>

### Téléchargement (Windows)

La dernière préversion est **[`v0.1.5 beta`](https://github.com/Martossien/DocFuse/releases/tag/v0.1.5)**
([notes de version](./docs/releases/v0.1.5.md)).

| Fichier | Lien |
|---|---|
| **Archive portable** (`CorpusOne.exe`) | [Télécharger .zip](https://github.com/Martossien/DocFuse/releases/download/v0.1.5/CorpusOne-0.1.5-beta-windows-x64.zip) |
| **Empreinte SHA-256** | [Télécharger .sha256](https://github.com/Martossien/DocFuse/releases/download/v0.1.5/CorpusOne-0.1.5-beta-windows-x64.zip.sha256) |
| **Archive portable avec OCR** (`CorpusOne-OCR.exe`, Tesseract embarqué) | [Télécharger .zip](https://github.com/Martossien/DocFuse/releases/download/v0.1.5/CorpusOne-OCR-0.1.5-beta-windows-x64.zip) |
| **Empreinte SHA-256** (OCR) | [Télécharger .sha256](https://github.com/Martossien/DocFuse/releases/download/v0.1.5/CorpusOne-OCR-0.1.5-beta-windows-x64.zip.sha256) |

Installation :

1. Téléchargez l'archive `.zip` (et optionnellement son `.sha256`).
2. Extrayez **le seul** `CorpusOne.exe` dans un dossier de votre choix.
3. Double-cliquez sur `CorpusOne.exe`. Aucune connexion réseau, aucun
   droit administrateur.

> Le binaire n'est pas signé : Windows SmartScreen affichera un
> avertissement au premier lancement. Vérifiez l'empreinte SHA-256.

### Démarrage rapide

#### Utiliser l'exécutable portable

```bash
# Depuis PowerShell, dans le dossier contenant CorpusOne.exe :
.\CorpusOne.exe --input "D:\Mon dossier" --output ".\corpus.md" --format md --yes
```

Le corpus et les rapports (`corpus.md`, `corpus_rapport.md`,
`corpus_rapport.json`) sont créés dans `D:\Mon dossier\CorpusOne_output\`.

#### Utiliser Python (développement)

Pré-requis : **Python 3.11+**.

```bash
git clone https://github.com/Martossien/DocFuse.git
cd DocFuse
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
```

Lancer la GUI :

```bash
python -m docfuse
```

Lancer la CLI :

```bash
python -m docfuse --input "D:\Mon dossier" --output "corpus.md" --format md --yes
```

### Utilisation CLI

```text
docfuse [OPTIONS]

Options :
  -i, --input PATH          Dossier ou fichier à analyser (répétable)
  -o, --output PATH         Fichier de sortie (.md ou .pdf) ou dossier
  -f, --format {md,pdf}     Format de sortie (défaut : md)
  -c, --context INT         Plafond de contexte en tokens (défaut : 128000)
      --margin FLOAT        Marge sur l'estimation tokens (défaut : 0.15)
      --tokenizer-engine    Moteur de comptage : approx (défaut), mistral, openai
      --list-tokenizers     Affiche les moteurs de comptage disponibles
      --recursive           Parcourir les sous-dossiers
      --no-recursive        Ne pas parcourir les sous-dossiers
      --include-ext EXT     Restreindre aux extensions données (répétable)
      --exclude-glob GLOB   Exclure les fichiers matchant le glob (répétable)
      --report PATH         Chemin du rapport généré
      --dry-run             Générer uniquement les rapports
      --yes                 Ne pas demander confirmation
      --force-images        Inclure les fichiers images dans l'inventaire
      --lang {fr,en}        Langue de l'interface (défaut : fr)
      --config PATH         Fichier de configuration JSON
      --list-formats        Lister les extensions supportées et quitter
      --version             Afficher la version et quitter
  -v, --verbose             Logs détaillés
```

**Codes de retour** :

| Code | Signification |
|------|---------------|
| `0`  | Succès |
| `1`  | Erreur d'utilisation (entrée inexistante, etc.) |
| `2`  | Blocage : fichier OU total > plafond de contexte |
| `3`  | Aucun fichier supporté trouvé |

### Utilisation comme bibliothèque Python

```python
from pathlib import Path
from docfuse.core.orchestrator import run_analysis, generate_corpus

# Lancer l'analyse
result = run_analysis(
    inputs=[Path("D:/Mon dossier")],
    context_limit=128_000,
    margin=0.15,
)

# Inspecter le résultat
for f in result.files:
    print(f"{f.relative_path}: {f.status.value}, "
          f"{f.text_length} chars, {f.image_count} images")

# Générer le corpus si non bloqué
if not result.is_blocked:
    generate_corpus(result, Path("corpus.md"), context_limit=128_000, margin=0.15)
```

### Configuration

DocFuse charge sa configuration depuis trois emplacements (du moins prioritaire
au plus prioritaire) :

1. Valeurs par défaut (cf. `src/docfuse/constants.py`).
2. `CorpusOne.json` à côté de l'exécutable (ou `pyproject.toml` du projet).
3. `CorpusOne.json` dans `%APPDATA%\CorpusOne\` (ou `~/.config/corpusone/`
   sous Linux).
4. `--config PATH` en CLI.

Exemple `CorpusOne.json` :

```json
{
  "context_limit": 128000,
  "margin": 0.15,
  "format": "md",
  "recursive": true,
  "max_depth": 8,
  "exclude_globs": ["~$*", "Thumbs.db"],
  "sort": "name",
  "lang": "fr"
}
```

### Architecture

```
src/docfuse/
├── __main__.py             # sans args → GUI, avec args → CLI
├── cli.py                  # CLI argparse + i18n + codes retour 0-3
├── gui.py                  # GUI CustomTkinter (sélection multiple, jauge dynamique)
├── config.py               # config JSON (3 niveaux) + validate()
├── i18n.py                 # catalogue FR/EN + format_number()
├── constants.py            # extensions, seuils, couleurs, IMAGE_EXTENSIONS
├── assets/                 # DejaVuSans.ttf (police PDF Unicode), tekken_240911.json (vocab Mistral), o200k_base.tiktoken (vocab OpenAI)
├── core/
│   ├── orchestrator.py     # pipeline multi-sources + scan_config + sort + max_depth
│   ├── registry.py         # @register + dispatch par extension
│   ├── context_counter.py  # estimateur tokens (octets/4, +15%) + moteur en option
│   ├── tokenizers/         # registre de moteurs de comptage : approx (défaut), mistral
│   ├── image_detector.py   # détection images + seuils pauvreté
│   ├── inventory.py        # parcours dossier, liste blanche, tri name/mtime/type
│   ├── progress.py         # ProgressEvent (thread-safe)
│   └── report.py           # rapport MD + JSON (i18n)
├── extractors/             # un extracteur = un fichier, registration par @register
│   ├── base.py             # Extractor ABC + safe_extract défensif
│   ├── pdf.py              # pdfminer.six + pypdf
│   ├── docx.py, pptx.py, xlsx.py
│   ├── rtf.py, html.py, text.py
│   ├── markdown.py, csv_tsv.py
│   ├── odf.py, xml_json.py, eml.py, mhtml.py
├── output/
│   ├── markdown_writer.py  # corpus .md + CRLF support
│   ├── pdf_writer.py       # ReportLab + DejaVu Sans
│   └── source_header.py    # en-tête SOURCE + backticks adaptatifs
└── models/
    ├── extraction_result.py # ExtractedFile (dataclass)
    ├── input_selection.py   # sélection exacte, dédoublonnage
    └── file_status.py       # enum FileStatus
```

### Développement

```bash
# Tests
pytest tests/ -v

# Tests d'acceptation (CdC §19)
pytest tests/test_acceptance.py -v

# Lint + format
ruff check src/ tests/
ruff format --check src/ tests/

# Type check strict
mypy --strict src/docfuse/

# Vérification licences (doit ne remonter aucune GPL/AGPL runtime)
pip-licenses --from=classifier --allow-only="MIT;BSD;Apache Software License;ISC License;Mozilla Public License 2.0;Python Software Foundation License;SIL Open Font License"
```

### Build Windows portable

```bash
# Sur une machine Windows avec Python 3.11+ et PyInstaller
pip install pyinstaller
pyinstaller --noconfirm CorpusOne.spec

# Le binaire est dans dist/CorpusOne.exe (~40.6 Mo, autoportant)

# Variante avec OCR bundlé (Tesseract) — nécessite Tesseract installé
# localement au moment du build (voir CorpusOne-OCR.spec pour le détail) :
choco install tesseract -y
pyinstaller --noconfirm CorpusOne-OCR.spec
```

### Contribution

Les contributions sont les bienvenues. Voir
[CONTRIBUTING.md](./CONTRIBUTING.md) pour le workflow complet
(pré-requis, conventions, ajout d'un extracteur, journaux de session).
Le code de conduite est dans [CODE_OF_CONDUCT.md](./CODE_OF_CONDUCT.md).

### Documentation complémentaire

- [Guide utilisateur](./docs/guide-utilisateur.md) — tutoriel GUI + exemples CLI
- [Cahier des charges](./docs/cahier-des-charges-docfuse.md) — spécification
  contractuelle (lecture seule)
- [Journal des décisions](./docs/journal-decisions.md) — 55 décisions
  d'architecture (D-001 à D-055)
- [Journal d'avancement](./docs/journal-avancement.md) — historique des sessions
- [Notes de version](./docs/releases/) — une page par release tag

### Licence

[Apache License 2.0](./LICENSE). Voir aussi [NOTICE](./NOTICE) pour les
attributions des dépendances.

---

## 🇬🇧 English

### Why DocFuse?

Hand-feeding an LLM a whole folder is tedious: open each PDF/DOCX, copy-paste
the text, lose the tables and structure. **DocFuse** automatically extracts the
text from 13 office formats and concatenates it into a single **Markdown**
file (readable by any LLM) or **PDF** (for archival), with a per-file and
total token estimate and a hard ceiling so you never overflow the model's
context window.

### Features

- **Portable Windows**: a single self-contained `CorpusOne.exe`, no external
  DLL, no install, no admin rights. Runs from a USB stick or a network share.
- **Strictly offline**: no network access, enforced by an automated test.
- **Multi-format**: PDF, DOCX, PPTX, XLSX, RTF, HTML, Markdown, CSV/TSV,
  ODT/ODS/ODP, XML/JSON/YAML/INI, EML, MHTML, plus about sixty development
  file extensions (`.py`, `.js`/`.ts`, `.sh`, `.sql`, `.css`, `.java`,
  `.c`/`.cpp`, `.go`, `.rs`, etc.).
- **Generic context counter**: tokens estimate (`UTF-8 bytes / 4`) +
  configurable margin (15% by default).
- **Optional precise counting engines**: real token count for Mistral or
  OpenAI (`--tokenizer-engine {mistral,openai}`), computed locally, no
  network.
- **Ceiling control**: blocks if a single file OR the total exceeds the
  ceiling (128,000 tokens by default).
- **Image and scan detection**, with **optional OCR for scanned PDFs**
  (Tesseract): recognized automatically if an engine is available, never
  blocking otherwise. `CorpusOne.exe` does not bundle Tesseract (unchanged
  size); a separate variant, `CorpusOne-OCR.exe`, bundles it for a
  zero-install experience.
- **Run report**: lists every file (processed, ignored, errors), exported as
  Markdown and JSON.
- **CustomTkinter GUI + argparse CLI + drag-and-drop**.
- **Full i18n**: French (default) and English.
- **Apache 2.0** license, only compatible dependencies
  (MIT/BSD/Apache/ISC/MPL/Python) — no GPL/AGPL.

### Screenshot

<p align="center">
  <img src="docs/assets/screenshots/gui-tokenizer-mistral-result.png" width="640" alt="DocFuse window after analysis: file list with real tokens computed by the Mistral engine"/>
</p>

<p align="center"><sub>Analysis done with the precise counting engine (Mistral) — see the <a href="docs/guide-utilisateur.md#4-le-compteur-de-contexte">user guide</a> (French) for details.</sub></p>

### Download (Windows)

The latest pre-release is **[`v0.1.5 beta`](https://github.com/Martossien/DocFuse/releases/tag/v0.1.5)**
([release notes](./docs/releases/v0.1.5.md), French).

| File | Link |
|---|---|
| **Portable archive** (`CorpusOne.exe`) | [Download .zip](https://github.com/Martossien/DocFuse/releases/download/v0.1.5/CorpusOne-0.1.5-beta-windows-x64.zip) |
| **SHA-256 checksum** | [Download .sha256](https://github.com/Martossien/DocFuse/releases/download/v0.1.5/CorpusOne-0.1.5-beta-windows-x64.zip.sha256) |
| **Portable archive with OCR** (`CorpusOne-OCR.exe`, Tesseract bundled) | [Download .zip](https://github.com/Martossien/DocFuse/releases/download/v0.1.5/CorpusOne-OCR-0.1.5-beta-windows-x64.zip) |
| **SHA-256 checksum** (OCR) | [Download .sha256](https://github.com/Martossien/DocFuse/releases/download/v0.1.5/CorpusOne-OCR-0.1.5-beta-windows-x64.zip.sha256) |

Install:

1. Download the `.zip` (and optionally its `.sha256`).
2. Extract **the single** `CorpusOne.exe` to a folder of your choice.
3. Double-click `CorpusOne.exe`. No network access, no admin rights.

> The binary is unsigned: Windows SmartScreen will show a warning on first
> launch. Verify the SHA-256.

### Quick start

#### Using the portable executable

```bash
# From PowerShell, in the folder containing CorpusOne.exe:
.\CorpusOne.exe --input "D:\My folder" --output ".\corpus.md" --format md --yes
```

The corpus and reports (`corpus.md`, `corpus_rapport.md`,
`corpus_rapport.json`) are written to `D:\My folder\CorpusOne_output\`.

#### Using Python (development)

Requirements: **Python 3.11+**.

```bash
git clone https://github.com/Martossien/DocFuse.git
cd DocFuse
python -m venv .venv
source .venv/bin/activate          # Linux / macOS
# .venv\Scripts\Activate.ps1       # Windows PowerShell
pip install -e ".[dev]"
```

Launch the GUI:

```bash
python -m docfuse
```

Launch the CLI:

```bash
python -m docfuse --input "D:/My folder" --output "corpus.md" --format md --yes
```

### CLI usage

```text
docfuse [OPTIONS]

Options:
  -i, --input PATH          Folder or file to analyse (repeatable)
  -o, --output PATH         Output file (.md or .pdf) or folder
  -f, --format {md,pdf}     Output format (default: md)
  -c, --context INT         Context ceiling in tokens (default: 128000)
      --margin FLOAT        Margin on token estimate (default: 0.15)
      --tokenizer-engine    Counting engine: approx (default), mistral, openai
      --list-tokenizers     List available counting engines
      --recursive           Walk sub-folders
      --no-recursive        Do not walk sub-folders
      --include-ext EXT     Restrict to given extensions (repeatable)
      --exclude-glob GLOB   Exclude files matching the glob (repeatable)
      --report PATH         Path of the generated report
      --dry-run             Only generate the reports
      --yes                 Skip confirmation prompt
      --force-images        Include image files in the inventory
      --lang {fr,en}        UI language (default: fr)
      --config PATH         JSON configuration file
      --list-formats        List supported extensions and exit
      --version             Print version and exit
  -v, --verbose             Verbose logs
```

**Exit codes**:

| Code | Meaning |
|------|---------|
| `0`  | Success |
| `1`  | Usage error (input not found, etc.) |
| `2`  | Blocked: file OR total > context ceiling |
| `3`  | No supported file found |

### Use as a Python library

```python
from pathlib import Path
from docfuse.core.orchestrator import run_analysis, generate_corpus

# Run the analysis
result = run_analysis(
    inputs=[Path("D:/My folder")],
    context_limit=128_000,
    margin=0.15,
)

# Inspect the result
for f in result.files:
    print(f"{f.relative_path}: {f.status.value}, "
          f"{f.text_length} chars, {f.image_count} images")

# Generate the corpus if not blocked
if not result.is_blocked:
    generate_corpus(result, Path("corpus.md"), context_limit=128_000, margin=0.15)
```

### Configuration

DocFuse loads its configuration from four sources (lowest to highest priority):

1. Built-in defaults (see `src/docfuse/constants.py`).
2. `CorpusOne.json` next to the executable (or `pyproject.toml`).
3. `CorpusOne.json` in `%APPDATA%\CorpusOne\` (or `~/.config/corpusone/`
   on Linux).
4. `--config PATH` on the CLI.

Example `CorpusOne.json`:

```json
{
  "context_limit": 128000,
  "margin": 0.15,
  "format": "md",
  "recursive": true,
  "max_depth": 8,
  "exclude_globs": ["~$*", "Thumbs.db"],
  "sort": "name",
  "lang": "fr"
}
```

### Architecture

```
src/docfuse/
├── __main__.py             # no args → GUI, args → CLI
├── cli.py                  # CLI argparse + i18n + exit codes 0-3
├── gui.py                  # CustomTkinter GUI (multi-select, dynamic gauge)
├── config.py               # JSON config (3 layers) + validate()
├── i18n.py                 # FR/EN catalog + format_number()
├── constants.py            # extensions, thresholds, colours, IMAGE_EXTENSIONS
├── assets/                 # DejaVuSans.ttf (Unicode PDF font), tekken_240911.json (Mistral vocab), o200k_base.tiktoken (OpenAI vocab)
├── core/
│   ├── orchestrator.py     # multi-source pipeline + scan_config + sort + max_depth
│   ├── registry.py         # @register + dispatch by extension
│   ├── context_counter.py  # tokens estimator (bytes/4, +15%) + optional engine
│   ├── tokenizers/         # counting engine registry: approx (default), mistral
│   ├── image_detector.py   # image detection + low-text thresholds
│   ├── inventory.py        # folder walk, whitelist, name/mtime/type sort
│   ├── progress.py         # ProgressEvent (thread-safe)
│   └── report.py           # MD + JSON report (i18n)
├── extractors/             # one extractor = one file, auto @register
│   ├── base.py             # Extractor ABC + defensive safe_extract
│   ├── pdf.py              # pdfminer.six + pypdf
│   ├── docx.py, pptx.py, xlsx.py
│   ├── rtf.py, html.py, text.py
│   ├── markdown.py, csv_tsv.py
│   ├── odf.py, xml_json.py, eml.py, mhtml.py
├── output/
│   ├── markdown_writer.py  # .md corpus + CRLF support
│   ├── pdf_writer.py       # ReportLab + DejaVu Sans
│   └── source_header.py    # SOURCE header + adaptive backticks
└── models/
    ├── extraction_result.py # ExtractedFile (dataclass)
    ├── input_selection.py   # exact selection, deduplication
    └── file_status.py       # FileStatus enum
```

### Development

```bash
# Tests
pytest tests/ -v

# Acceptance tests (spec §19)
pytest tests/test_acceptance.py -v

# Lint + format
ruff check src/ tests/
ruff format --check src/ tests/

# Strict type check
mypy --strict src/docfuse/

# License check (must not report any runtime GPL/AGPL)
pip-licenses --from=classifier --allow-only="MIT;BSD;Apache Software License;ISC License;Mozilla Public License 2.0;Python Software Foundation License;SIL Open Font License"
```

### Build the Windows portable

```bash
# On a Windows machine with Python 3.11+ and PyInstaller
pip install pyinstaller
pyinstaller --noconfirm CorpusOne.spec

# The binary lands in dist/CorpusOne.exe (~40.6 MB, self-contained)

# OCR-bundled variant (Tesseract) — requires Tesseract installed locally
# at build time (see CorpusOne-OCR.spec for details):
choco install tesseract -y
pyinstaller --noconfirm CorpusOne-OCR.spec
```

### Contributing

Contributions are welcome. See
[CONTRIBUTING.md](./CONTRIBUTING.md) for the full workflow
(prerequisites, conventions, adding an extractor, session logs).
Code of conduct in [CODE_OF_CONDUCT.md](./CODE_OF_CONDUCT.md).

### Further documentation

- [User guide](./docs/guide-utilisateur.md) — GUI tutorial + CLI examples
  *(currently French-only)*
- [Specification](./docs/cahier-des-charges-docfuse.md) — contractual
  specification (read-only, French)
- [Decision log](./docs/journal-decisions.md) — 55 architecture decisions
  (D-001 to D-055, French)
- [Progress log](./docs/journal-avancement.md) — session-by-session history
  (French)
- [Release notes](./docs/releases/) — one page per release tag

### License

[Apache License 2.0](./LICENSE). See [NOTICE](./NOTICE) for dependency
attributions.

---

<div align="center">

Made with care for the open-source community.

**[⬆ Back to top](#docfuse--corpusone)**

</div>
