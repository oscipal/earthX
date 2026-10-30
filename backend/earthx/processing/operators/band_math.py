"""``band_math``: one expression over the bands of an input, in physical values (adr/0014 §3.2, §5.2, §5.4).

An operator for ``T1`` and ``T2``: the tile (T1) and the job (T2) call the very same
function on a :class:`~rio_tiler.models.ImageData` whose bands already carry the
scaling of §5.4, which is why it is bit-identical on the native level (§6.3).

**What an expression may say (R5, narrowed on 2026-10-06 to what is bit-stable
across machines, adr/0014 §15c, adr/0016 §12a; extended by ``& | ~`` on 2026-10-07).**
The check below walks the syntax tree and knows only these nodes, so numexpr never
sees anything else:

* the names of the bands, numbers, ``+ - * /`` and a unary ``-``;
* ``**`` with a whole-number literal exponent of at most :data:`MAX_EXPONENT` — only
  up to there numexpr (``optimization="aggressive"``) breaks a power into
  multiplications; beyond it, it calls ``pow``, whose result depends on the CPU;
* comparisons, ``&``, ``|`` and ``~`` on **truth values only** — a comparison or a
  combination of them. ``~red`` or ``red & nir`` is refused here, with a text, instead
  of becoming an error out of numexpr;
* the calls :data:`FUNCTIONS`: ``where``, ``abs``, ``minimum``, ``maximum``, ``sqrt``.

``log``, ``exp``, the trigonometric functions and fractional powers are refused; they
come back later with a tolerance of their own.

**How it computes.** Inputs as ``float64``, ``numexpr.evaluate`` with
``optimization="aggressive"``, the result as ``float32``. Where the result is not
finite (``0/0``, ``x/0``) the pixel is masked instead of becoming a valid number, and
a pixel is masked where any band the expression names is masked.

**Version 1** replaces all bands by one band, :data:`OUTPUT_BAND`. **Version 2 (NM4-43c)** adds
a band with a name of its own to the stock and leaves the others where they are (adr/0020 §4, §6): a
later step, and the output, see it like any band of the data. The name follows the rules of
:func:`check_name`; the stock, not this module, knows which names are taken.
"""

from __future__ import annotations

import ast
import dataclasses
import keyword
import math
import re
from typing import Any

import numexpr
import numpy
from pydantic import BaseModel, ConfigDict, Field, field_validator
from rio_tiler.models import ImageData

from earthx.catalog.registry import LicenseTier
from earthx.processing.errors import RecipeInvalid
from earthx.processing.operators.base import BandMeta, BandUse, Operator, RasterMeta, Requirement, Tier

__all__ = [
    "BAND_MATH",
    "BAND_MATH_V2",
    "FUNCTIONS",
    "MAX_EXPONENT",
    "MAX_EXPRESSION_CHARS",
    "MAX_NAME_CHARS",
    "OUTPUT_BAND",
    "BandMathParams",
    "BandMathParamsV2",
    "check_expression",
    "check_name",
    "replace_name",
]

MAX_EXPRESSION_CHARS = 256

#: The longest name of a band a step adds: it fits on a chip in the panel (adr/0020 §6).
MAX_NAME_CHARS = 32

_NAME = re.compile(rf"[A-Za-z][A-Za-z0-9_]{{0,{MAX_NAME_CHARS - 1}}}")
# Not inside a number such as ``1e5``: an identifier does not start after a letter, a digit or ``_``.
_IDENTIFIER = re.compile(r"(?<![A-Za-z0-9_])[A-Za-z_][A-Za-z0-9_]*")

#: The largest whole-number exponent numexpr still breaks into multiplications.
MAX_EXPONENT = 50

OUTPUT_BAND = "band_math"

#: Function name → the types of its arguments; ``b`` is a truth value, ``n`` a number.
FUNCTIONS: dict[str, str] = {"where": "bnn", "abs": "n", "minimum": "nn", "maximum": "nn", "sqrt": "n"}

_ARITHMETIC = (ast.Add, ast.Sub, ast.Mult, ast.Div)
_COMPARISONS = (ast.Lt, ast.LtE, ast.Gt, ast.GtE, ast.Eq, ast.NotEq)
_COMBINATIONS = (ast.BitAnd, ast.BitOr)

_NUMBER, _TRUTH = "n", "b"
_KIND_NAME = {_NUMBER: "a number", _TRUTH: "a truth value"}


def _refuse(what: str) -> ValueError:
    return ValueError(f"expression: {what}")


def _literal_exponent(node: ast.expr) -> int:
    sign = 1
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.USub, ast.UAdd)):
        sign = -1 if isinstance(node.op, ast.USub) else 1
        node = node.operand
    if not (isinstance(node, ast.Constant) and type(node.value) is int):
        raise _refuse("the exponent of ** is a whole number written out, such as 2 or -3")
    exponent = sign * node.value
    if abs(exponent) > MAX_EXPONENT:
        raise _refuse(f"the exponent of ** is between -{MAX_EXPONENT} and {MAX_EXPONENT}")
    return exponent


def _expect(node: ast.expr, kinds: tuple[str, ...], names: set[str], where: str) -> str:
    kind = _kind(node, names)
    if kind not in kinds:
        raise _refuse(f"{where} needs {_KIND_NAME[kinds[0]]}, not {_KIND_NAME[kind]}")
    return kind


def _kind(node: ast.expr, names: set[str]) -> str:  # noqa: C901 - one branch per allowed node, on purpose
    """The type of ``node`` (number or truth value); raises ``ValueError`` for anything not allowed."""
    if isinstance(node, ast.Constant):
        value = node.value
        if type(value) not in (int, float):
            raise _refuse("only numbers are allowed as constants")
        try:
            finite = math.isfinite(float(value))
        except OverflowError:
            finite = False
        if not finite:
            raise _refuse("a number in the expression is too large")
        return _NUMBER
    if isinstance(node, ast.Name):
        if node.id in FUNCTIONS:
            raise _refuse(f"{node.id!r} is a function, so it cannot name a band")
        if node.id.startswith("_"):
            raise _refuse("a band name does not start with an underscore")
        names.add(node.id)
        return _NUMBER
    if isinstance(node, ast.UnaryOp):
        if isinstance(node.op, (ast.USub, ast.UAdd)):
            _expect(node.operand, (_NUMBER,), names, "a sign")
            return _NUMBER
        if isinstance(node.op, ast.Invert):
            _expect(node.operand, (_TRUTH,), names, "~")
            return _TRUTH
        raise _refuse("this unary operator is not allowed")
    if isinstance(node, ast.BinOp):
        if isinstance(node.op, ast.Pow):
            _expect(node.left, (_NUMBER,), names, "**")
            _literal_exponent(node.right)
            return _NUMBER
        if isinstance(node.op, _ARITHMETIC):
            _expect(node.left, (_NUMBER,), names, "this operator")
            _expect(node.right, (_NUMBER,), names, "this operator")
            return _NUMBER
        if isinstance(node.op, _COMBINATIONS):
            symbol = "&" if isinstance(node.op, ast.BitAnd) else "|"
            _expect(node.left, (_TRUTH,), names, symbol)
            _expect(node.right, (_TRUTH,), names, symbol)
            return _TRUTH
        raise _refuse("this operator is not allowed (use + - * / ** & | ~ and comparisons)")
    if isinstance(node, ast.Compare):
        if len(node.ops) != 1 or not isinstance(node.ops[0], _COMPARISONS):
            raise _refuse("compare two values at a time, with < <= > >= == !=")
        _expect(node.left, (_NUMBER,), names, "a comparison")
        _expect(node.comparators[0], (_NUMBER,), names, "a comparison")
        return _TRUTH
    if isinstance(node, ast.Call):
        if not isinstance(node.func, ast.Name) or node.func.id not in FUNCTIONS:
            raise _refuse(f"the functions are {', '.join(FUNCTIONS)}")
        if node.keywords:
            raise _refuse("a function takes its arguments in order, not by name")
        signature = FUNCTIONS[node.func.id]
        if len(node.args) != len(signature):
            raise _refuse(f"{node.func.id} takes {len(signature)} argument(s)")
        for argument, kind in zip(node.args, signature, strict=True):
            _expect(argument, (kind,), names, f"an argument of {node.func.id}")
        return _NUMBER
    raise _refuse(f"{type(node).__name__} is not allowed")


def check_expression(text: str) -> frozenset[str]:
    """Check ``text`` against R5; returns the band names it uses, or raises ``ValueError``.

    The text names the offending construct, never the whole expression.
    """
    if not text or len(text) > MAX_EXPRESSION_CHARS:
        raise _refuse(f"1 to {MAX_EXPRESSION_CHARS} characters")
    if not all(" " <= char <= "~" for char in text):
        raise _refuse("printable ASCII only")
    try:
        tree = ast.parse(text, mode="eval")
    except (SyntaxError, ValueError, RecursionError):
        raise _refuse("not a valid expression") from None
    names: set[str] = set()
    _kind(tree.body, names)
    if not names:
        raise _refuse("it names no band")
    return frozenset(names)


def check_name(text: str) -> None:
    """The name of a band a step adds, or ``ValueError`` with the reason (adr/0020 §6).

    Letters, digits and ``_``, a letter first, at most :data:`MAX_NAME_CHARS`; no Python keyword and no
    function of R5, because an expression could not name such a band. Whether it is free is for the stock
    to say, over all bands and ignoring case.
    """
    if not _NAME.fullmatch(text):
        raise ValueError(f"name: a letter, then letters, digits or _, at most {MAX_NAME_CHARS} characters")
    if keyword.iskeyword(text):
        raise ValueError(f"name: {text!r} is a Python keyword, so an expression cannot use it")
    if text in FUNCTIONS:
        raise ValueError(f"name: {text!r} is a function, so an expression cannot use it as a band")


def replace_name(expression: str, old: str, new: str) -> str:
    """``expression`` with the band ``old`` called ``new``, token by token (a longer name that contains it stays)."""
    return _IDENTIFIER.sub(lambda match: new if match.group() == old else match.group(), expression)


class BandMathParams(BaseModel):
    """The panel's form (K8): one expression over the bands, in physical values."""

    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)

    # No `pattern` here: the Rust `regex` of pydantic and ECMA-262 read it differently (§5.1).
    expression: str = Field(
        min_length=1,
        max_length=MAX_EXPRESSION_CHARS,
        description=(
            "Band names, numbers, + - * / **, comparisons, & | ~ on comparisons, and "
            "where(c, a, b), abs, minimum, maximum, sqrt. Evaluated on physical values."
        ),
    )

    @field_validator("expression")
    @classmethod
    def _allowed(cls, value: str) -> str:
        check_expression(value)
        return value


class BandMathParamsV2(BandMathParams):
    """Version 2: the expression and the name of the band it adds, always given (B10)."""

    # No `pattern` here either: :func:`check_name` says what a name may be.
    name: str = Field(
        min_length=1,
        max_length=MAX_NAME_CHARS,
        description=(
            "Name of the new band, such as NDVI: a letter, then letters, digits or _. It is free in the data and "
            "in the other results (case ignored); later steps and the output name the band by it."
        ),
    )

    @field_validator("name")
    @classmethod
    def _free_name(cls, value: str) -> str:
        check_name(value)
        return value


def _unknown_bands(used: frozenset[str], available: list[str]) -> RecipeInvalid:
    missing = ", ".join(sorted(used - set(available)))
    return RecipeInvalid(f"expression names unknown band(s): {missing}; the input has: {', '.join(available)}")


def _computed(image: ImageData, expression: str, used: frozenset[str]) -> tuple[numpy.ndarray, numpy.ndarray]:
    """The result of ``expression`` as ``float32`` data and its mask, one band; the kernel of both versions."""
    available = list(image.band_names)
    masked = image.array
    values = {name: numpy.ma.getdata(masked[available.index(name)]).astype("float64") for name in used}
    mask = numpy.logical_or.reduce([numpy.ma.getmaskarray(masked[available.index(name)]) for name in used])
    result = numexpr.evaluate(expression, local_dict=values, optimization="aggressive", truediv=True)
    result = numpy.broadcast_to(numpy.asarray(result).astype("float32"), mask.shape)
    mask = mask | ~numpy.isfinite(result)
    return numpy.where(mask, numpy.float32("nan"), result), mask


def _run(image: ImageData, params: BaseModel) -> ImageData:
    assert isinstance(params, BandMathParams)
    used = check_expression(params.expression)
    available = list(image.band_names)
    if not used <= set(available):
        raise _unknown_bands(used, available)
    result, mask = _computed(image, params.expression, used)
    data = numpy.ma.MaskedArray(result[None], mask=mask[None])
    return ImageData(data, bounds=image.bounds, crs=image.crs, band_names=[OUTPUT_BAND], nodata=None)


def _transform(meta: RasterMeta, params: BaseModel) -> RasterMeta:
    """One float band; also the check, before any block is read, that the names and the syntax work."""
    assert isinstance(params, BandMathParams)
    used = check_expression(params.expression)
    available = [band.name for band in meta.bands]
    if not used <= set(available):
        raise _unknown_bands(used, available)
    placeholders = {name: numpy.ones(2, dtype="float64") for name in used}
    problem = numexpr.validate(params.expression, local_dict=placeholders, optimization="aggressive", truediv=True)
    if problem is not None:
        raise RecipeInvalid("numexpr does not accept the expression")
    # A formula has no known unit. Only the bare name of a band is that band again, so it keeps the band's unit.
    units = {band.name: band.unit for band in meta.bands}
    unit = units.get(params.expression.strip())
    band = BandMeta(name=OUTPUT_BAND, data_type="float32", nodata=float("nan"), unit=unit)
    return RasterMeta(meta.crs, meta.transform, meta.width, meta.height, (band,), meta.resampled)


def _run_v2(image: ImageData, params: BaseModel) -> ImageData:
    """The stock and one band more, named ``params.name``; the bands that were there are the very same values."""
    assert isinstance(params, BandMathParamsV2)
    used = check_expression(params.expression)
    available = list(image.band_names)
    if not used <= set(available):
        raise _unknown_bands(used, available)
    data, mask = _computed(image, params.expression, used)
    added = numpy.ma.MaskedArray(data[None], mask=mask[None])
    stock = numpy.ma.concatenate([image.array, added.astype(numpy.promote_types(image.array.dtype, "float32"))])
    return ImageData(
        stock, bounds=image.bounds, crs=image.crs, band_names=[*available, params.name], nodata=image.nodata
    )


def _transform_v2(meta: RasterMeta, params: BaseModel) -> RasterMeta:
    """The bands and one more; also the check, before any block is read, that the names and the syntax work."""
    assert isinstance(params, BandMathParamsV2)
    used = check_expression(params.expression)
    available = [band.name for band in meta.bands]
    if not used <= set(available):
        raise _unknown_bands(used, available)
    if params.name.casefold() in {name.casefold() for name in available}:
        raise RecipeInvalid(f"{params.name} is used twice")
    placeholders = {name: numpy.ones(2, dtype="float64") for name in used}
    problem = numexpr.validate(params.expression, local_dict=placeholders, optimization="aggressive", truediv=True)
    if problem is not None:
        raise RecipeInvalid("numexpr does not accept the expression")
    # A formula has no known unit. Only the bare name of a band is that band again, so it keeps the band's unit.
    units = {band.name: band.unit for band in meta.bands}
    unit = units.get(params.expression.strip())
    resampled = any(band.resampled for band in meta.bands if band.name in used)
    band = BandMeta(name=params.name, data_type="float32", nodata=float("nan"), unit=unit, resampled=resampled)
    return RasterMeta(meta.crs, meta.transform, meta.width, meta.height, (*meta.bands, band), meta.resampled)


def _bands_used_v2(params: BaseModel) -> BandUse:
    assert isinstance(params, BandMathParamsV2)
    return BandUse(reads=check_expression(params.expression), adds=params.name)


def _lineage(params: BaseModel) -> str:
    assert isinstance(params, BandMathParams)
    return f"band math: {params.expression}"


def _method(params: BaseModel) -> str:
    assert isinstance(params, BandMathParams)
    return (
        f"One band was computed per pixel from the expression {params.expression!r} "
        "on physical values, in 32-bit floating point."
    )


def _properties(params: BaseModel) -> dict[str, Any]:
    assert isinstance(params, BandMathParams)
    return {"processing:expression": {"format": "numexpr", "expression": params.expression}}


def _lineage_v2(params: BaseModel) -> str:
    assert isinstance(params, BandMathParamsV2)
    return f"band math: {params.name} = {params.expression}"


def _method_v2(params: BaseModel) -> str:
    assert isinstance(params, BandMathParamsV2)
    return (
        f"A band named {params.name} was computed per pixel from the expression {params.expression!r} "
        "on physical values, in 32-bit floating point, and added to the bands."
    )


def _properties_v2(params: BaseModel) -> dict[str, Any]:
    assert isinstance(params, BandMathParamsV2)
    return {"processing:expression": {"format": "numexpr", "expression": params.expression, "name": params.name}}


BAND_MATH = Operator(
    op="band_math",
    op_version=1,
    category="bands",
    title="Band math",
    description="Compute one band from an expression over the bands, in physical values.",
    citation=None,
    params=BandMathParams,
    requires=Requirement(
        capabilities=frozenset({"band_math"}), data_classes=frozenset(), license_tier=LicenseTier.PROCESSING
    ),
    tiers=frozenset({Tier.T1, Tier.T2}),
    kind="pixel",
    # 1.0 until M4-32; the statistics of the result added 12 % (adr/0014 §15k), rounded up.
    cost_factor=lambda params: 1.2,
    transform=_transform,
    run=_run,
    lineage=_lineage,
    method=_method,
    properties=_properties,
    stock=False,
    listed=False,
)

#: Version 2 (NM4-43c): adds a named band to the stock. Listed since NM4-43e, the panel sends it (adr/0020 §13); version 1 is
#: accepted, not listed.
BAND_MATH_V2 = dataclasses.replace(
    BAND_MATH,
    op_version=2,
    params=BandMathParamsV2,
    description="Compute a band from an expression over the bands, in physical values, and add it to the bands.",
    transform=_transform_v2,
    run=_run_v2,
    lineage=_lineage_v2,
    method=_method_v2,
    properties=_properties_v2,
    bands_used=_bands_used_v2,
    stock=True,
    listed=True,
)
