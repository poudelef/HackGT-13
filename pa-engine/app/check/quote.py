"""Every free-text answer quote must be an exact substring of the original note (G3)."""

from __future__ import annotations

MIN_LEN = 12


def verify(quote: str | None, original: str | None) -> bool:
    if not quote or not original:
        return False
    if len(quote.strip()) < MIN_LEN:
        return False
    return quote in original


def value_digits_inside(quote: str | None, value) -> bool:
    if quote is None or value is None:
        return False
    digits = str(value)
    if digits.endswith(".0"):
        digits = digits[:-2]
    return digits in quote
