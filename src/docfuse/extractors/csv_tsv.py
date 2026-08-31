"""Extracteur CSV/TSV : .csv, .tsv.

CdC §7.3 — Texte tabulaire.
"""

from __future__ import annotations

import csv
import io
from pathlib import Path

from docfuse.constants import CSV_FIELD_SIZE_LIMIT
from docfuse.core.encoding import decode_text_with_note
from docfuse.core.registry import register
from docfuse.extractors.base import Extractor, error_result, file_type_for
from docfuse.models.extraction_result import ExtractedFile
from docfuse.models.file_status import FileStatus

# D-096 : la limite par défaut du module csv (131 072 caractères par champ)
# faisait échouer entièrement un CSV dont une seule cellule contient un long
# texte ou un JSON (exports de bases, logs applicatifs). Réglage global au
# processus, sûr sous le pool de threads (positionné une fois à l'import).
csv.field_size_limit(CSV_FIELD_SIZE_LIMIT)


@register(".csv", ".tsv")
class CsvTsvExtractor(Extractor):
    """Extracteur pour les fichiers CSV et TSV."""

    @classmethod
    def accepts(cls, path: Path) -> bool:
        return path.suffix.lower() in (".csv", ".tsv")

    @classmethod
    def extract(
        cls, path: Path, relative_path: str, _extract_images: bool = False
    ) -> ExtractedFile:
        try:
            raw = path.read_bytes()
            encoding, text_raw, extra_metadata = decode_text_with_note(raw)

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
