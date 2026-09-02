"""OCR des pages scannées d'un PDF : classement des pages, rendu PDFium, Tesseract.

Sorti de `docfuse.extractors.pdf` (D-110) : l'extracteur ne garde que pdfminer et
la dédoublonnage des en-têtes ; tout ce qui touche PDFium et au moteur OCR est ici.
Le verrou `_PDFIUM_LOCK` (D-078) et la pipeline page par page (D-108) sont inchangés.
"""

from __future__ import annotations

import io
import logging
import math
import threading
from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

from docfuse.branding import OCR_VARIANT_NAME
from docfuse.constants import (
    OCR_DPI,
    OCR_LANG,
    OCR_MAX_CONCURRENCY,
    OCR_MAX_PAGES_PER_FILE,
    OCR_MAX_PIXELS_PER_PAGE,
    OCR_MIN_DPI,
)
from docfuse.core.ocr.base import OcrEngine
from docfuse.core.ocr.registry import ocr_with_slot, resolve_ocr_engine
from docfuse.extractors.pdf_pages import (
    PageKind,
    PdfPageCountMismatchError,
    _blank_if_garbage,
    classify_page,
)
from docfuse.i18n import t

logger = logging.getLogger(__name__)

# D-078 : PDFium (pypdfium2) n'est pas thread-safe entre PdfDocument
# distincts chargés depuis des threads différents — voir le docstring de
# `_ocr_pages`. Verrou global au niveau du processus (pas par fichier :
# c'est justement l'accès concurrent ENTRE fichiers différents qui corrompt
# le tas natif de PDFium).
_PDFIUM_LOCK = threading.Lock()


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
        cleaned_pages = [
            _blank_if_garbage(kinds[i], page) if i in ocr_indices else page
            for i, page in enumerate(pages_text)
        ]
        return cleaned_pages, t(
            "ocr.unavailable_note", pages=len(ocr_indices), variant=OCR_VARIANT_NAME
        )

    # D-107 : `page_count` est le nombre de pages que pdfminer a numérotées ;
    # `_ocr_pages` refuse de rendre quoi que ce soit si PDFium n'en compte pas
    # autant (`PdfPageCountMismatchError`, laissée remonter jusqu'à `extract`).
    ocr_results = _ocr_pages(path, ocr_indices, OCR_LANG, engine, page_count)

    new_pages = list(pages_text)
    pages_ocr = pages_mixed = pages_failed = 0
    for idx in ocr_indices:
        text, ok = ocr_results.get(idx, ("", False))
        kind = kinds[idx]
        if not ok or not text.strip():
            pages_failed += 1
            # D-096 : l'OCR a échoué (raster impossible, page hors plafond,
            # timeout, résultat vide) — la règle D-086 s'applique exactement
            # comme sans moteur : ne pas laisser le texte poubelle.
            new_pages[idx] = _blank_if_garbage(kind, new_pages[idx])
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


def _ocr_render_scale(width_pt: float, height_pt: float) -> float | None:
    """Facteur d'échelle de rastérisation d'une page, ou `None` si elle doit
    être ignorée (D-105).

    Fonction pure, testable sans moteur OCR ni PDF : c'est elle qui remplace
    l'ancien `continue` qui perdait purement et simplement toute page dont la
    surface dépassait `OCR_MAX_PIXELS_PER_PAGE` à `OCR_DPI` — souvent
    justement les documents qui comptent (plan A0, scan haute résolution,
    facture numérisée à 600 dpi).

    Portée réelle du sauvetage (D-106 — la docstring précédente et celle de
    `constants.OCR_MIN_DPI` étaient inexactes). Avec `OCR_DPI = 200` et
    `OCR_MIN_DPI = 100`, la réduction autorisée est d'un facteur 2 en
    résolution, donc **4 en surface** : une page est rendue tant que son aire
    ne dépasse pas `OCR_MAX_PIXELS_PER_PAGE / (OCR_MIN_DPI/72)²`, soit
    8 294 400 pt². Chiffres mesurés (voir
    `tests/test_extractors/test_pdf.py::TestOcrRenderScaleBounds`) :

    * A4 (595 × 842 pt) → 200 dpi, plein tarif ;
    * ARCH E1 (2160 × 3024 pt) → 112,7 dpi ;
    * ANSI E (2448 × 3168 pt) → 103,4 dpi ;
    * **A0 (2384 × 3370 pt) → 101,6 dpi** — et non « 120 dpi » comme
      l'affirmait `constants.py` ;
    * ARCH E (2592 × 3456 pt) → 96,2 dpi, **sous le plancher : ignorée** ;
    * B0 (2835 × 4008 pt) → ignorée.

    Les très grands formats restent donc hors de portée. Le découpage de la
    page en bandes (`crop=` de `pypdfium2`) permettrait de garder 200 dpi,
    mais **n'a pas été retenu** (D-106) : une bande horizontale coupe les
    lignes de texte en deux, et Tesseract rend alors du bruit des deux côtés
    de la coupure — une corruption silencieuse du contenu, strictement pire
    que la résolution réduite déjà en place. Le rattraper demanderait un
    recouvrement entre bandes puis une déduplication heuristique des lignes,
    qui perd ou duplique du texte selon le réglage. Le sauvetage reste donc
    une réduction d'échelle honnête, et la page hors de portée est
    journalisée puis traitée par la règle D-086 (`_blank_if_garbage`), jamais
    silencieusement remplie de texte poubelle.

    Args:
        width_pt: Largeur de la page en points PDF (1/72 pouce).
        height_pt: Hauteur de la page en points PDF.

    Returns:
        L'échelle à passer à `page.render(scale=...)` : `OCR_DPI / 72` si la
        page tient déjà sous le plafond, sinon l'échelle réduite qui l'y fait
        tenir exactement. `None` si cette échelle réduite tombe sous
        `OCR_MIN_DPI` (page inexploitable même OCRisée) ou si les dimensions
        sont dégénérées.
    """
    # D-106 : garde explicite sur chaque dimension, et non sur leur produit.
    # `(-595, -842)` donnait une aire **positive** et passait à l'échelle
    # nominale (PDFium recevant des dimensions négatives), et `NaN` traversait
    # toutes les comparaisons (`NaN <= 0` est faux, `NaN < x` aussi) pour
    # ressortir en `NaN` vers `page.render(scale=NaN)`. `not (x > 0)` rejette
    # à la fois zéro, le négatif et `NaN`.
    if not (width_pt > 0 and height_pt > 0):
        return None
    base_scale = OCR_DPI / 72
    area_pt = width_pt * height_pt
    if area_pt * base_scale * base_scale <= OCR_MAX_PIXELS_PER_PAGE:
        return base_scale
    reduced = math.sqrt(OCR_MAX_PIXELS_PER_PAGE / area_pt)
    if reduced < OCR_MIN_DPI / 72:
        return None
    return reduced


def _render_page_image(path: Path, idx: int, expected_page_count: int) -> Any:
    """Rastérise UNE page et rend une image PIL détachée de PDFium (D-108).

    Le verrou `_PDFIUM_LOCK` (D-078) est pris et relâché ici, autour du seul
    code qui appelle réellement PDFium. À la sortie, **plus aucun objet
    PDFium n'est vivant** : le document est rouvert et refermé à chaque page
    plutôt que maintenu ouvert entre deux prises du verrou. Garder un
    `PdfDocument` vivant pendant qu'un autre thread charge le sien est
    précisément la situation que D-078 décrit comme corruptrice ;
    l'invariant « aucun état PDFium ne survit au verrou » est donc conservé
    à l'identique. Coût mesuré de la réouverture : **5,2 ms par page** (PDF
    scanné de 200 pages A4, 200 dpi), contre ~77 ms de rendu, et à comparer
    aux ~400 ms d'encodage PNG que ce découpage sort du verrou.

    L'appelant encode ensuite le PNG hors du verrou. `to_pil()` peut partager
    le tampon natif du bitmap (documenté par pypdfium2 : « for RGBA, RGBX and
    L bitmaps, PIL is supposed to share memory with the original buffer ») :
    `.copy()` détache l'image, sans quoi sortir du verrou reviendrait à lire
    de la mémoire PDFium pendant qu'un autre thread s'en sert. Coût mesuré :
    **5,0 ms par page** — le format rendu par défaut ici est `BGR`, que PIL
    recopie déjà, mais l'appel ne dépend alors d'aucun réglage de rendu.

    Args:
        path: Chemin du PDF.
        idx: Index 0-indexé de la page, dans la numérotation de l'appelant.
        expected_page_count: Nombre de pages attendu — vérifié contre PDFium
            (D-107) avant tout `pdf[idx]`.

    Returns:
        Une image `PIL.Image.Image` indépendante, ou `None` si la page n'a
        pas pu être rendue (PDF illisible, page hors plafond mémoire,
        rastérisation en échec). Ces cas sont journalisés, jamais silencieux.

    Raises:
        PdfPageCountMismatchError: PDFium ne compte pas `expected_page_count`
            pages (D-107).
    """
    import pypdfium2 as pdfium

    with _PDFIUM_LOCK:
        pdf = None
        bitmap = None
        try:
            pdf = pdfium.PdfDocument(str(path))
            # D-107 : garde avant tout `pdf[idx]`.
            pdfium_page_count = len(pdf)
            if pdfium_page_count != expected_page_count:
                raise PdfPageCountMismatchError(expected_page_count, pdfium_page_count, "PDFium")

            page = pdf[idx]
            # D-096 : le plafond de pixels est vérifié AVANT le rendu — sinon
            # la bitmap complète est déjà allouée (une page A0 à 200 dpi
            # ≈ 250 Mo RGBA, une page hostile plusieurs Go) : un OOM est un
            # SIGKILL, pas une exception rattrapable, et tue tout le processus
            # (même classe que D-078).
            # D-105 : le calcul se fait toujours avant allocation, mais une
            # page hors plafond n'est plus perdue — elle est rendue à
            # l'échelle réduite qui la fait tenir.
            width, height = page.get_size()
            page_scale = _ocr_render_scale(width, height)
            if page_scale is None:
                logger.warning("Page %d de %s trop grande pour l'OCR, ignorée", idx + 1, path)
                return None
            if page_scale < OCR_DPI / 72:
                logger.info(
                    "Page %d de %s rendue en résolution réduite (%d dpi au lieu de %d)"
                    " pour tenir sous le plafond mémoire OCR",
                    idx + 1,
                    path,
                    round(page_scale * 72),
                    OCR_DPI,
                )
            bitmap = page.render(scale=page_scale)
            return bitmap.to_pil().copy()
        except PdfPageCountMismatchError:
            raise
        except Exception:
            logger.warning("Rastérisation échouée page %d de %s", idx + 1, path, exc_info=True)
            return None
        finally:
            # `bitmap.close()` et `pdf.close()` sont des appels PDFium : ils
            # doivent rester à l'intérieur du verrou.
            if bitmap is not None:
                bitmap.close()
            if pdf is not None:
                pdf.close()


def _ocr_pages(
    path: Path,
    page_indices: list[int],
    lang: str,
    engine: OcrEngine,
    expected_page_count: int,
) -> dict[int, tuple[str, bool]]:
    """Rastérise puis reconnaît une sélection de pages (0-indexées).

    D-107 — **les indices reçus viennent de pdfminer, le rendu vient de
    PDFium** : `page_indices` numérote les pages telles que
    `_extract_pages_pdfminer` les a énumérées, `pdf[idx]` les prend telles
    que PDFium les voit. Ces deux suites ne coïncident pas toujours (pdfminer
    déduplique l'arbre `/Pages`, PDFium non). `expected_page_count` est le
    nombre de pages de l'appelant : s'il ne correspond pas à celui de PDFium,
    aucune page n'est rendue et `PdfPageCountMismatchError` est levée — laisser
    passer reviendrait à coller le texte reconnu d'une page sur une autre,
    en écrasant son vrai texte. C'est la deuxième garde, au point exact où
    les deux bibliothèques se croisent ; la première (pypdf) est dans
    `PdfExtractor.extract`.

    Tout accès à PDFium est **protégé par `_PDFIUM_LOCK`** (D-078) : PDFium
    n'est pas thread-safe entre `PdfDocument` distincts chargés depuis des
    threads différents — vérifié en conditions réelles, un dossier avec
    plusieurs PDF nécessitant l'OCR traités en parallèle
    (`ThreadPoolExecutor` de l'orchestrateur) produit une corruption de tas
    native (`malloc(): unsorted double linked list corrupted`) puis un
    SIGSEGV qui tue tout le processus — pas seulement le fichier en cours.
    Un verrou global sérialise l'accès à PDFium pour tout le processus ; la
    reconnaissance Tesseract, elle, reste parallélisée (chaque appel est déjà
    un process OS isolé via `subprocess`, donc thread-safe côté appelant,
    hors du verrou).

    D-108 — **étendue du verrou et pic mémoire.** Auparavant une seule prise
    du verrou couvrait tout le document, et l'encodage PNG — qui n'appelle
    jamais PDFium — se faisait dedans ; les PNG de toutes les pages étaient
    de plus accumulés jusqu'à la fin du rendu, contrairement à ce que cette
    docstring affirmait (« jamais tout le PDF en mémoire à la fois »). Mesuré
    sur un PDF scanné de 200 pages A4 à 200 dpi : **RSS 16 Mo → 2 023 Mo**,
    verrou détenu **95,7 s sur 96,2 s (99 %)**, dont ~83 % en encodage PNG.
    Avec `MAX_WORKERS` fichiers en parallèle, le débit OCR de tout le
    processus était plafonné par ce verrou.

    Désormais : une page à la fois (`_render_page_image`, verrou pris et
    relâché par page), encodage PNG **hors** du verrou, et soumission à
    l'OCR au fil de l'eau — bornée par `in_flight`, pour que la file des PNG
    ne remplace pas le dictionnaire qu'elle a supprimé.

    Args:
        path: Chemin du PDF.
        page_indices: Indices 0-indexés des pages à OCRiser, dans la
            numérotation de `_extract_pages_pdfminer`.
        lang: Langues Tesseract.
        engine: Moteur OCR résolu.
        expected_page_count: Nombre total de pages dans cette même
            numérotation, pour vérifier que PDFium parcourt bien le même
            document (D-107).

    Returns:
        Dict {index page: (texte reconnu, succès)}. Une page en échec (raster
        impossible, page trop grande, timeout) a `succès=False` et un texte
        vide.

    Raises:
        PdfPageCountMismatchError: PDFium ne compte pas `expected_page_count`
            pages — les indices ne désignent pas les mêmes pages des deux
            côtés. Seule exception que cette fonction laisse remonter.
    """
    results: dict[int, tuple[str, bool]] = {}
    capped = page_indices[:OCR_MAX_PAGES_PER_FILE]
    for skipped in page_indices[OCR_MAX_PAGES_PER_FILE:]:
        results[skipped] = ("", False)
    if not capped:
        return results

    # Défaut : échec. Une page rendue puis reconnue écrase son entrée.
    for idx in capped:
        results[idx] = ("", False)

    # D-098 : borné par le sémaphore global `OCR_SLOTS` (partagé avec les
    # images intégrées), plus de MAX_WORKERS² processus Tesseract.
    workers = min(OCR_MAX_CONCURRENCY, len(capped))
    # D-108 : les PNG ne sont plus tous gardés jusqu'à la fin du rendu, mais
    # la file du pool pourrait reproduire exactement le même pic si le rendu
    # (~85 ms/page) distance l'OCR (~1 s/page). `in_flight` borne le nombre
    # de PNG vivants à la fois : les travailleurs occupés, plus deux en
    # attente pour ne jamais les laisser sans travail.
    in_flight = threading.Semaphore(workers + 2)

    def _recognize(png: bytes) -> str:
        try:
            return ocr_with_slot(engine, png, lang)
        finally:
            in_flight.release()

    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures: dict[Future[str], int] = {}
        for idx in capped:
            image = _render_page_image(path, idx, expected_page_count)
            if image is None:
                continue
            # D-108 : hors `_PDFIUM_LOCK` — l'encodage PNG n'appelle jamais
            # PDFium et représentait ~83 % du temps passé sous le verrou.
            buf = io.BytesIO()
            image.save(buf, format="PNG")
            del image
            in_flight.acquire()
            futures[executor.submit(_recognize, buf.getvalue())] = idx

        for future in as_completed(futures):
            idx = futures[future]
            text = future.result()
            results[idx] = (text, bool(text.strip()))

    return results
