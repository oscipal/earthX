"""``python -m earthx.runner``: ``run``, ``check`` and ``versions`` (adr/0016 §4.2, §12b).

Exit codes, one table for every way a run ends:

* ``0`` done;
* ``2`` the recipe file: not I-JSON, not a recipe of a platform result, an unknown
  ``recipe_version`` or ``op_version``, an expression outside R5, an output the runner
  does not compute (only ``raster`` in M4; a crop comes from the platform);
* ``3`` refused before anything is read: a dataset this image does not know, a host
  its dataset does not declare (F4);
* ``4`` while reading: a source that cannot be reached, times out or answers with an
  error, and every refusal of `gateway` — also a host that does not resolve, which is
  what a run without a network sees (adr/0016 §12b);
* ``5`` anything else, an output folder that cannot be written among it.

What it prints names hosts, versions and the short name of a failure, never an address,
a coordinate or a hash; the failure's own text is not printed, because a message of
GDAL may carry an address.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

from earthx.catalog.datasets import REGISTRY as DATASETS
from earthx.catalog.registry import DatasetRegistry
from earthx.processing import RunResult, check_scope, failure_kind, run, worker_environment
from earthx.processing.errors import RecipeInvalid, UnsupportedRecipe
from earthx.processing.methods import DatasetFacts
from earthx.processing.recipe import RECIPE_VERSION, CropOutput, Recipe, engine_versions
from earthx.runner.output import RunFolder, platform_info, runner_version
from earthx.runner.recipe_file import HostRefused, RecipeFile, check_hosts, read_recipe_file

__all__ = ["EXIT_HOST", "EXIT_OK", "EXIT_OTHER", "EXIT_RECIPE", "EXIT_SOURCE", "exit_code", "main"]

EXIT_OK = 0
EXIT_RECIPE = 2
EXIT_HOST = 3
EXIT_SOURCE = 4
EXIT_OTHER = 5

#: Where a run's folder goes inside the image (adr/0016 §8).
DEFAULT_OUT = Path("/out")

_PROGRESS_STEPS = 10


def exit_code(kind: str) -> int:
    """The exit code for a short name of :func:`~earthx.processing.failure_kind`."""
    if kind in ("recipe_invalid", "unsupported_recipe"):
        return EXIT_RECIPE
    if kind == "rejected" or kind.startswith("source_"):
        return EXIT_SOURCE
    return EXIT_OTHER


def _say(text: str) -> None:
    print(text, file=sys.stderr)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="earthx-runner", description="Compute the recipe.json of a platform result on this machine."
    )
    commands = parser.add_subparsers(dest="command", required=True)
    run_command = commands.add_parser("run", help="compute the recipe into a new folder under --out")
    run_command.add_argument("recipe", type=Path)
    run_command.add_argument("--out", type=Path, default=DEFAULT_OUT)
    check_command = commands.add_parser("check", help="check the recipe and name the hosts it reads, read nothing")
    check_command.add_argument("recipe", type=Path)
    commands.add_parser("versions", help="the versions that decide a result, as JSON")
    return parser


def main(argv: Sequence[str] | None = None, *, registry: DatasetRegistry = DATASETS) -> int:
    """Run one command; returns its exit code. ``registry`` is the one of this image unless a test hands in another."""
    try:
        args = _parser().parse_args(argv)
    except SystemExit as stop:
        return EXIT_OK if stop.code in (0, None) else EXIT_RECIPE
    logging.basicConfig(stream=sys.stderr, level=logging.WARNING, format="%(levelname)s %(message)s")
    if args.command == "versions":
        versions = {"runner_version": runner_version(), "engine": engine_versions(), "platform": platform_info()}
        print(json.dumps(versions, indent=2, sort_keys=True))
        return EXIT_OK
    checked = _checked(args.recipe, registry)
    if isinstance(checked, int):
        return checked
    loaded, hosts = checked
    if args.command == "check":
        for host in hosts:
            print(host)
        return EXIT_OK
    _say(f"reads from: {', '.join(hosts)}")
    return _run(loaded, args.out)


def _checked(path: Path, registry: DatasetRegistry) -> tuple[RecipeFile, tuple[str, ...]] | int:
    """The recipe file and its hosts, or the exit code that refuses it."""
    try:
        loaded = read_recipe_file(path)
        _raster_only(loaded.recipe)
        check_scope(loaded.recipe)
    except (RecipeInvalid, UnsupportedRecipe) as error:
        _say(f"recipe refused: {error}")
        _say(f"this runner is {runner_version()} and runs recipe_version {RECIPE_VERSION}")
        return EXIT_RECIPE
    try:
        hosts = check_hosts(loaded.recipe, registry)
    except HostRefused as error:
        _say(f"recipe refused: {error}")
        return EXIT_HOST
    _compare_engine(loaded)
    return loaded, hosts


def _raster_only(recipe: Recipe) -> None:
    if isinstance(recipe.output, CropOutput):
        raise RecipeInvalid("this runner computes raster recipes; a crop comes from the platform")


def _compare_engine(loaded: RecipeFile) -> None:
    """K1: another version of the core is named, not refused; equal bits are then not promised.

    Only the names of what differs and this runner's own versions are printed, never a value
    of the file.
    """
    here = engine_versions()
    there = loaded.provenance.engine
    differing = sorted(name for name in here if here[name] != there.get(name))
    if differing:
        mine = ", ".join(f"{name} {here[name]}" for name in differing)
        _say(
            f"warning: the platform ran other versions of {', '.join(differing)} (this runner: {mine}); "
            "the result may differ in its last bits"
        )


def _facts_of(dataset_id: str) -> DatasetFacts | None:
    """The title and DOI of the dataset in this image's registry; the text names it by its identifier if it is not there."""
    known = DATASETS.attributable(dataset_id)
    return DatasetFacts.of(known) if known is not None else None


def _run(loaded: RecipeFile, out: Path) -> int:
    try:
        folder = RunFolder.create(out)
    except OSError:
        _say("run failed: the output folder cannot be written")
        return EXIT_OTHER
    started = datetime.now(UTC)
    shown = 0

    def progress(done: int, total: int) -> None:
        nonlocal shown
        step = done * _PROGRESS_STEPS // max(total, 1)
        if step > shown:
            shown = step
            _say(f"{done}/{total} blocks")

    try:
        with worker_environment():
            result = run(loaded.recipe, workdir=folder.workdir, progress=progress)
        if not isinstance(result, RunResult):
            raise UnsupportedRecipe("an export is not run here")
        folder.finish(
            result,
            recipe_raw=loaded.raw,
            source=loaded.provenance,
            started=started,
            finished=datetime.now(UTC),
            dataset=_facts_of(loaded.recipe.inputs[0].dataset),
        )
    except Exception as error:  # noqa: BLE001 - the runner's edge: every failure is named by its kind only
        folder.remove_workdir()
        kind = failure_kind(error)
        _say(f"run failed: {kind}")
        return exit_code(kind)
    except BaseException:
        folder.remove_workdir()
        raise
    print(folder.path)
    return EXIT_OK
