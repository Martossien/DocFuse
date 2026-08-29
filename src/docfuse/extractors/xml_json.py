"""Extracteur XML/JSON/YAML/INI : .xml, .json, .yaml, .yml, .ini, .cfg.

CdC §7.3 — Texte / pretty-print.
"""

from __future__ import annotations

import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path

from docfuse.core.registry import register
from docfuse.extractors.base import Extractor, error_result, file_type_for
from docfuse.extractors.text import decode_text, decode_text_with_note, mojibake_metadata
from docfuse.i18n import t
from docfuse.models.extraction_result import ExtractedFile
from docfuse.models.file_status import FileStatus


@register(".json")
class JsonExtractor(Extractor):
    """Extracteur JSON (pretty-print)."""

    @classmethod
    def accepts(cls, path: Path) -> bool:
        return path.suffix.lower() == ".json"

    @classmethod
    def extract(
        cls, path: Path, relative_path: str, _extract_images: bool = False
    ) -> ExtractedFile:
        try:
            raw = path.read_bytes()
            # D-093 : la réparation mojibake (ftfy) est appliquée AVANT
            # json.loads() — un JSON syntaxiquement corrompu par un
            # double-encodage UTF-8 en amont peut ainsi redevenir du JSON
            # valide au lieu de finir systématiquement en ERROR (D-092).
            encoding, text_raw, extra_metadata = decode_text_with_note(raw)
            obj = json.loads(text_raw)
            text = json.dumps(obj, indent=2, ensure_ascii=False)

            return ExtractedFile(
                path=path,
                relative_path=relative_path,
                extension=file_type_for(path),
                file_type=file_type_for(path),
                size_bytes=len(raw),
                text=text,
                status=FileStatus.READY,
                encoding=encoding,
                extra_metadata=extra_metadata,
            )
        except json.JSONDecodeError as exc:
            # D-092 : un JSON syntaxiquement invalide (tronqué, corrompu,
            # double-encodage UTF-8 en amont) donnait `JSONDecodeError: ...`
            # brut comme message — incompréhensible pour un utilisateur non
            # technique. `error.corrupt_file` (déjà présent en i18n, jamais
            # utilisé jusqu'ici) donne un message clair ; le détail
            # ligne/colonne de l'exception reste ajouté pour permettre de
            # localiser le problème dans le fichier.
            return ExtractedFile(
                path=path,
                relative_path=relative_path,
                extension=file_type_for(path),
                file_type=file_type_for(path),
                size_bytes=path.stat().st_size if path.exists() else 0,
                status=FileStatus.ERROR,
                error_message=f"{t('error.corrupt_file')} : {exc}",
            )
        except Exception as exc:
            return error_result(path, relative_path, exc)


_XML_DECLARED_ENCODING_RE = re.compile(rb'^\s*<\?xml[^>]*encoding=["\']([A-Za-z0-9._-]+)["\']')


def _decode_xml(raw: bytes) -> tuple[str, str, bool]:
    """Décode un XML en honorant sa déclaration `encoding=` (D-096).

    Même défaut que D-073 pour HTML : `detect_encoding()` acceptait cp1252
    (« plausible ») pour un fichier déclaré `windows-1251`, produisant du
    charabia en statut READY. La déclaration est la source de vérité quand
    Python connaît l'encodage et que le décodage réussit ; sinon repli sur
    la détection générique.
    """
    match = _XML_DECLARED_ENCODING_RE.match(raw[:200])
    if match:
        declared = match.group(1).decode("ascii", errors="ignore")
        try:
            return declared, raw.decode(declared), False
        except (LookupError, UnicodeDecodeError):
            pass
    return decode_text(raw)


@register(".xml")
class XmlExtractor(Extractor):
    """Extracteur XML (pretty-print)."""

    @classmethod
    def accepts(cls, path: Path) -> bool:
        return path.suffix.lower() == ".xml"

    @classmethod
    def extract(
        cls, path: Path, relative_path: str, _extract_images: bool = False
    ) -> ExtractedFile:
        try:
            raw = path.read_bytes()
            encoding, text_raw, xml_repaired = _decode_xml(raw)
            # Migration: minidom déprécié → ElementTree.indent (Python 3.9+)
            # D-096 : `insert_comments=True` — le pretty-print supprimait
            # tous les commentaires (`<!-- ... -->`), qui portent souvent la
            # documentation d'un fichier de configuration.
            parser = ET.XMLParser(target=ET.TreeBuilder(insert_comments=True))
            root_el = ET.fromstring(text_raw, parser=parser)
            ET.indent(root_el, space="  ")
            text = ET.tostring(root_el, encoding="unicode")
            extra_metadata = mojibake_metadata(xml_repaired)

            return ExtractedFile(
                path=path,
                relative_path=relative_path,
                extension=file_type_for(path),
                file_type=file_type_for(path),
                size_bytes=len(raw),
                text=text,
                status=FileStatus.READY,
                encoding=encoding,
                extra_metadata=extra_metadata,
            )
        except ET.ParseError as exc:
            # D-092 : même principe que JsonExtractor — message clair plutôt
            # que le `ParseError` brut de ElementTree.
            return ExtractedFile(
                path=path,
                relative_path=relative_path,
                extension=file_type_for(path),
                file_type=file_type_for(path),
                size_bytes=path.stat().st_size if path.exists() else 0,
                status=FileStatus.ERROR,
                error_message=f"{t('error.corrupt_file')} : {exc}",
            )
        except Exception as exc:
            return error_result(path, relative_path, exc)


@register(".yaml", ".yml", ".ini", ".cfg")
class YamlIniExtractor(Extractor):
    """Extracteur YAML/INI (tel quel, ce sont déjà du texte lisible)."""

    @classmethod
    def accepts(cls, path: Path) -> bool:
        return path.suffix.lower() in (".yaml", ".yml", ".ini", ".cfg")

    @classmethod
    def extract(
        cls, path: Path, relative_path: str, _extract_images: bool = False
    ) -> ExtractedFile:
        try:
            raw = path.read_bytes()
            encoding, text, extra_metadata = decode_text_with_note(raw)

            return ExtractedFile(
                path=path,
                relative_path=relative_path,
                extension=file_type_for(path),
                file_type=file_type_for(path),
                size_bytes=len(raw),
                text=text,
                status=FileStatus.READY,
                encoding=encoding,
                extra_metadata=extra_metadata,
            )
        except Exception as exc:
            return error_result(path, relative_path, exc)
