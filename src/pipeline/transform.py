"""Pure functions that clean and reshape data. No file or database access here."""


def normalize_status(raw: str | None) -> str:
    """Return an order status in lowercase without surrounding spaces.

    Raises ValueError for None or blank input, so bad rows fail loudly
    instead of becoming an empty status.
    """
    if raw is None or not raw.strip():
        raise ValueError("order status is empty")
    return raw.strip().lower()
