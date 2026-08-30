"""Point d'entrée : python -m docfuse

C-11: Sans arguments → lance la GUI. Avec arguments → lance la CLI.
"""

import sys


def main() -> None:
    if len(sys.argv) <= 1:
        # Pas d'arguments → lancer la GUI (CdC §2.1, §2.3)
        try:
            from docfuse.gui import launch

            launch()
        except ImportError as exc:
            # D-103 : la GUI est un extra (`docfuse[gui]`) — sans lui, un
            # message clair plutôt qu'une trace `ModuleNotFoundError`
            # (`customtkinter` est importé à la construction de la fenêtre).
            from docfuse.i18n import t

            print(f"{t('gui.not_installed')} ({exc})", file=sys.stderr)
            sys.exit(1)
    else:
        # Arguments fournis → mode CLI (CdC §6.3)
        from docfuse.cli import main as cli_main

        sys.exit(cli_main())


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nInterrupted", file=sys.stderr)
        sys.exit(1)
