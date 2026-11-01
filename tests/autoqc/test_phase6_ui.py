"""Phase 6: SQLite, the review UI, and resubmission diffs."""

from __future__ import annotations

import json
import zipfile
from pathlib import Path

from fastapi.testclient import TestClient

from autoqc.cli import main
from autoqc.db import get_review, save_review
from autoqc.pipeline import review_submission
from autoqc.ui.api import create_app
from tests.autoqc.support import paint_menu_clock, solid, write_bundle


def _folder(tmp_path: Path) -> Path:
    from autoqc.rules.loader import load_rules

    rules = load_rules()
    frames = []
    for stamp in (0, 1, 2):
        image = solid(180, 80)
        paint_menu_clock(image, "09:15:07", rules)
        frames.append((float(stamp), image))
    folder = tmp_path / "current"
    write_bundle(
        folder,
        frames,
        "Export the quarterly budget as a PDF from Numbers",
        ["Numbers"],
        description="Export a different quarterly poster",
    )
    write_bundle(
        folder / "prior",
        frames,
        "Export the quarterly budget as a PDF from Numbers",
        ["Numbers"],
        description="Export a different quarterly poster",
    )
    with zipfile.ZipFile(folder / "deliverables.zip", "a") as archive:
        archive.writestr("extra-note.txt", b"This is the final budget and it is ready for the review.")
    return folder


def test_prior_diff_and_sqlite(tmp_path: Path):
    folder = _folder(tmp_path)
    review = review_submission(folder)
    assert review.prior_diff is not None
    assert "extra-note.txt" in review.prior_diff["deliverables_added"]
    assert review.prior_diff["unchanged"] is False
    db_path = tmp_path / "reviews.db"
    review_id = save_review(db_path, review)
    loaded = get_review(db_path, review_id)
    assert loaded is not None
    assert loaded["prior_diff"]["deliverables_added"] == ["extra-note.txt"]
    assert loaded["auto_send"] is False


def test_review_api_and_page(tmp_path: Path):
    folder = _folder(tmp_path)
    client = TestClient(create_app(tmp_path / "ui.db"))
    created = client.post("/api/reviews", json={"submission_path": str(folder)})
    assert created.status_code == 200
    body = created.json()
    assert body["human_review_required"] is True
    assert body["auto_send"] is False
    assert body["prior_diff"]["deliverables_removed"] == []
    assert "extra-note.txt" in body["prior_diff"]["deliverables_added"]
    assert len(body["checks"]) == 14
    fetched = client.get(f"/api/reviews/{body['id']}")
    assert fetched.status_code == 200
    assert fetched.json()["recommended_action"] == body["recommended_action"]
    rtf = client.get(f"/api/reviews/{body['id']}/metadata.rtf")
    assert rtf.status_code == 200
    assert "quarterly poster" in rtf.text
    frame = client.get(f"/api/reviews/{body['id']}/frame", params={"t": 0})
    assert frame.status_code == 200
    assert frame.headers["content-type"].startswith("image/")
    page = client.get("/")
    script = client.get("/app.js")
    assert page.status_code == 200
    assert "Nothing is sent automatically" in page.text
    assert "react.production.min.js" in page.text
    assert "Copy" in script.text
    assert "slack.com/api" not in script.text
    assert client.get("/api/health").json()["auto_send"] is False
    listed = client.get("/api/reviews").json()
    assert listed[0]["id"] == body["id"]
    missing = client.post("/api/reviews", json={"submission_path": str(tmp_path / "missing")})
    assert missing.status_code == 400


def test_cli_db_flag(tmp_path: Path):
    folder = _folder(tmp_path)
    db_path = tmp_path / "cli.db"
    out = tmp_path / "review.json"
    code = main(["review", str(folder), "--json", str(out), "--db", str(db_path)])
    assert code == 0
    saved = json.loads(out.read_text(encoding="utf-8"))
    assert saved["prior_diff"]["text_similarity"] >= 0
    assert get_review(db_path, 1)["submission_path"] == str(folder)
