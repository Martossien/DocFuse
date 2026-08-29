# Journal des décisions d'architecture — DocFuse / CorpusOne

> Historique des décisions techniques d'architecture et leur rationale.
> Mis à jour à chaque session. **Lire avant de modifier l'architecture.**

---

## Session 1 — 20 août 2026

### D-001 : Choix du langage — Python 3.11+

**Décision** : Implémenter DocFuse en Python 3.11+.

**Rationale** :
- L'écosystème d'extracteurs Python est de loin le plus complet et éprouvé : pdfminer.six (MIT), python-docx (MIT), python-pptx (MIT), openpyxl (MIT), beautifulsoup4 (MIT), striprtf (MIT), charset-normalizer (MIT), ReportLab (BSD).
- Recoder ces extracteurs en C# .NET coûterait des semaines de développement supplémentaire pour un résultat moins fiable.
- La lenteur de Python sur Windows concerne surtout le lancement ; avec PyInstaller `--onedir` (pas `--onefile`) et Tkinter-based GUI, le démarrage reste acceptable (< 3 s objectif CdC NFR-07).
- Le CdC autorise explicitement Python 3.11+ (§13.2).
- Critère de jugement : rapidité + portabilité + richesse d'écosystème. Python gagnant sur le 3e critère, acceptable sur les 2 premiers.

**Alternatives écartées** :
- C# .NET 8 self-contained : lancement très rapide, GUI native, mais moins de librairies d'extraction Office prêtes (parser XML ZIP à la main).
- Go + Fyne : binaire léger, lancement instantané, mais écosystème PDF/Office pauvre.

---

### D-002 : Choix de la GUI — CustomTkinter

**Décision** : Utiliser CustomTkinter (MIT) pour l'interface graphique.

**Rationale** :
- Le CdC demande une UI « non intimidante », pensée utilisateur métier, pas développeur (§6.1, §20).
- Tkinter (stdlib) a un rendu visuellement daté (widgets Windows 95) — non conforme à l'exigence UX.
- CustomTkinter est un wrapper moderne de Tkinter : coins arrondis, dark mode natif, thème cohérent, widgets modernes (boutons, tableaux, barres de progression). Rendu 2026.
- Licence MIT → compatible Apache 2.0.
- Zéro dépendance C++ externe (contrairement à PySide6/Qt qui exige liaison dynamique LGPL).
- Lancement instantané (pas de runtime lourd).
- Alternative Dear PyGui (MIT) écartée : moins standard, écosystème plus petit, moins de documentation.

**Alternatives écartées** :
- Tkinter brut : rendu daté, non conforme UX.
- PySide6/Qt : LGPL impose liaison dynamique, complexité d'empaquetage, taille importante.
- Dear PyGui : moins mature, moins documenté.
- Flet (Flutter) : dépendance lourde, lancement potentiellement lent.

---

### D-003 : CLI avec argparse (stdlib)

**Décision** : Utiliser argparse (stdlib) pour la CLI, pas de bibliothèque externe.

**Rationale** :
- Le CdC (§6.3) spécifie des flags simples et bien définis : `--input`, `--output`, `--format`, `--context`, `--margin`, etc.
- argparse gère tout cela nativement, sans dépendance.
- `click` (BSD-3) est plus ergonomique mais ajoute une dépendance pour un gain marginal.
- Objectif : minimiser le nombre de dépendances pour la maintenabilité et la portabilité.

---

### D-004 : Parallélisation — ThreadPoolExecutor + queue de progression

**Décision** : Extraction parallèle des fichiers via `ThreadPoolExecutor`, avec une queue thread-safe pour la progression GUI.

**Rationale** :
- L'extraction de texte est IO-bound (lecture de fichiers, parsing XML) → les threads Python sont adaptés (GIL relâché sur IO).
- `ThreadPoolExecutor` avec un nombre de workers borné (CPU-1 ou fixe, ex. 4) évite l'épuisement mémoire.
- Progression par fichier : chaque thread émet un `ProgressEvent` (chemin, statut, tokens) dans une `queue.Queue()` thread-safe. La GUI ou la CLI consomme cette queue pour mettre à jour l'affichage en temps réel.
- Bouton « Arrêter » (GUI) / Ctrl+C (CLI) : un `threading.Event` partagé signale l'annulation à tous les threads.
- Le CdC (§13.3) demande « extraction parallèle (fichiers, pas les pages) bornée CPU-1 ».
- Le CdC (§17) demande une progression par fichier au minimum.

---

### D-005 : Architecture interne — approche directe (pas de modèle unifié type Docling)

**Décision** : Ne pas implémenter de modèle de document unifié type `DoclingDocument`. Chaque extracteur retourne directement un `ExtractedFile` (dataclass) contenant le texte, les métadonnées, le compteur d'images, le statut. Les writers consomment directement.

**Rationale** :
- Docling utilise un modèle unifié `DoclingDocument` puis des exporters Markdown/JSON. C'est élégant mais overkill pour DocFuse :
  - DocFuse n'a qu'un seul type de sortie par extraction (texte concaténé pour MD ou PDF).
  - Pas besoin de round-trip document → modifier → re-export.
  - Le modèle unifié ajoute une couche d'abstraction et de la maintenance supplémentaire.
- Approche directe : `Extractor.extract(path) -> ExtractedFile` → `MarkdownWriter.write(files) -> .md` ou `PdfWriter.write(files) -> .pdf`.
- Plus maintenable, moins de couches, code plus lisible.
- Si un jour il faut un modèle unifié (ex. pour préserver la structure des tableaux), on l'ajoutera en v2.

**Alternatives écartées** :
- Modèle unifié Docling-style : trop complexe pour v1, pas de besoin identifié.

---

### D-006 : PDF lecture — pdfminer.six + pypdf (sans pdfplumber)

**Décision** : Utiliser pdfminer.six (MIT) pour l'extraction de texte page-par-page et la détection d'images, et pypdf (BSD-3) pour l'inventaire des pages, métadonnées et détection d'encryption. Pas de pdfplumber.

**Rationale** :
- pdfminer.six fournit `extract_pages()` (générateur de `LTPage`) qui permet :
  - D'extraire le texte de chaque page individuellement (anti-perte, CdC §8.3).
  - De détecter les images embarquées (`LTImage` dans l'arbre `LTPage`, `LTFigure` pour les XObjects Form).
  - De compter les caractères par page (heuristique scan, CdC §9.2).
- pypdf est plus rapide pour l'inventaire (nombre de pages, métadonnées, détection encryption/mot de passe).
- pdfplumber (MIT) est une couche au-dessus de pdfminer.six — ajoute une dépendance pour un gain marginal (détection de tableaux). Les tableaux PDF ne sont pas dans le périmètre v1 (CdC §14.3 mentionne « optionnel v1.1 »).
- Garder le code léger : 2 dépendances PDF suffisent.

**Alternatives écartées** :
- pdfplumber : dépendance supplémentaire non indispensable en v1.
- PyMuPDF (fitz) : AGPL-3.0, interdit par le CdC (NFR-06).
- Poppler : GPL, interdit.

---

### D-007 : RTF — striprtf (MIT)

**Décision** : Utiliser la bibliothèque `striprtf` (MIT) pour l'extraction RTF, plutôt qu'un parser maison.

**Rationale** :
- Le RTF est un format complexe (groupes de contrôle imbriqués, tables, encodages). Un parser maison serait fragile.
- `striprtf` est une bibliothèque MIT simple et éprouvée.
- Licence MIT → compatible Apache 2.0.

---

### D-008 : PDF écriture — ReportLab (BSD)

**Décision** : Utiliser ReportLab (BSD) pour générer le PDF de sortie.

**Rationale** :
- Le CdC (§11.2) recommande ReportLab (BSD) ou fpdf2.
- ReportLab est mature, supporte les polices Unicode embarquées (DejaVu, Noto), les sauts de page, les en-têtes de page.
- Licence BSD → compatible Apache 2.0.
- Interdit : WeasyPrint (dépendances système), appel Word/LibreOffice.

**Polices** : Embarquer DejaVu Sans (licence SIL/OFL, libre, Unicode complet) ou Noto Sans. Pas de dépendance à Arial (restriction Windows).

---

### D-009 : Encodage — charset-normalizer (MIT)

**Décision** : Utiliser `charset-normalizer` (MIT) pour la détection d'encodage des fichiers texte.

**Rationale** :
- Le CdC (§14.5) recommande charset-normalizer plutôt que chardet (LGPL → à éviter).
- Pour les fichiers `.txt` : ordre de tentative BOM → UTF-8 → charset-normalizer → cp1252 → latin-1 en dernier (CdC §7.2).
- Licence MIT → compatible.

---

### D-010 : Tests — pytest + tests d'acceptation du CdC §19

**Décision** : Utiliser pytest (MIT) avec une structure de tests en trois niveaux :
1. Tests unitaires par extracteur (un fichier de test par format).
2. Tests unitaires du core (context_counter, inventory, image_detector, orchestrator).
3. Tests d'acceptation du CdC §19 (portabilité, fonctionnels, licence, i18n).

**Rationale** :
- pytest est le standard Python, MIT, riche en fixtures.
- Tests d'acceptation obligatoires car le CdC dit « le livrable est refusé si un cas échoue » (§19).
- Tests réseau coupé : un test qui bloque tout accès réseau et vérifie qu'aucune lib ne tente de se connecter (NFR-02).

---

### D-011 : CI — GitHub Actions (ruff + mypy + pytest)

**Décision** : Workflow GitHub Actions avec matrix Python 3.11/3.12/3.13 × windows-latest/ubuntu-latest.

**Steps** :
1. `ruff check` — lint
2. `ruff format --check` — format
3. `mypy --strict` — type checking
4. `pytest` — tests
5. `pip-licenses` — vérification absence GPL/AGPL

**Rationale** :
- Le CdC exige des tests sur Windows (§19.1 portabilité Windows). Ubuntu pour la vitesse de CI et le coût.
- `mypy --strict` garantit le typage complet (règle critique #6).
- `pip-licenses` automatise la vérification licence (règle critique #1).

---

### D-012 : i18n — catalogue JSON (FR + EN)

**Décision** : Catalogues i18n en fichiers JSON (`i18n/fr.json`, `i18n/en.json`), chargés au runtime.

**Rationale** :
- Le CdC (§15) demande : FR complet en v1, EN amorcé, ajout d'une langue = ajout d'un fichier sans rebuild.
- JSON plutôt que gettext (.po) : plus simple, plus lisible, chargement runtime trivial, pas de compilation.
- Toutes les chaînes UI, CLI et rapport utilisateur passent par `i18n.t("key")`.
- Le contenu extrait n'est jamais traduit.
- Formats nombres : espaces insécables FR (`96 830`).

---

### D-013 : Configuration — JSON 3 niveaux (exe / APPDATA / défauts)

**Décision** : Configuration JSON chargée dans l'ordre (le premier trouvé gagne, puis fusion avec les défauts) :
1. Fichier `CorpusOne.json` à côté de l'exe (priorité portable / clé USB).
2. `%APPDATA%\CorpusOne\config.json` (si le dossier de l'exe n'est pas inscriptible).
3. Valeurs par défaut compilées dans `constants.py`.

**Écriture** : Même endroit d'où la conf a été lue ; si lecture seule → fallback `%APPDATA%\CorpusOne\`.

**Rationale** :
- Le CdC (§5.2) spécifie cet ordre exact.
- Pas de HKLM, pas de Program Files, pas de services (NFR-01).
- HKCU autorisé en option mais pas obligatoire — préférer le JSON (lisible, portable, sauvegardable).

---

### D-014 : En-tête SOURCE — format Markdown avec séparateur `---`

**Décision** : Chaque fichier du corpus est encadré par un en-tête de provenance au format :

```markdown
---
## SOURCE: rapports/2024/contrat.docx
- type: docx
- taille_octets: 184320
- pages_ou_diapos: 12
- tokens_estimes: 4200
- tokens_avec_marge: 4830
- images: 4
- alerte: images
---

…texte extrait…

```

**Rationale** :
- Le CdC (§8.2) spécifie ce format exact.
- Inspiré de files-to-prompt (séparateur `---` + en-tête provenance) et de MarkItDown (métadonnées structurées).
- Ces métadonnées **comptent** dans le compteur de contexte (elles vont au LLM).
- Backticks adaptatifs pour le contenu (inspiré de files-to-prompt) : si le contenu contient ```` ``` ````, on augmente le nombre de backticks pour ne pas casser le bloc.

---

### D-015 : Registration automatique des extracteurs — décorateur @register

**Décision** : Chaque extracteur s'enregistre automatiquement via un décorateur `@register` sur la classe. Le registre est un dictionnaire `{extension: [extractor_classes]}` avec tri par priorité.

**Rationale** :
- Inspiré de MarkItDown (`ConverterRegistration` avec priorité, `_markitdown.py:86`).
- Un extracteur = un fichier Python. L'import du module déclenche l'enregistrement.
- Plus maintenable : pas de liste manuelle à tenir à jour. Ajouter un format = créer un fichier + le décorateur.
- Dispatch : pour un fichier donné, le registre cherche l'extension → liste d'extracteurs triés par priorité → premier `accepts()` qui retourne True gagne.
- Permet des plugins futurs (ex. OCR) avec priorité plus forte.

---

### D-016 : Pas de modèle ML ni de Magika

**Décision** : Ne pas utiliser Magika (détection de type par ML) contrairement à MarkItDown.

**Rationale** :
- Magika (Apache-2.0) est compatible licence, mais ajoute une dépendance lourde (modèle ML) incompatible avec l'objectif « exe léger hors-ligne ».
- DocFuse se fie à l'extension du fichier (liste blanche). Si l'extension est inconnue → fichier ignoré + rapport.
- Le CdC (§7.1) spécifie une liste blanche d'extensions — pas de besoin de détection de contenu.
- Gain de simplicité et de taille d'exe.

---

### D-017 : Pas de mammoth pour DOCX — python-docx direct

**Décision** : Utiliser `python-docx` (MIT) directement pour DOCX, pas `mammoth` (qui convertit en HTML intermédiaire).

**Rationale** :
- MarkItDown utilise mammoth (Word→HTML→Markdown) car il veut du Markdown riche (titres, listes, tableaux).
- DocFuse veut le **texte intégral** sans perte (CdC §8.3 « Interdit de nettoyer trop agressivement »). python-docx donne accès à : paragraphes, tableaux, headers/footers, footnotes, endnotes, zones de texte — tout ce qui est demandé.
- Approche directe : python-docx → texte structuré → writer. Pas de couche HTML intermédiaire.
- Une dépendance de moins.

**Alternatives écartées** :
- mammoth : boucle HTML intermédiaire inutile, dépendance supplémentaire.

---

### D-018 : Empaquetage — PyInstaller --onedir

**Décision** : Empaqueter avec PyInstaller `--onedir` (pas `--onefile`).

**Rationale** :
- `--onefile` décompresse l'exe à chaque lancement → démarrage lent (CdC NFR-07 : < 3 s).
- `--onedir` garde les fichiers décompressés dans `_internal/` → démarrage rapide.
- Le CdC (§5.1) accepte le onedir si le onefile ralentit trop.
- Structure de livraison : `CorpusOne.exe` + `_internal/` (runtime non documenté).
- PyInstaller est GPL mais avec une exception explicite pour les projets qui l'utilisent comme outil de build — pas de contamination de licence du code produit.

---

### D-019 : Structure du code — src layout

**Décision** : Utiliser le layout `src/docfuse/` (pas un package à la racine).

**Rationale** :
- Le `src layout` évite l'import accidentel du package depuis le répertoire de travail pendant les tests (force `pip install -e .`).
- Standard Python moderne recommandé par PyPA.
- `pyproject.toml` à la racine, package dans `src/`.

---

### D-020 : Compteur de contexte — formule unique générique

**Décision** : Estimateur unique : `tokens_estimes = ceil(octets_utf8 / 4)`, `tokens_avec_marge = ceil(tokens_estimes * (1 + margin))`, margin = 0.15 par défaut.

**Rationale** :
- Le CdC (§10.1) impose cette formule exacte.
- Approximation publique (~4 octets/token) largement utilisée. La marge +15 % couvre la variance.
- Pas d'API, pas de tiktoken embarqué. L'UI dit « compteur générique », pas « tokens GPT ».
- Les métadonnées des en-têtes SOURCE **comptent** dans le total (CdC §8.2).

---

## Session 2 — 20 août 2026 — Audit et corrections

### D-021 : Police PDF Unicode — DejaVu Sans (SIL/OFL)

**Décision** : Embarquer la police DejaVu Sans (TTF) dans `src/docfuse/assets/` et l'enregistrer via `pdfmetrics.registerFont(TTFont(...))` dans ReportLab.

**Rationale** :
- Le CdC §8.4 exige une police Unicode embarquée (DejaVu/Noto, licence SIL/OFL), pas Arial ou Helvetica.
- ReportLab utilise Helvetica (Type1 standard) qui ne supporte pas l'Unicode complet → accents au-delà de Latin-1, CJK, emojis corrompus.
- DejaVu Sans est libre (SIL Open Font License), Unicode complet, ~300 Ko par variant.
- Fallback sur Helvetica si les TTF sont absants (non blocant).

### D-022 : i18n généralisée à tous les modules (CLI, rapport, orchestrator)

**Décision** : Toutes les chaînes visibles de `cli.py`, `report.py`, `orchestrator.py` passent par `t()` du catalogue i18n.

**Rationale** :
- Le CdC §15 et la règle critique #5 exigent que **toutes** les chaînes UI, CLI, rapport passent par le catalogue.
- Auparavant, seul `gui.py` utilisait `t()`. La CLI et les rapports avaient des chaînes en dur en français.
- Maintenant `set_language()` est appelé avant `build_parser()` → les `help=` du parser argparse sont traduits.

### D-023 : Dry-run génère un rapport (CdC §19.2)

**Décision** : En mode `--dry-run`, le rapport MD + JSON est écrit même si aucun corpus n'est généré.

**Rationale** :
- Le CdC §19.2 exige « CLI --dry-run → pas de corpus, rapport stats ».
- Auparavant, dry-run affichait des stats sur stdout mais n'écrivait aucun rapport.

### D-024 : --include-ext et --report implémentés

**Décision** :
- `--include-ext` surcharge la liste blanche d'extensions (passé à `scan_directory(extensions=...)`).
- `--report` permet de spécifier un chemin personnalisé pour le rapport (au lieu de `output_stem_rapport.md`).

**Rationale** :
- Ces flags étaient définis dans argparse mais ignorés. Le CdC §6.3 les spécifie explicitement.

### D-025 : Seuils de scan passés depuis la config (C-08)

**Décision** : `run_analysis()` accepte un paramètre `scan_config` qui contient les seuils (`min_chars_file`, `min_chars_per_page`, `sparse_page_chars`, `sparse_page_ratio`). Ces seuils sont passés à `determine_status()`.

**Rationale** :
- Le CdC §9.2 et §12 spécifient que ces seuils sont configurables.
- Auparavant, `determine_status()` était appelée sans les seuils de la config → les modifications de l'utilisateur n'avaient aucun effet.

### D-026 : En-tête de page PDF (CdC §11.2)

**Décision** : Le PDF de sortie inclut un en-tête de page avec « Corpus DocFuse » à gauche et « Page N » à droite, via une fonction `onFirstPage`/`onLaterPages` callback de `SimpleDocTemplate.build()`.

**Rationale** :
- Le CdC §11.2 exige « En-tête de page : nom du corpus + n° de page ».

### D-027 : __main__.py dispatche vers GUI si pas d'arguments (C-11)

**Décision** : `python -m docfuse` sans arguments lance la GUI. Avec arguments → CLI.

**Rationale** :
- Le CdC §2.1 et §6.1 exigent que double-cliquer sur l'exe lance la GUI, pas une console noire.
- `__main__.py` détecte `len(sys.argv) <= 1` → `gui.launch()`, sinon `cli.main()`.

### D-028 : Sortie par défaut dans CorpusOne_output/ (I-13)

**Décision** : Le corpus de sortie est écrit dans un sous-dossier `CorpusOne_output/` du dossier source (pas directement dans le dossier source).

**Rationale** :
- Le CdC §5.3 spécifie « Défaut GUI : sous-dossier CorpusOne_output\ dans le dossier source ».

### D-029 : Profondeur max configurable via JSON (I-04)

**Décision** : Ajout du champ `max_depth: int = 12` dans `Config`, fusionné depuis le JSON. Passé à `scan_directory(max_depth=...)`.

**Rationale** :
- Le CdC §16 spécifie « profondeur max configurable, défaut 12 ».

### D-030 : Validation min/max de la config (I-17)

**Décision** : Ajout d'une méthode `Config.validate()` qui vérifie les bornes (ex: `context_limit >= 1`, `0 <= margin <= 10`, `sort in ('name','mtime','type')`, `0 <= sparse_page_ratio <= 1`).

**Rationale** :
- Le CdC §12 exige « Validation : types et min/max ; message clair si JSON cassé ».

### D-031 : Images pures — message spécifique au rapport (I-22)

**Décision** : Les fichiers d'images pures (`.jpg`, `.png`, etc.) sont ignorés avec le message « Fichier image, OCR désactivé, non inclus » au lieu du message générique « Extension non supportée ».

**Rationale** :
- Le CdC §7.4 exige « Une image seule = ignorée + ligne de rapport "fichier image, OCR désactivé, non inclus" ».

### D-032 : HTML — ordre du document respecté (I-18)

**Décision** : L'extracteur HTML parcourt le DOM séquentiellement (`body.descendants`) au lieu d'extraire les titres, puis les images, puis les tableaux séparément.

**Rationale** :
- L'ancienne approche perdait l'ordre d'apparition des éléments. Un tableau entre deux paragraphes était déplacé en fin de document.
- Le CdC §8.3 exige de respecter la structure du document.

### D-033 : Fichiers de rapport exclus de l'inventaire (I-05)

**Décision** : Les patterns `*_rapport.md` et `*_rapport.json` sont ajoutés à `IGNORE_PATTERNS` pour éviter que les rapports générés par DocFuse ne soient réingérés dans le corpus.

**Rationale** :
- Le CdC §7.5 exige que les fichiers de sortie CorpusOne soient exclus de l'inventaire.

### D-034 : CSV — délimiteur `;` supporté (M-05)

**Décision** : L'extracteur CSV détecte si la première ligne contient `;` et utilise ce délimiteur (fréquent en français).

### D-035 : file_type spécifique par extension (M-08)

**Décision** : Les extracteurs ODF et XML/JSON utilisent `path.suffix.lstrip(".")` comme `file_type` au lieu d'un type générique (`"odf"`, `"xml_json"`).

**Rationale** : L'en-tête SOURCE doit afficher `type: odt` au lieu de `type: odf`, `type: yaml` au lieu de `type: xml_json`.

---

## Session 4 — 20 août 2026 — GUI, log, CRLF, sort, DOCX, PDF

### D-036 : GUI refonte complète — recalcul plafond sans ré-extraction

**Décision** : La GUI conserve les `estimates` en cache après la première analyse. Quand l'utilisateur modifie le plafond, on recalcule `is_blocked` avec `check_limit(total, new_limit)` sans ré-extraire les fichiers.

**Rationale** :
- CdC §10.3 : « champs plafond éditable → recalcul immédiat sans ré-extraire si les textes sont en cache mémoire ».
- Les textes extraits et les `TokenEstimate` par fichier sont dans `result.files` et `result.estimates` → pas besoin de ré-exécuter l'orchestrator.

### D-037 : GUI jauge couleur dynamique

**Décision** : La `CTkProgressBar` change de couleur selon le ratio tokens/limit :
- Vert (`#22c55e`) si < 80 %
- Orange (`#f97316`) si 80-99 %
- Rouge (`#ef4444`) si ≥ 100 %

**Rationale** :
- CdC §6.1 : « Jauge. Vert / orange (> 80 %) / rouge (≥ 100 % → bloqué) ».

### D-038 : Log fichier avec rotation (CdC §18)

**Décision** : Ajout d'un `RotatingFileHandler` vers `%TEMP%/CorpusOne/corpusone.log`, rotation 2 Mo, 1 backup. Le log ne contient que les chemins et erreurs, jamais le contenu des documents.

**Rationale** :
- CdC §18 : « fichier %TEMP%\CorpusOne\corpusone.log rotation 2 Mo, sans contenu des documents ».

### D-039 : CRLF support dans markdown_writer

**Décision** : `write_markdown_corpus()` accepte un paramètre `line_ending: str = "lf"` qui peut être `"crlf"` pour Windows.

**Rationale** :
- CdC §11.1 : « LF ou CRLF (conf, défaut CRLF sous Windows) ».

### D-040 : Config sort — name | mtime | type

**Décision** : `scan_directory()` accepte un paramètre `sort` qui contrôle le tri :
- `name` (défaut) : tri naturel insensible à la casse
- `mtime` : tri par date de modification décroissante
- `type` : tri par extension puis nom

**Rationale** :
- CdC §8.1 : « Option conf : sort: name | mtime | type (défaut name) ».

### D-041 : DOCX zones de texte (w:txbxContent)

**Décision** : Ajout de `_extract_textboxes()` qui parse `word/document.xml` avec BeautifulSoup pour trouver les tags `w:txbxContent` et extraire leur texte.

**Rationale** :
- CdC §8.3 : « DOCX : Body, tableaux, headers/footers, footnotes, endnotes, zones de texte ».
- python-docx n'expose pas les text boxes → parsing XML manuel nécessaire.

### D-042 : Récursion PDF figures profonde

**Décision** : `_count_images_in_figure()` utilise maintenant une récursion véritable qui descend dans tous les `LTFigure` enfants, peu importe la profondeur.

**Rationale** :
- M-02 : L'ancienne version ne descendait que d'un niveau. Les figures profondément imbriquées (>2 niveaux) n'étaient pas explorées.

---

## Session 8 — 20 août 2026 — Sélection exacte et maîtrise du corpus

### D-043 : Une sélection d'entrée explicite partagée par toutes les interfaces

**Décision** : Introduire `InputSelection`, modèle immuable utilisé par la GUI, la CLI
et l'orchestrateur. Il normalise et déduplique les chemins, conserve les exclusions
utilisateur et détermine le dossier de sortie à partir de la première source.

**Rationale** :
- La GUI transformait auparavant un dépôt de fichiers en dossier parent, ce qui ajoutait
  silencieusement des documents non choisis.
- La CLI acceptait `--input` plusieurs fois mais n'analysait que la première valeur.
- Une source de vérité commune évite que les trois interfaces divergent à nouveau.

### D-044 : Inventaire multi-sources avec provenance unique

**Décision** : `run_analysis()` accepte un fichier, un dossier, une séquence de chemins
ou une `InputSelection`. L'inventaire agrège toutes les sources, élimine les doublons et
produit un `relative_path` lisible et unique. Un fichier sélectionné explicitement n'est
jamais élargi à son dossier parent.

**Rationale** :
- Conforme au CdC §2.3 et §6.2 : « Fichiers multiples → liste figée ».
- Les en-têtes `SOURCE` doivent rester non ambigus lorsque deux dossiers contiennent un
  fichier de même nom.
- Les fichiers explicitement choisis mais non supportés restent listés dans le rapport.

### D-045 : Retrait instantané sans ré-extraction

**Décision** : Chaque ligne de la GUI possède une action « Retirer ». Le retrait supprime
le fichier et son estimation du résultat en cache, recalcule le total et le blocage, puis
persiste dans `InputSelection.excluded_files` pour les analyses suivantes de la session.

**Rationale** :
- Le message de blocage du CdC propose explicitement de retirer des fichiers.
- L'utilisateur peut s'appuyer sur l'estimation de tokens par document pour décider.
- Ré-extraire tous les documents après chaque retrait serait lent et inutile.

### D-046 : Séparer statut d'extraction et statut de blocage

**Décision** : `OrchestratorResult` conserve le statut d'analyse original de chaque
fichier. `TOO_LARGE` reste un état d'affichage dérivé du plafond et ne détruit plus les
alertes `IMAGES` ou `LOW_TEXT`. Le changement du plafond dans la GUI déclenche un recalcul
immédiat à partir du cache.

**Rationale** :
- L'ancien recalcul restaurait systématiquement `READY`, ce qui faisait disparaître des
  alertes importantes après une modification du plafond.
- Le compteur, le blocage et les warnings doivent avoir chacun une source de vérité.

---

*Fin du journal des décisions — Session 8.*

---

## Session 9 — 20 août 2026 — Stabilisation de la GUI et beta 0.1.1

### D-047 : Les ajouts GUI sont cumulatifs et l'inventaire est progressif

**Décision** : Les actions « Ajouter des fichiers… » et « Ajouter un dossier… »
complètent la sélection existante au lieu de la remplacer. Lors du parcours d'un dossier,
chaque fichier inventorié est immédiatement affiché avec un état d'attente avant son
extraction.

**Rationale** :
- Une sélection successive doit être prévisible : choisir un second fichier ne doit pas
  faire disparaître le premier.
- L'affichage progressif rend explicite le contenu réellement retenu dans un dossier et
  évite de confondre un traitement en cours avec un échec silencieux.

### D-048 : Le compteur canonique porte sur les octets des blocs SOURCE

**Décision** : L'estimation de chaque source utilise les octets UTF-8 normalisés de son
en-tête `SOURCE` et de son contenu. Comme l'en-tête contient lui-même l'estimation, sa
valeur est calculée jusqu'au point fixe. Le total additionne les octets des sources puis
applique une seule fois `ceil(octets / 4)` et la marge configurée.

**Rationale** :
- Évite une variation lorsque le nombre de chiffres inscrit dans l'en-tête change.
- Évite le léger surcomptage provoqué par l'addition de valeurs déjà arrondies et déjà
  majorées fichier par fichier.
- Respecte directement la formule contractuelle du CdC sur l'ensemble des sources.

### D-049 : Les extracteurs dynamiques sont déclarés au build PyInstaller

**Décision** : `CorpusOne.spec` collecte explicitement tous les sous-modules de
`docfuse.extractors`. Un test de régression vérifie la présence de cette déclaration.

**Rationale** :
- Le registre charge les extracteurs avec `import_module`, ce que l'analyse statique de
  PyInstaller ne découvre pas automatiquement.
- Sans imports cachés, l'exécutable démarrait et inventoriait les fichiers, mais échouait
  au début de l'extraction.

---

## Session 10 — 20 août 2026 — Reprise après commit 0.1.1

### D-050 : Python 2.7.9 du PATH utilisateur ignoré, Python 3.13.15 utilisé

**Décision** : Sur la machine de développement, `C:\Python27\python.exe` (2.7.9)
demeure le `python` par défaut du PATH utilisateur mais est **ignoré**. Les commandes
de validation, les tests et le développement utilisent `C:\Windows\Temp\Python313\python.exe`
(Python 3.13.15) qui satisfait la contrainte `requires-python = ">=3.11"`.

**Rationale** :
- Le projet requiert Python ≥ 3.11 (cf. `pyproject.toml`) ; Python 2.7.9 ne peut pas
  exécuter `mypy --strict`, `ruff`, ou importer `customtkinter`.
- Le clonage d'un Python récent dans `C:\Windows\Temp` est cohérent avec le caractère
  portable et sans droits admin de DocFuse : pas d'installation système, pas
  d'UAC, juste un interpréteur portable.
- Cette note est consignée dans `AGENTS.md` (section « Python utilisé sur cette machine »).

### D-051 : Suppression d'un doublon accidentel `extraction_result.py` à la racine

**Décision** : Le fichier `extraction_result.py` (87 lignes, identique au bit près à
`src/docfuse/models/extraction_result.py`) détecté en **untracked** lors de la
reprise a été supprimé. Le module canonique vit sous `src/docfuse/models/` et est
le seul importé par le code.

**Rationale** :
- Un `fc.exe` binaire a confirmé l'égalité parfaite : c'est un copier-coller accidentel.
- Le module n'est pas référencé par `pyproject.toml` ni par aucun import ; sa présence
  à la racine n'apportait rien et pouvait laisser penser qu'il était un point d'entrée.
- Aucune ligne supprimée n'avait été committée (le fichier était untracked), donc
  aucun commit de nettoyage n'est nécessaire.

### D-052 : Binaire Windows en mode `--onefile` (un seul .exe autoportant)

**Décision** : `CorpusOne.spec` passe du mode `--onedir` (exe + dossier `_internal/`
contenant `python313.dll`, `python3.dll`, `VCRUNTIME140.dll`, etc.) au mode
**`--onefile`** : un unique `CorpusOne.exe` (~35.9 Mo) embarque la runtime Python
et toutes les dépendances. Plus de dossier `_internal/` distribué.

**Rationale** :
- L'utilisateur a constaté que déplacer `CorpusOne.exe` seul provoquait un message
  Windows « DLL Python 3.13 manquante » : c'est le symptôme classique d'un build
  `--onedir` mal distribué (le `.exe` n'est pas autoportant, il a besoin de ses
  voisines dans `_internal/`).
- Le CdC §5.1 prévoit explicitement l'option privilégiée d'un `.exe` unique
  (cf. `corpusone/CorpusOne.exe ← seul fichier visible indispensable`) ; l'option
  `--onedir` n'était mentionnée que comme alternative acceptable en cas de
  ralentissement rédhibitoire au démarrage.
- Le coût au démarrage d'un `--onefile` (extraction du bundle dans `%TEMP%`) est
  acceptable pour un outil de génération de corpus qui n'est pas lancé en boucle.
- Le binaire reste portable : un seul fichier à copier sur clé USB, par mail, etc.

**Changements techniques dans le spec** :
- `EXE(..., exclude_binaries=True, [], ...)` + bloc `COLLECT(exe, a.binaries, a.datas, ...)`
  → `EXE(..., a.scripts, a.binaries, a.datas, [], ...)` sans bloc `COLLECT`.
- Le `[]` final dans `EXE(...)` est le paramètre `icon` (laissé par défaut).

### D-053 : La CLI ajoute automatiquement l'extension quand `--output` est un dossier

**Décision** : Dans `src/docfuse/cli.py`, la branche « --output fourni mais sans
extension `.md`/`.pdf` » traite désormais le chemin comme un **dossier de sortie**
et y écrit `corpus.md` (ou `corpus.pdf`), en créant le dossier au besoin.

**Rationale** :
- Avant : si l'utilisateur passait `--output dist/smoke` (dossier, sans extension),
  `output_path.suffix.lower()` valait `""`, l'orchestrateur levait
  `ValueError: Format de sortie non supporté : `.
- Le cas « --output désigne un dossier » est légitime : on veut y placer le corpus
  sans avoir à choisir son nom complet.
- La résolution est non ambiguë : `--output foo.pdf` → PDF, `--output foo.md` → MD,
  `--output foo` (sans extension ou inexistant) → dossier → on dérive l'extension
  depuis `--format` (ou la config).
- Test de non-régression : `test_cli_output_dir_without_extension` dans
  `tests/test_context_blocking.py::TestCLIExitCodes`.

### D-054 : Le binaire onefile embarque les DLL Tcl/Tk runtime (tcl86t/tk86t/zlib1)

**Décision** : `CorpusOne.spec` ajoute explicitement les DLL `tcl86t.dll`,
`tk86t.dll` et `zlib1.dll` (présentes dans `<python>/DLLs/`) au paramètre
`binaries` de `Analysis`. Sans elles, le chargement de `_tkinter.pyd` échoue
au démarrage de la GUI avec `ImportError: DLL load failed while importing _tkinter`.

**Rationale** :
- En mode `--onefile`, PyInstaller extrait le bundle dans `sys._MEIPASS` au
  démarrage. Les `.pyd` (`_tkinter.pyd`, `_ctypes.pyd`, etc.) sont embarquées,
  mais pas les DLL natives dont elles dépendent, car aucun module Python ne les
  importe via `import`.
- Quand on lance `python.exe` directement, Windows trouve ces DLL via le PATH
  système ou le `DLLs/` adjacent à `python.exe`. Dans le bundle extrait en
  `%TEMP%/_MEIXXXXX/`, ce mécanisme ne fonctionne pas.
- Le hook PyInstaller officiel `hook-_tkinter.py` collecte les **data files**
  Tcl/Tk (`tcl8.6/`, `tk8.6/`) mais pas les DLL elles-mêmes.

### D-055 : Le binaire onefile embarque toutes les DLL natives de `<python>/DLLs/`

**Décision** : Généralisation de D-054 : au lieu de lister les DLL une à une,
`CorpusOne.spec` collecte dynamiquement **toutes les `*.dll` présentes dans
`<python>/DLLs/`** et les ajoute au bundle. Si la DLL est absente du Python de
build, elle est ignorée silencieusement.

**Rationale** :
- L'approche au cas par cas (D-054) s'est cassée dès la deuxième DLL manquante :
  `libffi-8.dll` (dépendance de `_ctypes.pyd`, requise par CustomTkinter).
- D'autres DLL natives (libssl-3, libcrypto-3, sqlite3.dll) ont la même
  vulnérabilité : aucun `import` Python, mais chargées dynamiquement par les
  modules `_ssl` / `_sqlite3`.
- L'approche générique « tout ce qui est dans `<python>/DLLs/*.dll` est embarqué »
  est la solution standard recommandée par la documentation PyInstaller pour les
  applications onefile avec GUI.
- Coût en taille : ~3 Mo supplémentaires (passage de 35.9 Mo à 40.6 Mo).
- Sécurité : aucune DLL arbitraire ; ce sont uniquement celles livrées avec le
  Python portable utilisé pour le build, sous contrôle de l'environnement DocFuse.

---

## Session 11 — 21 août 2026

### D-056 : Registre de moteurs de comptage de tokens, "approx" par défaut

**Décision** : Nouveau package `src/docfuse/core/tokenizers/` calqué sur le
pattern déjà utilisé pour les extracteurs (`core/registry.py`) : un
`TokenizerEngine` (ABC) avec `is_available()` / `count_tokens()`, un registre
qui liste les moteurs disponibles et résout un id (`resolve_engine`) sans
jamais lever d'exception — un id inconnu ou un moteur indisponible retombe
silencieusement sur `ApproxEngine` (octets/4, CdC §10.1), qui reste le
comportement par défaut inchangé.

**Rationale** :
- Un utilisateur a demandé de pouvoir se rapprocher du compte réel d'un
  moteur donné (en priorité Mistral), tout en gardant l'approximation
  générique comme option — pas un remplacement.
- Le pattern registre+id existait déjà pour les extracteurs ; le reproduire
  pour les moteurs de comptage évite d'inventer une deuxième façon de faire
  la même chose (maintenabilité).
- `context_counter.estimate_tokens`/`aggregate_tokens` gagnent un paramètre
  `engine` optionnel ; `engine=None` (défaut) reproduit exactement le calcul
  historique — zéro régression sur les 236 tests existants.
- `aggregate_tokens` corrige un point qui n'avait pas d'importance en mode
  approx mais en aurait eu un avec un vrai tokenizer : le total n'est plus
  recalculé depuis la somme des octets (`ceil(total_octets/4)`) quand un
  moteur précis est utilisé, mais devient la somme des comptes par fichier —
  un total BPE exact ne peut pas se déduire d'un total d'octets.

### D-057 : Moteur Mistral = `tiktoken` + vocabulaire vendoré, PAS le paquet `mistral-common`

**Décision** : `src/docfuse/core/tokenizers/mistral.py` reconstruit à la main
l'`Encoding` `tiktoken` du tokenizer Tekken de Mistral, à partir d'un fichier
de vocabulaire (`assets/tekken_240911.json`, 19 Mo) extrait du dépôt
`mistral-common` et committé dans le repo — sans installer le paquet
`mistral-common` lui-même. Dépendance ajoutée à `pyproject.toml` :
`tiktoken` (MIT) uniquement.

**Rationale** :
- Inspection du wheel réel `mistral-common` (1.11.7, 6.6 Mo) : il tire
  `pydantic-extra-types[pycountry]` en dépendance obligatoire, et
  `pycountry` est sous licence **LGPL-2.1** (vérifié dans son wheel :
  `License-Expression: LGPL-2.1-only`). `tests/test_acceptance.py::
  TestLicenseCompliance` interdit déjà explicitement `lgpl` dans les
  dépendances runtime — `mistral-common` tel quel aurait fait échouer ce
  garde-fou, et à raison : figer une dépendance LGPL dans un `.exe`
  PyInstaller onefile revient à de la liaison statique, sans le mécanisme de
  liaison dynamique que LGPL suppose (même remarque déjà faite dans ce CdC
  à propos de PySide6, §13.2).
- Le tokenizer Tekken de Mistral n'est lui-même qu'une fine couche autour du
  moteur BPE de `tiktoken` : il charge son vocabulaire (`data/tekken_*.json`,
  Apache-2.0, même dépôt) dans un `tiktoken.Encoding`. Rien d'autre dans
  `mistral-common` (formatage de chat, appels d'outils, tokens image/audio)
  ne sert à « combien de tokens fait ce document ».
- Vérifié par parité (`tests/test_core/test_tokenizers/test_mistral_parity.py`,
  ignoré si `mistral-common` n'est pas installé) : sur 7 textes (ASCII,
  accents FR, vide, texte long, japonais, code, emoji), notre adaptateur
  produit **exactement** le même nombre de tokens que
  `Tekkenizer.encode(text, bos=False, eos=False)` du vrai paquet.
- `tiktoken` tire lui-même `requests` (Apache-2.0) en dépendance — jamais
  appelé par notre code (`Tekkenizer`/notre adaptateur ne font que construire
  un `Encoding` depuis un dict local). Couvert par
  `test_no_network_call_during_load_and_encode` (mock de `socket.socket`,
  dans l'esprit déjà anticipé par le CdC §10.1 pour un tiktoken embarqué).
- Fichier vendoré plutôt que dépendance pip pour `mistral-common` uniquement
  dans le but d'en extraire un fichier de données : ~80 lignes de code
  maîtrisées valent mieux que ~10 dépendances transitives (pydantic,
  jsonschema, pillow, numpy...) pour une fonctionnalité qui n'en utilise
  qu'une fraction.

### D-058 : Convergence de l'en-tête SOURCE sans ré-encoder tout le texte

**Décision** : `estimate_source_context()` (source_header.py) garde son
algorithme historique (ré-encoder la concaténation en-tête+texte jusqu'à 20
fois) uniquement pour le moteur "approx". Avec un moteur précis, le texte du
fichier est encodé **une seule fois** ; seul le court en-tête (qui varie
d'une itération à l'autre à cause du nombre de chiffres qu'il contient) est
ré-encodé à chaque itération de convergence.

**Rationale** :
- Avec octets/4, ré-encoder tout le texte est gratuit (un `len()` et une
  division). Avec un vrai tokenizer BPE, ré-encoder un gros fichier jusqu'à
  20 fois pour converger sur un en-tête de quelques lignes aurait dégradé
  les performances sur un corpus volumineux — pour rien.
- Effet de bord accepté : à la frontière en-tête/texte, le BPE pourrait en
  théorie fusionner les tout derniers caractères de l'en-tête avec les tout
  premiers caractères du texte en un seul token, ce que le découpage en deux
  appels séparés ne peut pas reproduire. Écart possible ±1-2 tokens,
  négligeable devant la marge de sécurité +15 % déjà appliquée.
- Test de non-régression perf-comportement : un moteur factice qui
  journalise ses appels vérifie qu'un texte de 5000 mots n'est encodé en
  entier qu'une seule fois (`test_source_header.py::
  test_large_file_text_is_encoded_only_once`).

### D-059 : Corrige le chemin d'upload d'artifact CI, cassé silencieusement depuis le passage en `--onefile`

**Décision** : `.github/workflows/ci.yml`, job `build-windows` : le chemin
`path:` de `actions/upload-artifact` passe de `dist/CorpusOne/` (dossier,
ancien mode `--onedir`) à `dist/CorpusOne.exe` (fichier unique, mode
`--onefile` actuel). Ajout de `if-no-files-found: error` pour que ce genre
de régression fasse échouer la CI au lieu d'un simple avertissement ignoré.

**Rationale** :
- Découvert en vérifiant, sur demande, que la CI construisait bien l'exe
  avec les nouvelles dépendances (`tiktoken`) : le job `build-windows`
  s'affichait vert sur GitHub Actions depuis le passage en onefile, mais
  chaque run affichait *« No files were found with the provided path:
  dist/CorpusOne/. No artifacts will be uploaded »* — silencieusement
  ignoré parce que `if-no-files-found` valait `warn` par défaut.
- Le build PyInstaller lui-même a toujours réussi (`Build complete!`) ;
  seul le téléchargement de l'artifact depuis l'onglet Actions était cassé.
  Les .zip publiés sur les Releases GitHub n'en dépendent pas (upload
  manuel), donc ce n'était pas visible pour les utilisateurs finaux.
- `if-no-files-found: error` transforme ce genre de régression silencieuse
  en échec explicite de la CI, cohérent avec la discipline du projet (tests
  d'acceptation stricts plutôt que des `|| true` qui masquent les problèmes).

---

## Session 12 — 21 août 2026

### D-060 : Ajout du moteur de comptage précis OpenAI (`o200k_base`)

**Décision** : Deuxième moteur précis dans le registre, `core/tokenizers/openai.py`.
Même architecture que le moteur Mistral (D-057) : aucune dépendance
supplémentaire (`tiktoken` est déjà présent), un fichier de vocabulaire
officiel vendoré (`assets/o200k_base.tiktoken`, hash SHA-256 vérifié
identique à celui que `tiktoken_ext.openai_public.o200k_base()` attend :
`446a9538…`), chargé directement depuis le fichier local — jamais via
`tiktoken.get_encoding()` qui téléchargerait sinon depuis
`openaipublic.blob.core.windows.net` au premier appel. Aucun token spécial
enregistré (comme Mistral) : un document qui contiendrait littéralement
`<|endoftext|>` est compté comme texte normal plutôt que de lever une
exception.

**Rationale** :
- Choix demandé comme "le plus facile pour la prochaine version" : `tiktoken`
  étant déjà une dépendance (pour Mistral), ajouter l'encodage GPT natif de
  `tiktoken` ne coûte qu'un fichier de vocabulaire (~3,6 Mo, contre 19 Mo pour
  Mistral) et aucune nouvelle dépendance — contrairement à Llama/HuggingFace
  `tokenizers` (dépendance Rust supplémentaire), gardé pour plus tard.
- Vérifié par parité (`tests/test_core/test_tokenizers/test_openai_parity.py`)
  contre le vrai `tiktoken.get_encoding("o200k_base")` officiel, sur 7 textes
  (ASCII, accents, japonais, code, emoji) — comptes identiques. Contrairement
  au test de parité Mistral, celui-ci s'exécute dans la CI standard (pas de
  paquet optionnel à installer) : le cache de `tiktoken` est amorcé avec notre
  fichier vendoré (`TIKTOKEN_CACHE_DIR` pointé vers un dossier temporaire
  contenant le fichier sous la clé `sha1(url)` attendue), donc zéro réseau
  même pendant ce test.
- Testé sur un corpus de documents réels (DOCX/PDF/TXT, 10 Ko à 2 Mo, fourni
  par l'utilisateur) : extraction une fois, puis `recompute_engine()` (D-056)
  pour comparer approx/Mistral/OpenAI sur exactement le même texte extrait
  sans reproduire le coût d'extraction 3 fois.

### D-061 : Publication automatique de l'exe Windows sur les Releases GitHub

**Décision** : `.github/workflows/ci.yml`, job `build-windows` : quand le
déclencheur est une Release GitHub publiée (`github.event_name == 'release'`,
pas un simple push sur `main`), une étape supplémentaire zippe
`dist/CorpusOne.exe`, calcule son SHA-256, et attache les deux fichiers
(`CorpusOne-{version}-windows-x64.zip` + `.zip.sha256`) à cette Release via
`gh release upload`. Ajout de `permissions: contents: write` sur le job
(nécessaire pour cette action, pas garanti par les permissions par défaut).

**Rationale** :
- Jusqu'ici, l'exe buildé par la CI n'était accessible que via l'onglet
  Actions → artifacts (connexion GitHub requise, expire à 90 jours, peu
  découvrable — l'utilisateur ne savait pas que ça existait). La release
  v0.1.1 avait été publiée avec un zip uploadé **manuellement**.
- Même convention de nommage que ce zip manuel (`CorpusOne-{version}-windows-x64.zip`,
  `.sha256` au format `HASH<espace><espace>nom_fichier`, cf. `docs/releases/v0.1.1.md`)
  pour ne rien changer côté utilisateur — juste automatiser ce qui était fait
  à la main.
- Ne se déclenche que sur `release: published`, pas sur chaque push : décision
  de version explicite, pas un artifact de CI de dev.

---

## Session 13 — 24 août 2026

### D-062 : Déduplication des en-têtes/pieds de page répétés (PDF)

**Décision** : `extractors/pdf.py::_dedupe_page_boilerplate()` ne regarde que
la première et la dernière ligne de chaque page extraite par pdfminer (là où
un en-tête/pied de page physiquement positionné apparaît), jamais le corps
du texte. Une ligne n'est retirée que si elle est identique sur au moins
`PDF_BOILERPLATE_MIN_OCCURRENCES` (3) pages **et** `PDF_BOILERPLATE_MIN_RATIO`
(50 %) des pages, et fait moins de `PDF_BOILERPLATE_MAX_LINE_LEN` (200)
caractères. `chars_per_page` (utilisé par `image_detector.py` pour la
détection de pauvreté de texte) est recalculé sur le texte dédupliqué.

**Rationale** :
- Un PDF de plusieurs dizaines de pages avec un pied de page répété
  ("Confidentiel", "Page X sur Y") le duplique une fois par page dans le
  texte extrait — du bruit pur, aucune valeur informative, un vrai coût en
  tokens.
- Ne regarder que les extrémités de page limite le risque de retirer un
  paragraphe légitimement répété dans le corps du texte.
- Sans perte silencieuse (CdC §8) : la première occurrence reste dans le
  corpus, et une note (`extra_metadata["pdf_dedup"]`) apparaît dans l'en-tête
  SOURCE et le rapport, indiquant combien de lignes et d'occurrences ont été
  dédupliquées.

### D-063 : Retrait des images base64 intégrées dans les fichiers Markdown

**Décision** : `extractors/markdown.py::_strip_base64_images()` détecte les
data URI `data:image/...;base64,...` (payload ≥
`MARKDOWN_BASE64_MIN_LEN` = 100 caractères) et remplace uniquement le
payload par une note explicite ; la syntaxe Markdown environnante
(`![alt](...)`) et l'`alt` sont conservés. Le nombre d'images retirées
alimente `image_count` (réutilise l'alerte `images` déjà existante).

**Rationale** :
- En contexte texte, un LLM ne peut pas "voir" une image depuis du base64
  brut — c'est juste une longue chaîne illisible qui coûte des tokens sans
  rien apporter, contrairement à la compression sémantique (rejetée en
  amont de cette session, car elle risquerait de retirer du contenu
  réellement porteur de sens).
- Cas fréquent avec des exports Obsidian/Notion ou des captures d'écran
  collées directement dans une note.

### D-064 : Détection de doublons de contenu entre fichiers

**Décision** : nouveau module `core/duplicate_detector.py::detect_duplicates()`,
appelé dans `orchestrator.py::run_analysis()` après la détermination du
statut et avant le comptage de tokens. Hash SHA-256 du texte extrait
(normalisé par `strip()`) de chaque fichier avec `status.is_extracted()` et
au moins `DUPLICATE_MIN_CHARS` (50) caractères. Le premier fichier d'un
groupe de doublons (ordre de tri de l'inventaire) reste l'original ; les
suivants voient leur `text` remplacé par une courte note
(`extra_metadata["duplicate_of"]`).

**Rationale** :
- Cas fréquent quand l'utilisateur sélectionne un dossier entier plutôt que
  des fichiers un par un : copie dans deux dossiers, sauvegarde, export
  dupliqué.
- Remplacer le texte par une note (plutôt que garder un champ séparé) évite
  toute logique spécifique en aval : le comptage de tokens, l'écriture du
  corpus et l'en-tête SOURCE traitent un doublon exactement comme un
  fichier normal, avec un texte très court.
- A nécessité de corriger deux tests existants (`test_acceptance.py::
  test_multiple_files_total_blocked`, `test_context_blocking.py::
  big_files_dir`) qui utilisaient un contenu strictement identique sur
  plusieurs fichiers comme raccourci pour obtenir une taille totale
  déterministe — désormais dédupliqué par construction, donc plus assez
  volumineux pour déclencher le blocage testé. Contenu rendu distinct par
  fichier (`"A"`/`"B"`/`"C"` au lieu de `"A"` partout), l'intention du test
  (plusieurs fichiers non bloquants individuellement, total bloquant) reste
  inchangée.

### D-065 : Alerte non bloquante sur les secrets potentiels

**Décision** : nouveau module `core/secret_scanner.py::scan_for_secrets()`,
appelé pour chaque fichier extrait dans `run_analysis()`. Motifs à haute
confiance uniquement (clé AWS `AKIA...`, bloc `-----BEGIN ... PRIVATE
KEY-----`, jeton Slack `xox[baprs]-...`, JWT `eyJ...\.…\.…`, assignation
`api_key=`/`secret_key=`/`access_token=`/`client_secret=` suivie d'une
valeur ≥ 16 caractères). Ne modifie jamais le texte, ne bloque jamais la
génération — pose `extra_metadata["secrets_detected"]` avec le **type** de
secret et le numéro de ligne, jamais la valeur trouvée.

**Rationale** :
- DocFuse prépare un corpus destiné à un chat LLM externe : un `.env`, une
  clé API dans un fichier de config, une clé privée SSH glissés
  involontairement dans la sélection partiraient tels quels vers un tiers.
- Délibérément conservateur (peu de motifs, haute confiance) pour limiter
  les faux positifs — pas de motif générique `password=...` (trop de
  faux positifs sur de la documentation légitime qui mentionne le mot).
- Ne jamais journaliser/afficher la valeur trouvée : le rapport lui-même
  (MD/JSON, potentiellement committé par erreur) ne doit pas devenir un
  second vecteur de fuite.
- Surface v1 : en-tête SOURCE + rapport MD/JSON uniquement (pas de nouvelle
  pastille GUI ni de nouveau `FileStatus` — aurait élargi la portée aux
  couleurs/tri/sévérité déjà couplés à cette énumération). Amélioration
  possible plus tard si le besoin se confirme.

---

## Session 14 — 29 août 2026

### D-066 : Fichiers de développement traités comme texte brut

**Décision** : nouvelle constante `constants.CODE_EXTENSIONS` (~60
extensions : `.py`, `.js`/`.ts`, `.vba`, `.sh`/`.ps1`, `.sql`, `.css`,
`.java`, `.c`/`.cpp`, `.go`, `.rs`, `.toml`, etc.), fusionnée dans
`SUPPORTED_EXTENSIONS` avec la catégorie `"code"`, dispatchées vers
`TextExtractor` (même détection d'encodage que `.txt`) — aucune extraction
spécifique par langage, `file_type` reste l'extension elle-même (M-08).

**Rationale** :
- Trou fonctionnel réel identifié par l'utilisateur : envoyer une codebase à
  une LLM est un cas d'usage courant, et ces fichiers étaient auparavant
  silencieusement `IGNORED` (hors de `ALL_EXTENSIONS`).
- Zéro nouvelle dépendance, zéro risque de portabilité : un fichier `.py`
  est du texte, exactement comme un `.txt`.
- Limite assumée et documentée (pas corrigée ici) : le dispatch de
  `core/registry.py` se fait par **suffixe** (`Path.suffix`). Les fichiers
  sans extension (`Dockerfile`, `Makefile`) ou dotfiles purs (`.gitignore`,
  `.env`) ont un `suffix` vide en Python — ils restent hors périmètre. Un
  dispatch par nom de fichier complet serait un changement plus large,
  laissé pour une session future si le besoin se confirme.

### D-067 : OCR des PDF scannés — build séparé `CorpusOne-OCR`

**Décision** : nouveau package `core/ocr/` (même pattern que
`core/tokenizers/` — registre, `is_available()`, jamais d'exception).
Classification par page dans `extractors/pdf.py` (`native`/`ocr`/`blank`/
`mixed`, à partir du texte déjà extrait par pdfminer — pas de seconde
extraction), OCR via le binaire CLI Tesseract en `subprocess`
(`pypdfium2` pour la rastérisation). Le binaire Tesseract + ses modèles de
langue (~40-80 Mo, pas un paquet pip) ne sont **pas** embarqués dans
`CorpusOne.exe` : un second exe, `CorpusOne-OCR.exe`
(`CorpusOne-OCR.spec`, nouveau job CI `build-windows-ocr`), les embarque et
est publié en parallèle sur la même Release GitHub. Détail complet :
`docs/cahier-des-charges-docfuse.md` §9.5.

**Rationale** :
- Un PDF scanné était déjà **détecté** (`FileStatus.LOW_TEXT`) mais son
  contenu n'était jamais récupéré — l'utilisateur a fourni un cahier des
  charges add-on détaillé, adapté ici au code réel de DocFuse plutôt que
  porté tel quel (le document source ciblait un serveur MCP).
- **Décision produit tranchée explicitement avec l'utilisateur** (et non
  supposée) : `CorpusOne.exe` classique garde sa taille et sa promesse
  « zéro dépendance » inchangées ; l'embarquement de Tesseract est un choix
  de build séparé, pas une évolution silencieuse de l'exe existant.
- Invocation CLI via `subprocess` plutôt qu'une liaison native
  (`tesserocr`) : chaque appel est déjà un process OS isolé avec son propre
  `timeout=`, ce qui évite `ProcessPoolExecutor`/`multiprocessing` dans un
  exécutable PyInstaller figé (respawn, `freeze_support()`) — risque connu
  et documenté du document source, contourné par ce choix.
- `pypdfium2` (Apache-2.0/BSD-3) choisi pour la rastérisation ; `PyMuPDF`
  explicitement écarté (AGPL-3.0, contaminerait un livrable Apache-2.0).
- Portée v1 = PDF uniquement. Fichiers image seuls et images intégrées
  dans `.docx`/`.pptx` (soulevés par l'utilisateur) : notés pour une
  itération suivante, pas abandonnés — même moteur `core/ocr/` réutilisable.
- Vérifié en conditions réelles pendant la session (Tesseract 5.5 installé
  localement) : un PDF image-only construit avec `reportlab` recouvre bien
  son texte, le statut passe de `LOW_TEXT` à `READY`/`IMAGES`, et la
  bascule automatique vers le comportement inchangé (note "OCR non
  disponible") a été vérifiée en masquant Tesseract du PATH.

### D-068 : Texte imbriqué dans un Form XObject (LTFigure) — bug d'extraction PDF corrigé

**Décision** : `_extract_pages_pdfminer()` (`extractors/pdf.py`) appelle
désormais `extract_pages(path, laparams=LAParams(all_texts=True))` et
recurse dans chaque `LTFigure` pour en extraire le texte (`_extract_text_in_figure`,
symétrique de `_count_images_in_figure` qui existait déjà pour les images).

**Rationale** :
- Bug pré-existant, antérieur à cette session, découvert en diagnostiquant
  le retour utilisateur "un PDF confidentiel n'a extrait presque rien". Un
  PDF généré par TCPDF plaçait le texte réel de 3 de ses 5 pages dans un
  Form XObject imbriqué — `isinstance(element, LTTextContainer)` au premier
  niveau de la page ne le voyait jamais, donc ces pages semblaient vides
  (jusqu'à ~2500 caractères silencieusement perdus par page).
- Sans `LAParams(all_texts=True)`, pdfminer ne regroupe même pas ce texte
  en lignes/paragraphes (il reste en `LTChar` épars) — le réglage est
  nécessaire, la récursion seule n'aurait pas suffi.
- Effet de bord positif inattendu : ce même bug faisait que des pages avec
  du texte natif parfaitement propre étaient classées `blank`/`ocr` par la
  nouvelle classification OCR (D-067), qui se basait sur le même comptage
  de caractères erroné — corriger l'extraction native réduit aussi les
  faux déclenchements d'OCR (vérifié sur le fichier réel : le document
  n'a plus besoin d'OCR du tout une fois ce bug corrigé, seules 2 pages
  restent `mixed` à cause d'une image de fond légitime).
- Testé avec une reproduction minimale (`reportlab` `beginForm`/`doForm`,
  `test_text_nested_in_form_xobject_is_extracted`) plutôt qu'avec le
  fichier réel utilisé pour le diagnostic (confidentiel par erreur,
  jamais commité ni partagé) — la structure PDF générée est identique
  (texte dans un Form XObject), donc la repro est fidèle.
- Zéro régression : 364 tests passent (dont tous les tests PDF/dédup/OCR
  existants), recette 7/7.

### D-069 à D-076 : audit systématique des extracteurs, 9 bugs de perte silencieuse corrigés

**Contexte** : après le bug LTFigure (D-068), l'utilisateur a demandé une
vérification systématique — 5 recherches en parallèle (une par
bibliothèque : pdfminer/pypdf, python-docx, python-pptx, openpyxl,
HTML/RTF/EML/MHTML/ODF), croisant issues GitHub connues et lecture précise
du code réel de chaque extracteur. Résultat : ~25 classes de bugs
identifiées, 9 confirmées à forte gravité (perte totale/silencieuse de
contenu substantiel) et corrigées une par une, chacune avec un test de
non-régression construit sur un fichier réel généré par la bibliothèque
concernée (jamais un mock).

- **D-069 — DOCX, texte imbriqué invisible** (`w:ins` suivi des
  modifications, `w:sdt` contrôles de contenu bloc et run) :
  `Paragraph.text` de python-docx ne regarde que les runs enfants
  **directs** de `w:p` — tout texte inséré en suivi de modifications, ou
  dans un contrôle de contenu Word (omniprésent dans les modèles RH/
  juridique/formulaires), disparaissait. Corrigé par `_flatten_paragraph_text()`
  (parcourt tous les `w:t` descendants, quel que soit l'élément englobant,
  exclut `w:delText`) et `_iter_body_parts()` (descend dans les `w:sdt` au
  niveau bloc). Bonus non ciblé : corrige aussi implicitement les
  MERGEFIELD via `w:fldSimple` (même mécanisme).
- **D-070 — EML, email transféré (`message/rfc822`) perdu** : la logique
  "premier text/plain gagne" faisait que le corps du message englobant
  (toujours rencontré en premier) gagnait systématiquement sur le sujet et
  le corps du message transféré en pièce jointe — souvent le contenu le
  plus important du fichier. Corrigé par un rendu récursif par message
  (`_render_message`), chaque niveau ayant son propre corps direct
  (`_extract_direct_body`, qui ignore explicitement les `message/rfc822`
  imbriqués) et ses propres sous-messages (`_iter_nested_messages`).
- **D-071 — PDF, mot de passe utilisateur vide rejeté en erreur totale** :
  `reader.is_encrypted` (pypdf) reste `True` même après déchiffrement
  réussi — un PDF protégé uniquement en copie/impression (mot de passe
  utilisateur vide, cas très courant en juridique/financier) était rejeté
  comme un fichier totalement illisible alors que pdfminer l'aurait extrait
  sans problème (mot de passe vide essayé par défaut). Corrigé :
  `_check_encrypted()` tente `reader.decrypt("")` et ne bloque que si ça
  échoue réellement.
- **D-072 — ODF (.odt), en-têtes/pieds de page jamais lus** : vivent dans
  `styles.xml` (`office:master-styles`), jamais dans `content.xml`.
  Contiennent souvent des métadonnées de document (référence, mention de
  confidentialité). Corrigé par `_extract_master_headers_footers()`, lu en
  plus de `content.xml` si `styles.xml` est présent dans l'archive.
- **D-073 — HTML, `<meta charset>` jamais consulté** : `detect_encoding()`
  (BOM→UTF-8→cp1252→...) ignore la déclaration HTML — cp1252 décode presque
  tous les octets sans erreur, donc "gagne" avant même d'essayer le charset
  déclaré. Mojibake total et silencieux pour tout charset legacy mono-octet
  non latin (cyrillique, grec, hébreu...), vérifié empiriquement. Corrigé
  en remplaçant la détection générique par `bs4.UnicodeDammit(is_html=True)`
  (déjà une dépendance du projet), qui sait lire cette déclaration — repli
  sur `detect_encoding()` uniquement si Dammit échoue à produire du texte.
- **D-074 — PPTX, formes groupées (`GroupShape`) sans récursion** :
  `shape.has_text_frame`/`has_table` renvoient `False` pour le conteneur
  groupe lui-même — tout texte/tableau dans un groupe (schémas, diagrammes
  annotés, fréquents dans les decks "corporate") était invisible. Corrigé
  par `_iter_shapes()`, un itérateur récursif (un groupe peut contenir un
  groupe) remplaçant `slide.shapes`.
- **D-075 — RTF, texte de repli des objets OLE incrustés (`\result`)
  perdu** : striprtf traite `\result` comme une "destination ignorable", au
  même titre que les données binaires `\objdata` — le texte de repli
  (souvent un tableau Excel collé en objet, scénario très courant) disparaît
  avec. Dépendance externe non patchable ; corrigé par un pré-traitement du
  RTF brut (`_extract_ole_fallback_texts`, scan par profondeur d'accolades
  respectant les échappements `\{`/`\}`) qui isole chaque groupe `{\result
  ...}` et le repasse à `rtf_to_text()` séparément — son contenu est
  lui-même un fragment RTF valide.
- **D-076 — XLSX, formules jamais calculées → cellule vide sans trace** :
  `data_only=True` renvoie `None` pour une formule sans valeur en cache
  (fichier généré par script, jamais ouvert dans Excel/LibreOffice) —
  indistinguable d'une cellule réellement vide. Fréquent avec des exports
  automatisés (ERP/BI) : des colonnes de totaux entières disparaissaient.
  Corrigé en ouvrant un second classeur (`data_only=False`) en parallèle :
  une cellule `None` dont la formule commence par `=` devient
  `[formule non calculée: =...]` plutôt que du vide silencieux.

**Rationale commune** :
- Tous ces bugs partagent la même signature : une bibliothèque d'extraction
  a une hypothèse structurelle non vérifiée (ordre XML, cache de valeur,
  déclaration de charset, type de conteneur) et DocFuse lui faisait
  confiance aveuglément — exactement la même classe que le bug LTFigure
  (D-068) qui a déclenché cet audit.
- Chaque correctif a été vérifié par un test de non-régression construit
  avec la bibliothèque réelle du format concerné (python-docx, pptx,
  openpyxl, email stdlib, striprtf, zipfile+XML pour ODF), jamais un mock —
  reproduisant la structure exacte du bug avant de vérifier le correctif.
- Périmètre volontairement limité aux 9 bugs de **forte gravité** identifiés
  par l'audit ; les bugs de gravité moyenne/faible (tableaux DOCX imbriqués
  dans une cellule, SmartArt PPTX, cellules XLSX fusionnées, etc.) sont
  documentés dans `docs/journal-avancement.md` § Reste à faire, pas corrigés
  cette session.
- Non-régression stricte : 374 tests passent (+10 depuis le début de la
  session), recette 7/7. Effet de bord positif : le typage de `eml.py` a
  été nettoyé au passage (4 erreurs mypy pré-existantes résolues,
  8 → 4 sur l'ensemble du projet).

### D-077 : exclusion des bundles JS/CSS minifiés et des dossiers vendor

**Décision** : `IGNORE_PATTERNS` gagne `*.min.js`/`*.min.css` ;
`IGNORE_DIRS` gagne `node_modules`, `vendor`, `dist`, `build`.

**Rationale** :
- Trouvé en testant DocFuse sur de vrais dossiers utilisateur
  (`~/Documents`) après l'implémentation de `CODE_EXTENSIONS` (D-066) :
  un dossier de page web sauvegardée par un navigateur ("Enregistrer la
  page complète") contient un dossier `..._fichiers/` avec du JS/CSS tiers
  minifié (jQuery, jQuery UI...). Sur ce cas réel, ce bruit représentait
  **192 000 des 210 500 tokens du corpus généré (91 %)** — jQuery minifié
  seul faisait 78 000 tokens.
- `*.min.js`/`*.min.css` est un signal fiable et sans ambiguïté : un
  bundle minifié n'est par construction jamais du code destiné à être lu
  (ni par un humain, ni utilement par une LLM) — contrairement à une
  extension de langage, aucun faux positif plausible sur un fichier que
  l'utilisateur aurait lui-même écrit.
- `node_modules/vendor/dist/build` : mêmes dossiers déjà exclus par
  convention dans la quasi-totalité des `.gitignore` de l'écosystème
  JS/web — dépendances ou artefacts de build, jamais du code source.
- Vérifié sur le dossier réel qui a révélé le problème : les fichiers
  `*.min.js`/`*.min.css` disparaissent de l'inventaire, le reste
  (`.pptx`, `.pdf`, `.html`) reste inchangé. 376 tests passent, recette 7/7.

---

*Fin du journal des décisions — Session 14.*
