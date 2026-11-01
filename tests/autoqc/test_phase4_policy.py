"""Phase 4: AI use, PII, and licensing. Uncertain cases escalate."""

from __future__ import annotations

from autoqc.audio.transcribe import Transcript, Word
from autoqc.checks.ai_use import score_ai_use
from autoqc.checks.licensing import score_licensing
from autoqc.checks.pii import score_pii
from autoqc.models import FrameObservation, WindowBox
from tests.autoqc.support import make_context


def _window(app: str, title: str, text: str, content: bool = False, z: int = 1) -> WindowBox:
    return WindowBox(
        app=app,
        title=title,
        window_id=f"{app}-{title}",
        x=0,
        y=0,
        w=40,
        h=40,
        z=z,
        is_content=content,
        text=text,
    )


def _obs(windows: list[WindowBox], t: float = 1.0) -> FrameObservation:
    return FrameObservation(
        t=t,
        width=40,
        height=40,
        dock_visible=True,
        dock_position="bottom",
        frontmost_app=windows[0].app if windows else None,
        frontmost_title=windows[0].title if windows else None,
        windows=windows,
        cursor=None,
        cursor_default=None,
        mouse_moving=False,
        click=False,
        click_target=None,
        ocr_text=" ".join(window.text for window in windows),
        wallpaper_default=True,
    )


def _ctx(windows=None, transcript: str = "", task_type: str = "other"):
    ctx = make_context(task_type=task_type, duration=600)
    ctx.observations = [_obs(windows or [])]
    if transcript:
        ctx.transcript = Transcript(
            language="en",
            language_confidence=0.99,
            words=[Word(word, index * 0.4, index * 0.4 + 0.3, 0.95) for index, word in enumerate(transcript.split())],
            source="test",
        )
    else:
        ctx.transcript = Transcript(language="en", language_confidence=0.99, words=[], source="test")
    return ctx


def test_ai_bands_and_escalate():
    none = score_ai_use(_ctx([_window("Numbers", "Budget.xlsx", "Q1 totals", content=True)]))
    assert none.band == 1

    overview = score_ai_use(_ctx([_window("Safari", "Search", "Google AI Overview says the capital is Ottawa")]))
    assert overview.band == 2

    chat = score_ai_use(_ctx([_window("ChatGPT", "New chat", "write the summary for me")]))
    assert chat.band == 3

    ask = score_ai_use(_ctx([_window("Safari", "Google", "Ask anything about this topic")]))
    assert ask.band == 3

    select = score_ai_use(_ctx([_window("Photoshop", "Poster.psd", "subject select the person", content=True)]))
    assert select.band == 3

    coding = score_ai_use(
        _ctx([_window("Visual Studio Code", "main.py", "autocomplete filled the function", content=True)], task_type="Coding")
    )
    assert coding.band == 2

    unclear = _ctx([_window("Photos", "IMG.png", "auto enhance was applied", content=True)])
    result = score_ai_use(unclear)
    assert result.band is None
    assert result.details["escalate"] is True
    assert result.drives_verdict is True
    assert unclear.findings[0].action == "ESCALATE"
    assert unclear.findings[0].category == "unclear_ai"


def test_pii_bands_and_escalate():
    clean = score_pii(_ctx([_window("Numbers", "Budget.xlsx", "total 42", content=True)]))
    assert clean.band == 1

    email = score_pii(_ctx([_window("Mail", "Inbox", "writer@company.test is on screen", content=True)]))
    assert email.band == 3

    ignored = score_pii(_ctx([_window("Safari", "Docs", "contact test@example.com for help")]))
    assert ignored.band == 1

    phone = score_pii(_ctx(transcript="Call me at 415-555-1212 after lunch"))
    assert phone.band == 3

    card_ctx = _ctx([_window("Notes", "Card", "4111 1111 1111 1111", content=True)])
    assert score_pii(card_ctx).band == 3

    name_ctx = _ctx(transcript="My name is Ada Lovelace and I live nearby")
    named = score_pii(name_ctx)
    assert named.band is None
    assert named.details["escalate"] is True
    assert name_ctx.findings[0].category == "unclear_pii"

    placeholder = score_pii(_ctx([_window("Safari", "Form", "sample 123-45-6789")]))
    assert placeholder.band == 1


def test_licensing_logo_fail_and_escalate():
    clean = score_licensing(_ctx([_window("Numbers", "Budget.xlsx", "Q1 totals", content=True)]))
    assert clean.band == 1

    logo = score_licensing(_ctx([
        _window("Numbers", "Budget.xlsx", "Q1 totals", content=True),
        _window("Safari", "Nike.com", "the nike logo is in the header"),
    ]))
    assert logo.band == 1
    assert logo.details["browsing_only"] is True

    stock_browse = score_licensing(_ctx([
        _window("Numbers", "Budget.xlsx", "Q1 totals", content=True),
        _window("Safari", "Shutterstock", "browse shutterstock for ideas"),
    ]))
    assert stock_browse.band == 1

    used = score_licensing(_ctx([_window("Photoshop", "Poster.psd", "shutterstock watermark across the photo", content=True)]))
    assert used.band == 3

    allowed = score_licensing(_ctx([_window("Photoshop", "Poster.psd", "unsplash photo of a desk", content=True)]))
    assert allowed.band == 1

    unclear = _ctx([_window("Photoshop", "Poster.psd", "license unclear for this texture", content=True)])
    result = score_licensing(unclear)
    assert result.band is None
    assert result.details["escalate"] is True
    assert unclear.findings[0].action == "ESCALATE"
    assert unclear.findings[0].category == "unclear_licensing"
