"""Extracteur d'images autonomes (D-109) : un document scanné livré en .tif/.jpg.

Angle mort d'avant : ces fichiers étaient purement **ignorés** — ni classés, ni
signalés comme non lus. Or un copieur de bureau et un serveur de fax rendent du
`.tif`, pas du PDF, et un partage d'entreprise en est plein : bulletins de paie,
arrêts de travail, pièces d'identité numérisées.
"""

from __future__ import annotations

import logging
from pathlib import Path

import pytest

from docfuse.core.registry import get_extractor_for
from docfuse.extractors import image as img
from docfuse.models.file_status import FileStatus

pytest.importorskip("PIL")


def _image(chemin: Path, texte: str | None, taille: tuple[int, int] = (1600, 400)) -> Path:
    from PIL import Image, ImageDraw

    canevas = Image.new("RGB", taille, "white")
    if texte:
        ImageDraw.Draw(canevas).text((30, 80), texte, fill="black")
        canevas = canevas.resize((taille[0] * 2, taille[1] * 2))
    canevas.save(chemin)
    return chemin


def test_les_images_matricielles_ont_un_extracteur() -> None:
    """`.svg` et `.ico` restent hors périmètre, et c'est délibéré."""
    for nom in ("a.tif", "a.tiff", "a.jpg", "a.jpeg", "a.png", "a.bmp", "a.gif", "a.webp"):
        assert get_extractor_for(Path(nom)) is img.ImageExtractor, nom
    for nom in ("a.svg", "a.ico"):
        assert get_extractor_for(Path(nom)) is None, nom


def test_un_document_scanne_en_tif_est_lu(tmp_path: Path) -> None:
    """Le cas qui motive tout : la sortie par défaut d'un copieur."""
    chemin = _image(tmp_path / "bulletin.tif", "BULLETIN DE PAIE Jean DUPONT")

    resultat = img.ImageExtractor.extract(chemin, "bulletin.tif")

    if resultat.status is FileStatus.IMAGES and "aucun moteur OCR" in resultat.text:
        pytest.skip("aucun moteur OCR sur ce poste")
    assert resultat.status is FileStatus.READY
    assert "BULLETIN" in resultat.text.upper()
    assert resultat.image_count == 1


def test_une_image_sans_texte_le_dit_au_lieu_de_rendre_du_vide(tmp_path: Path) -> None:
    """Un vide muet ferait classer le fichier « sans contenu », donc à supprimer.

    Une photo ou un logo n'a pas de texte : c'est un fait, pas une absence de
    résultat, et le corpus doit le dire.
    """
    chemin = _image(tmp_path / "logo.png", None, taille=(60, 60))

    resultat = img.ImageExtractor.extract(chemin, "logo.png")

    assert resultat.text.strip() != ""
    assert "IMAGE" in resultat.text
    assert resultat.status is FileStatus.IMAGES


def test_sans_moteur_ocr_le_fichier_nest_pas_declare_vide(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """La variante de l'exe sans Tesseract ne doit pas transformer un scan en néant."""
    monkeypatch.setattr(img, "resolve_ocr_engine", lambda: None)
    chemin = _image(tmp_path / "courrier.jpg", "COURRIER")

    resultat = img.ImageExtractor.extract(chemin, "courrier.jpg")

    assert "aucun moteur OCR" in resultat.text
    assert "n'a pas été audité" in resultat.text
    assert resultat.status is FileStatus.IMAGES


def test_une_image_geante_est_refusee_en_le_disant(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """Au-delà de la limite OCR, on le dit — on ne rend pas un fichier vide."""
    monkeypatch.setattr(img, "_pixels", lambda _data: 400_000_000)
    appels: list[object] = []
    monkeypatch.setattr(img, "ocr_with_slot", lambda *args, **_kw: appels.append(args) or "")
    chemin = _image(tmp_path / "plan.png", "PLAN")

    with caplog.at_level(logging.WARNING):
        resultat = img.ImageExtractor.extract(chemin, "plan.png")

    assert appels == [], "on ne lance pas l'OCR sur une image hors limite"
    assert "au-delà de la limite OCR" in resultat.text
    assert resultat.status is FileStatus.IMAGES
    assert "trop grande" in caplog.text


def test_un_fichier_image_vide_est_signale(tmp_path: Path) -> None:
    chemin = tmp_path / "vide.png"
    chemin.write_bytes(b"")

    resultat = img.ImageExtractor.extract(chemin, "vide.png")

    assert "fichier vide" in resultat.text
    assert resultat.status is FileStatus.IMAGES
