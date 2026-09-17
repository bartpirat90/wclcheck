"""Unit-Tests der Demo-Kernlogik mit synthetischen Events (keine API)."""

from __future__ import annotations

import pytest

from wclcheck import spells
from wclcheck.analysis import rules_demo as rules
from wclcheck.analysis.demo import (
    active_at,
    buff_windows,
    drifts,
    mean_active,
    pet_spans,
    shard_timeline,
    shards_before,
    table_damage,
    table_uses_hits,
    targets_per_cast,
    track_core,
)

CORE = spells.DEMONIC_CORE_BUFF
PORTAL = spells.DOMINION_OF_ARGUS_PORTAL_BUFF


def buff(ts: int, kind: str, ability: int = CORE, stack: int | None = None) -> dict:
    ev = {"timestamp": ts, "type": kind, "abilityGameID": ability, "targetID": 3}
    if stack is not None:
        ev["stack"] = stack
    return ev


# --------------------------------------------------------------------------- Drift


def test_drift_ignoriert_rauschen_und_summiert_verlust():
    # 60 s Cooldown: 60,2 s liegt in der Toleranz, 66,2 s kostet 6,2 s.
    times = [0, 60_200, 126_400]
    assert drifts(times, 60.0) == pytest.approx([0.0, 6.2])


def test_drift_ohne_paare():
    assert drifts([1000], 60.0) == []


def test_expected_casts():
    assert rules.expected_casts(283.0, 60.0) == 5
    assert rules.expected_casts(305.0, 60.0) == 6
    assert rules.expected_casts(283.0, 20.0) == 15


# --------------------------------------------------------------------- Demonic Core


def test_core_stacks_und_overcap():
    events = [
        buff(1000, "applybuff"),
        buff(2000, "applybuffstack", stack=2),
        buff(3000, "applybuffstack", stack=3),
        buff(4000, "applybuffstack", stack=4),
        buff(4500, "refreshbuff"),  # Overcap: Stacks stehen auf dem Maximum
        buff(5000, "removebuffstack", stack=3),
        buff(5100, "refreshbuff"),  # kein Overcap
        buff(6000, "removebuff"),
    ]
    track = track_core(events)
    assert track.max_seen == 4
    assert track.overcap == 1
    # Stacks VOR dem Zeitpunkt: ein Event auf derselben ms zählt noch nicht.
    assert track.stacks_before(5000) == 4
    assert track.stacks_before(5001) == 3
    assert track.stacks_before(500) == 0
    assert track.stacks_at_end(9999) == 0


def test_core_am_kampfende_bleibt_stehen():
    events = [buff(1000, "applybuff"), buff(2000, "applybuffstack", stack=2)]
    track = track_core(events)
    assert track.stacks_at_end(99_000) == 2


def test_core_ignoriert_fremde_buffs():
    events = [buff(1000, "applybuff", ability=12345), buff(2000, "refreshbuff", ability=12345)]
    track = track_core(events)
    assert track.timeline == []
    assert track.overcap == 0


# --------------------------------------------------------------------- Portalfenster


def test_portal_fenster_aus_buff_events():
    events = [
        buff(1000, "applybuff", ability=PORTAL),
        buff(5000, "applybuffstack", ability=PORTAL, stack=2),
        buff(26_000, "removebuff", ability=PORTAL),
        buff(60_000, "applybuff", ability=PORTAL),
    ]
    windows = buff_windows(events, PORTAL, fight_end=80_000)
    assert windows == [(1000, 26_000), (60_000, 80_000)]


def test_portal_fenster_zaehlt_hog_und_daemonen():
    events = [
        buff(0, "applybuff", ability=PORTAL),
        buff(25_000, "removebuff", ability=PORTAL),
    ]
    (start, end), = buff_windows(events, PORTAL, fight_end=30_000)
    hog = [1_000, 5_000, 24_000, 26_000]
    assert sum(1 for t in hog if start <= t <= end) == 3


# -------------------------------------------------------------------- Shard-Timeline


def cast(ts: int, ability: int, amount: int | None = None, cost: int = 0) -> dict:
    ev = {"timestamp": ts, "type": "cast", "sourceID": 3, "abilityGameID": ability}
    if amount is not None:
        ev["classResources"] = [{"type": 7, "amount": amount, "max": 50, "cost": cost}]
    return ev


def gain(ts: int, amount: int, ability: int = spells.SHADOW_BOLT, waste: int = 0) -> dict:
    return {
        "timestamp": ts,
        "type": "resourcechange",
        "sourceID": 3,
        "abilityGameID": ability,
        "resourceChange": amount,
        "resourceChangeType": 7,
        "waste": waste,
    }


def test_shard_timeline_folgt_ankern_und_gewinnen():
    casts = [
        cast(1000, spells.HAND_OF_GULDAN, amount=50, cost=30),  # 5 Shards vor dem Cast
        cast(4000, spells.IMPLOSION),  # kostet nichts, kein Anker
        cast(6000, spells.HAND_OF_GULDAN, amount=30, cost=30),
    ]
    resources = [gain(3000, 1)]
    tl = shard_timeline(casts, resources, actor_id=3)
    # Nach HoG: 5 - 3 = 2, dann +1 = 3, Anker bei 6000 bestätigt 3 -> 0
    assert [v for _, v in tl] == [2.0, 3.0, 0.0]
    assert shards_before(tl, 4000) == 3.0
    assert shards_before(tl, 1000) is None


def test_shard_timeline_deckelt_bei_fuenf():
    tl = shard_timeline([cast(0, spells.HAND_OF_GULDAN, amount=50, cost=0)], [gain(10, 3)], 3)
    assert tl[-1][1] == 5.0


def test_shard_timeline_ignoriert_fremde_quellen():
    tl = shard_timeline([cast(0, spells.HAND_OF_GULDAN, amount=50, cost=30)], [], actor_id=99)
    assert tl == []


# -------------------------------------------------------------------------- Pet-Spans


def summon(ts: int, ability: int, pet: int, instance: int) -> dict:
    return {
        "timestamp": ts,
        "type": "summon",
        "sourceID": 3,
        "targetID": pet,
        "targetInstance": instance,
        "abilityGameID": ability,
    }


def hit(ts: int, pet: int, instance: int, ability: int = spells.FEL_FIREBOLT) -> dict:
    return {
        "timestamp": ts,
        "type": "damage",
        "sourceID": pet,
        "sourceInstance": instance,
        "abilityGameID": ability,
        "amount": 100,
    }


def test_imp_spans_enden_am_letzten_feuerblitz_plus_karenz():
    summons = [
        summon(0, spells.WILD_IMP_HOG_SUMMON, 7, 1),
        summon(0, spells.WILD_IMP_HOG_SUMMON, 7, 2),
        summon(10_000, spells.WILD_IMP_HOG_SUMMON, 7, 3),
    ]
    damage = [hit(1000, 7, 1), hit(5000, 7, 1), hit(2000, 7, 2), hit(11_000, 7, 3)]
    spans = pet_spans(summons, damage, [spells.WILD_IMP_HOG_SUMMON],
                      damage_ability=spells.FEL_FIREBOLT)
    grace = rules.IMP_BOLT_GRACE_MS
    # pet_spans liefert nach (Start, Ende) sortiert
    assert spans == [(0, 2000 + grace), (0, 5000 + grace), (10_000, 11_000 + grace)]
    # Imp 1 lebt noch bei 5,5 s, Imp 2 nicht mehr.
    assert active_at(spans, 5_500) == 1
    assert active_at(spans, 500) == 2
    assert active_at(spans, 10_500) == 1


def test_imp_ohne_treffer_lebt_nur_die_karenz():
    spans = pet_spans([summon(0, spells.WILD_IMP_HOG_SUMMON, 7, 1)], [],
                      [spells.WILD_IMP_HOG_SUMMON], damage_ability=spells.FEL_FIREBOLT)
    assert spans == [(0, rules.IMP_BOLT_GRACE_MS)]


def test_pet_span_wird_bei_maximaler_lebensdauer_gekappt():
    spans = pet_spans(
        [summon(0, spells.WILD_IMP_HOG_SUMMON, 7, 1)],
        [hit(100_000, 7, 1)],
        [spells.WILD_IMP_HOG_SUMMON],
        damage_ability=spells.FEL_FIREBOLT,
    )
    assert spans == [(0, rules.IMP_MAX_LIFETIME_MS)]


def test_mean_active_mittelt_ueber_das_fenster():
    # Abtastung alle 0,5 s an 20 Stellen (0 … 9,5 s); das kurze Pet deckt 11 davon ab.
    spans = [(0, 5_000), (0, 10_000)]
    assert mean_active(spans, 0, 10_000) == pytest.approx(31 / 20)
    assert mean_active([(0, 10_000)], 0, 10_000) == 1.0


# ------------------------------------------------------------------- Multi-Target


def test_targets_per_cast_fasst_gleichzeitige_treffer_zusammen():
    # Zwei Casts derselben Instanz mit je 2 Zielen plus ein Cast einer zweiten Instanz.
    damage = [
        hit(0, 119, 1, spells.MIND_SEAR),
        hit(20, 119, 1, spells.MIND_SEAR),
        hit(2000, 119, 1, spells.MIND_SEAR),
        hit(2030, 119, 1, spells.MIND_SEAR),
        hit(10, 119, 2, spells.MIND_SEAR),
    ]
    hits, casts = targets_per_cast(damage, spells.MIND_SEAR)
    assert (hits, casts) == (5, 3)


def test_targets_per_cast_ohne_events():
    assert targets_per_cast(None, spells.MIND_SEAR) == (0, 0)


# ------------------------------------------------------------------ Schadenstabelle


TABLE = [
    {"guid": 686, "name": "Shadow Bolt", "total": 2_836_666, "uses": 59, "hitCount": 65,
     "subentries": [
         {"guid": 686, "name": "Shadow Bolt", "total": 1_565_529, "uses": 59, "hitCount": 58},
         {"guid": 434506, "name": "Infernal Bolt", "total": 1_271_137, "uses": 7, "hitCount": 7},
     ]},
    {"guid": 104317, "name": "Wild Imp (HoG)", "total": 6_103_717, "uses": 1207,
     "hitCount": 1245},
]


def test_table_damage_top_und_subentry():
    assert table_damage(TABLE, 686) == 2_836_666
    assert table_damage(TABLE, 686, sub_only=True) == 1_565_529
    assert table_damage(TABLE, 434506) == 1_271_137
    assert table_damage(TABLE, 999) == 0


def test_table_uses_hits():
    assert table_uses_hits(TABLE, 104317) == (1207, 1245)
    assert table_uses_hits(TABLE, 434506) == (7, 7)
    assert table_uses_hits(TABLE, 999) == (None, 0)
