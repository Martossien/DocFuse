"""Classe de base abstraite pour tous les extracteurs.

Inspiré de MarkItDown (DocumentConverter avec accepts + convert),
adapté pour DocFuse.

Contrat :
- ``accepts(path) -> bool`` : vérifie rapidement si l'extracteur peut traiter
  le fichier (par extension, par contenu). Ne doit pas consommer le flux.
- ``extract(path) -> ExtractedFile`` : extrait le texte et les métadonnées.
  Capture ses propres erreurs et retourne un statut ERROR plutôt que de crasher.
"""

from __future__ import annotations

import logging
import zipfile
from abc import ABC, abstractmethod
from pathlib import Path

from docfuse.constants import ZIP_BOMB_MAX_RATIO, ZIP_BOMB_MIN_UNCOMPRESSED_BYTES
from docfuse.i18n import t
from docfuse.models.extraction_result import ExtractedFile
from docfuse.models.file_status import FileStatus

logger = logging.getLogger(__name__)


def file_type_for(path: Path) -> str:
    """Type affiché et rapporté pour un fichier : son extension en minuscules,
    sans le point (`odt`, `json`, `py`…).

    D-099 : politique unique. Avant, un résultat READY portait l'extension
    (`odt`, `yaml`) et un résultat ERREUR le nom de famille de l'extracteur
    (`odf`, `xml_json`) — le même fichier changeait de « type » dans le
    rapport selon l'issue de son extraction, et un test sur `file_type`
    dans le writer Markdown était mort depuis M-08.
    """
    return path.suffix.lower().lstrip(".")


_OLE_CFBF_MAGIC = bytes((0xD0, 0xCF, 0x11, 0xE0, 0xA1, 0xB1, 0x1A, 0xE1))


def is_ole_encrypted(path: Path) -> bool:
    """Détecte un fichier Office (.docx/.pptx/.xlsx) protégé par un mot de
    passe **à l'ouverture** (D-089).

    Un .docx/.pptx/.xlsx "normal" est un ZIP (signature `PK\\x03\\x04`).
    Quand Office chiffre le fichier avec un mot de passe d'ouverture (pas
    juste une protection de structure/feuille), il l'enveloppe dans un
    conteneur OLE2/CFBF (Compound File Binary Format — même format que les
    anciens .doc/.xls, spec MS-OFFCRYPTO) contenant des flux `EncryptionInfo`
    et `EncryptedPackage`. Ce conteneur n'est plus un ZIP valide du tout —
    sans cette détection, python-docx/python-pptx/openpyxl échouent avec une
    exception bas niveau (`BadZipFile: File is not a zip file`,
    `PackageNotFoundError: Package not found at ...`) qui ne dit jamais à
    l'utilisateur que le fichier est protégé.
    """
    try:
        with path.open("rb") as f:
            return f.read(len(_OLE_CFBF_MAGIC)) == _OLE_CFBF_MAGIC
    except OSError:
        return False


def is_zip_bomb(path: Path) -> bool:
    """Détecte un conteneur ZIP (DOCX/PPTX/XLSX/ODF/EPUB) suspect (D-093).

    Un fichier légitime généré par Office/LibreOffice a un taux de
    compression normal. Un ratio anormal (`ZIP_BOMB_MAX_RATIO`) N'EST
    dangereux que combiné à un volume décompressé réellement conséquent
    (`ZIP_BOMB_MIN_UNCOMPRESSED_BYTES`) — un petit fichier très répétitif
    (ex: un tableau creux généré par script) n'est jamais un problème,
    même avec un ratio élevé. Heuristique documentée comme telle, pas une
    science exacte.

    Un fichier qui n'est pas un ZIP valide (ex: déjà rejeté par
    `is_ole_encrypted()`) renvoie `False` — ce n'est pas le rôle de cette
    fonction de diagnostiquer ce cas.
    """
    try:
        with zipfile.ZipFile(path) as zf:
            total_uncompressed = sum(info.file_size for info in zf.infolist())
            total_compressed = sum(info.compress_size for info in zf.infolist())
    except (OSError, zipfile.BadZipFile):
        return False

    if total_uncompressed < ZIP_BOMB_MIN_UNCOMPRESSED_BYTES:
        return False
    if total_compressed == 0:
        return total_uncompressed > 0
    return (total_uncompressed / total_compressed) > ZIP_BOMB_MAX_RATIO


def error_result_message(path: Path, relative_path: str, message: str) -> ExtractedFile:
    """Résultat ERREUR avec un message déjà traduit (D-099 : remplace huit
    littéraux `ExtractedFile(... status=ERROR ...)` copiés dans les
    extracteurs)."""
    return ExtractedFile(
        path=path,
        relative_path=relative_path,
        extension=file_type_for(path),
        file_type=file_type_for(path),
        size_bytes=path.stat().st_size if path.exists() else 0,
        status=FileStatus.ERROR,
        error_message=message,
    )


def error_result(path: Path, relative_path: str, exc: Exception) -> ExtractedFile:
    """Résultat ERREUR construit depuis une exception — factorisation du bloc
    `except` de tous les extracteurs (`safe_extract` l'utilise aussi)."""
    return error_result_message(path, relative_path, f"{type(exc).__name__}: {exc}")


def container_guard(
    path: Path, relative_path: str, *, check_ole: bool = True
) -> ExtractedFile | None:
    """Gardes communes aux formats conteneurs ZIP (DOCX/PPTX/XLSX/ODF/EPUB).

    Renvoie un résultat ERREUR explicite si le fichier est un conteneur
    Office chiffré par mot de passe (D-089, `check_ole`) ou une « bombe
    zip » suspecte (D-093) ; `None` sinon — l'extracteur continue.
    D-099 : remplace le même bloc de ~22 lignes copié dans cinq extracteurs.
    """
    if check_ole and is_ole_encrypted(path):
        return error_result_message(path, relative_path, t("error.encrypted_office"))
    if is_zip_bomb(path):
        return error_result_message(path, relative_path, t("error.zip_bomb_suspected"))
    return None


class Extractor(ABC):
    """Classe de base abstraite pour les extracteurs de texte.

    Chaque sous-classe :
    1. Décore avec ``@register(".ext")`` pour s'enregistrer.
    2. Implémente ``accepts()`` et ``extract()``.
    3. ``extract()`` ne doit JAMAIS lever d'exception — capturer et retourner
       un ExtractedFile avec ``status=FileStatus.ERROR``.

    Le `file_type` d'un résultat est toujours `file_type_for(path)` (D-099).
    """

    @classmethod
    @abstractmethod
    def accepts(cls, path: Path) -> bool:
        """Vérifie rapidement si cet extracteur peut traiter le fichier."""
        ...

    @classmethod
    @abstractmethod
    def extract(cls, path: Path, relative_path: str, extract_images: bool = False) -> ExtractedFile:
        """Extrait le texte et les métadonnées d'un fichier.

        Ne doit JAMAIS lever d'exception. Utiliser ``error_result()``
        pour construire un résultat d'erreur en cas d'échec.

        Args:
            path: Chemin absolu du fichier source.
            relative_path: Chemin relatif au dossier d'entrée.
            extract_images: Exporter les images intégrées trouvées (D-091,
                voir `core/embedded_images.py`). Ignoré par les extracteurs
                qui n'ont pas d'images intégrées à exporter (défaut `False`).
        """
        ...

    @classmethod
    def safe_extract(
        cls, path: Path, relative_path: str, extract_images: bool = False
    ) -> ExtractedFile:
        """Wrapper défensif : appelle extract() et capture toute exception non gérée."""
        try:
            result = cls.extract(path, relative_path, extract_images)
            if result.status is FileStatus.ERROR and not result.error_message:
                result.error_message = t("error.unknown")
            return result
        except Exception as exc:
            logger.exception("Erreur non capturée dans %s pour %s", cls.__name__, path)
            return error_result(path, relative_path, exc)
