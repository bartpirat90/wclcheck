"""Rotationsregeln und abgeleitete Konstanten für Demonology (Diabolist).

Die Regeln stehen bewusst als Kommentarblock hier, damit sie beim nächsten Patch an
einer Stelle angepasst werden können. Alles darunter sind die daraus abgeleiteten
Zahlen, die `analysis/demo.py` benutzt – kein Code, der Regeln neu interpretiert.

===============================================================================
ROTATIONSREGELN (Method / Kalamazi 12.1, Stand Midnight)
===============================================================================

Opener
  (Power Siphon) -> 2x Shadow Bolt / Demonbolt -> Call Dreadstalkers -> auf 5 Shards
  -> Grimoire: Imp Lord -> Summon Demonic Tyrant -> Hand of Gul'dan bei 3+ Shards
  -> Demonbolt mit Cores bei < 3 Shards -> Shadow Bolt.
  Der Tyrant kommt VOR den Imps: in Midnight snapshottet er nicht mehr, sondern
  gibt "Demonic Power" (+10 % pro aktivem Wild Imp / Dreadstalker, dynamisch).

Tyrant
  On Cooldown (60 s). Soll-Anzahl = floor(Kampfdauer / 60) + 1.
  Bewertungsfenster 15 s ab Cast: möglichst viele aktive Dämonen, HoG hineinpressen.

Dominion of Argus
  Nach jedem Tyrant öffnet sich ein Portal. Jede 2. HoG im Fenster beschwört einen
  Argus-Dämon (Antoran Jailer -> Soul Barrage, Antoran Inquisitor -> Mind Sear,
  Grand Warlock Alythess -> Blaze, Lady Sacrolash -> Shadow Nova).
  Ziel: möglichst viele HoG ins Portalfenster, damit möglichst viele Dämonen kommen.

Hand of Gul'dan
  Nur ab 3 Shards (kostet 3). Jede HoG beschwört 3 Wild Imps (Talente können mehr
  geben – im Referenz-Log ~3,3 pro Cast).

Demonbolt
  Nur mit Demonic Core (dann instant). Ein Demonbolt ohne Core ist ein Hardcast und
  damit ein Fehler. Cores nicht auf Maximum stehen lassen (Overcap), am Kampfende
  keine Cores übrig lassen.

Implosion
  Ab ~6 aktiven Imps, und nur mit >= 3 Shards, damit sofort wieder HoG folgen kann.
  Implosionen im Tyrant-Fenster sind in Midnight kein Fehler mehr (nur ausgeben).

Call Dreadstalkers / Grimoire: Imp Lord
  Beide on Cooldown, Drift minimieren.

Ruination
  Wird durch die Beschwörung des Pit Lord aus dem Diabolic Ritual freigeschaltet
  (siehe RUINATION_SOURCE unten) und soll immer sofort verbraucht werden.

Infernal Bolt
  Wird durch die Beschwörung der Mother of Chaos freigeschaltet und ersetzt den
  nächsten Shadow Bolt. Immer verbrauchen.

Shadow Bolt
  Reiner Filler. Ein hoher Anteil bedeutet, dass Cores oder Shards fehlen.

Multi-Target (z. B. Lost Explorers)
  Ziele pro Cast bei Fel Firebolt der Inner-Demons-Imps, Mind Sear und Burning
  Cleave – niedrige Werte sind ein Positionierungs-/Targetproblem.

===============================================================================
"""

from __future__ import annotations

# --------------------------------------------------------------------------- Cooldowns
# Alle Cooldowns zusätzlich aus dem Referenz-Log gegengeprüft (kleinster Abstand
# zweier aufeinanderfolgender Casts in qCZ2bPkFVzgc46Lp Fight 22):
#   Tyrant        62,0 s  -> 60 s
#   Dreadstalkers 20,1 s  -> 20 s
#   Grimoire     124,0 s  -> 120 s (nur 3 Casts, daher die unsicherste Schätzung)
# Implosion hat keinen Cooldown (kleinster beobachteter Abstand 15,1 s ist reine
# Rotation), deshalb steht hier keine Zahl.
TYRANT_COOLDOWN_S = 60.0
DREADSTALKER_COOLDOWN_S = 20.0
GRIMOIRE_COOLDOWN_S = 120.0

# Drift unterhalb dieser Schwelle gilt als Rundungsrauschen (Reaktionszeit/GCD) und
# wird nicht als verlorene Zeit gewertet.
DRIFT_TOLERANCE_S = 0.5

# --------------------------------------------------------------------------- Fenster
# Bewertungsfenster ab dem Tyrant-Cast.
TYRANT_WINDOW_S = 15.0
# Portalfenster von Dominion of Argus: Basis 15 s, mit Rängen bis 25 s. Im
# Referenz-Log misst der Buff 1276166 konstant 25,0 s. `demo.py` misst die Länge
# primär aus den Buff-Events und benutzt diesen Wert nur als Rückfallebene.
DOMINION_PORTAL_S = 25.0
# Anzahl HoG im Portalfenster pro beschworenem Argus-Dämon.
ARGUS_HOG_PER_DEMON = 2

# --------------------------------------------------------------------------- Sollwerte
HOG_MIN_SHARDS = 3.0  # entspricht zugleich den Kosten -> < 3 kann im Log nicht auftreten
IMPLOSION_MIN_IMPS = 6
IMPLOSION_MIN_SHARDS = 3.0
DEMONIC_CORE_MAX_STACKS = 4  # aus den Buff-Events bestätigt (Maximum 4)
IMPS_PER_HOG_BASE = 3  # Talente können mehr geben (Referenz-Log ~3,3)

# --------------------------------------------------------------------------- Näherungen
# Wild-Imp-Lebensdauer: Despawn-Events liefert die API nicht. Ein Imp gilt ab seinem
# Summon-Event als aktiv und bis zu seinem letzten Fel-Firebolt-Treffer plus dieser
# Karenz (rund ein Firebolt-Intervall – im Referenz-Log ~1,3 s bei 6-7 Bolts auf
# ~8 s Lebenszeit). Damit zählen auch Imps mit, die eine Implosion verschluckt hat.
IMP_BOLT_GRACE_MS = 1000
# Harte Obergrenze der Lebenszeit, damit ein fehlender Treffer keinen Dauer-Imp erzeugt.
IMP_MAX_LIFETIME_MS = 20_000
# Abtastweite für die mittlere Anzahl aktiver Dämonen in einem Fenster.
ACTIVE_SAMPLE_MS = 500
# "Ziele pro Cast": Pet-Casts liefert die WCL-API nicht. Wo die DamageDone-Tabelle ein
# `uses` mitliefert (Fel Firebolt), wird exakt Treffer/Casts gerechnet. Sonst werden
# Treffer desselben (sourceID, sourceInstance) innerhalb dieses Fensters zu einem Cast
# zusammengefasst.
MULTI_TARGET_CLUSTER_MS = 50

# --------------------------------------------------------------------------- Ruination
# Proc-Quelle empirisch bestimmt (qCZ2bPkFVzgc46Lp Fight 22):
#   Summon Pit Lord (434400)   : 33,3 / 80,0 / 113,8 / 145,7 / 189,8 / 224,6 / 261,6 s
#   Buff "Ruination" (433885)  : 33,4 / 80,1 / 113,9 / 145,8 / 189,9 / 224,7 / 261,7 s
#   Ruination-Casts (434635)   : 35,6 / 82,9 / 116,9 / 148,2 / 196,6 / 227,6 / 263,7 s
# Der Buff folgt jeder Pit-Lord-Beschwörung nach 0,1 s; zu Tyrant (5/71/133/195/258 s)
# und Grimoire (0,9/128,7/252,8 s) gibt es keinen solchen Zusammenhang, und deren Summe
# wäre 8 statt der beobachteten 7. Das Soll ist deshalb die Anzahl der Pit-Lord-
# Beschwörungen aus dem Diabolic Ritual, nicht Tyrant + Grimoire.
RUINATION_SOURCE = "Summon Pit Lord (Diabolic Ritual)"
# Analog: Infernal Bolt wird von "Summon Mother of Chaos" freigeschaltet
# (Buff 433891 zeitgleich mit 428565: 22,5 / 61,8 / 98,9 / 138,4 / 174,1 / 212,4 / 249,4 s).
INFERNAL_BOLT_SOURCE = "Summon Mother of Chaos (Diabolic Ritual)"


def expected_casts(duration_s: float, cooldown_s: float) -> int:
    """Soll-Anzahl eines Cooldowns über die Kampfdauer: floor(Dauer / CD) + 1."""
    if cooldown_s <= 0:
        return 0
    return int(duration_s // cooldown_s) + 1
