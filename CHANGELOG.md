# Changelog

Toutes les modifications notables de DocFuse sont documentées ici.

Le format suit [Keep a Changelog](https://keepachangelog.com/fr/1.1.0/),
et ce projet adhère au [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

> Pour les notes de version détaillées (visibles sur la page GitHub Releases),
> voir le dossier [`docs/releases/`](./docs/releases/).

## [Unreleased]

_Rien pour l'instant._

## [0.2.2] — 2026-09-02

### Modifié

- **Extraction dans un pool de processus** (D-111, `core/workers.py`) : pdfminer,
  parseurs XML et rendu de pages sont du Python pur, et sous le GIL huit threads
  ne valaient que 1,6 thread. Mesure sur 181 fichiers réels (41 PDF, 12 Mo de
  texte) : 163 s en un thread, 101 s en huit threads, **48 s en huit processus**,
  sortie strictement identique. Contexte `spawn` sur tous les systèmes (pypdfium2
  déconseille `fork`), un seul pool réutilisé d'un appel à l'autre (sous Windows
  un travailleur est un interpréteur à relancer : payé une fois par campagne),
  journaux des travailleurs remontés au parent, sémaphore OCR **inter-processus**
  (`OCR_MAX_CONCURRENCY` vaut pour tout le pool, comme avant pour les threads),
  langue des messages transmise avec chaque tâche. Repli automatique sur les
  threads si le pool ne démarre pas ou se casse (aucun fichier perdu : ce qui
  n'était pas rendu est refait), d'office pour un exécutable gelé sur POSIX ;
  `DOCFUSE_EXTRACTION_POOL=thread` force les threads. `freeze_support()` aux
  points d'entrée (`__main__`, `cli.main`, `gui.launch`) pour l'exe PyInstaller.
- **CI** : l'exe Windows extrait réellement les fixtures (`--input … --output …`)
  en plus d'ouvrir sa fenêtre — la preuve que le pool tourne gelé.

## [0.2.1] — 2026-09-02

### Ajouté

- **Fenêtre testée sans écran** (D-110) — `tests/test_gui_app.py` construit
  `DocFuseGUI` sur une doublure de `customtkinter` : phases des boutons,
  analyse → table, retrait d'un fichier, tri, plafond saisi, découpage,
  génération du corpus, échec et annulation, dépôt de chemins. Couverture de
  `gui/app.py` 22 % → 79 %, projet 82 % → 90 %.
- **Images autonomes dans le corpus** (D-109) — `.tif`, `.tiff`, `.jpg`, `.jpeg`,
  `.png`, `.bmp`, `.gif`, `.webp` passent par l'OCR comme les images intégrées
  aux documents (`extractors/image.py`, même moteur, même créneau de
  concurrence). Un copieur ou un serveur de fax rend du `.tif`, pas du PDF :
  bulletins de paie, arrêts de travail et pièces d'identité numérisés étaient
  purement absents de l'audit. Aucun vide muet : image vide, sans texte, trop
  grande ou sans moteur OCR produit un marqueur qui le dit. `.svg` et `.ico`
  restent hors périmètre.
- **Test de fumée de l'exécutable** (D-110) — `DOCFUSE_GUI_SMOKE=1` construit
  la fenêtre complète puis la ferme seule ; la CI l'exécute sur `DocFuse.exe`
  et `DocFuse-OCR.exe` après chaque build (Tk, CustomTkinter et tkdnd prouvés
  embarqués, ce qu'aucun test ne vérifiait).

### Modifié

- **GUI découpée en paquet `docfuse.gui`** (D-110) — `gui.py` (1 136 lignes,
  22 % couvert) devient `gui/app.py` (la fenêtre ; `_build_ui` en six méthodes
  d'une zone chacune), `gui/helpers.py` (fonctions pures, testées sans fenêtre)
  et `gui/dnd.py` (glisser-déposer `tkinterdnd2`). `from docfuse.gui import
  launch, gauge_color, …` fonctionne comme avant.
- **Vocabulaires de comptage compressés** (D-110) — `tekken_240911.json` (19,3 Mo)
  et `o200k_base.tiktoken` (3,6 Mo) deviennent des `.gz` (2,6 Mo et 1,7 Mo) : le
  paquet et l'exe perdent 18,6 Mo ; chargement au premier comptage ~0,35 s. Les
  tests de parité décompressent le fichier d'origine pour la référence.
- **`pdf.py` (863 lignes) en trois modules** (D-110) — `pdf.py` (extracteur,
  pdfminer, en-têtes répétés), `pdf_pages.py` (genre de page, texte « poubelle »,
  erreur de comptage), `pdf_ocr.py` (verrou PDFium, rendu, Tesseract). Les noms
  historiques restent importables depuis `docfuse.extractors.pdf`.
- **Quatre fonctions denses découpées** (D-110) — `pptx._texte_diapo` (lecture
  d'une forme dans `_lire_forme`), `report.generate_markdown_report` (une
  fonction par section), `html._extract_elements` (`_render_tag`),
  `pdf._dedupe_page_boilerplate` (candidats / suppression). Plus aucune
  fonction du projet au-dessus de 20 de complexité.
- **`run_analysis` et `xlsx.extract` découpés** (D-110) — seuils de scan
  (`_scan_thresholds`), extraction parallèle (`_extract_all`), qualification et
  comptage (`_qualify_and_count`) ; lecture d'une feuille Excel (`_sheet_text`).
  Sorties identiques (tests d'orchestrateur et XLSX inchangés).
- **`cli.main` découpé** (D-110) — 231 lignes et 43 chemins devenaient six
  fonctions : réglages effectifs (`_Settings`), entrées, sortie, journal,
  livraison. Codes de retour et messages inchangés.

### Corrigé

- **Deux échecs muets** (D-110) — la relecture brute d'une propriété MSG et le
  contrôle de chiffrement pypdf avalaient leur exception sans un mot ; ils la
  consignent en `debug` (un PDF corrompu se diagnostique désormais dans le journal).
- **Le corpus n'affirme plus ce qu'il ne sait pas** (D-107) — trois documents
  scannés différents sans OCR étaient déclarés « contenu identique » (mêmes
  72 caractères de marqueurs) : le seuil de doublon porte sur le contenu propre,
  marqueurs `[[…]]` exclus. Accents perdus sur les gros fichiers, en-têtes,
  pieds de page et commentaires Word non lus, texte OCR d'une page PDF collé
  sur une autre (refus explicite `PdfPageCountMismatchError`) : corrigés.
- **OCR : verrou PDFium détenu 99 % du temps et tous les PNG gardés en
  mémoire** (D-108) — 200 pages A4 : pic RSS 2 023 Mo → 96 Mo, verrou 95,7 s →
  21,0 s.
- **OCR sous Windows : « Image file cannot be read! » sur 150 pages d'une
  campagne** — d'abord attribué à `stdin` (repli par fichier temporaire, image
  de zéro octet plus envoyée), puis vraie cause démontrée en local : Leptonica
  recopie les premiers octets du contenu à la place du nom de fichier quand le
  **format** lui est inconnu — métafichiers Windows EMF/WMF (graphiques Excel,
  dessins Word). Reconnus à leur en-tête et écartés avant tout appel au
  moteur, avec un message qui nomme le format.
- **Porte de licences de la CI inopérante** — `pip-licenses --allow-only`
  échouait à chaque exécution (« MIT License » absent d'une liste qui ne
  connaissait que « MIT ») et un `|| true` masquait l'échec depuis la 0.1.x.
  Remplacée par un contrôle qui refuse toute mention GPL/AGPL/LGPL/propriétaire
  dans les licences déclarées (même critère que `test_acceptance.py`).
- URL du projet dans `pyproject.toml` (`docfuse/docfuse` → `Martossien/DocFuse`).
- **Extraction MSG robuste** (D-104) — deux plantages en masse sur des
  `.msg` Outlook réels (serveur Windows de production) :
  - le nom des pièces jointes était lu via `Attachment.long_filename`,
    attribut inexistant dans `python-oxmsg` (l'API réelle est `file_name`) —
    `AttributeError` sur tout mail avec pièce jointe. La lecture passe
    désormais par une cascade de noms d'attribut tolérante aux versions ;
  - `Message.body` lève `UnicodeDecodeError` quand le corps est un
    `PtypString8` dont la code page déclarée (souvent 65001/UTF-8) ne
    correspond pas aux octets stockés — cas systématique des mails français
    en cp1252 (é, è, à, €). Le flux brut est relu dans le conteneur OLE2
    (décodage confié à `core/encoding.py` depuis D-106).

  Plus généralement, aucune propriété MSG n'est désormais lue sans garde :
  un mail dont un champ est illisible reste extrait au mieux au lieu de
  basculer le fichier entier en ERREUR.

- **OCR : échecs diagnosticables, pages géantes lues, console silencieuse**
  (D-105) — trois défauts remontés par un audit réel sur serveur Windows :
  - Tesseract échouait en code 1 sur *chaque* page (des centaines de PDF
    scannés sortis vides et mal classés) et son `stderr` était jeté : le
    journal ne disait que « tesseract a renvoyé le code 1 ». Le `stderr`
    (tronqué à 500 caractères), le binaire et la langue sont désormais
    journalisés, **une seule fois par message distinct** (compteur de module
    protégé par un verrou, l'OCR tournant dans un pool de threads), avec un
    rappel toutes les 50 occurrences. Cause première corrigée :
    `OCR_LANG = "fra+eng"` fait échouer Tesseract si une seule des deux
    langues manque du `tessdata` — la langue demandée est maintenant réduite
    aux langues réellement installées (`available_languages()` via
    `tesseract --list-langs`, mis en cache), avec un avertissement explicite
    (« langue eng absente du tessdata, OCR en fra seul »), et l'OCR est
    proprement désactivé si aucune langue n'est disponible. Nouvelle
    fonction publique `core.ocr.tesseract.self_test()` (retour JSON) :
    binaire, version, `TESSDATA_PREFIX`, langues installées, langue
    effective et OCR réel sur une image générée en mémoire.
  - Une page dépassant `OCR_MAX_PIXELS_PER_PAGE` était purement abandonnée
    (« trop grande pour l'OCR, ignorée ») — un plan A0 ou un scan haute
    résolution n'était jamais lu. Elle est désormais rastérisée à l'échelle
    réduite qui la fait tenir sous le plafond (garde-fou mémoire D-096
    inchangé : le calcul reste **avant** `page.render`), jusqu'à un plancher
    de lisibilité `OCR_MIN_DPI` (100 dpi) sous lequel elle est seulement
    ignorée. Journal INFO à chaque page rendue en résolution réduite.
  - Les `UserWarning` d'openpyxl (« Data Validation extension is not
    supported and will be removed », « Unknown extension », « Conditional
    Formatting extension ») inondaient la console de l'exécutable sans aucune
    conséquence sur le texte extrait : filtre posé une fois à l'import de
    `extractors/xlsx.py`, ciblé sur le module émetteur et cette seule
    catégorie (pas de `catch_warnings()` par appel, qui n'est pas
    thread-safe). Depuis D-106, le filtre est posé par le **point d'entrée
    applicatif** (`cli.main()` / `gui.launch()`) et non à l'import.

- **Relecture critique de D-104/D-105 : la perte silencieuse qu'ils
  laissaient passer** (D-106) — neuf défauts confirmés et reproduits :
  - **MSG, sujet et expéditeur perdus en silence** : `subject` et `sender`
    étaient lus par une garde qui rend `""` sans jamais tenter la relecture
    brute, alors qu'ils traversent le même décodage que le corps. Les mails
    visés par D-104 sortaient donc en `READY` **amputés de leurs deux
    en-têtes principaux** — pire qu'avant D-104, où l'erreur était au moins
    visible et comptabilisée. Ils passent par les PID `PidTagSubject`,
    `PidTagSenderEmailAddress`/`SmtpAddress`/`SenderName`.
  - **MSG, mojibake** : la cascade de repli `cp1252 → latin-1` n'essayait
    jamais l'UTF-8 (cp1252 ne lève que sur 5 octets indéfinis) et rendait
    `RÃ©union budgÃ©taire` sur un corps UTF-8 parfaitement valide — la
    régression même que D-097 avait corrigée ailleurs. Le décodage réutilise
    `detect_encoding()` / `repair_mojibake()`, remontés dans
    `core/encoding.py`.
  - **MSG, explosion mémoire** : `attachment_count` est un entier non signé
    32 bits lu dans le fichier ; un `.msg` corrompu annonçant 4 294 967 295
    pièces jointes faisait allouer 34 Go (un `MemoryError` est un SIGKILL,
    pas une exception rattrapable). Plafonné à 50 marqueurs, au-delà
    `[pièces jointes : N annoncées, illisibles]`.
  - **MSG, flux Unicode ignoré** : Outlook écrit souvent les deux variantes
    d'un champ ; le flux 8 bits était essayé en premier (`CoÃ»t 12â‚¬`) alors
    que le `PtypString` voisin est toujours de l'utf-16-le (`Coût 12€`).
  - **MSG, divers** : nom de pièce jointe avec repli brut
    (`PidTagAttachLongFilename`/`AttachFilename`), destinataires lus un par
    un (un seul illisible faisait perdre toute la liste), repli de décodage
    journalisé en DEBUG et non plus en WARNING par propriété et par fichier.
  - **Avertissements openpyxl** : le filtre était posé à l'import du module,
    donc sur le processus hôte — une application avec `-W error::UserWarning`
    perdait son choix en silence, sans opt-out. `silence_openpyxl_warnings()`
    devient une API publique appelée par les points d'entrée, et sa regex est
    ancrée.
  - **OCR, bornes dégénérées** : `_ocr_render_scale(-595, -842)` donnait une
    surface positive et passait à l'échelle nominale ; un `NaN` traversait
    toutes les comparaisons jusqu'à `page.render`. Docstrings corrigées : une
    page A0 sort à **101,6 dpi** et non « 120 dpi ».
  - **OCR, caches** : le compteur d'échecs n'était borné par rien et sa clé
    contenait le `stderr` complet (« Estimating resolution as 633 » créait
    une clé par page — dédoublonnage inopérant, bruit de retour) ; clé
    normalisée et nombre de causes plafonné. Ajout de
    `reset_language_cache()` : un échec transitoire du listage des langues
    était mémorisé pour toute la vie du process. Le message d'échec ne dit
    plus « langue : --list-langs ».

## [0.2.0] - 2026-08-30 — Beta

Version de reprise du projet Doc-IA : DocFuse devient la brique
d'extraction côté poste d'un pipeline d'analyse documentaire par LLM, et
gagne pour cela le découpage en plusieurs corpus. Elle abandonne aussi le
nom de code « CorpusOne » (D-101 à D-103).

### Ajouté

- **Découpage par budget de tokens** (D-101) — option CLI `--split-context`,
  clé de config `"split_context"`, case à cocher « Découper en plusieurs
  corpus si le plafond est dépassé ». Au lieu de bloquer, DocFuse écrit
  `corpus_001.md`, `corpus_002.md`… (ou `.pdf`), chacun sous le plafond :
  remplissage séquentiel dans l'ordre du tri, **un fichier n'est jamais
  coupé**, un fichier qui dépasse à lui seul le plafond est isolé dans sa
  propre partie et signalé (préambule et rapport) — jamais abandonné en
  silence. Le rapport liste les parties (section « Parties du corpus », clé
  JSON `parts`) et la partie de chaque fichier (`part`). API bibliothèque :
  `core.splitter.split_by_budget()` (module pur) et
  `orchestrator.generate_corpus_parts()` ; `run_analysis(split_context=True)`.
- **Nom d'application paramétrable** (D-102) — module `branding.py`, variable
  d'environnement `DOCFUSE_APP_NAME` (défaut `DocFuse`), lue au lancement et
  par les specs PyInstaller (`DOCFUSE_APP_NAME=MonOutil pyinstaller
  DocFuse.spec` → `dist/MonOutil.exe`).
- **Extra `[gui]`** (D-103) — `pip install "docfuse[gui]"` installe
  l'interface ; le cœur (CLI, bibliothèque) n'exige plus Tk ni CustomTkinter.
  `python -m docfuse` sans la GUI affiche un message clair.
- `py.typed` : les annotations du paquet sont visibles par mypy chez les
  consommateurs.

### Modifié

- **BREAKING (nommage)** : l'application s'appelle **DocFuse** partout —
  exécutables `DocFuse.exe` / `DocFuse-OCR.exe`, archives
  `DocFuse-<version>-beta-windows-x64.zip`, dossier de sortie
  `DocFuse_output/` (au lieu de `CorpusOne_output/`), config `DocFuse.json` /
  `%APPDATA%\DocFuse\`, journal `%TEMP%\DocFuse\docfuse.log`, specs
  `DocFuse.spec` / `DocFuse-OCR.spec`. **Compatibilité ascendante** : une
  config `CorpusOne.json` ou `%APPDATA%\CorpusOne\config.json` héritée
  d'une 0.1.x est encore lue (en repli, jamais réécrite) ; les anciennes
  sorties `corpusone_report.*` restent ignorées par l'inventaire.
- L'inventaire ignore les parties d'un corpus découpé
  (`corpus_NNN.md/.pdf`) pour ne jamais se réingérer.
- Rapport Markdown : le titre porte le nom d'application.

### Corrigé

- README : l'exemple « Utiliser comme bibliothèque » appelait
  `run_analysis(inputs=…)` et `generate_corpus(…, context_limit=…)`, deux
  signatures qui n'existaient plus depuis D-099.
- `build.sh` annonçait un chemin `--onedir` (`dist/CorpusOne/CorpusOne.exe`)
  alors que le build est `--onefile` depuis D-054.

### Technique

- 555 tests réussis (21 nouveaux : découpage, parties MD/PDF, rapport,
  branding, absence de nom en dur dans le code et les catalogues i18n),
  39 ignorés sans `tests/samples_real/` ; ruff, `mypy --strict`, recette 7/7.
- Aucune nouvelle dépendance. Décisions D-101 à D-103 dans
  `docs/journal-decisions.md`.

## [0.1.6] - 2026-08-29 — Beta

Version issue d'un audit complet du code (bugs, encodage, performance,
maintenabilité — D-096 à D-099) et d'un retour d'usage sur le corpus PDF
(D-100).

### Ajouté

- **Corpus PDF : chaque page indique son fichier source** (D-100) —
  l'en-tête de page porte désormais `Corpus DocFuse — fichier (3/12)` en
  plus du numéro de page. Les assistants d'entreprise qui indexent un PDF
  le découpent page par page : chaque passage reste ainsi attribuable à sa
  source, ce qu'un `.md` découpé à taille fixe ne garantit pas. Nouvelle
  section README « Quel format pour quel outil ? » (FR/EN) : Markdown pour
  un LLM qui reçoit le fichier entier, PDF pour un assistant à recherche.

### Corrigé

- **GUI : fenêtre maximisée au démarrage sous Windows** — retour utilisateur
  sur v0.1.5 : les 3 boutons du bas (Générer, Rapport, Annuler) restaient
  masqués une fois des fichiers chargés, nécessitant un redimensionnement
  manuel. Plutôt que deviner une nouvelle hauteur fixe, la fenêtre utilise
  désormais tout l'espace écran disponible sous Windows.
- **Audit qualité, lot 1 — 23 correctifs « contenu perdu / plantage »**
  (D-096), chacun reproduit avant d'être corrigé :
  - **Le glisser-déposer n'avait jamais fonctionné** (bibliothèque Tcl
    `tkdnd` jamais chargée, erreur avalée) — corrigé, et embarquée dans
    l'exe Windows.
  - HTML : titres, tableaux et listes perdus dès que le corps est dans un
    `<div>` (quasi toute page réelle) ; mots soudés autour du gras/liens.
  - ODF : sections, cadres et index ignorés en silence ; mots soudés ;
    `.ods` sans lignes/colonnes.
  - DOCX : zones de texte en double avec mots collés ; en-tête/pied répété
    à chaque section.
  - XLSX : une feuille graphique faisait perdre tout le classeur.
  - Retirer l'original d'un doublon dans l'interface faisait disparaître
    son contenu du corpus.
  - EML : pièce jointe texte prise pour le corps, `Cc` et noms de PJ
    absents, charset inconnu → email entier en erreur (aussi MHTML).
  - EPUB : chapitres au nom avec espaces (`chap%201.xhtml`) sautés en
    silence. XML : déclaration `encoding=` ignorée, commentaires perdus.
  - Plantages entiers évités : PDF avec `<` dans un nom de fichier, tri
    par date sur lien cassé, RTF avec octet cp1252 indéfini, CSV à long
    champ, config JSON mal typée (la GUI ne s'ouvrait plus).
  - Dossiers `build/`, `dist/`, `node_modules/`… désormais listés comme
    ignorés dans le rapport. Markdown CRLF sans fins de ligne mélangées.
    Plafond mémoire OCR vérifié avant rendu (risque de crash OOM).
    Erreurs de génération affichées dans l'interface.
- **Audit qualité, lot 2 — encodage** (D-097) : la réparation de mojibake
  ne touche plus qu'à la corruption d'encodage (entités HTML `&amp;`,
  codes ANSI des logs et texte NFD ne sont plus réécrits) ; un fichier
  UTF-8 coupé au milieu d'un caractère n'est plus basculé entièrement en
  cp1252 ; une page HTML sans charset déclaré n'est plus « devinée » en
  encodage exotique. Fichiers ASCII (code, logs, CSV) : réparation
  court-circuitée, 2,4 s économisées sur 200 000 lignes.

### Performance

- **Audit qualité, lot 3 — vitesse à sortie identique** (D-098), chaque
  gain mesuré et le corpus généré vérifié **identique byte à byte** avant/
  après :
  - OCR des images intégrées (DOCX, PPTX, XLSX, ODF) exécuté en parallèle
    à l'intérieur d'un fichier, résultats remis dans l'ordre du document :
    une présentation de 44 images passe de 21,0 s à 3,0 s.
  - Nombre de processus Tesseract borné globalement (images + pages PDF) ;
    nombre de workers dérivé du processeur. Dossier de 120 fichiers :
    28,4 s → 10,6 s.
  - XLSX : la feuille n'est plus décompressée 7 fois ; DOCX : plus de
    re-parse du document par BeautifulSoup ; PDF : fichier non recopié en
    mémoire pour la détection de chiffrement.
  - Interface : changer de moteur de comptage ne re-tokenise plus tout le
    corpus (cache) ; la saisie du plafond ne reconstruit plus la table à
    chaque frappe. Inventaire parcouru une seule fois par source.

### Modifié

- **Audit qualité, lot 4 — maintenabilité** (D-099) : code dupliqué
  factorisé (gardes des formats conteneurs, note d'encodage, écriture des
  rapports, chemins de sortie), ce qui a révélé et corrigé :
  - un fichier Markdown contenant des ``` était encapsulé dans des
    backticks (contraire au CdC : les formats texte sont inclus tels quels) ;
  - le « type » d'un fichier dans le rapport différait selon que son
    extraction avait réussi (`odt`) ou échoué (`odf`) ;
  - CLI : un fichier seul en entrée écrivait `corpus.md` dans le dossier
    courant au lieu de `CorpusOne_output/` à côté du fichier, comme la GUI ;
    `--output notes.txt` créait un dossier `notes.txt/` (refusé avec un
    message) ; `--input` manquant renvoie le code 1, plus le code 2 réservé
    au blocage ;
  - GUI : le bouton « Générer corpus.md » suit enfin le choix PDF ; le
    plafond saisi est lu de la même façon par le blocage, le compteur et
    le résumé ; la barre de progression ne recule plus.
  - Images exportées : deux documents homonymes ne s'écrasent plus.
  - Note « secrets potentiels » plafonnée à 10 lignes par type.

### Technique

- 534 tests (572 collectés ; 39 ignorés sans `tests/samples_real/`), 100
  décisions archivées (D-001 à D-100). Tests de non-régression par lot
  d'audit : `test_regressions_d096.py` à `d099.py`, `test_pdf_page_header.py`.
- CI Windows : `csv.field_size_limit(sys.maxsize)` levait `OverflowError`
  (C long 32 bits) ; nom de fichier `a<b>.txt` invalide dans un test ; CRLF
  conservés dans les blocs `<pre>` HTML — corrigés.
- Nouvelles constantes documentées (`OCR_MAX_CONCURRENCY`, `MAX_WORKERS`
  dérivé du CPU, `VERBATIM_EXTENSIONS`, `OUTPUT_DIR_NAME`, `REPORT_SUFFIX`,
  `SECRETS_NOTE_MAX_LINES_PER_KIND`, `PDF_PAGE_HEADER_MAX_CHARS`…), nouveau
  module `output/paths.py`.

## [0.1.5] - 2026-08-29 — Beta

### Corrigé

- **Fichiers Office protégés par mot de passe à l'ouverture (.xlsx/.docx/.pptx)** :
  donnaient une erreur bas niveau incompréhensible (`BadZipFile`,
  `PackageNotFoundError`) au lieu d'un message clair — même défaut déjà
  corrigé pour le PDF, jamais étendu aux formats Office. Détecté via la
  signature OLE2/CFBF du conteneur chiffré.
- **JSON/XML corrompus** : message `JSONDecodeError`/`ParseError` brut
  remplacé par un message clair (« Fichier corrompu ») avec le détail
  ligne/colonne conservé.
- **`__MACOSX/` ignoré** : dossier créé par macOS lors de la compression
  d'un ZIP (métadonnées `._nom`, jamais du contenu réel) — donnait
  auparavant une fausse alerte « fichier corrompu » sur des fichiers qui
  n'ont jamais été le vrai contenu.
- **Réparation automatique du mojibake** (encodage incohérent,
  double-encodage UTF-8/Latin-1) sur les fichiers texte/Markdown/CSV/
  JSON/XML/HTML — signalé dans l'en-tête `## SOURCE:` quand une correction
  a eu lieu, jamais silencieux.
- **Faux-positifs d'encodage cp1252 réduits** : un décodage cp1252
  implausible (beaucoup de caractères de contrôle) retombe désormais sur
  `charset-normalizer` au lieu d'être accepté aveuglément.

### Ajouté

- **GUI : tri des colonnes du tableau de fichiers** — en-têtes cliquables
  (nom, type, texte estimé, contexte +15 %, statut), second clic pour
  inverser l'ordre. Le tri par statut suit la sévérité (Prêt < Images <
  Peu de texte < ...), pas l'ordre alphabétique du libellé affiché.
- **GUI : fenêtre par défaut élargie** (900×720 → 1050×720, minsize
  700×600 → 900×600) — les boutons du bas (Générer, Rapport, Annuler)
  pouvaient déborder de la fenêtre par défaut sous Windows.
- **OCR automatique des images intégrées DOCX/PPTX** — même moteur
  Tesseract que les PDF scannés, sans réglage à activer. Corrige les
  fichiers `.pptx`/`.docx` dont le contenu est capturé dans une image
  (schéma, capture d'écran) plutôt qu'en texte natif.
- **Export optionnel des images intégrées pour description par IA**
  (désactivé par défaut — CLI `--extract-images`, GUI, config JSON) :
  chaque image DOCX/PPTX est écrite dans `<sortie>_images/` avec un nom
  explicite (document + emplacement), et un tag `[[IMAGE: nom.png]]` est
  inséré dans le corpus au point d'apparition, pour qu'un LLM multimodal
  externe sache où positionner sa description.
- **OCR/export des images intégrées étendu à Excel (.xlsx) et OpenDocument
  (.odt/.odp)** — même mécanisme que DOCX/PPTX : OCR automatique, export
  optionnel avec tag de position (`sheet_NomFeuille`/`slideN`).
- **Support EPUB** (`.epub`) — texte extrait dans l'ordre de lecture
  (spine), titre/auteur capturés, tableaux/listes convertis en Markdown.
  Aucun fichier chiffré/DRM traité (erreur claire à la place).
- **Garde-fou "bombe zip"** sur tous les formats conteneurs ZIP
  (DOCX/PPTX/XLSX/ODF/EPUB) : un fichier au taux de compression anormal
  est rejeté avant tout parsing, par sécurité.
- **Support des formats Office legacy binaires** : `.doc`, `.xls`, `.ppt`
  (Word/Excel/PowerPoint 97-2003) et `.msg` (email Outlook) — aucun
  binaire externe, aucune installation requise sur la machine.

### Technique

- 509 tests collectés (471 passed / 39 skipped) — 94 décisions archivées
  (D-001 à D-094).
- Nouvelles dépendances : `ftfy` (réparation mojibake), `office_oxide`
  (extension native Rust, `.doc`/`.xls`/`.ppt`), `python-oxmsg` (`.msg`) —
  toutes vérifiées MIT/Apache-2.0/BSD, sans GPL/AGPL/LGPL. `office_oxide`
  étant un binaire compilé par plateforme, son empaquetage PyInstaller
  Windows est à confirmer sur cette Release (pas d'environnement
  Windows/Wine disponible en session de développement pour le tester).

## [0.1.4] - 2026-08-29 — Beta

### Ajouté

- **Fichiers de développement traités comme texte brut** : `.py`, `.js`,
  `.ts`, `.vba`, `.sh`, `.ps1`, `.sql`, `.css`, `.java`, `.c`/`.cpp`, `.go`,
  `.rs` et une soixantaine d'autres extensions courantes (liste complète :
  `constants.CODE_EXTENSIONS`) sont désormais reconnues et incluses dans le
  corpus au lieu d'être ignorées silencieusement — cas d'usage LLM fréquent
  (envoyer une codebase). Même détection d'encodage que `.txt`. Limite
  connue : dispatch par extension, donc les fichiers sans extension
  (`Dockerfile`, `Makefile`) ou dotfiles purs (`.gitignore`, `.env`) restent
  hors périmètre.
- **OCR des PDF scannés** (portée v1 : PDF uniquement) : un PDF scanné
  était détecté (alerte « peu de texte ») mais son contenu n'était jamais
  récupéré. Chaque page est désormais classée (texte natif suffisant / à
  OCRiser / vide / mixte) et les pages qui en ont besoin sont reconnues via
  Tesseract, si disponible. Jamais bloquant : sans Tesseract, le
  comportement reste strictement identique à avant, avec une note
  expliquant pourquoi. `CorpusOne.exe` n'embarque pas Tesseract (taille et
  promesse « zéro dépendance » inchangées) — une variante distincte,
  `CorpusOne-OCR.exe`, l'embarque pour un usage sans aucune installation.

### Corrigé (critique)

- **Crash du processus entier (SIGSEGV) lors de l'OCR de plusieurs PDF en
  parallèle** : PDFium (`pypdfium2`) n'est pas thread-safe entre documents
  distincts chargés depuis des threads différents — un dossier avec
  plusieurs PDF scannés traités en parallèle pouvait corrompre la mémoire
  native et tuer tout le processus, sans message d'erreur exploitable.
  Trouvé en testant sur un vrai dossier de 741 fichiers. Corrigé par un
  verrou global sérialisant l'accès à PDFium.

### Corrigé — audit systématique des extracteurs, 17 bugs de perte silencieuse/qualité

Deux vagues de correctifs, chacun avec un test de non-régression construit
avec la bibliothèque réelle du format (jamais un mock), reproduisant la
structure exacte du bug avant de vérifier le correctif :

- **Texte imbriqué dans un Form XObject (PDF) silencieusement ignoré** :
  certains PDF (ex. générés par TCPDF — filigranes, tampons, contenu
  fusionné) placent du texte réel dans un objet `LTFigure` imbriqué, jamais
  vu par l'extraction au premier niveau de la page. Jusqu'à ~2500
  caractères par page pouvaient disparaître silencieusement — un document
  pouvait sembler presque vide (page "peu de texte") alors que son contenu
  était parfaitement extractible.
- **DOCX** : texte inséré en suivi des modifications (`w:ins`) et
  contrôles de contenu Word (`w:sdt`) invisibles ; zones de texte (bug de
  casse XML — n'avaient en réalité **jamais** fonctionné, sur aucun
  fichier) et celles des en-têtes/pieds de page ; tableau imbriqué dans une
  cellule.
- **EML** : email transféré en pièce jointe (`message/rfc822`) — sujet et
  corps totalement perdus.
- **PDF** : mot de passe utilisateur vide (juste des permissions
  restreintes) rejeté comme un fichier totalement illisible ; texte
  poubelle `(cid:...)` laissé tel quel dans le corpus quand l'OCR est
  indisponible au lieu de signaler une page vide.
- **ODF** : en-têtes/pieds de page (`.odt`, `styles.xml`) jamais lus ;
  notes d'orateur (`.odp`) mélangées indistinctement au contenu visible des
  diapos, sans séparation entre diapos ni gestion structurée des tableaux.
- **HTML** : `<meta charset>` jamais consulté → charabia total et
  silencieux pour tout encodage legacy non latin (cyrillique, etc.) ;
  commentaires HTML qui fuitaient dans le texte extrait.
- **MHTML** : `alt` des images jamais extrait.
- **PPTX** : formes groupées — texte/tableaux dans un groupe invisibles.
- **RTF** : texte de repli des objets OLE incrustés (tableau Excel collé en
  objet) perdu.
- **XLSX** : formules jamais calculées (fichier généré par script) →
  cellule vide sans aucune trace qu'un calcul existait ; dimension de
  feuille mal déclarée par le fichier pouvant tronquer silencieusement des
  lignes/colonnes ; cellules fusionnées non propagées aux autres cellules
  de la plage.
- **Bruit de bibliothèques JS/CSS tierces exclu des « fichiers de
  développement »** : trouvé en testant sur un vrai dossier de page web
  sauvegardée par un navigateur — `*.min.js`/`*.min.css` (jQuery, etc.)
  représentaient 91 % du corpus généré. Désormais exclus (`*.min.js`,
  `*.min.css`, dossiers `node_modules/`, `vendor/`, `dist/`, `build/`).

### Technique

- `ruff` épinglé sur une version exacte (`==0.16.5`) — dette identifiée en
  v0.1.3 (dérive local/CI ayant cassé la publication initiale de cette
  Release), corrigée pour de bon.
- `mypy` et `types-beautifulsoup4` épinglés (`==2.3.1` /
  `==4.12.0.20250516`) — même dérive local/CI, découverte en publiant
  cette Release : `mypy` non épinglé avait résolu la version 2.3.1 en CI
  (contre 1.16.1 en local), faisant échouer `lint-and-test` sur toute la
  matrice et empêchant `build-windows`/`build-windows-ocr` de se
  déclencher. Corrigé (D-088).

## [0.1.3] - 2026-08-24 — Beta

### Ajouté

- **Déduplication des en-têtes/pieds de page répétés (PDF)** : une ligne
  strictement identique en début/fin de page, répétée sur plusieurs pages
  d'un même PDF (ex. « Confidentiel — Usage interne », numéro de page),
  n'est conservée qu'une fois. Toujours signalé dans l'en-tête SOURCE et le
  rapport, jamais silencieux.
- **Retrait des images base64 intégrées (Markdown)** : un `data:image/...
  ;base64,...` collé dans un fichier `.md` (export Obsidian/Notion, capture
  d'écran collée) est remplacé par une note — inutile en contexte texte,
  coûteux en tokens.
- **Détection de doublons de contenu entre fichiers** : deux fichiers
  différents dont le texte extrait est strictement identique (copie,
  sauvegarde, export dupliqué) ne sont comptés/inclus qu'une fois ; le
  second pointe vers l'original au lieu de répéter le contenu.
- **Alerte non bloquante sur les secrets potentiels** : détection
  heuristique conservatrice (clé AWS, clé privée, jeton Slack/JWT, motif
  `api_key=...`) avant que le corpus ne parte vers un chat LLM externe. Ne
  modifie jamais le texte ; seul le type de secret et le numéro de ligne
  sont rapportés, jamais la valeur trouvée.
- Rapport MD : nouvelle section « Notes » regroupant ces quatre alertes de
  transparence par fichier.

### Technique

- Nouveaux modules `core/duplicate_detector.py`, `core/secret_scanner.py` ;
  logique PDF/Markdown dans `extractors/pdf.py` et `extractors/markdown.py`.
- Aucune nouvelle dépendance (bibliothèque standard uniquement : `re`,
  `hashlib`).
- Voir D-062 à D-065 dans `docs/journal-decisions.md` pour le détail des
  seuils et des choix (notamment pourquoi la compression sémantique de
  contenu a été écartée).

## [0.1.2] - 2026-08-21 — Beta

### Ajouté

- **Moteurs de comptage précis en option (Mistral, OpenAI)** : en plus de
  l'approximation générique (`octets/4`, inchangée par défaut), deux moteurs
  `--tokenizer-engine {mistral,openai}` / config `tokenizer_engine` / GUI
  « Précision du comptage » calculent le nombre de tokens réel du tokenizer
  Mistral (Tekken) ou d'OpenAI (`o200k_base`, GPT-4o/4.1), entièrement local,
  sans connexion réseau. Registre extensible (`core/tokenizers/`) pour
  d'autres moteurs à venir.
- `--list-tokenizers` : liste les moteurs de comptage disponibles.
- Rapport MD/JSON : nouvelle ligne « Moteur de comptage » + détail des
  tokens par fichier avec le moteur réellement utilisé.
- **Release GitHub automatisée** : quand une Release est publiée, la CI
  attache automatiquement `CorpusOne-{version}-windows-x64.zip` + son
  `.sha256` (auparavant fait à la main).

### Corrigé

- **GUI : changer de moteur de comptage recalcule instantanément** (sans
  ré-extraction), au lieu de laisser le tableau affiché sur les chiffres de
  l'ancien moteur tant qu'on ne relançait pas l'analyse.
- **CI : upload de l'artifact Windows** — le chemin pointait encore vers
  l'ancien dossier `--onedir` depuis le passage en `--onefile` ; chaque run
  échouait silencieusement à publier l'exe (`if-no-files-found: warn`,
  jamais remarqué). Corrigé + transformé en échec explicite si ça se
  reproduit (D-059).

### Technique

- Nouvelle dépendance : `tiktoken` (MIT). Le paquet `mistral-common` n'est
  **pas** installé (une de ses dépendances, `pycountry`, est LGPL-2.1,
  incompatible avec la politique zéro-copyleft du projet) — voir D-057 dans
  `docs/journal-decisions.md`.
- Vocabulaire Tekken de Mistral vendoré (`assets/tekken_240911.json`,
  Apache-2.0, voir `NOTICE`), utilisé directement avec `tiktoken.Encoding`.
- Vocabulaire OpenAI `o200k_base` vendoré (`assets/o200k_base.tiktoken`,
  MIT, fichier officiel `tiktoken`, hash vérifié — voir `NOTICE` et D-060).
- Nouveaux tests : parité avec le vrai `Tekkenizer` de `mistral-common` et
  avec le vrai `tiktoken.get_encoding("o200k_base")` (offline via cache
  amorcé), absence d'appel réseau (socket mocké) pour les deux moteurs,
  non-régression sur les tests existants.
- Validé sur un corpus de documents réels (65 fichiers synthétiques 10 Ko à
  2 Mo + 14 documents utilisateur variés — DOCX/PDF/MD/HTML/PPTX/ODT/RTF/XLSX/CSV) :
  0 erreur d'extraction, contenu intact, comptes de tokens cohérents et
  différenciés par moteur.
- 295 tests collectés (256 passed / 39 skipped — `tests/samples_real/` non
  versionné).
- 61 décisions d'architecture archivées (D-001 à D-061).

## [0.1.1] - 2026-08-20 — Beta

### Ajouté

- **GUI : sélection multi-sources exacte** (dossiers, fichiers précis, glisser-déposer).
  Chaque ajout est cumulatif ; le retrait individuel d'un fichier déclenche
  un recalcul instantané sans ré-extraction.
- **Affichage progressif** : les fichiers inventoriés apparaissent immédiatement
  avec un état « En attente », puis leur statut et leur estimation de tokens
  sont mis à jour au fil de l'extraction.
- **Mise en page responsive** de la fenêtre GUI (trois lignes d'options,
  plafond de contexte toujours visible).
- **Recette automatisée** : `tests/recette/run_recette.py` produit ses propres
  fixtures en CI et vérifie 7 scénarios (ASCII, CRLF, blocage, etc.).

### Modifié

- **Compteur de contexte générique** : calcul fiabilisé sur octets UTF-8
  exacts (en-têtes `SOURCE` compris), marge appliquée une seule fois au total.
- **Plafond et marge sont des variables** : configurables via CLI
  (`--context`, `--margin`) et JSON utilisateur.
- **Build PyInstaller** : spec corrigé pour embarquer les 13 extracteurs
  chargés dynamiquement (`collect_submodules`).

### Corrigé

- **Script de recette 100 % ASCII** : `UnicodeEncodeError` sur console
  Windows cp1252 résolu.
- **CRLF en écriture binaire** : `markdown_writer.write_bytes` utilise
  explicitement `\r\n` sous Windows.
- **Test `test_lf_output`** : tolérant au contenu CRLF des fichiers source
  sur Windows.

### Technique

- 236 tests collectés (198 passed / 38 skipped — `tests/samples_real/` non
  versionné).
- `ruff`, `ruff format --check` et `mypy --strict` validés.
- Binaire Windows compilé avec PyInstaller 6.22.2 et Python 3.13.15.
- 49 décisions d'architecture archivées (D-001 à D-049).

## [0.1.1-beta] - Correctifs post-publication (2026-08-20)

Correctifs appliqués sur la branche `main` après la publication initiale de
la 0.1.1, sans nouveau tag (le tag `v0.1.1` pointe sur le commit initial).

### Corrigé

- **Binaire Windows en mode `--onefile`** : passage du mode `--onedir`
  (`.exe` + dossier `_internal/`) au mode `--onefile` (un seul
  `CorpusOne.exe` autoportant, ~40.6 Mo). Fini les messages
  « DLL Python 3.13 manquante » quand on déplace l'exe.
- **DLL natives embarquées** : `tcl86t.dll`, `tk86t.dll`, `zlib1.dll`,
  `libffi-8.dll`, `libssl-3.dll`, `libcrypto-3.dll`, `sqlite3.dll` sont
  collectées depuis `<python>/DLLs/` et incluses dans le bundle.
- **CLI : `--output <dossier>`** : la CLI ajoute automatiquement `.md`
  ou `.pdf` selon `--format` et crée le dossier au besoin. Auparavant :
  `ValueError: Format de sortie non supporté :`.

### Ajouté

- Test de non-régression `test_cli_output_dir_without_extension`.
- Section « Téléchargements » dans les notes de release avec liens cliquables
  vers le `.zip` et le `.sha256`.

### Technique

- 237 tests collectés (199 passed / 38 skipped).
- Décisions archivées : D-050 à D-055.

## [0.1.0] - 2026-08-20 — Première publication

Première version publiée du projet. Scaffold complet, 13 formats supportés,
GUI CustomTkinter, CLI argparse, i18n FR/EN, config JSON 3 niveaux,
tests d'acceptation, build Windows initial.

[0.2.0]: https://github.com/Martossien/DocFuse/releases/tag/v0.2.0
[0.1.6]: https://github.com/Martossien/DocFuse/releases/tag/v0.1.6
[0.1.5]: https://github.com/Martossien/DocFuse/releases/tag/v0.1.5
[0.1.4]: https://github.com/Martossien/DocFuse/releases/tag/v0.1.4
[0.1.3]: https://github.com/Martossien/DocFuse/releases/tag/v0.1.3
[0.1.2]: https://github.com/Martossien/DocFuse/releases/tag/v0.1.2
[0.1.1]: https://github.com/Martossien/DocFuse/releases/tag/v0.1.1
[0.1.1-beta]: https://github.com/Martossien/DocFuse/compare/166e595...main
[0.1.0]: https://github.com/Martossien/DocFuse/releases/tag/v0.1.1
