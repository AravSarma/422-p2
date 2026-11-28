"""
File: database/__init__.py
Project: Emerald City Chess Hub (EC-ChessHub) — CS 422 Project 2
Author: Aaron Richards (Database Lead)
Created: 2026-11-27

Purpose:
    Exposes the public interface of the `database` package so that other
    modules (`backend/` and `standings/`) can import DatabaseManager and
    domain-specific database exceptions without touching sqlite3 directly
    (enforcing NFR-03: Database Encapsulation).

Relationships to Other Files:
    - Imports symbols from `database/db_manager.py`.
    - Imported by `backend/server.py`, `backend/auth.py`,
      `standings/elo_service.py`, and `tests/test_database.py`.

Dependencies:
    - Python 3.11+ Standard Library only (no third-party packages).
"""

# Re-export the DatabaseManager class and custom exception hierarchy
# so external callers have a single clean import path:
#   from database import DatabaseManager, DuplicateEmailError, MemberNotFoundError
from database.db_manager import (
    DatabaseError,
    DatabaseManager,
    DuplicateEmailError,
    MemberNotFoundError,
    RecordNotFoundError,
)

# __all__ explicitly defines the public API surface of the database package.
# Scope: module-level constant; Lifetime: duration of the Python process.
__all__ = [
    "DatabaseManager",
    "DatabaseError",
    "DuplicateEmailError",
    "MemberNotFoundError",
    "RecordNotFoundError",
]