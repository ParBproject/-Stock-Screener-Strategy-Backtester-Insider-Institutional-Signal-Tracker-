"""Diff a resubmission against the prior folder."""

from __future__ import annotations

from difflib import SequenceMatcher

from autoqc.ingest.submission import Submission


def _text(submission: Submission) -> str:
    parts = []
    if submission.metadata is not None:
        parts.append(submission.metadata.request)
    if submission.taskrecorder is not None:
        parts.append(submission.taskrecorder.description)
    return "\n".join(parts)


def submission_diff(current: Submission) -> dict | None:
    prior = current.prior
    if prior is None:
        return None
    current_files = set(current.zip_inventory.basenames) if current.zip_inventory else set()
    prior_files = set(prior.zip_inventory.basenames) if prior.zip_inventory else set()
    current_apps = set(current.taskrecorder.apps) if current.taskrecorder else set()
    prior_apps = set(prior.taskrecorder.apps) if prior.taskrecorder else set()
    current_text = _text(current)
    prior_text = _text(prior)
    ratio = SequenceMatcher(None, prior_text, current_text).ratio() if prior_text or current_text else 1.0
    current_duration = float(current.media.duration or 0.0)
    prior_duration = float(prior.media.duration or 0.0)
    unchanged = (
        current_files == prior_files
        and current_apps == prior_apps
        and ratio >= 0.97
        and abs(current_duration - prior_duration) <= max(1.0, prior_duration * 0.02)
    )
    return {
        "unchanged": unchanged,
        "text_similarity": round(ratio, 4),
        "duration_seconds": {"current": current_duration, "prior": prior_duration},
        "deliverables_added": sorted(current_files - prior_files),
        "deliverables_removed": sorted(prior_files - current_files),
        "apps_added": sorted(current_apps - prior_apps),
        "apps_removed": sorted(prior_apps - current_apps),
        "prior_notes": current.prior_notes,
    }
