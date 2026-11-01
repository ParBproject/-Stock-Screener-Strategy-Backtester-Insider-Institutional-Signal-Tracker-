"""Command line: ``autoqc review <submission_folder>``."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from autoqc.errors import AutoQCError
from autoqc.models import Review
from autoqc.pipeline import review_submission


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="autoqc",
        description="Reviewer-assist for macOS task recordings. Nothing is sent automatically.",
    )
    sub = parser.add_subparsers(dest="command", required=True)
    review = sub.add_parser("review", help="Score one submission folder")
    review.add_argument("submission_folder", type=Path)
    review.add_argument(
        "--config",
        type=Path,
        default=None,
        help="Directory with rules.yaml and optional policy lists",
    )
    review.add_argument(
        "--json",
        dest="json_out",
        default=None,
        help="Write the review JSON here, or - for stdout",
    )
    return parser


def format_summary(review: Review) -> str:
    lines = [
        "Auto QC review",
        f"Submission: {review.submission_path}",
        (
            f"Duration: {review.stats.get('duration_hms')} "
            f"({review.stats.get('duration_status')})"
        ),
    ]
    for check in review.checks:
        band = "unscored" if check.band is None else f"band {check.band}"
        lines.append(f"[{check.item}] {check.title}: {band} - {check.summary}")
    if review.needs_human:
        lines.append(f"Needs human look: {len(review.needs_human)}")
    action = review.recommended_action or "not decided yet"
    lines.append(f"Recommended action: {action}")
    lines.append("A human reviewer makes the final call. Nothing is sent automatically.")
    return "\n".join(lines)


def write_review(review: Review, destination: str | Path | None, submission: Path) -> Path | None:
    payload = json.dumps(review.to_dict(), indent=2)
    if destination is not None and str(destination) == "-":
        sys.stdout.write(payload)
        sys.stdout.write("\n")
        return None
    path = Path(destination) if destination else submission / ".autoqc" / "review.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(payload + "\n", encoding="utf-8")
    return path


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command != "review":
        parser.print_help()
        return 2
    folder = Path(args.submission_folder)
    try:
        review = review_submission(folder, args.config)
    except AutoQCError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    written = write_review(review, args.json_out, folder)
    if args.json_out is None or str(args.json_out) != "-":
        print(format_summary(review))
        if written is not None:
            print(f"Wrote {written}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
