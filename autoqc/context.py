"""Working set passed to every checklist scorer."""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from autoqc.ingest.submission import Submission
from autoqc.rules.loader import RuleSet


@dataclass
class FrameImage:
    t: float
    path: str
    rgb: np.ndarray


@dataclass
class ReviewContext:
    submission: Submission
    rules: RuleSet
    frames: list[FrameImage] = field(default_factory=list)
    ocr: object | None = None
    observations: list = field(default_factory=list)
    actions: list = field(default_factory=list)
    transcript: object | None = None
