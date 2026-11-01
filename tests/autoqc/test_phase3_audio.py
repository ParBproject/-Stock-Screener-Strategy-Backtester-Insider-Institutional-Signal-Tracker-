"""Phase 3: narration, clarity, English, profanity, and the epilogue."""

from __future__ import annotations

import math
import struct
import wave
import zipfile
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from autoqc.audio.narration import classify_utterance
from autoqc.audio.transcribe import Word, transcribe_with_whisper
from autoqc.audio.vad import energy_speech_spans
from autoqc.checks.clarity import score_clarity
from autoqc.checks.english import score_english
from autoqc.checks.epilogue import score_epilogue
from autoqc.checks.narration import score_narration
from autoqc.checks.profanity import score_profanity
from autoqc.models import Action, WindowBox
from autoqc.models import FrameObservation
from autoqc.rules.loader import load_rules
from tests.autoqc.support import make_context, solid

PT = ZoneInfo("America/Los_Angeles")
EXAMPLE = "I'll click the blue Export button in the top right to save the chart as a PDF."


def _say(text: str, start: float = 0.0, confidence: float = 0.95, step: float = 0.45) -> list[Word]:
    words = []
    clock = start
    for token in text.split():
        words.append(Word(token, clock, clock + 0.4, confidence))
        clock += step
    return words


def _ctx(words=None, actions=None, observations=None, duration=600.0, approved=None, zip_path=None, language="en", language_confidence=0.99):
    from autoqc.audio.transcribe import Transcript

    ctx = make_context(duration=duration)
    ctx.transcript = Transcript(
        language=language,
        language_confidence=language_confidence,
        words=list(words or []),
        source="test",
    )
    ctx.actions = list(actions or [])
    ctx.observations = list(observations or [])
    ctx.submission.idea_first_approved_at = approved
    ctx.submission.zip_path = zip_path
    return ctx


def _click(t: float, target: str = "Export") -> Action:
    return Action(t=t, kind="click", app="Numbers", target=target, window="Numbers - Budget.xlsx")


def test_example_sentence_has_what_where_and_why():
    label = classify_utterance(_click(1), EXAMPLE, load_rules())
    assert label.what and label.where and label.why
    vague = classify_utterance(_click(1), "I'll click it to save the chart.", load_rules())
    assert vague.what and vague.why and not vague.where


def test_narration_bands():
    good = _say(EXAMPLE, start=4.0)
    perfect = _ctx(words=good, actions=[_click(5.0)])
    assert score_narration(perfect).band == 1

    located = _say("I'll click the Export button in the toolbar.", start=4.0)
    band2 = _ctx(words=located, actions=[_click(5.0 + i * 20) for i in range(4)])
    # One utterance cannot cover clicks 20s apart. Repeat the line at each click.
    words = []
    actions = []
    for index in range(4):
        stamp = index * 20
        words.extend(_say("I'll click the Export button in the toolbar.", start=stamp))
        actions.append(_click(stamp + 0.5))
    assert score_narration(_ctx(words=words, actions=actions)).band == 2

    weak_words = []
    weak_actions = []
    for index in range(4):
        stamp = index * 20
        weak_words.extend(_say("I'll click it to save the chart.", start=stamp))
        weak_actions.append(_click(stamp + 0.5))
    failed = score_narration(_ctx(words=weak_words, actions=weak_actions))
    assert failed.band == 3
    assert failed.drives_verdict is True

    silent = score_narration(_ctx(words=[], actions=[_click(1)]))
    assert silent.band == 3
    assert silent.drives_verdict is False


def test_clarity_and_low_confidence_spans():
    clear = score_clarity(_ctx(words=_say(" ".join(["the budget cell is updated now"] * 4), confidence=0.96)))
    assert clear.band == 1
    assert clear.details["wpm"] is not None

    mumbled = []
    clock = 0.0
    for _ in range(12):
        mumbled.append(Word("something", clock, clock + 0.5, 0.3))
        clock += 0.5
    unclear = score_clarity(_ctx(words=mumbled))
    assert unclear.band == 3
    assert unclear.evidence
    assert unclear.details["low_span_count"] >= 1

    missing = score_clarity(_ctx(words=[]))
    assert missing.band is None
    assert missing.drives_verdict is False


def test_english_narration_and_deliverables(tmp_path: Path):
    assert score_english(_ctx(words=_say("hello there"))).band == 1

    foreign = score_english(_ctx(words=_say("bonjour"), language="fr", language_confidence=0.96))
    assert foreign.band == 3

    notes = tmp_path / "deliverables.zip"
    paragraph = (
        "This is the final budget and it is ready for the review. "
        "The table is complete and the chart is saved as a file."
    )
    french = "Le document est pret pour le client et il faut traduire la page du rapport encore."
    with zipfile.ZipFile(notes, "w") as archive:
        archive.writestr("notes.txt", paragraph)
    english_file = score_english(_ctx(words=[], language="", language_confidence=0.0, zip_path=notes))
    assert english_file.band == 1

    bad = tmp_path / "bad.zip"
    with zipfile.ZipFile(bad, "w") as archive:
        archive.writestr("notes.txt", french)
    assert score_english(_ctx(words=_say("hello there"), zip_path=bad)).band == 3

    unknown = score_english(_ctx(words=[], language="", language_confidence=0.0))
    assert unknown.band is None
    assert unknown.drives_verdict is False


def test_profanity_bands():
    clean = score_profanity(_ctx(words=_say("I click the export button.")))
    assert clean.band == 1

    safari = WindowBox(
        app="Safari",
        title="Article",
        window_id="safari",
        x=0,
        y=0,
        w=10,
        h=10,
        z=1,
        text="a damn headline",
    )
    obs = FrameObservation(
        t=3.0,
        width=10,
        height=10,
        dock_visible=True,
        dock_position="bottom",
        frontmost_app="Safari",
        frontmost_title="Article",
        windows=[safari],
        cursor=None,
        cursor_default=None,
        mouse_moving=False,
        click=False,
        click_target=None,
        ocr_text="a damn headline",
        wallpaper_default=True,
    )
    mild = score_profanity(_ctx(words=_say("I read the article."), observations=[obs]))
    assert mild.band == 2

    typed = WindowBox(
        app="Numbers",
        title="Budget.xlsx",
        window_id="sheet",
        x=0,
        y=0,
        w=20,
        h=20,
        z=1,
        is_content=True,
        text="this is shit",
    )
    typed_obs = FrameObservation(
        t=4.0,
        width=20,
        height=20,
        dock_visible=True,
        dock_position="bottom",
        frontmost_app="Numbers",
        frontmost_title="Budget.xlsx",
        windows=[typed],
        cursor=None,
        cursor_default=None,
        mouse_moving=False,
        click=False,
        click_target=None,
        ocr_text="this is shit",
        wallpaper_default=True,
    )
    assert score_profanity(_ctx(words=_say("I type the total."), observations=[typed_obs])).band == 3
    assert score_profanity(_ctx(words=_say("oh fuck"))).band == 3


def test_epilogue_bands():
    close = (
        "To verify the budget I checked every total and then checked the formulas again. "
        "My approach was to enter each line by hand and keep a written method. "
        "The challenge was the missing receipt and it was difficult to match. "
        "I care about quality and polish. What I learned is to label the columns earlier."
    )
    filler = _say("I click the cell and type the value.", start=0.0)
    detailed = filler + _say(close, start=1000.0)
    assert score_epilogue(_ctx(words=detailed, duration=1100)).band == 1

    long = filler + _say(close, start=700.0)
    assert score_epilogue(_ctx(words=long, duration=1100)).band == 2

    thin = filler + _say("I checked it.", start=1000.0)
    assert score_epilogue(_ctx(words=thin, duration=1100)).band == 2

    missing = score_epilogue(_ctx(words=filler, duration=1100))
    assert missing.band is None
    assert missing.unscored_reason == "Missing epilogue - does not block approval"
    assert missing.drives_verdict is False

    before = datetime(2026, 10, 19, 17, 59, tzinfo=PT)
    skipped = score_epilogue(_ctx(words=[], duration=1100, approved=before))
    assert skipped.band is None
    assert "not required" in (skipped.unscored_reason or "")
    assert skipped.drives_verdict is False

    at_cutoff = datetime(2026, 10, 19, 18, 0, tzinfo=PT)
    required = score_epilogue(_ctx(words=filler, duration=1100, approved=at_cutoff))
    assert required.unscored_reason == "Missing epilogue - does not block approval"


def test_energy_vad_and_whisper_opt_out(tmp_path: Path):
    path = tmp_path / "tone.wav"
    rate = 16000
    with wave.open(str(path), "w") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(rate)
        frames = []
        for index in range(rate * 3):
            if rate <= index < rate * 2:
                sample = int(8000 * math.sin(2 * math.pi * 440 * index / rate))
            else:
                sample = 0
            frames.append(struct.pack("<h", sample))
        handle.writeframes(b"".join(frames))
    spans = energy_speech_spans(path)
    assert spans
    assert spans[0][0] == 1.0 or abs(spans[0][0] - 1.0) < 0.15
    assert transcribe_with_whisper(tmp_path / "no-video.mp4", allow_download=False) is None
    from autoqc.audio.diarize import diarize_turns
    from autoqc.vision.llm import understand_frame

    rules = load_rules()
    assert diarize_turns(None, rules) is None
    assert understand_frame(solid(8, 8), rules) is None
