"""Phase-4-Regression: Destro-(Hellcaller-)Metriken gegen Fight 17 des Referenz-Reports."""

import pytest

from wclcheck import spells
from wclcheck.analysis import rules_destro as rules
from wclcheck.analysis.destro import compute_destro
from wclcheck.analysis.loader import load_fight_data
from wclcheck.analysis.metrics import compute_general

pytestmark = pytest.mark.live

REF_REPORT = "qCZ2bPkFVzgc46Lp"
REF_FIGHT = 17  # Entombed Sentinels, Destro/Hellcaller, 388 s, 74.70m

# Per Hand ermittelte Cast-Zahlen (Toleranz: exakt)
REF_CASTS = {
    spells.CHAOS_BOLT: 76,
    spells.CONFLAGRATE: 56,
    spells.SHADOWBURN: 36,
    spells.INCINERATE: 78,
    spells.WITHER: 17,
    spells.MALEVOLENCE: 7,
    spells.SOUL_FIRE: 7,
    spells.SUMMON_INFERNAL: 5,
}


@pytest.fixture(scope="module")
def destro(live_client):
    rep = live_client.report(REF_REPORT)
    actor = rep.find_player("Schauderbart")
    fight = rep.fight(REF_FIGHT)
    # damage_events werden für die Trennung von Blackened Soul und Wither gebraucht.
    data = load_fight_data(live_client, rep, fight, actor, with_damage_events=True)
    general = compute_general(data)
    return data, general, compute_destro(data, general)


def test_reference_cast_counts(destro):
    _, general, m = destro
    by = general.casts_by_ability
    assert general.spec.label == "Destro/Hellcaller"
    assert general.casts_total == 282
    for spell_id, expected in REF_CASTS.items():
        assert by[spell_id] == expected, spells.name(spell_id)
    assert m.chaos_bolt_casts == 76
    assert m.conflagrate_casts == 56
    assert m.shadowburn_casts == 36
    assert m.incinerate_casts == 78
    assert m.wither_casts == 17
    assert m.malevolence_casts == 7
    assert m.soul_fire_casts == 7
    assert m.infernal_casts == 5
    # Havoc zählt nicht als Spieler-Cast, wird aber als eigene Destro-Metrik geführt.
    assert m.havoc_casts == 11


def test_wither(destro):
    _, _, m = destro
    assert 80.0 <= m.wither_uptime_pct <= 100.0
    assert 80.0 <= m.wither_uptime_best_pct <= 100.0
    w = m.wither_refresh
    assert w.total > 0
    assert w.pandemic + w.too_early + w.expired <= w.total
    # Alle Restdauern bleiben im Modellrahmen (0 … 130 % der Basisdauer).
    assert all(0.0 <= r <= rules.WITHER_MAX_DURATION_S + 1e-6 for r in w.remaining_s)
    assert m.wither_damage > 0
    assert m.blackened_soul_damage and m.blackened_soul_damage > 0
    assert m.blackened_soul_damage < m.wither_damage


def test_shadowburn(destro):
    _, _, m = destro
    assert m.shadowburn_damage > 0
    # 4 Casts auf Adds, die innerhalb von 5 s starben (Venom Coagulation).
    assert m.shadowburn_kill_resets == 4
    # Hauptbefund dieses Bosses: mit 36 statt 60+ Casts steht Shadowburn den Großteil
    # des Kampfes auf voller Ladung.
    assert m.shadowburn_cap_time_s > 100.0


def test_chaos_bolt_and_havoc(destro):
    _, _, m = destro
    assert m.chaos_bolt_damage > 0
    assert m.chaos_bolt_in_malevolence > 0
    assert m.chaos_bolt_in_malevolence <= m.chaos_bolt_casts
    assert m.chaos_bolt_with_havoc > 0
    assert m.chaos_bolt_with_havoc <= m.chaos_bolt_casts
    # 11 Havoc-Casts à 20 s Debuff plus ein Pre-Pull-Rest → gut 60 % Uptime.
    assert 50.0 <= m.havoc_uptime_pct <= 70.0
    assert len(m.havoc_shards) == m.havoc_casts


def test_cooldowns_and_spenders(destro):
    _, general, m = destro
    # 7 Malevolence und 5 Infernals sind auf 388 s genau die per CD möglichen Casts.
    assert m.malevolence_casts == m.malevolence_possible
    assert m.infernal_casts == m.infernal_possible
    assert m.malevolence_drift_s > 0
    assert m.infernal_drift_s < m.malevolence_drift_s
    assert m.spenders_in_malevolence > 0
    assert m.spenders_in_malevolence <= m.chaos_bolt_casts + m.shadowburn_casts
    assert 0 <= m.soul_fire_with_backdraft <= m.soul_fire_casts
    assert m.soul_fire_possible >= m.soul_fire_casts


def test_shards_and_filler(destro):
    _, general, m = destro
    assert m.overcap.snapshots > 0
    assert m.overcap.cap_snapshots > 0
    assert m.overcap.time_at_cap_s > 0
    assert m.overcap.lost_shards > 0
    assert m.incinerate_share_pct == pytest.approx(100.0 * 78 / 282, abs=0.01)
    assert m.conflagrate_cap_time_s >= 0.0


def test_rows_are_wellformed(destro):
    _, _, m = destro
    rows = m.rows()
    keys = [r.key for r in rows]
    assert len(keys) == len(set(keys))
    assert all(k.startswith("destro.") for k in keys)
    assert all(r.label for r in rows)
    # Die Kennzahlen, auf die es bei diesem Boss ankommt, sind gefüllt.
    values = {r.key: r.value for r in rows}
    assert values["destro.shadowburn.casts"] == 36
    assert values["destro.chaos_bolt.casts"] == 76
    assert values["destro.wither.uptime"] is not None
    assert values["destro.havoc.uptime"] is not None
