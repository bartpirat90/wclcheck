"""Unit-Tests der gemeinsamen Zeitreihen-Hilfen (`analysis/timeline.py`)."""

from __future__ import annotations

import pytest

from wclcheck.analysis.timeline import (
    DRIFT_TOLERANCE_S,
    active_at,
    aura_intervals,
    cooldown_drift_s,
    drift_list_s,
    expected_casts,
    in_any,
    merge,
    total_ms,
)

S = 1000  # eine Sekunde in ms


def ev(ts_s: float, kind: str, ability: int = 1) -> dict:
    return {"timestamp": int(ts_s * S), "type": kind, "abilityGameID": ability}


# --------------------------------------------------------------------------- Intervalle
def test_aura_intervals_basics():
    evs = [ev(2, "applybuff"), ev(5, "removebuff")]
    assert aura_intervals(evs, 1, 0, 10 * S) == [(2 * S, 5 * S)]


def test_aura_intervals_ignoriert_fremde_ability():
    evs = [ev(2, "applybuff", ability=2), ev(5, "removebuff", ability=2)]
    assert aura_intervals(evs, 1, 0, 10 * S) == []


def test_aura_intervals_nur_removebuff_zaehlt_ab_kampfbeginn():
    """Pre-Pull-Aura: ein remove ohne vorheriges apply beginnt am Kampfbeginn."""
    assert aura_intervals([ev(3, "removebuff")], 1, 0, 10 * S) == [(0, 3 * S)]
    # Auch dann, wenn der Kampf nicht bei 0 beginnt.
    assert aura_intervals([ev(13, "removebuff")], 1, 10 * S, 20 * S) == [(10 * S, 13 * S)]


def test_aura_intervals_apply_refresh_remove():
    """refresh innerhalb eines laufenden Intervalls öffnet kein zweites Fenster."""
    evs = [ev(2, "applybuff"), ev(4, "refreshbuff"), ev(7, "refreshbuff"), ev(9, "removebuff")]
    assert aura_intervals(evs, 1, 0, 10 * S) == [(2 * S, 9 * S)]


def test_aura_intervals_offenes_ende_laeuft_bis_kampfende():
    evs = [ev(3, "removebuff"), ev(8, "applybuff")]
    assert aura_intervals(evs, 1, 0, 10 * S) == [(0, 3 * S), (8 * S, 10 * S)]


def test_aura_intervals_apply_remove_apply_auf_derselben_ms_bleibt_aktiv():
    """WCL protokolliert beim Aura-Austausch apply und remove auf derselben ms."""
    evs = [
        ev(1, "applybuff"),
        ev(4, "removebuff"),
        ev(4, "applybuff"),
        ev(9, "removebuff"),
    ]
    assert aura_intervals(evs, 1, 0, 10 * S) == [(1 * S, 9 * S)]


def test_aura_intervals_clamping_auf_kampffenster():
    """Intervalle außerhalb des Kampffensters werden beschnitten bzw. verworfen."""
    evs = [ev(1, "applybuff"), ev(30, "removebuff")]
    assert aura_intervals(evs, 1, 10 * S, 20 * S) == [(10 * S, 20 * S)]
    # Vollständig vor dem Kampf: bleibt nichts übrig.
    evs = [ev(1, "applybuff"), ev(5, "removebuff")]
    assert aura_intervals(evs, 1, 10 * S, 20 * S) == []


def test_merge_total_und_in_any():
    ivs = [(0, 5), (3, 7), (20, 25)]
    assert merge(ivs) == [(0, 7), (20, 25)]
    assert total_ms(ivs) == 12
    assert in_any(6, merge(ivs))
    assert not in_any(10, merge(ivs))
    # Ränder zählen mit.
    assert in_any(0, merge(ivs)) and in_any(7, merge(ivs))


def test_active_at_zaehlt_ueberlappungen():
    spans = [(0, 5), (3, 7), (20, 25)]
    assert active_at(spans, 4) == 2
    assert active_at(spans, 6) == 1
    assert active_at(spans, 10) == 0


# --------------------------------------------------------------------------- Drift
def test_drift_mit_toleranz():
    """90,4 s liegt in der Toleranz, 90,6 s kostet die vollen 0,6 s."""
    casts = [0, 90_400, 181_000]
    assert cooldown_drift_s(casts, 90.0, tolerance_s=DRIFT_TOLERANCE_S) == pytest.approx(0.6)
    assert cooldown_drift_s(casts, 90.0, tolerance_s=0.0) == pytest.approx(1.0)
    assert cooldown_drift_s(casts, 90.0) == pytest.approx(1.0)  # Toleranz 0 ist der Default
    assert drift_list_s(casts, 90.0, tolerance_s=DRIFT_TOLERANCE_S) == pytest.approx([0.0, 0.6])


def test_drift_ohne_paare_und_zu_frueh():
    assert cooldown_drift_s([], 90.0) == 0.0
    assert drift_list_s([1000], 90.0) == []
    # Ein Abstand unter dem Cooldown (Ladung/Reset) zählt nie negativ.
    assert cooldown_drift_s([0, 30_000], 90.0) == 0.0


def test_drift_sortiert_die_zeitpunkte():
    assert cooldown_drift_s([181_000, 0, 90_400], 90.0, tolerance_s=DRIFT_TOLERANCE_S) == (
        pytest.approx(0.6)
    )


# --------------------------------------------------------------------------- Soll-Anzahl
def test_expected_casts():
    assert expected_casts(283.0, 60.0) == 5
    assert expected_casts(305.0, 60.0) == 6
    assert expected_casts(283.0, 20.0) == 15
    assert expected_casts(388.0, 60.0) == 7
    assert expected_casts(388.0, 90.0) == 5
    assert expected_casts(388.0, 0.0) == 0
