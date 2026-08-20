# AGENTS.md — DocFuse / CorpusOne

> Guide de reprise pour tout agent (humain ou IA) qui travaille sur ce projet.
> Ce fichier est mis à jour à chaque session. **Le lire en premier.**

---

## 1. Le projet en une phrase

**DocFuse** (nom de code **CorpusOne**) est un outil Windows portable, hors-ligne, sans droits admin, qui parcourt un dossier de documents hétérogènes (PDF, DOCX, PPTX, XLSX, RTF, HTML, TXT, etc.), en extrait le texte, et produit un corpus unique (Markdown ou PDF) destiné à nourrir un LLM — avec un compteur de contexte générique et un contrôle de plafond.

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
| Empaquetage | PyInstaller --onedir | GPL (exception PyInstaller) |

## 4. Architecture

```
src/docfuse/
├── __main__.py             # sans args → GUI, avec args → CLI
├── cli.py                  # CLI argparse + i18n + codes retour 0-4
├── gui.py                  # GUI CustomTkinter (jauge couleur, recalcul sans ré-extraction)
├── config.py               # config JSON (3 niveaux) + validate() min/max
├── i18n.py                 # catalogue FR/EN + format_number()
├── constants.py            # extensions, seuils, couleurs, IMAGE_EXTENSIONS
├── assets/                 # DejaVuSans.ttf + DejaVuSans-Bold.ttf (police PDF Unicode)
├── core/
│   ├── orchestrator.py     # pipeline principal + scan_config + sort + max_depth
│   ├── registry.py         # @register + dispatch par extension
│   ├── context_counter.py  # estimateur tokens (octets/4, +15%)
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
    └── file_status.py       # enum FileStatus
```

### Pipeline

```
Entrée dossier
  → inventaire (liste blanche extensions, ignores ~$ Thumbs.db etc., sort name/mtime/type)
  → extraction parallèle (ThreadPoolExecutor, bornée)
  → mesure images + pauvreté texte (seuils config scan)
  → compteur par fichier (octets/4, +15%, en-têtes SOURCE comprises)
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
- **Cache mémoire** des textes extraits pour recalcul instantané du compteur si plafond modifié.
- **Parallélisation** : ThreadPoolExecutor (IO-bound) + queue thread-safe pour progression GUI.
- **Code haute qualité** : ruff + mypy --strict + 141 tests en CI.

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
| Typage strict | `mypy --strict` sur 36 fichiers | ✅ |
| Tests exhaustifs | 141 tests (extracteurs, core, acceptation CdC) | ✅ |
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
pyinstaller --noconfirm --onedir --windowed --name CorpusOne src/docfuse/__main__.py
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

- `docs/journal-decisions.md` — historique des décisions d'architecture (D-001 à D-042).
- `docs/journal-avancement.md` — suivi de l'implémentation, session par session, avec statut.
- `docs/cahier-des-charges-docfuse.md` — cahier des charges contractuel (lecture seule).

**Mettre à jour les journaux à chaque session.**

## 11. État actuel (Session 7)

| Métrique | Valeur |
|---|---|
| Fichiers source | 37 |
| Fichiers de test | 27 |
| Tests | 581 |
| ruff | ✅ |
| mypy --strict | ✅ |
| pytest | ✅ 581 passed, 4 skipped |
| Script de recette | ✅ 7/7 PASS |
| Fichiers de test réels | ✅ 75 fichiers (tests/samples_real/) |
| Edge cases testés | ✅ 15 cas (corrompus, vides, chiffrés, malformés) |
| Tests de blocage 128K | ✅ 27 tests (blocage, codes retour, plafond variable, marge variable) |
| Tests Windows | ✅ 10 vérifications (CRLF, APPDATA, frozen, HKLM, spec, log, GUI, cp1252) |
| Décisions archivées | 42 (D-001 à D-042) |
| Extracteurs | 13 formats |
| i18n | FR + EN complets |
| Guide utilisateur | ✅ docs/guide-utilisateur.md |
| Jeu de test + recette | ✅ tests/recette/ |
| Glisser-déposer GUI | ✅ via tkinterdnd2 |
| Police PDF Unicode | ✅ DejaVu Sans (SIL/OFL) |
| Build Windows spec | ✅ CorpusOne.spec + CI job build-windows |
| Bugs connus | 0 (8 bugs trouvés et corrigés) |

### Reste à faire

- ⬜ Build Windows PyInstaller effectif (via CI GitHub Actions sur windows-latest)

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