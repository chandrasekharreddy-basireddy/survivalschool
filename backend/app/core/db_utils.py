from __future__ import annotations


def escape_like(value: str) -> str:
    """Escape SQL LIKE/ILIKE metacharacters (%, _) so a value coming from a
    user-controlled field (a search query, a free-text profile field) is
    matched literally instead of as a wildcard pattern. Escapes the escape
    character itself first so a literal backslash in the input can't be
    used to unescape a following % or _."""
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
