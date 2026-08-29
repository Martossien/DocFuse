# Changelog

Toutes les modifications notables de DocFuse sont documentées ici.

Le format suit [Keep a Changelog](https://keepachangelog.com/fr/1.1.0/),
et ce projet adhère au [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

> Pour les notes de version détaillées (visibles sur la page GitHub Releases),
> voir le dossier [`docs/releases/`](./docs/releases/).

## [Non publié]

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

[0.1.4]: https://github.com/Martossien/DocFuse/releases/tag/v0.1.4
[0.1.3]: https://github.com/Martossien/DocFuse/releases/tag/v0.1.3
[0.1.2]: https://github.com/Martossien/DocFuse/releases/tag/v0.1.2
[0.1.1]: https://github.com/Martossien/DocFuse/releases/tag/v0.1.1
[0.1.1-beta]: https://github.com/Martossien/DocFuse/compare/166e595...main
[0.1.0]: https://github.com/Martossien/DocFuse/releases/tag/v0.1.1
