"""Écriture des images intégrées exportées (D-091).

Les octets sont conservés en mémoire sur `ExtractedFile.embedded_images`
jusqu'à la génération du corpus (le dossier de sortie n'est connu qu'à ce
moment-là) — voir `core/embedded_images.py` pour le nommage et
`extractors/docx.py`/`pptx.py` pour la collecte.
"""

from __future__ import annotations

import logging
from pathlib import Path

from docfuse.models.extraction_result import ExtractedFile

logger = logging.getLogger(__name__)


def write_embedded_images(files: list[ExtractedFile], output_path: Path) -> int:
    """Écrit les images intégrées exportées dans `<output_path.stem>_images/`.

    Le dossier n'est créé que s'il y a au moins une image à écrire — jamais
    de dossier vide laissé à côté d'un corpus sans image exportée.

    Args:
        files: Fichiers extraits (les images à écrire sont dans
            `file.embedded_images`, vide si l'export n'était pas actif).
        output_path: Chemin du corpus généré (MD ou PDF).

    Returns:
        Nombre d'images effectivement écrites.
    """
    all_images = [(f, img) for f in files for img in f.embedded_images]
    if not all_images:
        return 0

    images_dir = output_path.with_name(f"{output_path.stem}_images")
    images_dir.mkdir(parents=True, exist_ok=True)

    written = 0
    for file, image in all_images:
        try:
            (images_dir / image.filename).write_bytes(image.data)
            written += 1
        except OSError:
            logger.warning(
                "Échec d'écriture de l'image %s (fichier source %s)",
                image.filename,
                file.relative_path,
                exc_info=True,
            )
    return written
