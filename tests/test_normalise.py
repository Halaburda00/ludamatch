import pytest

from ludamatch import normalise_title


@pytest.mark.parametrize(
    ("title", "expected"),
    [
        ("The Witcher 3: Wild Hunt", "the witcher 3 wild hunt"),
        ("Batman™: Arkham Knight", "batman arkham knight"),
        ("Brütal Legend", "brutal legend"),
        ("  S.T.A.L.K.E.R.:   Shadow of Chornobyl ", "s t a l k e r shadow of chornobyl"),
        ("STRASSE", "strasse"),
        ("Straße", "strasse"),
        ("", ""),
    ],
)
def test_folds_spellings_of_one_name(title: str, expected: str) -> None:
    assert normalise_title(title) == expected


def test_keeps_what_tells_games_apart() -> None:
    assert normalise_title("Half-Life 2") != normalise_title("Half-Life")
