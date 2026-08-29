"""Tests de l'inventaire (parcours de dossier, liste blanche, ignores).

CdC §7.1, §7.5, §8.1.
"""

from __future__ import annotations

from pathlib import Path

from docfuse.core.inventory import list_ignored, scan_directory, scan_files


class TestScanDirectory:
    """Tests de scan_directory()."""

    def test_finds_supported_files(self, tmp_workspace: Path) -> None:
        files = scan_directory(tmp_workspace)
        names = {f.name for f in files}
        assert "doc1.txt" in names
        assert "notes.md" in names
        assert "data.json" in names
        assert "table.csv" in names
        assert "page.html" in names

    def test_ignores_unsupported_extensions(self, tmp_workspace: Path) -> None:
        files = scan_directory(tmp_workspace)
        names = {f.name for f in files}
        assert "program.exe" not in names

    def test_ignores_lock_files(self, tmp_workspace: Path) -> None:
        files = scan_directory(tmp_workspace)
        names = {f.name for f in files}
        assert "~$locked.docx" not in names

    def test_ignores_minified_js_and_css(self, tmp_path: Path) -> None:
        """D-077 : *.min.js/*.min.css sont des bundles tiers (jQuery, etc.),
        jamais du code écrit par l'utilisateur — trouvé en testant sur un
        vrai dossier de page web sauvegardée par un navigateur, où ce bruit
        représentait 91 % du corpus généré."""
        (tmp_path / "app.py").write_text("print('hello')", encoding="utf-8")
        (tmp_path / "jquery.min.js").write_text("(function(){})();", encoding="utf-8")
        (tmp_path / "styles.min.css").write_text(".a{color:red}", encoding="utf-8")

        files = scan_directory(tmp_path)
        names = {f.name for f in files}
        assert "app.py" in names
        assert "jquery.min.js" not in names
        assert "styles.min.css" not in names

    def test_ignores_vendor_dirs(self, tmp_path: Path) -> None:
        """D-077 : node_modules/vendor/dist/build sont des artefacts ou
        dépendances tiers, jamais du code écrit par l'utilisateur."""
        (tmp_path / "app.py").write_text("print('hello')", encoding="utf-8")
        for vendor_dir in ("node_modules", "vendor", "dist", "build"):
            d = tmp_path / vendor_dir
            d.mkdir()
            (d / "lib.js").write_text("var x = 1;", encoding="utf-8")

        files = scan_directory(tmp_path, recursive=True)
        names = {f.name for f in files}
        assert "app.py" in names
        assert "lib.js" not in names

    def test_recursive_finds_subdir_files(self, tmp_workspace: Path) -> None:
        files = scan_directory(tmp_workspace, recursive=True)
        names = {f.name for f in files}
        assert "deep.txt" in names

    def test_non_recursive_excludes_subdir(self, tmp_workspace: Path) -> None:
        files = scan_directory(tmp_workspace, recursive=False)
        names = {f.name for f in files}
        assert "deep.txt" not in names

    def test_natural_sort_order(self, tmp_workspace: Path) -> None:
        # Créer file1, file2, file10 pour vérifier le tri naturel
        (tmp_workspace / "file1.txt").write_text("1", encoding="utf-8")
        (tmp_workspace / "file2.txt").write_text("2", encoding="utf-8")
        (tmp_workspace / "file10.txt").write_text("10", encoding="utf-8")

        files = scan_directory(tmp_workspace)
        rel_names = [f.name for f in files]
        # file2 doit apparaître avant file10
        idx2 = rel_names.index("file2.txt")
        idx10 = rel_names.index("file10.txt")
        assert idx2 < idx10


class TestListIgnored:
    """Tests de list_ignored()."""

    def test_lists_exe_as_ignored(self, tmp_workspace: Path) -> None:
        ignored = list_ignored(tmp_workspace)
        names = {p.name for p, _ in ignored}
        assert "program.exe" in names

    def test_lists_lock_file_as_ignored(self, tmp_workspace: Path) -> None:
        ignored = list_ignored(tmp_workspace)
        names = {p.name for p, _ in ignored}
        assert "~$locked.docx" in names

    def test_ignored_has_reason(self, tmp_workspace: Path) -> None:
        ignored = list_ignored(tmp_workspace)
        for _, reason in ignored:
            assert len(reason) > 0


class TestShouldIgnoreDir:
    """M-07: _should_ignore_dir ne doit pas filtrer tous les dossiers .xxx."""

    def test_git_dir_ignored(self) -> None:
        from docfuse.core.inventory import _should_ignore_dir

        assert _should_ignore_dir(".git") is True
        assert _should_ignore_dir(".svn") is True

    def test_normal_dot_dir_not_ignored(self) -> None:
        from docfuse.core.inventory import _should_ignore_dir

        # .config, .local, etc. ne doivent pas être filtrés
        assert _should_ignore_dir(".config") is False
        assert _should_ignore_dir(".local") is False
        assert _should_ignore_dir(".archives") is False

    def test_system_dirs_ignored(self) -> None:
        from docfuse.core.inventory import _should_ignore_dir

        assert _should_ignore_dir("$RECYCLE.BIN") is True
        assert _should_ignore_dir("System Volume Information") is True
        assert _should_ignore_dir("__pycache__") is True


class TestScanFiles:
    """Tests de scan_files() (fichiers individuels, pas un dossier)."""

    def test_scan_individual_files(self, tmp_workspace: Path) -> None:
        paths = [tmp_workspace / "doc1.txt", tmp_workspace / "notes.md"]
        files = scan_files(paths)
        names = {f.name for f in files}
        assert "doc1.txt" in names
        assert "notes.md" in names

    def test_scan_filters_unsupported(self, tmp_workspace: Path) -> None:
        paths = [tmp_workspace / "doc1.txt", tmp_workspace / "program.exe"]
        files = scan_files(paths)
        names = {f.name for f in files}
        assert "program.exe" not in names
