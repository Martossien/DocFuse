"""Fenêtre principale (`docfuse.gui.app`) construite **sans Tk** : une doublure de
`customtkinter` fabrique des widgets inertes qui mémorisent leurs options.

Ce que ces tests attrapent : une faute dans la construction (attribut manquant,
widget renommé), un bouton oublié dans `_set_phase`, une table qui ne suit plus
le résultat, une génération qui n'écrit pas — sans écran, donc sous la CI Linux.
Le smoke de l'exe (`DOCFUSE_GUI_SMOKE=1`) reste le seul test avec un vrai Tk.
"""

from __future__ import annotations

import sys
import types
from pathlib import Path
from typing import Any

import pytest

from docfuse.config import Config
from docfuse.i18n import t


class _Widget:
    """Widget inerte : options, enfants, valeur ; toute autre méthode est un no-op."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self.options: dict[str, Any] = dict(kwargs)
        self.children: list[_Widget] = []
        self.value: Any = None
        parent = args[0] if args else None
        if isinstance(parent, _Widget):
            parent.children.append(self)
        self.parent = parent

    def configure(self, **kwargs: Any) -> None:
        self.options.update(kwargs)

    def cget(self, key: str) -> Any:
        return self.options.get(key)

    def set(self, value: Any) -> None:
        self.value = value

    def get(self) -> Any:
        return self.value

    def winfo_children(self) -> list[_Widget]:
        return list(self.children)

    def destroy(self) -> None:
        if isinstance(self.parent, _Widget) and self in self.parent.children:
            self.parent.children.remove(self)

    def __getattr__(self, name: str) -> Any:
        return lambda *a, **k: None


class _Root(_Widget):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.scheduled: list[tuple[int, Any]] = []

    def after(self, ms: int, callback: Any) -> str:
        self.scheduled.append((ms, callback))
        return f"after#{len(self.scheduled)}"

    def after_cancel(self, _ident: str) -> None:
        pass


class _Var:
    def __init__(self, value: Any = None, **_k: Any) -> None:
        self._value = value
        self._traces: list[Any] = []

    def get(self) -> Any:
        return self._value

    def set(self, value: Any) -> None:
        self._value = value
        for callback in self._traces:
            callback()

    def trace_add(self, _mode: str, callback: Any) -> None:
        self._traces.append(callback)


def _fake_ctk() -> Any:
    module = types.ModuleType("customtkinter")
    module.__getattr__ = lambda _name: _Widget  # type: ignore[attr-defined]
    module.CTk = _Root  # type: ignore[attr-defined]
    module.StringVar = _Var  # type: ignore[attr-defined]
    module.BooleanVar = _Var  # type: ignore[attr-defined]
    module.CTkFont = lambda **k: k  # type: ignore[attr-defined]
    module.set_appearance_mode = lambda *_a: None  # type: ignore[attr-defined]
    module.set_default_color_theme = lambda *_a: None  # type: ignore[attr-defined]
    return module


@pytest.fixture
def gui(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Any:
    monkeypatch.setitem(sys.modules, "customtkinter", _fake_ctk())
    from docfuse.gui import app as app_module
    from docfuse.gui import dnd

    monkeypatch.setattr(dnd, "DND_AVAILABLE", False)
    monkeypatch.setattr(app_module, "load_config", lambda: Config())
    return app_module.DocFuseGUI(initial_directory=tmp_path)


def _corpus_dir(tmp_path: Path, files: int = 2) -> Path:
    src = tmp_path / "docs"
    src.mkdir()
    for i in range(files):
        (src / f"note{i}.txt").write_text(f"Contenu du document {i}. " * 40, encoding="utf-8")
    return src


def _analyse(gui: Any, source: Path) -> None:
    """Sélection + analyse, en attendant le thread au lieu de `after(100, _poll_progress)`."""
    gui._add_input_paths([source])
    assert gui._analysis_thread is not None
    gui._analysis_thread.join(timeout=60)
    gui._poll_progress()  # thread fini : draine la progression puis `_analysis_complete`


def test_phases_des_boutons(gui: Any) -> None:
    gui._set_phase("analyzing")
    assert gui.analyze_button.options["state"] == "disabled"
    assert gui.stop_button.options["state"] == "normal"
    assert gui.generate_button.options["state"] == "disabled"
    gui._set_phase("idle")
    assert gui.analyze_button.options["state"] == "normal"
    assert gui.stop_button.options["state"] == "disabled"
    assert gui.report_button.options["state"] == "disabled"


def test_analyse_remplit_la_table_et_arme_la_generation(gui: Any, tmp_path: Path) -> None:
    source = _corpus_dir(tmp_path, files=3)
    _analyse(gui, source)
    assert gui.result is not None
    assert len(gui.result.files) == 3
    assert len(gui.file_rows_frame.winfo_children()) == 3
    assert gui.generate_button.options["state"] == "normal"
    assert gui.analysis_status_label.options["text"] == t("gui.analysis_done")
    assert t("counter.estimated") in gui.estimated_label.options["text"]
    assert gui.summary_label.options["text"]  # résumé non vide


def test_retrait_d_un_fichier_actualise_table_et_selection(gui: Any, tmp_path: Path) -> None:
    source = _corpus_dir(tmp_path, files=2)
    _analyse(gui, source)
    assert gui.result is not None
    first = gui.result.files[0].path
    row = gui.file_rows_frame.winfo_children()[0]
    remove_button = row.winfo_children()[-1]
    remove_button.options["command"]()  # clic sur « Retirer »
    assert len(gui.file_rows_frame.winfo_children()) == 1
    assert gui.input_selection is not None
    assert first in gui.input_selection.excluded_files
    assert t("gui.selection_removed", count=1) in gui.path_label.options["text"]


def test_tri_par_colonne_et_indicateur(gui: Any, tmp_path: Path) -> None:
    _analyse(gui, _corpus_dir(tmp_path, files=2))
    gui._sort_by("file")
    assert gui._sort_column == "file"
    assert gui._sort_reverse is False
    gui._sort_by("file")
    assert gui._sort_reverse is True
    label, base = gui._header_labels["file"]
    assert label.options["text"] == base + " ▼"


def test_plafond_saisi_bloque_sans_reextraire(gui: Any, tmp_path: Path) -> None:
    _analyse(gui, _corpus_dir(tmp_path, files=2))
    gui.context_var.set("1")  # trace → `after(250, _apply_context_limit)`
    assert gui.root.scheduled[-1][1] == gui._apply_context_limit
    gui._apply_context_limit()
    assert gui.result is not None
    assert gui.result.is_blocked
    assert gui.generate_button.options["state"] == "disabled"
    assert gui.result.block_reason in gui.summary_label.options["text"]
    gui.split_context_var.set(True)  # D-101 : le découpage lève le blocage
    assert not gui.result.is_blocked
    assert gui.generate_button.options["state"] == "normal"


def test_format_pdf_change_le_bouton_generer(gui: Any) -> None:
    gui.format_var.set("pdf")
    assert gui.generate_button.options["text"].endswith("corpus.pdf")


def test_generation_ecrit_le_corpus_et_le_rapport(gui: Any, tmp_path: Path) -> None:
    source = _corpus_dir(tmp_path, files=2)
    _analyse(gui, source)
    gui.open_folder_var.set(False)
    gui._generate()
    written = list(source.parent.rglob("corpus.md"))
    assert written, "corpus.md attendu dans <App>_output/"
    assert str(written[0]) in gui.summary_label.options["text"]


def test_echec_d_analyse_affiche_la_cause(
    gui: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from docfuse.gui import app as app_module

    def casse(**_k: Any) -> Any:
        raise RuntimeError("disque arraché")

    monkeypatch.setattr(app_module, "run_analysis", casse)
    _analyse(gui, _corpus_dir(tmp_path))
    assert gui.result is None
    assert gui.analysis_status_label.options["text"] == t("gui.analysis_failed")
    assert "disque arraché" in gui.summary_label.options["text"]
    assert gui.analyze_button.options["state"] == "normal"


def test_annulation_remet_l_ecran_au_repos(gui: Any, tmp_path: Path) -> None:
    _analyse(gui, _corpus_dir(tmp_path))
    gui.emitter.cancel()
    gui._analysis_complete()
    assert gui.result is None
    assert gui.analysis_status_label.options["text"] == t("gui.analysis_cancelled")


def test_effacer_la_selection_remet_tout_a_zero(gui: Any, tmp_path: Path) -> None:
    _analyse(gui, _corpus_dir(tmp_path))
    gui._clear_selection()
    assert gui.result is None
    assert gui.input_selection is None
    assert gui.file_rows_frame.winfo_children() == []
    assert gui.path_label.options["text"] == t("gui.drop_zone")
    assert gui.clear_button.options["state"] == "disabled"


def test_depot_de_chemins_lance_l_analyse(gui: Any, tmp_path: Path) -> None:
    source = _corpus_dir(tmp_path)
    event = types.SimpleNamespace(data=f"{{{source}}} {tmp_path / 'absent.txt'}")
    gui._on_drop(event)
    assert gui._analysis_thread is not None
    gui._analysis_thread.join(timeout=60)
    gui._poll_progress()
    assert gui.result is not None
    assert len(gui.result.files) == 2
