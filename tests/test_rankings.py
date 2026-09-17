from wclcheck.analysis.rankings import (
    Criteria,
    parse_rankings_page,
    reject_reason,
    relaxation_steps,
    select_comparators,
)


def entry(i, ilvl=320, dur=283_000, region="EU", code=None, size=25, hidden=False, name=None):
    code = code or f"CODE{i:012d}"
    return {
        "name": name or f"P{i}",
        "amount": 300000 - i * 100,
        "duration": dur,
        "bracketData": ilvl,
        "size": size,
        "hidden": hidden,
        "report": {"code": code, "fightID": i},
        "server": {"name": "Srv", "region": region},
    }


def page(entries, more=False):
    return {"page": 1, "hasMorePages": more, "count": len(entries), "rankings": entries}


def test_parse_and_rank_numbers():
    rows = parse_rankings_page(page([entry(1), entry(2)]), page=2)
    assert [r.rank for r in rows] == [101, 102]
    assert rows[0].url.endswith("#fight=1")


def test_reject_reasons():
    c = Criteria(ilvl=320, duration_ms=283_000)
    rows = parse_rankings_page(
        page([
            entry(1),                                   # top10
            *[entry(i) for i in range(2, 11)],          # top10
            entry(11, code="a:XXXXXXXXXXXXXXXX"),       # anonym
            entry(12, hidden=True),                     # anonym
            entry(13, region="US"),                     # Region
            entry(14, ilvl=323),                        # Ilvl
            entry(15, dur=330_000),                     # Dauer
            entry(16, size=10),                         # Raidgröße
            entry(17),                                  # ok
        ]),
        page=1,
    )
    reasons = [reject_reason(r, c) for r in rows]
    assert reasons[:10] == ["top10"] * 10
    assert reasons[10:] == ["anonym", "anonym", "Region", "Ilvl", "Dauer", "Raidgröße", None]


def test_select_first_three_after_rank_10():
    rows = [entry(i) for i in range(1, 30)]
    sel = select_comparators(lambda p: page(rows), Criteria(ilvl=320, duration_ms=283_000))
    assert [e.rank for e in sel.entries] == [11, 12, 13]
    assert not sel.relaxed and sel.pages_loaded == 1


def test_paginates_until_enough():
    p1 = page([entry(i, ilvl=330) for i in range(1, 101)], more=True)
    p2 = page([entry(i, ilvl=320) for i in range(101, 201)], more=True)
    calls = []

    def fetch(p):
        calls.append(p)
        return p1 if p == 1 else p2

    sel = select_comparators(fetch, Criteria(ilvl=320, duration_ms=283_000))
    assert calls == [1, 2]
    assert [e.rank for e in sel.entries] == [101, 102, 103]


def test_relaxes_when_not_enough():
    rows = [entry(i, ilvl=320) for i in range(1, 11)]  # top10
    rows += [entry(11, ilvl=320), entry(12, ilvl=323), entry(13, ilvl=324), entry(14, ilvl=326)]
    sel = select_comparators(
        lambda p: page(rows), Criteria(ilvl=320, duration_ms=283_000), max_pages=1
    )
    assert sel.relaxed
    assert [e.rank for e in sel.entries] == [11, 12, 13]
    assert sel.criteria.ilvl_tolerance == 4 and sel.criteria.duration_tolerance == 0.20


def test_relaxation_steps_from_custom_tolerance():
    steps = relaxation_steps(Criteria(ilvl=320, duration_ms=1, ilvl_tolerance=3))
    assert [(s.ilvl_tolerance, s.duration_tolerance) for s in steps] == [
        (3, 0.10), (4, 0.15), (4, 0.20)
    ]


def test_same_player_only_once_and_exclude_own_report():
    rows = [entry(i) for i in range(1, 11)]
    rows += [
        entry(11, name="Dup"), entry(12, name="Dup"),
        entry(13, code="MYREPORT00000000"), entry(14), entry(15),
    ]
    sel = select_comparators(
        lambda p: page(rows),
        Criteria(ilvl=320, duration_ms=283_000, exclude=frozenset({("MYREPORT00000000", 13)})),
    )
    assert [e.rank for e in sel.entries] == [11, 14, 15]
