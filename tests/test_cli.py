import pytest
import typer

from wclcheck.cli import parse_fight_list, parse_report_arg


@pytest.mark.parametrize(
    "arg,expected",
    [
        ("qCZ2bPkFVzgc46Lp", ("qCZ2bPkFVzgc46Lp", None)),
        ("https://www.warcraftlogs.com/reports/qCZ2bPkFVzgc46Lp", ("qCZ2bPkFVzgc46Lp", None)),
        ("https://www.warcraftlogs.com/reports/qCZ2bPkFVzgc46Lp#fight=22&type=damage-done",
         ("qCZ2bPkFVzgc46Lp", 22)),
        ("https://www.warcraftlogs.com/reports/qCZ2bPkFVzgc46Lp/#fight=last",
         ("qCZ2bPkFVzgc46Lp", None)),
        ("https://www.warcraftlogs.com/reports/a:qCZ2bPkFVzgc46Lp", ("a:qCZ2bPkFVzgc46Lp", None)),
    ],
)
def test_parse_report_arg(arg, expected):
    assert parse_report_arg(arg) == expected


def test_parse_report_arg_rejects_garbage():
    with pytest.raises(typer.BadParameter):
        parse_report_arg("nope")


def test_parse_fight_list():
    assert parse_fight_list(None) is None
    assert parse_fight_list("22") == [22]
    assert parse_fight_list("22, 13,7") == [22, 13, 7]
    with pytest.raises(typer.BadParameter):
        parse_fight_list("22,x")
