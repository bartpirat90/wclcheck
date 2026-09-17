"""Phase-1-Verifikation gegen den Referenz-Report (braucht Zugangsdaten)."""

import pytest

pytestmark = pytest.mark.live

REF_REPORT = "qCZ2bPkFVzgc46Lp"
REF_FIGHTS = {
    22: ("Vashnik the Malignant", 283),
    13: ("Sszorak", 298),
    7: ("The Lost Explorers", 274),
    2: ("Nek'zali the Soulcoiler", 305),
    17: ("Entombed Sentinels", 388),
}


def test_reference_report_fights(live_client):
    rep = live_client.report(REF_REPORT)
    assert rep.zone is not None
    for fid, (name, dur) in REF_FIGHTS.items():
        f = rep.fight(fid)
        assert f is not None, f"Fight {fid} fehlt"
        assert f.kill, f"Fight {fid} ist kein Kill"
        assert name.split()[0].lower() in f.name.lower(), (fid, f.name)
        assert abs(f.duration_s - dur) <= 1.5, (fid, f.duration_s)


def test_reference_player_actor_id(live_client):
    rep = live_client.report(REF_REPORT)
    actor = rep.find_player("Schauderbart")
    assert actor is not None
    assert actor.id == 3
    assert actor.subType == "Warlock"
    pets = rep.pets_of(3)
    assert pets, "keine Pets für Schauderbart gefunden"
    for fid in REF_FIGHTS:
        assert 3 in rep.fight(fid).friendlyPlayers
