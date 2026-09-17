"""Fensteroberfläche für wclcheck.

Start über `wclcheck-gui` oder `python -m wclcheck.gui`. PySide6 wird nur hier
gebraucht und deshalb erst beim Aufruf importiert.
"""

from __future__ import annotations

import sys
from pathlib import Path

ICON = Path(__file__).with_name("wclcheck.ico")


def _taskbar_identity() -> None:
    """Ohne eigene App-ID zeigt die Windows-Taskleiste das Symbol des Interpreters."""
    if sys.platform != "win32":
        return
    try:
        import ctypes

        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("wclcheck.wclcheck")
    except Exception:  # Symbol ist nett, aber nichts, woran der Start scheitern darf
        pass


def _fatal(message: str) -> None:
    """Meldung, die auch ohne Konsole ankommt.

    Beim Doppelklick läuft das Programm ohne Konsole, `sys.stderr` ist dann `None`
    und ein `print` würde selbst zum Fehler. Deshalb zusätzlich ein Fenster von
    Windows: Qt steht an dieser Stelle ja gerade nicht zur Verfügung.
    """
    if sys.stderr is not None:
        print(message, file=sys.stderr)
    if sys.platform == "win32":
        try:
            import ctypes

            ctypes.windll.user32.MessageBoxW(0, message, "wclcheck", 0x10)
        except Exception:
            pass


def main() -> int:
    try:
        from PySide6.QtWidgets import QApplication
    except ImportError:
        _fatal(
            "Für die Oberfläche fehlt PySide6. Installieren mit:\n"
            "  uv sync --extra gui\n"
            "oder:\n"
            "  pip install 'wclcheck[gui]'"
        )
        return 1

    from PySide6.QtGui import QIcon

    from . import style
    from .main_window import MainWindow

    _taskbar_identity()
    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName("wclcheck")
    app.setOrganizationName("wclcheck")
    app.setStyleSheet(style.STYLESHEET)
    if ICON.exists():
        app.setWindowIcon(QIcon(str(ICON)))

    window = MainWindow()
    window.show()
    return app.exec()


__all__ = ["main"]
