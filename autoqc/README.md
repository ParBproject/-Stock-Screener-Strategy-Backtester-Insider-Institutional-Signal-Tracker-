# Auto QC

Reviewer-assist for screen-recorded macOS task videos. It scores a submission and drafts notes. It does not send anything. A human reviewer makes the final call.

The finance app at the repository root is separate. Auto QC lives in this package.

## Run

```bash
pip install -r requirements-autoqc.txt
python -m autoqc review path/to/submission
```

The review JSON is written to `path/to/submission/.autoqc/review.json`. `--json -` prints it to stdout. `--config DIR` deep-merges `DIR/rules.yaml` over the packaged rubric and, when present, replaces the policy lists (`restricted_apps.txt`, `allowed_ai.txt`, `profanity.txt`, `pii_rules.yaml`, `licensing_rules.yaml`).

```bash
python -m pytest tests/autoqc -q
```

Tests use synthetic frames and do not need a GPU, ffmpeg models, or API keys. ffmpeg is used when a real recording is ingested.

## Submission folder

- `recording.mp4` or `.mov` (ffprobe duration is authoritative), or `frames.csv` plus PNGs (`filename,t`)
- `Metadata.rtf` with `Request`, `Task Description` (including an `Apps:` line), and `TOPOLOGY`
- `TaskRecorder.txt` or `.json` (`Description` and `Apps`)
- `StudioGoal.txt` (`Goal`, optional `First-Approved`)
- `deliverables.zip` (file names are compared, not file bytes)
- optional `submission.json` for `task_type`, `review_number` (1–3), `idea_first_approved_at`, `prior_notes`, `prior_submission`, `locked_fields`, and `duration_seconds` (frame bundles only)
- optional `transcript.json` and `prior_notes.txt`

## Thresholds

Edit `autoqc/rules/data/rules.yaml`. Findings below `low_confidence` (0.60) are listed under "Needs human look" and do not change the recommended action.

| Key | Default | Meaning |
| --- | --- | --- |
| `typing.max_share` | 0.25 | Typing cap. At or under is band 1. |
| `typing.max_share_coding_writing` | 0.35 | Cap for Coding and Content & Writing. |
| `typing.segment_feedback_seconds` | 45 | One segment longer than this is feedback only. |
| `overlap.cover_fraction` | 0.25 | Share of another window that counts as covering it. |
| `overlap.band2_over_seconds` | 6 | Cover longer than this, up to 30s, is band 2. |
| `overlap.band3_over_seconds` | 30 | Cover longer than this is band 3. |
| `overlap.working_content_fraction` | 0.15 | Any cover of the working body above this is band 3. |
| `narration.min_fraction` | 0.70 | Share of actions that need what/where (and why for band 1). |
| `video.min_seconds` / `max_seconds` | 900 / 3299 | 15:00 through the end of 54:59. |
| `video.long_notice_seconds` | 3059 | 50:59–54:59 is noted and is not a deduction by itself. |
| `epilogue.max_seconds` | 240 | Epilogue longer than 4:00 is band 2, not a send-back. |
| `epilogue.not_required_before` | 2026-10-19T18:00:00-07:00 | Ideas first approved before 6pm Pacific that day skip the epilogue. |
| `goal_doc.promptly_within_seconds` | 10 | Goal document must be gone after this. |
| `clock.edge_seconds` | 10 | Seconds must be readable in the first and last 10s. |
| `ui_feedback.intro_seconds` | 20 | Intro longer than this is optional feedback. |
| `ui_feedback.silence_seconds` | 45 | A narration gap longer than this is optional feedback. |
| `key_ideas.recall_min` | 0.85 | Metadata wording can differ if key ideas are kept. |

Typing share is the time-weighted ratio of consecutive frames whose content-area change falls between `typing.min_changed_pixels` and `typing.max_changed_pixels`. That computed ratio is the number item 7 reports.

## Optional models

Packaged defaults do not download weights.

- `ocr_engine`: `auto` (Tesseract binary if on PATH, otherwise the built-in glyph reader), `glyph`, `tesseract`, or `easyocr`. EasyOCR is never selected automatically.
- `audio.backend`: `auto` reads `transcript.json` and does not download a model. `whisper` uses faster-whisper when installed. Set `audio.allow_model_download` to allow a first-run download.
- `audio.vad`: `energy` always works. `webrtcvad` is used when that package is installed.
- `audio.diarize`: pyannote runs only when enabled, installed, and `HF_TOKEN` or `HUGGING_FACE_HUB_TOKEN` is set. Otherwise the narrator is treated as a single speaker.
- `vision_llm`: off unless `enabled` and an endpoint are set. The deterministic screen parser still runs.
- Scene cuts use ffmpeg. Set `ingest.scene_backend` to `pyscenedetect` when that package is installed.
