# Changelog

Toutes les modifications notables de DocFuse sont documentées ici.

Le format suit [Keep a Changelog](https://keepachangelog.com/fr/1.1.0/),
et ce projet adhère au [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

> Pour les notes de version détaillées (visibles sur la page GitHub Releases),
> voir le dossier [`docs/releases/`](./docs/releases/).

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

[0.1.1]: https://github.com/Martossien/DocFuse/releases/tag/v0.1.1
[0.1.1-beta]: https://github.com/Martossien/DocFuse/compare/166e595...main
[0.1.0]: https://github.com/Martossien/DocFuse/releases/tag/v0.1.1
