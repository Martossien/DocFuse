"""Extracteur CSV/TSV : .csv, .tsv.

CdC §7.3 — Texte tabulaire.
"""

from __future__ import annotations

import csv
import io
from pathlib import Path

from docfuse.core.registry import register
from docfuse.extractors.base import Extractor, error_result
from docfuse.extractors.text import decode_text
from docfuse.i18n import t
from docfuse.models.extraction_result import ExtractedFile
from docfuse.models.file_status import FileStatus


@register(".csv", ".tsv")
class CsvTsvExtractor(Extractor):
    """Extracteur pour les fichiers CSV et TSV."""

    file_type = "csv_tsv"

    @classmethod
    def accepts(cls, path: Path) -> bool:
        return path.suffix.lower() in (".csv", ".tsv")

    @classmethod
    def extract(
        cls, path: Path, relative_path: str, _extract_images: bool = False
    ) -> ExtractedFile:
        try:
            raw = path.read_bytes()
            encoding, text_raw, mojibake_repaired = decode_text(raw)
            extra_metadata: dict[str, str] = {}
            if mojibake_repaired:
                extra_metadata["mojibake_repaired"] = t("text.mojibake_repaired_note")

            delimiter = "\t" if path.suffix.lower() == ".tsv" else ","
            # M-05: Détecter si le CSV utilise ; (fréquent en français)
            if text_raw and delimiter == ",":
                first_line = text_raw.split("\n")[0]
                if ";" in first_line:
                    delimiter = ";"
            reader = csv.reader(io.StringIO(text_raw), delimiter=delimiter)
            lines: list[str] = []
            for row in reader:
                lines.append(" | ".join(row))

            text = "\n".join(lines)

            return ExtractedFile(
                path=path,
                relative_path=relative_path,
                extension=path.suffix.lower().lstrip("."),
                file_type=path.suffix.lower().lstrip("."),
                size_bytes=len(raw),
                text=text,
                status=FileStatus.READY,
                encoding=encoding,
                extra_metadata=extra_metadata,
            )
        except Exception as exc:
            return error_result(path, relative_path, cls.file_type, exc)
