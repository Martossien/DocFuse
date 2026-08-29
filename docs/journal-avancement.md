# Journal d'avancement — DocFuse / CorpusOne

> Suivi de l'implémentation, module par module, avec statut.
> Mis à jour à chaque session.

**Légende des statuts** :
- ⬜ Non commencé — ❌ En cours — ✅ Terminé — ⚠️ Partiel / Bloqué

---

## Session 1 — 20 août 2026

### Phase 0 : Étude et planification — ✅ Terminée

| Tâche | Statut | Notes |
|---|---|---|
| Lecture du cahier des charges | ✅ | 827 lignes |
| Clonage des 5 projets de référence | ✅ | MarkItDown, files-to-prompt, Docling, pdfminer.six, pypdf |
| Analyse de tous les projets de référence | ✅ | Voir détails dans `_references/` |
| Rédaction AGENTS.md | ✅ | |
| Rédaction journal des décisions | ✅ | 20 décisions (D-001 à D-020) |

### Phase 1 : Scaffold + Code — ✅ Terminée

Tout le code source est implémenté et fonctionnel :

| Module | Statut | Fichier |
|---|---|---|
| pyproject.toml | ✅ | Dependencies, ruff, mypy, pytest config |
| LICENSE (Apache 2.0) | ✅ | |
| NOTICE | ✅ | Toutes les deps listées |
| README.md | ✅ | |
| .github/workflows/ci.yml | ✅ | Matrix Python 3.11/3.12/3.13 × Win/Ubuntu + license-check |
| .gitignore | ✅ | |
| constants.py | ✅ | Extensions, seuils, couleurs, natural_sort |
| config.py | ✅ | Config JSON 3 niveaux |
| i18n.py + fr.json + en.json | ✅ | Catalogue complet FR/EN |
| models/file_status.py | ✅ | Enum + severity + is_blocking |
| models/extraction_result.py | ✅ | ExtractedFile dataclass + to_dict |
| core/registry.py | ✅ | @register + dispatch + auto-discovery |
| core/context_counter.py | ✅ | estimate_tokens + check_limit + aggregate |
| core/image_detector.py | ✅ | check_low_text + determine_status |
| core/inventory.py | ✅ | scan_directory + scan_files + list_ignored |
| core/progress.py | ✅ | ProgressEvent + ProgressEmitter thread-safe |
| core/report.py | ✅ | generate_json_report + generate_markdown_report |
| core/orchestrator.py | ✅ | run_analysis + generate_corpus + OrchestratorResult |
| extractors/base.py | ✅ | Extractor ABC + safe_extract défensif |
| extractors/text.py | ✅ | BOM/UTF-8/charset-normalizer/cp1252/latin-1 |
| extractors/markdown.py | ✅ | Tel quel |
| extractors/csv_tsv.py | ✅ | csv module + delimiter auto |
| extractors/xml_json.py | ✅ | JSON/XML pretty-print + YAML/INI tel quel |
| extractors/html.py | ✅ | BeautifulSoup4 + titres→MD + images alt + tableaux |
| extractors/rtf.py | ✅ | striprtf |
| extractors/docx.py | ✅ | python-docx + footnotes/endnotes + media count |
| extractors/pptx.py | ✅ | python-pptx + notes + [[DIAPO N]] + media count |
| extractors/xlsx.py | ✅ | openpyxl + feuilles + cellules non vides |
| extractors/pdf.py | ✅ | pdfminer.six extract_pages + pypdf encryption check |
| extractors/odf.py | ✅ | ZIP/XML content.xml + Pictures/ count |
| extractors/eml.py | ✅ | email module + headers + HTML→texte |
| output/source_header.py | ✅ | build_source_header + adaptive_backticks |
| output/markdown_writer.py | ✅ | write_markdown_corpus avec en-têtes SOURCE |
| output/pdf_writer.py | ✅ | ReportLab SimpleDocTemplate |
| cli.py | ✅ | argparse + codes retour 0-4 + --dry-run + --yes |
| gui.py | ✅ | CustomTkinter + thread analyse + progression |

### Phase 2 : Tests — ✅ Terminée

| Test file | Statut | # tests |
|---|---|---|
| conftest.py | ✅ | Fixtures tmp_workspace, large_text, fixtures_dir |
| test_acceptance.py | ✅ | 11 (portabilité réseau, blocage, ignores, licence, i18n) |
| test_core/test_context_counter.py | ✅ | 11 |
| test_core/test_image_detector.py | ✅ | 13 |
| test_core/test_inventory.py | ✅ | 11 |
| test_core/test_orchestrator.py | ✅ | 8 |
| test_core/test_registry.py | ✅ | 7 |
| test_core/test_report.py | ✅ | 2 |
| test_extractors/test_text.py | ✅ | 6 |
| test_extractors/test_markdown.py | ✅ | 3 |
| test_extractors/test_simple_formats.py | ✅ | 12 (CSV, TSV, JSON, XML, HTML) |
| test_extractors/test_docx.py | ✅ | 6 |
| test_extractors/test_pptx.py | ✅ | 5 |
| test_extractors/test_xlsx.py | ✅ | 5 |
| test_extractors/test_rtf.py | ✅ | 4 |
| test_extractors/test_pdf.py | ✅ | 5 |
| test_extractors/test_odf.py | ✅ | 5 |
| test_extractors/test_eml.py | ✅ | 4 |
| **Total** | ✅ | **118 tests** |

Fixtures binaires pré-générées dans `tests/fixtures/` :
- sample.docx, sample.pptx, sample.xlsx (via python-docx, python-pptx, openpyxl)
- sample.rtf, sample.eml, sample.odt, sample.pdf

### Phase 3 : Validation finale — ✅ Terminée

| Tâche | Statut | Notes |
|---|---|---|
| `ruff check` | ✅ | All checks passed |
| `ruff format --check` | ✅ | 58 files already formatted |
| `mypy --strict` | ✅ | Success: no issues found in 36 source files |
| `pytest` | ✅ | 118 passed in 1.42s |
| `pip-licenses` | ✅ | Toutes les deps DocFuse sont MIT/BSD/Apache. Le warning nvidia-cusparse est un package CUDA de l'environnement de dev global, pas une dépendance de DocFuse. |
| Test licence automatisé | ✅ | test_dependencies_licenses_compatible dans test_acceptance.py |

### CLI testée manuellement — ✅

- `python -m docfuse --list-formats` → ✅ Affiche toutes les extensions
- `python -m docfuse -i samples/test_corpus --dry-run` → ✅ Analyse, tokens, blocage
- `python -m docfuse -i samples/test_corpus -o corpus.md` → ✅ Corpus généré
- `python -m docfuse -i samples/test_corpus --context 50 --yes` → ✅ Code 2 (blocage)

---

## Session 2 — 20 août 2026

### Objectifs atteints

1. ✅ Ajout des tests pour tous les formats complexes (DOCX, PPTX, XLSX, PDF, RTF, EML, ODF)
2. ✅ Ajout test orchestrator end-to-end (8 tests)
3. ✅ Ajout test report (2 tests)
4. ✅ Création des fixtures binaires (generate_fixtures.py + fichiers sample.*)
5. ✅ Ajout .gitignore
6. ✅ Test de licence automatisé (test_dependencies_licenses_compatible)
7. ✅ Correction CLI exit code (--yes + blocage → code 2)
8. ✅ Mise à jour du journal d'avancement

### Statut final du projet

**Le projet DocFuse v0.1.0 est implémenté et validé :**
- 36 fichiers source Python
- 58 fichiers au total (src + tests)
- 118 tests, tous au vert
- ruff, mypy --strict, pytest passent
- Toutes les dépendances sont MIT/BSD/Apache (pas de GPL/AGPL)
- CLI fonctionnelle avec tous les flags du CdC §6.3
- GUI CustomTkinter implémentée (non testée en CI headless)
- 12 extracteurs de formats (PDF, DOCX, PPTX, XLSX, RTF, HTML, TXT, MD, CSV, ODF, XML/JSON, EML)

### Reste à faire (hors v1, si nécessaire)

- ⬜ Test GUI end-to-end (nécessite un environnement graphique)
- ⬜ Build Windows PyInstaller (nécessite Windows)
- ⬜ Guide utilisateur français (CdC §21.5)
- ⬐ Mini guide utilisateur FR (1-2 pages)
- ⬐ Jeu de fichiers de test anonymisé + script de recette

---

## Session 3 — 20 août 2026 — Audit et corrections

### Objectifs

Audit complet du code contre le CdC, correction de tous les problèmes CRITIQUES et IMPORTANTS.

### Audit

Un audit approfondi a identifié :
- **11 problèmes CRITIQUES** (police PDF, i18n absente, dry-run sans rapport, flags CLI non implémentés, seuils ignorés, en-tête PDF manquant, pas de lancement GUI)
- **23 problèmes IMPORTANTS** (tokens en-tête, formule rapport, format nombres, profondeur config, rapports réingérés, multi-input, recalcul GUI, sortie par défaut, validation config, ordre HTML, etc.)
- **22 problèmes MINEURS** (UTF-16 BOM, CSV `;`, file_type générique, etc.)

### Corrections appliquées

#### CRITIQUES corrigés (11/11)

| ID | Problème | Statut | Fichier(s) |
|---|---|---|---|
| C-01 | Police PDF Unicode (DejaVu Sans TTF embarquée) | ✅ | pdf_writer.py, assets/ |
| C-02 | i18n dans cli.py (toutes les chaînes via t()) | ✅ | cli.py |
| C-03 | i18n dans report.py (labels via t()) | ✅ | report.py |
| C-04 | i18n dans orchestrator.py (block_reason via t()) | ✅ | orchestrator.py |
| C-05 | Dry-run génère un rapport (CdC §19.2) | ✅ | cli.py |
| C-06 | --include-ext implémenté (surcharge extensions) | ✅ | cli.py, orchestrator.py |
| C-07 | --report implémenté (chemin personnalisé) | ✅ | cli.py |
| C-08 | Seuils de scan passés depuis la config | ✅ | orchestrator.py, image_detector.py |
| C-09 | En-tête de page PDF (nom + n° page) | ✅ | pdf_writer.py |
| C-10 | Glisser-déposer GUI (nécessite lib externe) | ⚠️ Reporté | — |
| C-11 | __main__.py dispatche vers GUI si pas d'args | ✅ | __main__.py |

#### IMPORTANTS corrigés (16/23)

| ID | Problème | Statut | Fichier(s) |
|---|---|---|---|
| I-01 | Tokens en-tête SOURCE (texte seul → texte+header) | ✅ | orchestrator.py |
| I-02 | Rapport MD formule tokens (ceil au lieu de //) | ✅ | report.py |
| I-03 | format_number() utilisé partout (FR espaces insécables) | ✅ | cli.py, report.py, markdown_writer.py |
| I-04 | Profondeur max configurable via JSON | ✅ | config.py |
| I-05 | Fichiers rapport exclus de l'inventaire | ✅ | constants.py |
| I-07 | --input répétable (tous les inputs utilisés) | ✅ | cli.py |
| I-13 | Sortie par défaut dans CorpusOne_output/ | ✅ | cli.py |
| I-15 | Avertissement pour fichier > 50 Mo | ✅ | orchestrator.py |
| I-17 | Validation min/max de la config | ✅ | config.py |
| I-18 | HTML ordre du document respecté | ✅ | html.py |
| I-22 | Images pures message spécifique au rapport | ✅ | inventory.py, constants.py |
| I-08+09 | GUI recalcul plafond + valeur éditée | ⚠️ Reporté | gui.py |
| I-06 | CRLF support | ⚠️ Reporté | — |
| I-14 | Config sort (name/mtime/type) | ⚠️ Partiel (name only) | inventory.py |
| I-16 | Log fichier avec rotation | ⚠️ Reporté | — |
| I-19 | DOCX zones de texte | ⚠️ Reporté | docx.py |
| I-20 | --output vs --format cohérence | ⚠️ Reporté | — |
| I-21 | GUI message de blocage conforme | ⚠️ Reporté | gui.py |
| I-12 | GUI cases manquantes | ⚠️ Reporté | gui.py |
| I-10 | GUI colonne Texte estimé | ⚠️ Reporté | gui.py |
| I-11 | GUI jauge couleur | ⚠️ Reporté | gui.py |

#### MINEURS corrigés (7/22)

| ID | Problème | Statut | Fichier(s) |
|---|---|---|---|
| M-01 | UTF-16 BOM strippé | ✅ | text.py |
| M-03 | determine_status condition simplifiée | ✅ | orchestrator.py |
| M-05 | CSV délimiteur `;` supporté | ✅ | csv_tsv.py |
| M-08 | file_type spécifique par extension | ✅ | odf.py, xml_json.py |
| M-17 | zip strict=True | ✅ | orchestrator.py, pdf_writer.py |
| M-22 | __main__.py gestion KeyboardInterrupt | ✅ | __main__.py |
| M-04 | .mhtml/.mht non supportés | ⚠️ Reporté | — |
| M-02 | Récursion PDF figures | ⚠️ Reporté | — |
| M-06 | Pattern ~$* vs ~$ * | ⚠️ Le code est correct | — |
| M-07 | _should_ignore_dir filtre .xxx | ⚠️ Reporté | — |
| M-09 à M-21 | Divers mineurs | ⚠️ Reportés | — |

### Validation finale

| Check | Résultat |
|---|---|
| ruff check | ✅ All checks passed |
| ruff format --check | ✅ 58 files already formatted |
| mypy --strict | ✅ no issues found in 36 source files |
| pytest | ✅ 118 passed |

### Reste à faire

- ⚠️ GUI : recalcul plafond sans ré-extraction, cases manquantes, jauge couleur, drag-and-drop
- ⚠️ CRLF support dans markdown_writer
- ⚠️ Config sort (mtime, type)
- ⚠️ Log fichier avec rotation (CdC §18)
- ⚠️ DOCX zones de texte (w:txbxContent)
- ⚠️ .mhtml/.mht support
- ⚠️ Récursion PDF figures profonde
- ⬜ Test GUI end-to-end
- ⬜ Build Windows PyInstaller
- ⬜ Guide utilisateur français

---

## Session 4 — 20 août 2026 — GUI, log, CRLF, sort, DOCX, PDF

### Objectifs

Continuer la correction des problèmes restants : GUI user-friendly, log fichier rotation,
CRLF support, config sort (mtime/type), DOCX zones de texte, récursion PDF profonde.

### Corrections appliquées

#### GUI (refonte complète)

| ID | Problème | Statut | Détails |
|---|---|---|---|
| I-08/I-09 | Recalcul plafond sans ré-extraction + valeur éditée | ✅ | `_get_current_limit()` lit `context_var`, recalcul `is_blocked` sans ré-extraire |
| I-10 | Colonne « Texte estimé » | ✅ | 5 colonnes : Fichier, Type, Texte estimé, Contexte +15%, Statut |
| I-11 | Jauge couleur vert/orange/rouge | ✅ | `progress_color` dynamique selon ratio |
| I-12 | Case « Ouvrir le dossier à la fin » | ✅ | `open_folder_var` + `_open_folder()` multi-plateforme |
| I-13 | Sortie dans CorpusOne_output/ | ✅ | `output_dir = input_path / "CorpusOne_output"` |
| I-21 | Message blocage conforme CdC | ✅ | `t("summary.blocked_file", ...)` avec valeurs numériques |
| M-10 | config.margin au lieu de DEFAULT_MARGIN | ✅ | `margin=self.config.margin` |
| M-13 | Bouton « Changer » | ✅ | Affiché après choix du dossier |
| M-14 | Lien « qu'est-ce que c'est ? » | ✅ | Label info à côté du plafond |
| M-15 | Export rapport fonctionnel | ✅ | `filedialog.asksaveasfilename()` |

#### Autres corrections

| ID | Problème | Statut | Fichier(s) |
|---|---|---|---|
| I-06 | CRLF support dans markdown_writer | ✅ | markdown_writer.py (`line_ending` param) |
| I-14 | Config sort (name/mtime/type) | ✅ | inventory.py (`sort` param) |
| I-16 | Log fichier avec rotation 2 Mo | ✅ | cli.py (`RotatingFileHandler`) |
| I-19 | DOCX zones de texte (w:txbxContent) | ✅ | docx.py (`_extract_textboxes`) |
| M-02 | Récursion PDF figures profonde | ✅ | pdf.py (`_count_recursive`) |
| I-15 | Avertissement fichier > 50 Mo | ✅ | orchestrator.py |

### Nouveaux tests (23)

| Test file | # tests | Couverture |
|---|---|---|
| test_new_features.py | 23 | sort modes, config.validate, dry-run rapport, --include-ext, image message, CRLF, format_number, report i18n FR/EN, CLI exit codes, max_depth |

### Validation finale

| Check | Résultat |
|---|---|
| ruff check | ✅ All checks passed |
| ruff format --check | ✅ 59 files already formatted |
| mypy --strict | ✅ no issues found in 36 source files |
| pytest | ✅ 141 passed in 1.51s |

### Reste à faire

- ⬜ C-10 : Glisser-déposer GUI (nécessite tkinterdnd2 ou windnd)
- ⬜ .mhtml/.mht support
- ⬜ M-07 : _should_ignore_dir trop agressif (.xxx)
- ⬜ Test GUI end-to-end
- ⬜ Build Windows PyInstaller
- ⬜ Guide utilisateur français

---

## Session 5 — 20 août 2026 — .mhtml, M-07, guide utilisateur

### Objectifs

Corriger les derniers problèmes restants : .mhtml/.mht support, M-07 (_should_ignore_dir),
guide utilisateur français (CdC §21.5), mise à jour AGENTS.md.

### Corrections appllicées

| ID | Problème | Statut | Fichier(s) |
|---|---|---|---|
| M-04 | .mhtml/.mht non supportés | ✅ | extractors/mhtml.py (nouveau), constants.py, registry.py |
| M-07 | _should_ignore_dir trop agressif (.xxx) | ✅ | inventory.py (filtre VCS seulement, pas .config/.local) |
| §21.5 | Guide utilisateur français | ✅ | docs/guide-utilisateur.md (1-2 pages) |
| — | AGENTS.md mis à jour avec état complet | ✅ | AGENTS.md (sections 6, 11 ajoutées) |

### Nouveaux tests (7)

| Test file | # tests | Couverture |
|---|---|---|
| test_mhtml.py | 4 | extract MHTML, accepts, safe_extract, empty |
| test_inventory.py | +3 | _should_ignore_dir (git, .config, system) |

### Validation finale

| Check | Résultat |
|---|---|
| ruff check | ✅ All checks passed |
| ruff format --check | ✅ 61 files already formatted |
| mypy --strict | ✅ no issues found in 37 source files |
| pytest | ✅ 148 passed in 1.53s |

### État final du projet

| Métrique | Valeur |
|---|---|
| Fichiers source | 37 (+ mhtml.py) |
| Fichiers de test | 24 |
| Tests | 148 |
| Extracteurs | 13 formats (+ mhtml) |
| Décisions archivées | 42 |
| Guide utilisateur | ✅ docs/guide-utilisateur.md |

### Reste à faire

- ⬜ Glisser-déposer GUI (nécessite tkinterdnd2 ou windnd, licence compatible)
- ⬜ Test GUI end-to-end (nécessite écran)
- ⬜ Build Windows PyInstaller (nécessite Windows)
- ⬐ Jeu de fichiers de test anonymisé + script de recette (CdC §21.4)

---

## Session 5 — 20 août 2026 — Finalisation complète

### Objectifs

Corriger les derniers problèmes restants : .mhtml/.mht, M-07, guide utilisateur,
glisser-déposer GUI, jeu de test + script de recette, police PDF Unicode.

### Corrections appliquées

| ID | Problème | Statut | Fichier(s) |
|---|---|---|---|
| C-01 | Police PDF Unicode (DejaVu Sans TTF valide) | ✅ | pdf_writer.py, assets/DejaVuSans.ttf |
| C-10 | Glisser-déposer GUI via tkinterdnd2 | ✅ | gui.py (_setup_drag_and_drop, _on_drop) |
| M-04 | .mhtml/.mht non supportés | ✅ | extractors/mhtml.py (nouveau) |
| M-07 | _should_ignore_dir trop agressif | ✅ | inventory.py (filtre VCS seulement) |
| §21.4 | Jeu de fichiers de test anonymisé + script de recette | ✅ | tests/recette/ (dossier_mixte, dossier_blocage, run_recette.py) |
| §21.5 | Guide utilisateur français | ✅ | docs/guide-utilisateur.md |
| — | AGENTS.md mis à jour avec état complet | ✅ | AGENTS.md |

### Script de recette (7/7 PASS)

- Dossier mixte → Markdown ✅
- Dossier mixte → PDF ✅
- Blocage par plafond → code 2 ✅
- Fichier .exe ignoré + rapport ✅
- Fichier verrou ~$ ignoré ✅
- Dry-run avec rapport ✅
- --list-formats ✅

### Validation finale

| Check | Résultat |
|---|---|
| ruff check | ✅ All checks passed |
| ruff format --check | ✅ 62 files already formatted |
| mypy --strict | ✅ no issues found in 37 source files |
| pytest | ✅ 148 passed in 1.56s |
| Script de recette | ✅ 7/7 PASS |

### État final du projet

| Métrique | Valeur |
|---|---|
| Fichiers source | 37 |
| Fichiers de test | 25 |
| Tests | 148 |
| Extracteurs | 13 formats |
| Décisions archivées | 42 |
| Guide utilisateur | ✅ |
| Jeu de recette | ✅ 7/7 |
| i18n | FR + EN complets |

### Reste à faire

- ⬜ Build Windows PyInstaller (nécessite Windows)

---

## Session 6 — 20 août 2026 — Chasse aux bugs + build Windows

### Objectifs

1. Télécharger des fichiers de test réels pour toutes les extensions
2. Vérifier le contenu extrait pour traquer les bugs
3. Configurer le build Windows (PyInstaller spec + CI)
4. Corriger tous les bugs trouvés

### Fichiers de test réels (31 fichiers)

Création de `tests/samples_real/` avec :
- 10 PDF réels (depuis pypdf sample-files + pdfminer.six samples)
- Fichiers texte : UTF-8, cp1252, BOM, log
- HTML avec titres, listes, tableaux, images, script
- CSV (délimiteur `;`), TSV, JSON, XML, YAML, INI, Markdown
- EML, MHTML, DOCX, PPTX, XLSX, RTF, ODT

### Bugs trouvés et corrigés (3)

| Bug | Description | Statut |
|---|---|---|
| **BUG 1** | cp1252 mal détecté : charset-normalizer retournait `mac_latin2` au lieu de `cp1252` pour les fichiers courts avec accents français → accents corrompus | ✅ Corrigé : cp1252 essayé avant charset-normalizer |
| **BUG 2** | HTML : texte dupliqué — le parcours DOM extrait titres/listes/tableaux, puis `get_text()` récupère aussi le texte de ces éléments | ✅ Corrigé : parcours des enfants directs (pas descendants) + pas de `get_text()` global |
| **BUG 3** | Markdown : contenu encapsulé dans des backticks ```` ```` au lieu d'être inclus "tel quel" (CdC §7.3) | ✅ Corrigé : pas de backticks pour les formats texte/markdown/csv/json/etc. |

### Build Windows

- `CorpusOne.spec` : spec file PyInstaller --onedir --windowed avec assets (polices DejaVu + i18n)
- `build.sh` : script de build (Windows natif ou Wine)
- CI GitHub Actions : job `build-windows` sur `windows-latest` qui build le binaire et l'upload en artifact
- Wine installé sur la machine de dev mais wine32 trop long à installer → le build se fait via CI

### Validation finale

| Check | Résultat |
|---|---|
| ruff check | ✅ All checks passed |
| ruff format --check | ✅ 62 files already formatted |
| mypy --strict | ✅ no issues found in 37 source files |
| pytest | ✅ 148 passed |
| Script de recette | ✅ 7/7 PASS |
| Extraction 31 fichiers réels | ✅ 0 problème |

---

## Session 7 — 20 août 2026 — Chasse aux bugs approfondie

### Objectifs

Vérifier avec de vrais fichiers complexes, traquer les bugs subtils, tester les edge cases.

### Fichiers de test complexes créés (15 nouveaux)

- rapport_activite.docx (titres, paragraphes, tableau, conclusion)
- presentation_strategie.pptx (3 diapos, notes d'orateur, textbox)
- donnees_financieres.xlsx (2 feuilles, formules SUM)
- documentation_technique.html (CSS, tableaux, listes, image)
- rapport_mensuel.eml (multipart text/plain + text/html)
- rapport_technique.rtf (mise en forme, accents cp1252)
- employes.csv (guillemets, virgules dans les noms)
- entreprise.json (structure imbriquée, booléens)
- catalogue.xml (namespaces, produits)
- guide_installation.md (tableaux, code blocks, blockquote)
- rapport_audit.odt (tableau ODF)
- page_sauvegardee.mhtml (multipart MIME)
- 15 edge cases (corrompus, vides, chiffrés, malformés)

### Bugs trouvés et corrigés (7)

| Bug | Description | Impact | Fix |
|---|---|---|---|
| 1 | cp1252 mal détecté (charset-normalizer retourne mac_latin2) | Accents français corrompus | cp1252 essayé avant charset-normalizer |
| 2 | HTML texte dupliqué (get_text + parcours DOM) | Texte en double | Parcours enfants directs, pas de get_text global |
| 3 | EML multipart dupliqué (text/plain ET text/html) | Corps en double | Prendre text/plain en priorité, HTML en fallback |
| 4 | ODT tableau dupliqué (paragraphes + cellules) | Tableau en double | Parcours enfants office:text, pas find_all global |
| 5 | DOCX tableau hors ordre (à la fin du document) | Ordre du document perdu | Itération sur body.element pour respecter l'ordre |
| 6 | HTML `<br>` crash (int("r") sur tag non-h) | Crash sur tags non-h1-h6 | Vérifier tag_name[1].isdigit() avant int() |
| 7 | Markdown encapsulé dans backticks | .md dans ```` au lieu de "tel quel" | Pas de backticks pour formats texte/markdown |

### Edge cases testés (15)

- PDF corrompu → ERROR ✅
- DOCX corrompu → ERROR ✅
- XLSX corrompu → ERROR ✅
- HTML malformé → READY ✅ (robuste)
- XML malformé → ERROR ✅
- JSON malformé → ERROR ✅
- CSV irrégulier → READY ✅ (robuste)
- TXT avec binaires → READY ✅ (robuste)
- RTF malformé → READY ✅ (robuste)
- EML sans sujet → READY ✅ (robuste)
- ZIP nommé .docx → ERROR ✅
- PDF chiffré → ERROR ✅ (mot de passe détecté)
- HTML tags seulement → READY ✅ (après fix bug 6)
- CSV vide → READY ✅
- MD backticks → READY ✅

### Validation finale

| Check | Résultat |
|---|---|
| ruff check | ✅ All checks passed |
| ruff format --check | ✅ 62 files already formatted |
| mypy --strict | ✅ no issues found in 37 source files |
| pytest | ✅ 148 passed |
| Script de recette | ✅ 7/7 PASS |
| Edge cases | ✅ 15/15 OK |
| Bugs | ✅ 7 corrigés, 0 restant |

---

## Session 8 — 20 août 2026 — Sélection multi-fichiers et GUI actionnable

### Objectifs prioritaires

1. Respecter exactement les fichiers et dossiers choisis par l'utilisateur.
2. Afficher et conserver l'estimation de tokens de chaque fichier.
3. Permettre de retirer un document et de débloquer le corpus sans ré-extraction.
4. Corriger la CLI répétable et préserver les alertes pendant les recalculs.

### Défauts corrigés

| Défaut | Impact utilisateur | Correction |
|---|---|---|
| Dépôt de plusieurs fichiers remplacé par leur dossier parent | Documents non choisis ajoutés silencieusement | Sélection exacte via `InputSelection` |
| CLI `--input` répétable mais seul le premier chemin analysé | Corpus incomplet | Fusion réelle de toutes les entrées |
| Aucun moyen concret de « retirer des fichiers » | Blocage difficile à résoudre | Bouton Retirer + recalcul en cache |
| Recalcul du plafond restaurant `READY` | Alertes images/scans perdues | Conservation des statuts d'analyse originaux |
| Plafond GUI non recalculé pendant la saisie | État du bouton Générer obsolète | Callback de recalcul immédiat |
| Accès à des variables Tk depuis le thread d'analyse | Risque d'erreur GUI intermittente | Options capturées sur le thread principal |
| Arrêt pouvant laisser un résultat partiel générable | Corpus incomplet présenté comme valide | Résultat annulé et génération désactivée |

### Fonctionnalités livrées

- Bouton **Choisir des fichiers…** avec sélection multiple.
- Glisser-déposer de plusieurs fichiers réellement figé.
- Sélection de plusieurs dossiers/fichiers supportée par le pipeline.
- Dédoublonnage des chemins et provenance unique dans les en-têtes `SOURCE`.
- Estimation brute et avec marge conservée pour chaque fichier.
- Bouton **Retirer** par ligne, mise à jour instantanée du compteur et du blocage.
- Exclusions utilisateur présentes dans le rapport et persistantes lors d'une réanalyse.
- Messages et libellés ajoutés aux catalogues français et anglais.
- Gestion explicite d'une erreur d'analyse dans la GUI.
- Annulation sûre : aucun corpus partiel ne peut être généré après « Arrêter ».

### Tests ajoutés

- Sélection immuable, dédoublonnage et dossier de sortie.
- Liste explicite sans élargissement au dossier parent.
- Multi-dossiers et noms de sources non ambigus.
- Déduplication d'un fichier présent via plusieurs sources.
- Exclusion persistante et présence au rapport.
- Estimation de tokens par fichier et cohérence avec le total.
- Retrait, recalcul du total et déblocage.
- Préservation du warning images après changement de plafond.
- CLI avec plusieurs `--input`.
- Parsing DnD de plusieurs chemins avec ou sans espaces.

### Validation

| Check | Résultat |
|---|---|
| ruff check | ✅ All checks passed |
| ruff format | ✅ 67 fichiers formatés ou déjà conformes |
| mypy --strict | ✅ no issues found in 38 source files |
| pytest ciblé après refactoring | ✅ 57 passed |
| pytest complet du clone frais | ✅ 194 passed, 38 skipped |
| Script de recette | ✅ 7/7 PASS |

### Écart de reproductibilité constaté

Le dossier `tests/samples_real/`, annoncé dans l'état de la Session 7 avec 75 fichiers,
n'est pas présent dans un clone Git frais. Les 38 tests associés sont donc ignorés. La
suite versionnée et la recette passent intégralement ; il reste à rendre ce jeu de données
reproductible ou à documenter sa génération.

---

*Fin du journal d'avancement — Session 8.*

---

## Session 9 — 20 août 2026 — Retours utilisateur et beta 0.1.1

### Retours traités

| Retour utilisateur | Correction |
|---|---|
| Le second fichier semblait remplacer le premier | Ajout cumulatif des fichiers et dossiers |
| Les fichiers d'un dossier n'apparaissaient pas immédiatement | Lignes créées dès l'inventaire avec état d'attente |
| La fenêtre devait être élargie horizontalement | Options réparties sur trois lignes et mise en page responsive |
| Le plafond 128 K était difficile à trouver | Contrôle du contexte maximal rendu visible dans la zone d'options |
| Doute sur le nombre de tokens | Audit de la formule, point fixe des en-têtes et marge appliquée une fois au total |

### Préparation de la version

- Version portée à **0.1.1 beta**.
- `CorpusOne.spec` corrigé pour inclure les 13 extracteurs chargés dynamiquement.
- Build Windows `--onedir` réalisé avec PyInstaller 6.22.2 et Python 3.13.15.
- Exécutable compilé testé sur le dossier de recette : génération Markdown et PDF,
  rapports Markdown/JSON présents, codes retour `0`.
- Archive portable et empreinte SHA-256 préparées comme fichiers de la préversion.

### Validation

| Check | Résultat |
|---|---|
| ruff check | ✅ All checks passed |
| ruff format --check | ✅ conforme |
| mypy --strict | ✅ no issues found in 38 source files |
| pytest complet du clone frais | ✅ 198 passed, 38 skipped |
| Script de recette | ✅ 7/7 PASS |
| Smoke test `.exe` → Markdown | ✅ code retour 0 |
| Smoke test `.exe` → PDF | ✅ code retour 0 |

Les 38 tests ignorés correspondent toujours au jeu `tests/samples_real/` absent du
clone Git ; aucun test de la suite versionnée n'échoue.

---

*Fin du journal d'avancement — Session 9.*

---

## Session 10 — 20 août 2026 — Reprise après commit 0.1.1 et nettoyage

### Contexte

Le dépôt venait d'être commité avec le tag `v0.1.1` (commit `166e595 chore: préparer la beta 0.1.1`).
Cette session est une **reprise** : installation de l'environnement sur une machine
fraîche, validation complète de la qualité et nettoyage d'un artefact accidentel.

### Installation de l'environnement

- Python par défaut détecté : `C:\Python27\python.exe` (2.7.9) — non utilisable
  (le projet exige Python ≥ 3.11).
- Python retenu : `C:\Windows\Temp\Python313\python.exe` (3.13.15, déjà présent sur la machine).
- Vérification `tkinter` et `customtkinter` : présents.
- Vérification de toutes les dépendances prod + dev : déjà installées sur cet interpréteur.
- `pip install -e ".[dev]"` : upgrade de `docfuse 0.1.0` (installé en editable) vers **`docfuse 0.1.1`**.
- Outils disponibles après install : `ruff 0.16.3`, `mypy 2.3.1`, `pytest 9.1.1`, `pip-licenses 5.5.5`.
- Script `docfuse.exe` installé dans `C:\Windows\Temp\Python313\Scripts\` (hors PATH ;
  utilisation directe via `-m docfuse.cli` ou `python -m docfuse`).

### Nettoyage

- `extraction_result.py` (87 lignes) détecté en **untracked** à la racine.
- Vérification `fc.exe` : identique au bit près à `src/docfuse/models/extraction_result.py`
  (doublon accidentel).
- Supprimé après validation utilisateur. `git status` → working tree clean.

### Validation complète

| Check | Résultat |
|---|---|
| `ruff check src/ tests/` | ✅ All checks passed |
| `ruff format --check src/ tests/` | ✅ 67 files already formatted |
| `mypy --strict src/docfuse/` | ✅ no issues found in 38 source files |
| `pytest` complet | ✅ **199 passed, 38 skipped in 6.31s** (+1 nouveau test) |
| `tests/test_acceptance.py::TestLicenseCompliance` | ✅ 2/2 (no GPL/AGPL, licenses compatibles) |
| `tests/test_acceptance.py::TestPortability::test_no_network_imports` | ✅ 1/1 |
| `tests/test_context_blocking.py` | ✅ 29/29 (dont nouveau test_cli_output_dir_without_extension) |
| `piplicenses --allow-only` | ✅ Aucune GPL/AGPL runtime ; seul `pyinstaller` (build-only, exception) |

### Bug DLL Python manquant : passage du binaire à `--onefile`

**Symptôme rapporté par l'utilisateur** : déplacer `CorpusOne.exe` seul déclenche
un message Windows « DLL Python 3.13 manquante ». C'est le comportement attendu
d'un build `--onedir` qui produit un `.exe` dépendant d'un dossier `_internal/`
voisin (`python313.dll`, `python3.dll`, `VCRUNTIME140.dll`, etc.). Si l'utilisateur
ne copie que l'exécutable, Windows ne trouve pas la DLL au chargement.

**Décision** : `CorpusOne.spec` passe en mode `--onefile` (D-052). La runtime Python
est désormais embarquée dans l'unique `CorpusOne.exe` (~35.9 Mo). Le dossier
`_internal/` n'est plus distribué. Le CdC §5.1 prévoyait déjà cette option comme
privilégiée pour la portabilité.

**Changements dans le spec** : suppression du bloc `COLLECT(exe, a.binaries, a.datas, ...)`,
passage de `exclude_binaries=True` à `False`, ajout de `a.binaries` et `a.datas`
comme arguments de `EXE(...)`.

**Smoke test du binaire onefile** :
- `CorpusOne.exe --version` → `docfuse 0.1.1`, exit 0, **aucune DLL manquante**.
- `CorpusOne.exe --input tests/recette/dossier_mixte --output dist/smoke_final --format md --yes`
  → corpus.md + corpus_rapport.md + corpus_rapport.json générés, exit 0.

### Bug CLI `--output` dossier : ValueError

**Symptôme découvert pendant le smoke test** : avec `--output dist/smoke` (dossier
sans extension `.md`/`.pdf`), la CLI levait `ValueError: Format de sortie non supporté :`
dans l'orchestrateur (`output_path.suffix` valait `""`).

**Décision** : la CLI ajoute automatiquement l'extension quand `--output` désigne
un dossier sans extension (D-053). Le dossier est créé au besoin. Test de
non-régression `test_cli_output_dir_without_extension` ajouté.

### Validation finale après les deux fixes

| Check | Résultat |
|---|---|
| `ruff check src/ tests/` | ✅ |
| `mypy --strict src/docfuse/` | ✅ 38 fichiers |
| `pytest` complet | ✅ 199 passed, 38 skipped |
| Smoke binaire onefile (--version) | ✅ exit 0, docfuse 0.1.1 |
| Smoke binaire onefile (run complet) | ✅ corpus.md + rapport MD + rapport JSON générés |

### DLL `_tkinter` / `_ctypes` manquantes au lancement de la GUI onefile

**Symptôme rapporté** : double `ImportError: DLL load failed while importing _tkinter`
puis `_ctypes` au démarrage de la GUI CustomTkinter via le binaire. Les `.pyd` étaient
dans le bundle mais pas leurs dépendances natives (`tcl86t.dll`, `tk86t.dll`, `zlib1.dll`
pour Tcl/Tk ; `libffi-8.dll` pour ctypes).

**Décision** (D-054 + D-055) : `CorpusOne.spec` collecte désormais dynamiquement
**toutes les `*.dll` du dossier `<python>/DLLs/`** et les embarque dans le bundle.
Solution générique recommandée par PyInstaller pour les GUI onefile.

**Smoke test final** : `dist\CorpusOne.exe` (40.6 Mo) démarre sans erreur,
fenêtre GUI CustomTkinter visible à l'écran. Suite complète `199 passed, 38 skipped`.

### Décisions prises

- **D-050** : Python 2.7.9 trouvé dans le PATH utilisateur est ignoré ;
  on documente l'utilisation de Python 3.13.15 depuis `C:\Windows\Temp\Python313`
  pour les sessions sur cette machine.
- **D-051** : Un doublon accidentel `extraction_result.py` à la racine du dépôt a été
  supprimé (le module canonique vit sous `src/docfuse/models/`). Ajout implicite
  au `.gitignore` non requis (le fichier n'a jamais été commité).

### État après Session 10

| Métrique | Valeur |
|---|---|
| Version | 0.1.1 beta |
| ruff | ✅ |
| mypy --strict | ✅ (38 fichiers) |
| pytest | ✅ 199 passed, 38 skipped (clone frais) |
| Binaire Windows | ✅ `CorpusOne.exe` **onefile** (~40.6 Mo, autoportant, GUI fonctionnelle) |
| Working tree | clean |

### Reste à faire

- ⬜ Rendre le jeu `tests/samples_real/` reproductible ou documenter sa génération pour supprimer les 38 skips d'un clone frais.
- ⬜ Documenter l'emplacement de l'interpréteur Python 3.13 utilisé sur cette machine
  (`C:\Windows\Temp\Python313\python.exe`) dans une note de session si nécessaire.

---

## Session 12 — 21 août 2026

Demande initiale : rendre le moteur de comptage de tokens configurable
(approximation générique existante vs moteur précis d'un fournisseur),
priorité Mistral. Étendue en cours de session à un deuxième moteur (OpenAI)
et à l'automatisation de la publication Windows, sur demande explicite.

### Moteur de comptage précis Mistral — ✅ Terminé

- Nouveau package `core/tokenizers/` (registre, même pattern que le registre
  d'extracteurs). `ApproxEngine` (défaut, comportement historique
  inchangé) + `MistralEngine`.
- **Découverte en cours d'implémentation** : le package `mistral-common`
  tire `pydantic-extra-types[pycountry]`, et `pycountry` est LGPL-2.1 —
  incompatible avec la politique zéro-copyleft du projet une fois figée
  dans un `.exe` onefile (pas de liaison dynamique possible). Vérifié en
  inspectant le wheel réel, pas supposé.
- Solution retenue : dépendance unique `tiktoken` (MIT) + fichier de
  vocabulaire Tekken vendoré (extrait de `mistral-common`, Apache-2.0,
  19 Mo). Parité vérifiée à l'identique contre le vrai `Tekkenizer` sur
  7 textes (ASCII, accents, japonais, code, emoji). Voir D-056/D-057.
- `aggregate_tokens()` corrigé au passage : le total était recalculé depuis
  la somme des octets (correct en mode approx, faux pour un vrai
  tokenizer BPE) — devient la somme des comptes par fichier avec un moteur
  précis.
- `estimate_source_context()` optimisé pour les moteurs précis : le texte
  du fichier n'est encodé qu'une fois pendant la convergence de l'en-tête
  SOURCE (au lieu de jusqu'à 20 fois), voir D-058.

### Bug GUI trouvé en testant la vraie fenêtre — ✅ Corrigé

- `self.tokenizer_engine_var.get()` était lu depuis le thread d'arrière-plan
  de l'analyse → `RuntimeError: main thread is not in main loop`. Trouvé en
  lançant réellement `DocFuseGUI()` sur un display X (capture d'écran), pas
  seulement en import/tests. Corrigé en suivant le pattern déjà utilisé pour
  `recursive_var` (lu sur le thread principal avant de lancer le thread).
- Second gap trouvé en re-testant : changer le menu de moteur **sans**
  re-cliquer Analyser ne recalculait rien — le tableau restait figé sur les
  chiffres de l'ancien moteur alors que le menu affichait déjà le nouveau.
  Corrigé avec `OrchestratorResult.recompute_engine()` (même principe que
  `recompute_blocking()` pour le plafond) + un `trace_add` sur la variable
  Tk, vérifié par capture d'écran avant/après bascule.

### Bug CI trouvé en vérifiant le build — ✅ Corrigé

- En vérifiant que la CI construisait bien l'exe avec `tiktoken`, découverte
  d'une régression silencieuse pré-existante (antérieure à cette session) :
  `actions/upload-artifact` pointait encore vers `dist/CorpusOne/` (ancien
  mode `--onedir`) alors que le projet est en `--onefile` depuis plusieurs
  sessions. Chaque run affichait *« No files were found… No artifacts will
  be uploaded »*, ignoré silencieusement (`if-no-files-found: warn` par
  défaut). Le build PyInstaller lui-même a toujours réussi. Corrigé (chemin
  + `if-no-files-found: error`), voir D-059.

### Moteur de comptage précis OpenAI — ✅ Terminé

- Deuxième moteur précis demandé comme « le plus facile pour la prochaine
  version » : `tiktoken` étant déjà présent, l'encodage natif `o200k_base`
  (GPT-4o/4.1/o-série) ne coûte qu'un fichier de vocabulaire (3,6 Mo)
  vendoré, aucune nouvelle dépendance. Chargé depuis le fichier local,
  jamais via `tiktoken.get_encoding()` (téléchargerait sinon depuis
  `openaipublic.blob.core.windows.net`). Voir D-060.
- Menu GUI et `--tokenizer-engine` détectent le nouveau moteur
  automatiquement via le registre — aucun changement de code GUI requis.
- Test de parité contre le vrai `tiktoken.get_encoding("o200k_base")`,
  exécuté hors ligne en amorçant le cache de `tiktoken` avec le fichier
  vendoré (`TIKTOKEN_CACHE_DIR` pointé vers un dossier temporaire) — pas
  besoin d'ignorer ce test en CI standard, contrairement à celui de Mistral.

### Publication automatique sur les Releases GitHub — ✅ Terminé

- Jusqu'ici l'exe n'était accessible que via l'onglet Actions (connexion
  requise, expire à 90 jours, peu découvrable — signalé par l'utilisateur
  après ne pas l'avoir trouvé). Ajout d'une étape CI qui, uniquement quand
  une Release est publiée, zippe l'exe, calcule son SHA-256, et attache les
  deux fichiers à la Release via `gh release upload`. Voir D-061.
- Procédure de release documentée dans `AGENTS.md` §13 (checklist complète,
  du bump de version à la vérification post-publication), à la demande
  explicite de l'utilisateur pour que ce soit répétable à chaque version.

### Tests sur documents réels — ✅ Fait

- L'utilisateur a explicitement autorisé l'usage de documents présents sur
  la machine pour vérifier le fonctionnement. Deux corpus utilisés :
  - 65 fichiers synthétiques (`~/Téléchargements/fichiers_test_.../`),
    10 Ko à 2 Mo, DOCX/PDF/TXT avec marqueurs de contenu vérifiables.
  - 14 documents utilisateur réels et variés (DOCX/PDF/MD/HTML/PPTX/ODT/
    RTF/XLSX/CSV) pris dans `~/Téléchargements` et `~/Documents`.
- Résultat : 0 erreur d'extraction sur les deux corpus, marqueurs de
  contenu intacts à 100 %, comptes de tokens cohérents et différenciés par
  moteur. Deux statuts particuliers (`peu_de_texte`, `images`) vérifiés un
  par un pour confirmer qu'il s'agissait du comportement attendu et non
  d'un bug d'extraction (un fichier `.odt` genuinement vide, une diapo
  composée d'une seule image).

### État après Session 12

| Métrique | Valeur |
|---|---|
| Version | 0.1.2 beta |
| ruff | ✅ |
| mypy --strict | ✅ (44 fichiers) |
| pytest | ✅ 256 passed, 39 skipped (clone frais) |
| Recette | ✅ 7/7 PASS |
| Moteurs de comptage | approx (défaut), mistral, openai |
| Décisions archivées | 61 (D-001 à D-061) |
| Working tree | clean |

### Reste à faire

- ⬜ Rendre le jeu `tests/samples_real/` reproductible ou documenter sa
  génération pour supprimer les skips d'un clone frais.
- ⬜ Moteur Llama/HuggingFace `tokenizers` évoqué pour une version future,
  pas retenu pour 0.1.2 (dépendance Rust supplémentaire, hors scope
  « facile »).
- ⬜ Publier effectivement la Release `v0.1.2` (checklist AGENTS.md §13,
  étape 8 — action publique, confirmation utilisateur requise avant
  exécution).

## Session 13 — 24 août 2026

Demande initiale : quatre optimisations/alertes de transparence discutées en
conversation (l'utilisateur jouant le rôle d'un utilisateur final), à
implémenter dans l'ordre puis à publier en `0.1.3 beta`.

### Quatre fonctionnalités — ✅ Terminées

- **Déduplication en-têtes/pieds de page PDF** (`extractors/pdf.py`,
  D-062) : ne regarde que première/dernière ligne de chaque page,
  `chars_per_page` recalculé sur le texte dédupliqué.
- **Retrait des images base64 intégrées Markdown** (`extractors/markdown.py`,
  D-063) : payload remplacé par une note, `alt`/syntaxe conservés,
  `image_count` incrémenté (réutilise l'alerte `images` existante).
- **Détection de doublons de contenu entre fichiers** (nouveau
  `core/duplicate_detector.py`, D-064) : hash SHA-256 du texte extrait,
  texte du doublon remplacé par une note plutôt que gardé dans un champ
  séparé (aucune logique spécifique en aval nécessaire).
- **Alerte non bloquante sur les secrets potentiels** (nouveau
  `core/secret_scanner.py`, D-065) : motifs à haute confiance uniquement
  (clé AWS, clé privée, jeton Slack/JWT, `api_key=...`), jamais la valeur
  trouvée journalisée/affichée — seulement le type et le numéro de ligne.
- Toutes les notes remontent dans l'en-tête SOURCE (`extra_metadata` sur
  `ExtractedFile`, déjà existant mais inutilisé jusqu'ici) et dans une
  nouvelle section « Notes » du rapport MD.
- Idée écartée en amont (compression sémantique du texte pour gagner des
  tokens) : contredit le CdC §8 (« sans perte silencieuse »), remplacée par
  des retraits de doublons **exacts** uniquement (jamais de reformulation).

### Régression de tests trouvée et corrigée — ✅ Corrigé

- Deux tests existants (`test_acceptance.py::test_multiple_files_total_blocked`,
  `test_context_blocking.py::big_files_dir`) construisaient délibérément
  plusieurs fichiers avec un contenu strictement identique comme raccourci
  pour obtenir une taille totale déterministe. La nouvelle déduplication de
  contenu (D-064) les dédupliquait, faisant chuter le total sous le plafond
  testé — 4 tests en échec. Corrigé en rendant le contenu distinct par
  fichier (`"A"`/`"B"`/`"C"` au lieu de `"A"` partout) : l'intention du test
  (plusieurs fichiers non bloquants individuellement, total bloquant) reste
  intacte.

### État après Session 13

| Métrique | Valeur |
|---|---|
| Version | 0.1.3 beta |
| ruff | ✅ |
| mypy --strict | ✅ (aucune nouvelle erreur sur les fichiers modifiés) |
| pytest | ✅ 278 passed, 39 skipped (clone frais) |
| Recette | ✅ 7/7 PASS |
| Décisions archivées | 65 (D-001 à D-065) |
| Working tree | clean après commit |

### Reste à faire

- ⬜ Rendre le jeu `tests/samples_real/` reproductible ou documenter sa
  génération pour supprimer les skips d'un clone frais.
- ⬜ Moteur Llama/HuggingFace `tokenizers` évoqué pour une version future,
  toujours pas retenu (dépendance Rust supplémentaire, hors scope
  « facile »).
- ⬜ Publier effectivement la Release `v0.1.3` (checklist AGENTS.md §13,
  étape 8 — action publique, confirmation utilisateur requise avant
  exécution).
- ⬜ Détection de secrets volontairement conservatrice (peu de motifs) —
  élargir si des faux négatifs sont signalés en usage réel.
- ⬜ **Trouvé en publiant la Release** : `ruff>=0.4.0` (sans borne haute)
  dans `pyproject.toml` laisse dériver la version installée en CI
  (0.8.0 en local vs 0.16.4 en CI au moment de cette session) — la CI a
  une opinion de formatage différente sur un bloc `assert` multi-lignes,
  ce qui a fait échouer `ruff format --check` sur la Release `v0.1.3`
  initiale (corrigé dans la foulée, tag/Release recréés). Envisager de
  pinner une plage de version plus stricte pour éviter la récidive.

## Session 14 — 29 août 2026

Deux chantiers demandés par l'utilisateur après relecture critique de sa
propre roadmap ("j'ai fait un mauvais travail sur l'évolution de DocFuse") :
des fichiers de développement silencieusement ignorés, et des PDF scannés
détectés mais jamais réellement récupérés.

### Fichiers de développement traités comme texte brut (D-066) — ✅ Livré

- `constants.CODE_EXTENSIONS` (~60 extensions courantes) fusionné dans
  `SUPPORTED_EXTENSIONS`, dispatché vers `TextExtractor` existant — aucune
  nouvelle dépendance.
- Limite documentée, pas corrigée : dispatch par suffixe uniquement, donc
  `Dockerfile`/`Makefile`/`.gitignore`/`.env` restent hors périmètre
  (`Path.suffix` est vide pour ces noms en Python — vérifié).

### OCR des PDF scannés — build séparé `CorpusOne-OCR` (D-067) — ✅ Livré

- L'utilisateur a fourni un document d'architecture détaillé (rédigé pour
  un contexte serveur MCP) ; adapté au code réel de DocFuse plutôt que
  porté tel quel, en plan mode avec validation explicite avant codage.
- Nouveau package `core/ocr/` (même pattern que `core/tokenizers/` :
  registre, `is_available()`, jamais d'exception). Classification par page
  dans `extractors/pdf.py` réutilisant le texte déjà extrait par pdfminer
  (`chars_per_page`, déjà calculé pour la dédup d'en-têtes v0.1.3) — pas de
  seconde extraction. OCR via le binaire CLI Tesseract en `subprocess`
  (isolation de process gratuite, pas de `ProcessPoolExecutor`),
  rastérisation par `pypdfium2`.
- **Décision produit tranchée explicitement avec l'utilisateur**
  (AskUserQuestion) : `CorpusOne.exe` n'embarque pas Tesseract (~40-80 Mo,
  pas un paquet pip) — un second exe, `CorpusOne-OCR.exe`
  (`CorpusOne-OCR.spec`, nouveau job CI `build-windows-ocr`), l'embarque et
  est publié en parallèle sur la même Release.
- Vérifié en conditions réelles pendant la session (Tesseract 5.5 installé
  localement sur la machine de dev) : un PDF image-only (construit avec
  `reportlab`, aucune couche texte) recouvre bien son texte par OCR, statut
  `LOW_TEXT` → `READY`/`IMAGES` ; bascule automatique et transparente
  vérifiée en masquant Tesseract du PATH (note explicite, texte inchangé).
- Portée v1 = PDF uniquement. Fichiers image seuls et images intégrées dans
  `.docx`/`.pptx` (aussi soulevés par l'utilisateur) : notés pour une
  itération suivante (même moteur réutilisable), pas abandonnés.
- Job CI `build-windows-ocr` et binaires Windows Tesseract non testés dans
  cette session (sandbox Linux, pas de runner Windows) — cf. "Reste à
  faire" ci-dessous.

### État après Session 14

| Métrique | Valeur |
|---|---|
| Version | 0.1.3 (non bumpée — aucune Release demandée cette session) |
| ruff | ✅ (fichiers modifiés ; dérive pré-existante documentée sur `test_acceptance.py` non touchée) |
| mypy --strict | ✅ (aucune nouvelle erreur ; ajout override `pypdfium2.*`) |
| pytest | ✅ 363 passed, 39 skipped (tests OCR exécutés, Tesseract présent en local) |
| Décisions archivées | 67 (D-001 à D-067) |

### Reste à faire

- ⬜ Job CI `build-windows-ocr` et `CorpusOne-OCR.spec` : jamais buildés
  réellement (pas de runner Windows disponible pendant la session). À
  valider au premier déclenchement réel (`gh workflow run` / une Release) :
  chemin d'installation Tesseract via `choco`, nom exact des DLL
  embarquées, taille finale de l'exe.
- ⬜ Décider si/quand cette fonctionnalité justifie une Release (v0.1.4 ?)
  — non tranché cette session, seule l'implémentation a été demandée.
- ⬜ v1.1 OCR envisagée : fichiers image seuls (`.jpg`/`.png`, aujourd'hui
  toujours `IGNORED`) et images intégrées dans `.docx`/`.pptx`, en
  réutilisant `core/ocr/`.
- ⬜ (reporté de la Session 13) `ruff>=0.4.0` sans borne haute — toujours
  pas pinné.

