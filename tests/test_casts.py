"""Synthetische Events für die Cast-Basismetriken."""

from wclcheck import spells
from wclcheck.analysis.casts import (
    active_time_s,
    casts_per_window,
    count_by_ability,
    find_gaps,
    parse_casts,
    player_casts,
    reaction_times,
)

START = 1_000_000
ME = 3


def bc(t, ability, src=ME):
    return {"timestamp": START + t, "type": "begincast", "sourceID": src,
            "targetID": -1, "abilityGameID": ability}


def cast(t, ability, src=ME, shards=None, cost=None):
    ev = {"timestamp": START + t, "type": "cast", "sourceID": src,
          "targetID": 250, "abilityGameID": ability}
    if shards is not None:
        ev["classResources"] = [{"amount": shards * 10, "max": 50, "type": 7,
                                 **({"cost": cost * 10} if cost is not None else {})}]
    return ev


def test_pairing_durations_and_shards():
    events = [
        bc(0, spells.SHADOW_BOLT), cast(1200, spells.SHADOW_BOLT),
        cast(2700, spells.DEMONBOLT),  # Instant ohne begincast
        bc(4000, spells.HAND_OF_GULDAN), cast(5000, spells.HAND_OF_GULDAN, shards=5, cost=3),
        cast(6000, 108416),  # Dark Pact (Utility, off-GCD)
    ]
    casts, cancelled = parse_casts(events, ME)
    assert cancelled == []
    assert [c.ability for c in casts] == [spells.SHADOW_BOLT, spells.DEMONBOLT,
                                          spells.HAND_OF_GULDAN, 108416]
    assert casts[0].duration_ms == 1200 and not casts[0].instant
    assert casts[1].instant and casts[1].begin is None
    assert casts[2].shards == 5.0 and casts[2].shard_cost == 3.0
    assert casts[0].shards is None


def test_cancelled_detection():
    events = [
        bc(0, spells.SHADOW_BOLT),            # abgebrochen durch neuen begincast
        bc(500, spells.HAND_OF_GULDAN), cast(1500, spells.HAND_OF_GULDAN),
        bc(2000, spells.SHADOW_BOLT),         # abgebrochen durch Instant
        cast(2400, spells.IMPLOSION),
        bc(3000, spells.SHADOW_BOLT),         # Off-GCD Utility unterbricht nicht
        cast(3300, 104773),                   # Unending Resolve
        cast(4200, spells.SHADOW_BOLT),
        bc(5000, spells.DEMONBOLT),           # bis Ende offen
    ]
    casts, cancelled = parse_casts(events, ME)
    assert [(c.ability, c.reason) for c in cancelled] == [
        (spells.SHADOW_BOLT, "begincast"),
        (spells.SHADOW_BOLT, "cast"),
        (spells.DEMONBOLT, "end"),
    ]
    assert [c.ability for c in casts] == [spells.HAND_OF_GULDAN, spells.IMPLOSION,
                                          104773, spells.SHADOW_BOLT]
    assert casts[-1].duration_ms == 1200


def test_ignores_other_sources():
    events = [cast(0, spells.SHADOW_BOLT, src=4), cast(100, spells.SHADOW_BOLT)]
    casts, _ = parse_casts(events, ME)
    assert len(casts) == 1


def test_player_casts_excludes_utility_and_havoc(caplog):
    events = [
        cast(0, spells.CHAOS_BOLT), cast(1000, spells.HAVOC), cast(2000, 108416),
        cast(3000, 999_999), cast(4000, spells.INCINERATE),
    ]
    casts, _ = parse_casts(events, ME)
    with caplog.at_level("WARNING", logger="wclcheck.casts"):
        pc = player_casts(casts)
    assert [c.ability for c in pc] == [spells.CHAOS_BOLT, 999_999, spells.INCINERATE]
    assert "999999" in caplog.text
    assert count_by_ability(pc)[spells.CHAOS_BOLT] == 1


def test_windows_and_gaps():
    times = [0, 1000, 2000, 31_000, 35_000, 59_000, 65_000]
    events = [cast(t, spells.SHADOW_BOLT) for t in times]
    casts, _ = parse_casts(events, ME)
    assert casts_per_window(casts, START, START + 66_000) == [3, 3, 1]
    gaps = find_gaps(casts, START, threshold_s=2.5, top=3)
    assert gaps.count == 4
    assert gaps.total_s == 29 + 4 + 24 + 6
    assert [g.length_s for g in gaps.largest] == [29.0, 24.0, 6.0]
    assert gaps.largest[0].length_s == 29.0
    assert gaps.largest[0].start_s == 2.0
    assert gaps.largest[0].from_ability == spells.SHADOW_BOLT


def test_reaction_times_and_gcd():
    events = [
        cast(0, spells.DEMONBOLT),
        cast(750, spells.IMPLOSION),                       # Instant → Instant 0,75 s (GCD)
        bc(1550, spells.SHADOW_BOLT), cast(2800, spells.SHADOW_BOLT),  # Reaktion 0,8 s
        cast(2900, spells.DEMONBOLT),
        cast(4900, spells.IMPLOSION),                      # 2,0 s Reaktion
    ]
    casts, _ = parse_casts(events, ME)
    rs = reaction_times(casts)
    assert rs.n == 3
    assert rs.gcd_estimate_s == 0.75
    assert rs.median_s == 0.8
    assert rs.p90_s > 1.5
    assert 0 < active_time_s(casts, 4.9, rs.gcd_estimate_s) <= 4.9
