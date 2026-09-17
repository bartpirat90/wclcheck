from wclcheck import spells
from wclcheck.analysis.spec import detect_spec


def test_demo_diabolist():
    s = detect_spec([spells.HAND_OF_GULDAN, spells.SHADOW_BOLT, spells.RUINATION])
    assert (s.spec, s.hero, s.label) == ("Demonology", "Diabolist", "Demo/Diabolist")
    assert s.is_demo and not s.is_destro


def test_destro_hellcaller():
    s = detect_spec([spells.CHAOS_BOLT, spells.WITHER, spells.INCINERATE])
    assert (s.spec, s.hero) == ("Destruction", "Hellcaller")


def test_unknown():
    s = detect_spec([spells.SHADOW_BOLT])
    assert (s.spec, s.hero, s.label) == (None, None, "?/?")
