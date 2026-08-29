"""Extracteur XML/JSON/YAML/INI : .xml, .json, .yaml, .yml, .ini, .cfg.

CdC §7.3 — Texte / pretty-print.
"""

from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from pathlib import Path

from docfuse.core.registry import register
from docfuse.extractors.base import Extractor, error_result
from docfuse.extractors.text import detect_encoding
from docfuse.i18n import t
from docfuse.models.extraction_result import ExtractedFile
from docfuse.models.file_status import FileStatus


@register(".json")
class JsonExtractor(Extractor):
    """Extracteur JSON (pretty-print)."""

    file_type = "xml_json"

    @classmethod
    def accepts(cls, path: Path) -> bool:
        return path.suffix.lower() == ".json"

    @classmethod
    def extract(
        cls, path: Path, relative_path: str, _extract_images: bool = False
    ) -> ExtractedFile:
        try:
            raw = path.read_bytes()
            encoding, data = detect_encoding(raw)
            text_raw = data.decode(encoding, errors="replace")
            obj = json.loads(text_raw)
            text = json.dumps(obj, indent=2, ensure_ascii=False)

            return ExtractedFile(
                path=path,
                relative_path=relative_path,
                extension="json",
                file_type="json",  # M-08
                size_bytes=len(raw),
                text=text,
                status=FileStatus.READY,
                encoding=encoding,
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
                extension="json",
                file_type="json",
                size_bytes=path.stat().st_size if path.exists() else 0,
                status=FileStatus.ERROR,
                error_message=f"{t('error.corrupt_file')} : {exc}",
            )
        except Exception as exc:
            return error_result(path, relative_path, "json", exc)


@register(".xml")
class XmlExtractor(Extractor):
    """Extracteur XML (pretty-print)."""

    file_type = "xml_json"

    @classmethod
    def accepts(cls, path: Path) -> bool:
        return path.suffix.lower() == ".xml"

    @classmethod
    def extract(
        cls, path: Path, relative_path: str, _extract_images: bool = False
    ) -> ExtractedFile:
        try:
            raw = path.read_bytes()
            encoding, data = detect_encoding(raw)
            text_raw = data.decode(encoding, errors="replace")
            # Migration: minidom déprécié → ElementTree.indent (Python 3.9+)
            root_el = ET.fromstring(text_raw)
            ET.indent(root_el, space="  ")
            text = ET.tostring(root_el, encoding="unicode")

            return ExtractedFile(
                path=path,
                relative_path=relative_path,
                extension="xml",
                file_type="xml",  # M-08
                size_bytes=len(raw),
                text=text,
                status=FileStatus.READY,
                encoding=encoding,
            )
        except ET.ParseError as exc:
            # D-092 : même principe que JsonExtractor — message clair plutôt
            # que le `ParseError` brut de ElementTree.
            return ExtractedFile(
                path=path,
                relative_path=relative_path,
                extension="xml",
                file_type="xml",
                size_bytes=path.stat().st_size if path.exists() else 0,
                status=FileStatus.ERROR,
                error_message=f"{t('error.corrupt_file')} : {exc}",
            )
        except Exception as exc:
            return error_result(path, relative_path, "xml", exc)


@register(".yaml", ".yml", ".ini", ".cfg")
class YamlIniExtractor(Extractor):
    """Extracteur YAML/INI (tel quel, ce sont déjà du texte lisible)."""

    file_type = "xml_json"

    @classmethod
    def accepts(cls, path: Path) -> bool:
        return path.suffix.lower() in (".yaml", ".yml", ".ini", ".cfg")

    @classmethod
    def extract(
        cls, path: Path, relative_path: str, _extract_images: bool = False
    ) -> ExtractedFile:
        try:
            raw = path.read_bytes()
            encoding, data = detect_encoding(raw)
            text = data.decode(encoding, errors="replace")

            return ExtractedFile(
                path=path,
                relative_path=relative_path,
                extension=path.suffix.lower().lstrip("."),
                file_type=path.suffix.lower().lstrip("."),  # M-08: "yaml" / "ini" etc.
                size_bytes=len(raw),
                text=text,
                status=FileStatus.READY,
                encoding=encoding,
            )
        except Exception as exc:
            return error_result(path, relative_path, path.suffix.lower().lstrip("."), exc)
