# DocFuse / CorpusOne

Outil portable Windows d'assemblage de documents bureautiques vers un corpus unique (Markdown ou PDF) destiné aux LLM.

## Caractéristiques

- **Portable** : aucune installation, aucun droit administrateur, fonctionne depuis une clé USB
- **Hors-ligne** : aucune connexion réseau requise
- **Multi-format** : PDF, DOCX, PPTX, XLSX, RTF, HTML, TXT, Markdown, CSV, ODF, XML, JSON, EML
- **Compteur de contexte générique** : estimation tokens (octets UTF-8 / 4) + marge 15 %
- **Contrôle de plafond** : blocage si un fichier ou le total dépasse le plafond
- **Détection d'images** : alerte si un document contient des images (pas d'OCR)
- **Détection de scans** : alerte si un PDF a peu ou pas de texte extractible
- **Rapport d'exécution** : liste tous les fichiers (traités, ignorés, erreurs)
- **Interface graphique + CLI + glisser-déposer**
- **i18n** : français par défaut, anglais supporté
- **Licence Apache 2.0** (aucune dépendance GPL/AGPL)

## Installation (développement)

```bash
pip install -e ".[dev]"
```

## Utilisation

### CLI

```bash
docfuse --input "D:\Dossier" --output "corpus.md" --format md
```

### GUI

```bash
python -m docfuse
```

## Tests

```bash
pytest tests/ -v
ruff check src/ tests/
mypy --strict src/docfuse/
```

## Build Windows portable

```bash
pyinstaller --noconfirm --onedir --windowed --name CorpusOne src/docfuse/__main__.py
```

## Licence

Apache License 2.0. Voir `LICENSE` et `NOTICE` pour les attributions.