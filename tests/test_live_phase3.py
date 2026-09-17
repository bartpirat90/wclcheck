"""Phase-3-Regression: Demonology-Spec-Metriken gegen die Referenzwerte (Fight 22).

Toleranz laut Spec: Zähler exakt, Schaden ±1 %, Zeitpunkte ±1 s.
"""

from __future__ import annotations

import pytest

from wclcheck.analysis import rules_demo as rules
from wclcheck.analysis.demo import compute_demo
from wclcheck.analysis.loader import load_fight_data
from wclcheck.analysis.metrics import compute_general

pytestmark = pytest.mark.live

REF_REPORT = "qCZ2bPkFVzgc46Lp"
DEMO_FIGHTS = (22, 13, 7, 2)


@pytest.fixture(scope="module")
def demo(live_client):
    rep = live_client.report(REF_REPORT)
    actor = rep.find_player("Schauderbart")
    out = {}
    for fid in DEMO_FIGHTS:
        data = load_fight_data(live_client, rep, rep.fight(fid), actor, with_damage_events=True)
        out[fid] = compute_demo(data, compute_general(data))
    return out


def rel(a: float, b: float) -> float:
    return abs(a - b) / b


# --------------------------------------------------------------- Fight 22: Pflichtwerte


def test_tyrant(demo):
    m = demo[22]
    assert m.tyrant_casts == 5
    assert m.tyrant_expected == 5
    for got, want in zip(m.tyrant_times_s, (5, 71, 133, 195, 258), strict=True):
        assert abs(got - want) <= 1.0
    assert rel(m.tyrant_damage, 7.13e6) <= 0.01
    assert m.first_tyrant_s is not None and abs(m.first_tyrant_s - 5) <= 1.0
    # Drift: 5 Casts über 283 s, der erste Abstand ist der längste (66,2 s)
    assert 10 <= m.tyrant_drift_s <= 15
    assert len(m.windows) == 5
    assert all(w.hog_casts >= 4 for w in m.windows)


def test_dominion(demo):
    m = demo[22]
    assert rel(m.dominion_damage, 9.83e6) <= 0.01
    assert m.dominion_portals == 5
    assert m.dominion_demons == 21
    # Jede 2. HoG im Portalfenster beschwört einen Dämon; Ruination ist eine
    # verstärkte HoG und zählt dabei mit (empirisch: Dämon bei 82,9 s = Ruination-Cast).
    for w in m.windows:
        assert w.portal_len_s is not None and abs(w.portal_len_s - 25.0) <= 1.0
        hog = w.portal_hog + w.portal_ruination
        assert w.portal_demons == hog // rules.ARGUS_HOG_PER_DEMON


def test_hand_of_guldan(demo):
    m = demo[22]
    assert m.hog_casts == 71
    assert m.hog_low_shard == 0  # HoG kostet 3 Shards, weniger ist nicht möglich
    assert m.hog_shards_mean is not None and 3.0 <= m.hog_shards_mean <= 5.0
    assert m.hog_imps == 234
    assert m.inner_demon_imps == 72
    # Referenzwerte der Wild-Imp-Feuerblitze (= `uses` der DamageDone-Tabelle)
    assert m.firebolts_hog == 1207
    assert m.firebolts_inner == 403
    assert m.firebolt_hits_hog == 1245
    assert m.firebolt_hits_inner == 741


def test_demonbolt_und_cores(demo):
    m = demo[22]
    assert m.demonbolt_casts == 47
    assert m.demonbolt_hardcasts == 0
    assert m.core_max_seen == rules.DEMONIC_CORE_MAX_STACKS
    assert m.core_stacks_mean is not None and 1.0 <= m.core_stacks_mean <= 3.0
    assert m.core_overcap == 5
    assert m.cores_at_end == 0


def test_implosion(demo):
    m = demo[22]
    assert m.implosion_casts == 16
    assert rel(m.isolated_implosion_damage, 3.63e6) <= 0.01
    assert rel(m.implosion_damage, 740_476) <= 0.01
    assert m.imps_per_implosion is not None
    assert m.imps_per_implosion >= rules.IMPLOSION_MIN_IMPS
    assert m.implosion_shards_mean is not None and 0.0 <= m.implosion_shards_mean <= 5.0
    assert m.implosions_in_tyrant == 5


def test_cooldowns_und_diabolist(demo):
    m = demo[22]
    assert m.dreadstalker_casts == 14
    assert m.dreadstalker_expected == 15
    assert 5 <= m.dreadstalker_drift_s <= 20
    assert m.grimoire_casts == 3
    assert m.grimoire_expected == 3
    assert m.ruination_casts == 7
    # Proc-Quelle ist die Pit-Lord-Beschwörung, nicht Tyrant + Grimoire (das wären 8).
    assert m.ruination_expected == 7
    assert m.tyrant_casts + m.grimoire_casts == 8
    assert m.infernal_bolt_casts == 7
    assert m.infernal_bolt_expected == 7
    assert m.ritual_procs == 22
    assert rel(m.ritual_damage, 5.85e6) <= 0.01


def test_filler_und_ziele(demo):
    m = demo[22]
    assert m.shadow_bolt_casts == 59
    assert 20 <= m.filler_pct <= 35
    assert m.targets_inner_demons is not None and abs(m.targets_inner_demons - 1.84) <= 0.05
    assert m.targets_mind_sear is not None and m.targets_mind_sear >= 1.0
    assert m.targets_burning_cleave is not None and m.targets_burning_cleave >= 1.0
    assert m.shard_waste == 1


def test_rows_sind_vollstaendig_und_benannt(demo):
    rows = demo[22].rows()
    keys = [r.key for r in rows]
    assert len(keys) == len(set(keys))
    assert all(k.startswith("demo.") for k in keys)
    assert all(r.label for r in rows)
    for key in ("demo.tyrant.casts", "demo.dominion.damage", "demo.hog.casts",
                "demo.implosion.damage", "demo.ruination.casts", "demo.filler.pct"):
        assert key in keys
    by_key = {r.key: r for r in rows}
    assert by_key["demo.tyrant.casts"].value == 5
    assert by_key["demo.dominion.damage"].formatted() == "9.83m"
    assert by_key["demo.implosion.imps"].better == "higher"
    assert by_key["demo.core.overcap"].better == "lower"


# ------------------------------------------------------- Plausibilität Fights 13/7/2


@pytest.mark.parametrize("fid", DEMO_FIGHTS)
def test_grundplausibilitaet(demo, fid):
    m = demo[fid]
    assert m.tyrant_casts == 5
    assert m.ruination_casts == 7
    assert m.ruination_expected == m.ruination_casts
    assert m.infernal_bolt_expected == m.infernal_bolt_casts
    assert m.grimoire_casts == 3
    assert m.demonbolt_hardcasts == 0
    assert m.hog_low_shard == 0
    assert m.dominion_portals == m.tyrant_casts
    assert m.core_max_seen == rules.DEMONIC_CORE_MAX_STACKS
    assert m.hog_imps >= m.hog_casts * rules.IMPS_PER_HOG_BASE
    assert m.imps_per_implosion is not None and m.imps_per_implosion >= 5
    assert m.dominion_damage > 5e6
    assert len(m.opener) == 10


def test_lost_explorers_ist_multi_target(demo):
    """Fight 7 ist der Multi-Target-Boss: mehr Ziele pro Fel Firebolt als sonst."""
    assert demo[7].targets_inner_demons is not None
    assert demo[7].targets_inner_demons > demo[13].targets_inner_demons


def test_nekzali_verpasst_einen_tyrant(demo):
    """Fight 2 dauert 305 s, das Soll ist damit 6 Tyrants – gecastet wurden 5."""
    m = demo[2]
    assert m.tyrant_expected == 6
    assert m.tyrant_casts == 5
