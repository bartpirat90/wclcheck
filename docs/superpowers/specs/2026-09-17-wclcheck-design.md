# Prompt für Claude Code: `wclcheck` – Warcraft-Logs-Analyse-Tool für Schauderbart

> Diesen gesamten Text als ersten Prompt in Claude Code einfügen (leeres Projektverzeichnis, z. B. `~/dev/wclcheck`).

---

## Rolle und Orchestrierung

Du bist Fable 5.1 und orchestrierst dieses Projekt. Du entscheidest selbst, welche Teilaufgaben du an Subagenten delegierst und mit welchem Modell. Richtwerte, von denen du abweichen darfst, wenn es sinnvoll ist:

- **Du selbst (Fable):** Architektur, Metrik-Definitionen, Auswahl der Vergleichsspieler, Review aller Ergebnisse, finale Abnahme gegen die Referenzwerte unten.
- **Opus:** Analyse-Kern (`analysis/`), alles, wo Spielmechanik in Code übersetzt wird, und die Regressionstests gegen die Referenzwerte.
- **Sonnet:** API-Client, OAuth, Caching, CLI, Konfig, Formatierung der Ausgabe, README.
- **Haiku:** Docstrings, Typ-Annotationen nachziehen, Lint-Fixes.

Arbeite in Phasen (siehe unten) und starte Phase n+1 erst, wenn Phase n gegen die Referenzwerte verifiziert ist. Frag mich nur, wenn eine Entscheidung nicht aus dieser Spec ableitbar ist. Antworte kurz, keine Zusammenfassungen dessen, was du gerade getan hast – ich sehe den Diff.

## Ziel

Ein Python-CLI `wclcheck`, das für einen Warcraft-Logs-Report automatisch das macht, was ich bisher per Hand mache: meinen Hexer **Schauderbart** (Antonidas EU) pro Boss-Kill gegen 3 vergleichbare Top-Spieler derselben Spec aus den WCL-Rankings stellen und die konkreten Abweichungen ausgeben. Nur Warlock, Specs **Demonology (Diabolist)** und **Destruction (Hellcaller)**. Der Report kann ein noch laufender Live-Log sein.

Aufruf:

```
wclcheck https://www.warcraftlogs.com/reports/qCZ2bPkFVzgc46Lp
wclcheck qCZ2bPkFVzgc46Lp --player Schauderbart --fights 22          # nur ein Fight
wclcheck qCZ2bPkFVzgc46Lp --comparators 5 --ilvl-tolerance 3         # mehr Vergleich
wclcheck qCZ2bPkFVzgc46Lp --format md > raid.md                      # Markdown statt Terminal
wclcheck qCZ2bPkFVzgc46Lp --no-cache                                 # Live-Log erneut ziehen
```

## Technik

- Python 3.12, `uv` als Projekt-Tool, `pyproject.toml`, Konsolen-Skript `wclcheck`.
- Abhängigkeiten minimal: `httpx`, `pydantic`, `rich`, `typer`, `platformdirs`. Keine ORMs, keine Frameworks.
- **WCL API v2 (GraphQL)**, ausschließlich offizielle Endpunkte:
  - Token: `POST https://www.warcraftlogs.com/oauth/token` mit `grant_type=client_credentials`, Basic-Auth aus Client-ID/Secret. Token lokal cachen bis Ablauf.
  - Client-API: `https://www.warcraftlogs.com/api/v2/client`.
  - Client-ID/Secret **nie** im Code oder Repo. Lesen aus `~/.config/wclcheck/config.toml` (`[wcl] client_id = "..." client_secret = "..."`) oder Env `WCL_CLIENT_ID` / `WCL_CLIENT_SECRET`. Beim ersten Start ohne Config eine Vorlage anlegen und sauber abbrechen. `.gitignore` von Anfang an.
  - Rate-Limit beachten (Punkte pro Stunde). Alle Report-Abfragen auf Disk cachen (`platformdirs.user_cache_dir`), Schlüssel = Report-Code + Fight-ID + Query-Hash. Für Live-Reports: Fights-Liste nie länger als 60 s cachen, Events eines *abgeschlossenen* Fights dauerhaft.
- Benötigte Queries (bitte im Code als eigene Datei `queries.py`):
  - `reportData.report(code){ zone{id name} fights(killType: Encounters){ id encounterID name kill difficulty startTime endTime averageItemLevel } masterData{ actors{ id name type subType petOwner } } }`
  - `report.events(fightIDs, startTime, endTime, dataType: Casts, sourceID, includeResources: true, limit: 10000)` mit Paginierung über `nextPageTimestamp`. Wir brauchen `cast` **und** `begincast` (mit `castDuration`/Erfolg), Zeitstempel, `abilityGameID`, `targetID`.
  - `report.events(dataType: DamageDone, sourceID, ...)` inkl. Pet-Schaden (Pets über `masterData.actors.petOwner` dem Spieler zuordnen) – oder `report.table(dataType: DamageDone, sourceID, viewBy: Ability)` wenn das billiger ist; Punktekosten vergleichen und das günstigere nehmen.
  - `report.events(dataType: Resources ...)` bzw. `includeResources` für Soul Shards und Demonic-Core-Stacks (Buffs: `dataType: Buffs`).
  - `report.table(dataType: Summary, sourceID)` → `combatantInfo` für Gear/Stats/Talente (oder `events(dataType: CombatantInfo)`).
  - `worldData.encounter(id: <encounterID>){ characterRankings(className: "Warlock", specName: "Demonology"|"Destruction", difficulty: <fight.difficulty>, metric: dps, page: n) }` – liefert JSON mit `rankings[]{ name, amount, duration, server, report{code fightID}, ... }`. Genug Seiten laden, bis 3 passende Vergleichsspieler gefunden sind (Abbruch nach 5 Seiten).
- Spec-Erkennung pro Fight aus den Casts: `Hand of Gul'dan` oder `Summon Demonic Tyrant` → Demonology; `Chaos Bolt` oder `Wither`/`Immolate` → Destruction. Hero-Talent-Erkennung: `Diabolic Ritual`/`Ruination` → Diabolist, `Wither`/`Malevolence` → Hellcaller. Beides ausgeben.
- Zauber ausschließlich über **Spell-IDs** matchen, nicht über Namen (Vergleichs-Logs sind teilweise lokalisiert, z. B. Französisch). Lege `spells.py` mit einer ID-Tabelle an und ermittle die IDs beim ersten Lauf aus `masterData.abilities` des Referenz-Reports unten; Namen nur als Kommentar. Unbekannte IDs loggen, nicht raten.

## Auswahl der Vergleichsspieler

Pro Boss-Kill von Schauderbart:

1. Rankings derselben Spec, derselben Schwierigkeit, gleicher Encounter.
2. Filter: Ilvl innerhalb ±2 von Schauderbart (Parameter `--ilvl-tolerance`), Kampfdauer innerhalb ±10 %, Raidgröße 20–30, kein anonymer Report (`a:`-Codes), Region EU oder US (Parameter). Nicht Rang 1–10 nehmen (Buff-/Sonderfälle), sondern die ersten drei Treffer ab Rang 11, die den Filter bestehen.
3. Wenn nach 5 Seiten keine 3 Treffer: Toleranzen schrittweise auf ±4 Ilvl / ±20 % Dauer lockern und das in der Ausgabe kennzeichnen.
4. Jeden Vergleichsspieler mit exakt derselben Metrik-Pipeline auswerten wie Schauderbart.

## Metriken (der Kern – bitte exakt so)

Alle Metriken pro Fight, für Schauderbart **und** jeden Vergleichsspieler. „Spieler-Casts" = `cast`-Events mit `sourceID` = Spieler, **ohne** Pets und **ohne** Utility (Healthstone, Potions, Dark Pact, Unending Resolve, Burning Rush, Demonic Circle, Mortal Coil, Soulburn, Racials, Trinkets, Flask-Procs, Raid-Buffs wie Empowering Venom / Light's Potential). Diese Ausschlussliste als ID-Set in `spells.py`.

### Allgemein (beide Specs)

- Dauer, Gesamtschaden, DPS, Parse-Perzentil (aus Rankings, falls vorhanden), Ilvl.
- **Casts gesamt** und **Casts pro 30-s-Fenster** als Liste. Das ist die wichtigste Einzelkennzahl; gestern lag ich in fast jedem Fenster 1–4 Casts hinter den Vergleichsspielern (Ursache: SpellQueueWindow stand auf 50 ms).
- **Lücken**: Abstände zwischen aufeinanderfolgenden Spieler-Casts > 2,5 s: Anzahl, Summe, und die 5 größten mit Zeitstempel und „von → nach"-Zauber. Dazu `begincast`-Events ohne erfolgreichen `cast` = abgebrochene Casts zählen.
- **Reaktionszeit nach Instants**: Für jeden Instant-Cast (Demonbolt mit Core, HoG bei Demo hat Castzeit – prüfen über `begincast`; Implosion, Dreadstalker, Conflagrate, Shadowburn, Malevolence) die Zeit bis zum nächsten `begincast` bzw. nächsten Instant. Median und 90. Perzentil ausgeben. GCD-Referenz aus dem Log schätzen (kleinster beobachteter Abstand zweier Instants).
- Trank (Potion of Recklessness o. ä., als „combat potion" über Buff-Events erkennen): Anzahl und Zeitpunkte relativ zu den Cooldowns.
- Tode, Aktivzeit.
- Gear/Stats-Snapshot: Ilvl, Int, Crit, Haste, Mastery, Vers, Trinkets, Enchants, Set-Teile. Nur als Tabelle nebeneinander, keine Bewertung – gestern war Gear nachweislich nicht der Unterschied.

### Demonology (Diabolist)

Rotationsregeln aus den aktuellen Guides (Method/Kalamazi 12.1), die das Tool prüfen soll:

- Opener: (Power Siphon) → 2× Shadow Bolt / Demonbolt → Call Dreadstalkers → auf 5 Shards → Grimoire: Imp Lord → Summon Demonic Tyrant → HoG bei 3+ Shards → Demonbolt mit Cores bei < 3 Shards → Shadow Bolt. Tyrant kommt **vor** den Imps (in Midnight snapshottet der Tyrant nicht mehr; Buff „Demonic Power" +10 % pro aktivem Wild Imp/Dreadstalker, dynamisch). Tool: Zeitpunkt des ersten Tyrants und die Reihenfolge der ersten 10 Casts ausgeben und gegen die Vergleichsspieler stellen.
- **Tyrant**: Anzahl (Soll = floor(Dauer/60)+1), Zeitpunkte, Abstand zum Cooldown (Drift in s), Schaden pro Tyrant, Treffer pro Tyrant. Pro Tyrant-Fenster (15 s ab Cast): Anzahl Wild Imps + Dreadstalker aktiv (aus Summon-/Despawn-Events der Pets ableiten, Näherung zulässig), HoG-Casts im Fenster.
- **Dominion of Argus**: Nach jedem Tyrant öffnet sich ein Portal (15 s, mit Rängen bis 25 s); jede 2. HoG im Fenster beschwört einen Argus-Dämon (Antoran Jailer → Soul Barrage, Antoran Inquisitor → Mind Sear, Alythess → Blaze, Sacrolash → Shadow Nova). Tool: HoG-Casts pro Portal-Fenster, beschworene Argus-Dämonen pro Tyrant, Dominion-Gesamtschaden. Das war gestern eine der größten Lücken (9,8m vs. 12,3m auf Vashnik).
- **Hand of Gul'dan**: Casts gesamt, Shards beim Cast (aus Resource-Events): Anteil der HoG mit < 3 Shards (Fehler), Imps pro HoG (aus Pet-Summons), Wild-Imp-Feuerblitze gesamt (Casts der Pets „Wild Imp"), getrennt nach HoG-Imps und Inner-Demons-Imps.
- **Demonbolt**: Casts, Anteil Hardcasts (`begincast` mit `castDuration` > 0,5 s = Fehler), Demonic-Core-Stacks beim Cast, Core-Overcap (Stacks = 4 während ein Core-Proc kommt – aus Buff-Events, Näherung zulässig), Cores beim Kampfende verschwendet.
- **Implosion**: Casts, Imps pro Implosion (Soll ≥ 6), Shards zum Zeitpunkt der Implosion (Soll ≥ 3 zum sofortigen Nachfüllen), Implosionen im Tyrant-Fenster (kein Fehler in Midnight, aber ausgeben), Schaden Implosion + Isolated Implosion.
- **Call Dreadstalkers**: Casts, Drift zum Cooldown, Schaden. **Grimoire: Imp Lord**: Casts, Drift. **Ruination**: Casts (Soll = Tyrant-Casts + Grimoire-Casts, sofern das die Proc-Quelle ist – bitte beim ersten Lauf gegen den Referenz-Log prüfen: dort 7 Ruinations bei 5 Tyrants + 3 Grimoires). **Infernal Bolt**: Casts. **Diabolic Ritual**: Procs, Schaden pro Proc.
- Shadow Bolt: Casts als Filler-Anteil (hoch = Cores/Shards fehlen).
- Multi-Target-Bosse (Lost Explorers): Treffer pro Cast bei Wild Imp (Inner Demons), Mind Sear, Burning Cleave → „Ziele pro Cast". Gestern 2,9 vs. 3,6 bei den Vergleichsspielern – Positionierungs-/Target-Thema.

### Destruction (Hellcaller)

Regeln (Method/Kalamazi 12.1): Wither nie ablaufen lassen, im Pandemic-Fenster refreshen; Infernal und Malevolence beide on Cooldown (desynct); Shadowburn bei Fiendish-Cruelty-Proc und gegen Shard-Overcap, resettet beim Kill; Chaos Bolt gegen Overcap; Soul Fire on Cooldown, bevorzugt mit Backdraft; Conflagrate nie auf 2 Charges sitzen; Incinerate als Filler; Havoc-Fenster mit 2,5–3,5 Shards betreten; Rain of Fire nur gegen Overcap bei Hellcaller.

- **Wither**: Uptime, Casts, Refresh-Timing (Restdauer beim Refresh; Pandemic ≤ 30 % der Dauer = gut, > 50 % = zu früh, 0 = abgelaufen), Blackened-Soul-Schaden.
- **Shadowburn**: Casts, Schaden, Casts auf Ziele, die innerhalb von 5 s danach starben (Kill-Resets genutzt), Zeit auf 2 Charges. Gestern 36 Casts bei mir vs. 60–63 bei den Vergleichsspielern auf Entombed Sentinels – Hauptfehler dieses Bosses.
- **Chaos Bolt**: Casts, Casts im Malevolence-Fenster, Casts mit Havoc aktiv.
- **Conflagrate**: Casts, Zeit auf 2 Charges (verschwendete Charges).
- **Soul Fire**: Casts vs. mögliche Casts (Cooldown), Anteil mit Backdraft.
- **Malevolence / Summon Infernal**: Casts, Drift zum Cooldown, Spender im Malevolence-Fenster.
- **Havoc**: Casts, Uptime, Shards beim Cast.
- Shard-Overcap: Zeit auf 5 Shards (aus Resource-Events), Anzahl Shards, die durch Overcap verloren gingen (Näherung: Builder-Cast bei 5 Shards).
- Incinerate-Anteil an allen Casts.

## Ausgabe

Terminal (rich) und `--format md`. Pro Boss:

1. Kopfzeile: Boss, Spec/Hero, Dauer, DPS, Parse, Ilvl – Schauderbart und die 3 Vergleichsspieler nebeneinander (Name, Server, Rang, Report-Link).
2. Tabelle Kernmetriken nebeneinander; Abweichung von Schauderbart zum Median der Vergleichsspieler in %, farbig ab ±8 %.
3. Casts pro 30 s als kompakte Zeile pro Spieler.
4. **Befunde**: Nur Abweichungen über Schwellwert (Default 8 %, Parameter), sortiert nach geschätztem Schadenswert, als ein Satz pro Befund mit Zahlen, z. B. „Shadowburn: 36 Casts vs. 61 (Median) – ~7m Schaden, ~9 %". Maximal 6 Befunde pro Boss. Keine Floskeln, keine Erklärungen, die nicht aus Zahlen folgen.
5. Am Ende ein Raid-Fazit mit den 3 größten Hebeln über alle Bosse.

Alle Zahlen in deutscher Schreibweise mit Punkt als Tausender ist **nicht** nötig – englische Zahlenformate sind okay, Texte auf Deutsch.

## Referenzwerte für Regressionstests (Pflicht)

Report `qCZ2bPkFVzgc46Lp`, Spieler Schauderbart (Actor-ID 3), gestern per Hand ermittelt. Das Tool muss diese Werte innerhalb der Toleranz reproduzieren, sonst ist die Pipeline falsch:

| Fight | Boss | Spec | Dauer | Schaden | Spieler-Casts | HoG | Demonbolt | Shadow Bolt | Implosion | Dreadst. | Ruination | Tyrant | Lücken >2,5 s (Anzahl / Summe) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 22 | Vashnik the Malignant | Demo/Diabolist | 283 s | 65.13m | 229 | 71 | 47 | 66 | 16 | 14 | 7 | 5 | 13 / 37,5 s |
| 13 | Sszorak | Demo/Diabolist | 298 s | 51.82m | 223 | 69 | 50 | 49 | 17 | 15 | 7 | 5 | 17 / 53 s |
| 7 | The Lost Explorers | Demo/Diabolist | 274 s | 60.46m | 211 | 65 | 46 | 50 | 15 | 13 | 7 | 5 | 10 / 30 s |
| 2 | Nek'zali the Soulcoiler | Demo/Diabolist | 305 s | 54.65m | 223 | 67 | 47 | 57 | 15 | 15 | 7 | 5 | 15 / 49 s |
| 17 | Entombed Sentinels | Destro/Hellcaller | 388 s | 74.70m | 282 | – | – | – | – | – | – | – | 29 / 101 s |

Weitere Referenzwerte Fight 22: Tyrant-Zeitpunkte 5/71/133/195/258 s; Casts pro 30 s = 30, 23, 23, 22, 24, 23, 23, 25, 26, 10; Wild-Imp-Feuerblitze HoG 1207, Inner Demons 403; Tyrant-Schaden 7.13m; Dominion of Argus 9.83m; Isolated Implosion 3.63m; Demonbolt-Hardcasts 0; Grimoire: Imp Lord 3. Fight 17: Chaos Bolt 76, Conflagrate 56, Shadowburn 36, Incinerate 78, Wither 17, Malevolence 7, Havoc 11, Soul Fire 7, Summon Infernal 5.

Vergleichsspieler, die das Tool für Fight 22 finden sollte (oder gleichwertige): Ugofan (`NJjD4TwgHvt68LcK` f27, Actor 207, 249 Casts, Lücken 6/15 s, Casts/30 s = 34,26,25,23,29,23,26,23,24), Moriwl (`LRrFMcqQBwHnhtf4` f13, Actor 66, 251 Casts, 4/10 s), Ninesecrets (`jrAmnvY1qVLx2RQw` f21, Actor 15 – französischer Client, guter Test für ID-basiertes Matching). Für Fight 17: Eboshir (`acTXxdbjHtJGzrvq` f8, Shadowburn 60), Luthienx (`6rBAjbagwW8HQGXf` f8, Shadowburn 63).

Toleranz: Cast-Zahlen exakt; Schaden ±1 %; Lücken-Summe ±2 s (Utility-Ausschlussliste kann minimal abweichen).

## Phasen

1. **Skelett + API**: Projekt, Config, OAuth, Cache, `fights`-Query, Actor-Auflösung. Verifikation: Fight-Liste und Actor-ID 3 für Schauderbart aus dem Referenz-Report.
2. **Events + Basismetriken**: Casts, Lücken, Casts/30 s, Reaktionszeiten. Verifikation: Tabelle oben für alle 5 Fights.
3. **Spec-Metriken Demo**: Tyrant/Dominion/HoG/Implosion/Cores. Verifikation: Fight-22-Referenzwerte.
4. **Spec-Metriken Destro**: Wither/Shadowburn/Charges/Overcap. Verifikation: Fight-17-Referenzwerte.
5. **Rankings + Vergleichsspieler + Befunde**: Verifikation: Vergleichsspieler wie oben oder gleichwertig, Befund „Shadowburn 36 vs. ~61" auf Fight 17 und „Casts 229 vs. ~249" auf Fight 22 erscheinen.
6. **Ausgabe, README, Live-Modus** (Fights-Cache 60 s, offene Fights überspringen).

Nach jeder Phase: Tests laufen lassen (`pytest`, Live-Tests gegen die API hinter einem Marker, damit sie ohne Credentials übersprungen werden), dann kurz melden, was verifiziert ist, und weitermachen.

## Nicht bauen

Kein Web-Frontend, kein Ingame-Addon, keine Datenbank, keine Auswertung anderer Klassen. Keine Namens-Matches für Zauber. Keine Guides scrapen – die Rotationsregeln stehen oben und gehören als Kommentar in `analysis/rules_demo.py` bzw. `rules_destro.py`, damit ich sie beim nächsten Patch anpassen kann.
