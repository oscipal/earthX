"""The gate of the tile reads: where a tile waits for one of its two places (M5-30b §8.11, Otto 13.11.2026).

The wait is an ``await`` in the event loop, so a waiting tile holds no thread of the pool the app shares. What the
gate promises: at most N places, first come first served, a client that hangs up while it waits never takes a place,
and a place comes back from any thread, once.
"""

from __future__ import annotations

import asyncio
import threading
from typing import Any

import pytest

from earthx.access import mosaic_tiles
from earthx.access.mosaic_tiles import ClientGone, TileGate, TilePlace


async def _here() -> bool:
    return False


class Client:
    """A client that is there until it is told to go."""

    def __init__(self) -> None:
        self.left = False

    async def gone(self) -> bool:
        return self.left


def test_the_gate_of_the_process_has_the_places_of_otto_s_answer() -> None:
    assert mosaic_tiles.TILE_GATE.places == mosaic_tiles.MAX_CONCURRENT_TILES == 2


def test_a_gate_has_a_place_at_least() -> None:
    with pytest.raises(ValueError, match="at least one place"):
        TileGate(0)


@pytest.mark.anyio
async def test_never_more_places_are_held_than_the_gate_has() -> None:
    gate = TileGate(2)
    holding, most = 0, 0

    async def tile() -> None:
        nonlocal holding, most
        place = await gate.enter(_here)
        holding += 1
        most = max(most, holding)
        await asyncio.sleep(0.01)
        holding -= 1
        place.release()

    await asyncio.gather(*(tile() for _ in range(12)))
    assert most == 2


@pytest.mark.anyio
async def test_the_places_go_in_the_order_the_tiles_came() -> None:
    gate = TileGate(1)
    first = await gate.enter(_here)
    order: list[int] = []

    async def tile(number: int) -> None:
        (await gate.enter(_here)).release()
        order.append(number)

    waiting = [asyncio.ensure_future(tile(number)) for number in range(5)]
    await asyncio.sleep(0.01)
    first.release()
    await asyncio.gather(*waiting)
    assert order == [0, 1, 2, 3, 4]


@pytest.mark.anyio
async def test_a_free_place_is_taken_without_waiting() -> None:
    gate = TileGate(2)
    places = [await asyncio.wait_for(gate.enter(_here), 0.05) for _ in range(2)]
    with pytest.raises(TimeoutError):
        await asyncio.wait_for(gate.enter(_here), 0.05)
    for place in places:
        place.release()
    (await asyncio.wait_for(gate.enter(_here), 0.05)).release()


@pytest.mark.anyio
async def test_a_client_that_hangs_up_while_it_waits_leaves_and_takes_no_place(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(TileGate, "POLL_S", 0.01)
    gate = TileGate(1)
    held = await gate.enter(_here)
    client = Client()
    waiting = asyncio.ensure_future(gate.enter(client.gone))
    await asyncio.sleep(0.05)
    assert not waiting.done()
    client.left = True
    with pytest.raises(ClientGone):
        await asyncio.wait_for(waiting, 1)
    # Nobody is in the queue any more: the place that comes back is free for the next tile, and nothing was taken for the one that left.
    held.release()
    (await asyncio.wait_for(gate.enter(_here), 0.2)).release()
    taken = [await asyncio.wait_for(gate.enter(_here), 0.2)]
    with pytest.raises(TimeoutError):
        await asyncio.wait_for(gate.enter(_here), 0.05)
    taken[0].release()


@pytest.mark.anyio
async def test_a_client_that_hung_up_in_the_moment_its_place_came_gives_the_place_back() -> None:
    gate = TileGate(1)
    left = Client()
    left.left = True
    with pytest.raises(ClientGone):
        await gate.enter(left.gone)
    (await asyncio.wait_for(gate.enter(_here), 0.05)).release()


@pytest.mark.anyio
async def test_a_cancelled_request_leaves_the_queue_and_takes_no_place() -> None:
    gate = TileGate(1)
    held = await gate.enter(_here)
    waiting = asyncio.ensure_future(gate.enter(_here))
    await asyncio.sleep(0.01)
    waiting.cancel()
    with pytest.raises(asyncio.CancelledError):
        await waiting
    held.release()
    (await asyncio.wait_for(gate.enter(_here), 0.2)).release()
    taken = await asyncio.wait_for(gate.enter(_here), 0.2)
    with pytest.raises(TimeoutError):
        await asyncio.wait_for(gate.enter(_here), 0.05)
    taken.release()


@pytest.mark.anyio
async def test_a_transport_that_cannot_say_whether_the_client_is_there_does_not_end_the_wait() -> None:
    gate = TileGate(1)
    held = await gate.enter(_here)
    calls = 0

    async def broken() -> bool:
        nonlocal calls
        calls += 1
        if calls == 1:
            return False  # the first look, with a place free or not, is for the moment of the place
        raise RuntimeError("no way to know")

    waiting = asyncio.ensure_future(gate.enter(broken))
    await asyncio.sleep(0.05)
    assert not waiting.done()
    held.release()
    (await asyncio.wait_for(waiting, 1)).release()


@pytest.mark.anyio
async def test_a_place_is_given_back_once_whoever_releases_it_and_from_any_thread() -> None:
    gate = TileGate(1)
    place = await gate.enter(_here)
    done = threading.Event()

    def release() -> None:
        place.release()
        place.release()
        done.set()

    threading.Thread(target=release).start()
    await asyncio.get_running_loop().run_in_executor(None, done.wait, 2)
    (await asyncio.wait_for(gate.enter(_here), 0.2)).release()
    taken = await asyncio.wait_for(gate.enter(_here), 0.2)
    with pytest.raises(TimeoutError):  # one place came back, not two
        await asyncio.wait_for(gate.enter(_here), 0.05)
    taken.release()


@pytest.mark.anyio
async def test_a_place_released_after_the_loop_is_closed_is_no_error() -> None:
    gate = TileGate(1)
    loop = asyncio.new_event_loop()
    loop.close()
    TilePlace(gate, loop).release()


def test_the_gate_follows_the_event_loop_it_is_used_in() -> None:
    gate = TileGate(1)

    async def take_and_keep() -> Any:
        return await gate.enter(_here)

    first = asyncio.run(take_and_keep())  # the loop ends with the place still held
    assert isinstance(first, TilePlace)
    second = asyncio.run(asyncio.wait_for(take_and_keep(), 0.2))  # a new loop has a new gate, not a stuck one
    assert isinstance(second, TilePlace)
    first.release()  # the old loop is gone: no error, and no effect on the new one


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


async def _all_places_free(gate: TileGate) -> None:
    """The gate hands out every one of its places, at once, and no more."""
    taken = [await asyncio.wait_for(gate.enter(_here), 0.3) for _ in range(gate.places)]
    with pytest.raises(TimeoutError):
        await asyncio.wait_for(gate.enter(_here), 0.05)
    for place in taken:
        place.release()


@pytest.mark.anyio
async def test_a_request_cancelled_after_its_place_came_gives_the_place_back() -> None:
    """The look at the client after the place is an await too, and a cancellation there must not keep the place."""
    gate = TileGate(1)

    async def slow_look() -> bool:
        await asyncio.sleep(10)
        return False

    task = asyncio.ensure_future(gate.enter(slow_look))
    await asyncio.sleep(0.05)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    await _all_places_free(gate)


@pytest.mark.anyio
@pytest.mark.parametrize("cancels", [1, 2, 3])
async def test_a_request_cancelled_again_while_it_leaves_the_queue_keeps_no_place(cancels: int) -> None:
    """A server that cancels at every await (anyio) can cancel the request again while it is abandoning the queue."""
    gate = TileGate(1)
    held = await gate.enter(_here)
    waiting = asyncio.ensure_future(gate.enter(_here))
    await asyncio.sleep(0.01)
    held.release()  # the place comes in the very moment the request is cancelled
    for _ in range(cancels):
        waiting.cancel()
        await asyncio.sleep(0)
    with pytest.raises(asyncio.CancelledError):
        await waiting
    await asyncio.sleep(0.01)
    await _all_places_free(gate)


@pytest.mark.anyio
async def test_a_place_that_came_is_given_back_even_when_the_abandoning_is_cancelled_too() -> None:
    free = asyncio.Semaphore(1)
    came = asyncio.ensure_future(free.acquire())  # the place came: the acquire is done and the semaphore is at 0
    await asyncio.sleep(0)
    assert came.done() and free.locked()
    abandoning = asyncio.ensure_future(TileGate._abandon(came, free))
    await asyncio.sleep(0)
    abandoning.cancel()  # the second cancellation, at the await inside `_abandon`
    with pytest.raises(asyncio.CancelledError):
        await abandoning
    assert not free.locked(), "the place that came is lost"
