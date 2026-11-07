"""Reading a registry entry from YAML, strictly (docs/plans/m5/m5-13-yaml-lader.md §3.2, adr/0025 §7.2).

A file is turned into the very dataclasses of ``catalog.registry``, with every check of their ``__post_init__``; there
is no second schema. Two layers keep a value from being quietly read as something else:

* YAML is read by the core schema of YAML 1.2, not 1.1: only ``true``/``false`` are booleans (``yes``, ``no``, ``on``,
  ``off`` stay text), nothing becomes a date or a time on its own, and sexagesimal or underscored numbers are text.
  Duplicate keys, anchors and aliases are errors: a file reads on its own, no value comes from somewhere else in it.
* pydantic then checks the plain data against the dataclasses in strict mode, with unknown fields forbidden
  (``registry.ENTRY_FILE_CONFIG``). A date is ISO 8601 text, an enum its value, a tuple a list.

An error names the file and the path of the field, never the value of the field.
"""

from __future__ import annotations

import dataclasses
import json
import re
from collections.abc import Mapping
from datetime import date, datetime
from enum import Enum
from functools import cache
from pathlib import Path
from typing import Any

import yaml
from pydantic import TypeAdapter, ValidationError

from earthx.catalog.registry import ConfigError, DatasetConfig, RetiredDataset

__all__ = ["EntryFileError", "load_entry", "load_retired", "read_yaml", "to_plain"]


class EntryFileError(ConfigError):
    """A registry file that cannot be read into its entries."""


class _StrictLoader(yaml.SafeLoader):
    """``SafeLoader`` with the implicit types of the YAML 1.2 core schema and no anchors, aliases or duplicate keys."""

    def compose_node(self, parent, index):
        if self.check_event(yaml.AliasEvent):
            raise yaml.YAMLError(f"an alias is not allowed (line {self.peek_event().start_mark.line + 1})")
        event = self.peek_event()
        if getattr(event, "anchor", None) is not None:
            raise yaml.YAMLError(f"an anchor is not allowed (line {event.start_mark.line + 1})")
        return super().compose_node(parent, index)

    def construct_mapping(self, node, deep=False):
        seen: set[str] = set()
        for key_node, _ in node.value:
            key = self.construct_object(key_node, deep=deep)
            # Every key of an entry is text: `1` and `'1'` would both become "1" in JSON, and one would vanish.
            if not isinstance(key, str):
                raise yaml.YAMLError(f"a key is not text (line {key_node.start_mark.line + 1})")
            if key in seen:
                raise yaml.YAMLError(f"duplicate key {key!r} (line {key_node.start_mark.line + 1})")
            seen.add(key)
        return super().construct_mapping(node, deep=deep)


_StrictLoader.yaml_implicit_resolvers = {}
for _tag, _pattern, _first in (
    ("tag:yaml.org,2002:null", r"~|null|Null|NULL|", "~nN"),
    ("tag:yaml.org,2002:bool", r"true|True|TRUE|false|False|FALSE", "tTfF"),
    ("tag:yaml.org,2002:int", r"[-+]?[0-9]+|0o[0-7]+|0x[0-9a-fA-F]+", "-+0123456789"),
    ("tag:yaml.org,2002:float", r"[-+]?(?:\.[0-9]+|[0-9]+(?:\.[0-9]*)?)(?:[eE][-+]?[0-9]+)?", "-+.0123456789"),
):
    _StrictLoader.add_implicit_resolver(_tag, re.compile(rf"\A(?:{_pattern})\Z"), list(_first) or [""])
# The empty plain scalar is null, as in YAML 1.2; `add_implicit_resolver` keys on the first character, so it needs
# its own entry for "no character".
_StrictLoader.add_implicit_resolver("tag:yaml.org,2002:null", re.compile(r"\A\Z"), [""])


def _core_int(loader: _StrictLoader, node: yaml.ScalarNode) -> int:
    value = loader.construct_scalar(node)
    if value.startswith("0o"):
        return int(value[2:], 8)
    if value.startswith("0x"):
        return int(value[2:], 16)
    return int(value)


_StrictLoader.add_constructor("tag:yaml.org,2002:int", _core_int)


def read_yaml(path: Path) -> Any:
    """The plain data of ``path`` by the rules above, or :class:`EntryFileError`."""
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as error:
        raise EntryFileError(f"{path.name}: cannot be read as UTF-8 text ({type(error).__name__})") from None
    try:
        return yaml.load(text, Loader=_StrictLoader)
    except yaml.YAMLError as error:
        problem = getattr(error, "problem", None) or str(error).splitlines()[0]
        mark = getattr(error, "problem_mark", None)
        where = f" (line {mark.line + 1})" if mark is not None else ""
        raise EntryFileError(f"{path.name}: not valid YAML: {problem}{where}") from None


@cache
def _adapter(kind: type) -> TypeAdapter:
    return TypeAdapter(kind)


def _validate(kind: type, data: object, name: str) -> Any:
    try:
        text = json.dumps(data, allow_nan=False)
    except (TypeError, ValueError):
        raise EntryFileError(f"{name}: holds a value that is no text, number, boolean, list or mapping") from None
    try:
        return _adapter(kind).validate_json(text, strict=True)
    except ValidationError as error:
        problems = []
        for problem in error.errors(include_input=False, include_url=False):
            where = ".".join(str(part) for part in problem["loc"]) or "(entry)"
            problems.append(f"{where}: {problem['msg']}")
        raise EntryFileError(f"{name}: " + "; ".join(problems)) from None


def load_entry(path: Path) -> DatasetConfig:
    """The entry in ``path``; the file is named after its ``dataset_id``."""
    data = read_yaml(path)
    if not isinstance(data, Mapping):
        raise EntryFileError(f"{path.name}: an entry is a mapping of its fields")
    entry = _validate(DatasetConfig, data, path.name)
    if path.name != f"{entry.dataset_id}.yaml":
        raise EntryFileError(f"{path.name}: the file of an entry is named <dataset_id>.yaml")
    return entry


def load_retired(path: Path) -> tuple[RetiredDataset, ...]:
    """The datasets that left the registry (adr/0017), a list in ``path``."""
    data = read_yaml(path)
    if not isinstance(data, list):
        raise EntryFileError(f"{path.name}: the retired datasets are a list")
    return tuple(_validate(RetiredDataset, item, f"{path.name}[{index}]") for index, item in enumerate(data))


def to_plain(value: object) -> Any:
    """The plain data of an entry, field by field in the order of the dataclass: what its YAML file holds."""
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return {field.name: to_plain(getattr(value, field.name)) for field in dataclasses.fields(value)}
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, (frozenset, set)):
        return sorted(to_plain(item) for item in value)
    if isinstance(value, (tuple, list)):
        return [to_plain(item) for item in value]
    if isinstance(value, Mapping):
        return {key: to_plain(item) for key, item in value.items()}
    return value
