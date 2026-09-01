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

### D-096 : audit qualité — lot 1, contenu perdu / plantages entiers (23 correctifs)

**Contexte** : audit demandé par l'utilisateur (« code haute qualité et
maintenabilité, chasse aux bugs, vitesse sans dégradation, refactoring si
besoin »). Méthode : 4 auditeurs en parallèle par zone du code, puis
**chaque finding reproduit sur un cas concret avant d'être retenu** (22
bugs confirmés, 0 accepté sur parole ; 2 findings « par lecture » vérifiés
en corrigeant). Plan en 4 lots (D-096 bugs, D-097 encodage, D-098
performance mesurée, D-099 maintenabilité). Constat général rassurant :
mypy strict, thread-safety, handles — sains. Les défauts se concentrent
sur trois classes : (a) contenu qui disparaît sans trace malgré la règle
12.4, (b) plantage entier sur un cas particulier au lieu d'une dégradation
locale, (c) code copié-collé qui a divergé.

**Décisions (une ligne par correctif, test de non-régression dans
`tests/test_regressions_d096.py`)** :

*Contenu perdu sans trace (règle 12.4)*
- `orchestrator.remove_file` : retirer l'original d'un doublon ne laissait
  que la note « identique à … » — le contenu réel disparaissait du corpus.
  Le premier doublon est promu (texte restauré, note retirée, autres
  doublons re-pointés, estimation recalculée).
- HTML : tout conteneur (`div`/`section`/`main`/`nav`…) était aplati par
  `get_text` — titres, tableaux et listes perdus sur quasi toute page
  réelle (le corps est toujours dans un `div`). Récursion si un descendant
  structuré existe. Impacte aussi l'EPUB (même parcours).
- HTML/ODF : `get_text(strip=True)` (séparateur vide) soudait les mots dès
  qu'un mot était en gras/lien (`HelloWorldagain`, `Bonjourmondeentier`).
  Helper partagé `html.tag_text()` (séparateur espace + compaction,
  tabulations et retours à la ligne préservés) ; en ODF, `text:s`/
  `text:tab`/`text:line-break` matérialisés en caractères avant lecture.
- ODF : tout enfant de `office:text` autre que table/p/h/list était
  ignoré en silence (`text:section` — mise en page multi-colonnes, très
  courant —, cadres, index) ; `"table" in nom` envoyait `table-of-content`
  vers un parseur de tableau vide. Correspondance exacte, récursion dans
  les conteneurs, branche finale qui émet le texte de tout inconnu.
- `.ods` : tombait dans le repli générique, une cellule par ligne (lignes/
  colonnes perdues). Traitement dédié `office:spreadsheet`, même rendu que
  XLSX.
- DOCX : zone de texte émise 2× (une fois inline via `iter()`, une fois par
  `_extract_textboxes`) avec les mots collés ; Word 2010+ double encore par
  `mc:Fallback`. `_flatten_paragraph_text` saute `w:txbxContent` et
  `mc:Fallback` (parcours à pile explicite) ; `_extract_textboxes` est
  l'unique émetteur, paragraphes joints par `\n`. Notes de bas de page/fin
  : `_flatten_paragraph_text` par `w:p` (cohérent D-069, plus de
  `w:delText`), et lecture sur les parties déjà chargées par python-docx
  (`_part_element`) — plus de BeautifulSoup ni de réouverture du ZIP dans
  `docx.py` (perf comptée en D-098).
- DOCX : en-tête/pied « lié au précédent » répété à chaque section (×N).
  `is_linked_to_previous` → ignoré.
- EPUB : item du spine introuvable (href percent-encodé `chap%201.xhtml`,
  Calibre/Sigil) sauté en silence, READY. `unquote()` puis note
  `epub_skipped_items` visible en-tête SOURCE/rapport.
- EML : une pièce jointe `text/plain` prenait la place du corps HTML ;
  `Cc` et noms de PJ jamais rendus. `Content-Disposition: attachment`
  exclu du corps, `Cc` + `[pièces jointes : …]` rendus (comme `msg.py`).
- Inventaire : `build/`, `dist/`, `vendor/`, `node_modules/`, `.git/`,
  `__MACOSX/` élagués sans apparaître dans le rapport (CdC §7.1 ; `build/`
  et `dist/` sont aussi des noms de dossiers documentaires). Une entrée
  ignorée par dossier élagué (`inventory.ignored_dir`). `.gitignore` retiré
  de la liste des « dossiers » VCS (nom de fichier).
- PDF (D-086) : le nettoyage du texte poubelle `(cid:…)` ne s'appliquait
  que sans moteur OCR ; quand l'OCR échoue, le bruit restait. Helper
  `_blank_if_garbage` partagé par les deux branches.

*Plantage entier sur un cas particulier*
- XLSX : une feuille graphique (`Chartsheet`) → `AttributeError` → tout le
  classeur en ERROR, données perdues. Détectée (`hasattr(iter_rows)`) et
  signalée `[Feuille graphique — pas de cellules]`. Classeurs fermés via
  `closing()` (fuite de handles sur le chemin d'erreur).
- `pdf_writer` : en-tête SOURCE non échappé → `a<b>.txt` faisait échouer
  toute la génération PDF. `xml.sax.saxutils.escape` partout.
- `inventory` : `sort="mtime"` plantait `run_analysis` sur un lien
  symbolique cassé (`stat()` dans la clé de tri). `_safe_mtime` → 0.
- `config.py` : `"context_limit": "abc"` → `ValueError` non rattrapé → la
  GUI ne s'ouvrait plus ; `"exclude_globs": "*.log"` → `['*','.','l','o',
  'g']` → tout exclu sans indice ; `"recursive": "false"` → `True`.
  `ValueError` rattrapé (retour aux défauts, config neuve), `_as_str_list`,
  `_as_bool` strict. **`Config.validate()` existait mais n'était appelé
  nulle part** : CLI → exit 1 avec message, GUI → journal + défauts.
- EML/MHTML : charset inconnu de Python (`unknown-8bit`, fréquent dans
  les bounces) → `LookupError` → tout l'email en ERROR. `eml.part_text()`
  : repli payload brut + `decode_text()` (apporte aussi la réparation
  mojibake à EML/MHTML).
- XML : déclaration `encoding=` ignorée (même défaut que D-073 pour HTML)
  → charabia READY sur du `windows-1251` ; commentaires supprimés au
  pretty-print. `_decode_xml` honore la déclaration ;
  `TreeBuilder(insert_comments=True)`.
- RTF : un seul `\'81` (octet indéfini en cp1252) → `UnicodeDecodeError`
  pour tout le fichier. `errors="replace"`.
- CSV : champ > 131 072 caractères → fichier entier en ERREUR.
  `csv.field_size_limit(sys.maxsize)`.
- PDF/OCR : plafond de pixels vérifié *après* le rendu — la bitmap était
  déjà allouée (page A0 ≈ 250 Mo, page hostile plusieurs Go) ; un OOM est
  un SIGKILL non rattrapable, même classe que D-078. `page.get_size()`
  avant `render()`.
- PPTX : `<a:br/>` rendu `\x0b` (tabulation verticale) par python-pptx,
  laissé tel quel dans le Markdown. `_clean_text` → `\n`.

*Interface*
- **Le glisser-déposer n'a jamais fonctionné** : `tkinterdnd2` greffe les
  méthodes Python mais le paquet Tcl `tkdnd` n'est chargé que par
  `TkinterDnD.require(root)`, jamais appelé → `TclError: invalid command
  name "tkdnd::drop_target"`, avalé par un `except`, message « fallback
  sur bouton uniquement » à chaque lancement (visible dans toutes les
  sessions de test GUI de ce projet, jamais relevé). `_load_tkdnd()` à la
  création de la fenêtre ; les deux specs PyInstaller embarquent désormais
  `collect_data_files("tkinterdnd2")` (sans quoi l'exe n'aurait pas la
  bibliothèque Tcl même une fois `require` appelé — aucun hook PyInstaller
  n'existe pour ce paquet). Vérifié en direct sur l'affichage de cette
  session : `_dnd_enabled == True`, paquet `tkdnd` présent.
- GUI Générer/Rapport : une exception partait vers `stderr`, inexistant en
  exe fenêtré — le clic semblait ne rien faire. `try/except` +
  `gui.generation_failed_detail`. Le dialogue « Rapport » avec `rapport.
  json` écrivait le Markdown dans le `.json` puis l'écrasait — Markdown
  toujours dans `.md`, JSON dans `.json`.
- Markdown CRLF : seules les jointures entre blocs prenaient CRLF, l'en-
  tête et le texte gardaient LF → fichier mélangé (18 CRLF + 11 LF mesurés).
  Normalisation en `\n` puis une seule conversion. `zip(strict=True)` dans
  le writer Markdown (le PDF l'était déjà) et alignement `files/estimates`
  vérifié bruyamment dans `report.py` au lieu d'un repli silencieux.

**Vérification** : 499 tests (28 nouveaux), ruff/mypy --strict propres,
recette 7/7 ; les 23 reproductions rejouées contre le code corrigé.

### D-097 : audit qualité — lot 2, encodage et réparation mojibake

**Décisions** (tests dans `tests/test_regressions_d097.py`) :
- **ftfy, 4 options cosmétiques de plus désactivées** — suite de D-093
  (qui en avait déjà écarté 4), trouvées en reproduisant l'audit :
  `unescape_html="auto"` décodait les entités (`&amp;` → `&`) ligne par
  ligne, donc un JSON sain était réécrit *avant* `json.loads` et de façon
  incohérente dans un même fichier (une ligne contenant `<` désactive
  l'option pour la suite) ; `remove_terminal_escapes` et
  `remove_control_chars` retiraient les codes ANSI (ESC) d'un `.log` ;
  `normalization="NFC"` réécrivait du texte NFD légitime. Ne restent que
  la famille `fix_encoding` (`decode_inconsistent_utf8`, `fix_c1_controls`,
  `replace_lossy_sequences`) et `fix_surrogates` — l'unique mission de la
  fonction est la corruption d'encodage, rien d'autre.
- **Chemin rapide ASCII, sortie identique** : avec cette configuration,
  aucune heuristique restante n'agit sur de l'ASCII pur →
  `if text.isascii(): return text`. Mesuré : 2,39 s → 0 ms sur 200 000
  lignes de code ASCII (identité d'objet), 0,37 s sur 900 k caractères
  français non-ASCII (contenu inchangé). Payé auparavant par tout
  `.py/.log/.json/.csv/.md`.
- **UTF-8 « presque » valide** (`_is_nearly_utf8`, seuil
  `ENCODING_MAX_UTF8_REPLACEMENT_RATIO` = 0,1 %) : une seule séquence
  multi-octets tronquée (fichier coupé, log tourné au milieu d'un
  caractère) faisait échouer le test UTF-8 strict ; cp1252 « réussissait »
  alors et TOUT le fichier sortait en `Ã©`, puis ftfy le « réparait » et le
  signalait comme mojibake — doublement trompeur (mauvais encodage
  rapporté, caractère tronqué survivant). Désormais : UTF-8 avec un U+FFFD
  local.
- **`_looks_plausible` : docstring corrigée**. Elle promettait de détecter
  « un UTF-8 tronqué pris pour du cp1252 » — impossible : cp1252 lève sur
  ses 5 octets indéfinis et ne produit jamais de caractère de contrôle
  pour les autres octets hauts. Ce que le ratio détecte réellement : des
  octets de contrôle ASCII bruts en rafale (binaire, UTF-16 sans BOM). Le
  cas promis est maintenant traité par `_is_nearly_utf8`. Le garde-fou est
  conservé pour ce qu'il fait vraiment.
- **HTML sans charset déclaré** : `UnicodeDammit` consultait le devineur
  statistique avant d'essayer UTF-8/cp1252 — une page cp1252 sans
  `<meta charset>` ressortait en `johab` (balise fermante mangée), une page
  française en `windows-1250` (à/è/ù faux). La déclaration reste
  prioritaire (D-073) ; en son absence, `detect_encoding()` (UTF-8 strict →
  presque-UTF-8 → cp1252 plausible → charset-normalizer) remplace la
  devinette.

**Vérification** : 507 tests (8 nouveaux), ruff/mypy --strict propres,
recette 7/7.

---

### D-098 : audit qualité — lot 3, performance à sortie strictement identique

**Contexte** : référence mesurée avant le lot — ~/Documents (120 fichiers)
en **28,4 s** ; le seul PPTX de 44 images en **21,0 s** (OCR séquentiel,
~0,5 s par image). Tesseract est mono-thread par processus et non lié à
OpenMP (vérifié `ldd`) : le parallélisme par processus scale linéairement
(8 appels : 2,0 s → 1,0 s). Contrainte posée par l'utilisateur : « sans
dégradation » — prouvée, pas affirmée : le `corpus.md` généré sur
~/Documents avant/après le lot (ligne d'horodatage normalisée) est
**identique byte à byte**, avec le même nombre d'images exportées (111).

**Décisions** (tests dans `tests/test_regressions_d098.py`) :
- **OCR des images intégrées parallélisé à l'intérieur d'un fichier**
  (`core/embedded_images.py::ImageBatch`). Les extracteurs docx/pptx/xlsx/
  odf **collectent** les images pendant leur parcours (`batch.add(tag,
  octets)` renvoie un jeton `\x00IMG:n\x00` posé à la place du futur
  marqueur), puis `batch.run()` fait l'OCR de tout le fichier via un
  `ThreadPoolExecutor` et `batch.apply(parts)` substitue les marqueurs
  **dans l'ordre du document** (les résultats sont rangés par index, pas
  par ordre d'arrivée — testé avec un moteur factice qui répond dans le
  désordre). Un marqueur vide (OCR sans texte, export désactivé) retire
  son jeton, ce qui conserve la règle « diapo/cellule sans texte » telle
  qu'avant (`apply` par diapo pour PPTX/ODF, par feuille pour XLSX ;
  `take()` pour la cellule DOCX qui résout localement). Ce helper remplace
  les 4 copies de la logique tag→OCR→marqueur→`EmbeddedImage`. Mesuré :
  PPTX de 44 images **21,0 s → 3,0 s** (44 marqueurs identiques).
- **Un seul plafond global de processus Tesseract** :
  `core/ocr/registry.py::OCR_SLOTS` (`BoundedSemaphore(OCR_MAX_CONCURRENCY)`)
  et `ocr_with_slot()` partagés par `ImageBatch` et `pdf._ocr_pages`. Avant,
  4 workers × 4 pages OCR pouvaient lancer 16 processus non bornés.
  `OCR_MAX_CONCURRENCY = max(2, min(8, cpu_count))` ; `OCR_PAGE_TIMEOUT_S`
  (documenté mais jamais lu) remplace le délai en dur de `tesseract.py`.
- **`MAX_WORKERS` dérivé du CPU** (4 → `max(2, min(8, cpu_count))`) —
  docstring corrigée : le travail est CPU-bound, pas IO-bound (mesuré seul
  29 s → 26 s ; le vrai gain vient du chemin critique libéré par le point
  précédent). Total ~/Documents : **28,4 s → 10,6 s**.
- **XLSX : la feuille XML était décompressée et parsée 7 fois par feuille**
  (mesuré en instrumentant `ZipFile.open`). Le XML brut, déjà lu pour
  `_merge_ranges`, est lu une fois et réutilisé ; s'il ne contient aucun
  `<f>`/`<f ` /`<f/`, `ws_formulas` n'est pas consulté pour cette feuille
  — identique par construction : seules les cellules `None` le consultent,
  et sans balise `<f` il ne peut rendre que `None`. `closing()` sur les
  deux classeurs (fuite sur le chemin d'erreur).
- **DOCX : ZIP ouvert 6 fois et `document.xml` re-parsé par BeautifulSoup**
  (≈10× plus lent que le parse lxml déjà en mémoire). Zones de texte,
  notes de bas de page/fin et en-têtes sont parcourus sur les arbres lxml
  chargés par python-docx (`doc.part.package.iter_parts()`) ; bs4 disparaît
  de `docx.py` — et c'est le même code que le correctif D-096 des zones de
  texte dupliquées.
- **PDF : `PdfReader(str(path))` recopiait tout le fichier en mémoire**
  (vérifié dans pypdf 6.16) pour lire `/Encrypt` → `with path.open("rb")`.
- **GUI : cache des estimations par moteur** (`OrchestratorResult.
  _estimates_by_engine`) — changer le moteur de comptage re-tokenisait tout
  le corpus sur le thread Tk (≈11 Mo/s pour Mistral → gel). Le cache est
  aligné sur `files` dans `remove_file` (et purgé quand un doublon est
  promu, D-096). **Saisie du plafond débouncée** (`_LIMIT_DEBOUNCE_MS` =
  250 ms) : la table n'est plus reconstruite à chaque frappe.
- **Inventaire : un seul parcours** (`inventory._walk_source`) renvoyant
  `(trouvés, ignorés)` là où `scan_directory` + `list_ignored` marchaient
  et triaient chaque source deux fois (`stat()` ×2 en tri par date).

**Rejeté** : mise à jour en place des lignes de la table GUI et génération
dans un thread worker — gains réels sur de grands dossiers mais intrusifs,
notés « Reste à faire » (v1.1).

**Vérification** : 513 tests (6 nouveaux), ruff/mypy --strict propres,
recette 7/7, corpus ~/Documents identique byte à byte, 111 = 111 images.

---

### D-099 : audit qualité — lot 4, maintenabilité et cohérence

**Contexte** : dernier lot de l'audit. Les auditeurs avaient relevé du code
copié-collé qui avait divergé (classe (c) du constat général) : garde
conteneur ×5, note mojibake ×6, écriture des rapports ×3 avec deux appels à
neuf arguments, chemins de sortie différents entre CLI et GUI, littéraux
magiques (`"CorpusOne_output"`, `"_rapport"`, `1_000_000`, couleurs, `20`,
`12`). En factorisant, trois vrais bugs sont apparus — c'est l'intérêt d'un
lot « maintenabilité » : la duplication cache des divergences.

**Décisions** (tests dans `tests/test_regressions_d099.py`) :
- **Politique unique `file_type`** = `extractors.base.file_type_for(path)`
  (extension normalisée). Avant, un résultat READY portait l'extension
  (`odt`, `yaml`) et un résultat ERREUR le nom de famille de l'extracteur
  (`odf`, `xml_json`) : le même fichier changeait de type dans le rapport
  selon l'issue. **Bug révélé** : `markdown_writer` comparait `file_type`
  à `("markdown", "text", "csv_tsv", …)` — mort depuis M-08 (`md` ≠
  `markdown`), donc un `.md` contenant des ``` était encapsulé dans des
  backticks malgré le CdC §7.3. Remplacé par `VERBATIM_EXTENSIONS`
  (constante documentée) sur `extension`. L'attribut de classe
  `Extractor.file_type` disparaît ; `error_result(path, relative_path,
  exc)` perd son argument.
- **`base.py`** : `container_guard(path, relative_path, check_ole=True)`
  (OLE chiffré + bombe zip) remplace ~22 lignes copiées dans docx/pptx/
  xlsx/odf/epub ; `error_result_message()` remplace les huit littéraux
  `ExtractedFile(... status=ERROR ...)`.
- **`text.py`** : `decode_text_with_note()` / `mojibake_metadata()` —
  la note de transparence n'est construite qu'à un endroit.
- **`core/report.py::write_report_pair(result, base_path)`** : écrit
  toujours `.md` ET `.json`, plafond/marge/moteur lus sur le résultat
  (une seule source de vérité), crée le dossier cible. Remplace trois
  copies (CLI, GUI, orchestrateur). `generate_corpus(result, output_path)`
  perd ses paramètres `context_limit`/`margin` en doublon de `result.*`.
- **`output/paths.py`** : `corpus_extension()`, `default_corpus_path()`,
  `report_base_path()` + constantes `OUTPUT_DIR_NAME`, `REPORT_SUFFIX`,
  `CORPUS_EXTENSIONS`. **Divergence corrigée** : pour un fichier seul en
  entrée, la CLI écrivait `corpus.md` dans le dossier courant, la GUI dans
  `<dossier du fichier>/CorpusOne_output/` — même règle désormais.
- **GUI, fonctions pures testables** (même esprit que `sort_file_pairs`) :
  `parse_context_limit()` (**bug révélé** : blocage, compteur et résumé
  pouvaient lire trois plafonds différents selon la validité de la
  saisie), `gauge_color()`, `build_summary_lines()` (réutilise
  `result.block_reason` au lieu de le reconstruire) ; `_set_phase(idle|
  analyzing|done)` centralise six sites de `configure(state=…)` ;
  `_refresh_from_result()` centralise quatre séquences table/compteur/
  résumé/bouton ; trace sur `format_var` (le bouton « Générer corpus.md »
  ne suivait pas le choix PDF).
- **CLI** : `--input` manquant → code 1 (avant : `parser.error()` → code 2,
  réservé au blocage plafond) ; `--output notes.txt` → message clair et
  code 1 (avant : création d'un dossier `notes.txt/`).
- **Orchestrateur** : `OrchestratorResult.cancelled` + retour immédiat
  après annulation (les étapes 3 à 6 tournaient sur un résultat jeté) ;
  `ProgressEvent.current` = nombre de fichiers terminés (compteur
  monotone — l'index d'inventaire faisait reculer la barre) ; note
  « secrets potentiels » groupée par type et plafonnée
  (`SECRETS_NOTE_MAX_LINES_PER_KIND` = 10 : un journal de 40 000 jetons
  produisait une note de 1,5 Mo, 29 % des tokens du fichier) ;
  `dedupe_image_filenames()` renomme les images exportées homonymes
  (`A/rapport.docx` + `B/rapport.docx`) **et** leur tag dans le texte —
  avant, la seconde écrasait la première en silence.
- **Divers** : `to_dict()` expose `embedded_images_count` ; `i18n` met en
  cache un catalogue absent (un avertissement, pas un par appel) et
  retombe sur `DEFAULT_LANG` pour une clé manquante ; 10 clés i18n mortes
  retirées (FR et EN restent alignés) ; `_walk_figure()` fusionne les deux
  parcours symétriques du PDF ; `chars_per_page` retiré du tuple de
  `_extract_pages_pdfminer` (recalculé et jamais lu) ;
  `HEADER_ESTIMATE_MAX_ITERATIONS`, `MAX_TRAVERSAL_DEPTH`,
  `UNUSUAL_CONTEXT_LIMIT`, `GAUGE_COLORS`, `PENDING_COLOR` remplacent les
  littéraux.

**Rejeté / reporté** (« Reste à faire ») : mise à jour en place des
lignes de la table GUI, génération dans un thread worker, faux positifs
du scanner de secrets sur des identifiants de code, sniff d'un `.doc` qui
est en réalité du RTF/HTML — intrusifs ou non reproduits, hors audit.

**Vérification** : 532 tests (19 nouveaux), ruff/mypy --strict propres,
recette 7/7 ; GUI relancée sur l'écran réel (glisser-déposer actif, trois
phases de boutons cohérentes, bouton « Générer » suivant le choix PDF).
Fin de chantier de l'audit (D-096 à D-099) : `run_analysis` sur
~/Documents + ~/Téléchargements avec OCR et export d'images — **1 417
fichiers** (1 413 au run D-094, 4 fichiers ajoutés depuis), 1 210 READY,
116 images, 89 peu de texte, **2 erreurs** (les deux JSON `wan22_*`
corrompus connus depuis D-092, 3 à l'époque), 1 207 ignorés, 2 581 images
exportées, corpus de 114 Mo avec 1 415 blocs SOURCE (= 1 417 − 2), 399 s.

---

### D-100 : en-tête de page PDF avec le fichier source — le PDF pour les assistants à recherche

**Contexte** : l'utilisateur a rejoué les 7 prompts de diagnostic (voir
D-095) dans un assistant d'entreprise tiers, cette fois avec le corpus
**PDF** de DocFuse au lieu du `.md` : résultat nettement meilleur (≈ 4/7
contre un quasi-échec), sans être fiable — la LLM locale à contexte long
fait 7/7 sur le `.md`. L'assistant décrit lui-même sa méthode : il découpe
le PDF **page par page** en « passages » avec métadonnées. Or
`pdf_writer` fait un saut de page entre chaque source : les passages d'un
PDF sont alignés sur les fichiers, ceux d'un `.md` (découpage à taille
fixe) sont à cheval sur deux `## SOURCE:` et perdent leur attribution. Les
erreurs restantes (« premier fichier » faux, « ligne précédente » qui est
en réalité 12 lignes après) sont des artefacts de découpage/recherche.

**Décision** : rendre chaque page du PDF autoporteuse. L'en-tête de page
inscrit désormais `Corpus DocFuse — <fichier> (i/N)` (clé i18n
`corpus.source_position`, chemin raccourci par la gauche au-delà de
`PDF_PAGE_HEADER_MAX_CHARS`) à côté du numéro de page. Implémentation :
un flowable invisible `_SourceMarker` avant chaque en-tête SOURCE, un
gabarit `_CorpusDocTemplate` qui note le dernier marqueur vu
(`afterFlowable`) et dessine l'en-tête en fin de page (`afterPage`) —
comme chaque source commence sur une nouvelle page, une page ne contient
jamais qu'un fichier, le dernier marqueur est le bon. `SimpleDocTemplate`
+ `onPage` ne convenait pas : `onPage` est appelé en *début* de page,
avant les flowables, donc avec le fichier de la page précédente.

**Documentation** : nouvelle section README FR/EN « Quel format pour quel
outil ? » — Markdown pour un LLM qui reçoit le fichier entier, PDF pour un
assistant qui indexe et répond par recherche, avec la limite explicite :
un tel assistant ne lit jamais tout le corpus, DocFuse garantit le fichier
produit, pas ce que l'outil aval choisit d'en lire. Aucun outil tiers n'est
nommé.

**Rejeté (pour l'instant)** : option « repères RAG » dans le Markdown
(ligne d'ancrage `[[SOURCE: fichier — page N]]` à chaque page et tous les
~80 lignes) — proposée à l'utilisateur, en attente de décision ; coût en
tokens inutile pour une LLM à grand contexte, donc jamais par défaut.

**Vérification** : `tests/test_pdf_page_header.py` (pypdf relit le PDF
généré : chaque page porte son fichier, jamais celui du voisin ; chemin
long raccourci), suite complète verte. Test réel avant v0.1.6 sur
~/Documents + ~/Téléchargements (1 417 fichiers, OCR + export) : Markdown
identique octet pour octet au run de fin d'audit (114,8 Mo, 1 s) ; PDF de
**38 649 pages** (75 Mo, 1 675 s — ReportLab, sans optimisation) relu par
pypdf : 60 pages tirées au hasard portent toutes leur en-tête `fichier
(i/1415)`, première page `(1/1415)`, dernière `(1415/1415)`.

---

### D-101 : découpage par budget de tokens — plusieurs corpus au lieu d'un blocage

**Contexte** : reprise du projet Doc-IA (analyse RGPD/finance/sécurité/
juridique de partages de fichiers par LLM). L'analyse du 30/08/2026
(`~/Doc-IA/docs/ANALYSE_2026-08-30.md`) retient DocFuse comme brique
d'extraction **sur le poste** : le texte des documents est envoyé à la LLM
par blocs de 16–64K tokens, en JSON structuré multi-fichiers, avec
`## SOURCE:` comme clé de corrélation. Or le CdC v1 (§10.3) **bloque** dès
que le total dépasse le plafond, et le découpage automatique était
explicitement hors périmètre (CdC, « hors périmètre v1 »). Un pipeline de
milliers de fichiers ne peut pas s'arrêter sur un code 2.

**Décision** : un mode « découpage » (`split_context`), **désactivé par
défaut** (le comportement CdC reste inchangé), qui remplace le blocage par
une répartition des fichiers extraits en parties successives sous le
plafond :

- remplissage **séquentiel** dans l'ordre du tri (first-fit) — jamais de
  bin-packing qui réordonnerait les fichiers, l'ordre du corpus reste celui
  de l'inventaire ;
- **un fichier n'est jamais coupé** — la garantie « chaque `## SOURCE:` est
  un fichier entier » est ce qui permet à la LLM de rendre un JSON par
  fichier ;
- un fichier qui dépasse à lui seul le plafond est **isolé dans sa propre
  partie et signalé** (`CorpusPart.oversized`, préambule, rapport) — jamais
  abandonné en silence (règle 12.4). Le consommateur décide (plafond plus
  grand, retrait), DocFuse ne décide pas à sa place.

Implémentation : `core/splitter.py` (module **pur**, `split_by_budget()`
retourne des indices dans `result.files`), `OrchestratorResult.split_context`
qui neutralise `recompute_blocking()` (statuts jamais `TOO_LARGE`,
`oversized_files` exposé), writers MD/PDF qui acceptent une `part`
(`selected_files()` partagé), `generate_corpus_parts()` qui écrit
`<stem>_001.<ext>`… et un rapport unique enrichi (`parts`, `part` par
fichier). `generate_corpus()` délègue en mode découpage pour ne pas casser
les appelants bibliothèque. Le préambule de chaque partie porte
« Partie i/N » et ses totaux. Le budget comparé au plafond est la **somme
des `tokens_with_margin` par fichier** (en-tête SOURCE comprise) — plus
conservateur que l'agrégat `approx` recalculé sur les octets, ce qui est le
bon sens pour un budget.

**Rejeté** : découper un fichier trop gros en morceaux (perd la
correspondance fichier ↔ JSON, et un morceau sans son contexte est une
perte de sens silencieuse) ; bin-packing optimal (réordonne, gain marginal
sur des blocs de 16–64K).

**Vérification** : `tests/test_core/test_splitter.py` (16 tests : first-fit,
fichier hors plafond isolé, jamais de blocage, bascule du mode, fichiers non
extraits ignorés, chaque `## SOURCE:` exactement une fois sur l'ensemble des
parties, rapport, PDF, délégation, dossier de sortie créé). CLI réel sur
`tests/fixtures` avec `--context 300` : 4 parties, code 0 ; sans l'option,
blocage, code 2.

---

### D-102 : fin du nom de code « CorpusOne » — `branding.py` et `DOCFUSE_APP_NAME`

**Contexte** : « CorpusOne » était le nom de code initial ; le projet et le
dépôt s'appellent DocFuse, mais l'exécutable, le dossier de sortie, la
config, le journal et les specs portaient encore l'ancien nom, écrit en dur
à six endroits du code (`constants.py`, `config.py` ×3, `cli.py` ×2,
`pdf_writer.py`), dans trois clés i18n, les specs, la CI et `build.sh`.
L'utilisateur veut un nom paramétrable (distribution interne).

**Décision** : un module `branding.py`, **seul** endroit qui connaît le
nom : `APP_NAME` (défaut `DocFuse`, surcharge par la variable
d'environnement `DOCFUSE_APP_NAME`, validée comme nom de fichier portable
— un nom invalide retombe sur le défaut, jamais d'échec au lancement) et
tous les dérivés (`OUTPUT_DIR_NAME`, `CONFIG_FILENAME`, `APPDATA_DIR_NAME`,
`LOG_DIR_NAME`, `LOG_FILENAME`, `OCR_VARIANT_NAME`, `PDF_AUTHOR`). Les
specs PyInstaller lisent la même variable pour `name=` — un seul nom pour
l'exe, le dossier de sortie et la config. Les clés i18n concernées
prennent un placeholder (`{app}`, `{variant}`) : le nom n'est pas du texte
d'interface. Les specs sont renommés `DocFuse.spec` / `DocFuse-OCR.spec`.

**Compatibilité ascendante** : `config._config_paths()` lit en repli
`CorpusOne.json` et `%APPDATA%/CorpusOne/config.json` (jamais écrits) ;
`IGNORE_PATTERNS` garde `corpusone_report.*`. Le nom hérité vit dans
`branding.LEGACY_*` uniquement.

**Garde-fou** : `tests/test_branding.py` échoue si un fichier `.py` du
paquet (hors `branding.py`) ou un catalogue i18n contient encore
« CorpusOne » — la dette ne peut pas revenir.

**Rejeté** : garder `CorpusOne_output` par défaut « pour ne rien casser » —
les utilisateurs 0.1.x sont peu nombreux, la 0.2.0 est marquée BREAKING
(nommage) dans le CHANGELOG, et la lecture en repli couvre la config.

---

### D-103 : l'interface graphique devient un extra `[gui]`

**Contexte** : pour servir de bibliothèque (analyzer Doc-IA v3, service
d'extraction) DocFuse tirait `customtkinter` et `tkinterdnd2` — donc Tk —
sur des machines sans écran ; et le README montrait un exemple
« bibliothèque » faux depuis D-099.

**Décision** : `customtkinter` et `tkinterdnd2` passent dans
`[project.optional-dependencies] gui` ; `__main__` sans argument affiche un
message i18n clair si la GUI est absente (au lieu d'un
`ModuleNotFoundError`). CI, specs et `build.sh` installent `.[dev,gui]`.
Ajout de `py.typed`. README corrigé et complété (découpage, branding).

**Vérification** : suite complète (555 réussis), `mypy --strict`, recette
7/7 ; l'exe Windows n'est pas buildé localement (voir « Reste à faire »
d'AGENTS.md : vérifier `DOCFUSE_APP_NAME` au prochain build CI).

---

### D-104 : `.msg` Outlook — aucune propriété lue sans garde

**Contexte** : bug de production sur le serveur Windows de l'utilisateur.
Des dossiers entiers de mails Outlook sortaient en `ERREUR`, deux causes
distinctes, toutes deux systématiques :

* `_attachment_name()` lisait `Attachment.long_filename` — attribut qui
  **n'existe dans aucune version de `python-oxmsg`** (l'API réelle est
  `file_name`, `PidTagAttachLongFilename`). Tout mail portant une pièce
  jointe levait `AttributeError` ;
* `Message.body` lève `UnicodeDecodeError` quand le corps est un
  `PtypString8` dont la code page annoncée (souvent 65001/UTF-8) ne
  correspond pas aux octets stockés — cas systématique des mails français
  écrits en cp1252 (é, è, à, €). Ce n'est pas une exception au chargement :
  les propriétés d'oxmsg sont paresseuses, le mail s'ouvre puis casse à la
  lecture du champ.

**Décision** : « aucun `.msg` ne doit faire échouer l'extraction ». Chaque
propriété est lue défensivement (`_safe()`), et une propriété texte qui lève
déclenche une **relecture du flux brut** dans le conteneur OLE2
(`Message._storage.property_stream_bytes(pid, ptyp)`), court-circuitant le
décodage d'oxmsg et sa code page mensongère. Au pire un champ manque, jamais
le fichier entier.

**Rejeté** : patcher `python-oxmsg` (dépendance tierce, mise à jour
impossible côté client) ; déclarer ces mails en erreur (règle 12.4 — jamais
de perte silencieuse, mais surtout ici : le contenu est parfaitement
récupérable).

**Vérification** : `tests/test_extractors/test_msg.py::TestMsgRobustness` —
pièce jointe via l'API réelle, pièce jointe sans nom, nom qui lève, corps
cp1252 relu du flux brut, HTML binaire relu, corps définitivement illisible
(le mail reste `READY`), destinataire illisible, pièces jointes annoncées
mais illisibles.

**Suite** : la relecture critique de ce correctif a trouvé qu'il laissait
passer exactement la classe de défaut qu'il visait — voir D-106.

---

### D-105 : OCR — échecs diagnosticables, pages géantes lues, console silencieuse

**Contexte** : trois défauts remontés par le même audit en conditions
réelles (serveur Windows), tous invisibles depuis le poste de développement.

**Décision** :

1. **Langue** — `OCR_LANG = "fra+eng"` fait sortir Tesseract en **code 1
   pour chaque page** si une seule des deux langues manque du `tessdata` :
   des centaines de PDF scannés sortaient vides, sans message exploitable.
   La demande est réduite aux langues réellement installées
   (`--list-langs` → `available_languages()` → `effective_lang()`), et le
   `stderr` de Tesseract (jusqu'ici jeté) est journalisé — **une fois par
   message distinct**, compteur de module sous verrou (l'OCR tourne dans un
   `ThreadPoolExecutor`), rappel toutes les 50 occurrences. Ajout de
   `self_test()`, retour sérialisable JSON, destiné à un `docia doctor`.
2. **Pages géantes** — une page hors `OCR_MAX_PIXELS_PER_PAGE` était
   purement abandonnée (`continue`), c'est-à-dire du contenu perdu en
   silence sur exactement les documents qui comptent (plan A0, scan 600
   dpi). Elle est désormais rendue à l'échelle réduite qui la fait tenir
   (`_ocr_render_scale()`, fonction pure), avec un plancher de lisibilité
   `OCR_MIN_DPI`. Le garde-fou mémoire D-096 est intact : le calcul reste
   **avant** `page.render`, jamais de bitmap allouée puis jetée.
3. **Bruit console** — les `UserWarning` d'openpyxl (« … extension is not
   supported and will be removed ») inondaient la console de l'exécutable
   sans aucune conséquence sur le texte extrait. Filtre ciblé sur le module
   émetteur et cette seule catégorie ; **pas** de `catch_warnings()` par
   appel, qui mute l'état global de `warnings` et n'est pas thread-safe.

**Vérification** : `tests/test_core/test_ocr/test_tesseract.py` (langue
réduite, OCR désactivé sans langue, `stderr` journalisé une fois, tronqué,
`self_test()` sérialisable) et `tests/test_extractors/test_pdf.py`
(`TestOcrRenderScale`, plus un bout en bout sous `skipif` Tesseract).

**Suite** : la portée réelle du sauvetage (2) et l'emplacement du filtre (3)
ont été corrigés par D-106.

---

### D-106 : relecture critique de D-104/D-105 — la perte silencieuse qu'ils laissaient passer

**Contexte** : relecture critique du commit `c7e2b3b` (D-104 + D-105).
Constat central : **le correctif laissait passer exactement la classe de
défaut qu'il visait**, la perte silencieuse de données. Neuf défauts
confirmés, tous reproduits avant correction.

**Décisions**

*MSG (`extractors/msg.py`)*

1. **Sujet et expéditeur disparaissaient en silence (bloquant)**.
   `subject` et `sender` étaient lus par `_safe()`, qui avale l'exception et
   rend `""` **sans jamais tenter la relecture brute**. Or `Message.subject`
   passe par le même `String8Property` avec la même code page mensongère que
   `Message.body` : sur les mails visés par D-104, le corps était récupéré et
   le mail sortait en `READY` **amputé de son sujet et de son expéditeur** —
   là où, avant D-104, il rendait au moins une erreur visible et
   comptabilisée. Les deux passent désormais par `_property_text()` avec leur
   PID (`PidTagSubject` 0x0037 ; expéditeur : `PidTagSenderEmailAddress`
   0x0C1F, puis `PidTagSenderSmtpAddress` 0x5D01, puis `PidTagSenderName`
   0x0C1A). Les doubles de test exposaient `subject` comme une **chaîne
   littérale**, jamais une propriété qui lève : ils ne pouvaient pas voir le
   défaut, ils ont été corrigés pour reproduire la réalité.
2. **`_decode_8bit` réintroduisait la régression corrigée par D-097**.
   La cascade `cp1252 → latin-1 → utf-8/replace` n'essaie **jamais** l'UTF-8 :
   cp1252 ne lève que sur 5 octets indéfinis, donc il « réussit » sur presque
   tout et rend du mojibake (`RÃ©union budgÃ©taire Ã\xa0 14h â€” cafÃ©…`
   pour un corps UTF-8 valide). C'est textuellement le scénario déjà résolu
   dans ce dépôt par `detect_encoding()` (BOM → UTF-8 strict → presque-UTF-8
   D-097 → cp1252 avec contrôle de plausibilité D-093 → charset-normalizer →
   latin-1) et `repair_mojibake()`. `msg.py` réutilise l'existant.
3. **`attachment_count` corrompu → explosion mémoire**. Il sort d'un
   `struct.unpack("<8x4I", …)` : entier **non signé 32 bits**, sans borne
   haute. `["?"] * 4294967295` = 34 Go de pointeurs puis un `", ".join` de
   8 Go — un `MemoryError` est un SIGKILL, pas une exception rattrapable
   (classe D-078/D-096). Plafonné par `MSG_MAX_ATTACHMENT_PLACEHOLDERS`
   (50) ; au-delà, `[pièces jointes : N annoncées, illisibles]`.
4. **Ordre des flux inversé**. `PtypString` (0x001F) est **toujours**
   utf-16-le, sans ambiguïté, et Outlook écrit fréquemment les deux
   variantes du même champ : commencer par `PtypString8` rendait
   `CoÃ»t 12â‚¬` alors que le flux Unicode voisin donnait `Coût 12€`.
   L'ordre devient `(STRING, STRING8, BINARY)`.
5. **Pièces jointes et destinataires**. `_attachment_name()` ne faisait
   qu'une cascade d'attributs : `Attachment.file_name` traverse le même
   décodage que `subject`, donc lève sur les mêmes mails, et on retombait sur
   `"?"` alors que le nom est lisible dans `PidTagAttachLongFilename`
   (0x3707) / `PidTagAttachFilename` (0x3704) — relecture brute ajoutée en
   dernier recours. `_ATTACHMENT_NAME_ATTRS` est réduit de 8 à 2 noms : six
   n'existent dans aucune version publiée d'oxmsg et `"name"` est assez
   générique pour capter un attribut sans rapport. Enfin
   `_safe(lambda: list(msg.recipients), [])` était tout-ou-rien : un seul
   destinataire dont la construction lève faisait perdre **tous** les
   destinataires — l'itérateur est consommé avec un `try` par élément.
6. **Bruit console**. Le repli de décodage était journalisé en WARNING par
   propriété et par fichier, sans compteur ni nom de fichier, et le libellé
   disait « Corps » alors que la fonction sert aussi `html_body`, le sujet et
   les pièces jointes : sur un dossier de centaines de mails, exactement le
   bruit que D-105 venait de supprimer côté openpyxl. Passé en DEBUG — le
   repli n'est pas une anomalie pour l'utilisateur, le texte est récupéré.

*Politique d'avertissements (`extractors/xlsx.py`, `cli.py`, `gui.py`)*

7. **Effet de bord global du filtre**. `warnings.filterwarnings(...)` était
   posé **à l'import du module**, donc sur le processus hôte : le filtre
   s'ajoute en tête de `warnings.filters`, une application qui avait choisi
   `-W error::UserWarning` le perdait **en silence, sans opt-out**, du seul
   fait d'importer DocFuse ; il disparaissait si l'hôte appelait
   `warnings.resetwarnings()` ; et la regex n'était pas ancrée
   (`openpyxl_autre.chose` était couvert). Le raisonnement anti-
   `catch_warnings()` de D-105 (non thread-safe) reste juste, mais la place
   d'une politique d'avertissements est le **point d'entrée applicatif** :
   `silence_openpyxl_warnings()` devient une API publique documentée,
   appelée par `cli.main()` et `gui.launch()`, et par personne d'autre. Une
   bibliothèque appelante décide elle-même (côté docia : à ajouter à son
   propre point d'entrée).

*OCR (`extractors/pdf.py`, `constants.py`, `core/ocr/tesseract.py`)*

8. **`_ocr_render_scale` : docstring inexacte et bornes dégénérées**. La
   formule et le garde-fou D-096 sont corrects, mais la portée annoncée était
   fausse : avec `OCR_DPI = 200` et `OCR_MIN_DPI = 100`, le sauvetage est
   borné à un facteur 2 en résolution, **4 en surface** — une page A0 sort à
   **101,6 dpi** (et non « 120 dpi » comme l'affirmait `constants.py`), un
   ANSI E à 103,4 dpi, tandis qu'un ARCH E (96,2 dpi) et un B0 restent
   ignorés. Les docstrings disent maintenant les chiffres mesurés.
   Le **découpage en bandes** (`crop=` de `pypdfium2`), qui permettrait de
   garder 200 dpi, a été **examiné puis écarté** : une bande horizontale
   coupe les lignes de texte en deux et Tesseract rend du bruit des deux
   côtés de la coupure — une corruption silencieuse du contenu, strictement
   pire que la résolution réduite ; le rattraper demanderait un recouvrement
   entre bandes puis une déduplication heuristique qui perd ou duplique du
   texte selon le réglage. Bornes dégénérées corrigées : `(-595, -842)`
   donnait une surface **positive** et passait à l'échelle nominale, et `NaN`
   traversait toutes les comparaisons pour ressortir en `NaN` vers
   `page.render` — la garde devient `if not (width_pt > 0 and height_pt > 0)`.
9. **Caches OCR**. `_FAILURE_COUNTS` n'était borné par rien et sa clé
   contenait le `stderr` complet : une valeur variable (« Estimating
   resolution as 633 ») créait une clé neuve par page — dictionnaire qui
   croît sans fin **et** dédoublonnage inopérant, donc le bruit revient. La
   clé est normalisée (chiffres neutralisés) et le nombre de causes
   distinctes plafonné (200 + un seau de débordement). `_list_langs` est un
   `lru_cache(maxsize=1)` sans purge : un échec transitoire (timeout) était
   mémorisé pour toute la vie du process — dans une session longue (fenêtre
   docia), installer un `.traineddata` ne débloquait rien avant redémarrage ;
   `reset_language_cache()` est ajouté à côté de `reset_failure_counts()`.
   Enfin `_failure_message(binary, "--list-langs", result)` passait une
   **option** dans le paramètre `lang` et le journal affichait « langue :
   --list-langs » : le paramètre devient `context`, explicite.

*Emplacement de la détection d'encodage*

10. `detect_encoding()` / `repair_mojibake()` sont remontés de
    `extractors/text.py` vers **`core/encoding.py`** : cinq extracteurs en
    dépendaient déjà et `msg.py` devait s'en servir à son tour — importer
    `extractors.text` depuis un autre extracteur y déclenche
    l'enregistrement d'un extracteur (`@register`) comme effet de bord d'un
    besoin de décodage. Le décodage est un service du cœur.
    `extractors/text.py` réexporte les mêmes noms (adresse historique de
    cette API, aucun appelant cassé), la définition n'existe qu'une fois.

**Rejeté** : découper les pages géantes en bandes (voir 8) ; garder le
filtre d'avertissements à l'import « parce que l'exécutable en a besoin »
(l'exécutable passe par `cli.main()`/`gui.launch()`, qui le posent) ;
remplacer `_safe()` partout par `_property_text()` (une propriété absente
vaut légitimement `None` — la relecture brute n'a de sens que pour les
champs texte qui *lèvent*).

**Vérification** : chaque défaut a un test qui **échoue avant** et **passe
après** — 25 tests ajoutés (`TestMsgSilentLossD106`,
`TestOxmsgContract`, `TestOpenpyxlWarningsAreNotAGlobalSideEffect`,
`TestOcrRenderScaleBounds`, `TestFailureCacheBounds`). Les doubles de test
MSG reproduisent la réalité : propriétés qui **lèvent**, flux `PtypString`
**et** `PtypString8` présents simultanément, octets UTF-8 valides et
tronqués. Un **test de contrat oxmsg** échoue explicitement si
`Message._storage` / `Storage.property_stream_bytes` /
`Attachment._storage` disparaît, plutôt que de laisser tous les replis
rendre `""` en silence. Suite complète : 606 réussis, 39 ignorés.

---

### D-107 : chasse aux fautes à contexte neuf — ce que le corpus affirmait à tort

**Contexte** : DocFuse n'avait jamais été audité par un regard extérieur, contrairement
à l'outil d'audit qui la consomme. Un chasseur de fautes à contexte neuf a fabriqué ses
propres entrées (dont un écrivain OLE2 minimal pour produire de **vrais** `.msg` — aucun
test du dépôt ne le faisait) et a rendu **3 critiques et 12 graves**. Les cinq corrigées
ici partagent une famille : le corpus livré à la LLM ne se contentait pas d'omettre, il
**affirmait** — une identité, une absence de contenu, un encodage, un numéro de page.

Rappel de l'enjeu : les rapports produits en aval décident de **suppressions de fichiers**.

**1. Trois documents différents déclarés « contenu identique »** (`core/duplicate_detector.py`)

Sans OCR — variante `DocFuse.exe` standard, ou les 36 échecs Tesseract du déploiement en
cours — deux PDF scannés de même pagination produisent exactement le même texte :
`[[PAGE 1: aucun texte extractible]]…`, 72 caractères, au-dessus de `DUPLICATE_MIN_CHARS`.
Un contrat de travail, une facture et un dossier médical sortaient avec
`doublon_de: contrat_travail_DUPONT.pdf`, et `_promote_duplicate_of` propageait l'identité.

Le seuil porte désormais sur le **contenu propre**, l'échafaudage retiré : marqueurs
reconnus **par leurs délimiteurs `[[…]]`**, pas par leur libellé — choix validé en vol,
la reformulation des marqueurs PPTX (point 3) n'a rien rouvert. Le hachage reste sur le
texte complet : le contenu significatif ne décide que de l'éligibilité. Le fichier écarté
garde son texte et ne reçoit aucun `duplicate_of`. Coût : 0,015 ms par fichier.

**2. Les accents d'un gros fichier perdus en silence** (`core/encoding.py`)

`ENCODING_MAX_UTF8_REPLACEMENT_RATIO` appliquait un **ratio** là où D-097 décrivait « une
seule séquence tronquée en fin de fichier » : 0,1 % de 3 M caractères = ~2 950 octets
invalides tolérés. Un export ERP français majoritairement ASCII était déclaré UTF-8 puis
décodé `errors="replace"` — et le corpus annonçait `encodage: utf-8`, ce qui était faux.

    ascii~   1000 accents=  5 -> cp1252  U+FFFD=   0
    ascii~  10000 accents=  5 -> utf-8   U+FFFD=   6
    ascii~3000000 accents=1050 -> utf-8  U+FFFD=1050

Remplacé par un décodeur incrémental (`final=False`) : le budget toléré ne dépend plus de
la taille, il est borné à une séquence UTF-8 incomplète. La constante est supprimée. Un
reliquat de remplacement se voit maintenant dans `encoding_replacements` (`core/notes.py`),
pas seulement au journal. Le cas légitime de D-097 est préservé.

**3. PPTX : graphiques, SmartArt et masques perdus, avec un marqueur qui mentait**
(`extractors/pptx.py`)

Un `graphicFrame` n'a ni `has_text_frame` ni `has_table` : le corpus émettait
`[[DIAPO N: aucun texte extractible]]`, une **affirmation fausse** qui oriente l'auditeur
vers « diapo image, rien à lire ». Perdus : titres/séries/catégories de graphique,
`ppt/diagrams/data*.xml` (un organigramme SmartArt est du nominatif pur), et le bandeau de
classification du masque — posé là précisément pour valoir partout.

Récupérés par lecture du XML des parties. Le gabarit sort **une seule fois**, en tête, dans
`## Gabarit` : le recopier sur chaque diapo gonflerait le corpus proportionnellement au
nombre de diapos pour une information qui ne varie pas. Trois marqueurs remplacent l'ancien,
et aucun n'affirme quoi que ce soit sur le contenu — seulement sur ce qui a été inspecté.
Arbitrage mesuré : signaler les images non OCRisées sur *toute* diapo coûtait **+8 % de
corpus** sur 9 présentations réelles ; elles ne sont donc nommées que si la diapo n'a
produit aucun texte, cas où l'ancien marqueur mentait.

**4. DOCX : en-têtes, pieds de page, commentaires** (`extractors/docx.py`)

`header.paragraphs` de python-docx ne rend que les `w:p` enfants directs : **aucun tableau
d'en-tête ou de pied de page n'était extrait**. Or le papier à en-tête est presque toujours
un tableau, et les gabarits RH y mettent la mention de diffusion, le responsable de
traitement et la durée de conservation — exactement les champs que la LLM doit produire, et
les seuls perdus. Le corps étant long, aucun `LOW_TEXT` ne se déclenchait : le document
sortait « rapport annuel banal, aucune donnée personnelle ».

`_iter_body_parts` est appliquée à la racine `w:hdr`/`w:ftr`. Aussi : les commentaires Word
(`word/comments.xml`, jamais lus — lieu privilégié des appréciations sur les personnes,
art. 9 RGPD ; attention, le premier commentaire réel porte `w:id="0"`, que le filtre des
notes écarte) et les lignes de tableau enveloppées dans un `w:sdt` (le contrôle « section
répétitive », donc les formulaires à lignes ajoutables : la LLM voyait un formulaire vierge).

**5. PDF : le texte OCR d'une page collé sur une autre** (`extractors/pdf.py`)

Les indices de page viennent de **pdfminer**, le rendu OCR de **PDFium**, et rien ne
comparait les deux. pdfminer déduplique son parcours de `/Kids` ; un objet page référencé
deux fois — cas d'un PDF fusionné — décale tout ce qui suit. Le genre étant `OCR`, le texte
natif réel est **écrasé**, pas concaténé :

    pdfminer  : 3 pages   pypdfium2 : 4 pages
    page 3 du corpus -> texte de la page 1 ; « salaires nominatifs » absent du corpus

Choix : **refuser** plutôt qu'aligner (`PdfPageCountMismatchError`), avec deux gardes —
structurelle (pypdf) et au point de croisement (PDFium avant tout `pdf[idx]`). Aligner
aurait imposé de recopier la boucle interne de pdfminer et de parier sur la concordance des
numéros d'objets, sans couvrir les autres causes de désaccord — le refus aurait donc été
nécessaire de toute façon. Coût assumé, écrit dans la docstring : le fichier quitte le
corpus et apparaît en `ERROR` avec les deux comptes, donc à examiner à la main.

**D-108, dans la foulée** : `_PDFIUM_LOCK` était détenu pendant l'encodage PNG, qui n'a
aucun besoin de PDFium — 99 % du temps sous verrou, débit plafonné à ~1,2 page/s quel que
soit le nombre de cœurs. Et tous les PNG rendus étaient conservés jusqu'à la fin de l'OCR,
malgré une docstring affirmant « jamais tout le PDF en mémoire à la fois ». Verrou pris par
page, encodage hors verrou, soumission au fil de l'eau bornée par un sémaphore. Le document
est **rouvert par page** plutôt que maintenu ouvert entre deux prises : garder un
`PdfDocument` vivant pendant qu'un autre thread charge le sien est exactement ce que D-078
décrit comme corrupteur.

| 200 pages A4 / 200 dpi | avant | après |
|---|---|---|
| pic RSS | 2 023 Mo | **96 Mo** |
| verrou détenu | 95,7 s (99 %) | **21,0 s (21 %)** |
| 4 fichiers en parallèle, Tesseract réel | 55,9 s / 1 411 Mo | **48,1 s / 627 Mo** |

**Vérification** : `ruff`, `ruff format`, `mypy --strict` (60 fichiers) propres ;
**650 réussis, 39 ignorés** (606 avant), sur pypdf 6.16.1 **et** 6.16.2 — les deux versions
traitent différemment l'arbre de pages dupliqué, ce qui a fait tomber un test de prémisse
avant d'être pris en compte.

**Ce qui reste ouvert**, et qui est un arbitrage, pas un oubli : un `w:sdt` de niveau
**cellule** fait toujours disparaître la cellule ; le corriger imposerait de sortir du
chemin `row.cells` de python-docx pour les lignes ordinaires, donc de reprendre à notre
charge la résolution des fusions (`gridSpan`, `vMerge`). Également : le classeur incorporé
d'un graphique PPTX (`ppt/embeddings/*.xlsx`) n'est ni lu ni signalé, et les notes de perte
d'encodage ne remontent pas encore pour `.html`, `.eml`, `.msg`, qui appellent
`detect_encoding()` sans passer par `decode_text_with_note()`.

---

## Session 18 — 1er septembre 2026 — Maintenabilité : GUI en paquet, CI qui dit vrai

### D-110 : `gui.py` devient le paquet `docfuse.gui` ; la CI prouve l'exe et les licences

**Constat** (revue de code du 01/09, note 15/20) : `gui.py` était le plus gros fichier du
projet (1 136 lignes), le moins couvert (22 %), avec un `_build_ui` de 248 lignes ; la CI
publiait un exe sans jamais l'ouvrir, et l'étape « licences » se terminait par `|| true`
— elle échouait à chaque exécution depuis la 0.1.x (« MIT License » n'était pas dans une
liste qui ne connaissait que « MIT ») sans que personne ne le voie.

**Décisions.**

1. `docfuse/gui/` : `app.py` (fenêtre, `_build_ui` découpé en six méthodes — une par zone),
   `helpers.py` (tout ce qui n'a pas de widget : jauge, tri, résumé, chemins déposés — les
   fonctions déjà testées, désormais sans import Tk possible), `dnd.py` (tkinterdnd2).
   `docfuse.gui.__init__` réexporte les noms publics : aucun appelant ne change.
2. `DOCFUSE_GUI_SMOKE=1` : `launch()` ferme la fenêtre après 1,5 s. La CI Windows lance
   `DocFuse.exe` et `DocFuse-OCR.exe` ainsi (`Start-Process -Wait` : un exe fenêtré n'est
   pas attendu par PowerShell sinon), `timeout-minutes: 5`. Même patron que `Docia.exe
   gui --smoke` chez docia.
3. Porte de licences : `pip-licenses --from=mixed --format=csv` puis refus de toute
   mention `gpl`/`proprietary` — le critère de `test_acceptance.py`, appliqué aux licences
   réellement déclarées par les paquets installés.

**Vérification** : `ruff`, `ruff format`, `mypy --strict` (64 fichiers) propres ;
**661 réussis, 39 ignorés** ; fenêtre ouverte et fermée en mode smoke sur `DISPLAY=:1`.
Les deux specs PyInstaller collectent `docfuse.gui` explicitement (`collect_submodules`).

---

*Fin du journal des décisions — Session 18.*
