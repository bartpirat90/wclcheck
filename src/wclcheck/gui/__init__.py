"""Fensteroberfläche für wclcheck.

Start über `wclcheck-gui` oder `python -m wclcheck.gui`. PySide6 wird nur hier
gebraucht und deshalb erst beim Aufruf importiert.
"""

from __future__ import annotations

import sys


def main() -> int:
    try:
        from PySide6.QtWidgets import QApplication
    except ImportError:
        print(
            "Für die Oberfläche fehlt PySide6. Installieren mit:\n"
            "  uv sync --extra gui\n"
            "oder:\n"
            "  pip install 'wclcheck[gui]'",
            file=sys.stderr,
        )
        return 1

    from . import style
    from .main_window import MainWindow

    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName("wclcheck")
    app.setOrganizationName("wclcheck")
    app.setStyleSheet(style.STYLESHEET)

    window = MainWindow()
    window.show()
    return app.exec()


__all__ = ["main"]
