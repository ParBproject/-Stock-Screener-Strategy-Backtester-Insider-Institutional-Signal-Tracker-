"""Parsers for Metadata.rtf, TaskRecorder, the Studio goal, and deliverables.zip."""

from __future__ import annotations

import json
import re
import zipfile
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from striprtf.striprtf import rtf_to_text

from autoqc.errors import AutoQCError

_PACIFIC = ZoneInfo("America/Los_Angeles")
_HEADER = re.compile(
    r"^(request|task description|topology|apps|goal|description|first-approved|first approved)\s*:\s*(.*)$",
    re.IGNORECASE,
)
_BULLET = re.compile(r"^(?:[-*•]+|\d+[.)])\s*")


@dataclass
class MetadataDoc:
    request: str
    task_description: str
    task_description_apps: list[str]
    topology_apps: list[str]
    apps: list[str]
    plain_text: str


@dataclass
class TaskRecorderDoc:
    description: str
    apps: list[str]
    source: str


@dataclass
class StudioDoc:
    goal: str
    first_approved_at: datetime | None


@dataclass
class ZipInventory:
    entries: list[str] = field(default_factory=list)
    basenames: list[str] = field(default_factory=list)


def rtf_to_plain(raw: str) -> str:
    stripped = raw.lstrip()
    if stripped.startswith("{\\rtf"):
        return rtf_to_text(raw)
    return raw


def _clean_block(lines: list[str]) -> str:
    text = "\n".join(line.rstrip() for line in lines)
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _split_apps(value: str) -> list[str]:
    parts = re.split(r"[,;]", value)
    apps = []
    for part in parts:
        name = _BULLET.sub("", part).strip()
        if name:
            apps.append(name)
    return apps


def _looks_like_app(line: str) -> bool:
    if not line or len(line) > 48:
        return False
    if len(line.split()) > 5:
        return False
    return True


def parse_metadata_text(text: str) -> MetadataDoc:
    section: str | None = None
    buckets: dict[str, list[str]] = {
        "request": [],
        "task_description": [],
        "topology": [],
        "apps": [],
    }
    for raw_line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        line = raw_line.strip()
        match = _HEADER.match(line)
        if match:
            label = match.group(1).lower().replace(" ", "")
            key = {
                "request": "request",
                "taskdescription": "task_description",
                "topology": "topology",
                "apps": "apps",
            }.get(label)
            if key is None:
                if section:
                    buckets[section].append(line)
                continue
            section = key
            rest = match.group(2).strip()
            if rest:
                buckets[key].append(rest)
            continue
        if section and line:
            buckets[section].append(line)
        elif section:
            buckets[section].append("")

    request = _clean_block(buckets["request"])
    description_lines = buckets["task_description"]
    prose: list[str] = []
    td_apps: list[str] = []
    for line in description_lines:
        stripped = line.strip()
        apps_match = re.match(r"^apps\s*:\s*(.*)$", stripped, re.IGNORECASE)
        if apps_match:
            td_apps.extend(_split_apps(apps_match.group(1)))
        else:
            prose.append(line)
    explicit_apps = []
    for line in buckets["apps"]:
        explicit_apps.extend(_split_apps(line))
    td_apps.extend(explicit_apps)

    topology: list[str] = []
    for line in buckets["topology"]:
        name = _BULLET.sub("", line.strip()).strip()
        if name and _looks_like_app(name):
            topology.append(name)

    combined: list[str] = []
    seen: set[str] = set()
    for name in td_apps + topology:
        key = name.casefold()
        if key not in seen:
            seen.add(key)
            combined.append(name)

    return MetadataDoc(
        request=request,
        task_description=_clean_block(prose),
        task_description_apps=td_apps,
        topology_apps=topology,
        apps=combined,
        plain_text=text.strip(),
    )


def parse_metadata_file(path: Path) -> MetadataDoc:
    try:
        raw = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        raise AutoQCError(f"unreadable Metadata file: {path.name}") from exc
    return parse_metadata_text(rtf_to_plain(raw))


def _parse_taskrecorder_text(text: str, source: str) -> TaskRecorderDoc:
    section: str | None = None
    description: list[str] = []
    apps: list[str] = []
    for raw_line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        line = raw_line.strip()
        match = _HEADER.match(line)
        if match:
            label = match.group(1).lower()
            rest = match.group(2).strip()
            if label in {"description", "request", "task description"}:
                section = "description"
                if rest:
                    description.append(rest)
                continue
            if label == "apps":
                section = "apps"
                if rest:
                    apps.extend(_split_apps(rest))
                continue
        if not line:
            if section == "description":
                description.append("")
            continue
        if section == "apps" or (section is None and line.lower().startswith("apps")):
            section = "apps"
            apps.extend(_split_apps(re.sub(r"^apps\s*:\s*", "", line, flags=re.IGNORECASE)))
            continue
        if section == "description" or section is None:
            section = "description"
            description.append(line)
    return TaskRecorderDoc(description=_clean_block(description), apps=apps, source=source)


def parse_taskrecorder_file(path: Path) -> TaskRecorderDoc:
    try:
        raw = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        raise AutoQCError(f"unreadable TaskRecorder file: {path.name}") from exc
    if path.suffix.lower() == ".json":
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise AutoQCError(f"{path.name} is not valid JSON") from exc
        apps = payload.get("apps") or payload.get("app_list") or []
        description = payload.get("description") or payload.get("task") or ""
        return TaskRecorderDoc(
            description=str(description).strip(),
            apps=[str(app).strip() for app in apps if str(app).strip()],
            source=path.name,
        )
    return _parse_taskrecorder_text(raw, path.name)


def parse_approved_at(value: str | None) -> datetime | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    # Allow a trailing " PT" / " Pacific" note on an otherwise ISO value.
    text = re.sub(r"\s+(PT|PST|PDT|Pacific)$", "", text, flags=re.IGNORECASE)
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as exc:
        raise AutoQCError(f"could not parse idea first-approved date: {value}") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=_PACIFIC)
    return parsed


def parse_studio_file(path: Path) -> StudioDoc:
    try:
        raw = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        raise AutoQCError(f"unreadable Studio goal: {path.name}") from exc
    if path.suffix.lower() == ".json":
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise AutoQCError(f"{path.name} is not valid JSON") from exc
        approved = payload.get("idea_first_approved_at") or payload.get("first_approved_at")
        goal = payload.get("goal") or payload.get("text") or ""
        return StudioDoc(goal=str(goal).strip(), first_approved_at=parse_approved_at(approved))

    approved: datetime | None = None
    goal_lines: list[str] = []
    seen_goal = False
    for raw_line in raw.replace("\r\n", "\n").split("\n"):
        line = raw_line.strip()
        match = _HEADER.match(line)
        if match and match.group(1).lower().replace(" ", "") in {"first-approved", "firstapproved"}:
            approved = parse_approved_at(match.group(2))
            continue
        if match and match.group(1).lower() == "goal":
            seen_goal = True
            if match.group(2).strip():
                goal_lines.append(match.group(2).strip())
            continue
        if seen_goal or not line.lower().startswith("first-approved"):
            if line or goal_lines:
                goal_lines.append(raw_line.rstrip())
    goal = _clean_block(goal_lines)
    return StudioDoc(goal=goal, first_approved_at=approved)


def parse_zip(path: Path) -> ZipInventory:
    try:
        with zipfile.ZipFile(path) as archive:
            entries = []
            basenames = []
            for info in archive.infolist():
                if info.is_dir() or info.filename.endswith("/"):
                    continue
                entries.append(info.filename)
                basenames.append(Path(info.filename).name)
    except zipfile.BadZipFile as exc:
        raise AutoQCError(f"{path.name} is not a readable zip") from exc
    return ZipInventory(entries=entries, basenames=basenames)


def render_metadata_rtf(request: str, apps: list[str]) -> str:
    """Build a Metadata.rtf whose Request matches ``request`` word for word."""

    def escape(value: str) -> str:
        return (
            value.replace("\\", "\\\\")
            .replace("{", "\\{")
            .replace("}", "\\}")
            .replace("\n", "\\par\n")
        )

    app_lines = "\\par\n".join(escape(app) for app in apps) or ""
    apps_inline = escape(", ".join(apps))
    body = (
        "{\\rtf1\\ansi\\deff0\n"
        f"Request: {escape(request)}\\par\n"
        "Task Description:\\par\n"
        f"{escape(request)}\\par\n"
        f"Apps: {apps_inline}\\par\n"
        "TOPOLOGY:\\par\n"
        f"{app_lines}\\par\n"
        "}\n"
    )
    return body
