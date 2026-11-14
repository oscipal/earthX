"""Counting GDAL's download lines for several readers at once (M5-30b part 8)."""

from __future__ import annotations

import logging
import threading

from earthx.gateway import Policy
from earthx.gateway.gdal import counting_gdal_lines

LINE = "VSICURL: Downloading 0-9 (https://secret.example.org/x.tif)..."


def _state() -> tuple[int, bool, list[logging.Handler]]:
    logger = logging.getLogger("rasterio")
    return logger.level, logger.propagate, list(logger.handlers)


def test_a_nested_counter_leaves_the_logger_as_the_last_one_out_found_it() -> None:
    before = _state()
    with counting_gdal_lines() as outer:
        with counting_gdal_lines() as inner:
            logging.getLogger("rasterio").debug(LINE)
        logging.getLogger("rasterio").debug(LINE)
        assert logging.getLogger("rasterio").propagate is False
    assert inner.take() == (1, 10)
    assert outer.take() == (2, 20)
    assert _state() == before


def test_a_counter_of_its_own_thread_ignores_the_lines_of_others() -> None:
    before = _state()
    other: list[tuple[int, int]] = []

    def read() -> None:
        with counting_gdal_lines(own_thread_only=True) as mine:
            logging.getLogger("rasterio").debug(LINE)
            logging.getLogger("rasterio").debug(LINE)
            other.append(mine.take())

    with counting_gdal_lines(own_thread_only=True) as counter:
        thread = threading.Thread(target=read)
        thread.start()
        thread.join()
        logging.getLogger("rasterio").debug(LINE)
    assert other == [(2, 20)]
    assert counter.take() == (1, 10)
    assert _state() == before


def test_the_counter_is_released_when_the_read_fails() -> None:
    before = _state()
    try:
        with counting_gdal_lines():
            raise RuntimeError
    except RuntimeError:
        pass
    assert _state() == before


def test_a_host_entry_is_none_where_the_policy_names_none() -> None:
    policy = Policy(
        allowed_hosts=frozenset({"a.example.org"}), min_interval_s=1.0, host_intervals={"a.example.org": 0.0}
    )
    assert policy.host_interval("x.a.example.org") == 0.0
    assert policy.host_interval("b.example.org") is None
    assert policy.interval_for("b.example.org") == 1.0
