"""
File: backend/__init__.py
Project: Emerald City Chess Hub (EC-ChessHub) — CS 422 Project 2
Author: Arav Sarma (Backend & API Lead)
Created: 2026-11-27

Purpose:
    Exposes the public interface of the `backend` package (authentication,
    payload validation, and HTTP server factory) for `tests/test_api.py`
    and the Docker container entry point (`python -m backend.server`).

Strict Boundary (NFR-03):
    This package handles HTTP routing, input validation, and officer
    authentication only. It never imports `sqlite3` directly; all persistence
    is delegated to `database.DatabaseManager`.

Dependencies:
    - Python 3.11+ Standard Library only.
"""

from backend.auth import AuthManager, hash_password, verify_password
from backend.server import ChessHubRequestHandler, create_server
from backend.validator import PayloadValidator, ValidationError

# Public exports of the backend package.
# Scope: module-level constant; Lifetime: duration of the Python process.
__all__ = [
    "AuthManager",
    "hash_password",
    "verify_password",
    "PayloadValidator",
    "ValidationError",
    "ChessHubRequestHandler",
    "create_server",
]