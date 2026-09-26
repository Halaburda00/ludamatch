"""Title normalisation for comparing names, never for showing them."""

import unicodedata
from typing import Final

# Stripped before decomposition: NFKD spells `™` as the letters `TM`, which
# would then survive as part of the name.
MARKS: Final = str.maketrans("", "", "™®©℠")


def normalise_title(title: str) -> str:
    """Fold a title so that spellings of one name compare equal.

    Case, accents, trademark signs, punctuation and runs of whitespace go.
    Nothing that distinguishes one game from another is attempted here —
    editions, numerals, subtitles — because two titles that fold to the same
    string are still not the same game (*Prey*, 2006 and 2017). That is what
    the layers after this one exist to decide.
    """

    decomposed = unicodedata.normalize("NFKD", title.translate(MARKS))
    # Decomposed again after casefolding: the two do not commute for every
    # character, and this is the order Unicode gives for a caseless comparison.
    folded = unicodedata.normalize("NFKD", decomposed.casefold())
    kept = "".join(
        character if character.isalnum() else " "
        for character in folded
        if not unicodedata.combining(character)
    )
    return " ".join(kept.split())
