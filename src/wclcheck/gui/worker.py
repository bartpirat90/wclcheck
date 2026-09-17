"""Analyse in einem Hintergrund-Thread, damit das Fenster bedienbar bleibt.

Der Worker meldet jeden fertigen Boss sofort, statt auf den ganzen Raid zu warten.
Abgebrochen wird über ein Flag, das die Fortschritts-Rückmeldung prüft: `analyze_raid`
fängt nur `WCLError`, deshalb beendet die `Cancelled`-Ausnahme den Lauf sofort.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

from PySide6.QtCore import QThread, Signal

from ..analysis.report import Options
from ..auth import AuthError
from ..cache import DiskCache
from ..client import WCLClient, WCLError
from ..config import ConfigError, load_settings

log = logging.getLogger("wclcheck.gui")


class Cancelled(Exception):
    """Vom Benutzer abgebrochen."""


@dataclass
class Job:
    """Alles, was ein Analyselauf braucht."""

    report: str  # URL oder Code
    player: str | None = None
    fight_ids: list[int] | None = None
    options: Options = field(default_factory=Options)
    no_cache: bool = False
    config_path: Path | None = None


class AnalysisWorker(QThread):
    """Führt einen `Job` aus und meldet Fortschritt, einzelne Bosse und das Ergebnis."""

    progress = Signal(str)  # Statustext
    step = Signal(int, int)  # fertige Bosse, Bosse gesamt
    boss_done = Signal(object)  # BossResult
    finished_ok = Signal(object)  # RaidResult
    failed = Signal(str)
    needs_config = Signal(str, str)  # Meldung, Pfad zur config.toml
    was_cancelled = Signal()

    def __init__(self, job: Job, parent=None) -> None:
        super().__init__(parent)
        self.job = job
        self._stop = False
        self.rate_limit: dict | None = None

    def cancel(self) -> None:
        self._stop = True

    def _tick(self, message: str) -> None:
        if self._stop:
            raise Cancelled
        self.progress.emit(message)

    def run(self) -> None:  # noqa: C901 - linearer Ablauf, bewusst an einem Stück
        from ..analysis.report import analyze_raid
        from ..cli import parse_report_arg

        try:
            settings = (
                load_settings(self.job.config_path) if self.job.config_path else load_settings()
            )
        except ConfigError as exc:
            from ..config import CONFIG_PATH

            self.needs_config.emit(str(exc), str(self.job.config_path or CONFIG_PATH))
            return

        try:
            code, url_fight = parse_report_arg(self.job.report)
        except Exception:
            self.failed.emit(
                "In der Eingabe steckt kein Report-Code. Erwartet wird eine Adresse wie "
                "https://www.warcraftlogs.com/reports/ABC123… oder der Code selbst."
            )
            return

        cache = DiskCache()
        client = WCLClient(settings, cache)
        if self.job.no_cache:
            client.no_cache_codes.add(code)

        try:
            self._tick("Report wird geladen …")
            report = client.report(code)

            name = self.job.player or settings.player
            actor = report.find_player(name)
            if actor is None:
                others = ", ".join(sorted(a.name for a in report.actors if a.is_player))
                self.failed.emit(
                    f"{name} kommt in diesem Report nicht vor.\n\nEnthalten sind: {others}"
                )
                return

            wanted = self.job.fight_ids or ([url_fight] if url_fight else None)
            if wanted:
                fights = [f for f in report.fights if f.id in wanted]
            else:
                fights = [
                    f for f in report.kills() if f.is_complete and actor.id in f.friendlyPlayers
                ]
            fights = [f for f in fights if not f.inProgress]
            if not fights:
                self.failed.emit(
                    "In diesem Report gibt es keinen abgeschlossenen Boss-Kill mit "
                    f"{actor.name}. Laufende Kämpfe werden übersprungen."
                )
                return

            total = len(fights)
            done = 0
            self.step.emit(0, total)

            def on_boss(boss) -> None:
                nonlocal done
                done += 1
                self.boss_done.emit(boss)
                self.step.emit(done, total)

            result = analyze_raid(
                client, report, actor, fights, self.job.options, self._tick, on_boss
            )
        except Cancelled:
            self.was_cancelled.emit()
            return
        except (WCLError, AuthError) as exc:
            self.failed.emit(str(exc))
            return
        except Exception as exc:  # letzte Rettung: nie stumm sterben
            log.exception("Analyse fehlgeschlagen")
            self.failed.emit(f"Unerwarteter Fehler: {exc}")
            return

        self.rate_limit = client.last_rate_limit
        self.finished_ok.emit(result)
