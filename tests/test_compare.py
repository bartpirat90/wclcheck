from wclcheck.analysis.compare import compare_rows, derive_findings, raid_levers
from wclcheck.analysis.rows import MetricRow


def rows(casts, dmg, gaps, potions=1, extra=None):
    out = [
        MetricRow("x.casts", "Shadowburn", casts, "", "higher", damage=dmg),
        MetricRow("g.gaps", "Lücken gesamt", gaps, "s", "lower"),
        MetricRow("g.potions", "Kampftränke", potions, "", "higher"),
        MetricRow("g.parse", "Parse", 50, "%", "neutral", compare=False),
    ]
    if extra:
        out.extend(extra)
    return out


def test_compare_rows_median_and_delta():
    player = rows(36, 20e6, 101)
    others = [rows(60, 33e6, 40), rows(63, 35e6, 30), rows(61, 34e6, 50)]
    comps = {c.key: c for c in compare_rows(player, others)}
    sb = comps["x.casts"]
    assert sb.median == 61 and round(sb.delta_pct, 1) == round((36 - 61) / 61 * 100, 1)
    assert sb.damage_delta == 14e6 and sb.worse
    gaps = comps["g.gaps"]
    assert gaps.median == 40 and gaps.worse and gaps.delta_pct > 100
    assert not comps["g.parse"].compare


def test_missing_rows_in_comparators_are_none():
    player = rows(10, 1e6, 5, extra=[MetricRow("only.me", "Nur ich", 3, "", "higher")])
    comps = {c.key: c for c in compare_rows(player, [rows(12, 1e6, 5)])}
    assert comps["only.me"].others == [None] and comps["only.me"].median is None
    assert comps["only.me"].delta_pct is None


def test_findings_sorted_by_damage_then_pct():
    player = rows(36, 20e6, 101, potions=0)
    others = [rows(60, 33e6, 40), rows(63, 35e6, 30), rows(61, 34e6, 50)]
    comps = compare_rows(player, others)
    findings = derive_findings(comps, threshold_pct=8.0, total_damage=74.7e6)
    assert [f.key for f in findings] == ["x.casts", "g.gaps", "g.potions"]
    assert findings[0].text.startswith("Shadowburn: 36 vs. 61 (Median) – ~14.0m Schaden, ~19 %")
    assert "Lücken gesamt: 101.0 s vs. 40.0 s (Median), +152 %" == findings[1].text
    assert findings[2].text == "Kampftränke: 0 vs. 1 (Median), -100 %"


def test_findings_respect_threshold_direction_and_limit():
    player = rows(60, 33e6, 41)  # 60 vs 61 = -1.6 %, Lücken 41 vs 40 = +2.5 %
    others = [rows(60, 33e6, 40), rows(63, 35e6, 30), rows(61, 34e6, 50)]
    assert derive_findings(compare_rows(player, others), threshold_pct=8.0) == []
    better = rows(80, 50e6, 10)  # besser als Median → kein Befund
    assert derive_findings(compare_rows(better, others), threshold_pct=8.0) == []
    many = [MetricRow(f"k{i}", f"M{i}", 1, "", "higher") for i in range(10)]
    many_others = [[MetricRow(f"k{i}", f"M{i}", 2, "", "higher") for i in range(10)]]
    assert len(derive_findings(compare_rows(many, many_others), max_findings=6)) == 6


def test_non_lever_rows_compare_but_never_become_findings():
    player = [MetricRow("g.dps", "DPS", 100, "", "higher", lever=False)]
    others = [[MetricRow("g.dps", "DPS", 200, "", "higher", lever=False)]]
    comps = compare_rows(player, others)
    assert comps[0].delta_pct == -50 and comps[0].worse
    assert derive_findings(comps) == []


def test_raid_levers_aggregate_by_key():
    player = rows(36, 20e6, 101, potions=0)
    others = [rows(60, 33e6, 40), rows(63, 35e6, 30)]
    f1 = derive_findings(compare_rows(player, others), total_damage=70e6)
    f2 = derive_findings(compare_rows(rows(40, 25e6, 30, potions=0), others), total_damage=70e6)
    levers = raid_levers({"Boss A": f1, "Boss B": f2}, n=3)
    assert levers[0].key == "x.casts" and levers[0].bosses == 2
    assert levers[0].damage_total == 14e6 + 9e6
    assert "auf 2 Bossen" in levers[0].text
    assert {lv.key for lv in levers} == {"x.casts", "g.gaps", "g.potions"}


def test_count_and_damage_row_of_same_ability_merge_into_one_finding():
    from wclcheck.analysis.rows import MetricRow

    def pair(casts, dmg):
        return [
            MetricRow("d.sb.casts", "Shadowburn-Casts", casts, "", "higher", damage=dmg),
            MetricRow("d.sb.damage", "Shadowburn-Schaden", dmg, "m", "higher", damage=dmg),
        ]

    comps = compare_rows(pair(36, 7e6), [pair(75, 18e6), pair(67, 14e6), pair(69, 13e6)])
    findings = derive_findings(comps, total_damage=70e6)
    assert [f.key for f in findings] == ["d.sb.casts"]
    assert findings[0].text == (
        "Shadowburn-Casts: 36 vs. 69 (Median) – ~7.0m Schaden (7.00m vs. 14.00m), ~10 %"
    )
