"""Rechen-Tests (adr/0002 T-A) for the resting quad-pol operator.

Only the compute core is tested here — `_warp_complex` needs GCP-georeferenced
GeoTIFFs and has no synthetic fixture (adr/0008 §6, §9 Frage 3 scopes the
tests to "Pauli und Freeman-Durden"). Each scattering vector below is a
canonical, analytically known case (pure surface, pure double-bounce, pure
volume scattering) so the expected RGB triple has exactly one non-zero
channel — the same three cases both decompositions are checked against.
"""

from __future__ import annotations

import numpy as np
import pytest

from earthx.datasets.quad_pol_reference.decomp import (
    _DECOMP,
    METHODS,
    DecompError,
    _boxcar,
    _freeman,
    _pauli,
)

SHAPE = (3, 3)


def _scatter(hh: complex, hv: complex, vh: complex, vv: complex) -> list[np.ndarray]:
    return [np.full(SHAPE, value, dtype="complex128") for value in (hh, hv, vh, vv)]


#: One scattering vector per canonical case, shared by Pauli and Freeman-Durden.
PURE_SURFACE = _scatter(1, 0, 0, 1)  # HH = VV, no cross-pol
PURE_DOUBLE_BOUNCE = _scatter(1, 0, 0, -1)  # HH = -VV (dihedral 180° shift)
PURE_VOLUME = _scatter(0, 1, 1, 0)  # only cross-pol


@pytest.mark.parametrize(
    ("scatter", "expected"),
    [
        (PURE_SURFACE, (0.0, 0.0, np.sqrt(2.0))),
        (PURE_DOUBLE_BOUNCE, (np.sqrt(2.0), 0.0, 0.0)),
        (PURE_VOLUME, (0.0, np.sqrt(2.0), 0.0)),
    ],
    ids=["surface", "double-bounce", "volume"],
)
def test_pauli_isolates_each_canonical_scatterer(scatter, expected) -> None:
    r, g, b = _pauli(scatter, valid=np.ones(SHAPE, dtype=bool))
    assert (float(r[0, 0]), float(g[0, 0]), float(b[0, 0])) == pytest.approx(expected)


@pytest.mark.parametrize(
    ("scatter", "expected"),
    [
        (PURE_SURFACE, (0.0, 0.0, 2.0)),
        (PURE_DOUBLE_BOUNCE, (2.0, 0.0, 0.0)),
        (PURE_VOLUME, (0.0, 8.0, 0.0)),
    ],
    ids=["surface", "double-bounce", "volume"],
)
def test_freeman_durden_isolates_each_canonical_scatterer(scatter, expected) -> None:
    pd, pv, ps = _freeman(scatter, valid=np.ones(SHAPE, dtype=bool))
    assert (float(pd[0, 0]), float(pv[0, 0]), float(ps[0, 0])) == pytest.approx(expected)


def test_methods_and_decomp_table_agree() -> None:
    assert set(METHODS) == set(_DECOMP) == {"pauli", "freeman"}
    assert _DECOMP["pauli"] is _pauli
    assert _DECOMP["freeman"] is _freeman


def test_decomp_error_is_a_runtime_error() -> None:
    assert issubclass(DecompError, RuntimeError)


@pytest.mark.parametrize("window", [0, 1])
def test_boxcar_is_a_no_op_below_a_window_of_two(window: int) -> None:
    a = np.array([[1.0, 2.0], [3.0, 4.0]])
    assert _boxcar(a, window) is a


def test_boxcar_averages_a_constant_field_to_itself() -> None:
    a = np.full((5, 5), 3.0)
    assert _boxcar(a, 3) == pytest.approx(np.full((5, 5), 3.0))
