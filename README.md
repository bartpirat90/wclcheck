# wclcheck

Warcraft-Logs-Analyse für den Hexer **Schauderbart** (Antonidas EU): pro Boss-Kill werden
die eigenen Werte gegen drei vergleichbare Top-Spieler derselben Spec aus den WCL-Rankings
gestellt und die konkreten Abweichungen ausgegeben. Nur Warlock, Specs **Demonology
(Diabolist)** und **Destruction (Hellcaller)**. Der Report darf ein laufender Live-Log sein.

## Installation

```bash
uv sync
uv run wclcheck --version
```

Beim ersten Start wird `~/.config/wclcheck/config.toml` angelegt. Dort Client-ID und
Client-Secret eines WCL-API-Clients eintragen (<https://www.warcraftlogs.com/api/clients/>),
alternativ die Umgebungsvariablen `WCL_CLIENT_ID` / `WCL_CLIENT_SECRET` setzen.

```toml
[wcl]
client_id = "..."
client_secret = "..."

[defaults]
player = "Schauderbart"
region = "EU"
```

## Aufruf

```bash
wclcheck https://www.warcraftlogs.com/reports/qCZ2bPkFVzgc46Lp
wclcheck qCZ2bPkFVzgc46Lp --player Schauderbart --fights 22       # nur ein Fight
wclcheck qCZ2bPkFVzgc46Lp --comparators 5 --ilvl-tolerance 3      # mehr Vergleich
wclcheck qCZ2bPkFVzgc46Lp --region EU,US                          # Rankings aus EU und US
wclcheck qCZ2bPkFVzgc46Lp --threshold 5                           # Befunde ab 5 %
wclcheck qCZ2bPkFVzgc46Lp --format md > raid.md                   # Markdown statt Terminal
wclcheck qCZ2bPkFVzgc46Lp --no-cache                              # Live-Log erneut ziehen
wclcheck qCZ2bPkFVzgc46Lp --debug                                 # Rate-Limit, Cache, Logs
```

Ohne `--fights` werden alle abgeschlossenen Boss-Kills analysiert, in denen der Spieler
dabei war. Laufende Fights eines Live-Logs werden übersprungen.

## Ausgabe pro Boss

1. Kopfzeile und Spieler-Tabelle: Boss, Spec/Hero, Dauer, DPS, Parse, Ilvl, Rang und
   Log-Link für dich und die Vergleichsspieler.
2. Kernmetriken nebeneinander mit Median der Vergleichsspieler und Abweichung in %
   (farbig ab Schwellwert, Default 8 %).
3. Casts pro 30 s als Zeile pro Spieler.
4. Spec-Metriken (Demo: Tyrant, Dominion of Argus, HoG, Demonbolt/Cores, Implosion,
   Dreadstalkers, Grimoire, Ruination; Destro: Wither, Shadowburn, Chaos Bolt, Conflagrate,
   Soul Fire, Malevolence/Infernal, Havoc, Shard-Overcap).
5. Befunde: maximal 6 Abweichungen über Schwellwert, sortiert nach geschätztem Schadenswert.
6. Gear/Stats nebeneinander, ohne Bewertung.

Am Ende ein Raid-Fazit mit den drei größten Hebeln über alle Bosse.

## Vergleichsspieler

Rankings desselben Encounters, derselben Spec und Schwierigkeit. Filter: Ilvl ±2
(`--ilvl-tolerance`), Kampfdauer ±10 %, Raidgröße 20–30, keine anonymen Reports, Region
laut `--region`. Rang 1–10 wird übersprungen, ebenso der analysierte Charakter selbst; genommen
werden die ersten drei Treffer danach. Reichen fünf Ranking-Seiten nicht, werden die Toleranzen schrittweise auf ±4 Ilvl /
±20 % gelockert und das in der Ausgabe vermerkt. Jeder Vergleichsspieler läuft durch
exakt dieselbe Metrik-Pipeline.

## Definitionen

- **Spieler-Casts**: `cast`-Events des Spielers ohne Pets und ohne Utility (Healthstone,
  Tränke, Dark Pact, Unending Resolve, Burning Rush, Demonic Circle, Mortal Coil, Soulburn,
  Racials, On-Use-Items, Raid-Buff-Procs). Havoc zählt ebenfalls nicht mit, damit die
  Zahlen zur manuellen Referenzzählung passen; es wird als eigene Destro-Metrik ausgewertet.
  Die Ausschlussliste steht als ID-Set in `src/wclcheck/spells.py`.
- **Lücken**: Abstände zwischen zwei aufeinanderfolgenden Spieler-Casts über 2,5 s.
- **Abgebrochene Casts**: `begincast` ohne zugehörigen `cast`.
- **Reaktionszeit**: Zeit von einem Instant bis zum Beginn der nächsten Aktion; GCD wird als
  kleinster Abstand zweier Instants im Log geschätzt.
- **Kampftrank**: Buff „Potion of Recklessness“.
- Zauber werden ausschließlich über Spell-IDs erkannt (lokalisierte Logs funktionieren).
  Unbekannte IDs werden geloggt (`--debug`), nicht geraten.

Rotationsregeln stehen als Kommentar in `src/wclcheck/analysis/rules_demo.py` und
`rules_destro.py` und sind dort für den nächsten Patch anpassbar.

## Cache und Rate-Limit

Alle Report-Abfragen werden unter `platformdirs.user_cache_dir("wclcheck")` gecacht
(Schlüssel: Report-Code, Fight-ID, Query-Hash). Die Fight-Liste eines Reports ist maximal
60 s gültig, Events abgeschlossener Fights dauerhaft. Report-Rankings (Parse) werden
erst gecacht, sobald WCL sie berechnet hat. `--no-cache` zieht nur den
analysierten Report neu; Vergleichslogs bleiben gecacht. Ein kompletter Boss mit drei
Vergleichsspielern kostet etwa 40 API-Punkte (Limit 3600 pro Stunde), gecachte Läufe
kosten nichts.

## Entwicklung

```bash
uv run pytest -q            # Unit- und Live-Tests (Live wird ohne Zugangsdaten übersprungen)
uv run pytest -q -m live    # nur Regressionstests gegen den Referenz-Report
uv run ruff check src tests
```

Die Referenzwerte (Report `qCZ2bPkFVzgc46Lp`, Fights 22/13/7/2 Demo, 17 Destro) stehen in
`tests/test_live_phase*.py`; Cast-Zahlen müssen exakt, Schaden auf ±1 %, Lücken-Summen auf
±2 s stimmen.
