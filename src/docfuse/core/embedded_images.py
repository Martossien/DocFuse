"""Nommage et marqueurs pour les images intégrées (DOCX/PPTX, D-091).

Fonctions pures partagées par `extractors/docx.py` et `extractors/pptx.py` :
construction du nom de fichier exporté (assez explicite pour qu'un LLM
externe relie une image à sa position sans lire le corpus) et du marqueur
inline placé dans le texte à l'emplacement de l'image.
"""

from __future__ import annotations

import re

_FORBIDDEN_CHARS_RE = re.compile(r'[\\/:*?"<>|]')


def sanitize_filename_component(value: str) -> str:
    """Remplace les caractères interdits dans un nom de fichier Windows par `_`.

    Args:
        value: Fragment de nom (chemin relatif, extension, ...).

    Returns:
        Chaîne sûre à utiliser dans un nom de fichier sur tout OS supporté.
    """
    return _FORBIDDEN_CHARS_RE.sub("_", value)


def build_image_tag(relative_path: str, location: str | None, index: int, ext: str) -> str:
    """Construit le nom de fichier exporté d'une image intégrée.

    Format : ``{doc_stem}__{location}__img{n}.{ext}`` (ou sans le segment
    ``location`` si `None` — cas DOCX, qui n'a pas de notion de page dans son
    XML). `doc_stem` dérive du chemin relatif complet (séparateurs remplacés)
    plutôt que du seul nom de fichier : garantit l'unicité même si deux
    dossiers différents contiennent un fichier de même nom, et permet de
    relier visuellement l'image à sa source sans avoir besoin du corpus.

    Args:
        relative_path: Chemin relatif du document source (ex: "Docs/a.pptx").
        location: Repère de position (ex: "slide12"), ou None si non applicable.
        index: Numéro d'image (1-indexé, dans l'ordre d'apparition).
        ext: Extension de l'image sans le point (ex: "png").

    Returns:
        Nom de fichier prêt à écrire dans le dossier d'export.
    """
    stem = relative_path.rsplit(".", 1)[0] if "." in relative_path else relative_path
    doc_stem = sanitize_filename_component(stem)
    clean_ext = sanitize_filename_component(ext).lstrip(".") or "png"
    location_segment = f"{sanitize_filename_component(location)}__" if location else ""
    return f"{doc_stem}__{location_segment}img{index}.{clean_ext}"


def build_image_marker(tag: str | None, ocr_text: str, lang: str) -> str:
    """Construit le marqueur inline placé au point d'apparition d'une image.

    Même convention que les marqueurs déjà présents dans le corpus
    (``[[PAGE N: ...]]``, ``[[DIAPO N: ...]]``) : littéral français fixe,
    contenu du corpus plutôt que chaîne d'interface — volontairement hors
    i18n, précédent déjà établi.

    Args:
        tag: Nom de fichier exporté si l'export est actif, sinon None.
        ocr_text: Texte reconnu par OCR sur l'image, chaîne vide si aucun.
        lang: Code(s) langue Tesseract utilisés (affiché seulement si
            `ocr_text` est non vide).

    Returns:
        Marqueur prêt à insérer dans le texte, ou chaîne vide si ni export
        ni OCR n'ont produit quoi que ce soit à signaler (comportement
        actuel inchangé dans ce cas).
    """
    text = ocr_text.strip()
    if tag and text:
        return f"[[IMAGE: {tag} — texte OCR (tesseract, {lang})]]\n{text}"
    if tag:
        return f"[[IMAGE: {tag}]]"
    if text:
        return f"[[IMAGE — texte OCR (tesseract, {lang})]]\n{text}"
    return ""
