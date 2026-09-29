"""Read optional vendor credentials.

yfinance does not need a key. Nothing in this repository should embed a
token. Callers that add a keyed vendor should use :func:`get_secret`, which
reads the process environment first and Streamlit secrets second.
"""

from __future__ import annotations

import os
from collections.abc import Mapping


def get_secret(
    name: str,
    *,
    environ: Mapping[str, str] | None = None,
    secrets: Mapping | None = None,
) -> str | None:
    """Return a stripped secret, or None when it is missing or blank."""
    if environ is None:
        _load_dotenv()
        source = os.environ
    else:
        source = environ
    from_env = source.get(name) if source is not None else None
    if _present(from_env):
        return str(from_env).strip()

    store = _streamlit_secrets() if secrets is None else secrets
    if store is None or name not in store:
        return None
    value = store[name]
    if not _present(value):
        return None
    return str(value).strip()


def _present(value) -> bool:
    if value is None:
        return False
    return bool(str(value).strip())


def _load_dotenv() -> None:
    """Load a local ``.env`` without overriding variables already set."""
    try:
        from dotenv import find_dotenv, load_dotenv
    except Exception:
        return
    try:
        path = find_dotenv(usecwd=True)
        if path:
            load_dotenv(path, override=False)
    except Exception:
        return


def _streamlit_secrets():
    try:
        import streamlit as st
    except Exception:
        return None
    try:
        return st.secrets
    except Exception:
        return None
