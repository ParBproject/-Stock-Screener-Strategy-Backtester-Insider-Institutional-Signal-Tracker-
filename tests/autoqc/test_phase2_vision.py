"""Phase 2: windows, overlap, Dock, cursor, goal document."""

from __future__ import annotations

from autoqc.checks.environment import environment_findings
from autoqc.checks.goal_doc import score_goal_doc
from autoqc.checks.visibility import score_visibility
from autoqc.ingest.parsers import StudioDoc
from autoqc.rules.loader import load_rules
from autoqc.vision.render import ButtonSpec, FrameSpec, WindowSpec, render_frame
from autoqc.vision.screen import build_actions, observe_frames
from tests.autoqc.support import make_context

GOAL = "Build a one-page budget"


def _window(app, title, x, y, w, h, active=False, body=(), buttons=()):
    return WindowSpec(
        app=app,
        title=title,
        x=x,
        y=y,
        w=w,
        h=h,
        active=active,
        z=2 if active else 1,
        body_lines=tuple(body),
        buttons=tuple(buttons),
    )


def _analyze(specs: list[tuple[float, FrameSpec]], goal: str = GOAL, duration: float | None = None):
    rules = load_rules()
    frames = []
    for stamp, spec in specs:
        spec.rules = rules
        frames.append((stamp, render_frame(spec)))
    if duration is None:
        duration = (specs[-1][0] + 1) if specs else 0
    ctx = make_context(frames, duration=duration, rules=rules)
    ctx.submission.studio = StudioDoc(goal=goal, first_approved_at=None)
    ctx.observations = observe_frames(ctx.frames, rules, ctx.ocr, goal)
    ctx.actions = build_actions(ctx.observations)
    return ctx


def _content():
    return _window("Numbers", "Budget.xlsx", 12, 24, 140, 120, body=("Q1 figures",))


def _palette(active=False, x=176, y=40, w=110, h=80):
    return _window("Preview", "Palette", x, y, w, h, active=active)


def _reference():
    return _window("Safari", "Reference", 160, 28, 148, 110)


def test_detects_app_window_and_treats_tabs_as_one_window():
    ctx = _analyze(
        [
            (
                0.0,
                FrameSpec(
                    windows=(
                        _window("Numbers", "Intro | Draft", 20, 28, 220, 120, active=True),
                    )
                ),
            )
        ]
    )
    windows = ctx.observations[0].windows
    assert len(windows) == 1
    assert windows[0].app == "Numbers"
    assert "Intro" in windows[0].title and "Draft" in windows[0].title
    assert windows[0].active is True
    assert score_visibility(ctx).band == 1


def test_overlap_bands_and_minor_overlap():
    short = _analyze([(float(t), FrameSpec(windows=(_content(), _reference(), _palette(True)))) for t in range(5)])
    short_score = score_visibility(short)
    assert short_score.band == 1
    assert short_score.details["content_covered"] is False

    medium = _analyze([(float(t), FrameSpec(windows=(_content(), _reference(), _palette(True)))) for t in range(8)])
    medium_score = score_visibility(medium)
    assert medium_score.band == 2
    assert medium_score.evidence
    assert medium_score.evidence[0].windows

    long = _analyze([(float(t), FrameSpec(windows=(_content(), _reference(), _palette(True)))) for t in range(32)])
    assert score_visibility(long).band == 3
    assert score_visibility(long).details["content_covered"] is False

    covered = _analyze(
        [
            (
                0.0,
                FrameSpec(
                    windows=(
                        _window("Numbers", "Budget.xlsx", 12, 24, 200, 120, body=("Q1 figures",)),
                        _window("Safari", "Notes panel", 30, 48, 130, 80, active=True),
                    )
                ),
            )
        ]
    )
    covered_score = score_visibility(covered)
    assert covered_score.details["content_covered"] is True
    assert covered_score.band == 3
    assert any("Budget.xlsx" in " ".join(item.windows) for item in covered_score.evidence)

    minor = _analyze(
        [
            (
                0.0,
                FrameSpec(
                    windows=(
                        _content(),
                        _reference(),
                        _palette(True, x=210, y=48, w=60, h=46),
                    )
                ),
            )
        ]
    )
    minor_score = score_visibility(minor)
    assert minor_score.band == 1
    assert minor_score.details["minor_overlap"] is True


def test_goal_document_rules():
    def goal_window(app="Preview"):
        return _window(app, "Goal.pdf", 40, 30, 240, 110, active=True, body=(GOAL,))

    passed = _analyze(
        [
            (0.0, FrameSpec(windows=(goal_window(), _content()))),
            (2.0, FrameSpec(windows=(goal_window(), _content()))),
            (11.0, FrameSpec(windows=(_content(),))),
        ]
    )
    assert score_goal_doc(passed).band == 1
    assert score_goal_doc(passed).details["app"] == "Preview"

    notes = _analyze(
        [
            (0.0, FrameSpec(windows=(goal_window("Notes"),))),
            (11.0, FrameSpec(windows=(_content(),))),
        ]
    )
    assert score_goal_doc(notes).band == 3
    assert "Notes" in score_goal_doc(notes).summary

    textedit = _analyze([(0.0, FrameSpec(windows=(goal_window("TextEdit"),)))])
    assert score_goal_doc(textedit).band == 3

    missing = _analyze([(0.0, FrameSpec(windows=(_content(),))), (12.0, FrameSpec(windows=(_content(),)))])
    assert score_goal_doc(missing).band == 3

    stayed = _analyze(
        [
            (0.0, FrameSpec(windows=(goal_window(),))),
            (12.0, FrameSpec(windows=(goal_window(),))),
        ]
    )
    assert score_goal_doc(stayed).band == 3


def test_dock_cursor_and_click():
    docked = _analyze([(0.0, FrameSpec(dock="bottom", windows=(_content(),)))])
    assert docked.observations[0].dock_visible is True
    assert docked.observations[0].dock_position == "bottom"

    hidden = _analyze([(0.0, FrameSpec(dock=None, windows=(_content(),), cursor=(30, 50)))])
    assert hidden.observations[0].dock_visible is False
    assert hidden.observations[0].cursor_default is True
    categories = {item.category for item in environment_findings(hidden)}
    assert "dock_not_visible" in categories

    left = _analyze([(0.0, FrameSpec(dock="left", windows=(_content(),)))])
    assert left.observations[0].dock_position == "left"

    custom = _analyze(
        [(0.0, FrameSpec(dock="bottom", windows=(_content(),), cursor=(28, 48), cursor_kind="custom"))]
    )
    assert custom.observations[0].cursor_default is False
    assert any(item.category == "cursor_not_default" for item in environment_findings(custom))

    button = ButtonSpec(20, 12, 80, 22, "Export")
    pressed = ButtonSpec(20, 12, 80, 22, "Export", fill=(150, 190, 230))
    base = _window("Numbers", "Budget.xlsx", 16, 26, 240, 120, active=True, buttons=(button,))
    clicked = _window("Numbers", "Budget.xlsx", 16, 26, 240, 120, active=True, buttons=(pressed,))
    interaction = _analyze(
        [
            (0.0, FrameSpec(windows=(base,), cursor=(70, 70))),
            (1.0, FrameSpec(windows=(clicked,), cursor=(70, 70))),
        ]
    )
    assert interaction.observations[1].click is True
    assert "Export" in (interaction.observations[1].click_target or "")
    assert any(action.kind == "click" and "Export" in action.target for action in interaction.actions)
