"""
File: backend/validator.py
Project: Emerald City Chess Hub (EC-ChessHub) — CS 422 Project 2
Author: Arav Sarma (Backend & API Lead)
Created: 2026-11-27

Purpose:
    Validates and sanitizes incoming HTTP/JSON request payloads before they
    reach the Database or Standings modules. Enforces required fields,
    valid UO email formatting (`@uoregon.edu`), allowed skill tiers, and
    standard chess match outcomes.

Strict Boundary (NFR-03):
    Pure input-validation module. Does not import `sqlite3` or perform I/O.

Relationships to Other Files:
    - Called by `backend/server.py` for every `POST` and `PUT` endpoint.
    - Tested by `tests/test_api.py`.

Dependencies:
    - Python 3.11+ Standard Library only (`re`, `typing`).
"""

import re
from typing import Any, Dict, Tuple

# Compiled regex matching valid University of Oregon email addresses.
# Scope: module-level constant; Lifetime: duration of the Python process.
UO_EMAIL_PATTERN = re.compile(r"^[A-Za-z0-9._%+-]+@uoregon\.edu$", re.IGNORECASE)

# Allowed self-selected chess experience tiers (must match database/schema.sql).
# Scope: module-level constant; Lifetime: duration of the Python process.
ALLOWED_SKILL_TIERS: Tuple[str, ...] = ("Beginner", "Casual", "Tournament")

# Allowed chess match result strings (must match database/schema.sql).
# Scope: module-level constant; Lifetime: duration of the Python process.
ALLOWED_OUTCOMES: Tuple[str, ...] = ("1-0", "0-1", "1/2-1/2")


class ValidationError(ValueError):
    """Raised when an incoming JSON payload fails schema or domain validation."""


class PayloadValidator:
    """
    Stateless collection of payload validation methods for EC-ChessHub API routes.
    """

    @staticmethod
    def _require_non_empty_str(
        payload: Dict[str, Any],
        field: str,
        max_length: int = 255,
    ) -> str:
        """
        Verifies that `field` is present in `payload`, is a string, is non-empty
        after stripping whitespace, and does not exceed `max_length`.

        Args:
            payload: Parsed JSON request body dict.
            field: Required key name.
            max_length: Maximum permitted character count.

        Returns:
            Trimmed string value.

        Raises:
            ValidationError: If missing, non-string, blank, or too long.
        """
        value: Any = payload.get(field)
        if not isinstance(value, str) or not value.strip():
            raise ValidationError(f"Field '{field}' is required and must be a non-empty string.")

        cleaned: str = value.strip()
        if len(cleaned) > max_length:
            raise ValidationError(f"Field '{field}' must be at most {max_length} characters.")
        return cleaned

    @classmethod
    def validate_member_registration(cls, payload: Dict[str, Any]) -> Dict[str, str]:
        """
        Validates an in-site student registration payload (FR-04).

        Required Fields:
            - name: Non-empty string (<= 100 chars).
            - email: Valid `@uoregon.edu` email address.
            - skill_tier: One of 'Beginner', 'Casual', or 'Tournament'.

        Returns:
            Sanitized dict `{name, email, skill_tier}`.
        """
        if not isinstance(payload, dict):
            raise ValidationError("Request body must be a JSON object.")

        name: str = cls._require_non_empty_str(payload, "name", max_length=100)
        email: str = cls._require_non_empty_str(payload, "email", max_length=150).lower()

        # Enforce University of Oregon email format.
        if not UO_EMAIL_PATTERN.match(email):
            raise ValidationError("Email must be a valid @uoregon.edu address.")

        # Support both snake_case (`skill_tier`) and camelCase (`skillTier`) from React.
        raw_tier: Any = payload.get("skill_tier", payload.get("skillTier"))
        if not isinstance(raw_tier, str) or raw_tier.strip() not in ALLOWED_SKILL_TIERS:
            raise ValidationError(
                f"Field 'skill_tier' must be one of: {', '.join(ALLOWED_SKILL_TIERS)}."
            )

        return {
            "name": name,
            "email": email,
            "skill_tier": raw_tier.strip(),
        }

    @classmethod
    def validate_event(cls, payload: Dict[str, Any]) -> Dict[str, str]:
        """
        Validates a create/update club event payload (FR-07).

        Required Fields:
            - title: Non-empty string (<= 150 chars).
            - date_time (or dateTime): Non-empty ISO-8601 date/time string.
            - location: Non-empty string (<= 150 chars).
            - description: Optional string (<= 2000 chars).
        """
        if not isinstance(payload, dict):
            raise ValidationError("Request body must be a JSON object.")

        title: str = cls._require_non_empty_str(payload, "title", max_length=150)

        # Accept either snake_case or camelCase date field for frontend convenience.
        raw_dt: Any = payload.get("date_time", payload.get("dateTime"))
        if not isinstance(raw_dt, str) or not raw_dt.strip():
            raise ValidationError("Field 'date_time' is required and must be a non-empty string.")
        date_time: str = raw_dt.strip()

        location: str = cls._require_non_empty_str(payload, "location", max_length=150)

        raw_desc: Any = payload.get("description", "")
        if raw_desc is None:
            raw_desc = ""
        if not isinstance(raw_desc, str):
            raise ValidationError("Field 'description' must be a string.")
        description: str = raw_desc.strip()
        if len(description) > 2000:
            raise ValidationError("Field 'description' must be at most 2000 characters.")

        return {
            "title": title,
            "date_time": date_time,
            "location": location,
            "description": description,
        }

    @classmethod
    def validate_announcement(cls, payload: Dict[str, Any]) -> Dict[str, str]:
        """
        Validates a create/update club announcement payload (FR-07).

        Required Fields:
            - title: Non-empty string (<= 150 chars).
            - body: Non-empty string (<= 4000 chars).
        """
        if not isinstance(payload, dict):
            raise ValidationError("Request body must be a JSON object.")

        title: str = cls._require_non_empty_str(payload, "title", max_length=150)
        body: str = cls._require_non_empty_str(payload, "body", max_length=4000)
        return {"title": title, "body": body}

    @classmethod
    def validate_match(cls, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Validates a match result submission payload (FR-08).

        Required Fields:
            - white_id (or whiteId): Positive integer member ID.
            - black_id (or blackId): Positive integer member ID (must differ from white_id).
            - outcome: One of '1-0', '0-1', or '1/2-1/2'.
        """
        if not isinstance(payload, dict):
            raise ValidationError("Request body must be a JSON object.")

        raw_white: Any = payload.get("white_id", payload.get("whiteId"))
        raw_black: Any = payload.get("black_id", payload.get("blackId"))

        # Booleans are a subclass of int in Python; explicitly reject them.
        if isinstance(raw_white, bool) or not isinstance(raw_white, int) or raw_white <= 0:
            raise ValidationError("Field 'white_id' must be a positive integer.")
        if isinstance(raw_black, bool) or not isinstance(raw_black, int) or raw_black <= 0:
            raise ValidationError("Field 'black_id' must be a positive integer.")
        if raw_white == raw_black:
            raise ValidationError("White and Black players must be different members.")

        outcome: Any = payload.get("outcome")
        if not isinstance(outcome, str) or outcome not in ALLOWED_OUTCOMES:
            raise ValidationError(
                f"Field 'outcome' must be one of: {', '.join(ALLOWED_OUTCOMES)}."
            )

        return {
            "white_id": raw_white,
            "black_id": raw_black,
            "outcome": outcome,
        }

    @classmethod
    def validate_login(cls, payload: Dict[str, Any]) -> Dict[str, str]:
        """
        Validates an officer login payload (FR-06).

        Required Fields:
            - username: Non-empty string.
            - password: Non-empty string.
        """
        if not isinstance(payload, dict):
            raise ValidationError("Request body must be a JSON object.")

        username: str = cls._require_non_empty_str(payload, "username", max_length=100).lower()
        password: str = cls._require_non_empty_str(payload, "password", max_length=200)
        return {"username": username, "password": password}