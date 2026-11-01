"""Timestamp formatting for notes and the CLI."""


def fmt_ts(seconds: float | None) -> str:
    """Format a timestamp as ``MM:SS`` or ``H:MM:SS``."""
    if seconds is None:
        return "--:--"
    total = max(0, int(round(float(seconds))))
    hours, rem = divmod(total, 3600)
    minutes, secs = divmod(rem, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"
