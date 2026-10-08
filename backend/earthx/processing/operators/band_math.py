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
a pixel is masked where any band the expression names is masked. The result has one
band, :data:`OUTPUT_BAND`.
"""

from __future__ import annotations

import ast
import math
from typing import Any

import numexpr
import numpy
from pydantic import BaseModel, ConfigDict, Field, field_validator
from rio_tiler.models import ImageData

from earthx.catalog.registry import LicenseTier
from earthx.processing.errors import RecipeInvalid
from earthx.processing.operators.base import BandMeta, Operator, RasterMeta, Requirement, Tier

__all__ = [
    "BAND_MATH",
    "FUNCTIONS",
    "MAX_EXPONENT",
    "MAX_EXPRESSION_CHARS",
    "OUTPUT_BAND",
    "BandMathParams",
    "check_expression",
]

MAX_EXPRESSION_CHARS = 256

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


def _unknown_bands(used: frozenset[str], available: list[str]) -> RecipeInvalid:
    missing = ", ".join(sorted(used - set(available)))
    return RecipeInvalid(f"expression names unknown band(s): {missing}; the input has: {', '.join(available)}")


def _run(image: ImageData, params: BaseModel) -> ImageData:
    assert isinstance(params, BandMathParams)
    used = check_expression(params.expression)
    available = list(image.band_names)
    if not used <= set(available):
        raise _unknown_bands(used, available)
    masked = image.array
    values = {name: numpy.ma.getdata(masked[available.index(name)]).astype("float64") for name in used}
    mask = numpy.logical_or.reduce([numpy.ma.getmaskarray(masked[available.index(name)]) for name in used])
    result = numexpr.evaluate(params.expression, local_dict=values, optimization="aggressive", truediv=True)
    result = numpy.broadcast_to(numpy.asarray(result).astype("float32"), mask.shape)
    mask = mask | ~numpy.isfinite(result)
    data = numpy.ma.MaskedArray(numpy.where(mask, numpy.float32("nan"), result)[None], mask=mask[None])
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
    band = BandMeta(name=OUTPUT_BAND, data_type="float32", nodata=float("nan"))
    return RasterMeta(meta.crs, meta.transform, meta.width, meta.height, (band,), meta.resampled)


def _lineage(params: BaseModel) -> str:
    assert isinstance(params, BandMathParams)
    return f"band math: {params.expression}"


def _properties(params: BaseModel) -> dict[str, Any]:
    assert isinstance(params, BandMathParams)
    return {"processing:expression": {"format": "numexpr", "expression": params.expression}}


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
    cost_factor=lambda params: 1.0,
    transform=_transform,
    run=_run,
    lineage=_lineage,
    properties=_properties,
)
