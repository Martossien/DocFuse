# Cahier des charges — DocFuse

**Outil portable Windows d’assemblage de documents bureautiques vers un corpus unique (Markdown ou PDF) destiné aux LLM**

| Champ | Valeur |
|---|---|
| Nom de code | CorpusOne |
| Type de document | Cahier des charges fonctionnel et technique (CdC) |
| Version | 1.0 |
| Date | 20 août 2026 |
| Statut | Validé pour développement |
| Licence du livrable | Apache License 2.0 |
| Plateforme | Windows 10 et Windows 11 (x64) |
| Langue UI par défaut | Français (autres langues possibles) |
| Public | Utilisateur métier / administrateur système, sans droit administrateur |

Ce document est contractuel pour le développement. En cas d’ambiguïté d’implémentation, l’expérience utilisateur et la **non-perte de texte extractible** priment sur l’élégance technique.

---

## 1. Objet et vision produit

### 1.1 Problème utilisateur

Un utilisateur dispose d’un **dossier** contenant des documents hétérogènes (PDF, Word, PowerPoint, RTF, HTML, texte, etc.). Il doit les donner à une IA / un LLM. Il n’a pas besoin de la mise en page. Il a besoin :

- d’**un seul fichier** de sortie ;
- du **texte intégral** extractible, sans perte silencieuse ;
- de savoir si le corpus **rentre dans une fenêtre de contexte** ;
- d’être prévenu si un document est un **scan** ou **contient des images** (texte non lu, car pas d’OCR) ;
- d’un outil **local**, **hors-ligne**, **portable**, **sans installation administrateur**.

### 1.2 Promesse

L’utilisateur désigne un répertoire. CorpusOne parcourt les fichiers supportés, extrait le texte, concatène, produit un `.md` ou un `.pdf`, affiche un **compteur de contexte générique avec marge +15 %**, et **refuse de générer** si le plafond de contexte (défaut **128 000**, variable) est dépassé **sur un fichier d’entrée ou sur le total**.

### 1.3 Ce que l’outil n’est pas

- Pas un éditeur PDF, pas un OCR, pas un cloud, pas un client LLM.
- Pas une conversion fidèle (polices, colonnes, animations, commentaires manuscrits).
- Pas un installeur déployé par GPO (possible plus tard, hors v1).

---

## 2. Acteurs et scénarios

### 2.1 Acteurs

| Acteur | Besoin |
|---|---|
| Utilisateur final | Glisser un dossier, cliquer, récupérer un fichier, comprendre les alertes |
| Utilisateur avancé / IT | CLI, fichier de conf, code retour, journal, déploiement portable sur clé USB ou partage réseau |
| Développeur | Spécifications testables, licences claires, références open source |

### 2.2 Scénario principal (GUI)

1. L’utilisateur lance `CorpusOne.exe` (double-clic, pas d’UAC).
2. Il glisse un dossier **ou** clique sur « Choisir un dossier ».
3. L’outil liste immédiatement les fichiers retenus / ignorés.
4. Il choisit **Markdown** (défaut) ou **PDF**.
5. Il voit le **plafond de contexte** (128K, modifiable).
6. Il clique sur **Analyser** (ou l’analyse démarre toute seule dès le dossier choisi).
7. Il voit, fichier par fichier : OK, image (warning), peu de texte (alerte forte), trop gros (blocage).
8. Le compteur total se met à jour (estimé, estimé +15 %, plafond).
9. Si un fichier ou le total dépasse le plafond → bouton **Générer** désactivé, message clair, proposition de **monter le plafond** ou de **retirer des fichiers**.
10. S’il n’y a que des warnings images → **Générer** reste actif.
11. Génération → un fichier + un rapport à côté.

### 2.3 Scénario glisser-déposer sur l’icône

- Déposer un dossier sur `CorpusOne.exe` ouvre l’UI préremplie avec ce dossier.
- Déposer des fichiers (pas un dossier) : même comportement, liste = ces fichiers.

### 2.4 Scénario CLI

```text
CorpusOne.exe --input "D:\Dossier" --output "D:\Sortie\corpus.md" --format md
```

Sans `--output`, le fichier est créé dans le dossier d’entrée, nom par défaut `corpus.md` / `corpus.pdf`.

---

## 3. Périmètre

### 3.1 Dans le périmètre (v1)

- Windows 10/11 x64, utilisateur standard, portable, hors-ligne strict.
- Trois interfaces : **GUI**, **glisser-déposer**, **CLI**.
- Extraction texte + concaténation + sortie MD ou PDF.
- Compteur de contexte générique + marge 15 %.
- Contrôle de plafond **par fichier d’entrée** et **sur le total**.
- Alertes images à deux niveaux.
- Rapport d’exécution (succès, ignorés, warnings, blocages).
- Français + infrastructure i18n.
- Licence Apache 2.0.

### 3.2 Hors périmètre (v1)

- OCR / vision / description d’images.
- Connexion Internet, télémétrie, mise à jour auto en ligne.
- Fichiers protégés par mot de passe (échec explicite, pas de cassage).
- Formats binaires anciens difficiles (`.doc`, `.ppt`, `.xls`) sauf si un parseur **léger, hors-ligne, licence compatible** est trivial. Sinon : **refus explicite** dans le rapport, jamais un silence.
- Fusion visuelle PDF (pages d’origine collées). Le PDF de sortie est un **document texte** généré.
- Compteurs par modèle propriétaire (GPT-4o, Claude, etc.). Un seul estimateur générique.
- Découpage automatique en plusieurs corpus.

---

## 4. Exigences non négociables

| ID | Exigence |
|---|---|
| NFR-01 | Aucun droit administrateur. Aucun UAC. |
| NFR-02 | Aucune connexion réseau. Timeout / échec si une lib tente un accès réseau. Tests hors-ligne obligatoires (pare-feu bloquant). |
| NFR-03 | Portable : lancable depuis un dossier utilisateur, une clé USB, un partage `\\serveur\share` en lecture + écriture locale. |
| NFR-04 | Pas d’OCR. |
| NFR-05 | Pas de perte silencieuse de **texte extractible**. Tout fichier non traité apparaît dans le rapport avec la cause. |
| NFR-06 | Licence Apache 2.0 du code produit. Dépendances **compatibles** (Apache-2.0, MIT, BSD, ISC, MPL-2.0). **Interdit : GPL, AGPL** (ex. Poppler, PyMuPDF/AGPL). |
| NFR-07 | Démarrage perçu comme rapide : GUI visible **< 3 s** sur machine de bureau SSD ; extraction **prioritaire au texte**, pas à la mise en page. |
| NFR-08 | UI par défaut en français ; autre langue via configuration, sans recompiler. |

---

## 5. Livrable d’installation (contrainte « peu de fichiers »)

### 5.1 Cible utilisateur

Idéal :

```text
CorpusOne/
  CorpusOne.exe          ← seul fichier visible indispensable
  CorpusOne.json         ← optionnel ; créé au premier enregistrement des préférences
  licences/NOTICE.txt    ← attributions Apache 2.0 (peut être embarqué dans l’exe)
```

Acceptable si le one-file ralentit trop le démarrage (PyInstaller `--onefile` décompresse à chaque lancement) :

```text
CorpusOne/
  CorpusOne.exe
  CorpusOne.json
  _internal/             ← runtime, pas à manipuler
```

Dans ce cas, l’utilisateur ne double-clique **que** sur l’exe. Le dossier `_internal` n’est pas documenté comme « à configurer ».

### 5.2 Emplacement de la configuration

Ordre de lecture (le premier trouvé gagne, puis fusion avec les défauts) :

1. Fichier `CorpusOne.json` **à côté de l’exe** (priorité « clé USB / portable »).
2. `%APPDATA%\CorpusOne\config.json` (si le dossier de l’exe n’est pas inscriptible, ex. partage en lecture).
3. Valeurs par défaut compilées.

**Écriture** : même endroit d’où la conf a été lue ; si lecture seule → fallback `%APPDATA%\CorpusOne\`.

Le registre HKCU est **autorisé en option** (`HKCU\Software\CorpusOne`) mais **pas obligatoire**. Préférer le JSON : lisible, portable, sauvegardable, compatible Apache, sans surprise IT.

**Interdit** : HKLM, Program Files, services Windows, tâches planifiées, drivers.

### 5.3 Écriture des sorties

- Jamais dans le dossier de l’exe par défaut (risque de partage en lecture).
- Défaut GUI : sous-dossier `CorpusOne_output\` **dans le dossier source**, ou dossier choisi par l’utilisateur.
- Si le dossier source n’est pas inscriptible → « Enregistrer sous… » obligatoire.

---

## 6. Interfaces

### 6.1 GUI — penser utilisateur, pas développeur

Fenêtre unique, non intimidante, ~900×640, redimensionnable.

**Haut**
- Zone de dépôt très visible : « Glissez un dossier ici » + bouton « Choisir un dossier… ».
- Chemin affiché en clair, bouton « Changer ».

**Options (une ligne)**
- Format de sortie : `Markdown (recommandé pour l’IA)` | `PDF (relecture)`.
- Plafond de contexte : champ numérique, défaut `128000`, suffixe `tokens estimés`, lien discret « qu’est-ce que c’est ? ».
- Cases : `Inclure les sous-dossiers` (oui par défaut), `Ouvrir le dossier à la fin`.

**Liste fichiers** (tableau)
Colonnes : Fichier (chemin relatif) | Type | Texte estimé | Contexte +15 % | Statut.

Statuts visuels :

| Statut | Couleur | Signification |
|---|---|---|
| Prêt | vert | Texte extractible, sous le plafond |
| Images | jaune | Contient des images ; le texte sera quand même pris |
| Peu / pas de texte | orange foncé / rouge | Scan ou quasi-scan ; perte probable |
| Trop volumineux | rouge, cadenas | Fichier seul ≥ plafond → génération bloquée |
| Ignoré | gris | Extension hors périmètre, verrouillé, vide, `~$` |
| Erreur | rouge | Corrompu, mot de passe, lecture impossible |

**Bandeau compteur (toujours visible)**
- `Estimé : 84 200`
- `Avec marge +15 % : 96 830`
- `Plafond : 128 000`
- Jauge. Vert / orange (> 80 %) / rouge (≥ 100 % → bloqué).

**Bas**
- Bouton **Générer** (primaire). Désactivé si blocage contexte.
- Bouton **Exporter le rapport** (toujours actif après analyse).
- Ligne de résumé en français courant, pas en jargon :
  - OK : « 12 fichiers prêts. Le corpus devrait passer dans 128 000 tokens (marge comprise). »
  - Warning : « 3 documents contiennent des images : leur contenu visuel ne sera pas lu (pas d’OCR). Vous pouvez continuer. »
  - Critique : « 2 documents ont peu ou pas de texte (probablement des scans). Le texte de ces fichiers sera quasi vide. Vous pouvez continuer, mais l’IA n’aura pas ce contenu. »
  - Blocage : « Impossible de générer : “contrat.pdf” dépasse à lui seul le plafond (152 000 > 128 000). Augmentez le plafond ou retirez ce fichier. »

Aide contextuelle en français simple. Pas de console noire derrière la GUI.

Accessibilité minimale : navigation clavier, contrastes, ne pas reposer uniquement sur la couleur.

### 6.2 Glisser-déposer

- Dossier → racine d’entrée.
- Fichiers multiples → liste figée (pas de parent récursif).
- Un `.zip` n’est **pas** décompressé en v1 (hors périmètre sauf si trivial). Mention au rapport : « ZIP non lu en v1 ». Alternative documentée : extraire d’abord.

### 6.3 CLI

```text
CorpusOne.exe --input <chemin> [options]

  --input, -i        Fichier ou dossier (répétable)
  --output, -o       Fichier de sortie (.md ou .pdf)
  --format, -f       md | pdf          (défaut : md)
  --context, -c      Entier            (défaut : 128000)
  --margin           Flottant          (défaut : 0.15)
  --recursive / --no-recursive
  --include-ext      Liste             (surcharge)
  --exclude-glob     ex. "*.tmp"
  --report           Chemin JSON/MD du rapport
  --dry-run          Analyse seule, pas de corpus
  --yes              N’interagit pas ; échoue si blocage
  --force-images     Accepté, no-op fonctionnel (les images ne bloquent jamais)
  --lang             fr | en | ...
  --config           Chemin JSON
  --list-formats     Affiche les extensions gérées et sort
  --version
```

Codes retour :

| Code | Sens |
|---|---|
| 0 | Corpus généré (warnings images possibles) |
| 1 | Erreur technique |
| 2 | Blocage plafond de contexte |
| 3 | Aucun fichier supporté |
| 4 | Sortie / dossier non inscriptible |

`--yes` + dépassement → code 2, **aucun** fichier corpus (rapport éventuel oui).

---

## 7. Formats de fichiers

### 7.1 Principe

- **Liste blanche** d’extensions. Rien d’inconnu n’est concaténé (évite d’injecter un `.exe` ou un binaire dans le LLM).
- Tout fichier rencontré et **non retenu** est listé dans le rapport (nom, raison). C’est la garantie « pas de perte silencieuse ».
- « Formats faciles » = parseur pur, hors-ligne, licence compatible, sans LibreOffice ni modèle ML.

### 7.2 Obligatoires (doit fonctionner)

| Extension | Extraction | Notes anti-perte |
|---|---|---|
| `.pdf` | Texte page à page | Détection images / pages scannées |
| `.docx` | Paragraphes, tableaux, en-têtes/pieds, notes, zones de texte | Pas le binaire `.doc` |
| `.pptx` | Texte des diapos, notes d’orateur, tableaux | Masques / notes = à extraire si présents |
| `.rtf` | Texte | |
| `.txt` `.text` `.log` | Contenu brut | Encodage : BOM, puis UTF-8, puis cp1252, latin-1 en dernier. Signalé au rapport. |
| `.html` `.htm` | Texte visible | Pas le JS. Titres → Markdown `#` |

### 7.3 Faciles — à faire en v1 si effort faible (doit, sauf justification)

| Extension | Extraction |
|---|---|
| `.md` `.markdown` | Tel quel |
| `.csv` `.tsv` | Texte tabulaire |
| `.xlsx` | Toutes les feuilles, toutes les cellules non vides ; nom de feuille en titre |
| `.ods` `.odt` `.odp` | Si ZIP/XML trivial (OpenDocument) |
| `.xml` `.json` `.yaml` `.yml` `.ini` `.cfg` | Texte / pretty-print |
| `.eml` | En-têtes utiles + corps texte/html→texte |
| `.mhtml` `.mht` | Corps HTML→texte si simple |
| Fichiers de développement (`.py` `.js` `.ts` `.vba` `.sh` `.sql` `.css` `.java` `.c`/`.cpp` `.go` `.rs` etc. — liste complète : `constants.CODE_EXTENSIONS`) | Texte brut (même détection d'encodage que `.txt`) — cas d'usage LLM courant : envoyer une codebase. Limite : dispatch par extension, donc les fichiers sans extension (`Dockerfile`, `Makefile`) ou dotfiles purs (`.gitignore`, `.env`) restent hors périmètre (2026-08-29) |

### 7.4 Explicitement refusés en v1 (rapport, pas d’exception silencieuse)

`.doc` `.ppt` `.xls` (OLE), `.pages`, images pures (`.jpg` `.png` `.tif` `.webp`), audio/vidéo, `.exe` `.dll` `.zip` `.7z`, PDF/Office chiffrés.

Une image seule = **ignorée** + ligne de rapport « fichier image, OCR désactivé, non inclus ».

### 7.5 Fichiers spéciaux à ignorer proprement

- `~$*.docx` / fichiers Office de verrouillage
- Thumbs.db, desktop.ini, `.DS_Store`
- Dossiers `$RECYCLE.BIN`, `System Volume Information`
- Fichiers de sortie CorpusOne déjà présents (`corpus.md`, `corpusone_report.json`) pour éviter de se réingérer

---

## 8. Règles d’extraction et de concaténation

### 8.1 Ordre

1. Tri par **chemin relatif**, ordre naturel (`file2` avant `file10`), insensible à la casse.
2. Option conf : `sort: name | mtime | type` (défaut `name`).

### 8.2 En-tête de source (anti-perte de provenance)

Chaque fichier devient un bloc :

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

Ces métadonnées **comptent** dans le compteur (elles iront au LLM).

### 8.3 Anti-perte — contenu à extraire si présent

| Source | Obligatoire | Si absent |
|---|---|---|
| PDF | Texte de chaque page, dans l’ordre des pages | Page vide → marqueur `[[PAGE 7: aucun texte extractible]]` |
| DOCX | Body, tableaux, headers/footers, footnotes, endnotes | — |
| PPTX | Texte des shapes, tableaux, **notes d’orateur** | Diapo sans texte → `[[DIAPO 3: aucun texte extractible]]` |
| XLSX | Chaque feuille, cellules non vides, ordre A1… | Feuille vide signalée |
| HTML | Titres, paragraphes, listes, tableaux, `alt` des images | `alt` vide + image → warning image |

Interdit de « nettoyer » trop agressivement (supprimer des lignes courtes, des chiffres, des sommaires). Mieux vaut trop de texte que trop peu.

### 8.4 Encodage

Tout est normalisé **UTF-8** en interne et en sortie MD. Le PDF de sortie embarque une police Unicode (ex. DejaVu / Noto **déjà groupée**, licence SIL/OFL ou Apache — pas de police Windows liée à une restriction). Pas de dépendance à Arial.

### 8.5 Optimisations de tokens et alertes de transparence (v0.1.3)

Quatre mécanismes, tous **non silencieux** (une note dans l'en-tête SOURCE et
le rapport signale systématiquement ce qui a été fait) :

- **Déduplication des en-têtes/pieds de page PDF** : une ligne strictement
  identique (première ou dernière ligne de page) répétée sur plusieurs pages
  d'un même PDF n'est conservée qu'une fois. Seuils en conf
  (`PDF_BOILERPLATE_MIN_PAGES/MIN_OCCURRENCES/MIN_RATIO`).
- **Images base64 intégrées (Markdown)** : un `data:image/...;base64,...`
  collé dans un fichier `.md` n'apporte aucune information à un LLM en
  contexte texte (il ne peut pas "voir" l'image depuis le texte brut) —
  le payload est remplacé par une note, l'`alt` est conservé.
- **Doublons de contenu entre fichiers** : deux fichiers différents dont le
  texte extrait est strictement identique (copie, sauvegarde, export
  dupliqué) ne sont comptés/inclus qu'une fois ; le second pointe vers
  l'original (`doublon_de`) au lieu de répéter le contenu.
- **Alerte secrets potentiels** : détection heuristique conservatrice (clé
  AWS, clé privée, jeton Slack/JWT, motif `api_key=...`) qui pose une
  alerte non bloquante (`alerte_secret`) — le texte n'est **jamais**
  modifié ni la valeur trouvée journalisée/affichée, seul le type et le
  numéro de ligne le sont.

---

## 9. Images et pauvreté de texte (deux niveaux)

Deux sévérités **cumulables** sur un même fichier. Un PDF scanné peut
être reconnu par OCR si un moteur est disponible (§9.5) — sinon le
comportement ci-dessous (pas de texte récupéré) reste inchangé.

### 9.1 Warning — le document comporte des images

**Quand** : au moins une image / XObject / blip / média raster détecté, **et** le texte extractible n’est pas sous le seuil critique.

**Effet** :
- Pastille jaune.
- Message : « Contient N images. Leur contenu visuel ne sera pas lu. »
- **Ne bloque pas.** L’utilisateur peut générer.
- Le bloc source contient `alerte: images` et `images: N`.

### 9.2 Alerte importante — peu ou pas de texte

**Quand** (après extraction) :

- texte extractible du fichier, espaces normalisés, **< 80 caractères**, **ou**
- PDF : moyenne **< 50 caractères par page** sur l’ensemble du fichier, **ou**
- PDF : **≥ 30 % des pages** avec **< 20 caractères** et présence d’image sur ces pages.

Ces seuils sont dans la conf (`scan.min_chars_file`, `scan.min_chars_per_page`, `scan.image_page_ratio`).

**Effet** :
- Pastille orange/rouge, plus visible que le warning.
- Message : « Peu ou pas de texte extractible (probable scan ou diapo image). L’IA n’aura quasiment rien de ce fichier. » Pour un PDF, si un
  moteur OCR est disponible (§9.5), le texte est reconnu **avant** ce
  contrôle : un scan bien reconnu ressort donc `READY`/`IMAGES`, pas cette
  alerte — qui ne reste déclenchée que si le texte est resté illisible
  (ou si l'OCR n'était pas disponible).
- Insertion de marqueurs de pages vides (voir 8.3) pour ne pas « avaler » le fichier sans trace.
- **Ne bloque pas** la génération.

### 9.3 Combinaison

Un scan illustré = alerte importante (+ éventuellement compteur d’images). Le bandeau global affiche d’abord le plus grave.

### 9.4 Détection — pistes d’implémentation

- **PDF** : nombre de caractères extraits par page + présence d’images (`/XObject` `/Subtype /Image`). Ne pas se fier au seul nombre de polices.
- **DOCX** : `word/media/*` dans le ZIP ; relations `a:blip`.
- **PPTX** : `ppt/media/*` ; diapo sans `a:t` mais avec image → alerte importante pour cette diapo, agrégée au fichier.

Ne pas alerter pour un minuscule logo si et seulement si le texte est abondant : c’est le **warning images**, pas l’alerte scan. C’est voulu (demande utilisateur : les deux).

### 9.5 OCR des PDF scannés (moteur optionnel, `core/ocr/`)

Portée v1 : **PDF uniquement**. Les fichiers image seuls (`.jpg`/`.png`,
§7.4) et les images intégrées dans `.docx`/`.pptx` restent hors OCR pour
l'instant — même moteur réutilisable plus tard, priorité au cas PDF scanné
(le plus fréquent).

**Classification par page** (`extractors/pdf.py::classify_page`), à partir
du texte déjà extrait par pdfminer (pas de seconde extraction) :

| Classe | Critère | Action |
|---|---|---|
| `native` | Texte utile ≥ seuil (`PDF_OCR_MIN_CHARS_PER_PAGE`), pas d'image | Rien, texte natif conservé tel quel |
| `mixed` | Texte utile ≥ seuil **et** au moins une image sur la page | Texte natif conservé **et** OCR tenté, concaténés (jamais dédupliqués) |
| `ocr` | Texte insuffisant, poubelle (glyphes non mappés `(cid:`/`�`), ou page avec une image et sans texte | OCR tenté |
| `blank` | Aucun texte, aucune image | Rien — pas de texte fantôme |

**Moteur** : Tesseract (Apache-2.0) via son binaire CLI en `subprocess`
(`tesseract stdin stdout -l fra+eng`), jamais une liaison native — chaque
appel est déjà un process isolé, avec son propre timeout par page
(`OCR_PAGE_TIMEOUT_S`). Rastérisation par `pypdfium2` (Apache-2.0/BSD-3) ;
`PyMuPDF` explicitement écarté (AGPL-3.0). Plafonds de sécurité :
`OCR_MAX_PAGES_PER_FILE`, `OCR_MAX_PIXELS_PER_PAGE` (bombe de rendu PDF).

**Disponibilité, jamais bloquante** : `core/ocr/registry.py::resolve_ocr_engine()`
ne lève jamais d'exception — si Tesseract n'est trouvé ni bundlé ni sur le
PATH système, le comportement est strictement identique à avant l'ajout de
cette fonctionnalité (§9.2), plus une note de transparence expliquant
pourquoi (`extra_metadata["ocr"]`, visible dans l'en-tête SOURCE et le
rapport, jamais silencieux — CdC §8).

**Distribution — deux exe** : `CorpusOne.exe` n'embarque jamais Tesseract
(taille et promesse « zéro dépendance » inchangées). `CorpusOne-OCR.exe`
(build séparé, `CorpusOne-OCR.spec`) l'embarque avec les modèles `fra`+`eng`
(`tessdata_fast`) et fonctionne sans aucune installation sur la machine
cible. Un utilisateur de `CorpusOne.exe` peut aussi installer Tesseract à
part (ex. UB-Mannheim) : l'OCR s'active alors automatiquement, sans exe
distinct.

---

## 10. Compteur de contexte

### 10.1 Estimateur générique (pas un modèle nommé)

Formule unique, documentée dans l’UI :

```text
octets_utf8 = nombre d’octets UTF-8 du texte qui irait au LLM
                 (contenu + en-têtes SOURCE)
tokens_estimes = ceil(octets_utf8 / 4)
tokens_avec_marge = ceil(tokens_estimes * (1 + margin))
                   # margin = 0,15 par défaut
```

Justification : approximation publique largement utilisée (~4 octets / token en moyenne pour l’anglais/français technique). La marge **+15 %** couvre la variance (code, tableaux, langues agglutinantes).

**Interdit** d’appeler une API pour compter. **Pas obligatoire** d’embarquer `tiktoken`. Si le développeur l’ajoute (MIT), les fichiers d’encodage doivent être **dans le bundle**, cache local, **zéro réseau**. L’UI reste « compteur générique », pas « tokens GPT » **par défaut** — voir §10.6 pour le moteur précis optionnel qui, lui, a le droit de se nommer.

### 10.2 Double contrôle (entrée et total)

Soit `L` le plafond (`context_limit`, défaut **128000**).

Pour chaque fichier i, après extraction :

```text
si tokens_avec_marge(i) > L  →  fichier BLOQUANT
```

Après agrégation (en-têtes compris) :

```text
si tokens_avec_marge(total) > L  →  TOTAL BLOQUANT
```

Un seul fichier à 128K+ « n’est plus possible » : **génération interdite**, même s’il est seul.

Égalité : `>` bloque ; `== L` passe (limite inclusive).

### 10.3 Dépassement = NON (blocage)

- GUI : **Générer** disabled ; explication en français ; champs plafond éditable → recalcul immédiat sans ré-extraire si les textes sont en cache mémoire.
- CLI : exit 2, pas de fichier corpus.
- Le rapport est quand même émis (pour comprendre qui dépasse).

L’utilisateur peut **augmenter L** (ex. 200000) et générer. Aucune valeur magique max imposée, mais avertir au-delà de 1 000 000 (« inhabituel, fichier énorme »).

### 10.4 Images = OUI (pas de blocage)

Les warnings / alertes images n’empêchent jamais la génération.

### 10.5 Affichage

Toujours montrer les **deux** chiffres : brut et +15 %. Le comparatif au plafond utilise **uniquement** `tokens_avec_marge`.

Exemple : 120 000 estimés → 138 000 avec marge → bloqué à 128 000. L’utilisateur doit comprendre pourquoi « 120K » est refusé : **à cause de la marge**. Phrase UI obligatoire.

### 10.6 Moteurs de comptage précis (optionnel)

Le compteur générique (§10.1) reste le **défaut**. En plus, un registre de
moteurs de comptage précis (`core/tokenizers/`, même pattern que le registre
d’extracteurs) permet de choisir un moteur qui compte les tokens réels d’un
fournisseur — CLI `--tokenizer-engine`, config `tokenizer_engine`, GUI
« Précision du comptage ». Un id inconnu ou indisponible retombe toujours
silencieusement sur l’approximation (jamais de blocage à cause d’un choix de
moteur).

v1 : **Mistral** (tokenizer Tekken). v2 : **OpenAI** (encodage `o200k_base`,
GPT-4o/4.1/o-série) — même architecture, un fichier `.tiktoken` officiel
vendoré (`assets/o200k_base.tiktoken`, hash SHA-256 vérifié à l'identique de
celui que `tiktoken` attend) plutôt que le mécanisme de téléchargement par
défaut de `tiktoken.get_encoding()`. Contraintes inchangées (NFR-02/NFR-06)
— un moteur précis n’est accepté que si :

- **Zéro réseau** : vocabulaire chargé depuis un fichier embarqué, jamais
  téléchargé à l’exécution.
- **Licence compatible** : la dépendance retenue doit être Apache-2.0/MIT/BSD.
  Le moteur Mistral n’installe **pas** le paquet `mistral-common` (dont une
  dépendance transitive, `pycountry`, est LGPL-2.1) : il dépend uniquement de
  `tiktoken` (MIT) et d’un fichier de vocabulaire Tekken extrait du dépôt
  `mistral-common` (Apache-2.0) et vendoré dans `assets/` — voir
  `core/tokenizers/mistral.py` et `NOTICE`. Le moteur OpenAI dépend
  uniquement de `tiktoken` (déjà présent) — voir `core/tokenizers/openai.py`.
- Quand le total agrégé est produit par un moteur précis, il est recalculé
  comme la **somme** des comptes par fichier (pas un recalcul depuis un total
  d’octets, impossible à faire correctement pour un vrai tokenizer BPE).

---

## 11. Sorties

### 11.1 Markdown (défaut, recommandé IA)

- UTF-8, LF ou CRLF (conf, défaut CRLF sous Windows).
- Structure : titre du corpus, date, plafond, puis blocs SOURCE.
- Pas de binaire encodé en base64.

### 11.2 PDF

- PDF texte généré (pas un merge des PDF sources).
- Police Unicode embarquée.
- En-tête de page : nom du corpus + n° de page.
- Saut de page entre sources si possible.
- Objectif : relecture humaine / archive. Qualité visuelle secondaire.

Bibliothèque conseillée : **ReportLab** (BSD) ou **fpdf2** si licence compatible au moment de l’implémentation. Vérifier avant inclusion. Interdit WeasyPrint (dépendances système). Interdit d’appeler Word/LibreOffice.

### 11.3 Rapport (toujours)

Deux fichiers possibles à côté de la sortie :

- `*_rapport.md` — lisible
- `*_rapport.json` — pour IT / scripts

Contenu : horodatage, version, plafond, marge, totaux, liste de tous les fichiers du dossier (retenus ou non), statuts, erreurs, encodages détectés, nombre d’images, caractères extraits.

---

## 12. Configuration (schéma)

`CorpusOne.json` exemple :

```json
{
  "lang": "fr",
  "format": "md",
  "context_limit": 128000,
  "margin": 0.15,
  "recursive": true,
  "sort": "name",
  "open_output_folder": true,
  "scan": {
    "min_chars_file": 80,
    "min_chars_per_page": 50,
    "sparse_page_chars": 20,
    "sparse_page_ratio": 0.30
  },
  "exclude_globs": ["~$ *", "Thumbs.db", "desktop.ini"]
}
```

Champs inconnus = ignorés (forward compatible). Validation : types et min/max ; message clair si JSON cassé, bascule sur défauts + warning.

---

## 13. Architecture technique recommandée (non imposée, mais contrainte « rapide + portable »)

### 13.1 Ce qu’il ne faut pas faire

| Approche | Pourquoi non |
|---|---|
| LibreOffice / `soffice` headless | Lourd, peu portable, chemins Program Files, lent |
| Docling **comme runtime** | Excellent outil, mais modèles, 1er lancement, RAM, trop gros pour un exe portable hors-ligne |
| MarkItDown **tel quel avec extras Azure / OCR / YouTube** | Réseau, hors besoin |
| PyMuPDF | **AGPL-3.0**, incompatible Apache 2.0 du livrable |
| Poppler `pdftotext` | GPL |
| Appel Microsoft 365 / Graph | Réseau, compte |

### 13.2 Ce qu’il faut faire

Un **petit orchestrateur** + extracteurs par format, inspirés des projets ci-dessous, code **vendored ou réécrit**, attributions dans `NOTICE`.

Stack indicative (le développeur peut équivalent Rust/Go/.NET self-contained si plus rapide au démarrage) :

- Langage : **Python 3.11+** *ou* **C# .NET 8 self-contained** *ou* **Go**. Critère : temps de lancement GUI et taille raisonnable (< ~80 Mo visé, < 150 Mo max).
- GUI : **PySide6** (LGPL — **attention** : LGPL impose liaison dynamique, pas de static link). Plus sûr pour Apache 2.0 : **Dear PyGui** (MIT), **FreeSimpleGUI** selon licence, ou **WinUI / WPF** en C# (pas de copyleft). **Recommandation** : C# WPF/WinUI si l’équipe est .NET ; sinon Python + Dear PyGui (MIT) ou Tkinter (intégré).
- Empaquetage Python : PyInstaller **onedir** préféré à onefile pour la vitesse.
- Zéro thread réseau : pas de `requests` sauf si jamais appelé ; greps CI interdits sur `http://`.

### 13.3 Pipeline

```text
Entrée dossier
  → inventaire (liste blanche, ignores)
  → extraction parallèle (fichiers, pas les pages) bornée CPU-1
  → mesure images + pauvreté texte
  → compteur par fichier
  → agrégation + compteur total
  → décision bloquer / autoriser
  → écriture MD ou PDF + rapport
```

Cache mémoire des textes extraits pour recalcul instantané si l’utilisateur change le plafond.

Annulation : bouton « Arrêter » ; CLI Ctrl+C.

---

## 14. Références open source — s’en inspirer (pas forcément dépendre)

Le développeur **doit lire** ces projets avant d’écrire les extracteurs. Recopier des idées et des structures, pas des modules à licence incompatible. Conserver copyright + NOTICE.

### 14.1 Orchestration « dossier → Markdown pour LLM »

**MarkItDown** (Microsoft) — MIT  
https://github.com/microsoft/markitdown

- Convertit PDF, PowerPoint, Word, Excel, HTML, CSV, JSON, XML, ZIP, etc. vers Markdown pour LLM.
- CLI simple (`markitdown fichier -o out.md`).
- Philosophie : structure légère (titres, listes, tableaux), pas de fidélité PAO.
- **À reprendre** : dispatch par type MIME/extension ; sortie Markdown « token-efficient » ; traitement Office via ZIP/XML.
- **À ne pas reprendre** : plugins Azure, YouTube, OCR cloud, `convert()` trop permissif sur des URI distantes. CorpusOne = fichiers locaux uniquement.

### 14.2 Qualité PDF / export structuré (inspiration, pas runtime)

**Docling** (Linux Foundation / IBM Research) — MIT  
https://github.com/docling-project/docling  
https://docling.ai/

- Parse PDF, DOCX, PPTX, XLSX, HTML, e-mail, ODF, texte…
- Export Markdown / JSON, exécution locale possible.
- **À reprendre** : idée d’un document interne unifié puis export MD ; conscience des tableaux.
- **À ne pas embarquer** : pipelines VLM, OCR, poids et modèles. Incompatible avec « exe léger hors-ligne sans droit admin » en v1.

### 14.3 PDF — extraction texte (runtime probable)

**pdfminer.six** — MIT, pur Python  
https://pypi.org/project/pdfminer.six/

- Extraction depuis le code source PDF, analyse de layout, images optionnelles.
- Idéal pour compter le texte **par page** (heuristique scan).
- Plus lent que PyMuPDF, mais **licence OK** et zéro binaire C.

**pypdf** — BSD-3, pur Python  
https://pypi.org/project/pypdf/

- Rapide pour inventaire, pages, métadonnées, détection encryption.
- Extraction texte plus rustique : possible en premier passage, pdfminer.six en repli si texte trop pauvre alors que le PDF n’est pas visuellement vide… **Attention** : sans OCR on ne « rattrape » pas un scan. Le repli sert aux encodages bizarres, pas à la magie.

**pdfplumber** — MIT, basé sur pdfminer.six  
Utile si tableaux PDF fréquents. Optionnel v1.1.

**Interdit** : PyMuPDF (AGPL-3.0).

Référence comparative licences 2026 : PyPDF BSD-3, pdfminer.six MIT, PyMuPDF AGPL, ReportLab BSD.  
https://www.nutrient.io/blog/best-python-pdf-libraries/

### 14.4 Office Open XML

- **python-docx** (MIT) — paragraphes, tableaux, sections.
- **python-pptx** (MIT) — diapos, shapes, notes.
- **openpyxl** (MIT) — xlsx.
- Un `.docx`/`.pptx` est un **ZIP**. S’inspirer de MarkItDown : ouvrir le ZIP, parser `document.xml` / `slide*.xml`, lister `media/`.

RTF : parser léger (strip des groupes de contrôle) ou bibliothèque MIT/BSD à documenter. Pas Word Automation (`win32com`) : dépend d’Office installé, lent, fragile, parfois des licences.

### 14.5 HTML / texte

- **BeautifulSoup4** + **lxml** (MIT / BSD) ou html.parser stdlib.
- **charset-normalizer** (MIT) plutôt que `chardet` (LGPL).

### 14.6 Concaténation style « prompt LLM »

**files-to-prompt** (Simon Willison) — Apache 2.0  
https://github.com/simonw/files-to-prompt

- Parcourt un dossier, concatène avec séparateurs de noms de fichiers.
- **À reprendre** : en-têtes de provenance, CLI simple, esprit « un blob pour le LLM ».
- **Limite** : ne convertit pas PDF/Office ; CorpusOne apporte cette couche.

### 14.7 PDF en écriture

**ReportLab** — BSD (édition open source)  
Création PDF texte, sauts de page, polices embarquées. Ne lit pas les PDF.

### 14.8 Compteur

Approximation documentée par l’écosystème BPE : un token ≈ 4 octets en moyenne (voir tiktoken, MIT, https://github.com/openai/tiktoken — *« each token corresponds to about 4 bytes »*). CorpusOne **utilise cette règle + 15 %**, sans se prétendre tokenizer d’un fournisseur.

Si tiktoken est embarqué un jour : encodages dans le bundle, variable d’environnement de cache **locale**, tests avec réseau coupé.

### 14.9 GUI / portable Windows

S’inspirer des pratiques « portable app » : rien dans HKLM, conf côte-à-côte, fonctionnement depuis USB. Pas besoin d’installer Visual C++ redist si self-contained ; sinon **documenter** le redist et fournir le merge module **sans admin** (DLL privées dans `_internal`, jamais au GAC).

---

## 15. Internationalisation

- Toutes les chaînes UI, CLI, rapport utilisateur via catalogue (gettext `.po` ou fichiers JSON `i18n/fr.json`).
- v1 : **français complet**.
- v1 : **anglais** au moins amorcé (fichiers présents, même 80 %).
- Ajouter une langue = ajouter un fichier, sans rebuild si possible (chargement runtime).
- Formats nombres : espaces insécables FR (`96 830`).
- Le **contenu extrait** n’est pas traduit.

---

## 16. Sécurité, vie privée, IT

- Données : traitement **100 % local**. Aucun fichier envoyé.
- Pas de télémétrie.
- N’exécute pas de macros Office, n’ouvre pas de lien, ne résout pas les `file://` externes.
- PDF avec actions / JavaScript : ignorer, extraire le texte seulement.
- Chemins : pas de traversal ; on ne suit pas les jonctions de façon illimitée (profondeur max configurable, défaut 12).
- Antivirus : l’exe Python/PyInstaller déclenche parfois SmartScreen. Fournir un hash SHA-256 et, si l’organisation signe, une signature Authenticode **utilisateur** (hors obligation v1).
- Mots de passe : jamais logués.

Contexte d’usage typique : poste d’administration / support, documents internes. Le rapport ne doit pas recopier tout le corpus (juste stats + chemins).

---

## 17. Performance (objectifs mesurables)

Machine de référence : Windows 11, CPU 4 cœurs, SSD, 8 Go RAM, session utilisateur standard.

| Cas | Objectif |
|---|---|
| Ouverture GUI | < 3 s |
| Analyse 20 DOCX/PPTX/PDF texte, ~50 Mo total | < 30 s |
| Analyse 200 petits TXT/HTML | < 15 s |
| RAM | < 500 Mo hors très gros PDF |
| Un PDF texte 200 pages | < 20 s |

Si un fichier dépasse 50 Mo : message « fichier volumineux, patience » plutôt qu’un gel sans feedback. Progression **par fichier** au minimum.

---

## 18. Journalisation

- Niveau user : la liste et le rapport.
- Niveau debug : fichier `%TEMP%\CorpusOne\corpusone.log` rotation 2 Mo, **sans contenu des documents** (chemins et erreurs seulement).
- CLI `--verbose` : stderr.

---

## 19. Tests d’acceptation

Le livrable est refusé si un cas ci-dessous échoue.

### 19.1 Portabilité

- Copier le dossier sur le Bureau d’un compte **sans** droits admin, lancer : OK.
- Copier sur une clé USB, lancer sur un autre PC Win10/11 : OK.
- Désactiver le réseau (mode avion) : OK, aucun timeout réseau.
- Exe dans un chemin en lecture seule + sortie ailleurs : OK.

### 19.2 Fonctionnels

- Dossier mixte PDF+DOCX+PPTX+RTF+TXT+HTML → un MD unique, chaque source identifiable.
- Même dossier → un PDF unique, texte sélectionnable.
- Un PDF scanné (image, 0 texte) → alerte importante, marqueurs de pages, génération **possible**.
- Un PPTX avec photos et beaucoup de puces → warning images, génération **possible**.
- Un TXT dont le compteur +15 % > 128000 → **pas** de corpus, code 2 / bouton inactif.
- Trois fichiers 50k+marge chacun, total > 128k → blocage total, aucun fichier « trop gros » isolément : message sur **le total**.
- Monter le plafond à 400000 → Générer redevient actif sans redemander les fichiers.
- Fichier `.exe` dans le dossier → ignoré, présent au rapport.
- `~$w.docx` → ignoré.
- PDF mot de passe → erreur fichier, pas de crash global.
- CLI ` --dry-run` → pas de corpus, rapport stats.

### 19.3 Licence

- `NOTICE` liste toutes les deps.
- Scan `pip-licenses` / équivalent : pas de GPL/AGPL.
- LICENSE Apache-2.0 à la racine du code source.

### 19.4 I18n

- UI fr par défaut.
- `lang: en` → interface anglaise (chaînes principales).

---

## 20. Critères UX (recette « comme un utilisateur »)

Un collègue non développeur doit pouvoir, **sans notice** :

1. Double-cliquer.
2. Glisser un dossier.
3. Comprendre le compteur.
4. Voir pourquoi c’est bloqué.
5. Changer 128000.
6. Récupérer `corpus.md`.

Si une phrase d’UI nécessite de connaître BPE, GPT ou « tokenizer », elle est **non conforme**. On dit « volume estimé pour une IA » et « plafond ».

---

## 21. Livrables attendus du développeur

1. Code source, Apache 2.0, README de build hors-ligne.
2. Binaire Windows x64 portable.
3. `NOTICE` + licences tierces.
4. Jeu de fichiers de test (petit, anonymisé) + script de recette.
5. Mini guide utilisateur **français** (1-2 pages) : usage GUI et 5 exemples CLI.
6. Journal des écarts si un format « facile » est reporté (justifier).

Hors v1 : store Microsoft, signatures EV, traductions additionnelles, OCR optionnel pluggable.

---

## 22. Décisions tranchées (ne plus rediscuter)

| Sujet | Décision |
|---|---|
| Interfaces | GUI + glisser-déposer + CLI |
| Sortie | MD ou PDF au choix, défaut MD |
| Compteur | Générique, octets/4, **marge +15 %** |
| Plafond | Variable, défaut **128 000**, test **fichier et total** |
| Dépassement plafond | **Bloque** la génération |
| Images | **Ne bloque pas** |
| Peu/pas de texte | Alerte **plus grave**, ne bloque pas |
| Images + texte normal | Warning |
| OCR | Non |
| Réseau | Interdit |
| Admin | Interdit |
| Langue | FR + i18n |
| Licence | Apache 2.0 |
| Stack | Libre, **rapidité** et **portabilité** juges de paix |
| Perte de données | Interdite **en silence** ; scans = perte assumée **signalée** |

---

## 23. Glossaire

| Terme | Sens ici |
|---|---|
| Token estimé | Unité générique ≈ 4 octets UTF-8, **pas** un token d’un fournisseur |
| Marge | +15 % appliquée **avant** comparaison au plafond |
| Plafond / contexte | Variable `context_limit` |
| Warning images | Des images existent ; le texte par ailleurs est lu |
| Alerte importante | Quasi pas de texte extractible |
| Portable | Pas d’installeur machine, pas d’admin, conf utilisateur |
| Corpus | Fichier unique de sortie |

---

## 24. Maquette textuelle de la fenêtre

```text
┌ CorpusOne — Assembler un dossier pour une IA ─────────────────────┐
│                                                                   │
│  ┌─ Glissez un dossier ici, ou [ Choisir un dossier… ] ─────────┐ │
│  │  D:\CallCenter\Procedure_2026                                │ │
│  └──────────────────────────────────────────────────────────────┘ │
│  Sortie : (•) Markdown   ( ) PDF     ☐ Sous-dossiers (coché)     │
│  Plafond : [128000] tokens estimés     Marge +15 % (non décochable)│
│                                                                   │
│  Fichier                    Type   +15%    Statut                 │
│  accueil.html               html   1 200   Prêt                   │
│  process.docx               docx   18 400  Images (3)             │
│  slides_formation.pptx      pptx   9 100   Images (12)            │
│  scan_badge.pdf             pdf      140   Peu de texte           │
│  dump.exe                   exe        —   Ignoré                 │
│                                                                   │
│  Estimé 92 000   Avec marge 105 800   Plafond 128 000   [====  ]  │
│  3 documents contiennent des images (non lues).                   │
│  1 document a peu de texte (probable scan). Vous pouvez continuer.│
│                                                                   │
│                    [ Générer corpus.md ]     [ Rapport ]          │
└───────────────────────────────────────────────────────────────────┘
```

État bloqué : jauge rouge, bouton grisé, phrase du type  
« Impossible : le total avec marge (139 000) dépasse 128 000. Augmentez le plafond ou retirez des fichiers. »

---

*Fin du cahier des charges v1.0 — CorpusOne.*
