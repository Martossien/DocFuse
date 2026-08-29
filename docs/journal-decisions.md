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

### D-078 : verrou global sur PDFium — corruption mémoire native / crash du processus entier

**Décision** : `extractors/pdf.py::_ocr_pages()` tient désormais
`_PDFIUM_LOCK` (verrou global au niveau du processus, pas par fichier)
pendant tout accès à `pypdfium2` (`PdfDocument`, `page.render()`,
`pdf.close()`).

**Rationale** :
- Trouvé en testant DocFuse sur `~/Téléchargements` (741 fichiers,
  `--no-recursive`) : `python3 -m docfuse.cli` s'est terminé par un
  **SIGSEGV** (`systemd-coredump` confirmé, `coredumpctl info`). Trace :
  crash natif dans `libpdfium.so`
  (`CPDF_ColorSpace::CreateBufAndSetDefaultColor` ← `FPDF_LoadPage`),
  provoqué par l'appel OCR (`_ocr_pages`, D-067).
- **Cause racine confirmée par reproduction isolée** : PDFium (via
  `pypdfium2`) n'est **pas thread-safe entre `PdfDocument` distincts**
  chargés depuis des threads différents. Un script minimal ouvrant/rendant
  plusieurs PDF réels différents en parallèle (`ThreadPoolExecutor(max_workers=4)`,
  même pattern que l'orchestrateur) reproduit de façon fiable une
  corruption de tas (`malloc(): unsorted double linked list corrupted`)
  puis un abort/SIGSEGV — sur les mêmes fichiers, en séquentiel, aucun
  problème. L'orchestrateur (`orchestrator.py`) traite les fichiers d'un
  dossier en parallèle (`ThreadPoolExecutor`, `MAX_WORKERS`), donc
  plusieurs PDF nécessitant l'OCR simultanément déclenchent la course.
- Ma protection D-067 ("un seul `PdfDocument`, séquentiel") ne couvrait
  que l'intérieur d'UN fichier — pas l'accès concurrent à PDFium **entre**
  fichiers différents traités par des threads différents, qui est la
  vraie source du problème.
- Gravité maximale : un SIGSEGV natif tue **tout le processus** — pas
  seulement le fichier en cours (contrairement à une exception Python,
  qu'un `try/except` aurait pu absorber). Un dossier avec ne serait-ce que
  2 PDF nécessitant l'OCR peut faire échouer la génération de tout le
  corpus, sans message d'erreur exploitable pour l'utilisateur.
- Correction vérifiée par reproduction : le même script de test
  (ouverture/rendu concurrents de tous les PDF réels d'un dossier) passe
  sans erreur une fois le verrou en place ; la commande CLI qui avait
  crashé (741 fichiers) se termine proprement (bloquée seulement par le
  plafond de contexte, pas par un crash).
- Test de non-régression déterministe plutôt que dépendant d'une vraie
  course native (non fiable en CI) : un `PdfDocument` factice observe
  l'état de `_PDFIUM_LOCK.locked()` à l'appel — vérifié qu'il échoue si le
  verrou est retiré (`with _PDFIUM_LOCK:` → `if True:`).
- Coût : rastérisation PDFium sérialisée process-wide (pas de parallélisme
  entre fichiers pour cette étape spécifique). Acceptable : c'est
  uniquement l'ouverture/rendu de page (rapide), pas l'OCR Tesseract
  lui-même (qui reste parallélisé, isolé par process via `subprocess`).

### D-079 : `ruff` épinglé sur une version exacte

**Décision** : `ruff>=0.4.0` → `ruff==0.16.5` dans `pyproject.toml` (dev).
CI installe déjà via `pip install -e ".[dev]"`, donc aligné automatiquement
— aucun changement séparé nécessaire dans `ci.yml`.

**Rationale** :
- Dette technique identifiée en Session 13 : la CI installait `ruff` sans
  borne haute, dérivant vers la dernière version (0.16.4 à l'époque) alors
  que l'environnement local restait sur 0.8.0 — deux versions avec des avis
  de formatage différents sur un `assert` multi-lignes, faisant échouer
  `ruff format --check` en CI sur du code déjà passé en local. Avait cassé
  la publication initiale de la Release `v0.1.3`.
- `ruff` ne suit pas un contrat de stabilité strict sur le comportement du
  formatter/linter entre versions mineures (contrairement à son API CLI) —
  une plage `>=`/`<` resterait exposée à la même classe de dérive à chaque
  nouvelle version publiée. Seul un épinglage exact élimine le risque.
- Local remis à niveau (0.16.5) et vérifié : `ruff check`/`ruff format
  --check` propres sur tout le dépôt. Une seule règle nouvelle déclenchée
  (`UP042`, `PageKind(str, Enum)` → `PageKind(StrEnum)`, cohérent avec
  `FileStatus` qui utilise déjà `StrEnum`) — corrigée.
- Prochaine mise à jour de `ruff` : un choix explicite (bump du pin +
  vérification locale), plus jamais une dérive silencieuse via la CI.

### D-080 à D-087 : bugs de gravité moyenne de l'audit extracteurs, corrigés

**Contexte** : suite de l'audit D-069 à D-076 — les bugs de gravité moyenne
identifiés à l'époque (documentés dans `journal-avancement.md` § Reste à
faire) sont traités ici, sur décision explicite de l'utilisateur. Même
méthode : un test de non-régression par bug, construit avec la bibliothèque
réelle du format (jamais un mock), reproduisant la structure exacte du bug
avant de vérifier le correctif.

- **D-080 — HTML, commentaires qui fuitent dans le texte extrait** :
  `bs4.Comment` hérite de `NavigableString` — sans exclusion explicite, un
  commentaire HTML (notes internes, IE conditional comments, code
  commenté) apparaissait comme du contenu visible normal. Corrigé par une
  exclusion explicite avant le test `NavigableString` générique dans
  `_extract_elements`. `get_text()` (utilisé pour les conteneurs
  génériques) exclut déjà correctement les commentaires par défaut — seul
  le chemin manuel top-level était touché.
- **D-081 — MHTML, `alt` des images jamais extrait** : contrairement à
  `extractors/html.py`, `_html_to_text` de `mhtml.py` faisait un
  `get_text()` brut sans jamais traiter les `<img>`. Corrigé en remplaçant
  chaque `<img>` par un marqueur texte avant `get_text()`, même convention
  que `html.py` (`[image: ...]` / `[image sans description]`).
- **D-082 — DOCX, zones de texte : deux bugs corrigés ensemble** :
  1. `_extract_textboxes` cherchait `find_all("w:txbxcontent")`
     (minuscules) — le parseur XML de BeautifulSoup est sensible à la
     casse et ne matchait donc **jamais** `<w:txbxContent>` (la casse
     réelle produite par Word). Cette fonction n'a jamais rien trouvé, sur
     aucun fichier, en dépit de son nom (I-19) — découvert en écrivant le
     test de non-régression de ce chantier.
  2. Une fois (1) corrigé : les en-têtes/pieds de page vivent dans des
     parties ZIP séparées (`word/header1.xml`, `word/footer1.xml`, ...),
     jamais lues (seul `document.xml` l'était) — une zone de texte dans un
     en-tête (logo + bloc adresse en papier à en-tête) restait invisible.
- **D-083 — DOCX, tableau imbriqué dans une cellule** : `_Cell.paragraphs`
  ne liste que les paragraphes directs d'une cellule, jamais un tableau
  imbriqué (fréquent dans les gabarits de rapports/formulaires complexes).
  Corrigé en remplaçant la jointure de `cell.paragraphs` par un appel
  récursif à `_iter_body_parts(cell._tc, ...)` — réutilise le même
  parcours que le corps du document (paragraphes, tableaux, `w:sdt`
  imbriqués), au lieu d'un traitement de cellule séparé et plus pauvre.
- **D-084 — XLSX, dimension déclarée incorrecte → troncature silencieuse** :
  en mode `read_only`, openpyxl fait confiance à l'élément XML
  `<dimension>` déclaré par le fichier plutôt que de scanner le contenu
  réel — documenté par openpyxl lui-même comme un risque si le générateur
  tiers écrit une dimension trop petite. `iter_rows()` tronque alors les
  lignes/colonnes en fin de feuille, sans erreur. Corrigé par
  `reset_dimensions()` + `calculate_dimension(force=True)` avant lecture.
  Édge case trouvé en testant : `calculate_dimension(force=True)` lève
  `UnboundLocalError` sur une feuille réellement vide (bug openpyxl,
  `cell` jamais assignée dans sa boucle) — capturé sans conséquence.
- **D-085 — XLSX, cellules fusionnées non propagées** : seule la cellule
  en haut à gauche d'une plage fusionnée porte une valeur (comportement
  Excel normal) ; `ReadOnlyWorksheet` (mode `read_only=True`, utilisé
  partout dans cet extracteur) n'expose même pas `merged_cells`. Sans
  propagation, une ligne dont le titre fusionné s'étale sur plusieurs
  colonnes perd tout contexte pour les cellules "creuses" qui suivent —
  très fréquent dans les tableaux "présentables". Corrigé en lisant
  `<mergeCell ref="...">` directement dans le XML de la feuille (`ws._worksheet_path`,
  cohérent avec `read_only` — pas de second classeur non-read_only chargé
  entièrement en mémoire) et en propageant la valeur en mémoire (grille
  matérialisée), horizontalement et verticalement.
- **D-086 — PDF, texte "poubelle" `(cid:...)` laissé tel quel si OCR
  indisponible** : le texte natif illisible (glyphes non mappés) qui a
  justement déclenché la classification `ocr` restait dans le corpus sans
  moteur OCR disponible — pollution de bruit inutilisable plutôt qu'une
  simple absence de contenu. Corrigé : ce texte est vidé (devient la page
  vide standard `[[PAGE N: aucun texte extractible]]`) uniquement pour les
  pages classées `ocr` à cause de la détection poubelle — une page `ocr`
  pour texte simplement trop court (mais réel) reste inchangée.
- **D-087 — ODF, `.odp` : notes d'orateur mélangées au contenu visible** :
  aucun tag ne matche `office:text` dans une présentation
  (`office:presentation` à la place) — le code tombait systématiquement
  dans le "dernier fallback" document-wide (`text:p`/`text:h`), qui
  mélangeait indistinctement le contenu visible des diapos ET les notes
  d'orateur (`presentation:notes`, jamais affichées à l'écran — risque de
  fuite de contenu non destiné à la diffusion), sans aucune séparation
  entre diapos ni gestion structurée des tableaux. Corrigé par
  `_extract_presentation()` : parcourt chaque `draw:page` séparément,
  extrait et étiquette les notes à part (`[notes orateur diapo N]`), gère
  les tableaux comme `office:text` (`_table_rows_to_parts()`, factorisée).

**Non traités cette session** (gravité moyenne, mais effort plus important
ou nécessitant un choix de conception) : DOCX `MERGEFIELD`/commentaires,
PPTX SmartArt/texte des graphiques, PDF annotations/champs de formulaire,
XLSX commentaires en `read_only`, HTML `title`/`alt` hors `<img>` — restent
documentés dans `journal-avancement.md` § Reste à faire.

**Vérification** : 388 tests passent (+11 depuis D-079), recette 7/7,
`ruff check`/`format --check` propres, mypy --strict sans nouvelle erreur
(2 attendues en plus, même classe pré-existante `bs4.NavigableString` non
exportée — `html.py` l'avait déjà, `mhtml.py` l'acquiert avec le même
import D-081).

### D-088 : `mypy` et `types-beautifulsoup4` épinglés — même dérive que ruff (D-079), découverte en publiant v0.1.4

**Décision** : `mypy>=1.10.0` → `mypy==2.3.1` ; `types-beautifulsoup4>=4.12.0`
→ `types-beautifulsoup4==4.12.0.20250516`.

**Rationale** :
- Découvert en publiant la Release v0.1.4 : la CI installe `mypy` sans
  borne haute, qui a résolu **mypy 2.3.1** (un saut de version majeure)
  alors que l'environnement local tournait en 1.16.1 — exactement la même
  classe de dérive que D-079 (`ruff`), avec le même effet : `lint-and-test`
  a échoué sur les 6 jambes de la matrice, empêchant `build-windows` et
  `build-windows-ocr` de se déclencher (les deux `skipped`, 0 asset publié
  sur la Release initiale).
- Root cause à deux niveaux :
  1. `types-beautifulsoup4` n'était en réalité **pas installé du tout**
     dans l'environnement de dev local (`pip show` → introuvable), alors
     que `[[tool.mypy.overrides]] module = "bs4.*"` a
     `ignore_missing_imports = true` — ce réglage masque silencieusement
     TOUTE erreur de typage bs4 quand le paquet de stubs est absent
     (repli sur `Any`), mais n'a aucun effet une fois le paquet installé
     (comme en CI) : mypy type-check alors pour de vrai contre les stubs
     réels, révélant des erreurs invisibles en local.
  2. mypy 2.3.1 infère correctement `EmailMessage` depuis
     `BytesParser(policy=policy.default)` (`eml.py`, `mhtml.py`) — une
     amélioration par rapport à 1.16.1, qui nécessitait le `cast()`
     explicite ajouté en D-070. Sous 2.3.1, ce cast devient une erreur
     `redundant-cast` plutôt qu'une nécessité. Supprimé.
  3. `types-beautifulsoup4` ne réexporte pas `UnicodeDammit` depuis
     `bs4/__init__.pyi` (bien que la classe existe réellement et soit
     correctement stubée dans `bs4/dammit.pyi`) — corrigé en important
     directement depuis le sous-module (`from bs4.dammit import
     UnicodeDammit`, D-073) plutôt que le point d'entrée du package.
- Une fois les deux versions installées localement pour matcher la CI
  exactement : **0 erreur mypy sur tout le projet** — y compris les
  erreurs `bs4.NavigableString`/`email.BytesParser` considérées comme
  « baseline pré-existante » tout au long de cette session (D-069 à D-087)
  ont en réalité disparu avec la bonne version de mypy. Ce qui semblait
  être une dette acceptée était en fait un artefact de dérive de version
  locale, jamais un vrai baseline stable.
- Leçon retenue : après D-079 (ruff), cette session confirme que **tout
  outil de dev qui affecte la sortie CI (lint, format, typage) doit être
  épinglé sur une version exacte**, pas seulement `ruff`. `pytest`/
  `pip-licenses` restent non épinglés (n'affectent pas le pass/fail sur la
  base d'une opinion de version, contrairement à ruff/mypy/stubs).

### D-089 : détection des fichiers Office protégés par mot de passe à l'ouverture

**Décision** : nouveau helper `extractors/base.py::is_ole_encrypted()`,
appelé en tout premier dans `extract()` de `xlsx.py`/`docx.py`/`pptx.py`.
Nouvelle clé i18n `error.encrypted_office`.

**Rationale** :
- Retour utilisateur (test sur machine Windows réelle) : un `.xlsx`
  protégé par mot de passe à l'ouverture donnait une erreur incompréhensible
  plutôt qu'un message clair — même défaut déjà corrigé pour le PDF
  (`error.encrypted_pdf`), jamais étendu aux formats Office.
- Vérifié empiriquement (signature OLE2/CFBF `D0 CF 11 E0 A1 B1 1A E1`,
  spec MS-OFFCRYPTO) : `openpyxl`/`python-docx`/`python-pptx` échouent
  tous les trois avec une exception bas niveau différente et peu parlante
  (`BadZipFile: File is not a zip file`, `PackageNotFoundError: Package
  not found at ...`) — même classe de bug sur les trois formats, un seul
  helper partagé suffit (contrairement à la détection PDF, qui utilise
  `pypdf.PdfReader.is_encrypted`, propre au format PDF).
- Distinction volontaire avec la protection de structure/feuille
  (`wb.security.workbookPassword`, verrouille l'édition mais pas la
  lecture) : seul le chiffrement complet du conteneur (mot de passe
  obligatoire pour même ouvrir le fichier) est détecté ici — les fichiers
  avec juste une protection de structure continuent de s'extraire
  normalement, comme avant.

### D-090 : GUI — tri des colonnes du tableau de fichiers, fenêtre élargie

**Décision** : en-têtes du tableau cliquables (tri par nom/type/texte
estimé/contexte/statut, second clic = inverse), logique de tri extraite en
fonction pure `sort_file_pairs()` (même esprit que `resolve_tokenizer_choice`,
testable sans ouvrir de fenêtre). Fenêtre par défaut `900x720`/`minsize
700x600` → `1050x720`/`minsize 900x600`.

**Rationale** :
- Retour utilisateur (test sur machine Windows réelle) : impossible de
  trier la liste de fichiers, et les boutons du bas (Générer, Rapport,
  Annuler) débordaient de la fenêtre par défaut, obligeant à l'agrandir
  manuellement à chaque lancement.
- Tri par statut : sévérité (`FileStatus.severity`, 0=ready) plutôt que
  libellé traduit affiché — regroupe "Peu de texte" avec "Images"/"Erreur"
  dans un ordre de gravité cohérent, pas un tri alphabétique arbitraire du
  texte français/anglais affiché.
- Fenêtre élargie : vérifié par capture d'écran (session Linux avec
  affichage réel disponible) que le rendu CustomTkinter local n'était PAS
  cassé à 900x720 — le débordement observé par l'utilisateur est donc
  probablement spécifique au rendu de police Windows (Segoe UI plus large,
  ou mise à l'échelle DPI) et n'a pas pu être reproduit tel quel ici. La
  marge supplémentaire est une mitigation de bon sens, pas une correction
  vérifiée à l'identique du bug original — à confirmer par l'utilisateur.

### D-091 : OCR des images intégrées DOCX/PPTX + export optionnel pour description LLM

**Décision** : deux fonctionnalités liées, tranchées séparément avec
l'utilisateur —
1. **OCR automatique** des images intégrées (`w:drawing//a:blip` DOCX,
   formes `PICTURE` PPTX), même moteur Tesseract que l'OCR PDF
   (`core/ocr/`), sans réglage à activer — dès que Tesseract est
   disponible, ça marche.
2. **Export optionnel** (`extract_embedded_images`, désactivé par défaut —
   CLI `--extract-images`, GUI case à cocher, config JSON) : chaque image
   est écrite dans `<sortie>_images/`, nommée
   `{doc_stem}__{emplacement}__img{n}.{ext}` (ex.
   `atelier_camelia_managers_V0.4__slide7__img1.png`), avec un tag inline
   `[[IMAGE: nom.png]]` (+ texte OCR s'il y en a) au point d'apparition
   dans le corpus — pour qu'un LLM multimodal externe reçoive à la fois le
   corpus texte et les images, et sache où positionner sa description.

Nouveau module pur `core/embedded_images.py` (nommage/marqueur), nouveau
`ExtractedFile.embedded_images` (`EmbeddedImage(filename, data)`, en
mémoire jusqu'à la génération du corpus), nouveau `output/image_writer.py`
(écriture différée, dossier créé seulement s'il y a au moins une image).

**Rationale** :
- Retour utilisateur (test machine Windows réelle, v0.1.4) : PPTX avec
  texte dans une image (capture d'écran) mal extraits — « quasiement que
  les titres ». Confirmé sur le fichier cité par l'utilisateur
  (`atelier_camelia_managers_V0.4.pptx`, slide 7) : 214 Ko d'image
  contenant une conversation captée à l'écran, invisible avant D-091.
- Simplification trouvée en explorant le code : contrairement à l'OCR PDF
  (doit *rendre* une page vectorielle via `pypdfium2`), les images
  DOCX/PPTX sont déjà des fichiers image bruts dans le ZIP — aucune
  rastérisation nécessaire, les octets vont directement à
  `TesseractEngine.ocr_image()` (Tesseract/Leptonica détecte le format
  automatiquement). **Aucune nouvelle dépendance.**
- OCR automatique (pas de case à cocher) choisi pour rester cohérent avec
  l'OCR PDF déjà en place — le bug signalé se corrige sans que
  l'utilisateur ait à découvrir un nouveau réglage. L'export d'image, lui,
  écrit des fichiers en plus du corpus (seule fonctionnalité de DocFuse à
  le faire) — décision explicite de l'utilisateur de le garder désactivé
  par défaut.
- Portée v1 = DOCX + PPTX seulement. XLSX exclu : ses images sont ancrées
  via un XML de dessin séparé (`xl/drawings/`), jamais exposé par
  `openpyxl` en mode `read_only` (utilisé partout dans `extractors/xlsx.py`
  pour les gros classeurs) — surcoût disproportionné pour des images
  généralement décoratives (logos). Noté comme extension v1.1 possible.
- `Extractor.extract()`/`safe_extract()` gagnent un paramètre
  `extract_images: bool = False` (mécanique, comme D-089 sur 3
  extracteurs) — les 11 extracteurs qui ne l'utilisent pas reçoivent le
  paramètre sous un nom préfixé `_` (convention ruff ARG003 pour un
  argument volontairement ignoré) sans que cela gêne mypy --strict sur la
  compatibilité de signature avec la classe abstraite.
- Petit polish en passant : `OcrEngine.ocr_image(png_bytes, ...)` renommé
  en `image_bytes` — le nom suggérait à tort un format unique, alors que
  Tesseract/Leptonica accepte déjà PNG/JPEG/BMP/TIFF par ce même chemin.

### D-092 : erreurs JSON/XML corrompus clarifiées, `__MACOSX/` ignoré

**Décision** :
1. `JsonExtractor`/`XmlExtractor` capturent maintenant explicitement
   `json.JSONDecodeError`/`xml.etree.ElementTree.ParseError` avant le
   `except Exception` générique, et renvoient `t("error.corrupt_file")` +
   le détail ligne/colonne de l'exception plutôt que le nom brut de la
   classe d'exception Python.
2. `__MACOSX` ajouté à `IGNORE_DIRS` (`constants.py`), même liste que
   `node_modules`/`vendor`/`dist`/`build` (D-077).

**Rationale** :
- Trouvé en testant D-091 en conditions réelles (~/Documents,
  ~/Téléchargements, 1413 fichiers) : 3 erreurs JSON sur des fichiers
  `.json` réels.
- Deux causes distinctes, deux fixes différents :
  1. `wan22_corrected_workflow(1).json` / `wan22_corrected_workflow.json`
     (fichiers ComfyUI réels) : JSON réellement corrompu (double-encodage
     UTF-8 en amont produisant des octets qui cassent la syntaxe JSON,
     vérifié en inspectant le contenu brut). Le fichier reste en
     `FileStatus.ERROR` (rien n'est récupérable, correct de le signaler)
     mais le message passe de `JSONDecodeError: Expecting ',' delimiter:
     line 1 column 9951 (char 9950)` (incompréhensible pour un utilisateur
     non technique) à `Fichier corrompu : Expecting ',' delimiter: ...`
     (clair, avec le détail technique conservé pour qui veut localiser le
     problème). Réutilise `error.corrupt_file`, une clé i18n déjà présente
     mais jamais câblée jusqu'ici.
  2. `__MACOSX/._multiple_models_hiresfix_v1.json` : pas du JSON du tout —
     un fichier AppleDouble (métadonnées de resource fork) créé par macOS
     lors de la compression d'un ZIP, qui hérite du nom de l'original avec
     un préfixe `._`. Le signaler comme "fichier corrompu" aurait été
     trompeur (le vrai fichier JSON à côté, sans le préfixe, est
     parfaitement valide) — ignoré silencieusement comme les autres
     artefacts tiers déjà filtrés (D-077), pas une erreur.
- Non-régression : les 420 tests existants restent verts, 2 nouveaux tests
  d'extracteur (JSON/XML corrompus) + 1 nouveau test d'inventaire
  (`__MACOSX/` ignoré). Reproduit et confirmé corrigé sur les fichiers
  réels ayant révélé le bug.

### D-093 : mojibake, garde-fou zip, plausibilité d'encodage, EPUB, images XLSX/ODF

**Contexte** : après avoir testé D-091/D-092 en conditions réelles et
comparé la gestion de fichiers de DocFuse à celle d'un projet tiers pour
trouver des idées (sans copier de code, sans attribution dans aucun
artefact du dépôt — contrainte explicite de l'utilisateur), 5 pistes
retenues, une analysée sans implémentation.

**1. Réparation du mojibake (`ftfy`, nouvelle dépendance)** — `ftfy`
(Apache-2.0, dépendance unique `wcwidth` MIT — licences vérifiées) répare
les cas de double-encodage UTF-8/Latin-1 évidents. Nouvelle fonction
combinée `extractors/text.py::decode_text()` (détecte, décode, répare),
appliquée dans les 5 extracteurs qui partagent `detect_encoding()`
(text/markdown/csv_tsv/xml_json ×3/html), toujours avant tout parsing
structuré (JSON/XML) — un fichier corrompu peut ainsi redevenir valide au
lieu de finir systématiquement en `ERROR` (D-092). Jamais silencieux :
`extra_metadata["mojibake_repaired"]` trace toute modification, visible en
en-tête `## SOURCE:` et rapport, comme les notes existantes. **Testé sur
les 2 fichiers réels ayant motivé ce correctif**
(`wan22_corrected_workflow*.json`, D-092) : `ftfy` répare une partie du
texte (`decode_inconsistent_utf8`, `fix_character_width`) mais **ne suffit
pas à rendre ces 2 fichiers syntaxiquement valides** — leur corruption
combine plusieurs passes de mojibake sur du texte chinois, un cas plus
retors que le schéma simple testé unitairement. Honnêteté : ces 2 fichiers
précis restent en `ERROR` (message clair, D-092), mais `ftfy` reste une
amélioration nette pour le cas général (mojibake simple, plus fréquent).
**Faux positifs trouvés et corrigés en testant sur ~/Téléchargements — 3
passes successives, chacune re-testée en conditions réelles avant de
considérer le correctif terminé** : la configuration par défaut de `ftfy`
marquait ~145 fichiers non corrompus comme « réparés ». Trois causes
distinctes, chacune isolée en inspectant le diff caractère par caractère
d'un vrai fichier flagué avant de désactiver l'option correspondante :
1. `uncurl_quotes` : guillemets typographiques légitimes (`’`) convertis
   en guillemets ASCII (`'`) — normalisation cosmétique, pas une
   réparation. 145 → 79 fichiers après désactivation.
2. `fix_line_breaks` : CRLF converti en LF sur n'importe quel fichier
   texte, sans lien avec le mojibake — la gestion des fins de ligne est
   déjà un choix explicite du corpus généré (`line_ending=`), pas de
   l'extraction. 79 → 41 fichiers.
3. `fix_character_width` : cassait un littéral de chaîne JS listant les
   espaces Unicode (bundle minifié réel, `　` collapsé en espace
   ASCII simple) et convertissait la ponctuation chinoise pleine chasse
   légitime (`，`) en ASCII dans un JSON réel contenant du texte chinois.
   41 → 2 fichiers (Documents) / 39 (Téléchargements).
Restait ensuite un résidu attendu et accepté, pas un bug : la
normalisation NFC (conservée) fusionne U+2000/U+2001 (EN/EM QUAD) avec
U+2002/U+2003 (EN/EM SPACE) — des singletons canoniquement équivalents
selon Unicode lui-même, un comportement standard que fait tout logiciel
Unicode-aware, pas une perte de sens ; `fix_c1_controls` (partie de
`fix_encoding`, volontairement conservé) répare aussi de vrais octets
Windows-1252 égarés comme `\x85` → `…`, exactement le comportement
recherché. Seules les heuristiques de détection/correction d'encodage
réellement corrompu (famille `fix_encoding`) restent actives ; `ftfy.
TextFixerConfig(uncurl_quotes=False, fix_latin_ligatures=False,
fix_line_breaks=False, fix_character_width=False)`. 6 tests de
non-régression dédiés (guillemets/ligatures/CRLF/ponctuation
chinoise/espace pleine chasse légitimes préservés tels quels + réparation
cp1252 réelle toujours fonctionnelle).

**2. Garde-fou "bombe zip"** — nouveau `extractors/base.py::is_zip_bomb()`
(même emplacement que `is_ole_encrypted`) : ratio décompressé/compressé
(`ZIP_BOMB_MAX_RATIO`=200) **combiné à** un volume décompressé minimal
(`ZIP_BOMB_MIN_UNCOMPRESSED_BYTES`=300 Mo) — un petit fichier très
répétitif n'est jamais dangereux même avec un ratio élevé. Appelé en tout
début d'`extract()` dans DOCX/PPTX/XLSX/ODF/EPUB, avant tout parsing.
Nouvelle clé i18n `error.zip_bomb_suspected`.

**3. Validation de plausibilité après décodage cp1252** —
`extractors/text.py::_looks_plausible()` : ratio de caractères de contrôle
Unicode (catégorie `Cc`, hors tab/LF/CR) sur un échantillon
(`ENCODING_PLAUSIBILITY_SAMPLE_CHARS`=100 000 caractères, coût borné).
cp1252 accepte presque tous les octets — sans ce garde-fou, un fichier qui
échoue le test UTF-8 strict pour une raison anodine (séquence multi-octets
tronquée en fin de fichier) tombait directement sur un cp1252 potentiellement
mal choisi, sans jamais tenter `charset-normalizer`.

**4. Extracteur EPUB natif (`extractors/epub.py`, aucune nouvelle
dépendance)** — **découverte importante** : `ebooklib`, la bibliothèque
EPUB Python la plus évidente, est en **AGPLv3+** (vérifié sur PyPI) —
strictement interdite (règle 12.1). Implémentation native sur
`zipfile`+`ElementTree`+BeautifulSoup, même approche que `extractors/odf.py`
pour un format structurellement très proche (ZIP de XHTML/OPF). Pipeline :
`is_zip_bomb()` → `META-INF/container.xml` (chemin OPF) → OPF
(`<metadata>` titre/auteur → `extra_metadata`, `<manifest>` id→href,
`<spine>` ordre de lecture) → chaque chapitre XHTML extrait via le parcours
structuré déjà testé de `extractors/html.py::_extract_elements` (titres →
Markdown, tableaux, listes — réutilisé, pas dupliqué). DRM
(`META-INF/encryption.xml`) détecté explicitement → erreur claire
(`error.encrypted_epub`) plutôt qu'une tentative d'extraction sur du
contenu chiffré. Garde-fou de non-régression :
`test_ebooklib_not_a_dependency` (même esprit que
`test_mistral_common_not_a_dependency`).

**5. `.doc`/`.msg` — analyse seule, aucun code** : `extract-msg` (choix
évident pour `.msg`) est en **GPL**, interdit. `olefile` (BSD) donne accès
aux flux OLE2 bruts des deux formats mais aucune logique d'extraction de
texte prête à l'emploi et compatible licence — `.doc` nécessiterait de
décoder soi-même la "piece table" du format binaire Word 97-2003 (chantier
important, source d'erreurs) ; `.msg` (spec MS-OXMSG) est plus direct mais
reste à écrire de zéro. Conclusion : non recommandé maintenant, aucun
chemin propre/léger/conforme licence. Piste v1.2+ si des fichiers `.msg`
réels posent un jour problème (voir « Reste à faire » AGENTS.md).

**6. Extension de l'OCR/export d'images (D-091) à XLSX et ODF (odt/odp)** —
`openpyxl` en `read_only=True` (obligatoire pour les gros classeurs)
n'expose aucun dessin/image ; résolu en lisant le XML brut du ZIP,
exactement comme `_merge_ranges()`/`_apply_merged_cells()` le font déjà
dans ce même fichier pour les cellules fusionnées. Chaîne XML vérifiée
empiriquement (XLSX de test généré et inspecté) :
`sheetN.xml` → relation "drawing" → `drawingM.xml` (ancres
`oneCellAnchor`/`twoCellAnchor`, chacune avec un `<a:blip r:embed>`) →
relation "image" → média réel. Position : `sheet_{nom_feuille}`, marqueurs
regroupés **en fin de feuille** (pas d'ancrage cellule-par-cellule — la
position XML de l'ancre ne correspond pas forcément à une ligne "avec
données" du tableau pipe déjà généré, une fausse précision serait
trompeuse). ODF plus simple : `<draw:frame><draw:image xlink:href="...">`
donne le chemin ZIP direct, sans indirection par relation — hooké dans la
boucle `office_text.children` existante (odt, séquentiel) et
`_extract_presentation` (odp, `slide{i}` comme PPTX). `.ods` non traité
pour la position (comme XLSX, hors scope — feuilles de calcul, images
rarement porteuses de contenu). Même infrastructure que D-091
(`core/embedded_images.py`, `resolve_ocr_engine()`), aucun nouveau module.

**Vérification** : 452 tests (nouveaux : mojibake/plausibilité,
zip-bomb ×9, EPUB ×7, images XLSX ×3, images ODT/ODP ×5), ruff/mypy stricts
propres, recette 7/7 (92 extensions listées, +1 pour `.epub`). Re-testé sur
~/Documents + ~/Téléchargements (1413 fichiers réels) avec toutes les
nouvelles fonctionnalités actives simultanément.

### D-094 : support `.doc`/`.xls`/`.ppt`/`.msg` — révision de la conclusion D-093

**Contexte** : D-093 concluait qu'aucun chemin propre, léger et conforme
licence n'existait pour `.doc`/`.msg` (`extract-msg` GPL, `olefile` seul
insuffisant), basé sur les bibliothèques déjà connues (`antiword`, `wv` —
confirmées GPL par une recherche web dédiée). L'utilisateur a explicitement
demandé de rechercher plus loin, avec un budget clair (+100 Mo max, pas de
ralentissement du traitement) — recherche complémentaire qui a trouvé deux
bibliothèques ne figurant pas dans l'analyse initiale.

**Décision** :
1. **`.doc`/`.xls`/`.ppt`** (Word/Excel/PowerPoint 97-2003 binaires) via
   `office_oxide` (Rust/PyO3, double licence MIT/Apache-2.0, ~1,3 Mo par
   plateforme, auto-suffisant — aucun binaire externe, aucune JVM). Nouvel
   `extractors/legacy_office.py`, une seule classe enregistrée pour les
   trois extensions (API `extract_text()` identique quel que soit le
   format).
2. **`.msg`** (email Outlook) via `python-oxmsg` (MIT, même auteur que
   python-docx/python-pptx — Steve Canny —, dépendances `click` BSD-3 +
   `olefile` BSD déjà vétées + `typing_extensions`). Nouvel
   `extractors/msg.py`, réutilise `extractors/eml.py::_render_body()`
   (préférence texte, repli HTML→texte) plutôt que de dupliquer cette
   logique.

**Vérification avant adoption** (jamais de dépendance ajoutée sur la seule
foi d'une description marketing) :
- Licences vérifiées sur PyPI (métadonnées + classifiers) pour les deux
  paquets et leurs dépendances transitives — toutes MIT/Apache-2.0/BSD-3,
  aucune GPL/AGPL/LGPL.
- **Testé directement sur les fichiers réels de l'utilisateur** avant toute
  ligne de code d'extracteur : `plan_formation_codage_ia_v2.4_BETA.doc`
  (82 722 caractères extraits, accents et tableaux corrects),
  `EXOS BASES.xls` (plusieurs feuilles, nombres/texte corrects),
  `Téhou Suite réunion Sylvie.msg` (sujet/expéditeur/destinataires/date/
  corps tous corrects). `.ppt` testé sur un fichier de test synthétique
  (l'utilisateur n'en avait pas) généré via LibreOffice, disponible sur
  cette machine de dev — utilisé uniquement comme outil de génération de
  fixture ponctuel, jamais comme dépendance runtime du projet.
- Gestion d'erreur vérifiée : fichier manquant/corrompu → exception propre
  et catchable des deux côtés (`OfficeOxideError`, `FileNotFoundError`/
  `ValueError`), jamais de plantage ni de blocage — mappé sur
  `error.corrupt_file` (même principe que D-092).

**Fixtures de test** : `sample.doc`/`sample.xls`/`sample.ppt` générés via
LibreOffice (disponible sur cette machine) à partir des fixtures
`.docx`/`.xlsx`/`.pptx` déjà commitées, suivant exactement la convention
déjà en place (`tests/fixtures/generate_fixtures.py`). Pas de fixture
`.msg` committée — contrairement aux autres formats, il n'existe aucune
bibliothèque disponible ici pour EN ÉCRIRE un (`python-oxmsg` est
lecture seule, Outlook n'est pas disponible) ; la logique de
correspondance `Message → ExtractedFile` est testée via un double de
`Message` (`unittest`/`monkeypatch`), le parsing OLE2/MS-OXMSG lui-même
étant la responsabilité de `python-oxmsg`, déjà vérifié manuellement sur
un fichier réel.

**Point non vérifié, transparence assumée** : `office_oxide` est une
extension Rust compilée (binaire natif par plateforme) — contrairement à
`ftfy`/`python-oxmsg` (Python pur), son empaquetage par PyInstaller en
onefile Windows n'a pas pu être testé dans cette session (pas
d'environnement Windows/Wine disponible). Le spec PyInstaller
(`CorpusOne.spec`) n'a pas été modifié : `hiddenimports=
collect_submodules("docfuse.extractors")` couvre déjà `legacy_office.py`/
`msg.py`, et les dépendances compilées existantes du projet
(`pypdfium2`, `lxml`, `pillow`) n'ont jamais nécessité d'entrée
spécifique dans ce spec — hypothèse raisonnable que `office_oxide` suivra
le même chemin, à confirmer au prochain build de release. Filet de
sécurité déjà en place si l'hypothèse est fausse : un échec d'import
serait capté par `Extractor.safe_extract()` (garantie déjà existante,
`try/except Exception` généralisé) et isolé au fichier concerné, jamais un
crash de l'application entière.

**Vérification** : 12 nouveaux tests (6 legacy_office, 6 msg), garde-fous
de licence dédiés (`test_gpl_doc_tools_not_dependencies` — `antiword`/
`wvware`/`doctotext`/`textract` bannis), 471 tests passent, ruff/mypy
stricts propres, recette 7/7 (96 extensions, +4 pour `.doc`/`.xls`/`.ppt`/
`.msg`).

### D-095 : GUI — fenêtre maximisée sous Windows (boutons du bas toujours masqués)

**Décision** : la fenêtre démarre maximisée sous Windows
(`self.root.state("zoomed")`, dans un `try/except` qui ne doit jamais
empêcher le lancement de la GUI) plutôt que d'essayer de deviner une
nouvelle hauteur fixe en pixels. Hauteur par défaut aussi augmentée de
720 à 760 (minsize 600 → 640) pour compenser la 5e ligne d'options ajoutée
par D-091 (case « Exporter les images intégrées »), absente quand la
hauteur 720 avait été choisie en D-090.

**Rationale** :
- Retour utilisateur sur machine Windows réelle (v0.1.5) : les 3 boutons du
  bas (Générer, Rapport, Annuler) restent masqués une fois des fichiers
  chargés — précision de l'utilisateur : « il faut que j'agrandisse pour
  avoir les boutons », c'est-à-dire qu'ils redimensionnent manuellement la
  fenêtre pour les voir.
- Non reproduit dans cette session malgré un test ciblé et honnête :
  fenêtre relancée avec 59 fichiers réels chargés et la liste peuplée
  (`_populate_file_list()` appelé directement, pas seulement une fenêtre
  vide) — `file_rows_frame` reste correctement confiné dans le
  `CTkScrollableFrame` prévu à cet effet, les 3 boutons restent visibles.
  Cause la plus probable : mise à l'échelle DPI/police Windows qui
  agrandit chaque ligne au-delà de ce que le rendu Linux de cette session
  peut reproduire (même famille de cause que D-090 — jamais vérifiable
  sans machine Windows réelle).
- Plutôt que d'itérer sur des paris de hauteur en pixels (comme D-090 puis
  la première moitié de ce correctif), la fenêtre utilise tout l'espace
  écran disponible sous Windows — élimine la question "est-ce assez de
  pixels ?" quelle que soit la résolution/mise à l'échelle réelle de
  l'utilisateur. C'est exactement ce que l'utilisateur fait déjà
  manuellement. Comportement Linux/macOS inchangé (`sys.platform ==
  "win32"` uniquement) — pas de risque de régression sur le rendu déjà
  vérifié dans cette session.
- Honnêteté : comme D-090, ce correctif n'a pas pu être vérifié comme
  reproduisant exactement le symptôme réel — à confirmer par
  l'utilisateur.

---

*Fin du journal des décisions — Session 14.*
