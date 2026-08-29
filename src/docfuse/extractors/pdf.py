"""Extracteur PDF : .pdf.

CdC §8.3 — Texte de chaque page, dans l'ordre des pages.
Page vide → marqueur [[PAGE N: aucun texte extractible]].
CdC §9.4 — Détection images via XObject /Subtype /Image + LTImage/LTFigure.
CdC §14.3 — pdfminer.six (MIT) pour extraction + détection images ;
            pypdf (BSD) pour inventaire pages + détection encryption.

Inspiré de MarkItDown PdfConverter :
- extract_pages() pour traiter page-par-page (libération mémoire).
- extract_text() en fallback si le rendu est trop pauvre.

OCR (v1, PDF scannés) — voir `core/ocr/` : chaque page est classée
native/ocr/blank/mixed à partir du texte déjà extrait par pdfminer (pas de
seconde passe d'extraction). Seules les pages classées ocr/mixed sont
rastérisées (pypdfium2) puis passées à Tesseract, si disponible — sinon le
comportement est strictement identique à avant l'ajout de cette
fonctionnalité (voir `core/ocr/registry.py::resolve_ocr_engine`).
"""

from __future__ import annotations

import io
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from enum import Enum
from pathlib import Path
from typing import Any

from docfuse.constants import (
    MAX_WORKERS,
    OCR_DPI,
    OCR_LANG,
    OCR_MAX_PAGES_PER_FILE,
    OCR_MAX_PIXELS_PER_PAGE,
    PDF_BOILERPLATE_MAX_LINE_LEN,
    PDF_BOILERPLATE_MIN_OCCURRENCES,
    PDF_BOILERPLATE_MIN_PAGES,
    PDF_BOILERPLATE_MIN_RATIO,
    PDF_OCR_GARBAGE_MARKERS,
    PDF_OCR_MIN_CHARS_PER_PAGE,
)
from docfuse.core.ocr.base import OcrEngine
from docfuse.core.ocr.registry import resolve_ocr_engine
from docfuse.core.registry import register
from docfuse.extractors.base import Extractor, error_result
from docfuse.i18n import t
from docfuse.models.extraction_result import ExtractedFile
from docfuse.models.file_status import FileStatus

logger = logging.getLogger(__name__)


class PageKind(str, Enum):
    """Classification d'une page PDF pour décider si l'OCR est utile.

    Simplification assumée par rapport à une détection par couverture
    d'image (ratio surface image / surface page) : DocFuse ne dispose que
    d'un compte d'images par page (pdfminer), pas de leurs dimensions —
    même logique booléenne que `core/image_detector.py` (image_count > 0).
    """

    NATIVE = "native"
    OCR = "ocr"
    BLANK = "blank"
    MIXED = "mixed"


@register(".pdf")
class PdfExtractor(Extractor):
    """Extracteur PDF via pdfminer.six + pypdf, avec OCR optionnel des pages scannées."""

    file_type = "pdf"

    @classmethod
    def accepts(cls, path: Path) -> bool:
        return path.suffix.lower() == ".pdf"

    @classmethod
    def extract(cls, path: Path, relative_path: str) -> ExtractedFile:
        try:
            # 1. Vérifier l'encryption avec pypdf
            encrypted = _check_encrypted(path)
            if encrypted:
                return ExtractedFile(
                    path=path,
                    relative_path=relative_path,
                    extension="pdf",
                    file_type=cls.file_type,
                    size_bytes=path.stat().st_size,
                    status=FileStatus.ERROR,
                    error_message=t("error.encrypted_pdf"),
                )

            # 2. Extraction texte page-par-page avec pdfminer
            pages_text, chars_per_page, image_count, page_count, image_count_per_page = (
                _extract_pages_pdfminer(path)
            )

            # 2b. Déduplication des en-têtes/pieds de page répétés sur chaque page.
            # Recalcule chars_per_page à partir du texte dédupliqué : la densité de
            # texte utile pour la détection de pauvreté (image_detector.py) doit
            # refléter le contenu réel, pas le bruit répété.
            pages_text, dedup_note = _dedupe_page_boilerplate(pages_text)
            chars_per_page = [len(p.strip()) for p in pages_text]

            extra_metadata: dict[str, str] = {}
            if dedup_note:
                extra_metadata["pdf_dedup"] = dedup_note

            # 2c. OCR des pages scannées (moteur optionnel, jamais bloquant).
            pages_text, ocr_note = _apply_ocr(
                path, pages_text, chars_per_page, image_count_per_page
            )
            if ocr_note:
                extra_metadata["ocr"] = ocr_note
            chars_per_page = [len(p.strip()) for p in pages_text]

            # 3. Construction du texte avec marqueurs de pages vides
            parts: list[str] = []
            for i, (text, char_count) in enumerate(
                zip(pages_text, chars_per_page, strict=False), 1
            ):
                if char_count == 0:
                    parts.append(f"[[PAGE {i}: aucun texte extractible]]")
                else:
                    parts.append(text)

            full_text = "\n\n".join(parts)

            return ExtractedFile(
                path=path,
                relative_path=relative_path,
                extension="pdf",
                file_type=cls.file_type,
                size_bytes=path.stat().st_size,
                text=full_text,
                status=FileStatus.READY,
                image_count=image_count,
                page_count=page_count,
                chars_per_page=chars_per_page,
                extra_metadata=extra_metadata,
            )
        except Exception as exc:
            logger.exception("Erreur extraction PDF %s", path)
            return error_result(path, relative_path, cls.file_type, exc)


def _check_encrypted(path: Path) -> bool:
    """Vérifie si le PDF est chiffré / protégé par mot de passe via pypdf."""
    try:
        from pypdf import PdfReader

        reader = PdfReader(str(path))
        return reader.is_encrypted
    except Exception:
        # Si pypdf échoue, on continue avec pdfminer
        return False


def _extract_pages_pdfminer(
    path: Path,
) -> tuple[list[str], list[int], int, int, list[int]]:
    """Extrait le texte et les images page par page via pdfminer.six.

    ``LAParams(all_texts=True)`` : sans ce réglage, pdfminer ne regroupe pas
    en lignes/paragraphes le texte situé dans un Form XObject (``LTFigure``
    imbriqué — filigranes, tampons, contenu fusionné, courant avec des
    générateurs comme TCPDF). Ce texte reste alors de simples ``LTChar``
    épars, invisibles pour `isinstance(element, LTTextContainer)` — une page
    entière de texte réel peut ainsi être vue comme vide. Constaté
    concrètement en session (2026-08-29, D-068) : jusqu'à ~2500 caractères
    de texte natif silencieusement ignorés sur certaines pages.

    Returns:
        Tuple (textes par page, caractères par page, nombre d'images total,
        nombre de pages, nombre d'images par page).
    """
    from pdfminer.high_level import extract_pages
    from pdfminer.layout import LAParams, LTFigure, LTImage, LTTextContainer

    pages_text: list[str] = []
    chars_per_page: list[int] = []
    image_count_per_page: list[int] = []
    total_images = 0
    page_count = 0

    for page in extract_pages(str(path), laparams=LAParams(all_texts=True)):
        page_count += 1
        page_text_parts: list[str] = []
        page_images = 0

        for element in page:
            # Texte
            if isinstance(element, LTTextContainer):
                text = element.get_text()
                if text.strip():
                    page_text_parts.append(text.strip())

            # Images directes
            if isinstance(element, LTImage):
                page_images += 1

            # Figures (contiennent souvent des images ET/OU du texte imbriqué
            # via un Form XObject — voir le docstring de la fonction)
            if isinstance(element, LTFigure):
                page_images += _count_images_in_figure(element)
                page_text_parts.extend(_extract_text_in_figure(element))

        total_images += page_images
        image_count_per_page.append(page_images)
        page_text = "\n".join(page_text_parts)
        pages_text.append(page_text)
        chars_per_page.append(len(page_text.strip()))

        # Libération mémoire (inspiré de MarkItDown PdfConverter:566)
        # pdfminer gère la mémoire page-par-page avec extract_pages()

    return pages_text, chars_per_page, total_images, page_count, image_count_per_page


def _dedupe_page_boilerplate(pages_text: list[str]) -> tuple[list[str], str | None]:
    """Retire les en-têtes/pieds de page répétés à l'identique sur plusieurs pages.

    Un en-tête/pied de page PDF est extrait par pdfminer comme la première ou
    la dernière ligne du texte de chaque page (les blocs de texte y sont
    physiquement positionnés). On ne regarde donc que ces deux positions par
    page — jamais le corps du texte — pour ne pas risquer de retirer un
    paragraphe légitimement répété.

    Une ligne candidate n'est retirée que si elle apparaît identique sur au
    moins ``PDF_BOILERPLATE_MIN_OCCURRENCES`` pages ET sur au moins
    ``PDF_BOILERPLATE_MIN_RATIO`` des pages du document — un simple "Page 1"
    répété deux fois dans un document de 40 pages ne déclenche rien.

    Toutes les occurrences sauf la première sont supprimées ; la première
    reste visible une fois dans le corpus (CdC §8 — sans perte silencieuse :
    le contenu répété disparaît du texte, mais son existence est signalée
    dans l'en-tête SOURCE via la note retournée).

    Returns:
        Tuple (pages de texte mises à jour, note descriptive ou None si rien
        n'a été dédupliqué).
    """
    page_count = len(pages_text)
    if page_count < PDF_BOILERPLATE_MIN_PAGES:
        return pages_text, None

    pages_lines = [p.split("\n") for p in pages_text]

    # Compter les occurrences des lignes candidates (première/dernière de chaque page).
    occurrences: dict[str, int] = {}
    for lines in pages_lines:
        candidates = set()
        if lines and lines[0].strip():
            candidates.add(lines[0].strip())
        if lines and lines[-1].strip():
            candidates.add(lines[-1].strip())
        for candidate in candidates:
            if len(candidate) <= PDF_BOILERPLATE_MAX_LINE_LEN:
                occurrences[candidate] = occurrences.get(candidate, 0) + 1

    min_occurrences = max(
        PDF_BOILERPLATE_MIN_OCCURRENCES, round(PDF_BOILERPLATE_MIN_RATIO * page_count)
    )
    boilerplate = {line for line, count in occurrences.items() if count >= min_occurrences}
    if not boilerplate:
        return pages_text, None

    seen_once: set[str] = set()
    chars_saved = 0
    new_pages: list[str] = []
    for lines in pages_lines:
        kept_lines = []
        for j, line in enumerate(lines):
            stripped = line.strip()
            is_edge = j == 0 or j == len(lines) - 1
            if is_edge and stripped in boilerplate:
                if stripped in seen_once:
                    chars_saved += len(line)
                    continue
                seen_once.add(stripped)
            kept_lines.append(line)
        new_pages.append("\n".join(kept_lines))

    total_occurrences = sum(occurrences[line] for line in boilerplate)
    note = t(
        "pdf.dedup_note",
        count=len(boilerplate),
        occurrences=total_occurrences,
        chars=chars_saved,
    )
    return new_pages, note


def _count_images_in_figure(figure: Any) -> int:
    """M-02: Compte les images dans un LTFigure (récursion profonde sur les sous-figures)."""
    from pdfminer.layout import LTFigure, LTImage

    def _count_recursive(element: Any) -> int:
        count = 0
        for child in element:
            if isinstance(child, LTImage):
                count += 1
            if isinstance(child, LTFigure):
                count += _count_recursive(child)
        return count

    return _count_recursive(figure)


def _extract_text_in_figure(figure: Any) -> list[str]:
    """Texte imbriqué dans un LTFigure (récursion profonde, symétrique de
    `_count_images_in_figure`). Voir le docstring de `_extract_pages_pdfminer`
    (D-068) : nécessite `LAParams(all_texts=True)` pour que ce texte soit
    déjà regroupé en `LTTextContainer` plutôt qu'en `LTChar` épars."""
    from pdfminer.layout import LTFigure, LTTextContainer

    parts: list[str] = []
    for child in figure:
        if isinstance(child, LTTextContainer):
            text = child.get_text()
            if text.strip():
                parts.append(text.strip())
        elif isinstance(child, LTFigure):
            parts.extend(_extract_text_in_figure(child))
    return parts


def _has_garbage_text(text: str) -> bool:
    """Détecte un texte natif « poubelle » (polices cassées, glyphes non mappés)."""
    return any(marker in text for marker in PDF_OCR_GARBAGE_MARKERS)


def classify_page(text: str, char_count: int, has_image: bool) -> PageKind:
    """Classe une page pour décider si l'OCR lui serait utile.

    Args:
        text: Texte natif de la page (avant dédup, peu importe ici).
        char_count: Caractères utiles déjà comptés (`chars_per_page[i]`).
        has_image: Au moins une image détectée sur cette page (pdfminer).

    Returns:
        `NATIVE` (texte natif suffisant, rien à faire), `BLANK` (page
        réellement vide — pas de texte fantôme), `OCR` (pas de texte natif
        utile, qu'il n'y en ait jamais eu ou qu'il soit illisible/poubelle),
        ou `MIXED` (texte natif utile + une image sur la page).

    Une page « poubelle » (glyphes non mappés) a du contenu visible même si
    rien n'est extractible : ce n'est jamais `BLANK`, seulement une page
    sans image (`char_count == 0` et pas de glyphes poubelle) l'est.
    """
    useful_chars = 0 if _has_garbage_text(text) else char_count
    if useful_chars == 0:
        if char_count == 0 and not has_image:
            return PageKind.BLANK
        return PageKind.OCR
    if useful_chars < PDF_OCR_MIN_CHARS_PER_PAGE:
        return PageKind.OCR
    return PageKind.MIXED if has_image else PageKind.NATIVE


def _apply_ocr(
    path: Path,
    pages_text: list[str],
    chars_per_page: list[int],
    image_count_per_page: list[int],
) -> tuple[list[str], str | None]:
    """Classe chaque page et lance l'OCR sur celles qui en ont besoin.

    Ne modifie jamais une page classée `native` ou `blank`. Si aucun moteur
    OCR n'est disponible, le texte n'est pas modifié — seule une note de
    transparence est ajoutée si des pages semblaient scannées.

    Returns:
        Tuple (pages de texte éventuellement enrichies de texte OCR, note
        de transparence ou None si rien à signaler).
    """
    page_count = len(pages_text)
    if page_count == 0:
        return pages_text, None

    kinds = [
        classify_page(text, chars, images > 0)
        for text, chars, images in zip(
            pages_text, chars_per_page, image_count_per_page, strict=True
        )
    ]

    ocr_indices = [i for i, k in enumerate(kinds) if k in (PageKind.OCR, PageKind.MIXED)]
    if not ocr_indices:
        return pages_text, None

    engine = resolve_ocr_engine()
    if engine is None:
        return pages_text, t("ocr.unavailable_note", pages=len(ocr_indices))

    ocr_results = _ocr_pages(path, ocr_indices, OCR_LANG, engine)

    new_pages = list(pages_text)
    pages_ocr = pages_mixed = pages_failed = 0
    for idx in ocr_indices:
        text, ok = ocr_results.get(idx, ("", False))
        kind = kinds[idx]
        if not ok or not text.strip():
            pages_failed += 1
            continue
        marker = f"[[PAGE {idx + 1} — texte OCR (tesseract, {OCR_LANG})]]\n{text.strip()}"
        if kind is PageKind.MIXED and new_pages[idx].strip():
            new_pages[idx] = f"{new_pages[idx]}\n\n{marker}"
            pages_mixed += 1
        else:
            new_pages[idx] = marker
            pages_ocr += 1

    note = t(
        "ocr.applied_note",
        pages_ocr=pages_ocr,
        pages_mixed=pages_mixed,
        pages_failed=pages_failed,
        pages_total=page_count,
        lang=OCR_LANG,
    )
    return new_pages, note


def _ocr_pages(
    path: Path,
    page_indices: list[int],
    lang: str,
    engine: OcrEngine,
) -> dict[int, tuple[str, bool]]:
    """Rastérise puis reconnaît une sélection de pages (0-indexées).

    Rastérisation séquentielle (un seul `PdfDocument`, un pixmap jeté après
    chaque page — jamais tout le PDF en mémoire à la fois) ; la
    reconnaissance Tesseract, elle, est parallélisée (chaque appel est déjà
    un process OS isolé via `subprocess`, donc thread-safe côté appelant).

    Returns:
        Dict {index page: (texte reconnu, succès)}. Jamais d'exception :
        une page en échec (raster impossible, page trop grande, timeout)
        a `succès=False` et un texte vide.
    """
    results: dict[int, tuple[str, bool]] = {}
    capped = page_indices[:OCR_MAX_PAGES_PER_FILE]
    for skipped in page_indices[OCR_MAX_PAGES_PER_FILE:]:
        results[skipped] = ("", False)
    if not capped:
        return results

    import pypdfium2 as pdfium

    pngs: dict[int, bytes] = {}
    try:
        pdf = pdfium.PdfDocument(str(path))
        try:
            for idx in capped:
                try:
                    page = pdf[idx]
                    bitmap = page.render(scale=OCR_DPI / 72)
                    pil_image = bitmap.to_pil()
                    if pil_image.width * pil_image.height <= OCR_MAX_PIXELS_PER_PAGE:
                        buf = io.BytesIO()
                        pil_image.save(buf, format="PNG")
                        pngs[idx] = buf.getvalue()
                except Exception:
                    logger.warning(
                        "Rastérisation échouée page %d de %s", idx + 1, path, exc_info=True
                    )
        finally:
            pdf.close()
    except Exception:
        logger.warning("Ouverture PDFium impossible pour l'OCR : %s", path, exc_info=True)

    for idx in capped:
        if idx not in pngs:
            results[idx] = ("", False)

    if pngs:
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            futures = {
                executor.submit(engine.ocr_image, png, lang): idx for idx, png in pngs.items()
            }
            for future in as_completed(futures):
                idx = futures[future]
                try:
                    text = future.result()
                except Exception:
                    logger.warning("Échec OCR page %d de %s", idx + 1, path, exc_info=True)
                    text = ""
                results[idx] = (text, bool(text.strip()))

    return results
