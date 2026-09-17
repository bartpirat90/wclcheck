"""Phase-2-Regression: Basismetriken gegen die per Hand ermittelten Referenzwerte."""

import pytest

from wclcheck import spells
from wclcheck.analysis.loader import load_fight_data
from wclcheck.analysis.metrics import compute_general

pytestmark = pytest.mark.live

REF_REPORT = "qCZ2bPkFVzgc46Lp"

# fight: (dauer_s, schaden, casts, hog, demonbolt, shadow_bolt_inkl_infernal_bolt, implosion,
#         dreadstalkers, ruination, tyrant, lücken_anzahl, lücken_summe_s)
REF_DEMO = {
    22: (283, 65.13e6, 229, 71, 47, 66, 16, 14, 7, 5, 13, 37.5),
    13: (298, 51.82e6, 223, 69, 50, 57, 17, 15, 7, 5, 17, 53),
    7: (274, 60.46e6, 211, 65, 46, 57, 15, 13, 7, 5, 10, 30),
    2: (305, 54.65e6, 223, 67, 47, 64, 15, 15, 7, 5, 15, 49),
}
REF_DESTRO = {17: (388, 74.70e6, 282, 29, 101)}


@pytest.fixture(scope="module")
def metrics(live_client):
    rep = live_client.report(REF_REPORT)
    actor = rep.find_player("Schauderbart")
    out = {}
    for fid in list(REF_DEMO) + list(REF_DESTRO):
        data = load_fight_data(live_client, rep, rep.fight(fid), actor)
        out[fid] = compute_general(data)
    return out


@pytest.mark.parametrize("fid", sorted(REF_DEMO))
def test_demo_reference(metrics, fid):
    (dur, dmg, casts, hog, db, sb, imp, dread, ruin, tyr, gap_n, gap_s) = REF_DEMO[fid]
    m = metrics[fid]
    by = m.casts_by_ability
    assert m.spec.label == "Demo/Diabolist"
    assert abs(m.duration_s - dur) <= 1.5
    assert abs(m.total_damage - dmg) / dmg <= 0.01
    assert m.casts_total == casts
    assert by[spells.HAND_OF_GULDAN] == hog
    assert by[spells.DEMONBOLT] == db
    assert by[spells.SHADOW_BOLT] + by[spells.INFERNAL_BOLT] == sb
    assert by[spells.IMPLOSION] == imp
    assert by[spells.CALL_DREADSTALKERS] == dread
    assert by[spells.RUINATION] == ruin
    assert by[spells.SUMMON_DEMONIC_TYRANT] == tyr
    assert m.gaps.count == gap_n
    assert abs(m.gaps.total_s - gap_s) <= 2.0


def test_fight22_windows_and_details(metrics):
    m = metrics[22]
    assert m.casts_per_30s == [30, 23, 23, 22, 24, 23, 23, 25, 26, 10]
    assert m.casts_by_ability[spells.GRIMOIRE_IMP_LORD] == 3
    assert m.deaths == 0
    assert m.gear.ilvl and 315 <= m.gear.ilvl <= 325
    assert m.gear.intellect and m.gear.haste
    assert len(m.gear.trinkets) == 2
    assert m.reaction.gcd_estimate_s and 0.6 <= m.reaction.gcd_estimate_s <= 1.5
    assert m.reaction.median_s and m.reaction.median_s < 3


@pytest.mark.parametrize("fid", sorted(REF_DESTRO))
def test_destro_reference(metrics, fid):
    dur, dmg, casts, gap_n, gap_s = REF_DESTRO[fid]
    m = metrics[fid]
    by = m.casts_by_ability
    assert m.spec.label == "Destro/Hellcaller"
    assert abs(m.duration_s - dur) <= 1.5
    assert abs(m.total_damage - dmg) / dmg <= 0.01
    assert m.casts_total == casts
    assert m.gaps.count == gap_n
    assert abs(m.gaps.total_s - gap_s) <= 2.0
    assert by[spells.CHAOS_BOLT] == 76
    assert by[spells.CONFLAGRATE] == 56
    assert by[spells.SHADOWBURN] == 36
    assert by[spells.INCINERATE] == 78
    assert by[spells.WITHER] == 17
    assert by[spells.MALEVOLENCE] == 7
    assert by[spells.SOUL_FIRE] == 7
    assert by[spells.SUMMON_INFERNAL] == 5
    # Havoc zählt nicht als Spieler-Cast, kommt aber in all_casts vor
    assert sum(1 for c in m.all_casts if c.ability == spells.HAVOC) == 11
