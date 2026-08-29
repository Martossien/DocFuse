"""Interface graphique avec CustomTkinter + tkinterdnd2.

CdC §6.1 — Fenêtre unique, non intimidante, ~900×640, redimensionnable.
CdC §2.3 — Glisser-déposer un dossier sur la fenêtre préremplit l'UI.
GUI user-friendly : zone de dépôt, liste fichiers, compteur couleur, boutons.

Corrections Session 3 :
- I-08/I-09 : recalcul du plafond sans ré-extraction (cache mémoire)
- I-10 : colonne « Texte estimé » ajoutée
- I-11 : jauge couleur vert/orange/rouge
- I-12 : case « Ouvrir le dossier à la fin »
- I-13 : sortie dans CorpusOne_output/
- I-21 : message de blocage conforme au CdC
- M-10 : utilise config.margin au lieu de DEFAULT_MARGIN
- M-13 : bouton « Changer »
- M-14 : lien « qu'est-ce que c'est ? »
- M-15 : export rapport fonctionnel (save dialog)

Session 5 :
- C-10 : glisser-déposer GUI via tkinterdnd2 (MIT)
"""

from __future__ import annotations

import logging
import subprocess
import sys
import threading
from pathlib import Path
from typing import Any

from docfuse.config import load_config
from docfuse.constants import ALL_EXTENSIONS, DEFAULT_TOKENIZER_ENGINE, STATUS_COLORS
from docfuse.core.orchestrator import OrchestratorResult, generate_corpus, run_analysis
from docfuse.core.progress import ProgressEmitter, ProgressEvent
from docfuse.core.tokenizers.registry import list_engines
from docfuse.i18n import format_number, set_language, t
from docfuse.models.file_status import FileStatus
from docfuse.models.input_selection import InputSelection

logger = logging.getLogger(__name__)


def _try_import_dnd() -> tuple[bool, Any]:
    """Tente d'importer tkinterdnd2. Retourne (disponible, module ou None)."""
    try:
        import tkinterdnd2

        return True, tkinterdnd2
    except ImportError:
        return False, None


_DND_AVAILABLE, _dnd_mod = _try_import_dnd()


class DocFuseGUI:
    """Interface graphique principale de DocFuse."""

    def __init__(self, initial_directory: Path | None = None) -> None:
        import customtkinter as ctk

        self.config = load_config()
        set_language(self.config.lang)

        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        # C-10: glisser-déposer via tkinterdnd2 si disponible
        self.root = ctk.CTk(className="DocFuse")
        self._dnd_enabled = _DND_AVAILABLE

        self.root.title(t("app.title"))
        # D-090 : à 900x720 (minsize 700x600), les boutons du bas (Générer,
        # Rapport, Annuler) débordaient de la fenêtre sous Windows au premier
        # lancement — rendu de police (Segoe UI) plus large que sur Linux, et
        # `pack(side=...)` ne fait jamais passer les boutons à la ligne : un
        # débordement horizontal les pousse simplement hors de la zone
        # visible plutôt que de les redimensionner. Marge généreuse.
        # D-095 : confirmé par l'utilisateur sur machine Windows réelle (v0.1.5)
        # que les 3 boutons du bas restent masqués une fois des fichiers
        # chargés — cause supplémentaire identifiée : D-091 a ajouté une 5e
        # ligne à `options_frame` (case « Exporter les images intégrées »),
        # qui n'existait pas quand la hauteur 720 a été choisie en D-090 ;
        # hauteur augmentée d'autant (+40 px) pour compenser. Mais reproduit
        # même en chargeant 59 fichiers réels dans cette session (Linux,
        # `file_rows_frame` bien confiné dans le `CTkScrollableFrame`
        # attendu, boutons toujours visibles) — non reproduit ici malgré un
        # test ciblé, très probablement une histoire de mise à l'échelle
        # DPI/police Windows qui agrandit chaque ligne au-delà de ce qui
        # tient sur l'écran réel de l'utilisateur. Plutôt que deviner une
        # nouvelle valeur de pixels, la fenêtre démarre maximisée sous
        # Windows (voir plus bas) : utilise tout l'espace écran disponible
        # au lieu d'un pari sur une hauteur fixe.
        self.root.geometry("1050x760")
        self.root.minsize(900, 640)
        if sys.platform == "win32":
            # D-095 : `state("zoomed")` est l'idiome Tk standard pour démarrer
            # maximisé sous Windows — jamais utilisé ici (comportement
            # inchangé) pour ne pas modifier l'expérience Linux/macOS déjà
            # vérifiée. `try/except` : ne doit jamais empêcher le lancement
            # de la GUI si l'appel échoue pour une raison quelconque.
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

        self._build_ui()

    def _build_ui(self) -> None:
        """Construit l'interface complète."""
        import customtkinter as ctk

        # ─── Haut : zone de dépôt + boutons choisir/changer ───
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

        # ─── Options ───
        options_frame = ctk.CTkFrame(self.root, corner_radius=10)
        options_frame.pack(fill="x", padx=15, pady=5)
        for column in range(4):
            options_frame.grid_columnconfigure(column, weight=1)

        self.format_var = ctk.StringVar(value=self.config.format)
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

        # D-091 : export des images intégrées DOCX/PPTX (+ tag de position) —
        # désactivé par défaut, seule fonctionnalité qui écrit des fichiers
        # en plus du corpus/rapport.
        self.extract_images_var = ctk.BooleanVar(value=self.config.extract_embedded_images)
        ctk.CTkCheckBox(
            options_frame, text=t("gui.extract_embedded_images"), variable=self.extract_images_var
        ).grid(row=4, column=0, columnspan=4, padx=10, pady=(0, 10), sticky="w")

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

        # ─── Bouton Analyser + barre de progression ───
        analyze_frame = ctk.CTkFrame(self.root, fg_color="transparent")
        analyze_frame.pack(fill="x", padx=15, pady=5)

        self.analyze_button = ctk.CTkButton(
            analyze_frame, text=t("gui.analyze"), command=self._start_analysis
        )
        self.analyze_button.pack(side="left", padx=5)

        # Indicateur de progression pendant l'analyse
        self.analysis_progress = ctk.CTkProgressBar(analyze_frame, width=200)
        self.analysis_progress.set(0)
        self.analysis_progress.pack(side="left", padx=10)

        # Label de statut pendant l'analyse
        self.analysis_status_label = ctk.CTkLabel(analyze_frame, text="", font=ctk.CTkFont(size=11))
        self.analysis_status_label.pack(side="left", padx=5)

        # ─── Liste fichiers (tableau) ───
        list_frame = ctk.CTkFrame(self.root, corner_radius=10)
        list_frame.pack(fill="both", expand=True, padx=15, pady=5)

        self.file_tree = ctk.CTkScrollableFrame(list_frame)
        self.file_tree.pack(fill="both", expand=True)

        # I-10: En-têtes du tableau avec colonne « Texte estimé »
        # D-090 : en-têtes cliquables pour trier (nom de fichier n'est pas
        # forcément l'ordre le plus utile une fois le dossier volumineux).
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

        # ─── Bandeau compteur ───
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

        # I-11: jauge couleur vert/orange/rouge
        self.progress_bar = ctk.CTkProgressBar(counter_frame, progress_color="#22c55e")
        self.progress_bar.set(0)
        self.progress_bar.grid(row=1, column=0, columnspan=3, padx=12, pady=(0, 10), sticky="ew")

        # ─── Résumé ───
        self.summary_label = ctk.CTkLabel(
            self.root, text="", font=ctk.CTkFont(size=12), wraplength=700
        )
        self.summary_label.pack(pady=5)

        # ─── Bas : boutons ───
        bottom_frame = ctk.CTkFrame(self.root, corner_radius=10)
        bottom_frame.pack(fill="x", padx=15, pady=(5, 15))

        self.generate_button = ctk.CTkButton(
            bottom_frame,
            text=t("gui.generate", filename="corpus.md"),
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

    def _show_context_help(self) -> None:
        """Affiche une fenêtre d'aide sur le plafond de contexte."""
        import customtkinter as ctk

        help_window = ctk.CTkToplevel(self.root)
        help_window.title(t("gui.context_limit"))
        help_window.geometry("450x250")
        help_window.resizable(False, False)

        text = t("gui.help_context_text")

        label = ctk.CTkLabel(help_window, text=text, justify="left", font=ctk.CTkFont(size=12))
        label.pack(padx=20, pady=20)

        close_button = ctk.CTkButton(help_window, text=t("gui.ok"), command=help_window.destroy)
        close_button.pack(pady=10)

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
        self.clear_button.configure(state="disabled")
        self.generate_button.configure(state="disabled")
        self.report_button.configure(state="disabled")
        self.summary_label.configure(text="")
        self.analysis_status_label.configure(text="")
        self.analysis_progress.set(0)
        self.estimated_label.configure(text=f"{t('counter.estimated')}: 0")
        self.margin_label.configure(text=f"{t('counter.with_margin')}: 0")
        self.progress_bar.set(0)
        for widget in self.file_rows_frame.winfo_children():
            widget.destroy()

    def _setup_drag_and_drop(self, widget: Any) -> None:
        """C-10: enregistre les événements de glisser-déposer sur un widget."""
        try:
            dnd = _dnd_mod
            if dnd is None:
                return

            widget.drop_target_register(dnd.DND_FILES)
            widget.dnd_bind("<<Drop>>", self._on_drop)
            self.path_label.drop_target_register(dnd.DND_FILES)
            self.path_label.dnd_bind("<<Drop>>", self._on_drop)
        except Exception:
            # Si tkinterdnd2 échoue silencieusement, on continue sans DnD
            self._dnd_enabled = False
            logger.warning("Drag-and-drop non disponible, fallback sur bouton uniquement")

    def _on_drop(self, event: object) -> None:
        """C-10: callback appelé quand un fichier/dossier est déposé sur la fenêtre.

        CdC §2.3 — Dossier → racine d'entrée. Fichiers multiples → liste figée.
        """
        # tkinterdnd2 event.data contient les chemins déposés
        data = getattr(event, "data", "")
        if not data:
            return

        # Les chemins peuvent être entre accolades si contenant des espaces
        paths = _parse_dnd_paths(str(data))
        if not paths:
            return

        selected_paths = [Path(path) for path in paths]
        existing_paths = [path for path in selected_paths if path.is_file() or path.is_dir()]
        if existing_paths:
            self._add_input_paths(existing_paths)

    def _add_input_paths(self, paths: list[Path]) -> None:
        """Ajoute des sources à la sélection exacte puis relance l'analyse."""

        if self._analysis_thread is not None and self._analysis_thread.is_alive():
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

    def _start_analysis(self) -> None:
        """Lance l'analyse dans un thread séparé."""
        if self.input_selection is None:
            return

        selection = self.input_selection
        context_limit = self._get_current_limit()
        recursive = bool(self.recursive_var.get())
        extract_embedded_images = bool(self.extract_images_var.get())
        # Lu sur le thread principal : StringVar.get() n'est pas thread-safe.
        tokenizer_engine = resolve_tokenizer_choice(
            self.tokenizer_engine_var.get(), self._tokenizer_label_to_id
        )

        self.emitter = ProgressEmitter()
        self.result = None
        self._analysis_error = None
        self.choose_button.configure(state="disabled")
        self.choose_files_button.configure(state="disabled")
        self.clear_button.configure(state="disabled")
        self.analyze_button.configure(state="disabled")
        self.generate_button.configure(state="disabled")
        self.report_button.configure(state="disabled")
        self.stop_button.configure(state="normal")
        self.analysis_progress.set(0)
        self.analysis_status_label.configure(text=t("gui.analyze") + "...")
        self.summary_label.configure(text=t("gui.analysis_in_progress"))
        self._pending_status_labels.clear()
        for widget in self.file_rows_frame.winfo_children():
            widget.destroy()

        self._analysis_thread = threading.Thread(
            target=self._run_analysis_thread,
            args=(selection, context_limit, recursive, tokenizer_engine, extract_embedded_images),
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
            )
        except Exception as exc:
            logger.exception("Échec de l'analyse")
            self._analysis_error = str(exc)

    def _poll_progress(self) -> None:
        """Met à jour la GUI depuis les événements de progression."""
        for event in self.emitter.drain():
            self._update_file_row(event)

        if self._analysis_thread and self._analysis_thread.is_alive():
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
                    text_color=STATUS_COLORS.get(status.value, "#9ca3af"),
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
        file_type = Path(event.file_path).suffix.lower().lstrip(".") or "—"
        ctk.CTkLabel(row, text=file_type, anchor="w").grid(row=0, column=1, padx=8, sticky="w")
        ctk.CTkLabel(row, text="—", anchor="w").grid(row=0, column=2, padx=8, sticky="w")
        ctk.CTkLabel(row, text="—", anchor="w").grid(row=0, column=3, padx=8, sticky="w")
        status_label = ctk.CTkLabel(
            row,
            text=t("status.pending"),
            text_color="#9ca3af",
            anchor="w",
        )
        status_label.grid(row=0, column=4, padx=8, sticky="w")
        self._pending_status_labels[event.file_path] = status_label

    def _analysis_complete(self) -> None:
        """Appelé quand l'analyse est terminée."""
        self.choose_button.configure(state="normal")
        self.choose_files_button.configure(state="normal")
        self.clear_button.configure(state="normal" if self.input_selection else "disabled")
        self.analyze_button.configure(state="normal")
        self.stop_button.configure(state="disabled")

        if self.emitter.is_cancelled:
            self.result = None
            self.analysis_progress.set(0)
            self.analysis_status_label.configure(text=t("gui.analysis_cancelled"))
            self.summary_label.configure(text=t("gui.analysis_cancelled_detail"))
            return

        if self.result is None:
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

        self._populate_file_list()
        self._update_counter()

        # Résumé
        self._update_summary()

        # Bouton générer
        if self.result.is_blocked or not self.result.files:
            self.generate_button.configure(state="disabled")
        else:
            self.generate_button.configure(state="normal")

        self.report_button.configure(state="normal")

    def _get_current_limit(self) -> int:
        """Récupère la valeur du plafond éditée par l'utilisateur (I-09)."""
        try:
            value = int(self.context_var.get())
            return value if value > 0 else self.config.context_limit
        except ValueError:
            return self.config.context_limit

    def _on_context_limit_changed(self, *_args: str) -> None:
        """Recalcule instantanément le blocage sans ré-extraire les documents."""

        if self.result is None:
            return
        try:
            context_limit = int(self.context_var.get())
        except ValueError:
            return
        if context_limit <= 0:
            return

        self.result.recompute_blocking(context_limit)
        self._populate_file_list()
        self._update_counter()
        self._update_summary()
        state = "normal" if self.result.files and not self.result.is_blocked else "disabled"
        self.generate_button.configure(state=state)

    def _on_tokenizer_engine_changed(self, *_args: str) -> None:
        """Recalcule instantanément les tokens avec le nouveau moteur, sans ré-extraire.

        Sans ça, changer le menu après une analyse laissait le tableau affiché
        avec les chiffres de l'ancien moteur alors que le menu affichait déjà
        le nouveau — trompeur, pas juste périmé.
        """
        if self.result is None:
            return

        tokenizer_engine = resolve_tokenizer_choice(
            self.tokenizer_engine_var.get(), self._tokenizer_label_to_id
        )
        self.result.recompute_engine(tokenizer_engine)
        self._populate_file_list()
        self._update_counter()
        self._update_summary()
        state = "normal" if self.result.files and not self.result.is_blocked else "disabled"
        self.generate_button.configure(state=state)

    def _update_counter(self) -> None:
        """Met à jour le bandeau compteur avec la valeur éditée du plafond."""
        if not self.result:
            return

        context_limit = self._get_current_limit()

        self.estimated_label.configure(
            text=f"{t('counter.estimated')}: {format_number(self.result.total.tokens_estimated)}"
        )
        self.margin_label.configure(
            text=f"{t('counter.with_margin')}: {format_number(self.result.total.tokens_with_margin)}"
        )
        self.limit_label.configure(text=f"{t('counter.limit')}: {format_number(context_limit)}")

        # I-11: jauge couleur vert/orange/rouge
        progress = self.result.total.tokens_with_margin / context_limit if context_limit > 0 else 0
        self.progress_bar.set(min(progress, 1.0))

        if progress >= 1.0:
            self.progress_bar.configure(progress_color="#ef4444")  # rouge
        elif progress >= 0.8:
            self.progress_bar.configure(progress_color="#f97316")  # orange
        else:
            self.progress_bar.configure(progress_color="#22c55e")  # vert

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

        for widget in self.file_rows_frame.winfo_children():
            widget.destroy()

        if not self.result:
            return

        for f, est in self._sorted_file_pairs():
            row = ctk.CTkFrame(self.file_rows_frame, fg_color="transparent")
            row.pack(fill="x", pady=1)

            # Colonne 0: Fichier
            ctk.CTkLabel(row, text=f.relative_path, anchor="w").grid(
                row=0, column=0, padx=8, sticky="w"
            )
            # Colonne 1: Type
            ctk.CTkLabel(row, text=f.file_type, anchor="w").grid(
                row=0, column=1, padx=8, sticky="w"
            )
            # I-10: Colonne 2: Texte estimé (tokens sans marge)
            tokens_est = est.tokens_estimated if est is not None else 0
            ctk.CTkLabel(
                row, text=format_number(tokens_est) if tokens_est else "—", anchor="w"
            ).grid(row=0, column=2, padx=8, sticky="w")
            # Colonne 3: Contexte +15%
            tokens_margin = est.tokens_with_margin if est is not None else 0
            ctk.CTkLabel(
                row, text=format_number(tokens_margin) if tokens_margin else "—", anchor="w"
            ).grid(row=0, column=3, padx=8, sticky="w")
            # Colonne 4: Statut
            status_text = f.status.label()
            color = STATUS_COLORS.get(f.status.value, "#9ca3af")
            ctk.CTkLabel(row, text=status_text, text_color=color, anchor="w").grid(
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

        reason = t("inventory.removed_by_user")
        if not self.result.remove_file(path, reason):
            return

        self.input_selection = self.input_selection.exclude(path)
        self._update_selection_label()
        self._populate_file_list()
        self._update_counter()
        self._update_summary()
        state = "normal" if self.result.files and not self.result.is_blocked else "disabled"
        self.generate_button.configure(state=state)

    def _update_summary(self) -> None:
        """Met à jour le texte de résumé (I-21: conforme au CdC §6.1)."""
        if not self.result:
            return

        images_count = self.result.count_base_status(FileStatus.IMAGES)
        low_text_count = self.result.count_base_status(FileStatus.LOW_TEXT)
        ready_count = self.result.count_base_status(FileStatus.READY)
        context_limit = self._get_current_limit()

        parts: list[str] = []

        if ready_count > 0 and not self.result.is_blocked:
            parts.append(t("summary.ok", count=ready_count, limit=format_number(context_limit)))

        if images_count > 0:
            parts.append(t("summary.images", count=images_count))

        if low_text_count > 0:
            parts.append(t("summary.low_text", count=low_text_count))

        # I-21: message de blocage conforme au CdC
        if self.result.is_blocked:
            if self.result.blocking_files:
                worst = self.result.blocking_files[0]
                worst_idx = self.result.files.index(worst)
                worst_tokens = self.result.estimates[worst_idx].tokens_with_margin
                parts.append(
                    t(
                        "summary.blocked_file",
                        file=worst.relative_path,
                        tokens=format_number(worst_tokens),
                        limit=format_number(context_limit),
                    )
                )
            elif self.result.block_reason:
                parts.append(
                    t(
                        "summary.blocked_total",
                        total=format_number(self.result.total.tokens_with_margin),
                        limit=format_number(context_limit),
                    )
                )

        self.summary_label.configure(text="\n".join(parts))

    def _generate(self) -> None:
        """Génère le corpus dans CorpusOne_output/ (I-13)."""
        if not self.result or self.input_selection is None:
            return

        ext = ".md" if self.format_var.get() == "md" else ".pdf"
        # I-13: sortie dans CorpusOne_output/
        output_dir = self.input_selection.output_directory / "CorpusOne_output"
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / f"corpus{ext}"

        context_limit = self._get_current_limit()

        # I-08: recalcul du plafond sans ré-extraction (cache mémoire)
        # Source unique de vérité : OrchestratorResult.recompute_blocking()
        self.result.recompute_blocking(context_limit)

        success = generate_corpus(self.result, output_path, context_limit, self.config.margin)
        if success:
            self.summary_label.configure(text=t("gui.corpus_generated", path=str(output_path)))
            # I-12: ouvrir le dossier à la fin si demandé
            if self.open_folder_var.get():
                _open_folder(output_dir)
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
        if filepath:
            from docfuse.core.report import generate_json_report, generate_markdown_report

            rp = Path(filepath)
            context_limit = self._get_current_limit()
            generate_markdown_report(
                self.result.files,
                self.result.ignored,
                context_limit,
                self.config.margin,
                self.result.total.tokens_estimated,
                self.result.total.tokens_with_margin,
                rp,
                estimates=self.result.estimates,
                engine_id=self.result.engine_id,
            )
            json_rp = rp.with_suffix(".json")
            generate_json_report(
                self.result.files,
                self.result.ignored,
                context_limit,
                self.config.margin,
                self.result.total.tokens_estimated,
                self.result.total.tokens_with_margin,
                json_rp,
                estimates=self.result.estimates,
                engine_id=self.result.engine_id,
            )
            self.summary_label.configure(text=t("gui.report_exported", path=str(rp)))

    def _stop_analysis(self) -> None:
        """Arrête l'analyse en cours."""
        self.emitter.cancel()
        self.stop_button.configure(state="disabled")

    def run(self) -> None:
        """Lance la boucle principale."""
        self.root.mainloop()


def _sort_key_for_column(pair: tuple[Any, Any], column: str) -> Any:
    """Valeur de tri pour une colonne du tableau de fichiers (D-090)."""
    f, est = pair
    if column == "file":
        return f.relative_path.lower()
    if column == "type":
        return f.file_type.lower()
    if column == "text_estimated":
        return est.tokens_estimated if est is not None else 0
    if column == "context_margin":
        return est.tokens_with_margin if est is not None else 0
    if column == "status":
        # Sévérité (0 = ready), pas le libellé traduit : "Peu de texte"
        # doit se regrouper avec "Images"/"Erreur", pas se ranger avec un
        # tri alphabétique arbitraire du texte affiché.
        return f.status.severity
    return 0


def sort_file_pairs(
    pairs: list[tuple[Any, Any]], column: str | None, reverse: bool
) -> list[tuple[Any, Any]]:
    """Trie des paires (ExtractedFile, TokenEstimate) pour l'affichage GUI (D-090).

    Fonction pure (testable sans ouvrir de fenêtre), même esprit que
    `resolve_tokenizer_choice`. `column=None` (pas encore trié par
    l'utilisateur) renvoie l'ordre reçu tel quel — ordre natural du dossier.
    """
    if column is None:
        return pairs
    return sorted(pairs, key=lambda pair: _sort_key_for_column(pair, column), reverse=reverse)


def resolve_tokenizer_choice(label: str, label_to_id: dict[str, str]) -> str:
    """Traduit le libellé affiché dans le menu déroulant vers l'id du moteur.

    Fonction pure (testable sans ouvrir de fenêtre) : un libellé inconnu
    (ex: langue changée entre-temps) retombe sur l'approximation par défaut
    plutôt que de faire planter l'analyse.
    """
    return label_to_id.get(label, DEFAULT_TOKENIZER_ENGINE)


def _parse_dnd_paths(data: str) -> list[str]:
    """Parse les chemins déposés depuis l'événement DnD de tkinterdnd2.

    Les chemins avec espaces sont entre accolades : {C:\\My Path\\file.txt}
    Les chemins sans espaces sont séparés par des espaces.
    """
    paths: list[str] = []
    import re

    # Chercher les chemins entre accolades {path with spaces}
    brace_pattern = re.compile(r"\{([^}]+)\}")
    brace_matches = brace_pattern.findall(data)

    if brace_matches:
        paths.extend(brace_matches)
        # Retirer les matches du data pour les chemins restants
        remaining = brace_pattern.sub("", data).strip()
        if remaining:
            paths.extend(remaining.split())
    else:
        # Pas d'accolades — split par espaces
        parts = data.strip().split()
        paths.extend(parts)

    return [p for p in paths if p]


def _open_folder(path: Path) -> None:
    """Ouvre un dossier dans l'explorateur de fichiers (multi-plateforme)."""
    try:
        if sys.platform == "win32":
            subprocess.Popen(["explorer", str(path)])
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(path)])
        else:
            subprocess.Popen(["xdg-open", str(path)])
    except Exception:
        logger.warning("Impossible d'ouvrir le dossier: %s", path)


def launch() -> None:
    """Lance la GUI."""
    gui = DocFuseGUI()
    gui.run()
