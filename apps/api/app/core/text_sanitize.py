"""Sanitize text for PostgreSQL UTF-8 columns (rejects NUL bytes)."""


def sanitize_pg_text(value: str | None) -> str | None:
    if value is None:
        return None
    # PostgreSQL text/varchar UTF-8 encoding rejects NUL (0x00)
    cleaned = value.replace("\x00", "")
    # Drop lone surrogates / invalid sequences
    return cleaned.encode("utf-8", errors="ignore").decode("utf-8")
