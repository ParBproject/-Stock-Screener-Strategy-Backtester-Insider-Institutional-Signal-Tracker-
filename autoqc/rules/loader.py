"""Load rules.yaml and the editable policy lists.

A config directory overrides files that are present and inherits the packaged
defaults for the rest. ``rules.yaml`` is deep-merged, so a reviewer can change
one threshold without copying the whole file.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

_DATA = Path(__file__).resolve().parent / "data"


def default_data_dir() -> Path:
    return _DATA


def deep_merge(base: dict, override: dict) -> dict:
    merged = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


@dataclass
class RestrictedApp:
    name: str
    prohibited_use: str


@dataclass
class AllowedAi:
    name: str
    condition: str


@dataclass
class ProfanityTerm:
    term: str
    severity: str


@dataclass
class RuleSet:
    data: dict[str, Any]
    directory: Path
    defaults: Path
    restricted_apps: list[RestrictedApp] = field(default_factory=list)
    allowed_ai: list[AllowedAi] = field(default_factory=list)
    profanity: list[ProfanityTerm] = field(default_factory=list)
    pii: dict[str, Any] = field(default_factory=dict)
    licensing: dict[str, Any] = field(default_factory=dict)

    def get(self, path: str, default: Any = None) -> Any:
        current: Any = self.data
        for part in path.split("."):
            if isinstance(current, dict) and part in current:
                current = current[part]
            else:
                return default
        return current

    @property
    def low_confidence(self) -> float:
        return float(self.get("low_confidence", 0.6))

    def resolve(self, name: str) -> Path:
        override = self.directory / name
        if self.directory != self.defaults and override.exists():
            return override
        return self.defaults / name


def _read_yaml(path: Path) -> dict:
    if not path.exists():
        return {}
    loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    return loaded or {}


def _strip_lines(path: Path) -> list[str]:
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        rows.append(line)
    return rows


def _load_restricted(path: Path) -> list[RestrictedApp]:
    apps = []
    for line in _strip_lines(path):
        name, _, use = line.partition("|")
        apps.append(RestrictedApp(name.strip(), use.strip() or "prohibited by the Writer Handbook"))
    return apps


def _load_allowed_ai(path: Path) -> list[AllowedAi]:
    rows = []
    for line in _strip_lines(path):
        name, _, condition = line.partition("|")
        rows.append(AllowedAi(name.strip(), condition.strip()))
    return rows


def _load_profanity(path: Path) -> list[ProfanityTerm]:
    terms = []
    for line in _strip_lines(path):
        parts = [part.strip() for part in line.split("|")]
        severity = parts[1] if len(parts) > 1 and parts[1] else "minor"
        terms.append(ProfanityTerm(parts[0], severity))
    return terms


def load_rules(config_dir: Path | None = None) -> RuleSet:
    data = _read_yaml(_DATA / "rules.yaml")
    directory = _DATA
    if config_dir is not None:
        directory = Path(config_dir)
        overlay = directory / "rules.yaml"
        if overlay.exists():
            data = deep_merge(data, _read_yaml(overlay))
    rules = RuleSet(data=data, directory=directory, defaults=_DATA)
    rules.restricted_apps = _load_restricted(rules.resolve("restricted_apps.txt"))
    rules.allowed_ai = _load_allowed_ai(rules.resolve("allowed_ai.txt"))
    rules.profanity = _load_profanity(rules.resolve("profanity.txt"))
    rules.pii = _read_yaml(rules.resolve("pii_rules.yaml"))
    rules.licensing = _read_yaml(rules.resolve("licensing_rules.yaml"))
    return rules
