"""Unit-Tests der Destro-Kernlogik mit synthetischen Events (keine API)."""

from __future__ import annotations

import pytest

from wclcheck import spells
from wclcheck.analysis import rules_destro as rules
from wclcheck.analysis.casts import Cast
from wclcheck.analysis.destro import (
    aura_intervals,
    charge_cap_time_s,
    classify_wither_refreshes,
    cooldown_drift_s,
    debuff_intervals_by_target,
    in_any,
    kill_reset_casts,
    last_known_shards,
    merge,
    possible_casts,
    shard_overcap,
    total_ms,
)

S = 1000  # eine Sekunde in ms


def debuff(ts_s: float, kind: str, target: int = 10, instance: int | None = None,
           ability: int = spells.WITHER_DEBUFF) -> dict:
    return {
        "timestamp": int(ts_s * S),
        "type": kind,
        "abilityGameID": ability,
        "targetID": target,
        "targetInstance": instance,
    }


def buff(ts_s: float, kind: str, ability: int) -> dict:
    return {"timestamp": int(ts_s * S), "type": kind, "abilityGameID": ability}


def cast(ts_s: float, ability: int, target: int = 10, shards: float | None = None,
         cost: float | None = None) -> Cast:
    return Cast(t=int(ts_s * S), ability=ability, target=target, shards=shards, shard_cost=cost)


# --------------------------------------------------------------------------- Intervalle
def test_aura_intervals_basics():
    evs = [buff(2, "applybuff", 1), buff(5, "removebuff", 1)]
    assert aura_intervals(evs, 1, 0, 10 * S) == [(2 * S, 5 * S)]


def test_aura_intervals_prepull_and_open_end():
    """remove ohne apply zählt ab Kampfbeginn, ein offener Buff bis Kampfende."""
    evs = [buff(3, "removebuff", 1), buff(8, "applybuff", 1)]
    assert aura_intervals(evs, 1, 0, 10 * S) == [(0, 3 * S), (8 * S, 10 * S)]


def test_aura_intervals_apply_and_remove_same_ms_stays_active():
    """WCL protokolliert beim Aura-Austausch apply+remove auf derselben Millisekunde."""
    evs = [
        buff(1, "applybuff", 1),
        buff(4, "applybuff", 1),
        buff(4, "removebuff", 1),
        buff(9, "removebuff", 1),
    ]
    assert aura_intervals(evs, 1, 0, 10 * S) == [(1 * S, 9 * S)]


def test_merge_and_total_and_in_any():
    ivs = [(0, 5), (3, 7), (20, 25)]
    assert merge(ivs) == [(0, 7), (20, 25)]
    assert total_ms(ivs) == 12
    assert in_any(6, merge(ivs)) and not in_any(10, merge(ivs))


def test_debuff_intervals_separated_by_instance():
    evs = [
        debuff(0, "applydebuff", 10, 1),
        debuff(5, "removedebuff", 10, 1),
        debuff(2, "applydebuff", 10, 2),
        debuff(9, "removedebuff", 10, 2),
    ]
    out = debuff_intervals_by_target(evs, spells.WITHER_DEBUFF, 0, 10 * S)
    assert out[(10, 1)] == [(0, 5 * S)]
    assert out[(10, 2)] == [(2 * S, 9 * S)]


# --------------------------------------------------------------------------- Wither
def test_wither_refresh_pandemic():
    """Refresh 1 s vor Ablauf (Restdauer 1 s ≤ 6,3 s) = im Pandemic-Fenster."""
    evs = [debuff(0, "applydebuff"), debuff(20, "refreshdebuff")]
    st = classify_wither_refreshes(evs)
    assert (st.refreshes, st.pandemic, st.too_early, st.expired) == (1, 1, 0, 0)
    assert st.remaining_s == pytest.approx([1.0])
    assert st.pandemic_pct == pytest.approx(100.0)


def test_wither_refresh_too_early():
    """Refresh nach 2 s: Restdauer 19 s > 10,5 s = zu früh."""
    evs = [debuff(0, "applydebuff"), debuff(2, "refreshdebuff")]
    st = classify_wither_refreshes(evs)
    assert (st.refreshes, st.pandemic, st.too_early) == (1, 0, 1)
    assert st.remaining_s == pytest.approx([19.0])


def test_wither_refresh_middle_band_counts_nowhere():
    """Restdauer 8 s liegt zwischen 30 % und 50 % – weder gut noch zu früh."""
    evs = [debuff(0, "applydebuff"), debuff(13, "refreshdebuff")]
    st = classify_wither_refreshes(evs)
    assert (st.refreshes, st.pandemic, st.too_early) == (1, 0, 0)


def test_wither_expired_reapply():
    """Neuauftrag nach removedebuff = abgelaufen, der Erstauftrag zählt nicht mit."""
    evs = [
        debuff(0, "applydebuff"),
        debuff(21, "removedebuff"),
        debuff(30, "applydebuff"),
    ]
    st = classify_wither_refreshes(evs)
    assert (st.refreshes, st.expired, st.total) == (0, 1, 1)
    assert st.expired_pct == pytest.approx(100.0)


def test_wither_pandemic_extension_is_capped():
    """Zweimal früh refreshen: die Restdauer wächst nie über 130 % der Basisdauer."""
    evs = [
        debuff(0, "applydebuff"),
        debuff(1, "refreshdebuff"),  # Rest 20 → neue Ablaufzeit 1 + 27,3
        debuff(2, "refreshdebuff"),  # Rest 26,3 (nicht 41)
    ]
    st = classify_wither_refreshes(evs)
    assert st.remaining_s == pytest.approx([20.0, 26.3])
    assert max(st.remaining_s) <= rules.WITHER_MAX_DURATION_S


def test_wither_targets_are_tracked_separately():
    evs = [
        debuff(0, "applydebuff", 10),
        debuff(20, "refreshdebuff", 10),
        debuff(0, "applydebuff", 11),
        debuff(2, "refreshdebuff", 11),
    ]
    st = classify_wither_refreshes(evs)
    assert (st.pandemic, st.too_early) == (1, 1)


# --------------------------------------------------------------------------- Ladungen
def test_charge_cap_time_full_the_whole_fight():
    """Ohne Casts steht die Fähigkeit den ganzen Kampf auf voller Ladung."""
    assert charge_cap_time_s([], 2, 10.0, 0, 100 * S) == pytest.approx(100.0)


def test_charge_cap_time_perfect_usage():
    """Sofort beide Ladungen raus und danach exakt im Recharge-Takt = keine Cap-Zeit."""
    casts = [0, 1 * S, 10 * S, 20 * S, 30 * S, 40 * S]
    assert charge_cap_time_s(casts, 2, 10.0, 0, 40 * S) == pytest.approx(0.0, abs=0.2)


def test_charge_cap_time_counts_only_the_waiting_at_cap():
    """Ein Cast bei t=0, dann 50 s Pause: 10 s zum Auffüllen, 40 s am Cap."""
    assert charge_cap_time_s([0], 2, 10.0, 0, 50 * S) == pytest.approx(40.0)


def test_charge_cap_time_refund_extends_cap_time():
    """Ein Kill-Reset gibt die Ladung sofort zurück – die Cap-Zeit steigt entsprechend."""
    without = charge_cap_time_s([0, 1 * S], 2, 10.0, 0, 30 * S)
    with_refund = charge_cap_time_s([0, 1 * S], 2, 10.0, 0, 30 * S, refunds_ms=[2 * S])
    assert with_refund > without
    assert without == pytest.approx(10.0)
    assert with_refund == pytest.approx(20.0)


# --------------------------------------------------------------------------- Kill-Resets
def _death(ts_s: float, target: int, instance: int | None = 1) -> dict:
    return {
        "timestamp": int(ts_s * S),
        "type": "death",
        "targetID": target,
        "targetInstance": instance,
    }


def test_kill_reset_detection():
    casts = [cast(10, spells.SHADOWBURN, target=42), cast(30, spells.SHADOWBURN, target=42)]
    deaths = [_death(12, 42)]
    hits, refunds = kill_reset_casts(casts, deaths)
    assert [c.t for c in hits] == [10 * S]
    assert refunds == [12 * S]


def test_kill_reset_respects_window_and_target():
    casts = [
        cast(10, spells.SHADOWBURN, target=42),  # Tod erst nach 6 s
        cast(20, spells.SHADOWBURN, target=43),  # falsches Ziel
    ]
    deaths = [_death(16, 42), _death(21, 99)]
    hits, refunds = kill_reset_casts(casts, deaths)
    assert hits == [] and refunds == []


def test_kill_reset_deduplicates_refunds():
    """Zwei Casts auf denselben sterbenden Gegner = zwei Treffer, aber nur ein Refund."""
    casts = [cast(10, spells.SHADOWBURN, target=42), cast(11, spells.SHADOWBURN, target=42)]
    hits, refunds = kill_reset_casts(casts, [_death(12, 42)])
    assert len(hits) == 2
    assert refunds == [12 * S]


# --------------------------------------------------------------------------- Malevolence
def test_malevolence_window_assignment():
    """Chaos Bolts werden dem Buff-Fenster über die Buff-Events zugeordnet."""
    evs = [
        buff(10, "applybuff", spells.MALEVOLENCE_BUFF),
        buff(30, "removebuff", spells.MALEVOLENCE_BUFF),
    ]
    windows = aura_intervals(evs, spells.MALEVOLENCE_BUFF, 0, 60 * S)
    bolts = [cast(5, spells.CHAOS_BOLT), cast(15, spells.CHAOS_BOLT), cast(45, spells.CHAOS_BOLT)]
    assert sum(1 for c in bolts if in_any(c.t, windows)) == 1


def test_malevolence_refresh_keeps_window_open():
    """Ein refreshbuff mitten im Fenster darf es nicht zerschneiden."""
    evs = [
        buff(10, "applybuff", spells.MALEVOLENCE_BUFF),
        buff(20, "refreshbuff", spells.MALEVOLENCE_BUFF),
        buff(40, "removebuff", spells.MALEVOLENCE_BUFF),
    ]
    assert aura_intervals(evs, spells.MALEVOLENCE_BUFF, 0, 60 * S) == [(10 * S, 40 * S)]


# --------------------------------------------------------------------------- Shards
def test_shard_overcap_counts_builders_after_a_cap_snapshot():
    casts = [
        cast(0, spells.CHAOS_BOLT, shards=5.0, cost=2.0),  # Snapshot am Cap
        cast(2, spells.INCINERATE),
        cast(4, spells.CONFLAGRATE),
        cast(6, spells.CHAOS_BOLT, shards=4.0, cost=2.0),  # nächster Spender
        cast(8, spells.INCINERATE),
    ]
    out = shard_overcap(casts)
    assert out.cap_snapshots == 1
    assert out.time_at_cap_s == pytest.approx(6.0)
    assert out.lost_shards == 2
    assert out.snapshots == 2


def test_shard_overcap_without_cap_snapshot():
    casts = [
        cast(0, spells.CHAOS_BOLT, shards=3.0, cost=2.0),
        cast(2, spells.INCINERATE),
        cast(4, spells.CHAOS_BOLT, shards=2.0, cost=2.0),
    ]
    out = shard_overcap(casts)
    assert (out.cap_snapshots, out.lost_shards, out.time_at_cap_s) == (0, 0, 0.0)


def test_shard_overcap_ignores_dangling_last_snapshot():
    """Ein Cap-Snapshot ohne nachfolgenden Spender liefert kein Fenster."""
    casts = [cast(0, spells.CHAOS_BOLT, shards=5.0, cost=2.0), cast(2, spells.INCINERATE)]
    out = shard_overcap(casts)
    assert out.cap_snapshots == 1 and out.time_at_cap_s == 0.0 and out.lost_shards == 0


def test_last_known_shards_uses_snapshot_minus_cost():
    casts = [
        cast(0, spells.CHAOS_BOLT, shards=3.5, cost=2.0),
        cast(2, spells.INCINERATE),
        cast(4, spells.HAVOC),
    ]
    assert last_known_shards(casts, 2) == pytest.approx(1.5)
    assert last_known_shards(casts, 0) is None


# --------------------------------------------------------------------------- Cooldowns
def test_cooldown_drift_and_possible_casts():
    times = [0, 60 * S, 125 * S]  # 5 s Drift im zweiten Abstand
    assert cooldown_drift_s(times, 60.0) == pytest.approx(5.0)
    assert possible_casts(388.0, 60.0) == 7
    assert possible_casts(388.0, 90.0) == 5


def test_estimate_recharge_ignores_windows_with_deaths():
    """Ohne Todesfälle liefert der Minimum-Schätzer den echten Takt."""
    casts = [0, 1 * S, 8 * S, 9 * S, 16 * S]
    assert rules.estimate_recharge_s(
        casts, 2, [], fallback=99.0, lo=5.0, hi=13.0
    ) == pytest.approx(8.0)
    # Ein Tod im Fenster 0→8 s verwirft diesen Kandidaten, der nächste ist 8 s (1→9).
    assert rules.estimate_recharge_s(
        casts, 2, [4 * S], fallback=99.0, lo=5.0, hi=13.0
    ) == pytest.approx(8.0)


def test_estimate_recharge_clamps_and_falls_back():
    assert rules.estimate_recharge_s([0, 1 * S, 2 * S], 2, fallback=9.0, lo=6.0, hi=14.0) == 6.0
    assert rules.estimate_recharge_s([0], 2, fallback=9.0, lo=6.0, hi=14.0) == 9.0


def test_estimate_cooldown_clamps():
    assert rules.estimate_cooldown_s(
        [0, 47 * S, 110 * S], fallback=45.0, lo=20.0, hi=60.0
    ) == pytest.approx(47.0)


def test_wither_constants_match_the_reference_log():
    """21 s Basisdauer, 6,3 s Pandemic, 27,3 s Deckel – so im Referenz-Log gemessen."""
    assert rules.WITHER_DURATION_S == 21.0
    assert rules.PANDEMIC_WINDOW_S == pytest.approx(6.3)
    assert rules.WITHER_MAX_DURATION_S == pytest.approx(27.3)
    assert rules.REFRESH_TOO_EARLY_S == pytest.approx(10.5)
