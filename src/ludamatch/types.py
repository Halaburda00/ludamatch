"""What both sides of a match pass around."""

from dataclasses import dataclass
from enum import IntEnum, StrEnum


class Store(StrEnum):
    STEAM = "steam"
    GOG = "gog"
    EPIC = "epic"


class Layer(IntEnum):
    """Which step of the cascade made a match. Lower is more certain."""

    HARD_ID = 1


@dataclass(frozen=True, slots=True)
class ExternalId:
    """An entry as one store names it: a Steam appid, a GOG product id."""

    store: Store
    uid: str


@dataclass(frozen=True, slots=True)
class Match:
    external_id: ExternalId
    igdb_game_id: int
    layer: Layer
