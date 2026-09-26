import re
from typing import Any

import pytest

from ludamatch import (
    ExternalId,
    Layer,
    MalformedRowError,
    Match,
    Store,
    match_by_external_id,
)
from ludamatch.igdb import BATCH_SIZE

# Rows shaped as `external_games` answers `fields game,uid`, measured against
# the live endpoint. The ids are invented: IGDB data is not redistributed, and
# the shape is what is under test.


class FakeIgdb:
    """Answers as IGDB does, `limit` and `offset` included: rows past the limit
    are cut without a word, in the order of the rows' ids."""

    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self.rows = [{"id": n, **row} for n, row in enumerate(rows)]
        self.queries: list[tuple[str, str]] = []

    async def query(self, endpoint: str, body: str) -> list[dict[str, Any]]:
        self.queries.append((endpoint, body))
        source = int(clause(r"external_game_source = (\d+)", body))
        limit = int(clause(r"limit (\d+);", body))
        offset = int(clause(r"offset (\d+);", body, default="0"))
        asked = set(re.findall(r'"([^"]+)"', body))
        found = [
            r for r in self.rows if r.get("source", source) == source and r.get("uid") in asked
        ]
        return [
            {key: value for key, value in row.items() if key != "source"}
            for row in found[offset : offset + limit]
        ]


def clause(pattern: str, body: str, default: str | None = None) -> str:
    found = re.search(pattern, body)
    if found is None:
        assert default is not None, f"no {pattern!r} in {body!r}"
        return default
    return found.group(1)


def steam(uid: str) -> ExternalId:
    return ExternalId(Store.STEAM, uid)


async def test_matches_an_id_to_the_one_game_that_claims_it() -> None:
    client = FakeIgdb([{"game": 10, "uid": "100"}])

    matches = await match_by_external_id(client, [steam("100")])

    assert matches == {steam("100"): Match(steam("100"), 10, Layer.HARD_ID)}
    assert client.queries == [
        (
            "external_games",
            'fields game,uid; where external_game_source = 1 & uid = ("100"); '
            "sort id asc; limit 500; offset 0;",
        )
    ]


async def test_an_id_igdb_does_not_know_is_absent() -> None:
    assert await match_by_external_id(FakeIgdb([]), [steam("100")]) == {}


async def test_an_id_claimed_by_two_games_is_not_a_match() -> None:
    client = FakeIgdb([{"game": 10, "uid": "100"}, {"game": 11, "uid": "100"}])

    assert await match_by_external_id(client, [steam("100")]) == {}


async def test_two_rows_for_the_same_game_are_still_one_match() -> None:
    client = FakeIgdb([{"game": 10, "uid": "100"}, {"game": 10, "uid": "100"}])

    assert (await match_by_external_id(client, [steam("100")]))[steam("100")].igdb_game_id == 10


async def test_asks_each_store_under_its_own_source() -> None:
    epic = ExternalId(Store.EPIC, "9efde363a6c9497da6888b47ae0c837b")
    gog = ExternalId(Store.GOG, "1495134320")
    client = FakeIgdb(
        [
            {"game": 10, "uid": "100", "source": 1},
            {"game": 20, "uid": gog.uid, "source": 5},
            {"game": 30, "uid": epic.uid, "source": 26},
        ]
    )

    matches = await match_by_external_id(client, [steam("100"), gog, epic])

    assert {key: match.igdb_game_id for key, match in matches.items()} == {
        steam("100"): 10,
        gog: 20,
        epic: 30,
    }


async def test_the_same_uid_in_two_stores_is_two_ids() -> None:
    client = FakeIgdb([{"game": 10, "uid": "100", "source": 1}])

    matches = await match_by_external_id(client, [steam("100"), ExternalId(Store.GOG, "100")])

    assert list(matches) == [steam("100")]


async def test_batches_at_the_row_ceiling_and_asks_once_per_uid() -> None:
    uids = [str(n) for n in range(BATCH_SIZE + 1)]
    client = FakeIgdb([{"game": int(uid), "uid": uid} for uid in uids])

    matches = await match_by_external_id(client, [steam(uid) for uid in uids + uids])

    assert len(matches) == BATCH_SIZE + 1
    # The first batch fills a page exactly, so it is asked once more to be sure.
    assert [
        (body.count('"') // 2, clause(r"offset (\d+);", body)) for _, body in client.queries
    ] == [(BATCH_SIZE, "0"), (BATCH_SIZE, "500"), (1, "0")]


async def test_a_full_batch_is_read_to_the_end_before_anything_is_decided() -> None:
    uids = [str(n) for n in range(BATCH_SIZE)]
    # The second claim on uid 0 is the last row, past the first page.
    client = FakeIgdb([{"game": int(uid), "uid": uid} for uid in uids] + [{"game": 99, "uid": "0"}])

    matches = await match_by_external_id(client, [steam(uid) for uid in uids])

    assert steam("0") not in matches
    assert len(matches) == BATCH_SIZE - 1
    assert [clause(r"offset (\d+);", body) for _, body in client.queries] == ["0", "500"]


async def test_a_row_for_a_uid_nobody_asked_about_is_ignored() -> None:
    class Chatty(FakeIgdb):
        async def query(self, endpoint: str, body: str) -> list[dict[str, Any]]:
            return [*await super().query(endpoint, body), {"game": 99, "uid": "999"}]

    matches = await match_by_external_id(Chatty([{"game": 10, "uid": "100"}]), [steam("100")])

    assert list(matches) == [steam("100")]


@pytest.mark.parametrize(
    "row",
    [
        {"uid": "100"},
        {"game": 10},
        {"game": "10", "uid": "100"},
        {"game": True, "uid": "100"},
        {"game": 10, "uid": 100},
    ],
)
async def test_a_row_without_a_usable_game_and_uid_is_refused(row: dict[str, Any]) -> None:
    class Returns(FakeIgdb):
        async def query(self, endpoint: str, body: str) -> list[dict[str, Any]]:
            return [row]

    with pytest.raises(MalformedRowError):
        await match_by_external_id(Returns([]), [steam("100")])


@pytest.mark.parametrize("uid", ['1" | uid = "2', "", "a b", "é"])
async def test_a_uid_that_would_change_the_query_is_refused(uid: str) -> None:
    client = FakeIgdb([])

    with pytest.raises(ValueError, match="refusing"):
        await match_by_external_id(client, [steam(uid)])
    assert client.queries == []
