"""Tests de l'extracteur EPUB.

CdC §7.3 — livre électronique (ZIP + XHTML/OPF), texte dans l'ordre du spine.
D-093 : implémentation native (pas de dépendance `ebooklib`, AGPLv3+).
"""

from __future__ import annotations

import zipfile
from pathlib import Path

from docfuse.extractors.epub import EpubExtractor
from docfuse.models.file_status import FileStatus

_CONTAINER_XML = """<?xml version="1.0"?>
<container xmlns="urn:oasis:names:tc:opendocument:xmlns:container" version="1.0">
  <rootfiles>
    <rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>
  </rootfiles>
</container>"""


def _opf(spine_items: str, manifest_items: str, title: str = "", author: str = "") -> str:
    metadata = ""
    if title:
        metadata += f"<dc:title>{title}</dc:title>"
    if author:
        metadata += f"<dc:creator>{author}</dc:creator>"
    return f"""<?xml version="1.0"?>
<package xmlns="http://www.idpf.org/2007/opf" version="2.0">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">{metadata}</metadata>
  <manifest>{manifest_items}</manifest>
  <spine>{spine_items}</spine>
</package>"""


def _build_epub(tmp_path: Path, name: str, opf: str, chapters: dict[str, str]) -> Path:
    f = tmp_path / name
    with zipfile.ZipFile(f, "w") as zf:
        zf.writestr("mimetype", "application/epub+zip")
        zf.writestr("META-INF/container.xml", _CONTAINER_XML)
        zf.writestr("OEBPS/content.opf", opf)
        for href, content in chapters.items():
            zf.writestr(f"OEBPS/{href}", content)
    return f


class TestEpubExtractor:
    def test_accepts(self) -> None:
        assert EpubExtractor.accepts(Path("book.epub")) is True
        assert EpubExtractor.accepts(Path("book.pdf")) is False

    def test_safe_extract_no_crash(self, tmp_path: Path) -> None:
        f = tmp_path / "nonexistent.epub"
        result = EpubExtractor.safe_extract(f, "nonexistent.epub")
        assert result.status is FileStatus.ERROR

    def test_extracts_chapters_in_spine_order(self, tmp_path: Path) -> None:
        opf = _opf(
            spine_items='<itemref idref="ch1"/><itemref idref="ch2"/>',
            manifest_items=(
                '<item id="ch1" href="chap1.xhtml" media-type="application/xhtml+xml"/>'
                '<item id="ch2" href="chap2.xhtml" media-type="application/xhtml+xml"/>'
            ),
        )
        f = _build_epub(
            tmp_path,
            "book.epub",
            opf,
            {
                "chap1.xhtml": "<html><body><h1>Chapitre 1</h1><p>PREMIER_TEXTE</p></body></html>",
                "chap2.xhtml": "<html><body><h1>Chapitre 2</h1><p>SECOND_TEXTE</p></body></html>",
            },
        )

        result = EpubExtractor.extract(f, "book.epub")
        assert result.status is FileStatus.READY
        assert result.text.index("PREMIER_TEXTE") < result.text.index("SECOND_TEXTE")
        assert result.page_count == 2

    def test_title_and_author_captured(self, tmp_path: Path) -> None:
        opf = _opf(
            spine_items='<itemref idref="ch1"/>',
            manifest_items='<item id="ch1" href="chap1.xhtml" media-type="application/xhtml+xml"/>',
            title="Mon Livre",
            author="Un Auteur",
        )
        f = _build_epub(
            tmp_path,
            "book.epub",
            opf,
            {"chap1.xhtml": "<html><body><p>Texte.</p></body></html>"},
        )

        result = EpubExtractor.extract(f, "book.epub")
        assert result.status is FileStatus.READY
        assert result.extra_metadata.get("epub_title") == "Mon Livre"
        assert result.extra_metadata.get("epub_author") == "Un Auteur"

    def test_drm_protected_epub_gives_clear_error(self, tmp_path: Path) -> None:
        """D-093 : un EPUB DRM (`META-INF/encryption.xml`) ne doit jamais
        être « extrait » en bruit binaire — erreur claire à la place."""
        f = tmp_path / "drm.epub"
        opf = _opf(spine_items="", manifest_items="")
        with zipfile.ZipFile(f, "w") as zf:
            zf.writestr("mimetype", "application/epub+zip")
            zf.writestr("META-INF/container.xml", _CONTAINER_XML)
            zf.writestr("META-INF/encryption.xml", "<encryption/>")
            zf.writestr("OEBPS/content.opf", opf)

        result = EpubExtractor.extract(f, "drm.epub")
        assert result.status is FileStatus.ERROR
        assert result.error_message is not None
        assert "DRM" in result.error_message

    def test_missing_container_xml_gives_clear_error(self, tmp_path: Path) -> None:
        f = tmp_path / "broken.epub"
        with zipfile.ZipFile(f, "w") as zf:
            zf.writestr("mimetype", "application/epub+zip")
            # Pas de META-INF/container.xml

        result = EpubExtractor.extract(f, "broken.epub")
        assert result.status is FileStatus.ERROR
        assert result.error_message is not None
        assert "corrompu" in result.error_message.lower()

    def test_table_and_list_are_converted_to_markdown(self, tmp_path: Path) -> None:
        """Réutilise le parcours structuré de html.py (D-093) : tableaux et
        listes d'un chapitre EPUB doivent être convertis en Markdown."""
        opf = _opf(
            spine_items='<itemref idref="ch1"/>',
            manifest_items='<item id="ch1" href="chap1.xhtml" media-type="application/xhtml+xml"/>',
        )
        chapter = (
            "<html><body>"
            "<table><tr><td>Alpha</td><td>Beta</td></tr></table>"
            "<ul><li>Item un</li><li>Item deux</li></ul>"
            "</body></html>"
        )
        f = _build_epub(tmp_path, "book.epub", opf, {"chap1.xhtml": chapter})

        result = EpubExtractor.extract(f, "book.epub")
        assert result.status is FileStatus.READY
        assert "Alpha" in result.text
        assert "Beta" in result.text
        assert "- Item un" in result.text
        assert "- Item deux" in result.text
