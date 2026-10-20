"""YAML helpers shared by the scanner, the library and the installer.

Secrets are carried as SecretRef objects and written back as `!secret name`.
Other HA tags found in package files (!include, !input, !env_var) are kept as
TaggedValue so a round trip does not lose them.
"""
from __future__ import annotations

import re
from typing import Any

import yaml


class SecretRef(str):
    """A reference to secrets.yaml (`!secret name`)."""

    __slots__ = ()

    @property
    def name(self) -> str:
        return str(self)

    def __repr__(self) -> str:
        return f"SecretRef({str(self)!r})"


class TaggedValue:
    """Any other custom tag, kept verbatim."""

    def __init__(self, tag: str, value: Any) -> None:
        self.tag = tag
        self.value = value

    def __eq__(self, other: object) -> bool:
        return isinstance(other, TaggedValue) and other.tag == self.tag and other.value == self.value

    def __repr__(self) -> str:
        return f"TaggedValue({self.tag!r}, {self.value!r})"


class _Loader(yaml.SafeLoader):
    pass


def _secret_ctor(loader: yaml.SafeLoader, node: yaml.Node) -> SecretRef:
    return SecretRef(loader.construct_scalar(node))


def _tag_ctor(loader: yaml.SafeLoader, suffix: str, node: yaml.Node) -> TaggedValue:
    tag = "!" + suffix
    if isinstance(node, yaml.ScalarNode):
        return TaggedValue(tag, loader.construct_scalar(node))
    if isinstance(node, yaml.SequenceNode):
        return TaggedValue(tag, loader.construct_sequence(node, deep=True))
    return TaggedValue(tag, loader.construct_mapping(node, deep=True))


_Loader.add_constructor("!secret", _secret_ctor)
_Loader.add_multi_constructor("!", _tag_ctor)


class _Dumper(yaml.SafeDumper):
    def ignore_aliases(self, data: Any) -> bool:  # never emit &anchors
        return True

    def choose_scalar_style(self) -> str:
        # write `!secret name` / `!include file` without quotes, as people write them
        if self.event.tag and self.event.tag.startswith("!") and not self.event.tag.startswith("!!"):
            if self.analysis is None:
                self.analysis = self.analyze_scalar(self.event.value)
            if self.analysis.allow_block_plain and self.analysis.allow_flow_plain and not self.analysis.empty:
                return ""
        return super().choose_scalar_style()


def _str_rep(dumper: yaml.SafeDumper, data: str) -> yaml.Node:
    if "\n" in data:
        return dumper.represent_scalar("tag:yaml.org,2002:str", data, style="|")
    return dumper.represent_scalar("tag:yaml.org,2002:str", data)


def _secret_rep(dumper: yaml.SafeDumper, data: SecretRef) -> yaml.Node:
    return dumper.represent_scalar("!secret", str(data))


def _tagged_rep(dumper: yaml.SafeDumper, data: TaggedValue) -> yaml.Node:
    if isinstance(data.value, dict):
        return dumper.represent_mapping(data.tag, data.value)
    if isinstance(data.value, list):
        return dumper.represent_sequence(data.tag, data.value)
    return dumper.represent_scalar(data.tag, str(data.value))


_Dumper.add_representer(str, _str_rep)
_Dumper.add_representer(SecretRef, _secret_rep)
_Dumper.add_representer(TaggedValue, _tagged_rep)


def _clean_multiline(o: Any) -> Any:
    """PyYAML refuses block style for strings with trailing spaces; strip them."""
    if isinstance(o, SecretRef) or isinstance(o, TaggedValue):
        return o
    if isinstance(o, str) and "\n" in o:
        return "\n".join(line.rstrip() for line in o.split("\n"))
    if isinstance(o, dict):
        return {k: _clean_multiline(v) for k, v in o.items()}
    if isinstance(o, list):
        return [_clean_multiline(v) for v in o]
    return o


def load(text: str) -> Any:
    return yaml.load(text, Loader=_Loader)  # noqa: S506 - safe loader subclass


def dump(obj: Any) -> str:
    return yaml.dump(_clean_multiline(obj), Dumper=_Dumper, allow_unicode=True, sort_keys=False, width=4096)


# ---------------------------------------------------------------- JSON bridge
# Catalogs are JSON; secrets travel there as {"__secret__": name}.

def to_jsonable(o: Any) -> Any:
    if isinstance(o, SecretRef):
        return {"__secret__": str(o)}
    if isinstance(o, TaggedValue):
        return {"__tag__": o.tag, "value": to_jsonable(o.value)}
    if isinstance(o, dict):
        return {str(k): to_jsonable(v) for k, v in o.items()}
    if isinstance(o, (list, tuple, set)):
        return [to_jsonable(v) for v in o]
    if isinstance(o, (str, int, float, bool)) or o is None:
        return o
    return str(o)  # timedelta, datetime, Template objects…


def from_jsonable(o: Any) -> Any:
    if isinstance(o, dict):
        if set(o) == {"__secret__"}:
            return SecretRef(o["__secret__"])
        if set(o) == {"__tag__", "value"}:
            return TaggedValue(o["__tag__"], from_jsonable(o["value"]))
        return {k: from_jsonable(v) for k, v in o.items()}
    if isinstance(o, list):
        return [from_jsonable(v) for v in o]
    return o


def secrets_in(o: Any) -> set[str]:
    out: set[str] = set()

    def walk(x: Any) -> None:
        if isinstance(x, SecretRef):
            out.add(str(x))
        elif isinstance(x, TaggedValue):
            walk(x.value)
        elif isinstance(x, dict):
            for v in x.values():
                walk(v)
        elif isinstance(x, list):
            for v in x:
                walk(v)

    walk(o)
    return out


def slugify(text: str) -> str:
    table = str.maketrans("àâäáãåçéèêëíìîïñóòôöõúùûüýÿœæ", "aaaaaaceeeeiiiinooooouuuuyyoa")
    text = str(text).lower().translate(table)
    text = re.sub(r"[^a-z0-9]+", "_", text).strip("_")
    return text or "unnamed"
