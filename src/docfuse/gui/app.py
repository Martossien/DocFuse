"""Fenêtre principale CustomTkinter (+ tkinterdnd2 en option).

CdC §6.1 — Fenêtre unique, non intimidante, redimensionnable.
CdC §2.3 — Glisser-déposer un dossier sur la fenêtre préremplit l'UI.

Historique des corrections (I-xx, M-xx, C-xx, D-xxx) : voir
`docs/journal-decisions.md`. Les fonctions sans widget vivent dans
`docfuse.gui.helpers`, le glisser-déposer dans `docfuse.gui.dnd`.
"""

from __future__ import annotations

import logging
import multiprocessing
import os
import sys
import threading
from pathlib import Path
from typing import Any

from docfuse.branding import APP_NAME
from docfuse.config import Config, load_config
from docfuse.constants import ALL_EXTENSIONS, PENDING_COLOR, STATUS_COLORS
from docfuse.core.orchestrator import (
    OrchestratorResult,
    generate_corpus,
    generate_corpus_parts,
    run_analysis,
)
from docfuse.core.progress import ProgressEmitter, ProgressEvent
from docfuse.core.report import write_report_pair
from docfuse.core.tokenizers.registry import list_engines
from docfuse.extractors.base import file_type_for
from docfuse.gui import dnd
from docfuse.gui.helpers import (
    _parse_dnd_paths,
    build_summary_lines,
    gauge_color,
    open_folder,
    parse_context_limit,
    resolve_tokenizer_choice,
    sort_file_pairs,
    widget_state,
)
from docfuse.i18n import format_number, set_language, t
from docfuse.models.file_status import FileStatus
from docfuse.models.input_selection import InputSelection
from docfuse.output.paths import corpus_extension, default_corpus_path

logger = logging.getLogger(__name__)

_LIMIT_DEBOUNCE_MS = 250
"""D-098 : délai sans frappe avant d'appliquer un nouveau plafond saisi."""

SMOKE_ENV = "DOCFUSE_GUI_SMOKE"
"""`=1` : la fenêtre se construit puis se ferme seule (`SMOKE_CLOSE_MS`) — test de fumée."""

SMOKE_CLOSE_MS = 1500


class DocFuseGUI:
    """Interface graphique principale de DocFuse."""

    def __init__(self, initial_directory: Path | None = None) -> None:
        import customtkinter as ctk

        self.config = load_config()
        # D-096 : une config incohérente (plafond ≤ 0, marge hors bornes…)
        # est signalée dans le journal et remplacée par les défauts plutôt
        # que d'alimenter silencieusement l'interface avec des valeurs
        # absurdes (`validate()` n'était jamais appelé).
        config_errors = self.config.validate()
        if config_errors:
            logger.warning("Config invalide, retour aux défauts : %s", "; ".join(config_errors))
            self.config = Config()
        set_language(self.config.lang)

        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        # C-10: glisser-déposer via tkinterdnd2 si disponible
        self.root = ctk.CTk(className="DocFuse")
        self._dnd_enabled = dnd.DND_AVAILABLE and dnd.load_tkdnd(self.root)

        self.root.title(t("app.title", app=APP_NAME))
        # D-090/D-095 : sous Windows la fenêtre démarre maximisée (rendu de
        # police et mise à l'échelle DPI imprévisibles : les boutons du bas
        # débordaient) ; ailleurs, une taille généreuse suffit.
        self.root.geometry("1050x760")
        self.root.minsize(900, 640)
        if sys.platform == "win32":
            try:
                self.root.state("zoomed")
            except Exception:
                logger.warning("Impossible de démarrer la fenêtre maximisée", exc_info=True)

        self.initial_directory = initial_directory
        self.input_selection: InputSelection | None = None
        self.result: OrchestratorResult | None = None
        self.emitter = ProgressEmitter()
        self._analysis_thread: threading.Thread | None = None
        self._analysis_error: str | None = None
        self._pending_status_labels: dict[str, Any] = {}
        self._limit_after_id: str | None = None

        self._build_ui()

    # ------------------------------------------------------------ construction
    def _build_ui(self) -> None:
        """Construit l'interface complète, de haut en bas."""
        self._build_source_frame()
        self._build_options_frame()
        self._build_analyze_bar()
        self._build_file_table()
        self._build_counter()
        self._build_bottom_bar()

    def _build_source_frame(self) -> None:
        """Haut : zone de dépôt + boutons choisir / fichiers / effacer."""
        import customtkinter as ctk

        top_frame = ctk.CTkFrame(self.root, corner_radius=10)
        top_frame.pack(fill="x", padx=15, pady=(15, 5))

        self.path_label = ctk.CTkLabel(
            top_frame,
            text=t("gui.drop_zone"),
            font=ctk.CTkFont(size=14),
            wraplength=780,
        )
        self.path_label.pack(pady=(10, 5))

        buttons_frame = ctk.CTkFrame(top_frame, fg_color="transparent")
        buttons_frame.pack(pady=(0, 10))

        self.choose_button = ctk.CTkButton(
            buttons_frame,
            text=t("gui.choose_folder"),
            command=self._choose_folder,
        )
        self.choose_button.pack(side="left", padx=5)

        self.choose_files_button = ctk.CTkButton(
            buttons_frame,
            text=t("gui.choose_files"),
            command=self._choose_files,
        )
        self.choose_files_button.pack(side="left", padx=5)

        self.clear_button = ctk.CTkButton(
            buttons_frame,
            text=t("gui.clear_selection"),
            command=self._clear_selection,
            state="disabled",
        )
        self.clear_button.pack(side="left", padx=5)

        # C-10: enregistrer le drag-and-drop si tkinterdnd2 est disponible
        if self._dnd_enabled:
            self._setup_drag_and_drop(top_frame)

    def _build_options_frame(self) -> None:
        """Options : format, plafond, sous-dossiers, images, découpage, moteur."""
        import customtkinter as ctk

        options_frame = ctk.CTkFrame(self.root, corner_radius=10)
        options_frame.pack(fill="x", padx=15, pady=5)
        for column in range(4):
            options_frame.grid_columnconfigure(column, weight=1)

        self.format_var = ctk.StringVar(value=self.config.format)
        # D-099 : le bouton « Générer corpus.md » ne suivait pas le choix PDF.
        self.format_var.trace_add("write", self._on_format_changed)
        ctk.CTkLabel(options_frame, text=t("gui.output_format")).grid(
            row=0, column=0, padx=10, pady=(10, 5), sticky="w"
        )
        ctk.CTkRadioButton(
            options_frame, text=t("gui.markdown"), variable=self.format_var, value="md"
        ).grid(row=0, column=1, padx=5, pady=(10, 5), sticky="w")
        ctk.CTkRadioButton(
            options_frame, text=t("gui.pdf"), variable=self.format_var, value="pdf"
        ).grid(row=0, column=2, padx=5, pady=(10, 5), sticky="w")

        ctk.CTkLabel(options_frame, text=t("gui.context_limit")).grid(
            row=1, column=0, padx=10, pady=5, sticky="w"
        )
        self.context_var = ctk.StringVar(value=str(self.config.context_limit))
        self.context_var.trace_add("write", self._on_context_limit_changed)
        context_entry = ctk.CTkEntry(options_frame, textvariable=self.context_var, width=80)
        context_entry.grid(row=1, column=1, padx=5, pady=5, sticky="w")
        ctk.CTkLabel(options_frame, text=t("gui.tokens_estimated"), font=ctk.CTkFont(size=11)).grid(
            row=1, column=2, padx=5, pady=5, sticky="w"
        )

        # M-14: lien « qu'est-ce que c'est ? »
        info_label = ctk.CTkLabel(
            options_frame,
            text=t("gui.what_is_context"),
            font=ctk.CTkFont(size=10, underline=True),
            text_color="#3b82f6",
            cursor="hand2",
        )
        info_label.grid(row=1, column=3, padx=5, pady=5, sticky="w")
        info_label.bind("<Button-1>", lambda _e: self._show_context_help())

        self.recursive_var = ctk.BooleanVar(value=self.config.recursive)
        ctk.CTkCheckBox(
            options_frame, text=t("gui.include_subfolders"), variable=self.recursive_var
        ).grid(row=2, column=0, columnspan=2, padx=10, pady=(5, 10), sticky="w")

        # I-12: case « Ouvrir le dossier à la fin »
        self.open_folder_var = ctk.BooleanVar(value=self.config.open_output_folder)
        ctk.CTkCheckBox(
            options_frame, text=t("gui.open_output_folder"), variable=self.open_folder_var
        ).grid(row=2, column=2, columnspan=2, padx=10, pady=(5, 10), sticky="w")

        # Moteur de comptage : "Approximation" (défaut) ou un moteur précis
        # (ex: Mistral) si disponible dans cet environnement.
        ctk.CTkLabel(options_frame, text=t("gui.tokenizer_engine")).grid(
            row=3, column=0, padx=10, pady=(5, 10), sticky="w"
        )
        self._tokenizer_label_to_id = {t(info.label_key): info.id for info in list_engines()}
        self.tokenizer_engine_var = ctk.StringVar(
            value=t(f"tokenizer.{self.config.tokenizer_engine}")
        )
        # Recalcul instantané (sans ré-extraction) si une analyse existe déjà —
        # même principe que context_var pour le plafond (I-08/I-09).
        self.tokenizer_engine_var.trace_add("write", self._on_tokenizer_engine_changed)
        ctk.CTkOptionMenu(
            options_frame,
            variable=self.tokenizer_engine_var,
            values=list(self._tokenizer_label_to_id.keys()),
        ).grid(row=3, column=1, columnspan=2, padx=5, pady=(5, 10), sticky="w")

        # D-091 : export des images intégrées DOCX/PPTX (+ tag de position) —
        # désactivé par défaut, seule fonctionnalité qui écrit des fichiers
        # en plus du corpus/rapport.
        self.extract_images_var = ctk.BooleanVar(value=self.config.extract_embedded_images)
        ctk.CTkCheckBox(
            options_frame, text=t("gui.extract_embedded_images"), variable=self.extract_images_var
        ).grid(row=4, column=0, columnspan=4, padx=10, pady=(0, 5), sticky="w")

        # D-101 : découpage en plusieurs corpus sous le plafond au lieu de
        # bloquer — recalcul instantané si une analyse existe déjà.
        self.split_context_var = ctk.BooleanVar(value=self.config.split_context)
        self.split_context_var.trace_add("write", self._on_split_context_changed)
        ctk.CTkCheckBox(
            options_frame, text=t("gui.split_context"), variable=self.split_context_var
        ).grid(row=5, column=0, columnspan=4, padx=10, pady=(0, 10), sticky="w")

    def _build_analyze_bar(self) -> None:
        """Bouton Analyser + barre et libellé de progression."""
        import customtkinter as ctk

        analyze_frame = ctk.CTkFrame(self.root, fg_color="transparent")
        analyze_frame.pack(fill="x", padx=15, pady=5)

        self.analyze_button = ctk.CTkButton(
            analyze_frame, text=t("gui.analyze"), command=self._start_analysis
        )
        self.analyze_button.pack(side="left", padx=5)

        self.analysis_progress = ctk.CTkProgressBar(analyze_frame, width=200)
        self.analysis_progress.set(0)
        self.analysis_progress.pack(side="left", padx=10)

        self.analysis_status_label = ctk.CTkLabel(analyze_frame, text="", font=ctk.CTkFont(size=11))
        self.analysis_status_label.pack(side="left", padx=5)

    def _build_file_table(self) -> None:
        """Tableau des fichiers : en-têtes triables (D-090) + lignes."""
        import customtkinter as ctk

        list_frame = ctk.CTkFrame(self.root, corner_radius=10)
        list_frame.pack(fill="both", expand=True, padx=15, pady=5)

        self.file_tree = ctk.CTkScrollableFrame(list_frame)
        self.file_tree.pack(fill="both", expand=True)

        # I-10: En-têtes du tableau avec colonne « Texte estimé »
        header_frame = ctk.CTkFrame(self.file_tree)
        header_frame.pack(fill="x")
        headers: list[tuple[str, str | None]] = [
            (t("table.file"), "file"),
            (t("table.type"), "type"),
            (t("table.text_estimated"), "text_estimated"),
            (t("table.context_margin"), "context_margin"),
            (t("table.status"), "status"),
            (t("table.actions"), None),
        ]
        self._sort_column: str | None = None
        self._sort_reverse = False
        self._header_labels: dict[str, Any] = {}
        for i, (col_text, sort_key) in enumerate(headers):
            label = ctk.CTkLabel(
                header_frame, text=col_text, font=ctk.CTkFont(size=12, weight="bold")
            )
            label.grid(row=0, column=i, padx=8, sticky="w")
            if sort_key is not None:
                label.configure(cursor="hand2")
                label.bind("<Button-1>", lambda _e, key=sort_key: self._sort_by(key))
                self._header_labels[sort_key] = (label, col_text)

        self.file_rows_frame = ctk.CTkFrame(self.file_tree)
        self.file_rows_frame.pack(fill="both", expand=True)

    def _build_counter(self) -> None:
        """Bandeau compteur (estimé / avec marge / plafond) + jauge (I-11) + résumé."""
        import customtkinter as ctk

        counter_frame = ctk.CTkFrame(self.root, corner_radius=10)
        counter_frame.pack(fill="x", padx=15, pady=5)
        for column in range(3):
            counter_frame.grid_columnconfigure(column, weight=1)

        self.estimated_label = ctk.CTkLabel(
            counter_frame,
            text=f"{t('counter.estimated')}: 0",
            font=ctk.CTkFont(size=13),
        )
        self.estimated_label.grid(row=0, column=0, padx=12, pady=10)

        self.margin_label = ctk.CTkLabel(
            counter_frame,
            text=f"{t('counter.with_margin')}: 0",
            font=ctk.CTkFont(size=13),
        )
        self.margin_label.grid(row=0, column=1, padx=12, pady=10)

        self.limit_label = ctk.CTkLabel(
            counter_frame,
            text=f"{t('counter.limit')}: {format_number(self.config.context_limit)}",
            font=ctk.CTkFont(size=13),
        )
        self.limit_label.grid(row=0, column=2, padx=12, pady=10)

        self.progress_bar = ctk.CTkProgressBar(counter_frame, progress_color=gauge_color(0.0))
        self.progress_bar.set(0)
        self.progress_bar.grid(row=1, column=0, columnspan=3, padx=12, pady=(0, 10), sticky="ew")

        self.summary_label = ctk.CTkLabel(
            self.root, text="", font=ctk.CTkFont(size=12), wraplength=700
        )
        self.summary_label.pack(pady=5)

    def _build_bottom_bar(self) -> None:
        """Bas : Générer, Rapport, Annuler."""
        import customtkinter as ctk

        bottom_frame = ctk.CTkFrame(self.root, corner_radius=10)
        bottom_frame.pack(fill="x", padx=15, pady=(5, 15))

        self.generate_button = ctk.CTkButton(
            bottom_frame,
            text=self._generate_button_text(),
            command=self._generate,
            state="disabled",
        )
        self.generate_button.pack(side="left", padx=10, pady=10)

        self.report_button = ctk.CTkButton(
            bottom_frame, text=t("gui.report"), command=self._export_report, state="disabled"
        )
        self.report_button.pack(side="left", padx=10, pady=10)

        self.stop_button = ctk.CTkButton(
            bottom_frame,
            text=t("gui.stop"),
            command=self._stop_analysis,
            state="disabled",
            fg_color="#ef4444",
        )
        self.stop_button.pack(side="right", padx=10, pady=10)

    # ------------------------------------------------------------------- état
    def _generate_button_text(self) -> str:
        return t("gui.generate", filename=f"corpus{corpus_extension(self.format_var.get())}")

    def _on_format_changed(self, *_args: str) -> None:
        button = getattr(self, "generate_button", None)
        if button is not None:
            button.configure(text=self._generate_button_text())

    def _can_generate(self) -> bool:
        return self.result is not None and bool(self.result.files) and not self.result.is_blocked

    def _is_analyzing(self) -> bool:
        return self._analysis_thread is not None and self._analysis_thread.is_alive()

    def _set_phase(self, phase: str) -> None:
        """État des boutons selon la phase : `idle` (pas de résultat),
        `analyzing` (thread en cours), `done` (résultat affiché) — D-099 : un
        seul endroit au lieu de six sites de `configure(state=...)`."""
        analyzing = phase == "analyzing"
        done = phase == "done"
        self.choose_button.configure(state=widget_state(not analyzing))
        self.choose_files_button.configure(state=widget_state(not analyzing))
        self.clear_button.configure(
            state=widget_state(not analyzing and self.input_selection is not None)
        )
        self.analyze_button.configure(state=widget_state(not analyzing))
        self.stop_button.configure(state=widget_state(analyzing))
        self.report_button.configure(state=widget_state(done))
        self.generate_button.configure(state=widget_state(done and self._can_generate()))

    def _refresh_from_result(self) -> None:
        """Ré-affiche table, compteur, résumé et boutons depuis `self.result`
        (après un recalcul de plafond, de moteur ou un retrait de fichier)."""
        self._populate_file_list()
        self._update_counter()
        self._update_summary()
        self._set_phase("done")

    def _show_context_help(self) -> None:
        """Affiche une fenêtre d'aide sur le plafond de contexte."""
        import customtkinter as ctk

        help_window = ctk.CTkToplevel(self.root)
        help_window.title(t("gui.context_limit"))
        help_window.geometry("450x250")
        help_window.resizable(False, False)

        label = ctk.CTkLabel(
            help_window, text=t("gui.help_context_text"), justify="left", font=ctk.CTkFont(size=12)
        )
        label.pack(padx=20, pady=20)

        close_button = ctk.CTkButton(help_window, text=t("gui.ok"), command=help_window.destroy)
        close_button.pack(pady=10)

    # -------------------------------------------------------------- sélection
    def _choose_folder(self) -> None:
        """Ouvre un dialogue de sélection de dossier."""
        from tkinter import filedialog

        folder = filedialog.askdirectory(initialdir=self._dialog_initial_directory())
        if folder:
            self._add_input_paths([Path(folder)])

    def _choose_files(self) -> None:
        """Ouvre un dialogue de sélection de plusieurs fichiers exacts."""
        from tkinter import filedialog

        patterns = " ".join(f"*{extension}" for extension in sorted(ALL_EXTENSIONS))
        paths = filedialog.askopenfilenames(
            initialdir=self._dialog_initial_directory(),
            filetypes=[
                (t("gui.supported_documents"), patterns),
                (t("gui.all_files"), "*.*"),
            ],
        )
        if paths:
            self._add_input_paths([Path(path) for path in paths])

    def _dialog_initial_directory(self) -> str:
        """Retourne un dossier existant et prévisible pour les dialogues natifs."""
        if self.input_selection is not None:
            candidate = self.input_selection.output_directory
        elif self.initial_directory is not None:
            candidate = self.initial_directory
        else:
            documents = Path.home() / "Documents"
            candidate = documents if documents.is_dir() else Path.home()
        return str(candidate if candidate.is_dir() else candidate.parent)

    def _clear_selection(self) -> None:
        """Efface la sélection courante et réinitialise les résultats."""
        self.input_selection = None
        self.result = None
        self.path_label.configure(text=t("gui.drop_zone"))
        self._set_phase("idle")
        self.summary_label.configure(text="")
        self.analysis_status_label.configure(text="")
        self.analysis_progress.set(0)
        self.estimated_label.configure(text=f"{t('counter.estimated')}: 0")
        self.margin_label.configure(text=f"{t('counter.with_margin')}: 0")
        self.progress_bar.set(0)
        self._clear_file_rows()

    def _clear_file_rows(self) -> None:
        for widget in self.file_rows_frame.winfo_children():
            widget.destroy()

    def _setup_drag_and_drop(self, widget: Any) -> None:
        """C-10: enregistre les événements de glisser-déposer sur un widget."""
        try:
            module = dnd.dnd_module
            if module is None or not self._dnd_enabled:
                return
            widget.drop_target_register(module.DND_FILES)
            widget.dnd_bind("<<Drop>>", self._on_drop)
            self.path_label.drop_target_register(module.DND_FILES)
            self.path_label.dnd_bind("<<Drop>>", self._on_drop)
        except Exception:
            # Si tkinterdnd2 échoue silencieusement, on continue sans DnD
            self._dnd_enabled = False
            logger.warning("Drag-and-drop non disponible, fallback sur bouton uniquement")

    def _on_drop(self, event: object) -> None:
        """C-10: callback appelé quand un fichier/dossier est déposé sur la fenêtre.

        CdC §2.3 — Dossier → racine d'entrée. Fichiers multiples → liste figée.
        """
        data = getattr(event, "data", "")
        if not data:
            return
        paths = _parse_dnd_paths(str(data))
        selected_paths = [Path(path) for path in paths]
        existing_paths = [path for path in selected_paths if path.is_file() or path.is_dir()]
        if existing_paths:
            self._add_input_paths(existing_paths)

    def _add_input_paths(self, paths: list[Path]) -> None:
        """Ajoute des sources à la sélection exacte puis relance l'analyse."""
        if self._is_analyzing():
            return
        if self.input_selection is None:
            self.input_selection = InputSelection.from_paths(paths)
        else:
            self.input_selection = self.input_selection.add(paths)
        self._update_selection_label()
        self.clear_button.configure(state="normal")
        self._start_analysis()

    def _update_selection_label(self) -> None:
        """Affiche la sélection en langage simple sans chemin trompeur."""
        if self.input_selection is None:
            self.path_label.configure(text=t("gui.drop_zone"))
            return

        paths = self.input_selection.paths
        if len(paths) == 1 and paths[0].is_dir():
            label = t("gui.selection_folder", path=str(paths[0]))
        elif len(paths) == 1:
            label = t("gui.selection_one_file", path=str(paths[0]))
        else:
            label = t("gui.selection_multiple", count=len(paths))

        removed = len(self.input_selection.excluded_files)
        if removed:
            label += " — " + t("gui.selection_removed", count=removed)
        self.path_label.configure(text=label)

    # ---------------------------------------------------------------- analyse
    def _start_analysis(self) -> None:
        """Lance l'analyse dans un thread séparé."""
        if self.input_selection is None:
            return

        selection = self.input_selection
        context_limit = self._get_current_limit()
        recursive = bool(self.recursive_var.get())
        extract_embedded_images = bool(self.extract_images_var.get())
        split_context = bool(self.split_context_var.get())
        # Lu sur le thread principal : StringVar.get() n'est pas thread-safe.
        tokenizer_engine = resolve_tokenizer_choice(
            self.tokenizer_engine_var.get(), self._tokenizer_label_to_id
        )

        self.emitter = ProgressEmitter()
        self.result = None
        self._analysis_error = None
        self._set_phase("analyzing")
        self.analysis_progress.set(0)
        self.analysis_status_label.configure(text=t("gui.analyze") + "...")
        self.summary_label.configure(text=t("gui.analysis_in_progress"))
        self._pending_status_labels.clear()
        self._clear_file_rows()

        self._analysis_thread = threading.Thread(
            target=self._run_analysis_thread,
            args=(
                selection,
                context_limit,
                recursive,
                tokenizer_engine,
                extract_embedded_images,
                split_context,
            ),
            daemon=True,
        )
        self._analysis_thread.start()

        self.root.after(100, self._poll_progress)

    def _run_analysis_thread(
        self,
        selection: InputSelection,
        context_limit: int,
        recursive: bool,
        tokenizer_engine: str,
        extract_embedded_images: bool,
        split_context: bool = False,
    ) -> None:
        """Thread d'analyse."""
        try:
            self.result = run_analysis(
                input_path=selection,
                context_limit=context_limit,
                margin=self.config.margin,  # M-10: utilise config.margin
                recursive=recursive,
                exclude_globs=self.config.exclude_globs,
                emitter=self.emitter,
                scan_config=self.config.scan,
                tokenizer_engine=tokenizer_engine,
                extract_embedded_images=extract_embedded_images,
                split_context=split_context,
            )
        except Exception as exc:
            logger.exception("Échec de l'analyse")
            self._analysis_error = str(exc)

    def _poll_progress(self) -> None:
        """Met à jour la GUI depuis les événements de progression."""
        for event in self.emitter.drain():
            self._update_file_row(event)

        if self._is_analyzing():
            self.root.after(100, self._poll_progress)
        else:
            self._analysis_complete()

    def _update_file_row(self, event: ProgressEvent) -> None:
        """Met à jour la progression pendant l'analyse (en temps réel)."""
        if event.status == "pending":
            self._add_pending_file_row(event)
            return

        progress = event.current / event.total if event.total > 0 else 0
        self.analysis_progress.set(progress)
        self.analysis_status_label.configure(
            text=f"{event.current}/{event.total} — {event.file_path}"
        )
        status_label = self._pending_status_labels.get(event.file_path)
        if status_label is not None:
            try:
                status = FileStatus(event.status)
                status_label.configure(
                    text=status.label(),
                    text_color=STATUS_COLORS.get(status.value, PENDING_COLOR),
                )
            except ValueError:
                status_label.configure(text=event.status)

    def _add_pending_file_row(self, event: ProgressEvent) -> None:
        """Affiche immédiatement un fichier inventorié avant son extraction."""
        import customtkinter as ctk

        if event.file_path in self._pending_status_labels:
            return

        row = ctk.CTkFrame(self.file_rows_frame, fg_color="transparent")
        row.pack(fill="x", pady=1)
        ctk.CTkLabel(row, text=event.file_path, anchor="w", wraplength=280).grid(
            row=0, column=0, padx=8, sticky="w"
        )
        file_type = file_type_for(Path(event.file_path)) or "—"
        ctk.CTkLabel(row, text=file_type, anchor="w").grid(row=0, column=1, padx=8, sticky="w")
        ctk.CTkLabel(row, text="—", anchor="w").grid(row=0, column=2, padx=8, sticky="w")
        ctk.CTkLabel(row, text="—", anchor="w").grid(row=0, column=3, padx=8, sticky="w")
        status_label = ctk.CTkLabel(
            row,
            text=t("status.pending"),
            text_color=PENDING_COLOR,
            anchor="w",
        )
        status_label.grid(row=0, column=4, padx=8, sticky="w")
        self._pending_status_labels[event.file_path] = status_label

    def _analysis_complete(self) -> None:
        """Appelé quand l'analyse est terminée."""
        if self.emitter.is_cancelled or (self.result is not None and self.result.cancelled):
            self.result = None
            self._set_phase("idle")
            self.analysis_progress.set(0)
            self.analysis_status_label.configure(text=t("gui.analysis_cancelled"))
            self.summary_label.configure(text=t("gui.analysis_cancelled_detail"))
            return

        if self.result is None:
            self._set_phase("idle")
            self.analysis_progress.set(0)
            self.analysis_status_label.configure(text=t("gui.analysis_failed"))
            self.summary_label.configure(
                text=t(
                    "gui.analysis_failed_detail", error=self._analysis_error or t("error.unknown")
                )
            )
            return

        self.result.recompute_blocking(self._get_current_limit())
        self.analysis_progress.set(1.0)
        self.analysis_status_label.configure(text=t("gui.analysis_done"))
        self._refresh_from_result()

    def _stop_analysis(self) -> None:
        """Arrête l'analyse en cours."""
        self.emitter.cancel()
        self.stop_button.configure(state="disabled")

    # ------------------------------------------------------------- recalculs
    def _get_current_limit(self) -> int:
        """Plafond saisi par l'utilisateur (I-09), ou celui de la config si la
        saisie est vide/invalide — même règle partout (D-099 : le blocage,
        le compteur et le résumé pouvaient lire trois valeurs différentes)."""
        return parse_context_limit(self.context_var.get(), self.config.context_limit)

    def _on_context_limit_changed(self, *_args: str) -> None:
        """Recalcule le blocage sans ré-extraire, après une courte pause de
        saisie (D-098) : la trace `write` se déclenche à chaque caractère tapé,
        et chaque déclenchement reconstruisait toute la table."""
        if self._limit_after_id is not None:
            self.root.after_cancel(self._limit_after_id)
        self._limit_after_id = self.root.after(_LIMIT_DEBOUNCE_MS, self._apply_context_limit)

    def _apply_context_limit(self) -> None:
        self._limit_after_id = None
        if self.result is None:
            return
        self.result.recompute_blocking(self._get_current_limit())
        self._refresh_from_result()

    def _on_split_context_changed(self, *_args: str) -> None:
        """Bascule du mode découpage (D-101) : recalcul du blocage sans
        ré-extraction, comme pour le plafond."""
        if self.result is None or self._is_analyzing():
            return
        self.result.split_context = bool(self.split_context_var.get())
        self.result.recompute_blocking(self._get_current_limit())
        self._refresh_from_result()

    def _on_tokenizer_engine_changed(self, *_args: str) -> None:
        """Recalcule instantanément les tokens avec le nouveau moteur, sans
        ré-extraire — sinon le tableau affichait les chiffres de l'ancien
        moteur alors que le menu affichait déjà le nouveau."""
        if self.result is None:
            return
        tokenizer_engine = resolve_tokenizer_choice(
            self.tokenizer_engine_var.get(), self._tokenizer_label_to_id
        )
        self.result.recompute_engine(tokenizer_engine)
        self._refresh_from_result()

    # -------------------------------------------------------------- affichage
    def _update_counter(self) -> None:
        """Met à jour le bandeau compteur avec le plafond en vigueur dans le
        résultat (celui qui a servi au blocage)."""
        if not self.result:
            return

        context_limit = self.result.context_limit
        self.estimated_label.configure(
            text=f"{t('counter.estimated')}: {format_number(self.result.total.tokens_estimated)}"
        )
        self.margin_label.configure(
            text=f"{t('counter.with_margin')}: {format_number(self.result.total.tokens_with_margin)}"
        )
        self.limit_label.configure(text=f"{t('counter.limit')}: {format_number(context_limit)}")

        # I-11: jauge couleur vert/orange/rouge
        ratio = self.result.total.tokens_with_margin / context_limit if context_limit > 0 else 0.0
        self.progress_bar.set(min(ratio, 1.0))
        self.progress_bar.configure(progress_color=gauge_color(ratio))

    def _sort_by(self, key: str) -> None:
        """Trie la liste des fichiers par colonne (D-090). Un second clic sur
        la même colonne inverse l'ordre — même convention qu'un tableur."""
        if self._sort_column == key:
            self._sort_reverse = not self._sort_reverse
        else:
            self._sort_column = key
            self._sort_reverse = False
        self._update_sort_indicators()
        self._populate_file_list()

    def _update_sort_indicators(self) -> None:
        """Affiche ▲/▼ sur la colonne triée, texte simple sur les autres."""
        for key, (label, base_text) in self._header_labels.items():
            if key == self._sort_column:
                arrow = " ▼" if self._sort_reverse else " ▲"
                label.configure(text=base_text + arrow)
            else:
                label.configure(text=base_text)

    def _sorted_file_pairs(self) -> list[tuple[Any, Any]]:
        """Fichiers + leur estimation, dans l'ordre d'affichage actuel."""
        assert self.result is not None
        pairs = list(zip(self.result.files, self.result.estimates, strict=False))
        return sort_file_pairs(pairs, self._sort_column, self._sort_reverse)

    def _populate_file_list(self) -> None:
        """Remplit la liste des fichiers avec colonnes CdC §6.1."""
        import customtkinter as ctk

        self._clear_file_rows()
        if not self.result:
            return

        for f, est in self._sorted_file_pairs():
            row = ctk.CTkFrame(self.file_rows_frame, fg_color="transparent")
            row.pack(fill="x", pady=1)

            ctk.CTkLabel(row, text=f.relative_path, anchor="w").grid(
                row=0, column=0, padx=8, sticky="w"
            )
            ctk.CTkLabel(row, text=f.file_type, anchor="w").grid(
                row=0, column=1, padx=8, sticky="w"
            )
            # I-10: texte estimé (tokens sans marge), puis contexte avec marge
            tokens_est = est.tokens_estimated if est is not None else 0
            ctk.CTkLabel(
                row, text=format_number(tokens_est) if tokens_est else "—", anchor="w"
            ).grid(row=0, column=2, padx=8, sticky="w")
            tokens_margin = est.tokens_with_margin if est is not None else 0
            ctk.CTkLabel(
                row, text=format_number(tokens_margin) if tokens_margin else "—", anchor="w"
            ).grid(row=0, column=3, padx=8, sticky="w")
            color = STATUS_COLORS.get(f.status.value, "#9ca3af")
            ctk.CTkLabel(row, text=f.status.label(), text_color=color, anchor="w").grid(
                row=0, column=4, padx=8, sticky="w"
            )
            ctk.CTkButton(
                row,
                text=t("table.remove"),
                width=75,
                command=lambda path=f.path: self._remove_file(path),
            ).grid(row=0, column=5, padx=8, sticky="e")

    def _remove_file(self, path: Path) -> None:
        """Retire un document du corpus et actualise le compteur sans extraction."""
        if self.result is None or self.input_selection is None:
            return
        if not self.result.remove_file(path, t("inventory.removed_by_user")):
            return
        self.input_selection = self.input_selection.exclude(path)
        self._update_selection_label()
        self._refresh_from_result()

    def _update_summary(self) -> None:
        """Met à jour le texte de résumé (I-21: conforme au CdC §6.1)."""
        if not self.result:
            return
        self.summary_label.configure(text="\n".join(build_summary_lines(self.result)))

    # ------------------------------------------------------------- génération
    def _generate(self) -> None:
        """Génère le corpus dans <App>_output/ (I-13)."""
        if not self.result or self.input_selection is None:
            return

        output_path = default_corpus_path(self.input_selection, self.format_var.get())
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # I-08: recalcul du plafond sans ré-extraction (cache mémoire)
        # Source unique de vérité : OrchestratorResult.recompute_blocking()
        self.result.recompute_blocking(self._get_current_limit())

        # D-096 : une exception ici (corpus.md verrouillé par un éditeur
        # sous Windows, dossier en lecture seule, erreur ReportLab) partait
        # dans `report_callback_exception` de Tk → stderr, inexistant dans
        # l'exe fenêtré : le clic semblait ne rien faire.
        try:
            if self.result.split_context:
                # D-101 : plusieurs fichiers `<stem>_NNN.<ext>`.
                part_paths = generate_corpus_parts(self.result, output_path)
                success = bool(part_paths)
                generated_message = t(
                    "gui.corpus_parts_generated",
                    count=len(part_paths),
                    path=str(output_path.parent),
                )
            else:
                success = generate_corpus(self.result, output_path)
                generated_message = t("gui.corpus_generated", path=str(output_path))
        except Exception as exc:
            logger.exception("Échec de la génération du corpus")
            self.summary_label.configure(text=t("gui.generation_failed_detail", error=str(exc)))
            return
        if success:
            self.summary_label.configure(text=generated_message)
            # I-12: ouvrir le dossier à la fin si demandé
            if self.open_folder_var.get():
                open_folder(output_path.parent)
        else:
            self._update_summary()

    def _export_report(self) -> None:
        """M-15: exporte le rapport avec un dialogue de sauvegarde."""
        from tkinter import filedialog

        if not self.result or self.input_selection is None:
            return

        filepath = filedialog.asksaveasfilename(
            defaultextension=".md",
            filetypes=[("Markdown", "*.md"), ("JSON", "*.json"), ("All files", "*.*")],
            initialfile="rapport.md",
        )
        if not filepath:
            return
        self.result.recompute_blocking(self._get_current_limit())
        # D-096 : `rapport.json` choisi ici écrasait le Markdown ;
        # `write_report_pair` écrit toujours `.md` ET `.json`.
        try:
            md_rp, _json_rp = write_report_pair(self.result, Path(filepath))
        except Exception as exc:
            logger.exception("Échec de l'export du rapport")
            self.summary_label.configure(text=t("gui.generation_failed_detail", error=str(exc)))
            return
        self.summary_label.configure(text=t("gui.report_exported", path=str(md_rp)))

    def run(self) -> None:
        """Lance la boucle principale."""
        self.root.mainloop()


def launch() -> None:
    """Lance la GUI.

    D-105/D-106 : c'est ici — point d'entrée applicatif — qu'est posée la
    politique d'avertissements, et non à l'import d'`extractors/xlsx.py`
    (effet de bord sur le processus hôte, sans opt-out possible).

    `DOCFUSE_GUI_SMOKE=1` : la fenêtre complète est construite puis fermée
    d'elle-même après `SMOKE_CLOSE_MS` — c'est le test de fumée de l'exécutable
    empaqueté (CI), qui prouve que Tk, CustomTkinter et tkdnd sont embarqués.
    """
    multiprocessing.freeze_support()  # D-111 : travailleurs du pool dans l'exe
    from docfuse.extractors.xlsx import silence_openpyxl_warnings

    silence_openpyxl_warnings()
    gui = DocFuseGUI()
    if os.environ.get(SMOKE_ENV) == "1":
        gui.root.after(SMOKE_CLOSE_MS, gui.root.destroy)
    gui.run()
