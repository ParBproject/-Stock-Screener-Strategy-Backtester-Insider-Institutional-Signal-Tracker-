"""FastAPI review browser. Drafts stay on this machine until a person copies them."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from autoqc import __version__
from autoqc.db import get_review, list_reviews, save_review
from autoqc.errors import AutoQCError
from autoqc.pipeline import review_submission

_STATIC = Path(__file__).resolve().parent / "static"


class ReviewRequest(BaseModel):
    submission_path: str
    config_dir: str | None = None


def _inside(path: Path, root: Path) -> bool:
    try:
        resolved = path.resolve()
        base = root.resolve()
    except OSError:
        return False
    return resolved == base or base in resolved.parents


def create_app(db_path: Path) -> FastAPI:
    app = FastAPI(title="Auto QC", version=__version__)
    app.state.db_path = Path(db_path)

    @app.get("/api/health")
    def health() -> dict:
        return {"ok": True, "auto_send": False}

    @app.get("/api/reviews")
    def reviews() -> list[dict]:
        return list_reviews(app.state.db_path)

    @app.post("/api/reviews")
    def create(body: ReviewRequest) -> dict:
        try:
            review = review_submission(body.submission_path, body.config_dir)
        except AutoQCError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        review_id = save_review(app.state.db_path, review)
        payload = review.to_dict()
        payload["id"] = review_id
        return payload

    @app.get("/api/reviews/{review_id}")
    def read(review_id: int) -> dict:
        payload = get_review(app.state.db_path, review_id)
        if payload is None:
            raise HTTPException(status_code=404, detail="review not found")
        payload["id"] = review_id
        return payload

    @app.get("/api/reviews/{review_id}/metadata.rtf")
    def metadata(review_id: int) -> PlainTextResponse:
        payload = get_review(app.state.db_path, review_id)
        if payload is None:
            raise HTTPException(status_code=404, detail="review not found")
        text = payload.get("corrected_metadata_rtf")
        if not text:
            raise HTTPException(status_code=404, detail="no corrected Metadata.rtf")
        return PlainTextResponse(text, media_type="application/rtf")

    @app.get("/api/reviews/{review_id}/frame")
    def frame(review_id: int, t: float = 0.0) -> FileResponse:
        payload = get_review(app.state.db_path, review_id)
        if payload is None:
            raise HTTPException(status_code=404, detail="review not found")
        frames = (payload.get("media") or {}).get("frames") or []
        if not frames:
            raise HTTPException(status_code=404, detail="no frames")
        nearest = min(frames, key=lambda item: abs(float(item.get("t") or 0) - t))
        path = Path(str(nearest.get("path") or ""))
        root = Path(str(payload.get("submission_path") or ""))
        if not path.is_file() or not _inside(path, root):
            raise HTTPException(status_code=404, detail="frame not available")
        return FileResponse(path)

    if _STATIC.is_dir():
        app.mount("/", StaticFiles(directory=_STATIC, html=True), name="ui")
    return app
