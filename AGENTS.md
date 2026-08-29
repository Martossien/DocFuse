# AGENTS.md — DocFuse / CorpusOne

> Guide de reprise pour tout agent (humain ou IA) qui travaille sur ce projet.
> Ce fichier est mis à jour à chaque session. **Le lire en premier.**

---

## 1. Le projet en une phrase

**DocFuse** (nom de code **CorpusOne**) est un outil Windows portable, hors-ligne, sans droits admin, qui prend un ou plusieurs dossiers ou fichiers hétérogènes (PDF, DOCX, PPTX, XLSX, RTF, HTML, TXT, etc.), en extrait le texte, et produit un corpus unique (Markdown ou PDF) destiné à nourrir un LLM — avec un compteur de contexte générique par fichier et total, et un contrôle de plafond.

## 2. Cahier des charges

Le cahier des charges contractuel est dans `docs/cahier-des-charges-docfuse.md`.
Il fait foi en cas d'ambiguïté. **Le lire avant toute implémentation.**

Points non négociables (résumé) :
- Aucun droit admin, aucun UAC, aucune connexion réseau.
- Portable (clé USB, partage réseau, dossier utilisateur).
- Pas d'OCR. Pas de perte silencieuse de texte extractible.
- Licence Apache 2.0. Dépendances compatibles (MIT, BSD, Apache, ISC, MPL). **GPL/AGPL interdits.**
- UI en français par défaut + infrastructure i18n.
- Compteur générique : octets_UTF8 / 4, marge +15 %, plafond 128 000 (variable).
- Blocage si un fichier OU le total dépasse le plafond. Images = warning (ne bloque pas).

## 3. Stack technique

| Composant | Choix | Licence |
|---|---|---|
| Langage | Python 3.11+ | PSF |
| GUI | CustomTkinter | MIT |
| CLI | argparse (stdlib) | PSF |
| PDF lecture | pdfminer.six + pypdf | MIT / BSD-3 |
| DOCX | python-docx | MIT |
| PPTX | python-pptx | MIT |
| XLSX | openpyxl | MIT |
| HTML | beautifulsoup4 + lxml | MIT / BSD |
| RTF | striprtf | MIT |
| PDF écriture | ReportLab + DejaVu Sans (SIL/OFL) | BSD / SIL |
| Encodage | charset-normalizer | MIT |
| Tests | pytest | MIT |
| Lint | ruff | MIT |
| Type check | mypy | MIT |
| Empaquetage | PyInstaller --onefile | GPL (exception PyInstaller) |
| Tokenizers précis (option) | tiktoken | MIT |

## 4. Architecture

```
src/docfuse/
├── __main__.py             # sans args → GUI, avec args → CLI
├── cli.py                  # CLI argparse + i18n + codes retour 0-4
├── gui.py                  # GUI CustomTkinter (sélection multiple, retrait, jauge dynamique)
├── config.py               # config JSON (3 niveaux) + validate() min/max
├── i18n.py                 # catalogue FR/EN + format_number()
├── constants.py            # extensions, seuils, couleurs, IMAGE_EXTENSIONS
├── assets/                 # DejaVuSans.ttf/-Bold (police PDF), tekken_240911.json (vocab Mistral), o200k_base.tiktoken (vocab OpenAI)
├── core/
│   ├── orchestrator.py     # pipeline multi-sources + scan_config + sort + max_depth
│   ├── registry.py         # @register + dispatch par extension
│   ├── context_counter.py  # compteur tokens (octets/4 par défaut, ou moteur precis)
│   ├── tokenizers/         # registre de moteurs : approx (défaut), mistral, openai
│   │   ├── base.py         # TokenizerEngine (ABC), TokenizerEngineInfo
│   │   ├── approx.py       # octets/4 (formule historique, comportement inchangé)
│   │   ├── mistral.py      # tiktoken.Encoding + vocab Tekken vendoré (pas mistral-common : pycountry est LGPL)
│   │   ├── openai.py       # tiktoken.Encoding + vocab o200k_base vendoré (pas de téléchargement au 1er lancement)
│   │   └── registry.py     # resolve_engine() ne lève jamais, list_engines()
│   ├── image_detector.py   # détection images + seuils pauvreté (configurables)
│   ├── inventory.py        # parcours dossier, liste blanche, tri name/mtime/type
│   ├── progress.py         # ProgressEvent (thread-safe)
│   └── report.py           # rapport MD + JSON (i18n)
├── extractors/
│   ├── base.py             # Extractor ABC + safe_extract défensif
│   ├── pdf.py              # pdfminer.six + pypdf + récursion figures profonde
│   ├── docx.py             # python-docx + footnotes/endnotes/textboxes + media
│   ├── pptx.py             # python-pptx + notes + [[DIAPO N]] + media
│   ├── xlsx.py             # openpyxl + feuilles + cellules non vides
│   ├── rtf.py              # striprtf
│   ├── html.py             # BeautifulSoup4 + parcours DOM séquentiel
│   ├── text.py             # BOM/UTF-8/charset-normalizer/cp1252/latin-1
│   ├── markdown.py         # .md/.markdown tel quel
│   ├── csv_tsv.py           # .csv/.tsv + délimiteur ; auto
│   ├── odf.py              # .odt/.ods/.odp ZIP/XML
│   ├── xml_json.py         # .xml/.json/.yaml/.ini pretty-print
│   ├── eml.py             # .eml en-têtes + corps
│   └── mhtml.py           # .mhtml/.mht MIME multipart → texte
├── output/
│   ├── markdown_writer.py  # corpus .md + CRLF support
│   ├── pdf_writer.py       # ReportLab + DejaVu Sans + en-tête page
│   └── source_header.py   # en-tête SOURCE + backticks adaptatifs
└── models/
    ├── extraction_result.py # ExtractedFile (dataclass)
    ├── input_selection.py   # sélection exacte, dédoublonnage, exclusions utilisateur
    └── file_status.py       # enum FileStatus
```

### Pipeline

```
Entrée : dossier(s) et/ou fichier(s) explicites
  → sélection normalisée (dédoublonnage + exclusions utilisateur)
  → inventaire (liste blanche extensions, ignores ~$ Thumbs.db etc., sort name/mtime/type)
  → extraction parallèle (ThreadPoolExecutor, bornée)
  → mesure images + pauvreté texte (seuils config scan)
  → compteur par fichier (octets/4 par défaut ou moteur précis, +15%, en-têtes SOURCE comprises)
  → agrégation + compteur total
  → décision: bloquer / autoriser (fichier OU total > plafond)
  → écriture MD ou PDF + rapport MD/JSON
```

### Principes de conception

- **Un extracteur = un fichier**, registration automatique par décorateur `@register`.
- **Type hints** partout, `mypy --strict` en CI.
- **0 dépendance réseau** : aucune lib n'a le droit de faire d'HTTP.
- **Code défensif** : chaque extracteur capture ses erreurs → statut `Erreur` plutôt que crash.
- **i18n** : toutes les chaînes via catalogue (cli, gui, report, orchestrator), aucune en dur.
- **Cache mémoire** des textes extraits pour recalcul instantané du compteur si plafond **ou moteur de comptage** modifié (`OrchestratorResult.recompute_blocking()` / `.recompute_engine()`).
- **Moteurs de comptage précis, jamais bloquants** : `resolve_engine()` ne lève jamais — un id inconnu ou indisponible retombe silencieusement sur `approx`.
- **Sélection exacte** : plusieurs fichiers ne sont jamais remplacés par leur dossier parent ; les retraits persistent pendant la session.
- **Parallélisation** : ThreadPoolExecutor (IO-bound) + queue thread-safe pour progression GUI.
- **Code haute qualité** : ruff + mypy --strict + tests unitaires, d'acceptation et de recette.

## 5. Projets de référence (dans `_references/`)

Clonés pour étude. **Ne pas modifier.** S'en inspirer, pas tout copier.

| Projet | Chemin | Licence | Ce qu'on en reprend |
|---|---|---|---|
| MarkItDown | `_references/markitdown/` | MIT | Pattern Extractor ABC + registry prioritisé, pré-traitement ZIP OOXML, libération mémoire PDF page-par-page, fallback pdfminer pour prose |
| files-to-prompt | `_references/files-to-prompt/` | Apache 2.0 | Séparateur `---` + en-tête provenance, backticks adaptatifs, gestion UnicodeDecodeError non fatale |
| Docling | `_references/docling/` | MIT | Séparation backends déclaratifs vs paginés, étapes pipeline explicites, cache par hash d'options |
| pdfminer.six | `_references/pdfminer.six/` | MIT | `extract_pages()` → LTImage/LTFigure pour détection images, `extract_text()` page-par-page |
| pypdf | `_references/pypdf/` | BSD-3 | Inventaire pages, métadonnées, détection encryption |

## 6. Objectifs de qualité

| Objectif | Mesure | Statut |
|---|---|---|
| Code haute qualité | `ruff check` + `ruff format --check` | ✅ |
| Typage strict | `mypy --strict` sur 44 fichiers | ✅ |
| Tests versionnés | 295 collectés : 256 réussis, 39 ignorés sans `tests/samples_real/` | ⚠️ jeu réel non versionné |
| Maintenabilité | Un extracteur = un fichier, registry auto, docstrings | ✅ |
| User-friendly | GUI CustomTkinter, jauge couleur, recalcul sans ré-extraction | ✅ |
| Configurable | JSON 3 niveaux + validate() + scan_config + sort + max_depth | ✅ |
| i18n complet | FR (défaut) + EN, toutes chaînes via t() | ✅ |
| Pas de GPL/AGPL | Test automatisé test_dependencies_licenses_compatible | ✅ |
| Pas de réseau | Test automatisé test_no_network_imports | ✅ |

## 7. Commandes de développement

```bash
# Installation (mode dev, hors-ligne possible après premier pip install)
pip install -e ".[dev]"

# Lint
ruff check src/ tests/
ruff format --check src/ tests/

# Type check
mypy --strict src/docfuse/

# Tests
pytest tests/ -v

# Tests d'acceptation (CdC §19)
pytest tests/test_acceptance.py -v

# Vérification licences (pas de GPL/AGPL)
pip-licenses --from=classifier --allow-only="MIT;BSD;Apache Software License;ISC License;Mozilla Public License 2.0;Python Software Foundation License"

# Build Windows portable (sur machine Windows)
pyinstaller --noconfirm CorpusOne.spec
```

## 8. CI GitHub Actions

Workflow dans `.github/workflows/ci.yml` :
- Matrix : Python 3.11, 3.12, 3.13 × windows-latest, ubuntu-latest
- Steps : `ruff check` + `ruff format --check` + `mypy --strict` + `pytest`
- Test réseau coupé : un test qui vérifie qu'aucune lib ne tente un accès réseau.
- License check : `pip-licenses` vérifie l'absence de GPL/AGPL.

## 9. Convention de commits

Conventional Commits (sans scope obligatoire) :
- `feat:` nouvelle fonctionnalité
- `fix:` correction
- `refactor:` refactorisation
- `test:` tests
- `docs:` documentation
- `chore:` divers

## 10. Journaux

- `docs/journal-decisions.md` — historique des décisions d'architecture (D-001 à D-055).
- `docs/journal-avancement.md` — suivi de l'implémentation, session par session, avec statut.
- `docs/cahier-des-charges-docfuse.md` — cahier des charges contractuel (lecture seule).

**Mettre à jour les journaux à chaque session.**

## 11. État actuel (Session 14 — 0.1.4 beta)

| Métrique | Valeur |
|---|---|
| Fichiers source Python | 51 |
| Tests collectés depuis un clone frais | 427 |
| ruff | ✅ épinglé `==0.16.5` (D-079), plus de dérive local/CI possible |
| mypy --strict | ✅ 5 erreurs pré-existantes (même classe `bs4.NavigableString`/email `BytesParser`, aucune nouvelle catégorie) |
| pytest | ✅ 388 passed, 39 skipped (`tests/samples_real/` absent) |
| Script de recette | ✅ 7/7 PASS |
| Fichiers de test réels | ⚠️ non présents dans le clone Git (voir « Reste à faire ») |
| Décisions archivées | 87 (D-001 à D-087) |
| Audit extracteurs | 17 bugs de perte silencieuse/qualité corrigés (D-069 à D-076 forte gravité, D-080 à D-087 gravité moyenne) — DOCX, EML, PDF, ODF, HTML, PPTX, RTF, XLSX, MHTML |
| Test conditions réelles | ~/Documents + ~/Téléchargements — 2 bugs trouvés et corrigés : D-077 (bruit JS/CSS minifié), **D-078 (crash SIGSEGV, PDFium non thread-safe entre PDF concurrents)** |
| Extracteurs | 13 formats + fichiers de développement (`CODE_EXTENSIONS`, ~60 extensions, via `TextExtractor`) |
| Moteurs de comptage | 3 : approx (défaut, octets/4), mistral (Tekken), openai (o200k_base) — registre extensible `core/tokenizers/` |
| OCR PDF scannés | Optionnel (Tesseract), registre `core/ocr/` — `CorpusOne.exe` sans OCR bundlé, `CorpusOne-OCR.exe` avec (build CI non encore exécuté, D-067) |
| Optimisations/alertes de transparence | 5 : dédup en-têtes/pieds PDF, retrait base64 Markdown, doublons de contenu, alerte secrets, OCR (D-062 à D-065, D-067) |
| i18n | FR + EN complets |
| Guide utilisateur | ✅ docs/guide-utilisateur.md, captures d'écran réelles |
| Jeu de test + recette | ✅ tests/recette/ |
| Sélection GUI | ✅ dossier(s), fichiers exacts, glisser-déposer, retrait instantané, changement de moteur instantané |
| Police PDF Unicode | ✅ DejaVu Sans (SIL/OFL) |
| Build Windows | ✅ PyInstaller **`--onefile`** (un seul .exe autoportant, GUI + CLI) |
| Publication Windows | ✅ automatique sur les Releases GitHub (`.zip` + `.sha256` × 2 : `CorpusOne` et `CorpusOne-OCR`) à chaque Release publiée — voir §13 |
| Testé sur documents réels | ✅ 65 fichiers synthétiques + 14 documents utilisateur variés, 0 erreur |
| Régressions connues sur la suite versionnée | 0 |
| Working tree | clean |

### Python utilisé sur cette machine

Le PATH utilisateur pointe par défaut vers `C:\Python27\python.exe` (Python 2.7.9), inutilisable
pour ce projet. Les commandes de ce guide utilisent **Python 3.13.15** depuis :

```
C:\Windows\Temp\Python313\python.exe
```

### Reste à faire

- ⬜ Rendre le jeu `tests/samples_real/` reproductible ou documenter sa génération pour supprimer les 39 skips d'un clone frais
- ⬜ Moteur de comptage Llama/HuggingFace `tokenizers` (évoqué comme prochaine option, pas retenu pour 0.1.2 : dépendance Rust supplémentaire)

## 12. Règles critiques

1. **Jamais de GPL/AGPL** dans les dépendances. Vérifier avec `pip-licenses`.
2. **Jamais de réseau** dans le code runtime. Tests CI avec réseau coupé.
3. **Jamais de droits admin**. Pas d'écriture en HKLM, Program Files, services.
4. **Jamais de perte silencieuse**. Tout fichier non traité → rapport avec cause.
5. **Toutes les chaînes UI** via i18n. Pas de chaîne en dur.
6. **Type hints** sur tout le code public. `mypy --strict` doit passer.
7. **Tests** pour chaque extracteur + tests d'acceptation du CdC.
8. **Mise à jour des journaux** à chaque session (décisions + avancement).
9. **Mise à jour de AGENTS.md** si décision de stack ou d'architecture change.

## 13. Procédure de release

Checklist à suivre pour chaque nouvelle version (depuis 0.1.2). Tout se fait
sur `main`, en local (pas de branche de release séparée à ce stade).

1. **Vérifier que `main` est vert** : `ruff check`, `ruff format --check`,
   `mypy --strict src/docfuse/`, `pytest tests/`, `python tests/recette/run_recette.py`.
2. **Bump de version** : `pyproject.toml` (`version = "..."`) **et**
   `src/docfuse/__init__.py` (`__version__ = "..."`) — les deux doivent être
   identiques, aucun autre endroit ne doit contenir la version en dur
   (`grep -rn "0\.1\.X" src/ tests/` doit ne rien trouver côté ancienne
   version).
3. **CHANGELOG.md** : renommer `## [Unreleased]` en `## [X.Y.Z] - AAAA-MM-JJ
   — Beta`, compléter Ajouté/Modifié/Corrigé/Technique (compter les tests et
   décisions à jour), ajouter le lien `[X.Y.Z]: .../releases/tag/vX.Y.Z` en
   bas de fichier.
4. **`docs/releases/vX.Y.Z.md`** : nouvelles notes de version (voir les
   fichiers précédents pour le gabarit). Le nom de zip attendu est
   `CorpusOne-X.Y.Z-beta-windows-x64.zip` (déterminé par le tag Git, voir
   étape 6 — ne pas inventer un autre nom).
5. **README.md** (sections FR **et** EN) : badge de version, tableau de
   téléchargement (lien vers `vX.Y.Z`, nom de fichier `CorpusOne-X.Y.Z-beta-windows-x64.zip`),
   lien vers les notes de version, badge de tests si le nombre a changé.
6. **AGENTS.md** : section « État actuel », `docs/journal-avancement.md` :
   nouvelle entrée de session, `docs/journal-decisions.md` : ADR des
   décisions de la session si non déjà fait.
7. **Commit + push** ces changements sur `main` (voir Git Safety Protocol —
   jamais de force-push, jamais sans review du diff).
8. **Tag + Release** :
   ```bash
   git tag vX.Y.Z
   git push origin vX.Y.Z
   gh release create vX.Y.Z --title "CorpusOne X.Y.Z beta" \
     --notes-file docs/releases/vX.Y.Z.md
   ```
   Publier la Release déclenche automatiquement deux jobs indépendants de
   `.github/workflows/ci.yml` (`github.event_name == 'release'`) :
   `build-windows` (zippe `dist/CorpusOne.exe`) et `build-windows-ocr`
   (zippe `dist/CorpusOne-OCR.exe`, Tesseract embarqué — D-067/D-078).
   Chacun calcule son SHA-256 et attache ses deux fichiers à la Release
   (`gh release upload ... --clobber`) — voir D-061 dans
   `docs/journal-decisions.md`. Aucune étape manuelle d'upload. Les deux
   jobs sont indépendants : un échec de `build-windows-ocr` n'empêche pas
   `CorpusOne.exe` d'être publié normalement.
9. **Vérifier** : `gh run list --branch main --limit 1` jusqu'à
   `completed`/`success`, puis `gh release view vX.Y.Z --json assets` pour
   confirmer que le `.zip` et le `.sha256` sont bien attachés.

**Publier une Release GitHub est une action publique et visible** (notifie
les watchers du dépôt, apparaît dans l'onglet Releases). Un agent qui exécute
cette procédure doit avoir une confirmation explicite de l'utilisateur avant
l'étape 8 — les étapes 1 à 7 sont des modifications locales réversibles, pas
l'étape 8.
