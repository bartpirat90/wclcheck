"""Einstellungen des Fensters. Gespeichert wird über QSettings, nicht in der config.toml.

Die config.toml bleibt allein für die Zugangsdaten zuständig; sie wird hier nur gelesen,
um Spielername und Region vorzubelegen.
"""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QSpinBox,
    QVBoxLayout,
)

from ..analysis.report import Options

REGIONS = ["EU", "US", "EU,US", "KR", "TW", "Alle"]


@dataclass
class Prefs:
    player: str = "Schauderbart"
    region: str = "EU"
    comparators: int = 3
    ilvl_tolerance: int = 2
    threshold: float = 8.0
    no_cache: bool = False

    def options(self) -> Options:
        from ..cli import parse_regions

        return Options(
            comparators=self.comparators,
            ilvl_tolerance=self.ilvl_tolerance,
            threshold_pct=self.threshold,
            regions=parse_regions("ALL" if self.region == "Alle" else self.region),
        )


def load_prefs() -> Prefs:
    s = QSettings("wclcheck", "wclcheck")
    default = Prefs()
    try:  # Zugangsdaten-Datei als Vorbelegung, falls schon ausgefüllt
        from ..config import load_settings

        cfg = load_settings()
        default = Prefs(player=cfg.player, region=cfg.region)
    except Exception:
        pass
    return Prefs(
        player=str(s.value("player", default.player)),
        region=str(s.value("region", default.region)),
        comparators=int(s.value("comparators", default.comparators)),
        ilvl_tolerance=int(s.value("ilvl_tolerance", default.ilvl_tolerance)),
        threshold=float(s.value("threshold", default.threshold)),
        no_cache=str(s.value("no_cache", "false")).lower() in ("true", "1"),
    )


def save_prefs(p: Prefs) -> None:
    s = QSettings("wclcheck", "wclcheck")
    s.setValue("player", p.player)
    s.setValue("region", p.region)
    s.setValue("comparators", p.comparators)
    s.setValue("ilvl_tolerance", p.ilvl_tolerance)
    s.setValue("threshold", p.threshold)
    s.setValue("no_cache", "true" if p.no_cache else "false")


class SettingsDialog(QDialog):
    def __init__(self, prefs: Prefs, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Einstellungen")
        self.setMinimumWidth(420)

        self.player = QLineEdit(prefs.player)
        self.region = QComboBox()
        self.region.addItems(REGIONS)
        if prefs.region in REGIONS:
            self.region.setCurrentText(prefs.region)
        self.comparators = QSpinBox()
        self.comparators.setRange(0, 10)
        self.comparators.setValue(prefs.comparators)
        self.ilvl = QSpinBox()
        self.ilvl.setRange(0, 30)
        self.ilvl.setValue(prefs.ilvl_tolerance)
        self.threshold = QDoubleSpinBox()
        self.threshold.setRange(0.0, 100.0)
        self.threshold.setSingleStep(1.0)
        self.threshold.setDecimals(1)
        self.threshold.setSuffix(" %")
        self.threshold.setValue(prefs.threshold)
        self.no_cache = QCheckBox("Daten immer neu laden (für laufende Logs)")
        self.no_cache.setChecked(prefs.no_cache)

        form = QFormLayout()
        form.setSpacing(10)
        form.addRow("Spieler", self.player)
        form.addRow("Ranglisten-Region", self.region)
        form.addRow("Vergleichsspieler", self.comparators)
        form.addRow("Ilvl-Toleranz ±", self.ilvl)
        form.addRow("Befund ab Abweichung", self.threshold)
        form.addRow("", self.no_cache)

        note = QLabel(
            "Mehr Vergleichsspieler machen den Mittelwert stabiler, kosten aber mehr "
            "Abfragen. Ein kompletter Raid mit drei Vergleichsspielern liegt bei rund "
            "460 von 3600 Punkten pro Stunde."
        )
        note.setObjectName("Subtitle")
        note.setWordWrap(True)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Übernehmen")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("Abbrechen")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        box = QVBoxLayout(self)
        box.setContentsMargins(20, 20, 20, 20)
        box.setSpacing(16)
        box.addLayout(form)
        box.addWidget(note)
        box.addWidget(buttons)

    def prefs(self) -> Prefs:
        return Prefs(
            player=self.player.text().strip() or "Schauderbart",
            region=self.region.currentText(),
            comparators=self.comparators.value(),
            ilvl_tolerance=self.ilvl.value(),
            threshold=self.threshold.value(),
            no_cache=self.no_cache.isChecked(),
        )
