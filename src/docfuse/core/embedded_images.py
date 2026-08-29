"""Nommage, marqueurs et traitement (OCR parallèle) des images intégrées
(DOCX/PPTX/XLSX/ODF — D-091, D-093, D-098).

Fonctions pures partagées par les extracteurs : construction du nom de
fichier exporté (assez explicite pour qu'un LLM externe relie une image à
sa position sans lire le corpus), du marqueur inline placé dans le texte à
l'emplacement de l'image, et — depuis D-098 — `ImageBatch`, le point unique
qui applique l'OCR à toutes les images d'un fichier **en parallèle** tout
en rendant les marqueurs dans l'ordre du document.
"""

from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

from docfuse.constants import OCR_LANG, OCR_MAX_CONCURRENCY
from docfuse.core.ocr.base import OcrEngine
from docfuse.core.ocr.registry import ocr_with_slot
from docfuse.models.extraction_result import EmbeddedImage, ExtractedFile

_FORBIDDEN_CHARS_RE = re.compile(r'[\\/:*?"<>|]')


def dedupe_image_filenames(files: list[ExtractedFile]) -> int:
    """Renomme les images exportées dont le nom est déjà pris par un fichier
    précédent, et met à jour le marqueur `[[IMAGE: …]]` correspondant dans le
    texte (D-099).

    Le nom dérive du chemin relatif, unique dans un dossier — mais une
    sélection explicite de fichiers homonymes venant de dossiers différents
    (`A/rapport.docx` + `B/rapport.docx`) produit les mêmes noms, et
    l'écriture silencieuse écrasait la première image par la seconde.

    Returns:
        Nombre d'images renommées.
    """
    seen: set[str] = set()
    renamed = 0
    for file in files:
        if not file.embedded_images:
            continue
        images: list[EmbeddedImage] = []
        for image in file.embedded_images:
            name = image.filename
            if name in seen:
                new_name = _next_free_name(name, seen)
                file.text = file.text.replace(f"[[IMAGE: {name}]]", f"[[IMAGE: {new_name}]]")
                file.text = file.text.replace(f"[[IMAGE: {name} —", f"[[IMAGE: {new_name} —")
                image = EmbeddedImage(filename=new_name, data=image.data)
                renamed += 1
            seen.add(image.filename)
            images.append(image)
        file.embedded_images = images
    return renamed


def _next_free_name(name: str, taken: set[str]) -> str:
    stem, dot, ext = name.rpartition(".")
    counter = 2
    while True:
        candidate = f"{stem}_{counter}.{ext}" if dot else f"{name}_{counter}"
        if candidate not in taken:
            return candidate
        counter += 1


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


@dataclass(frozen=True)
class _Candidate:
    tag: str
    data: bytes


class ImageBatch:
    """Toutes les images intégrées d'un fichier, OCRisées en parallèle (D-098).

    Usage par un extracteur :
    1. Pendant le parcours du document (dans l'ordre), `add(tag, data)`
       renvoie un **jeton de position** à insérer dans la liste des parties
       de texte, exactement là où l'image apparaît.
    2. À la fin, `resolve(parts)` lance l'OCR de toutes les images d'un coup
       (`ThreadPoolExecutor`, borné par le sémaphore global `OCR_SLOTS`) et
       remplace chaque jeton par son marqueur — ou le retire si ni OCR ni
       export n'ont rien produit — puis expose `images` à exporter.

    Pourquoi : l'OCR était séquentiel à l'intérieur d'un fichier (un appel
    Tesseract ≈ 0,5 s, mono-thread par processus) — un PPTX de 44 images
    prenait 21 s seul et bornait à lui seul le temps total d'un dossier de
    120 fichiers (26 s). Le parallélisme par fichier de l'orchestrateur ne
    peut rien contre un tel chemin critique unique.
    """

    def __init__(self, engine: OcrEngine | None, want_export: bool, lang: str = OCR_LANG) -> None:
        self._engine = engine
        self._want_export = want_export
        self._lang = lang
        self._candidates: list[_Candidate | None] = []
        self._markers: dict[str, str] | None = None
        self.images: list[EmbeddedImage] = []

    @property
    def active(self) -> bool:
        """Vrai s'il y a quelque chose à faire des images (OCR ou export)."""
        return self._want_export or self._engine is not None

    @property
    def engine(self) -> OcrEngine | None:
        return self._engine

    @property
    def want_export(self) -> bool:
        return self._want_export

    def add(self, tag: str, data: bytes) -> str:
        """Enregistre une image et renvoie son jeton de position."""
        self._candidates.append(_Candidate(tag, data))
        return _token(len(self._candidates) - 1)

    def take(self, token: str) -> _Candidate | None:
        """Retire une image du lot (pour la traiter à part) ; `None` si
        `token` n'est pas un jeton de ce lot. Le jeton retiré ne sera plus
        résolu par `apply` (il est remplacé par "" — il ne doit plus
        apparaître dans les parties finales)."""
        if not _is_token(token) or self._markers is not None:
            return None
        index = int(token[len(_TOKEN_PREFIX) : -1])
        candidate = self._candidates[index]
        if candidate is None:
            return None
        self._candidates[index] = None
        return candidate

    def run(self) -> None:
        """OCR de toutes les images enregistrées (une seule fois) et
        construction des marqueurs / images à exporter."""
        if self._markers is not None:
            return
        self._markers = {}
        pending = [(i, c) for i, c in enumerate(self._candidates) if c is not None]
        if not pending:
            return
        ocr_texts = self._run_ocr([c for _, c in pending])
        for (index, candidate), ocr_text in zip(pending, ocr_texts, strict=True):
            marker = build_image_marker(
                candidate.tag if self._want_export else None, ocr_text, self._lang
            )
            self._markers[_token(index)] = marker
            if self._want_export and marker:
                self.images.append(EmbeddedImage(filename=candidate.tag, data=candidate.data))

    def apply(self, parts: list[str]) -> list[str]:
        """Substitue les jetons (éléments entiers de `parts`) par leur
        marqueur ; un jeton dont le marqueur est vide est retiré — rien à
        signaler pour cette image, exactement comme avant D-098 (sortie
        identique). Appelable plusieurs fois après `run()` (par diapo, par
        feuille…)."""
        markers = self._markers if self._markers is not None else {}
        resolved: list[str] = []
        for part in parts:
            if _is_token(part):
                marker = markers.get(part, "")
                if marker:
                    resolved.append(marker)
            else:
                resolved.append(part)
        return resolved

    def resolve(self, parts: list[str]) -> list[str]:
        """`run()` puis `apply(parts)` — cas simple d'une liste unique."""
        self.run()
        return self.apply(parts)

    def _run_ocr(self, candidates: list[_Candidate]) -> list[str]:
        if self._engine is None:
            return [""] * len(candidates)
        engine = self._engine
        lang = self._lang
        workers = min(OCR_MAX_CONCURRENCY, len(candidates))
        if workers <= 1:
            return [ocr_with_slot(engine, c.data, lang) for c in candidates]
        with ThreadPoolExecutor(max_workers=workers) as executor:
            # `map` rend les résultats dans l'ordre de soumission.
            return list(executor.map(lambda c: ocr_with_slot(engine, c.data, lang), candidates))


_TOKEN_PREFIX = "\x00IMG:"


def _token(index: int) -> str:
    return f"{_TOKEN_PREFIX}{index}\x00"


def _is_token(part: str) -> bool:
    return part.startswith(_TOKEN_PREFIX) and part.endswith("\x00")
