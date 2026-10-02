"""The backend lock files match the requirement files, and every installer uses them (M4-00b).

`backend/requirements.txt` and `backend/requirements-dev.txt` say what the backend
needs; `scripts/lock-backend.sh` turns them into `backend/requirements.lock` and
`backend/requirements-dev.lock`, exact versions with hashes. CI, the live smoke, the
image and the SessionStart hook install from the lock files only
(docs/plans/m4-00b-lock-datei.md).

Nothing ties the two kinds of file together but this test: a requirement added to a
`.txt` file without renewing the lock would otherwise only surface as a failed
`pip install --require-hashes` in CI. It reads files and nothing else — no network,
no `uv`, no resolver. Whether the lock is the *newest* possible resolution is not its
business: renewing is a PR of its own.

Every install site also has to pass the same pip options in the same order. pip lets
a later `--only-binary :all:` cancel an earlier `--no-binary version-parser`, and
the install then fails on the one sdist-only package in the tree.
"""

from __future__ import annotations

import re
import shlex
from dataclasses import dataclass
from pathlib import Path

import pytest
import yaml
from packaging.requirements import InvalidRequirement, Requirement
from packaging.utils import canonicalize_name

REPO = Path(__file__).resolve().parents[2]
BACKEND = REPO / "backend"
LOCK_SCRIPT = REPO / "scripts" / "lock-backend.sh"

RUNTIME_LOCK = BACKEND / "requirements.lock"
DEV_LOCK = BACKEND / "requirements-dev.lock"

# Each requirement file and the lock written from it.
LOCKS = {
    BACKEND / "requirements.txt": RUNTIME_LOCK,
    BACKEND / "requirements-dev.txt": DEV_LOCK,
}

# Every place that installs the backend packages, and the lock it must install from.
# Each must contain at least one install command; any other workflow that installs
# the backend packages is checked against the dev lock too (WORKFLOWS below).
INSTALL_SITES = {
    ".github/workflows/ci.yml": "backend/requirements-dev.lock",
    ".github/workflows/live-smoke.yml": "backend/requirements-dev.lock",
    "backend/Dockerfile": "requirements.lock",
    "scripts/setup-cloud-session.sh": "backend/requirements-dev.lock",
}
WORKFLOWS = sorted((REPO / ".github" / "workflows").glob("*.y*ml"))

HASH = re.compile(r"^--hash=sha256:[0-9a-f]{64}$")
# The backend's own files, not e.g. compose/objectstore/requirements-smoke.txt.
BACKEND_FILE = re.compile(r"\brequirements(-dev)?\.(txt|lock)\b")


class LockError(ValueError):
    """A lock file that is not what `scripts/lock-backend.sh` writes."""


@dataclass(frozen=True)
class Locked:
    version: str
    marker: str | None
    hashes: frozenset[str]


def logical_lines(text: str) -> list[str]:
    """Lines with backslash continuations joined; comment lines dropped."""
    lines: list[str] = []
    current = ""
    for raw in text.splitlines():
        stripped = raw.strip()
        if not current and (not stripped or stripped.startswith("#")):
            continue
        if stripped.endswith("\\"):
            current += stripped[:-1].rstrip() + " "
            continue
        lines.append((current + stripped).strip())
        current = ""
    if current:
        lines.append(current.strip())
    return lines


def parse_lock(text: str) -> dict[str, Locked]:
    """Lock entries by canonical name; anything but `name==version` with hashes is an error."""
    entries: dict[str, Locked] = {}
    for line in logical_lines(text):
        if line.startswith("-"):
            raise LockError(f"option line in a lock file: {line!r}")
        requirement_text, _, hash_text = line.partition(" --hash=")
        hashes = ("--hash=" + hash_text).split() if hash_text else []
        if not hashes:
            raise LockError(f"no hash: {requirement_text!r}")
        bad = [h for h in hashes if not HASH.match(h)]
        if bad:
            raise LockError(f"not a sha256 hash in {requirement_text!r}: {bad}")
        try:
            requirement = Requirement(requirement_text)
        except InvalidRequirement as exc:
            raise LockError(f"unreadable entry {requirement_text!r}: {exc}") from exc
        if requirement.url:
            raise LockError(f"URL entry: {requirement_text!r}")
        specs = list(requirement.specifier)
        if len(specs) != 1 or specs[0].operator != "==" or "*" in specs[0].version:
            raise LockError(f"not an exact version: {requirement_text!r}")
        name = canonicalize_name(requirement.name)
        if name in entries:
            raise LockError(f"locked twice: {name}")
        entries[name] = Locked(
            version=specs[0].version,
            marker=str(requirement.marker) if requirement.marker else None,
            hashes=frozenset(hashes),
        )
    return entries


def parse_requirements(path: Path) -> list[Requirement]:
    """The requirements of ``path``, following ``-r`` includes."""
    requirements: list[Requirement] = []
    for line in logical_lines(path.read_text()):
        line = line.split(" #", 1)[0].strip()
        if line.startswith("-r "):
            requirements += parse_requirements(path.parent / line[3:].strip())
        elif line.startswith("-"):
            raise ValueError(f"{path.name}: unexpected option line {line!r}")
        else:
            requirements.append(Requirement(line))
    return requirements


def lock_problems(requirements: list[Requirement], lock: dict[str, Locked]) -> list[str]:
    """What in ``requirements`` the lock leaves out or locks to a version it excludes."""
    problems = []
    for requirement in requirements:
        name = canonicalize_name(requirement.name)
        locked = lock.get(name)
        if locked is None:
            problems.append(f"{requirement.name} is not in the lock file")
        elif not requirement.specifier.contains(locked.version, prereleases=True):
            problems.append(f"{requirement.name}=={locked.version} does not satisfy {requirement}")
    return problems


def install_commands(text: str) -> list[str]:
    """Each pip command in ``text`` that installs from a backend requirement or lock file."""
    commands = []
    for line in logical_lines(text):
        for part in line.split("&&"):
            if re.search(r"\bpip3?\b.*\b(install|sync)\b", part) and BACKEND_FILE.search(part):
                commands.append(part.strip())
    return commands


def workflow_run_scripts(path: Path) -> list[str]:
    """The `run:` scripts of every step, read as YAML: what GitHub runs, not the raw text."""
    workflow = yaml.safe_load(path.read_text())
    return [
        step["run"]
        for job in workflow.get("jobs", {}).values()
        for step in job.get("steps", [])
        if isinstance(step.get("run"), str)
    ]


def site_install_commands(path: Path) -> list[str]:
    if path.suffix in (".yml", ".yaml"):
        return [c for script in workflow_run_scripts(path) for c in install_commands(script)]
    return install_commands(path.read_text())


def install_problems(command: str, lock: str) -> list[str]:
    """What keeps ``command`` from being a hash-checked install from ``lock``."""
    try:
        tokens = shlex.split(command, comments=True)
    except ValueError as exc:
        return [f"cannot split {command!r}: {exc}"]
    problems = []
    lock_parts = Path(lock).parts
    files = [tokens[i + 1] for i, t in enumerate(tokens[:-1]) if t in ("-r", "--requirement")]
    if not files or not all(Path(f).parts[-len(lock_parts) :] == lock_parts for f in files):
        problems.append(f"does not install from {lock}: {files}")
    if "--require-hashes" not in tokens:
        problems.append("no --require-hashes")
    pairs = list(zip(tokens, tokens[1:], strict=False))
    only_binary = [i for i, pair in enumerate(pairs) if pair == ("--only-binary", ":all:")]
    no_binary = [i for i, pair in enumerate(pairs) if pair == ("--no-binary", "version-parser")]
    if not only_binary or not no_binary:
        problems.append("not '--only-binary :all:' and '--no-binary version-parser'")
    elif no_binary[-1] < only_binary[-1]:
        # pip lets a later `--only-binary :all:` clear every earlier `--no-binary`.
        problems.append("'--only-binary :all:' after '--no-binary version-parser' (pip drops the exception)")
    return problems


# --- the repo ------------------------------------------------------------------


@pytest.mark.parametrize("requirements_file", sorted(LOCKS), ids=lambda p: p.name)
def test_every_requirement_is_locked_to_a_version_it_allows(requirements_file: Path) -> None:
    lock = parse_lock(LOCKS[requirements_file].read_text())
    problems = lock_problems(parse_requirements(requirements_file), lock)
    assert not problems, "run scripts/lock-backend.sh:\n" + "\n".join(problems)


def test_the_dev_lock_installs_what_the_image_installs() -> None:
    """CI tests the dev lock; it must carry the runtime lock unchanged."""
    runtime = parse_lock(RUNTIME_LOCK.read_text())
    dev = parse_lock(DEV_LOCK.read_text())
    differing = sorted(name for name, locked in runtime.items() if dev.get(name) != locked)
    assert not differing, f"locked differently for the image and for CI: {differing}"


@pytest.mark.parametrize("lock", [RUNTIME_LOCK, DEV_LOCK], ids=lambda p: p.name)
def test_the_lock_file_names_the_script_that_writes_it(lock: Path) -> None:
    header = lock.read_text().splitlines()[:3]
    assert any(line.strip() == "#    scripts/lock-backend.sh" for line in header), header


@pytest.mark.parametrize("path", sorted(INSTALL_SITES))
def test_every_install_site_installs_from_the_lock_with_hashes(path: str) -> None:
    commands = site_install_commands(REPO / path)
    assert commands, f"{path}: no install command found — reworded? then adjust this test"
    problems = {command: install_problems(command, INSTALL_SITES[path]) for command in commands}
    assert not any(problems.values()), {c: p for c, p in problems.items() if p}


@pytest.mark.parametrize("path", WORKFLOWS, ids=lambda p: p.name)
def test_no_workflow_installs_the_backend_any_other_way(path: Path) -> None:
    """Also the YAML check: a `run:` GitHub cannot parse never runs at all."""
    problems = {c: install_problems(c, "backend/requirements-dev.lock") for c in site_install_commands(path)}
    assert not any(problems.values()), {c: p for c, p in problems.items() if p}


def test_the_lock_script_compiles_with_the_options_the_installers_use() -> None:
    """Wheels only while renewing too, so a new sdist-only package shows up there."""
    text = LOCK_SCRIPT.read_text()
    code = "\n".join(line for line in text.splitlines() if not line.lstrip().startswith("#"))
    for option in ("--universal", "--generate-hashes", "--only-binary :all:", "--no-binary version-parser"):
        assert option in code, option


# --- the checks themselves, against synthetic files -------------------------------

ENTRY = "{name}=={version} \\\n    --hash=sha256:" + "a" * 64 + "\n"


def write_requirements(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "requirements.txt"
    path.write_text(text)
    return path


def test_a_requirement_missing_from_the_lock_is_found(tmp_path: Path) -> None:
    requirements = parse_requirements(write_requirements(tmp_path, "zarr>=3.1,<3.2\nshapely>=2.0\n"))
    lock = parse_lock(ENTRY.format(name="zarr", version="3.1.6"))
    assert lock_problems(requirements, lock) == ["shapely is not in the lock file"]


@pytest.mark.parametrize(
    ("requirement", "locked"),
    [("zarr>=3.1,<3.2", "3.2.0"), ("rio-tiler==9.4.6", "9.4.7"), ("pytest>=8.2", "8.1.0")],
)
def test_a_locked_version_the_requirement_excludes_is_found(tmp_path: Path, requirement: str, locked: str) -> None:
    name = Requirement(requirement).name
    requirements = parse_requirements(write_requirements(tmp_path, requirement + "\n"))
    assert len(lock_problems(requirements, parse_lock(ENTRY.format(name=name, version=locked)))) == 1


@pytest.mark.parametrize(
    ("requirement", "locked_name", "locked_version"),
    [
        ("stac-fastapi.pgstac==6.4.1", "stac-fastapi-pgstac", "6.4.1"),
        ("titiler.core==2.3.0", "titiler-core", "2.3.0"),
        ("Jinja2>=3", "jinja2", "3.1.6"),
        ("uvicorn[standard]>=0.29", "uvicorn", "0.54.0"),
    ],
)
def test_names_and_extras_are_compared_after_normalising(
    tmp_path: Path, requirement: str, locked_name: str, locked_version: str
) -> None:
    requirements = parse_requirements(write_requirements(tmp_path, requirement + "\n"))
    lock = parse_lock(ENTRY.format(name=locked_name, version=locked_version))
    assert lock_problems(requirements, lock) == []


def test_includes_are_followed(tmp_path: Path) -> None:
    (tmp_path / "base.txt").write_text("# runtime\nshapely>=2.0\n")
    dev = tmp_path / "dev.txt"
    dev.write_text("-r base.txt\npytest>=8.2  # tests\n")
    assert [r.name for r in parse_requirements(dev)] == ["shapely", "pytest"]


def test_an_option_line_in_a_requirement_file_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="option line"):
        parse_requirements(write_requirements(tmp_path, "--index-url https://example.invalid/simple\n"))


def test_a_marker_survives_parsing() -> None:
    entry = "uvloop==0.23.0 ; sys_platform != 'win32' \\\n    --hash=sha256:" + "b" * 64 + "\n"
    assert parse_lock(entry)["uvloop"].marker == 'sys_platform != "win32"'


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("zarr==3.1.6\n", "no hash"),
        ("zarr==3.1.6 --hash=md5:" + "a" * 32 + "\n", "not a sha256 hash"),
        ("zarr>=3.1 --hash=sha256:" + "a" * 64 + "\n", "not an exact version"),
        ("zarr==3.* --hash=sha256:" + "a" * 64 + "\n", "not an exact version"),
        ("zarr @ https://example.invalid/zarr.whl --hash=sha256:" + "a" * 64 + "\n", "URL entry"),
        ("-e . --hash=sha256:" + "a" * 64 + "\n", "option line"),
        ("--only-binary :all:\n", "option line"),
        (ENTRY.format(name="zarr", version="3.1.6") + ENTRY.format(name="Zarr", version="3.1.5"), "locked twice"),
        ("zarr=3.1.6 --hash=sha256:" + "a" * 64 + "\n", "unreadable entry"),
    ],
)
def test_a_malformed_lock_file_is_rejected(text: str, message: str) -> None:
    with pytest.raises(LockError, match=message):
        parse_lock(text)


@pytest.mark.parametrize(
    ("command", "problem"),
    [
        ("pip install -r backend/requirements-dev.txt", "does not install from"),
        (
            "pip install --only-binary :all: --no-binary version-parser -r backend/requirements-dev.lock",
            "no --require-hashes",
        ),
        ("pip install --require-hashes -r backend/requirements-dev.lock", "not '--only-binary"),
        (
            "pip install --require-hashes --no-binary version-parser --only-binary :all: "
            "-r backend/requirements-dev.lock",
            "after '--no-binary version-parser'",
        ),
        (
            "pip install --require-hashes --only-binary :all: --no-binary version-parser --only-binary :all: "
            "-r backend/requirements-dev.lock",
            "after '--no-binary version-parser'",
        ),
        (
            "pip install --require-hashes --only-binary :all: --no-binary version-parser "
            "-r backend/xrequirements-dev.lock",
            "does not install from",
        ),
        ("pip install --require-hashes -r 'backend/requirements-dev.lock", "cannot split"),
        (
            "pip install --require-hashes --only-binary :all: --no-binary version-parser -r backend/requirements.lock",
            "does not install from",
        ),
    ],
)
def test_a_wrong_install_command_is_found(command: str, problem: str) -> None:
    problems = install_problems(command, "backend/requirements-dev.lock")
    assert any(problem in p for p in problems), problems


def test_a_correct_install_command_passes() -> None:
    command = (
        "pip install --require-hashes --only-binary :all: --no-binary version-parser "
        '-r "${REPO_ROOT}/backend/requirements-dev.lock"'
    )
    assert install_problems(command, "backend/requirements-dev.lock") == []


def test_install_commands_are_found_across_continuations_and_chains() -> None:
    text = (
        "      - run: python -m pip install --upgrade pip && pip install -r backend/requirements-dev.lock\n"
        "RUN pip install --no-cache-dir \\\n      --require-hashes -r requirements.lock\n"
        "  npm ci\n"
        "        run: pip install -r compose/objectstore/requirements-smoke.txt\n"
        "pip3 install -r backend/requirements.txt\n"
        "uv pip sync backend/requirements.lock\n"
    )
    assert install_commands(text) == [
        "pip install -r backend/requirements-dev.lock",
        "RUN pip install --no-cache-dir --require-hashes -r requirements.lock",
        "pip3 install -r backend/requirements.txt",
        "uv pip sync backend/requirements.lock",
    ]


def test_a_workflow_run_is_read_as_yaml(tmp_path: Path) -> None:
    workflow = tmp_path / "ci.yml"
    workflow.write_text(
        "jobs:\n  backend:\n    steps:\n      - uses: actions/checkout@v4\n      - run: |\n"
        "          pip install --require-hashes --only-binary :all: --no-binary version-parser \\\n"
        "            -r backend/requirements-dev.lock\n"
    )
    [command] = site_install_commands(workflow)
    assert install_problems(command, "backend/requirements-dev.lock") == []


def test_an_unquoted_run_with_a_colon_is_not_valid_yaml(tmp_path: Path) -> None:
    """The plain scalar `--only-binary :all: --no-binary` holds ': ' and breaks the file."""
    workflow = tmp_path / "ci.yml"
    workflow.write_text(
        "jobs:\n  backend:\n    steps:\n"
        "      - run: pip install --only-binary :all: --no-binary version-parser -r backend/requirements-dev.lock\n"
    )
    with pytest.raises(yaml.YAMLError):
        site_install_commands(workflow)
