"""Review data model and JSON export."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from autoqc import __version__


@dataclass
class Evidence:
    text: str
    start: float | None = None
    end: float | None = None
    windows: list[str] = field(default_factory=list)
    thumbnail: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "text": self.text,
            "start": self.start,
            "end": self.end,
            "windows": list(self.windows),
            "thumbnail": self.thumbnail,
        }


@dataclass
class CheckResult:
    item: int | None
    key: str
    title: str
    band: int | None
    confidence: float
    summary: str
    evidence: list[Evidence] = field(default_factory=list)
    details: dict[str, Any] = field(default_factory=dict)
    drives_verdict: bool = False
    unscored_reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "item": self.item,
            "key": self.key,
            "title": self.title,
            "band": self.band,
            "confidence": self.confidence,
            "summary": self.summary,
            "evidence": [item.to_dict() for item in self.evidence],
            "details": self.details,
            "drives_verdict": self.drives_verdict,
            "unscored_reason": self.unscored_reason,
        }


@dataclass
class WindowBox:
    app: str
    title: str
    window_id: str
    x: int
    y: int
    w: int
    h: int
    z: int
    active: bool = False
    is_content: bool = False
    is_goal: bool = False
    text: str = ""

    @property
    def area(self) -> int:
        return max(0, self.w) * max(0, self.h)

    @property
    def label(self) -> str:
        if self.app and self.title:
            return f"{self.app} - {self.title}"
        return self.app or self.title or "window"


@dataclass
class FrameObservation:
    t: float
    width: int
    height: int
    dock_visible: bool
    dock_position: str
    frontmost_app: str | None
    frontmost_title: str | None
    windows: list[WindowBox]
    cursor: tuple[int, int] | None
    cursor_default: bool | None
    mouse_moving: bool
    click: bool
    click_target: str | None
    ocr_text: str
    wallpaper_default: bool
    image_path: str | None = None


@dataclass
class Action:
    t: float
    kind: str
    app: str
    target: str
    window: str
    detail: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "t": self.t,
            "kind": self.kind,
            "app": self.app,
            "target": self.target,
            "window": self.window,
            "detail": self.detail,
        }


@dataclass
class Finding:
    id: str
    category: str
    action: str
    confidence: float
    summary: str
    evidence: list[Evidence] = field(default_factory=list)
    checklist_item: int | None = None
    drives_verdict: bool = False
    data: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "category": self.category,
            "action": self.action,
            "confidence": self.confidence,
            "summary": self.summary,
            "evidence": [item.to_dict() for item in self.evidence],
            "checklist_item": self.checklist_item,
            "drives_verdict": self.drives_verdict,
            "data": self.data,
        }


@dataclass
class Review:
    """One assisted review. ``auto_send`` is always false."""

    submission_path: str
    status: str
    recommended_action: str | None
    reasons: list[str]
    needs_human: list[dict[str, Any]]
    checks: list[CheckResult]
    findings: list[dict[str, Any]]
    stats: dict[str, Any]
    drafts: dict[str, str]
    notices: list[str]
    media: dict[str, Any]
    parsed: dict[str, Any]
    issues: list[str]
    actions: list[dict[str, Any]] = field(default_factory=list)
    corrected_metadata_rtf: str | None = None
    rename_suggestions: list[dict[str, Any]] = field(default_factory=list)
    prior_diff: dict[str, Any] | None = None
    auto_send: bool = False
    human_review_required: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": __version__,
            "submission_path": self.submission_path,
            "status": self.status,
            "recommended_action": self.recommended_action,
            "reasons": list(self.reasons),
            "needs_human": self.needs_human,
            "checks": [check.to_dict() for check in self.checks],
            "findings": self.findings,
            "stats": self.stats,
            "drafts": dict(self.drafts),
            "notices": list(self.notices),
            "media": self.media,
            "parsed": self.parsed,
            "issues": list(self.issues),
            "actions": self.actions,
            "corrected_metadata_rtf": self.corrected_metadata_rtf,
            "rename_suggestions": self.rename_suggestions,
            "prior_diff": self.prior_diff,
            "auto_send": False,
            "human_review_required": True,
        }
