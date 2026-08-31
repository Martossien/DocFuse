"""Moteur OCR basé sur le binaire CLI Tesseract (Apache-2.0).

Invocation via `subprocess` plutôt qu'une liaison native (`tesserocr`) :
chaque appel est déjà un process OS isolé, avec son propre `timeout=` — pas
besoin d'un `ProcessPoolExecutor` ni d'un `TessBaseAPI` partagé (non
thread-safe). `tesseract stdin stdout` lit l'image sur l'entrée standard et
écrit le texte reconnu sur la sortie standard : aucun fichier temporaire à
créer ni à nettoyer.

Résolution du binaire, dans l'ordre :
1. Bundlé à côté de l'exécutable figé (variante `<App>-OCR.exe`, voir
   `DocFuse-OCR.spec`) — détecté via `sys._MEIPASS`.
2. Une installation Tesseract déjà présente sur la machine (PATH), ex.
   l'installeur Windows officiel (UB-Mannheim). Aucun réseau dans les deux cas.

Si aucun des deux n'est trouvé, `is_available()` renvoie `False` — l'appelant
(`extractors/pdf.py`) se comporte alors exactement comme avant l'ajout de
cette fonctionnalité (voir `core/ocr/registry.py::resolve_ocr_engine`).

Langues (D-105) : `OCR_LANG` demande `"fra+eng"`, mais Tesseract sort en
**code 1 pour chaque page** si une seule des langues demandées manque du
`tessdata` (« Error opening data file .../eng.traineddata ») — un bundle
incomplet ou un `TESSDATA_PREFIX` mal résolu rendait donc TOUS les PDF
scannés vides, sans aucun message exploitable. La langue demandée est
désormais réduite aux langues réellement installées (`available_languages()`
→ `effective_lang()`), et le `stderr` de Tesseract est journalisé (une seule
fois par message distinct, voir `_log_failure_once`).

Diagnostic : `self_test()` (fonction publique, retour sérialisable JSON) rend
le binaire résolu, sa version, les langues installées, la langue effective et
le résultat d'un OCR réel sur une image générée en mémoire — destiné à une
commande de type `docia doctor` côté application appelante.
"""

from __future__ import annotations

import io
import logging
import os
import re
import shutil
import subprocess
import sys
import threading
from functools import lru_cache
from pathlib import Path

from docfuse.constants import OCR_LANG, OCR_PAGE_TIMEOUT_S
from docfuse.core.ocr.base import OcrEngine, OcrEngineInfo

logger = logging.getLogger(__name__)

_STDERR_LOG_MAX_CHARS = 500
"""Troncature du `stderr` Tesseract journalisé : assez pour identifier la
cause (chemin du `.traineddata` manquant), assez court pour ne pas noyer le
journal si Tesseract déverse sa configuration complète."""

_LOG_REPEAT_EVERY = 50
"""Un message d'échec déjà vu n'est re-journalisé que toutes les N
occurrences (récapitulatif du compteur) — sur un dossier de centaines de
scans, la même erreur produisait autant de lignes identiques."""

_FAILURE_COUNTS: dict[str, int] = {}
"""Compteur par **clé** d'échec distincte (message normalisé, voir
`_failure_key`). Protégé par `_LOG_LOCK` : l'OCR tourne dans un
`ThreadPoolExecutor` (voir `extractors/pdf.py::_ocr_pages`)."""

_MAX_FAILURE_KEYS = 200
"""Plafond du nombre de causes distinctes conservées (D-106). Sans lui, le
dictionnaire n'était borné par rien : il vit toute la durée du process
(session longue côté docia) et sa clé contient le `stderr` complet de
Tesseract. `_FAILURE_COUNTS` ne dépasse donc jamais `_MAX_FAILURE_KEYS + 1`
entrées (le seau de débordement compris)."""

_FAILURE_OVERFLOW_KEY = "(autres échecs OCR, clés distinctes au-delà du plafond)"
"""Seau unique où sont comptés les échecs une fois `_MAX_FAILURE_KEYS`
atteint : le dédoublonnage continue de fonctionner (une seule ligne de
journal toutes les `_LOG_REPEAT_EVERY`) au lieu de repartir de zéro à chaque
message inédit."""

_DIGITS_RE = re.compile(r"\d+")
"""Toute suite de chiffres est remplacée dans la clé de dédoublonnage :
Tesseract glisse des valeurs variables dans son `stderr` (« Estimating
resolution as 633 », numéros de page, tailles), et chaque page créait alors
une clé neuve — dictionnaire qui croît sans fin et dédoublonnage inopérant,
le bruit console revenant en entier (D-106)."""

_LOG_LOCK = threading.Lock()

_SELF_TEST_TEXT = "4711"
"""Texte de l'image générée par `self_test()` — chiffres sans ambiguïté de
casse, reconnus par le jeu de données de n'importe quelle langue latine."""


def _failure_key(message: str) -> str:
    """Clé de dédoublonnage d'un message d'échec (D-106).

    Les chiffres sont neutralisés : « Estimating resolution as 633 » et
    « … as 641 » sont le **même** échec pour l'utilisateur, mais formaient
    deux clés — donc deux lignes de journal, et une entrée de plus dans un
    dictionnaire jamais purgé, à chaque page."""
    return _DIGITS_RE.sub("#", message)


def _log_failure_once(message: str) -> None:
    """Journalise `message` la première fois, puis une fois toutes les
    `_LOG_REPEAT_EVERY` occurrences avec le total cumulé.

    Le dédoublonnage porte sur `_failure_key(message)` et le nombre de clés
    est plafonné par `_MAX_FAILURE_KEYS` (D-106).

    Thread-safe : le décompte et la décision de journaliser sont pris sous
    `_LOG_LOCK`, l'écriture elle-même se fait hors du verrou.
    """
    key = _failure_key(message)
    with _LOG_LOCK:
        if key not in _FAILURE_COUNTS and len(_FAILURE_COUNTS) >= _MAX_FAILURE_KEYS:
            key = _FAILURE_OVERFLOW_KEY
        count = _FAILURE_COUNTS.get(key, 0) + 1
        _FAILURE_COUNTS[key] = count
    if count == 1:
        logger.warning("%s", message)
    elif count % _LOG_REPEAT_EVERY == 0:
        logger.warning("%s [répété %d fois]", message, count)


def failure_counts() -> dict[str, int]:
    """Copie du compteur des échecs OCR par cause distincte (diagnostic).

    Les clés sont les messages **normalisés** (`_failure_key`) : c'est la
    granularité réelle du dédoublonnage."""
    with _LOG_LOCK:
        return dict(_FAILURE_COUNTS)


def reset_failure_counts() -> None:
    """Remet le compteur d'échecs à zéro (tests, ou nouvelle analyse)."""
    with _LOG_LOCK:
        _FAILURE_COUNTS.clear()


def reset_language_cache() -> None:
    """Oublie les langues Tesseract mémorisées (D-106).

    `_list_langs()` est un `lru_cache(maxsize=1)` sans purge : un échec
    **transitoire** (timeout du `--list-langs`, binaire momentanément
    occupé) était mémorisé pour toute la vie du process. Dans une session
    longue — la fenêtre d'usage côté docia — installer un `.traineddata`
    ne débloquait alors plus rien avant un redémarrage complet. À appeler
    après une installation de langue, ou avant un nouveau diagnostic."""
    _list_langs.cache_clear()


class TesseractEngine(OcrEngine):
    """OCR via le binaire CLI `tesseract`."""

    info = OcrEngineInfo(id="tesseract", label_key="ocr.tesseract")

    def is_available(self) -> bool:
        return _resolve_binary() is not None

    def ocr_image(self, image_bytes: bytes, lang: str) -> str:
        binary = _resolve_binary()
        if binary is None:
            return ""
        # D-105 : une langue absente du tessdata fait échouer CHAQUE page en
        # code 1 — on ne demande que ce qui est réellement installé.
        lang = effective_lang(lang)
        if not lang:
            return ""
        result = _run_tesseract(binary, ["stdin", "stdout", "-l", lang], image_bytes)
        if result is None:
            return ""
        if result.returncode != 0:
            _log_failure_once(_failure_message(binary, result, context=f"langue : {lang}"))
            return ""
        return result.stdout.decode("utf-8", errors="replace")


def _failure_message(
    binary: str, result: subprocess.CompletedProcess[bytes], *, context: str
) -> str:
    """Message d'échec Tesseract, avec le `stderr` qui était jusqu'ici jeté.

    C'est ce message qui permet de distinguer sur le serveur de l'utilisateur
    un `tessdata` incomplet (« Error opening data file »), un binaire sans
    droits d'exécution, ou une image illisible.

    Args:
        binary: Chemin du binaire réellement exécuté.
        result: Process terminé, dont le `stderr` est repris (tronqué).
        context: Ce qui était demandé, déjà libellé — `"langue : fra+eng"`
            pour un OCR, `"commande : --list-langs"` pour un listage.
            D-106 : le paramètre s'appelait `lang` et l'appelant du listage
            y passait une **option**, ce qui affichait « langue :
            --list-langs » dans le journal de l'utilisateur.
    """
    stderr = result.stderr.decode("utf-8", errors="replace").strip()
    if len(stderr) > _STDERR_LOG_MAX_CHARS:
        stderr = stderr[:_STDERR_LOG_MAX_CHARS] + "… (tronqué)"
    return (
        f"tesseract a renvoyé le code {result.returncode} "
        f"(binaire : {binary}, {context}) — stderr : {stderr or '(vide)'}"
    )


def _run_tesseract(
    binary: str, args: list[str], input_bytes: bytes | None = None
) -> subprocess.CompletedProcess[bytes] | None:
    """Lance `tesseract` avec l'environnement résolu, ou `None` si le process
    n'a pas pu être lancé/terminé (timeout, OSError) — jamais d'exception."""
    try:
        return subprocess.run(
            [binary, *args],
            input=input_bytes,
            capture_output=True,
            timeout=OCR_PAGE_TIMEOUT_S,
            check=False,
            env=_subprocess_env(binary),
        )
    except (subprocess.TimeoutExpired, OSError) as exc:
        _log_failure_once(
            f"Échec OCR (timeout ou erreur process) : {binary} {' '.join(args)} — {exc!r}"
        )
        return None


@lru_cache(maxsize=1)
def _list_langs() -> frozenset[str] | None:
    """Langues déclarées par `tesseract --list-langs`, ou `None` si le
    listage lui-même a échoué.

    La distinction est importante (D-105) : un ensemble **vide** signifie un
    `tessdata` réellement vide → l'OCR est inutilisable ; `None` signifie
    qu'on ne sait pas (binaire trop ancien, sortie inattendue) → on n'ose
    pas désactiver l'OCR sur cette seule base et la langue demandée est
    conservée telle quelle.
    """
    binary = _resolve_binary()
    if binary is None:
        return None
    result = _run_tesseract(binary, ["--list-langs"])
    if result is None or result.returncode != 0:
        if result is not None:
            _log_failure_once(_failure_message(binary, result, context="commande : --list-langs"))
        return None
    # Selon les versions, la liste sort sur stdout (4.x/5.x) ou stderr (3.x) ;
    # la première ligne est un en-tête (« List of available languages… »),
    # écarté par la présence d'espaces, absents d'un code langue.
    raw = (result.stdout + b"\n" + result.stderr).decode("utf-8", errors="replace")
    langs = {
        line.strip()
        for line in raw.splitlines()
        if line.strip() and not any(c.isspace() for c in line.strip())
    }
    return frozenset(langs)


def available_languages() -> frozenset[str]:
    """Langues Tesseract réellement installées dans cet environnement.

    Mise en cache pour toute la durée du process (`_list_langs`) : c'est un
    lancement de process, il ne doit pas être refait à chaque page.

    Returns:
        Ensemble des codes langue (`{"fra", "eng"}`), vide si aucune langue
        n'est installée **ou** si le listage a échoué. Jamais d'exception.
    """
    return _list_langs() or frozenset()


def effective_lang(lang: str) -> str:
    """Réduit une demande de langue (`"fra+eng"`) aux langues installées.

    Args:
        lang: Codes langue Tesseract séparés par `+`, dans l'ordre de
            priorité (`OCR_LANG`).

    Returns:
        Les langues demandées **et** installées, dans l'ordre d'origine, ou
        `""` si aucune n'est installée — l'appelant renvoie alors un texte
        vide plutôt que de lancer un Tesseract voué au code 1. Si le listage
        des langues a échoué (`_list_langs()` → `None`), `lang` est renvoyée
        inchangée : c'est le comportement d'avant D-105.
    """
    installed = _list_langs()
    if installed is None:
        return lang
    requested = [code for code in lang.split("+") if code]
    kept = [code for code in requested if code in installed]
    if not kept:
        _log_failure_once(
            f"Aucune des langues demandées ({lang}) n'est présente dans le tessdata "
            f"(langues installées : {', '.join(sorted(installed)) or 'aucune'}) — "
            "OCR désactivé pour ce document. Vérifiez TESSDATA_PREFIX et les "
            "fichiers *.traineddata livrés."
        )
        return ""
    if len(kept) < len(requested):
        missing = ", ".join(code for code in requested if code not in installed)
        _log_failure_once(f"langue {missing} absente du tessdata, OCR en {'+'.join(kept)} seul")
    return "+".join(kept)


def _version() -> str | None:
    """Première ligne de `tesseract --version` (ex. « tesseract 5.5.0 »)."""
    binary = _resolve_binary()
    if binary is None:
        return None
    result = _run_tesseract(binary, ["--version"])
    if result is None:
        return None
    raw = (result.stdout + b"\n" + result.stderr).decode("utf-8", errors="replace")
    for line in raw.splitlines():
        if line.strip():
            return line.strip()
    return None


def _self_test_image() -> bytes:
    """PNG en mémoire portant `_SELF_TEST_TEXT`, sans dépendre d'une police
    système : le texte est tracé avec la police bitmap par défaut de Pillow
    puis l'image est agrandie, ce qui donne des glyphes assez hauts pour
    Tesseract sur toutes les versions de Pillow."""
    from PIL import Image, ImageDraw

    img = Image.new("RGB", (160, 60), "white")
    draw = ImageDraw.Draw(img)
    draw.text((20, 20), _SELF_TEST_TEXT, fill="black")
    img = img.resize((img.width * 6, img.height * 6), Image.Resampling.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def self_test() -> dict[str, object]:
    """Diagnostic complet du moteur OCR (destiné à `docia doctor`).

    Lance un OCR réel sur une petite image générée en mémoire et rend, sans
    jamais lever d'exception, un dictionnaire **sérialisable en JSON** :

    - `available` : le binaire a été résolu ;
    - `binary`, `version`, `tessdata_prefix` : ce qui sera réellement exécuté ;
    - `requested_lang` / `effective_lang` : `OCR_LANG` et ce qu'il en reste
      après intersection avec `available_languages` (c'est ici qu'apparaît un
      `eng.traineddata` manquant) ;
    - `ocr_ok`, `ocr_text`, `expected_text`, `returncode`, `stderr` : l'essai
      réel — `stderr` est la cause exacte d'un échec en code 1 ;
    - `failure_counts` : les échecs OCR cumulés depuis le début du process.
    """
    binary = _resolve_binary()
    installed = sorted(available_languages())
    lang = effective_lang(OCR_LANG)
    report: dict[str, object] = {
        "engine": TesseractEngine.info.id,
        "available": binary is not None,
        "binary": binary,
        "version": _version() if binary else None,
        "tessdata_prefix": (_subprocess_env(binary) or {}).get("TESSDATA_PREFIX")
        if binary
        else None,
        "available_languages": installed,
        "requested_lang": OCR_LANG,
        "effective_lang": lang,
        "expected_text": _SELF_TEST_TEXT,
        "ocr_ok": False,
        "ocr_text": "",
        "returncode": None,
        "stderr": None,
    }
    if binary is not None and lang:
        try:
            result = _run_tesseract(binary, ["stdin", "stdout", "-l", lang], _self_test_image())
        except Exception as exc:  # génération d'image impossible (Pillow)
            report["stderr"] = repr(exc)
            result = None
        if result is not None:
            text = result.stdout.decode("utf-8", errors="replace").strip()
            report["returncode"] = result.returncode
            report["ocr_text"] = text
            report["stderr"] = result.stderr.decode("utf-8", errors="replace").strip()[
                :_STDERR_LOG_MAX_CHARS
            ]
            # Blancs normalisés : Tesseract peut espacer les chiffres (« 47 11 ») selon
            # le rendu de la police. Le contrôle porte sur « l'OCR a-t-il lu quelque
            # chose de juste », pas sur la mise en page — et `docia doctor` en fait un
            # code de retour, donc un faux négatif casserait la construction de
            # l'exécutable Windows sans aucune raison réelle.
            lu = "".join(text.split())
            report["ocr_ok"] = result.returncode == 0 and _SELF_TEST_TEXT in lu
    report["failure_counts"] = failure_counts()
    return report


def _bundled_binary_path() -> Path | None:
    """Chemin du binaire Tesseract embarqué dans un exécutable figé (variante OCR).

    `sys._MEIPASS` n'existe que dans un exécutable PyInstaller onefile en
    cours d'exécution (extraction temporaire du bundle). L'arborescence
    attendue (voir `DocFuse-OCR.spec`) : `tesseract/tesseract.exe` +
    `tesseract/tessdata/*.traineddata` juste à côté.
    """
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass is None:
        return None
    candidate = Path(meipass) / "tesseract" / "tesseract.exe"
    return candidate if candidate.is_file() else None


@lru_cache(maxsize=1)
def _resolve_binary() -> str | None:
    """Résout le chemin du binaire Tesseract utilisable, ou `None`.

    Mis en cache : la résolution (accès disque + PATH) ne doit être refaite
    qu'une fois par exécution.
    """
    bundled = _bundled_binary_path()
    if bundled is not None:
        return str(bundled)
    return shutil.which("tesseract")


def _subprocess_env(binary: str) -> dict[str, str] | None:
    """Environnement à passer au process `tesseract`.

    Pour le binaire bundlé (variante OCR), `TESSDATA_PREFIX` est fixé
    explicitement vers le `tessdata/` embarqué à côté — on ne compte pas sur
    la détection relative par défaut de Tesseract, qui dépend du répertoire
    de travail du process appelant, imprévisible depuis un onefile
    PyInstaller (extraction dans %TEMP%). Pour une installation système
    (PATH), l'environnement hérité suffit — c'est celui que son propre
    installeur a déjà configuré.
    """
    bundled = _bundled_binary_path()
    if bundled is None or str(bundled) != binary:
        return None
    tessdata_dir = bundled.parent / "tessdata"
    env = dict(os.environ)
    env["TESSDATA_PREFIX"] = str(tessdata_dir)
    return env
