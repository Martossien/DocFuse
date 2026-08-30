# Contributing to DocFuse

Merci de votre intérêt pour DocFuse (anciennement CorpusOne). Toute contribution
est la bienvenue :
corrections de bugs, nouvelles fonctionnalités, nouveaux extracteurs de formats,
traductions, documentation, rapports de bugs, revues de PRs.

> Pour les questions de comportement au sein de la communauté, voir
> [CODE_OF_CONDUCT.md](./CODE_OF_CONDUCT.md).
> Pour signaler une faille de sécurité, voir [SECURITY.md](./SECURITY.md).

## Pré-requis

- **Python 3.11+** (testé sur 3.11, 3.12, 3.13).
- **Git** récent.
- Sous Windows pour le build portable : **PyInstaller 6.x**.
- Sous Linux pour reproduire le binaire : Wine + Python Windows.

## Mise en place de l'environnement de développement

```bash
# Cloner le dépôt
git clone https://github.com/Martossien/DocFuse.git
cd DocFuse

# Environnement virtuel (recommandé)
python -m venv .venv
source .venv/bin/activate          # Linux / macOS
# .venv\Scripts\activate           # Windows PowerShell

# Installation en mode éditable avec les dépendances de dev + l'interface
# graphique (extra `gui` : customtkinter + tkinterdnd2). Sans `gui`, seuls
# la CLI et la bibliothèque sont installées.
pip install -e ".[dev,gui]"

# Vérifier que tout fonctionne
pytest tests/ -v
ruff check src/ tests/
mypy --strict src/docfuse/
```

## Workflow de contribution

1. **Fork** le dépôt et créer une branche depuis `main` :
   ```bash
   git checkout -b feat/ma-nouvelle-fonctionnalite
   # ou
   git checkout -b fix/issue-123-courte-description
   ```
2. **Commits** : nous suivons [Conventional Commits](https://www.conventionalcommits.org/).
   Préfixes utilisés : `feat:`, `fix:`, `refactor:`, `test:`, `docs:`, `chore:`.
   Décrire le *pourquoi*, pas le *quoi* (le diff le montre déjà).
3. **Tests** : toute modification de code doit être accompagnée d'un test unitaire
   ou d'acceptation. La suite complète doit rester verte :
   ```bash
   pytest tests/ -v
   ruff check src/ tests/
   ruff format --check src/ tests/
   mypy --strict src/docfuse/
   ```
4. **Ouvrir une Pull Request** vers `main` avec un titre clair et une description
   qui rappelle le problème traité, l'approche choisie et les captures / logs
   pertinents. Liez l'issue concernée si elle existe (`Fixes #123`).
5. La CI GitHub Actions (Python 3.11/3.12/3.13 × Windows/Ubuntu) doit passer
   avant merge.

## Conventions de code

- **Type hints obligatoires** sur tout le code public. `mypy --strict` doit passer.
- **Style** : `ruff` pour le lint et le format (configuré dans `pyproject.toml`).
  Ne pas reformater manuellement, laisser `ruff format` faire.
- **Docstrings** : Google-style, en français ou en anglais (cohérent dans le module).
- **Pas de dépendances GPL/AGPL** : la licence du projet est Apache 2.0 et le
  tableau des licences autorisées est strict (cf. `tests/test_acceptance.py`).
- **Pas d'accès réseau** dans le code runtime. Un test vérifie qu'aucune lib
  importée ne tente de connexion (cf. `TestPortability::test_no_network_imports`).
- **i18n** : toutes les chaînes affichées à l'utilisateur passent par
  `docfuse.i18n.t()`. Pas de chaîne en dur dans le code.

## Ajouter un extracteur de format

Un extracteur = un fichier dans `src/docfuse/extractors/`. Le pattern :

1. Créer `src/docfuse/extractors/mon_format.py` avec une classe héritant de
   `Extractor` (cf. `src/docfuse/extractors/base.py`).
2. Déclarer l'extension dans `SUPPORTED_EXTENSIONS` (`src/docfuse/constants.py`).
3. Enregistrer avec le décorateur `@register` — c'est automatique, aucune
   ligne à toucher ailleurs.
4. Ajouter un test dans `tests/test_extractors/test_mon_format.py`.
5. Si votre extracteur a une dépendance externe, l'ajouter dans `dependencies`
   du `pyproject.toml` et vérifier sa licence (`pip-licenses --allow-only=...`).

## Documentation et journaux

Après chaque session de développement :

- Mettre à jour `docs/journal-avancement.md` (statut, métriques).
- Ajouter une entrée dans `docs/journal-decisions.md` (numérotée D-NNN) pour
  toute décision d'architecture ou de stack.
- Si la décision touche au code public ou à la stack, mettre aussi à jour
  `AGENTS.md`.

## Signalement de bugs

Ouvrir une [issue](https://github.com/Martossien/DocFuse/issues) avec :

- Version de DocFuse (`docfuse --version`).
- Système d'exploitation et version.
- Commande exacte ou capture de la GUI.
- Fichier concerné (si possible, un échantillon anonymisé).
- Comportement attendu vs observé.
- Sortie de `pytest tests/ -v` le cas échéant.

## Questions ?

Ouvrez une issue avec le tag `question`. Il n'y a pas encore de canal de
discussion dédié — la page *Issues* fait office de forum pour l'instant.

Merci de contribuer à DocFuse !
