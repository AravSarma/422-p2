"""
File: backend/auth.py
Project: Emerald City Chess Hub (EC-ChessHub) — CS 422 Project 2
Author: Arav Sarma (Backend & API Lead)
Created: 2026-11-27

Purpose:
    Implements officer password hashing (PBKDF2-HMAC-SHA256), credential
    verification, and in-memory bearer session token management (FR-06).

Strict Boundary (NFR-03):
    Does NOT import `sqlite3`. All officer record lookups are delegated to
    `DatabaseManager.get_officer_by_username()`.

Relationships to Other Files:
    - Used by `backend/server.py` to authenticate officer login requests and
      guard administrative HTTP routes (`/api/events`, `/api/announcements`,
      `/api/matches`, `/api/members`).
    - Delegates credential storage/retrieval to `database/db_manager.py`.
    - Tested by `tests/test_api.py`.

Dependencies:
    - Python 3.11+ Standard Library only (`hashlib`, `hmac`, `secrets`, `time`, `typing`).
"""

import hashlib
import hmac
import secrets
import time
from typing import Any, Dict, Mapping, Optional

# PBKDF2 iteration count for password hashing (OWASP recommended floor).
# Scope: module-level constant; Lifetime: duration of the Python process.
PBKDF2_ITERATIONS: int = 120_000

# Default session token time-to-live in seconds (8 hours).
# Scope: module-level constant; Lifetime: duration of the Python process.
DEFAULT_SESSION_TTL_SECONDS: int = 8 * 60 * 60


def hash_password(password: str, salt: Optional[str] = None) -> str:
    """
    Hashes a plaintext officer password using PBKDF2-HMAC-SHA256 with a random salt.

    Format returned:
        "pbkdf2_sha256$<iterations>$<hex_salt>$<hex_digest>"

    Args:
        password: Plaintext password string.
        salt: Optional hex-encoded salt (auto-generated via `secrets` if omitted).

    Returns:
        Formatted password hash string safe for storage in `officers.password_hash`.
    """
    # Generate a cryptographically secure 16-byte salt if the caller did not supply one.
    # Scope: local variable; Lifetime: duration of hash_password().
    salt_hex: str = salt if salt is not None else secrets.token_hex(16)

    # Derive a 32-byte key from the UTF-8 password and salt using PBKDF2-HMAC-SHA256.
    derived_key: bytes = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt_hex.encode("utf-8"),
        PBKDF2_ITERATIONS,
    )
    return f"pbkdf2_sha256${PBKDF2_ITERATIONS}${salt_hex}${derived_key.hex()}"


def verify_password(password: str, stored_hash: str) -> bool:
    """
    Verifies a plaintext password against a stored PBKDF2 hash in constant time.

    Args:
        password: Candidate plaintext password submitted during login.
        stored_hash: Formatted hash string retrieved from `DatabaseManager`.

    Returns:
        True if the password matches `stored_hash`; False otherwise.
    """
    try:
        # Unpack the four '$'-delimited components of the stored hash.
        algorithm, iter_str, salt_hex, expected_hex = stored_hash.split("$", 3)

        # Reject unrecognized hash formats immediately.
        if algorithm != "pbkdf2_sha256":
            return False

        # Recompute the PBKDF2 digest using the stored iteration count and salt.
        iterations: int = int(iter_str)
        candidate_key: bytes = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            salt_hex.encode("utf-8"),
            iterations,
        )

        # Use hmac.compare_digest to prevent timing side-channel attacks.
        return hmac.compare_digest(candidate_key.hex(), expected_hex)
    except (ValueError, TypeError):
        # Malformed hash strings never authenticate.
        return False


class AuthManager:
    """
    Manages officer authentication and bearer-token sessions for EC-ChessHub.

    Instance Attributes:
        db (Any):
            Purpose: DatabaseManager instance used to look up officer records.
            Scope: Instance attribute; Lifetime: lifetime of AuthManager.
        session_ttl (int):
            Purpose: Session expiration window in seconds.
            Scope: Instance attribute; Lifetime: lifetime of AuthManager.
        _sessions (Dict[str, Dict[str, Any]]):
            Purpose: In-memory map of active bearer tokens to {username, expires_at}.
            Scope: Private instance attribute; Lifetime: lifetime of AuthManager.
    """

    def __init__(
        self,
        db: Any,
        session_ttl: int = DEFAULT_SESSION_TTL_SECONDS,
    ) -> None:
        """
        Initializes AuthManager with a DatabaseManager dependency.

        Args:
            db: Encapsulated DatabaseManager instance (never raw sqlite3).
            session_ttl: Token lifetime in seconds before automatic expiry.
        """
        self.db = db
        self.session_ttl: int = session_ttl
        self._sessions: Dict[str, Dict[str, Any]] = {}

    def ensure_default_officer(self, username: str, password: str) -> None:
        """
        Seeds an initial officer account on startup if it does not already exist.

        Args:
            username: Default officer username (e.g., from OFFICER_USERNAME env var).
            password: Default officer plaintext password (hashed before storage).
        """
        # Only create the officer if no account with this username exists yet.
        existing: Optional[Dict[str, Any]] = self.db.get_officer_by_username(username)
        if existing is None:
            pw_hash: str = hash_password(password)
            self.db.create_officer(username, pw_hash)

    def login(self, username: str, password: str) -> Optional[Dict[str, Any]]:
        """
        Authenticates an officer and issues a cryptographically random bearer token.

        Args:
            username: Submitted officer username.
            password: Submitted plaintext password.

        Returns:
            Dict `{token, username, expires_at}` on success, or None if invalid.
        """
        # Look up the officer record through the Database module.
        officer: Optional[Dict[str, Any]] = self.db.get_officer_by_username(username)
        if officer is None:
            return None

        # Verify submitted password against the stored PBKDF2 hash.
        if not verify_password(password, officer["password_hash"]):
            return None

        # Issue a 32-byte URL-safe random bearer token and store its expiry.
        token: str = secrets.token_urlsafe(32)
        expires_at: float = time.time() + self.session_ttl
        self._sessions[token] = {
            "username": officer["username"],
            "expires_at": expires_at,
        }
        return {
            "token": token,
            "username": officer["username"],
            "expires_at": int(expires_at),
        }

    def logout(self, token: str) -> bool:
        """
        Revokes an active session token.

        Args:
            token: Bearer token string to invalidate.

        Returns:
            True if the token existed and was removed; False otherwise.
        """
        return self._sessions.pop(token, None) is not None

    def extract_bearer_token(self, headers: Mapping[str, str]) -> Optional[str]:
        """
        Extracts the bearer token from an HTTP `Authorization` header.

        Args:
            headers: HTTP request headers mapping (case-insensitive via `http.client`).

        Returns:
            Raw token string if formatted as `Bearer <token>`, else None.
        """
        # Read Authorization header safely (handles both dict and Message headers).
        auth_header: Optional[str] = headers.get("Authorization") or headers.get("authorization")
        if not auth_header:
            return None

        # Split into scheme and token; require exact "Bearer" scheme.
        parts = auth_header.strip().split(" ", 1)
        if len(parts) != 2 or parts[0].lower() != "bearer":
            return None

        token: str = parts[1].strip()
        return token if token else None

    def verify_session(self, headers: Mapping[str, str]) -> Optional[str]:
        """
        Validates the bearer token in HTTP request headers (FR-06).

        Args:
            headers: HTTP request headers containing `Authorization: Bearer <token>`.

        Returns:
            Authenticated officer's username if valid and unexpired; otherwise None.
        """
        token: Optional[str] = self.extract_bearer_token(headers)
        if token is None:
            return None

        session: Optional[Dict[str, Any]] = self._sessions.get(token)
        if session is None:
            return None

        # Evict expired tokens immediately so stale credentials cannot be reused.
        if time.time() > session["expires_at"]:
            self._sessions.pop(token, None)
            return None

        return str(session["username"])