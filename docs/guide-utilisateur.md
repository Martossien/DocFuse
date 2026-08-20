# Guide utilisateur DocFuse / CorpusOne

> Mini guide français — usage GUI et exemples CLI (CdC §21.5)
> Version 0.1.1 beta — 20 août 2026

---

## Qu'est-ce que DocFuse ?

DocFuse (nom de code CorpusOne) est un outil qui assemble les documents d'un ou plusieurs
dossiers, ou une sélection précise de fichiers (PDF, Word, PowerPoint, Excel, HTML,
texte, etc.), en **un seul fichier** prêt à être donné à une IA (LLM). Il extrait le
texte, estime le nombre de tokens de chaque fichier et du corpus complet, puis vous
avertit si le plafond de contexte est dépassé.

**Pas d'installation, pas de droits admin, pas d'internet.** Ça marche depuis une clé USB.

---

## Utilisation avec l'interface graphique

### 1. Lancer DocFuse

Double-cliquez sur `CorpusOne.exe`. La fenêtre s'ouvre (pas de console noire).

### 2. Choisir les documents

- Cliquez sur **« Ajouter un dossier… »** pour analyser son contenu et, si l'option est
  cochée, ses sous-dossiers.
- Cliquez sur **« Ajouter des fichiers… »** pour sélectionner uniquement certains
  fichiers. Chaque nouvelle sélection s'ajoute aux précédentes ; les autres fichiers
  présents dans leur dossier ne sont pas ajoutés.
- Vous pouvez aussi glisser-déposer un dossier ou plusieurs fichiers sur la zone du haut.
- L'analyse démarre automatiquement.

Lorsqu'un dossier contient de nombreux documents, ils apparaissent d'abord avec le statut
**En attente**, puis leurs estimations sont affichées au fur et à mesure de l'extraction.

### 3. Comprendre la liste

Chaque fichier apparaît avec son statut :

| Couleur | Statut | Signification |
|---|---|---|
| 🟢 Vert | Prêt | Texte extractible, sous le plafond |
| 🟡 Jaune | Images | Contient des images — le texte sera pris, le visuel ne sera pas lu |
| 🟠 Orange | Peu de texte | Probablement un scan — l'IA n'aura presque rien de ce fichier |
| 🔴 Rouge | Trop volumineux | Fichier seul ≥ plafond → génération bloquée |
| ⚪ Gris | Ignoré | Extension non supportée (ex: .exe, .jpg) |
| 🔴 Rouge | Erreur | Corrompu, protégé par mot de passe |

Les colonnes **Texte estimé** et **Contexte +15 %** donnent le nombre approximatif de
tokens pour chaque fichier. Le bouton **Retirer** enlève immédiatement un document du
corpus et recalcule le total sans relancer l'extraction. Le retrait reste appliqué si
vous cliquez ensuite sur **Analyser**.

### 4. Le compteur de contexte

En bas, un bandeau affiche :
- **Estimé** : volume de tokens estimé (octets UTF-8 / 4)
- **Avec marge +15 %** : estimation + marge de sécurité
- **Plafond** : limite de contexte (128 000 par défaut, modifiable)
- **Jauge** : verte (< 80 %), orange (80-99 %), rouge (≥ 100 %)

Si la jauge est rouge, le bouton **Générer** est désactivé.
**Solution** : montez le plafond ou cliquez sur **Retirer** pour les documents inutiles
ou les plus volumineux.

### 5. Générer le corpus

- Choisissez **Markdown** (recommandé pour l'IA) ou **PDF** (relecture humaine).
- Modifiez le plafond si besoin (recalcul instantané sans ré-extraction).
- Cliquez sur **Générer**.
- Le fichier `corpus.md` (ou `corpus.pdf`) est créé dans `CorpusOne_output/`.
- Le rapport d'exécution est généré à côté (`corpus_rapport.md` + `.json`).

---

## Utilisation en ligne de commande

### Syntaxe

```
CorpusOne.exe --input <chemin> [options]
```

### Exemples

**Assembler un dossier en Markdown :**
```
CorpusOne.exe -i "D:\Projets\Rapports" -o "D:\Sortie\corpus.md"
```

**Assembler en PDF :**
```
CorpusOne.exe -i "D:\Projets" -o "corpus.pdf" --format pdf
```

**Analyse seule (sans générer), avec rapport :**
```
CorpusOne.exe -i "D:\Projets" --dry-run --report "D:\rapport.json"
```

**Changer le plafond de contexte :**
```
CorpusOne.exe -i "D:\Projets" --context 200000
```

**Assembler uniquement plusieurs fichiers précis :**
```
CorpusOne.exe -i "D:\Contrats\contrat.pdf" -i "D:\Notes\synthese.docx" -o "D:\Sortie\corpus.md"
```

Chaque option `--input` est prise en compte. Une liste de fichiers n'est jamais élargie
automatiquement à tout leur dossier parent.

**Non-interactif (scripts) — échoue si blocage :**
```
CorpusOne.exe -i "D:\Projets" --yes -o "corpus.md"
```

**Ne prendre que les .txt et .md :**
```
CorpusOne.exe -i "D:\Projets" --include-ext ".txt" --include-ext ".md"
```

### Codes retour

| Code | Sens |
|---|---|
| 0 | Corpus généré (warnings images possibles) |
| 1 | Erreur technique |
| 2 | Blocage plafond de contexte |
| 3 | Aucun fichier supporté |
| 4 | Sortie / dossier non inscriptible |

---

## Configuration

Créez un fichier `CorpusOne.json` à côté de l'exécutable :

```json
{
  "lang": "fr",
  "format": "md",
  "context_limit": 128000,
  "margin": 0.15,
  "recursive": true,
  "sort": "name",
  "open_output_folder": true,
  "max_depth": 12,
  "scan": {
    "min_chars_file": 80,
    "min_chars_per_page": 50,
    "sparse_page_chars": 20,
    "sparse_page_ratio": 0.30
  },
  "exclude_globs": ["~$*", "Thumbs.db", "desktop.ini"]
}
```

---

## Formats supportés

| Extension | Extraction |
|---|---|
| `.pdf` | Texte page à page + détection images/scans |
| `.docx` | Paragraphes, tableaux, en-têtes, notes, zones de texte |
| `.pptx` | Diapos + notes d'orateur |
| `.xlsx` | Toutes les feuilles et cellules |
| `.rtf` | Texte |
| `.html` `.htm` | Texte visible + titres → Markdown |
| `.txt` `.text` `.log` | Contenu brut (BOM, UTF-8, cp1252, latin-1) |
| `.md` `.markdown` | Tel quel |
| `.csv` `.tsv` | Texte tabulaire (délimiteur ; auto) |
| `.odt` `.ods` `.odp` | OpenDocument (ZIP/XML) |
| `.xml` `.json` `.yaml` `.ini` | Pretty-print |
| `.eml` `.mhtml` `.mht` | En-têtes + corps HTML→texte |

**Non supportés** : `.doc`/`.ppt`/`.xls` (OLE), images pures, audio/vidéo, fichiers chiffrés.

---

## FAQ

**« Mon PDF est un scan, l'IA n'aura rien ? »**
Correct. DocFuse ne fait pas d'OCR. Vous verrez une alerte orange « Peu de texte ».
Le texte extractible (souvent vide) sera inclus avec des marqueurs `[[PAGE N: aucun texte]]`.

**« Le bouton Générer est désactivé »**
Le total avec marge (+15 %) dépasse le plafond. Montez le plafond ou retirez des fichiers.

**« Mes images sont ignorées ? »**
Les images dans les documents (DOCX, PPTX, PDF) sont détectées (warning jaune) mais
leur contenu visuel n'est pas lu. Le texte autour est bien extrait. Les fichiers image
seuls (`.jpg`, `.png`) sont ignorés avec un message dans le rapport.

**« Combien de tokens pour mon corpus ? »**
L'estimation utilise la formule : `octets_UTF-8 / 4` avec une marge de +15 %.
C'est un estimateur générique, pas un tokenizer d'un fournisseur spécifique. La GUI
affiche l'estimation pour chaque fichier ainsi que le total du corpus.
