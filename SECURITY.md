# Security Policy

## Modèle de menace

DocFuse est un outil **100 % local et hors-ligne** : il n'ouvre pas de connexion
réseau, n'enregistre rien dans `%APPDATA%` sans consentement, n'écrit rien dans
`HKLM` ni dans `Program Files`, et ne nécessite aucun droit administrateur.

Les fichiers manipulés restent sur le disque de l'utilisateur ; aucun service
cloud n'est contacté. Les sorties (corpus Markdown/PDF, rapports MD/JSON) sont
écrites dans un sous-dossier `DocFuse_output/` du dossier d'entrée (le nom
dérive du nom d'application, personnalisable par `DOCFUSE_APP_NAME`).

Cela dit, DocFuse lit et parse des fichiers dans des formats variés (PDF,
DOCX, PPTX, XLSX, RTF, HTML, ODF, EML, MHTML…). Comme tout parser, les
extracteurs peuvent être exposés à des fichiers **malformés** voire
**malveillants** (PDF piégé, ZIP office avec chemin traversal, etc.).

## Versions supportées

| Version | Supportée        |
|---------|------------------|
| 0.2.x   | ✅ Oui           |
| 0.1.x   | ❌ Non           |
| < 0.1   | ❌ Non           |

Seule la dernière série (0.2.x) reçoit des correctifs. Le projet est en
préversion alpha (3 - Alpha selon le classifier PyPI) : l'API peut encore
évoluer, ne l'utilisez pas en production sans audit.

## Signaler une vulnérabilité

**Ne pas** ouvrir d'issue publique pour une faille de sécurité.

Envoyez un rapport privé par :

- **Email** : ouvrez une discussion privée via l'onglet *Security* →
  *Report a vulnerability* sur GitHub :
  <https://github.com/Martossien/DocFuse/security/advisories/new>
- Ou par message direct au mainteneur : voir l'onglet *Insights* →
  *Contributors* du dépôt.

Merci d'inclure :

1. Description de la vulnérabilité et de son impact (RCE, fuite, DoS, etc.).
2. Étapes de reproduction minimales (un fichier ou un script).
3. Version concernée (`docfuse --version`) et système d'exploitation.
4. Capture / log pertinent.

## Engagement

- **Accusé de réception** sous 7 jours ouvrés.
- **Évaluation** et plan de correctif sous 30 jours pour les failles critiques.
- **Coordination** sur la divulgation : nous proposons un délai raisonnable
  (par défaut 90 jours) avant publication d'un CVE, ajustable selon la
  complexité du correctif.

## Bonnes pratiques pour les contributeurs

- Valider toute entrée utilisateur avant de la passer à un parser tiers
  (taille, extensions, magic bytes).
- Utiliser `safe_extract` (`src/docfuse/extractors/base.py`) qui capture les
  exceptions et renvoie un statut `ERROR` plutôt que de crasher.
- Ne jamais désactiver `mypy --strict` ni les tests
  `TestPortability::test_no_network_imports` et
  `TestLicenseCompliance::test_no_gpl_agpl_in_dependencies` — ils sont notre
  première ligne de défense contre les régressions de sécurité.

Merci de garder DocFuse sûr pour ses utilisateurs.
