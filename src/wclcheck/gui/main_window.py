"""Hauptfenster: Adresse eingeben, Analyse starten, Ergebnisse durchsehen."""

from __future__ import annotations

import re
import webbrowser
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from ..analysis.report import BossResult, RaidResult
from ..output import build_boss_block, render_markdown
from . import style
from .blocks import boss_detail, card, section_label
from .settings_dialog import Prefs, SettingsDialog, load_prefs, save_prefs
from .worker import AnalysisWorker, Job

WCL_URL = re.compile(r"warcraftlogs\.com/reports/[A-Za-z0-9:]{16,}")


def _dot(colour: str) -> QLabel:
    label = QLabel()
    label.setFixedSize(8, 8)
    label.setStyleSheet(f"background: {colour}; border-radius: 4px;")
    return label


class BossListItem(QWidget):
    """Eintrag in der Bossliste: Punkt, Name, Parse und Anzahl Befunde."""

    def __init__(self, boss: BossResult) -> None:
        super().__init__()
        self.setObjectName("Plain")
        count = len(boss.findings)
        colour = style.GOOD if count == 0 else (style.WARN if count <= 2 else style.BAD)

        name = QLabel(boss.fight.name)
        name.setStyleSheet("font-weight: 600;")
        parse = boss.player.general.parse_percent
        bits = [f"Parse {parse:.0f}" if parse is not None else "Parse –"]
        bits.append("keine Befunde" if count == 0 else f"{count} Befund{'e' if count > 1 else ''}")
        meta = QLabel("  ·  ".join(bits))
        meta.setObjectName("Subtitle")

        text = QVBoxLayout()
        text.setContentsMargins(0, 0, 0, 0)
        text.setSpacing(2)
        text.addWidget(name)
        text.addWidget(meta)

        row = QHBoxLayout(self)
        row.setContentsMargins(10, 8, 10, 8)
        row.setSpacing(10)
        row.addWidget(_dot(colour), 0, Qt.AlignmentFlag.AlignTop)
        row.addLayout(text, 1)


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("wclcheck")
        self.resize(1180, 820)
        self.setMinimumSize(780, 560)

        self.prefs: Prefs = load_prefs()
        self.worker: AnalysisWorker | None = None
        self.result: RaidResult | None = None
        self.bosses: list[BossResult] = []

        self._build()
        self._prefill_from_clipboard()

    # ------------------------------------------------------------------ Aufbau

    def _build(self) -> None:
        root = QWidget()
        outer = QVBoxLayout(root)
        outer.setContentsMargins(20, 18, 20, 14)
        outer.setSpacing(14)

        outer.addLayout(self._header())
        outer.addLayout(self._input_row())
        outer.addWidget(self._body(), 1)
        outer.addLayout(self._footer())

        self.setCentralWidget(root)
        QShortcut(QKeySequence("Ctrl+S"), self, self._save)
        QShortcut(QKeySequence("Ctrl+L"), self, self.url.setFocus)

    def _header(self) -> QHBoxLayout:
        title = QLabel("wclcheck")
        title.setObjectName("Title")
        subtitle = QLabel("Warlock-Kills gegen vergleichbare Top-Spieler")
        subtitle.setObjectName("Subtitle")
        left = QVBoxLayout()
        left.setSpacing(1)
        left.addWidget(title)
        left.addWidget(subtitle)

        self.settings_button = QPushButton("Einstellungen")
        self.settings_button.clicked.connect(self._open_settings)
        self.save_button = QPushButton("Speichern …")
        self.save_button.setEnabled(False)
        self.save_button.clicked.connect(self._save)

        row = QHBoxLayout()
        row.addLayout(left)
        row.addStretch(1)
        row.addWidget(self.settings_button)
        row.addWidget(self.save_button)
        return row

    def _input_row(self) -> QHBoxLayout:
        self.url = QLineEdit()
        self.url.setPlaceholderText(
            "Adresse des Warcraft-Logs-Berichts einfügen, zum Beispiel "
            "https://www.warcraftlogs.com/reports/…"
        )
        self.url.setClearButtonEnabled(True)
        self.url.returnPressed.connect(self._start_or_cancel)

        self.go = QPushButton("Analysieren")
        self.go.setObjectName("Primary")
        self.go.setMinimumWidth(130)
        self.go.clicked.connect(self._start_or_cancel)

        row = QHBoxLayout()
        row.setSpacing(10)
        row.addWidget(self.url, 1)
        row.addWidget(self.go)
        return row

    def _body(self) -> QWidget:
        self.boss_list = QListWidget()
        self.boss_list.setMinimumWidth(250)
        self.boss_list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.boss_list.setMaximumWidth(340)
        self.boss_list.currentRowChanged.connect(self._show_row)

        self.detail = QScrollArea()
        self.detail.setWidgetResizable(True)
        self.detail.setWidget(self._empty_state())

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(self.boss_list)
        splitter.addWidget(self.detail)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([280, 900])
        return splitter

    def _footer(self) -> QHBoxLayout:
        self.progress = QProgressBar()
        self.progress.setTextVisible(False)
        self.progress.setMaximumWidth(220)
        self.progress.hide()
        self.status = QLabel("Bereit.")
        self.status.setObjectName("Subtitle")
        self.rate = QLabel("")
        self.rate.setObjectName("Subtitle")

        row = QHBoxLayout()
        row.setSpacing(12)
        row.addWidget(self.progress)
        row.addWidget(self.status, 1)
        row.addWidget(self.rate)
        return row

    # ------------------------------------------------------------- Platzhalter

    def _empty_state(self) -> QWidget:
        page = QWidget()
        box = QVBoxLayout(page)
        box.setAlignment(Qt.AlignmentFlag.AlignCenter)
        box.setSpacing(10)
        headline = QLabel("Noch nichts analysiert")
        headline.setObjectName("Empty")
        headline.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hint = QLabel(
            "Adresse eines Berichts oben einfügen und auf Analysieren klicken.\n"
            "Jeder abgeschlossene Boss-Kill wird gegen drei vergleichbare Spieler gestellt."
        )
        hint.setObjectName("Subtitle")
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        box.addWidget(headline)
        box.addWidget(hint)
        return page

    def _message_page(self, title: str, text: str, tone: str = "Error") -> QWidget:
        page = QWidget()
        box = QVBoxLayout(page)
        box.setContentsMargins(4, 4, 4, 4)
        box.setSpacing(12)
        head = QLabel(title)
        head.setObjectName("BossHeading")
        body = QLabel(text)
        body.setObjectName(tone)
        body.setWordWrap(True)
        body.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        box.addWidget(head)
        box.addWidget(body)
        box.addStretch(1)
        return page

    def _set_detail(self, widget: QWidget) -> None:
        self.detail.setWidget(widget)

    def _prefill_from_clipboard(self) -> None:
        text = (QGuiApplication.clipboard().text() or "").strip()
        if WCL_URL.search(text):
            self.url.setText(text)

    # ----------------------------------------------------------------- Ablauf

    def _start_or_cancel(self) -> None:
        if self.worker is not None and self.worker.isRunning():
            self.worker.cancel()
            self.status.setText("Wird abgebrochen …")
            self.go.setEnabled(False)
            return
        self._start()

    def _start(self) -> None:
        report = self.url.text().strip()
        if not report:
            self.status.setText("Bitte zuerst eine Adresse einfügen.")
            self.url.setFocus()
            return

        self.boss_list.clear()
        self.bosses.clear()
        self.result = None
        self.save_button.setEnabled(False)
        self._set_detail(self._message_page("Analyse läuft", "Der erste Boss erscheint gleich.",
                                            tone="Subtitle"))
        self.progress.setRange(0, 0)
        self.progress.show()
        self.go.setText("Abbrechen")
        self.settings_button.setEnabled(False)
        self.rate.setText("")

        job = Job(
            report=report,
            player=self.prefs.player,
            options=self.prefs.options(),
            no_cache=self.prefs.no_cache,
        )
        self.worker = AnalysisWorker(job, self)
        self.worker.progress.connect(self.status.setText)
        self.worker.step.connect(self._on_step)
        self.worker.boss_done.connect(self._on_boss)
        self.worker.finished_ok.connect(self._on_finished)
        self.worker.failed.connect(self._on_failed)
        self.worker.needs_config.connect(self._on_needs_config)
        self.worker.was_cancelled.connect(self._on_cancelled)
        self.worker.start()

    def _idle(self) -> None:
        self.progress.hide()
        self.go.setText("Analysieren")
        self.go.setEnabled(True)
        self.settings_button.setEnabled(True)

    def _on_step(self, done: int, total: int) -> None:
        self.progress.setRange(0, total)
        self.progress.setValue(done)

    def _on_boss(self, boss: BossResult) -> None:
        self.bosses.append(boss)
        item = QListWidgetItem()
        widget = BossListItem(boss)
        item.setSizeHint(widget.sizeHint())
        self.boss_list.addItem(item)
        self.boss_list.setItemWidget(item, widget)
        if self.boss_list.currentRow() < 0:
            self.boss_list.setCurrentRow(0)

    def _on_finished(self, result: RaidResult) -> None:
        self.result = result
        self.save_button.setEnabled(True)
        self._idle()

        item = QListWidgetItem()
        item.setData(Qt.ItemDataRole.UserRole, "summary")
        label = QLabel("Raid-Fazit")
        label.setObjectName("Plain")
        label.setStyleSheet("font-weight: 600; background: transparent;")
        label.setContentsMargins(10, 10, 10, 10)
        item.setSizeHint(label.sizeHint())
        self.boss_list.insertItem(0, item)
        self.boss_list.setItemWidget(item, label)

        count = len(result.bosses)
        self.status.setText(
            f"Fertig: {count} Boss{'e' if count != 1 else ''} analysiert."
            + (f" {len(result.errors)} übersprungen." if result.errors else "")
        )
        if self.worker is not None and self.worker.rate_limit:
            rl = self.worker.rate_limit
            spent, limit = rl.get("pointsSpentThisHour"), rl.get("limitPerHour")
            if spent is not None and limit:
                self.rate.setText(f"{float(spent):.0f} von {limit} Punkten diese Stunde")
        self.boss_list.setCurrentRow(0)

    def _on_failed(self, message: str) -> None:
        self._idle()
        self.status.setText("Fehlgeschlagen.")
        self._set_detail(self._message_page("Das hat nicht geklappt", message))

    def _on_cancelled(self) -> None:
        self._idle()
        self.status.setText("Abgebrochen. Bereits geladene Daten bleiben gespeichert.")

    def _on_needs_config(self, message: str, path: str) -> None:
        self._idle()
        self.status.setText("Zugangsdaten fehlen.")
        box = QMessageBox(self)
        box.setWindowTitle("Zugangsdaten fehlen")
        box.setText("Für die Abfrage bei Warcraft Logs werden eigene Zugangsdaten gebraucht.")
        box.setInformativeText(
            f"{message}\n\nTrage Client-ID und Client-Secret in die Datei ein und starte "
            "die Analyse erneut."
        )
        open_file = box.addButton("Datei öffnen", QMessageBox.ButtonRole.ActionRole)
        website = box.addButton("Zugang anlegen", QMessageBox.ButtonRole.ActionRole)
        box.addButton("Schließen", QMessageBox.ButtonRole.RejectRole)
        box.exec()
        if box.clickedButton() is open_file and Path(path).exists():
            webbrowser.open(Path(path).as_uri())
        elif box.clickedButton() is website:
            webbrowser.open("https://www.warcraftlogs.com/api/clients/")

    # --------------------------------------------------------------- Anzeigen

    def _show_row(self, row: int) -> None:
        if row < 0:
            return
        item = self.boss_list.item(row)
        if item is not None and item.data(Qt.ItemDataRole.UserRole) == "summary":
            self._set_detail(self._summary_page())
            return
        index = row - (1 if self.result is not None else 0)
        if 0 <= index < len(self.bosses):
            boss = self.bosses[index]
            self._set_detail(
                boss_detail(build_boss_block(boss, self.prefs.threshold), bool(boss.comparators))
            )

    def _summary_page(self) -> QWidget:
        assert self.result is not None
        page = QWidget()
        box = QVBoxLayout(page)
        box.setContentsMargins(4, 4, 4, 4)
        box.setSpacing(14)

        title = QLabel("Raid-Fazit")
        title.setObjectName("BossHeading")
        subtitle = QLabel("Die größten Hebel über alle Bosse dieses Abends.")
        subtitle.setObjectName("BossMeta")
        box.addWidget(title)
        box.addWidget(subtitle)

        rows: list[QWidget] = []
        if self.result.levers:
            for i, lever in enumerate(self.result.levers, 1):
                label = QLabel(f"{i}.  {lever.text}")
                label.setWordWrap(True)
                rows.append(label)
        else:
            empty = QLabel("Keine Abweichung über dem Schwellwert.")
            empty.setObjectName("Subtitle")
            rows.append(empty)
        box.addWidget(card(*rows, title="Hebel"))

        if self.result.errors:
            errs: list[QWidget] = []
            for err in self.result.errors:
                label = QLabel(err)
                label.setObjectName("Error")
                label.setWordWrap(True)
                errs.append(label)
            box.addWidget(card(*errs, title="Nicht analysiert"))

        box.addWidget(self._overview_card())
        box.addStretch(1)
        return page

    def _overview_card(self) -> QFrame:
        assert self.result is not None
        inner = QWidget()
        inner.setObjectName("Plain")
        grid = QVBoxLayout(inner)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(6)
        for boss in self.result.bosses:
            g = boss.player.general
            parse = f"{g.parse_percent:.0f}" if g.parse_percent is not None else "–"
            line = QLabel(
                f"{boss.fight.name}  ·  {g.spec.label}  ·  Parse {parse}  ·  "
                f"{len(boss.findings)} Befunde"
            )
            line.setWordWrap(True)
            grid.addWidget(line)
        frame = QFrame()
        frame.setObjectName("Card")
        outer = QVBoxLayout(frame)
        outer.setContentsMargins(16, 14, 16, 14)
        outer.setSpacing(10)
        outer.addWidget(section_label("Alle Bosse"))
        outer.addWidget(inner)
        return frame

    # ------------------------------------------------------------- Werkzeuge

    def _open_settings(self) -> None:
        dialog = SettingsDialog(self.prefs, self)
        if dialog.exec():
            self.prefs = dialog.prefs()
            save_prefs(self.prefs)
            self.status.setText("Einstellungen übernommen. Gilt ab der nächsten Analyse.")

    def _save(self) -> None:
        if self.result is None:
            return
        name = f"{self.result.report.code}.md"
        path, _ = QFileDialog.getSaveFileName(
            self, "Ergebnis speichern", name, "Markdown (*.md);;Alle Dateien (*)"
        )
        if not path:
            return
        Path(path).write_text(render_markdown(self.result), encoding="utf-8")
        self.status.setText(f"Gespeichert: {path}")

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt-Namensschema
        if self.worker is not None and self.worker.isRunning():
            self.worker.cancel()
            self.worker.wait(3000)
        super().closeEvent(event)
