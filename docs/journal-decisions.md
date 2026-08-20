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

*Fin du journal des décisions — Session 9.*
