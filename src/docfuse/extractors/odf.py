"""Extracteur OpenDocument : .odt, .ods, .odp.

CdC §7.3 — Si ZIP/XML trivial (OpenDocument).
Les fichiers ODF sont des ZIP contenant du XML (content.xml, meta.xml).
On extrait le texte de content.xml.
"""

from __future__ import annotations

import logging
import zipfile
from pathlib import Path
from typing import Any

from docfuse.core.embedded_images import ImageBatch, build_image_tag
from docfuse.core.ocr.registry import resolve_ocr_engine
from docfuse.core.registry import register
from docfuse.extractors.base import Extractor, error_result, is_zip_bomb
from docfuse.extractors.html import tag_text
from docfuse.i18n import t
from docfuse.models.extraction_result import ExtractedFile
from docfuse.models.file_status import FileStatus

logger = logging.getLogger(__name__)


@register(".odt", ".ods", ".odp")
class OdfExtractor(Extractor):
    """Extracteur OpenDocument (ODT/ODS/ODP) via ZIP/XML."""

    file_type = "odf"

    @classmethod
    def accepts(cls, path: Path) -> bool:
        return path.suffix.lower() in (".odt", ".ods", ".odp")

    @classmethod
    def extract(cls, path: Path, relative_path: str, extract_images: bool = False) -> ExtractedFile:
        try:
            # D-093 : garde-fou "bombe zip" avant tout parsing du conteneur.
            if is_zip_bomb(path):
                return ExtractedFile(
                    path=path,
                    relative_path=relative_path,
                    extension=path.suffix.lower().lstrip("."),
                    file_type=path.suffix.lower().lstrip("."),
                    size_bytes=path.stat().st_size,
                    status=FileStatus.ERROR,
                    error_message=t("error.zip_bomb_suspected"),
                )

            from bs4 import BeautifulSoup

            # D-093 : OCR/export des images intégrées (odt/odp), seulement
            # si utile — sinon zéro coût ajouté par rapport à avant.
            # D-098 : jetons pendant le parcours, OCR parallèle unique.
            batch = ImageBatch(resolve_ocr_engine(), extract_images)

            with zipfile.ZipFile(str(path), "r") as zf:
                # Compter les images
                image_count = sum(1 for n in zf.namelist() if n.startswith(("Pictures/", "media/")))

                # Lire content.xml
                if "content.xml" not in zf.namelist():
                    return ExtractedFile(
                        path=path,
                        relative_path=relative_path,
                        extension=path.suffix.lower().lstrip("."),
                        file_type=path.suffix.lower().lstrip("."),
                        size_bytes=path.stat().st_size,
                        text="",
                        status=FileStatus.ERROR,
                        error_message="content.xml introuvable dans l'archive ODF",
                    )

                content_xml = zf.read("content.xml")
                soup = BeautifulSoup(content_xml, "xml")
                _materialize_whitespace(soup)

                # BUG FIX: extraire les paragraphes et les tableaux dans l'ordre
                # sans duplication. On parcourt les enfants de office:text.
                parts: list[str] = []

                from bs4 import Tag as BTag

                # D-087 : .odp (office:presentation) traité en premier, à
                # part — voir _extract_presentation. Sans ce cas dédié, le
                # code tombait dans un repli générique qui mélangeait le
                # contenu visible des diapos ET les notes d'orateur.
                # D-096 : `.ods` (office:spreadsheet) a aussi son traitement
                # dédié — il tombait dans le même repli, qui listait chaque
                # cellule sur sa propre ligne (structure lignes/colonnes
                # perdue, un LLM ne peut plus reconstituer le tableau).
                office_presentation = soup.find("office:presentation")
                office_spreadsheet = soup.find("office:spreadsheet")
                office_text = soup.find("office:text")
                if isinstance(office_presentation, BTag):
                    parts.extend(
                        _extract_presentation(office_presentation, zf, relative_path, batch)
                    )
                elif isinstance(office_spreadsheet, BTag):
                    parts.extend(_extract_spreadsheet(office_spreadsheet))
                elif isinstance(office_text, BTag):
                    ctx = _ImageContext(zf, relative_path, batch)
                    parts.extend(_extract_text_children(office_text, ctx))
                    parts = batch.resolve(parts)
                else:
                    # Dernier repli (document sans corps reconnu) : tout le
                    # texte, sans coller les mots.
                    for p in soup.find_all(["text:p", "text:h"]):
                        text = tag_text(p)
                        if text:
                            parts.append(text)

                # D-072 : en-têtes/pieds de page ODT vivent dans styles.xml
                # (office:master-styles), jamais dans content.xml — invisibles
                # sans ce second passage. Contiennent souvent des métadonnées
                # de document (référence, mention de confidentialité).
                if "styles.xml" in zf.namelist():
                    parts.extend(_extract_master_headers_footers(zf.read("styles.xml")))

                full_text = "\n".join(parts)

                return ExtractedFile(
                    path=path,
                    relative_path=relative_path,
                    extension=path.suffix.lower().lstrip("."),
                    file_type=path.suffix.lower().lstrip("."),  # M-08: "odt" / "ods" / "odp"
                    size_bytes=path.stat().st_size,
                    text=full_text,
                    status=FileStatus.READY,
                    image_count=image_count,
                    embedded_images=batch.images,
                )
        except Exception as exc:
            logger.exception("Erreur extraction ODF %s", path)
            return error_result(path, relative_path, cls.file_type, exc)


def _materialize_whitespace(soup: Any) -> None:
    """Remplace les blancs structurels ODF par des caractères (D-096).

    Dans ODF, plusieurs espaces, une tabulation et un saut de ligne manuel
    sont des éléments vides (`text:s`, `text:tab`, `text:line-break`) et non
    des caractères : `get_text` les ignorait, `col1<text:tab/>col2` donnait
    `col1col2`. Pré-passe unique sur tout le document.
    """
    from bs4 import NavigableString

    for tag in soup.find_all(["text:s", "text:tab", "text:line-break"]):
        if tag.name == "s":
            count = tag.get("text:c") or tag.get("c") or "1"
            try:
                replacement = " " * max(1, int(count))
            except ValueError:
                replacement = " "
        elif tag.name == "tab":
            replacement = "\t"
        else:
            replacement = "\n"
        tag.replace_with(NavigableString(replacement))


class _ImageContext:
    """État partagé du parcours d'un `.odt` : lot d'images + compteur."""

    def __init__(self, zf: zipfile.ZipFile, relative_path: str, batch: ImageBatch) -> None:
        self.zf = zf
        self.relative_path = relative_path
        self.batch = batch
        self.count = 0

    @property
    def active(self) -> bool:
        return self.batch.active


def _extract_text_children(container: Any, ctx: _ImageContext) -> list[str]:
    """Contenu d'un conteneur « body-like » ODT (`office:text`, `text:section`,
    cadre, zone de texte…), dans l'ordre d'apparition (D-096).

    L'ancienne boucle ne connaissait que table/p/h/list : tout autre enfant
    de `office:text` — `text:section` (mise en page multi-colonnes, sections
    liées, très courant), cadre ancré à la page, table des matières — était
    **silencieusement ignoré**, statut READY. De plus `"table" in tag_name`
    envoyait `table-of-content`/`illustration-index` vers le parseur de
    tableau, qui ne trouvait aucune ligne et ne rendait rien. Désormais :
    correspondance exacte pour les tableaux, récursion pour tout conteneur
    connu, et une branche finale qui émet le texte de tout élément inconnu —
    rien ne peut disparaître sans trace.
    """
    from bs4 import Tag as BTag

    parts: list[str] = []
    for child in container.children:
        if not isinstance(child, BTag):
            continue
        name = child.name or ""

        if name == "table":
            parts.extend(_table_rows_to_parts(child))
        elif name in ("p", "h"):
            text = tag_text(child)
            if text:
                parts.append(text)
        elif name == "list":
            for item in child.find_all(True, recursive=True):
                if item.name and "list-item" in item.name:
                    text = tag_text(item)
                    if text:
                        parts.append(f"- {text}")
        elif name in ("section", "frame", "text-box", "table-of-content", "index-body") or (
            name.endswith(("-index", "-source"))
        ):
            parts.extend(_extract_text_children(child, ctx))
        else:
            text = tag_text(child)
            if text:
                parts.append(text)

        # D-093 : images intégrées (`draw:frame`/`draw:image`) ancrées au
        # paragraphe (inline), à la page (`child` est lui-même un cadre) ou
        # dans un cadre. Les sections/zones de texte sont parcourues
        # récursivement : leurs cadres sont traités à leur niveau.
        if ctx.active and name not in ("section", "text-box"):
            for href in _iter_image_hrefs(child):
                ctx.count += 1
                token = _image_token(ctx.zf, href, ctx.relative_path, None, ctx.count, ctx.batch)
                if token:
                    parts.append(token)
    return parts


def _extract_spreadsheet(office_spreadsheet: Any) -> list[str]:
    """Contenu d'un `office:spreadsheet` (.ods), feuille par feuille (D-096),
    même rendu que l'extracteur XLSX (`### Feuille : nom` + lignes `a | b`)."""
    from bs4 import Tag as BTag

    parts: list[str] = []
    for table in office_spreadsheet.find_all("table:table", recursive=False):
        if not isinstance(table, BTag):
            continue
        name = table.get("table:name") or table.get("name") or "?"
        rows = _table_rows_to_parts(table)
        body = "\n".join(rows) if rows else "[Feuille vide]"
        parts.append(f"### Feuille : {name}\n\n{body}")
    return parts


def _table_rows_to_parts(table_tag: Any) -> list[str]:
    """Cellules d'un tableau ODF, une ligne `" | "` par ligne de tableau."""
    from bs4 import Tag as BTag

    parts: list[str] = []
    for row in table_tag.find_all(True, recursive=True):
        if row.name and "table-row" in row.name:
            cells = [
                c for c in row.children if isinstance(c, BTag) and c.name and "table-cell" in c.name
            ]
            cell_texts = [tag_text(c) for c in cells]
            if any(cell_texts):
                parts.append(" | ".join(cell_texts))
    return parts


def _extract_presentation(
    office_presentation: Any, zf: zipfile.ZipFile, relative_path: str, batch: ImageBatch
) -> list[str]:
    """Contenu d'un `office:presentation` (.odp), diapo par diapo (D-087).

    Corrige deux problèmes du fallback générique (`text:p`/`text:h`
    document-wide) qu'un `.odp` déclenchait systématiquement (aucun tag ne
    matche `office:text` dans une présentation, qui utilise
    `office:presentation` à la place) :
    - Les notes d'orateur (`presentation:notes`, jamais affichées à
      l'écran) étaient mélangées indistinctement au contenu visible des
      diapos — extraites ici séparément, étiquetées, jamais silencieusement
      fondues dans le texte "normal" (risque de fuite de contenu non
      destiné à la diffusion).
    - Aucune séparation entre diapos.

    D-093 : les images intégrées de chaque diapo sont détectées et
    numérotées par diapo (`slide{i}`, comme PPTX), avant que les tables
    soient retirées de l'arbre (une image dans une cellule reste détectée).
    """
    from bs4 import Tag as BTag

    slides: list[tuple[list[str], list[str]]] = []
    for i, page in enumerate(office_presentation.find_all("draw:page", recursive=False), 1):
        notes_texts: list[str] = []
        for notes in page.find_all("presentation:notes"):
            text = notes.get_text(separator=" ", strip=True)
            if text:
                notes_texts.append(text)
            notes.extract()  # retiré de l'arbre : jamais compté deux fois

        slide_parts: list[str] = []

        if batch.active:
            for slide_image_index, href in enumerate(_iter_image_hrefs(page), 1):
                token = _image_token(zf, href, relative_path, f"slide{i}", slide_image_index, batch)
                if token:
                    slide_parts.append(token)

        # Tables d'abord, puis retirées de l'arbre — sinon le texte de leurs
        # cellules serait aussi capté par la recherche text:p/text:h plus
        # bas (une cellule contient un text:p) et compté deux fois.
        tables = [
            t
            for t in page.find_all(True, recursive=True)
            if isinstance(t, BTag) and t.name and (t.name == "table" or t.name.endswith(":table"))
        ]
        for table in tables:
            slide_parts.extend(_table_rows_to_parts(table))
            table.extract()

        for p in page.find_all(["text:p", "text:h"]):
            text = tag_text(p)
            if text:
                slide_parts.append(text)

        slides.append((slide_parts, notes_texts))

    # D-098 : OCR de toutes les diapos en parallèle, puis assemblage par
    # diapo (un jeton sans marqueur disparaît, comme avant — sortie identique).
    batch.run()
    parts: list[str] = []
    for i, (slide_parts, notes_texts) in enumerate(slides, 1):
        resolved = batch.apply(slide_parts)
        if resolved:
            parts.append(f"## Diapo {i}\n" + "\n".join(resolved))
        if notes_texts:
            parts.append(f"[notes orateur diapo {i}]\n" + "\n".join(notes_texts))
    return parts


def _iter_image_hrefs(tag: Any) -> list[str]:
    """Chemins ZIP (`xlink:href`) des images intégrées (`draw:frame` >
    `draw:image`) trouvées dans `tag`, y compris `tag` lui-même si c'est
    déjà un `draw:frame` (ancrage "à la page", D-093). Contrairement à
    OOXML (DOCX/PPTX/XLSX), pas d'indirection par relation : le chemin ZIP
    est donné directement par `xlink:href`."""
    from bs4 import Tag as BTag

    def _is_frame(t: Any) -> bool:
        return (
            isinstance(t, BTag)
            and bool(t.name)
            and (t.name == "frame" or t.name.endswith(":frame"))
        )

    def _is_image(t: Any) -> bool:
        return (
            isinstance(t, BTag)
            and bool(t.name)
            and (t.name == "image" or t.name.endswith(":image"))
        )

    frames = [tag] if _is_frame(tag) else []
    frames.extend(t for t in tag.find_all(True, recursive=True) if _is_frame(t))

    hrefs: list[str] = []
    for frame in frames:
        image_tag = next((t for t in frame.find_all(True, recursive=True) if _is_image(t)), None)
        if image_tag is None:
            continue
        href = image_tag.get("xlink:href")
        if href:
            hrefs.append(str(href))
    return hrefs


def _image_token(
    zf: zipfile.ZipFile,
    href: str,
    relative_path: str,
    location: str | None,
    index: int,
    batch: ImageBatch,
) -> str:
    """Enregistre une image ODF dans le lot et renvoie son jeton de position
    (D-093, D-098). N'échoue jamais : une image illisible est ignorée."""
    try:
        data = zf.read(href)
    except KeyError:
        return ""
    ext = href.rsplit(".", 1)[-1] if "." in href else "png"
    return batch.add(build_image_tag(relative_path, location, index, ext), data)


def _extract_master_headers_footers(styles_xml: bytes) -> list[str]:
    """Texte des en-têtes/pieds de page ODT (D-072).

    Spec OASIS ODF 1.2 §16.4-16.5 : `office:master-styles` contient un ou
    plusieurs `style:master-page`, chacun avec un `style:header`/
    `style:footer` optionnel — le texte récurrent affiché sur les pages qui
    utilisent ce style de page. Absent de `content.xml`.
    """
    from bs4 import BeautifulSoup
    from bs4 import Tag as BTag

    soup = BeautifulSoup(styles_xml, "xml")
    parts: list[str] = []
    for master_page in soup.find_all("style:master-page"):
        if not isinstance(master_page, BTag):
            continue
        header = master_page.find("style:header")
        if isinstance(header, BTag):
            text = tag_text(header)
            if text:
                parts.append(f"[en-tête] {text}")
        footer = master_page.find("style:footer")
        if isinstance(footer, BTag):
            text = tag_text(footer)
            if text:
                parts.append(f"[pied de page] {text}")
    return parts
