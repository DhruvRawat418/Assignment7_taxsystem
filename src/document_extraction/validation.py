"""Shared entry validation for Intake; validate before adding SSNs to state."""
import re


def validate_synthetic_ssn(value: str) -> str:
    match = re.fullmatch(r"(\d{3})[- ]?(\d{2})[- ]?(\d{4})", value.strip())
    if match is None or not 900 <= int(match[1]) <= 999:
        # Never interpolate the rejected identifier into exceptions or logs.
        raise ValueError("Use a synthetic SSN beginning with 900 through 999.")
    return f"{match[1]}-{match[2]}-{match[3]}"
