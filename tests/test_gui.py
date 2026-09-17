"""Oberfläche ohne Bildschirm prüfen: Widgets bauen, Zustände schalten.

Läuft mit QT_QPA_PLATFORM=offscreen; ohne PySide6 werden die Tests übersprungen.
"""

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6")

from PySide6.QtCore import QSettings  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402
from test_output import _raid_result  # noqa: E402

from wclcheck.gui import style  # noqa: E402
from wclcheck.gui.blocks import boss_detail, findings_card, table  # noqa: E402
from wclcheck.gui.main_window import MainWindow  # noqa: E402
from wclcheck.gui.settings_dialog import Prefs, SettingsDialog  # noqa: E402
from wclcheck.output import build_boss_block  # noqa: E402


@pytest.fixture(scope="session")
def app():
    application = QApplication.instance() or QApplication([])
    application.setStyleSheet(style.STYLESHEET)
    return application


@pytest.fixture(autouse=True)
def _isolated_settings(tmp_path, monkeypatch):
    """QSettings in eine Wegwerf-Datei lenken, damit die echten Einstellungen bleiben."""
    QSettings.setPath(
        QSettings.Format.IniFormat, QSettings.Scope.UserScope, str(tmp_path)
    )
    monkeypatch.setattr(QSettings, "defaultFormat", lambda: QSettings.Format.IniFormat,
                        raising=False)


def test_table_uses_tone_colours(app):
    block = build_boss_block(_raid_result(True).bosses[0], 8.0)
    widget = table(block.general)
    assert widget.rowCount() == len(block.general.rows)
    assert widget.columnCount() == len(block.general.headers)
    assert widget.item(0, 0).text() == block.general.rows[0][0].text


def test_findings_card_without_comparators_explains_itself(app):
    card = findings_card([], has_comparators=False)
    texts = [w.text() for w in card.findChildren(type(card.children()[1])) if hasattr(w, "text")]
    assert any("Vergleichsspieler" in t for t in texts)


def test_narrow_table_scrolls_instead_of_cutting_labels(app):
    """Zu wenig Platz darf die Beschriftungsspalte nicht auf „…“ eindampfen."""
    block = build_boss_block(_raid_result(True).bosses[0], 8.0)
    widget = table(block.general)
    widget.show()  # ohne show richtet Qt das Innere der Tabelle nicht neu aus
    labels = widget.sizeHintForColumn(0)

    widget.resize(1400, widget.height())
    app.processEvents()
    wide = widget.height()
    assert widget.horizontalScrollBar().maximum() == 0  # alles sichtbar

    widget.resize(180, widget.height())
    app.processEvents()

    assert widget.columnWidth(0) >= labels
    assert widget.horizontalScrollBar().maximum() > 0  # scrollt selbst
    assert widget.height() > wide  # Platz für die Bildlaufleiste kam dazu


def test_detail_page_fits_into_a_narrow_window(app):
    """Keine Spalte und keine Linkzeile darf die ganze Seite breit halten."""
    boss = _raid_result(True).bosses[0]
    page = boss_detail(build_boss_block(boss, 8.0), has_comparators=True)
    assert page.minimumSizeHint().width() <= 520


def test_boss_detail_builds_all_sections(app):
    boss = _raid_result(True).bosses[0]
    page = boss_detail(build_boss_block(boss, 8.0), has_comparators=True)
    assert page.layout().count() > 5


def test_main_window_starts_empty(app):
    window = MainWindow()
    assert window.boss_list.count() == 0
    assert not window.save_button.isEnabled()
    assert window.progress.isHidden()


def test_main_window_shows_bosses_and_summary(app):
    result = _raid_result(True)
    window = MainWindow()
    for boss in result.bosses:
        window._on_boss(boss)
    assert window.boss_list.count() == len(result.bosses)
    window._on_finished(result)
    assert window.boss_list.count() == len(result.bosses) + 1
    assert window.save_button.isEnabled()
    assert window.boss_list.currentRow() == 0  # Raid-Fazit zuerst
    window._show_row(1)  # erster Boss
    window.close()


def test_main_window_reports_failure(app):
    window = MainWindow()
    window._on_failed("Kaputt.")
    assert not window.progress.isVisible()
    assert "Fehl" in window.status.text()


def test_settings_dialog_round_trip(app):
    prefs = Prefs(player="Foo", region="US", comparators=5, ilvl_tolerance=4,
                  threshold=12.5, no_cache=True)
    dialog = SettingsDialog(prefs)
    assert dialog.prefs() == prefs


def test_prefs_build_options():
    opts = Prefs(comparators=4, ilvl_tolerance=3, threshold=6.0, region="EU,US").options()
    assert opts.comparators == 4
    assert opts.ilvl_tolerance == 3
    assert opts.threshold_pct == 6.0
    assert opts.regions == frozenset({"EU", "US"})
