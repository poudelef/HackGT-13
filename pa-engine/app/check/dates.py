"""Dates and numbers are code. The engine clock is DEMO_TODAY when it is set."""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta

from app.config import settings

_MONTHS = {
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
    "july": 7, "august": 8, "september": 9, "october": 10, "november": 11, "december": 12,
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "jun": 6, "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}


def today() -> date:
    raw = settings.demo_today
    if raw:
        return date.fromisoformat(raw)
    return date.today()


def parse_date(value: str | None) -> date | None:
    if not value:
        return None
    value = value.strip()
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    match = re.search(
        r"(january|february|march|april|may|june|july|august|september|october|november|december|"
        r"jan|feb|mar|apr|jun|jul|aug|sep|oct|nov|dec)\s+(\d{1,2}),?\s+(20\d{2})",
        value,
        re.I,
    )
    if match:
        return date(int(match.group(3)), _MONTHS[match.group(1).lower()], int(match.group(2)))
    return None


def shift(day: date, count: int, unit: str | None) -> date:
    unit = (unit or "days").lower()
    if unit.startswith("week"):
        return day - timedelta(weeks=count)
    if unit.startswith("day"):
        return day - timedelta(days=count)
    if unit.startswith("month"):
        return day - timedelta(days=30 * count)
    if unit.startswith("year"):
        return day - timedelta(days=365 * count)
    return day - timedelta(days=count)


def within(value: date, count: int, unit: str | None, clock: date | None = None) -> bool:
    clock = clock or today()
    if value > clock:
        return False
    return value >= shift(clock, count, unit)


def at_least_ago(value: date, count: int, unit: str | None, clock: date | None = None) -> bool:
    clock = clock or today()
    return value <= shift(clock, count, unit)


def age_years(dob: date, clock: date | None = None) -> int:
    clock = clock or today()
    years = clock.year - dob.year
    if (clock.month, clock.day) < (dob.month, dob.day):
        years -= 1
    return years


def display(value: date) -> str:
    return value.strftime("%b %-d").replace(" 0", " ")
