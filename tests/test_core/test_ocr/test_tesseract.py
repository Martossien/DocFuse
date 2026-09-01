"""Tests du moteur OCR Tesseract (binaire CLI, subprocess).

Ces tests s'exécutent que Tesseract soit installé ou non sur la machine de
test : `is_available()` reflète l'environnement réel, et les tests qui ont
besoin d'un vrai OCR sont sous `skipif(not is_available())` — même idiome
que les moteurs de comptage optionnels (`test_tokenizers/test_mistral.py`).
"""

from __future__ import annotations

import io
import json
import logging
import subprocess

import pytest

from docfuse.core.ocr import tesseract as tess
from docfuse.core.ocr.tesseract import (
    TesseractEngine,
    _resolve_binary,
    available_languages,
    effective_lang,
    failure_counts,
    reset_failure_counts,
    self_test,
)

_ENGINE = TesseractEngine()


def _completed(
    returncode: int, stdout: bytes = b"", stderr: bytes = b""
) -> subprocess.CompletedProcess[bytes]:
    return subprocess.CompletedProcess(
        args=["tesseract"], returncode=returncode, stdout=stdout, stderr=stderr
    )


@pytest.fixture(autouse=True)
def _clean_counters() -> None:
    """Le dédoublonnage des messages est un état de module : on repart de zéro
    à chaque test, sinon un message déjà vu ailleurs masquerait le log attendu."""
    reset_failure_counts()


class TestTesseractEngine:
    def test_info_id(self) -> None:
        assert TesseractEngine.info.id == "tesseract"

    def test_is_available_reflects_environment(self) -> None:
        import shutil

        expected = shutil.which("tesseract") is not None
        assert _ENGINE.is_available() is expected

    def test_unavailable_when_binary_not_found(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("shutil.which", lambda _name: None)
        _resolve_binary.cache_clear()
        try:
            assert _ENGINE.is_available() is False
            assert _ENGINE.ocr_image(b"not a real png", "fra") == ""
        finally:
            _resolve_binary.cache_clear()

    @pytest.mark.skipif(not _ENGINE.is_available(), reason="Tesseract non installé")
    def test_ocr_image_recognizes_rendered_text(self) -> None:
        from PIL import Image, ImageDraw

        img = Image.new("RGB", (600, 150), "white")
        draw = ImageDraw.Draw(img)
        draw.text((10, 50), "Bonjour le monde", fill="black")
        buf = io.BytesIO()
        img.save(buf, format="PNG")

        text = _ENGINE.ocr_image(buf.getvalue(), "fra+eng")
        assert "onjour" in text or "monde" in text

    @pytest.mark.skipif(not _ENGINE.is_available(), reason="Tesseract non installé")
    def test_ocr_image_invalid_data_returns_empty_not_raises(self) -> None:
        assert _ENGINE.ocr_image(b"clearly not a png", "fra") == ""


class TestLanguageResolution:
    """D-105 : une langue absente du tessdata faisait échouer CHAQUE page en
    code 1 (`OCR_LANG = "fra+eng"` sur un bundle sans `eng.traineddata`)."""

    def test_reduces_to_installed_languages(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        monkeypatch.setattr(tess, "_list_langs", lambda: frozenset({"fra"}))
        with caplog.at_level(logging.WARNING, logger=tess.__name__):
            assert effective_lang("fra+eng") == "fra"
        assert "langue eng absente du tessdata, OCR en fra seul" in caplog.text

    def test_keeps_requested_order(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(tess, "_list_langs", lambda: frozenset({"eng", "fra", "deu"}))
        assert effective_lang("fra+eng") == "fra+eng"

    def test_empty_tessdata_disables_ocr(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        monkeypatch.setattr(tess, "_list_langs", lambda: frozenset())
        with caplog.at_level(logging.WARNING, logger=tess.__name__):
            assert effective_lang("fra+eng") == ""
        assert "Aucune des langues demandées" in caplog.text

    def test_ocr_image_does_not_run_tesseract_without_language(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Sans langue utilisable, aucun process n'est lancé — c'est ce qui
        évitait les 36 lignes « code 1 » consécutives du journal réel."""
        monkeypatch.setattr(tess, "_resolve_binary", lambda: "/usr/bin/tesseract")
        monkeypatch.setattr(tess, "_list_langs", lambda: frozenset())

        def _forbidden(*_args: object, **_kwargs: object) -> None:
            raise AssertionError("tesseract ne doit pas être lancé")

        monkeypatch.setattr(subprocess, "run", _forbidden)
        assert _ENGINE.ocr_image(b"png", "fra+eng") == ""

    def test_unknown_listing_keeps_request_unchanged(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Listage impossible (`None`) ≠ tessdata vide : on ne désactive pas
        l'OCR sur un doute, la demande passe telle quelle (comportement d'avant)."""
        monkeypatch.setattr(tess, "_list_langs", lambda: None)
        assert effective_lang("fra+eng") == "fra+eng"
        assert available_languages() == frozenset()

    def test_available_languages_parses_list_langs(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(tess, "_resolve_binary", lambda: "/usr/bin/tesseract")
        monkeypatch.setattr(
            subprocess,
            "run",
            lambda *_a, **_k: _completed(
                0, stdout=b'List of available languages in "/usr/share/tessdata/" (2):\neng\nfra\n'
            ),
        )
        tess._list_langs.cache_clear()
        try:
            assert available_languages() == frozenset({"eng", "fra"})
        finally:
            tess._list_langs.cache_clear()


class TestFailureLogging:
    """D-105 : le `stderr` de Tesseract était jeté — on ne pouvait pas savoir
    pourquoi le code 1 tombait. Il est journalisé, mais une seule fois."""

    def test_stderr_is_logged_once_and_counted(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        stderr = b"Error opening data file /opt/tessdata/eng.traineddata"
        monkeypatch.setattr(tess, "_resolve_binary", lambda: "/opt/tesseract")
        monkeypatch.setattr(tess, "_list_langs", lambda: None)
        monkeypatch.setattr(subprocess, "run", lambda *_a, **_k: _completed(1, stderr=stderr))

        with caplog.at_level(logging.WARNING, logger=tess.__name__):
            for _ in range(3):
                assert _ENGINE.ocr_image(b"png", "fra+eng") == ""

        messages = [r.getMessage() for r in caplog.records]
        assert len(messages) == 1, messages
        assert "code 1" in messages[0]
        assert "/opt/tesseract" in messages[0]
        assert "fra+eng" in messages[0]
        assert "eng.traineddata" in messages[0]
        assert sum(failure_counts().values()) == 3

    def test_stderr_is_truncated(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(tess, "_resolve_binary", lambda: "/opt/tesseract")
        monkeypatch.setattr(tess, "_list_langs", lambda: None)
        monkeypatch.setattr(subprocess, "run", lambda *_a, **_k: _completed(1, stderr=b"x" * 5000))
        _ENGINE.ocr_image(b"png", "fra")
        message = next(iter(failure_counts()))
        assert "(tronqué)" in message
        assert len(message) < 800


class TestSelfTest:
    """`self_test()` — diagnostic destiné à `docia doctor`."""

    def test_result_is_json_serializable_without_binary(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(tess, "_resolve_binary", lambda: None)
        report = self_test()
        assert report["available"] is False
        assert report["ocr_ok"] is False
        json.dumps(report)

    @pytest.mark.skipif(not _ENGINE.is_available(), reason="Tesseract non installé")
    def test_real_engine_reads_its_own_image(self) -> None:
        report = self_test()
        json.dumps(report)
        assert report["available"] is True
        assert report["binary"]
        assert report["version"]
        assert report["ocr_ok"] is True
        assert report["expected_text"] == "4711"
        # Blancs normalisés : Tesseract peut espacer les chiffres selon le rendu.
        assert "4711" in "".join(str(report["ocr_text"]).split())

    def test_spaced_reading_is_accepted(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """« 47 11 » vaut « 4711 » : `docia doctor` en fait un code de retour, et la
        construction de l'exécutable Windows ne doit pas échouer sur un espacement."""
        monkeypatch.setattr(tess, "_resolve_binary", lambda: "/usr/bin/tesseract")
        monkeypatch.setattr(tess, "_version", lambda: "tesseract 5.5.0")
        monkeypatch.setattr(tess, "available_languages", lambda: frozenset({"fra", "eng"}))
        monkeypatch.setattr(
            tess,
            "_run_tesseract",
            lambda *_a, **_k: subprocess.CompletedProcess([], 0, b" 47 11 \n", b""),
        )
        assert self_test()["ocr_ok"] is True


class TestFailureCacheBounds:
    """D-106 : `_FAILURE_COUNTS` n'était borné par rien et sa clé contenait le
    `stderr` complet — une valeur variable dans ce `stderr` (« Estimating
    resolution as 633 ») créait une clé neuve par page : dictionnaire qui
    croît sans fin **et** dédoublonnage inopérant, donc le bruit revient."""

    def test_variable_numbers_in_stderr_collapse_to_one_key(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        monkeypatch.setattr(tess, "_resolve_binary", lambda: "/opt/tesseract")
        monkeypatch.setattr(tess, "_list_langs", lambda: None)

        calls = {"n": 0}

        def _run(*_a: object, **_k: object) -> subprocess.CompletedProcess[bytes]:
            calls["n"] += 1
            stderr = f"Estimating resolution as {600 + calls['n']}".encode()
            return _completed(1, stderr=stderr)

        monkeypatch.setattr(subprocess, "run", _run)

        with caplog.at_level(logging.WARNING, logger=tess.__name__):
            for _ in range(30):
                _ENGINE.ocr_image(b"png", "fra")

        assert len(failure_counts()) == 1, failure_counts()
        assert sum(failure_counts().values()) == 30
        assert len(caplog.records) == 1, [r.getMessage() for r in caplog.records]

    def test_distinct_keys_are_capped(self) -> None:
        """Au-delà du plafond, les causes inédites tombent dans un seau unique :
        le dictionnaire ne peut plus croître, le dédoublonnage tient toujours."""
        for i in range(tess._MAX_FAILURE_KEYS + 50):
            tess._log_failure_once(f"cause inédite {chr(97 + i % 26)}{'x' * i}")

        counts = failure_counts()
        # `_MAX_FAILURE_KEYS` causes distinctes + le seau de débordement.
        assert len(counts) == tess._MAX_FAILURE_KEYS + 1
        assert tess._FAILURE_OVERFLOW_KEY in counts
        assert counts[tess._FAILURE_OVERFLOW_KEY] == 50

    def test_reset_language_cache_forgets_a_transient_failure(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """`_list_langs` est un `lru_cache(maxsize=1)` : un timeout mémorisé
        interdisait l'OCR jusqu'au redémarrage du process, même après
        installation d'un `.traineddata` (session longue côté docia)."""
        monkeypatch.setattr(tess, "_resolve_binary", lambda: "/opt/tesseract")
        tess.reset_language_cache()

        state = {"failing": True}

        def _run(*_a: object, **_k: object) -> subprocess.CompletedProcess[bytes]:
            if state["failing"]:
                raise subprocess.TimeoutExpired(cmd="tesseract", timeout=1)
            return _completed(0, stdout=b"List of available languages:\nfra\n")

        monkeypatch.setattr(subprocess, "run", _run)

        assert available_languages() == frozenset()
        state["failing"] = False
        # Sans purge, l'échec transitoire reste mémorisé pour toujours.
        assert available_languages() == frozenset()

        tess.reset_language_cache()
        assert available_languages() == frozenset({"fra"})
        tess.reset_language_cache()

    def test_list_langs_failure_is_not_reported_as_a_language(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        """`_failure_message(binary, "--list-langs", result)` passait une option
        dans le paramètre `lang` : le journal affichait « langue :
        --list-langs »."""
        monkeypatch.setattr(tess, "_resolve_binary", lambda: "/opt/tesseract")
        monkeypatch.setattr(subprocess, "run", lambda *_a, **_k: _completed(1, stderr=b"boum"))
        tess.reset_language_cache()

        with caplog.at_level(logging.WARNING, logger=tess.__name__):
            assert available_languages() == frozenset()

        tess.reset_language_cache()
        messages = [r.getMessage() for r in caplog.records]
        assert messages, "l'échec du listage doit être journalisé"
        assert "langue : --list-langs" not in messages[0]
        assert "commande : --list-langs" in messages[0]


# ------------------------------------------- repli quand `stdin` est inutilisable


def _resultat(
    code: int, sortie: bytes = b"", erreur: bytes = b""
) -> subprocess.CompletedProcess[bytes]:
    return subprocess.CompletedProcess(
        args=["tesseract"], returncode=code, stdout=sortie, stderr=erreur
    )


_STDERR_WINDOWS = (
    b"Error in fopenReadStream: failed to open locally with tail  for filename \n"
    b"Leptonica Error in pixRead: image file not found: \n"
    b"Image file  cannot be read!\nError during processing.\n"
)
"""stderr réellement observé sur un poste Windows : le nom de fichier est **vide**."""


@pytest.fixture(autouse=True)
def _stdin_reputee_utilisable(monkeypatch: pytest.MonkeyPatch) -> None:
    """L'état « stdin inutilisable » est global : il ne doit pas fuir d'un test à l'autre."""
    monkeypatch.setattr(tess, "_STDIN_UNUSABLE", False)


def test_une_image_vide_naccuse_pas_tesseract(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """Zéro octet en entrée produisait « Image file cannot be read! » à chaque page.

    La trace accusait alors tesseract d'un défaut qui n'est pas le sien : c'est le
    rendu de la page qui n'a rien donné. On ne lance plus le processus du tout.
    """
    monkeypatch.setattr(tess, "_resolve_binary", lambda: "tesseract")
    monkeypatch.setattr(tess, "effective_lang", lambda _lang: "fra")
    appels: list[object] = []
    monkeypatch.setattr(tess, "_run_tesseract", lambda *args, **_kw: appels.append(args))

    with caplog.at_level(logging.WARNING):
        assert tess.TesseractEngine().ocr_image(b"", "fra+eng") == ""

    assert appels == [], "aucun processus ne doit être lancé pour une image vide"
    assert "image vide" in caplog.text
    assert "tesseract n'est pas en cause" in caplog.text


def test_stdin_illisible_bascule_sur_un_fichier_temporaire(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """Sous Windows, Leptonica ne sait pas lire une image sur un tube.

    Constaté en production : 150 pages perdues sur une seule campagne, avec pour
    seule trace un « nom de fichier vide » qui ne désignait pas la cause. Le repli
    par fichier temporaire fonctionne partout, et n'est payé qu'une fois : la
    session entière l'emprunte ensuite directement.
    """
    monkeypatch.setattr(tess, "_resolve_binary", lambda: "tesseract")
    monkeypatch.setattr(tess, "effective_lang", lambda _lang: "fra")
    vus: list[list[str]] = []

    def faux_tesseract(_binary: str, args: list[str], _entree: bytes | None = None):  # type: ignore[no-untyped-def]
        vus.append(args)
        if args[0] == "stdin":
            return _resultat(1, erreur=_STDERR_WINDOWS)
        return _resultat(0, sortie=b"FACTURE 4711")

    monkeypatch.setattr(tess, "_run_tesseract", faux_tesseract)

    with caplog.at_level(logging.WARNING):
        premier = tess.TesseractEngine().ocr_image(b"\x89PNG-faux", "fra+eng")
        second = tess.TesseractEngine().ocr_image(b"\x89PNG-faux", "fra+eng")

    assert premier == "FACTURE 4711", "le texte est bien lu par le repli"
    assert second == "FACTURE 4711"
    assert [a[0] for a in vus].count("stdin") == 1, "stdin n'est tenté qu'une seule fois"
    assert vus[-1][0].endswith("page.png")
    assert "entrée standard" in caplog.text


def test_un_echec_qui_nest_pas_celui_de_stdin_reste_signale(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """Contre-épreuve : on ne bascule pas sur un fichier pour n'importe quel échec."""
    monkeypatch.setattr(tess, "_resolve_binary", lambda: "tesseract")
    monkeypatch.setattr(tess, "effective_lang", lambda _lang: "fra")
    monkeypatch.setattr(
        tess, "_run_tesseract", lambda *_a, **_k: _resultat(1, erreur=b"Error opening data file")
    )

    with caplog.at_level(logging.WARNING):
        assert tess.TesseractEngine().ocr_image(b"\x89PNG-faux", "fra+eng") == ""

    assert tess._STDIN_UNUSABLE is False
    assert "Error opening data file" in caplog.text
