"""Détection de doublons de contenu entre fichiers.

Deux fichiers différents peuvent contenir un texte extrait strictement
identique (copie dans deux dossiers, export dupliqué, sauvegarde) — un cas
fréquent quand l'utilisateur sélectionne un dossier entier plutôt que des
fichiers un par un. Sans détection, ce contenu est compté et inclus deux
fois dans le corpus, gaspillant des tokens sans rien apporter.

CdC §8 — sans perte silencieuse : le fichier doublon reste visible dans la
liste et le rapport, mais son texte est remplacé par une note pointant vers
l'original plutôt que d'être répété.
"""

from __future__ import annotations

import hashlib
import re

from docfuse.constants import DUPLICATE_MIN_CHARS
from docfuse.i18n import t
from docfuse.models.extraction_result import ExtractedFile

# Marqueur DocFuse inséré dans le corpus par les extracteurs : la convention
# stable est la paire de doubles crochets, pas le libellé qu'elle encadre
# (`[[PAGE N: aucun texte extractible]]`, `[[DIAPO N: ...]]`,
# `[[PAGE N — texte OCR (tesseract, fra)]]`, `[[IMAGE: ...]]`) — voir
# `extractors/pdf.py`, `extractors/pptx.py`, `core/embedded_images.py`, qui
# documentent explicitement cette convention commune. On matche donc les
# délimiteurs, jamais les mots français : reformuler un marqueur ne rouvre
# pas la faille. `DOTALL` car un marqueur peut être écrit sur plusieurs
# lignes ; non gourmand pour ne pas avaler le texte entre deux marqueurs.
_MARQUEUR_DOCFUSE = re.compile(r"\[\[.*?\]\]", re.DOTALL)

# Titre de section généré par un extracteur pour numéroter une unité du
# document : un mot + un nombre, rien d'autre (`## Diapo 1`, `## Slide 3`).
# Volontairement étroit — un vrai titre Markdown de document porte des mots,
# donc du contenu, et n'est pas retiré.
_TITRE_NUMEROTE = re.compile(r"^#{1,6}[ \t]*\S+[ \t]+\d+[ \t]*$")

# Filet horizontal Markdown séparant deux unités (`---` entre deux diapos).
_SEPARATEUR = re.compile(r"^([-*_])\1{2,}$")


def _porte_assez_de_contenu(texte: str, plafond: int) -> bool:
    """Vrai si `texte` porte au moins `plafond` caractères de contenu propre,
    c'est-à-dire hors échafaudage produit par DocFuse lui-même.

    Pourquoi ce critère (D-107). La détection de doublons hachait le texte
    extrait tel quel. Quand l'OCR est absent (`DocFuse.exe` standard
    n'embarque pas Tesseract) ou en échec, deux PDF scannés de même nombre
    de pages produisent un texte **strictement identique** fait uniquement
    de marqueurs d'absence de contenu :
    `[[PAGE 1: aucun texte extractible]]\\n\\n[[PAGE 2: aucun texte
    extractible]]` — 72 caractères, au-dessus de `DUPLICATE_MIN_CHARS`.
    Résultat constaté en production : un dossier médical et une facture
    déclarés « contenu identique » à un contrat de travail, avec
    `doublon_de:` en en-tête, sur un rapport qui sert à décider de
    suppressions de fichiers.

    Un texte qui ne dit rien du document ne peut pas fonder son identité.
    Ce qui est retiré est exactement ce que DocFuse a écrit lui-même et qui
    ne dépend que de la *structure* (nombre de pages, de diapos), jamais du
    contenu :

    1. tout marqueur `[[...]]`, reconnu par ses délimiteurs et non par son
       libellé — les libellés sont des littéraux français hors i18n, sujets
       à reformulation ;
    2. les titres de section purement numériques (`## Diapo 1`) ;
    3. les filets horizontaux (`---`) et les lignes vides.

    Le reste — y compris le texte reconnu par OCR, qui suit son marqueur —
    est du contenu et compte normalement : deux scans réellement identiques
    dont l'OCR a réussi restent détectés comme doublons.

    Ce que ce critère laisse passer :

    - deux documents dont le *vrai* contenu est identique mais trop court
      (< `DUPLICATE_MIN_CHARS` une fois l'échafaudage retiré) ne sont plus
      dédoublonnés : quelques dizaines de tokens répétés, jamais une fausse
      identité — l'erreur est du côté sûr ;
    - un document dont le contenu réel est lui-même écrit entre doubles
      crochets (rare : un fichier `.md` de notation formelle) verrait ce
      contenu ignoré pour la seule décision d'éligibilité ;
    - deux documents *réellement* identiques et non vides restent
      dédoublonnés, y compris s'ils contiennent des marqueurs : le hachage
      porte toujours sur le texte complet, le texte significatif ne sert
      qu'à décider si le fichier a le droit d'entrer dans la comparaison.

    Coût : l'appelant n'a besoin que d'une comparaison à un seuil, donc on
    compte en s'arrêtant dès qu'il est atteint et sans jamais matérialiser
    de copie du texte nettoyé — un corpus porte des fichiers de plusieurs
    mégaoctets et cette fonction est appelée une fois par fichier. Sur un
    vrai document la réponse tombe à la première ligne.

    Args:
        texte: Texte extrait, déjà `strip()`.
        plafond: Nombre de caractères de contenu à atteindre.

    Returns:
        True si le fichier peut entrer dans la comparaison de doublons.
    """
    # `in` est un scan C sans allocation : la substitution (qui, elle, copie
    # le texte) n'est payée que par les fichiers qui portent un marqueur.
    nettoye = _MARQUEUR_DOCFUSE.sub("", texte) if "[[" in texte else texte

    total = 0
    debut = 0
    longueur = len(nettoye)
    while debut <= longueur and total < plafond:
        fin = nettoye.find("\n", debut)
        if fin == -1:
            fin = longueur
        ligne = nettoye[debut:fin].strip()
        debut = fin + 1
        if ligne and not _TITRE_NUMEROTE.match(ligne) and not _SEPARATEUR.match(ligne):
            total += len(ligne)
    return total >= plafond


def detect_duplicates(files: list[ExtractedFile]) -> None:
    """Marque les fichiers dont le texte extrait est identique à un précédent.

    Modifie les fichiers en place : le premier fichier d'un groupe de
    doublons (dans l'ordre de `files`, déjà trié par l'inventaire) reste
    inchangé et sert d'original ; les suivants voient leur `text` remplacé
    par une courte note et `extra_metadata["duplicate_of"]` renseigné.

    D-107 : un fichier dont le texte ne porte pas assez de contenu propre
    (voir `_porte_assez_de_contenu`) est écarté de la comparaison. Écarté ne
    veut pas dire perdu : il garde son texte intégral, reste dans la liste
    et le rapport avec son statut (typiquement `LOW_TEXT`), et ne reçoit
    aucun `duplicate_of` — il n'est donc jamais présenté comme le doublon
    de quoi que ce soit, et `_promote_duplicate_of` ne le voit pas.

    Args:
        files: Fichiers extraits (modifiés en place).
    """
    seen_hashes: dict[str, ExtractedFile] = {}

    for file in files:
        if not file.status.is_extracted():
            continue

        normalized = file.text.strip()
        # Le seuil porte sur le contenu propre du document, pas sur
        # l'échafaudage que DocFuse a lui-même écrit dans le texte extrait.
        if not _porte_assez_de_contenu(normalized, DUPLICATE_MIN_CHARS):
            continue

        digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
        original = seen_hashes.get(digest)
        if original is None:
            seen_hashes[digest] = file
            continue

        file.extra_metadata["duplicate_of"] = original.relative_path
        file.text = t("duplicate.placeholder_text", original=original.relative_path)
