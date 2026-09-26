"""Layer 1: a store's own id, looked up in IGDB `external_games`.

The library holds the query and the reading of its answer, not the transport.
Whoever calls it owns the IGDB credentials, the rate limit and the retries, and
passes anything with a matching `query` method.
"""

import re
from collections import defaultdict
from collections.abc import Iterable, Sequence
from typing import Any, Final, Protocol

from ludamatch.types import ExternalId, Layer, Match, Store

# IGDB's `external_game_sources` ids, read from the live endpoint rather than
# from its documentation. `category`, which carried the same numbers as an
# enum, is gone from `external_games` rows.
SOURCE_IDS: Final = {Store.STEAM: 1, Store.GOG: 5, Store.EPIC: 26}

# IGDB's ceiling on rows per query. One row per uid is the usual answer, so a
# batch this size can come back truncated only when uids are shared — and a
# shared uid is refused anyway.
BATCH_SIZE: Final = 500

# Steam and GOG ids are digits, Epic's are 32 hex characters. Anything else is
# refused rather than quoted, because the uid is spliced into the query text.
UID: Final = re.compile(r"[A-Za-z0-9_.:-]+")


class IgdbQuery(Protocol):
    async def query(self, endpoint: str, body: str) -> list[dict[str, Any]]: ...


class MalformedRowError(ValueError):
    """An `external_games` row without a usable `game` or `uid`."""


async def match_by_external_id(
    client: IgdbQuery, ids: Iterable[ExternalId]
) -> dict[ExternalId, Match]:
    """The IGDB game behind each id, for the ids that name exactly one.

    An id missing from the result either is not in IGDB or is claimed by more
    than one game. The second is not narrowed down: a hard id that points two
    ways is not a hard id, and a wrong merge costs more than a missed one.
    """

    by_store: dict[Store, list[str]] = defaultdict(list)
    for external_id in dict.fromkeys(ids):
        if not UID.fullmatch(external_id.uid):
            raise ValueError(f"refusing to query IGDB for uid {external_id.uid!r}")
        by_store[external_id.store].append(external_id.uid)

    matches: dict[ExternalId, Match] = {}
    for store, uids in by_store.items():
        for start in range(0, len(uids), BATCH_SIZE):
            batch = uids[start : start + BATCH_SIZE]
            rows = await client.query("external_games", external_games_query(store, batch))
            found = read_external_games(store, rows)
            # Only what was asked. A row for another uid would be a bug on the
            # other side, and it should not become a match nobody requested.
            matches.update(
                {
                    key: found[key]
                    for key in found.keys() & {ExternalId(store, uid) for uid in batch}
                }
            )
    return matches


def external_games_query(store: Store, uids: Sequence[str]) -> str:
    quoted = ",".join(f'"{uid}"' for uid in uids)
    return (
        f"fields game,uid; "
        f"where external_game_source = {SOURCE_IDS[store]} & uid = ({quoted}); "
        f"limit {BATCH_SIZE};"
    )


def read_external_games(store: Store, rows: Iterable[dict[str, Any]]) -> dict[ExternalId, Match]:
    games: dict[str, set[int]] = defaultdict(set)
    for row in rows:
        uid, game = row.get("uid"), row.get("game")
        # `bool` is an `int`; a `True` here is not game 1.
        if not isinstance(uid, str) or not isinstance(game, int) or isinstance(game, bool):
            raise MalformedRowError(f"external_games row without a usable uid and game: {row!r}")
        games[uid].add(game)
    return {
        ExternalId(store, uid): Match(ExternalId(store, uid), next(iter(ids)), Layer.HARD_ID)
        for uid, ids in games.items()
        if len(ids) == 1
    }
