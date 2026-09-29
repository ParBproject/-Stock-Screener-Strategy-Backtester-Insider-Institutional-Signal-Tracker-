"""API keys stay in the environment, a .env file, or Streamlit secrets."""

import re
from pathlib import Path

import pytest

from utils.secrets import get_secret

ROOT = Path(__file__).resolve().parents[1]
ASSIGNED_SECRET = re.compile(
    r"(?i)(api_key|secret|token|password)\s*=\s*['\"][A-Za-z0-9_\-]{8,}['\"]"
)


def test_environment_wins_and_blanks_are_ignored():
    assert get_secret("EXAMPLE_API_KEY", environ={"EXAMPLE_API_KEY": "  from-env  "}, secrets={"EXAMPLE_API_KEY": "other"}) == "from-env"
    assert get_secret("EXAMPLE_API_KEY", environ={"EXAMPLE_API_KEY": "  "}, secrets={"EXAMPLE_API_KEY": " from-secrets "}) == "from-secrets"
    assert get_secret("EXAMPLE_API_KEY", environ={}, secrets={"EXAMPLE_API_KEY": "   "}) is None


def test_dotenv_file_is_read_without_overriding_the_environment(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env").write_text("EXAMPLE_API_KEY=from-dotenv\n", encoding="utf-8")
    monkeypatch.delenv("EXAMPLE_API_KEY", raising=False)
    try:
        assert get_secret("EXAMPLE_API_KEY", secrets={}) == "from-dotenv"
        monkeypatch.setenv("EXAMPLE_API_KEY", "already-set")
        assert get_secret("EXAMPLE_API_KEY", secrets={}) == "already-set"
    finally:
        import os

        os.environ.pop("EXAMPLE_API_KEY", None)


def test_source_does_not_assign_a_secret_literal():
    offenders = []
    for path in ROOT.rglob("*.py"):
        if any(part in {".git", ".venv", "venv"} for part in path.parts):
            continue
        text = path.read_text(encoding="utf-8")
        if ASSIGNED_SECRET.search(text):
            offenders.append(str(path.relative_to(ROOT)))
    assert offenders == []


def test_missing_name_is_none(monkeypatch):
    monkeypatch.delenv("EXAMPLE_API_KEY", raising=False)
    assert get_secret("EXAMPLE_API_KEY", secrets={}) is None
