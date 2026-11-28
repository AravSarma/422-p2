"""
File: database/db_manager.py
Project: Emerald City Chess Hub (EC-ChessHub) — CS 422 Project 2
Author: Aaron Richards (Database Lead) with AI assistance
Created: 2026-11-27

Purpose:
    Provides the sole persistence layer (`DatabaseManager`) for EC-ChessHub.
    Encapsulates all SQLite (`sqlite3`) connections, schema initialization,
    CRUD operations for events, announcements, members, matches, and officers,
    and the atomic "Former Member" un-enrollment policy (FR-11 & FR-12).

Relationships to Other Files:
    - Reads and executes `database/schema.sql` during initialization.
    - Called by `backend/server.py` (HTTP/JSON routes), `backend/auth.py`
      (officer credential lookup), and `standings/elo_service.py` (rating
      retrieval and atomic match/rating commits).
    - Unit-tested by `tests/test_database.py`.
    - Enforces NFR-03: no other module imports or depends on `sqlite3`.

Dependencies:
    - Python 3.11+ Standard Library only (`contextlib`, `pathlib`, `sqlite3`, `typing`).
"""

from contextlib import contextmanager
from pathlib import Path
import sqlite3
from typing import Any, Dict, Iterator, List, Optional


# -----------------------------------------------------------------------------
# Domain-Specific Exception Hierarchy
# Purpose: Decouples callers (`backend/`, `standings/`) from sqlite3 exceptions
#          so that storage-engine internals never leak outside this module.
# -----------------------------------------------------------------------------

class DatabaseError(Exception):
    """Base exception for all persistence-layer errors in EC-ChessHub."""


class DuplicateEmailError(DatabaseError):
    """Raised when attempting to enroll a member with an existing email (FR-05)."""


class MemberNotFoundError(DatabaseError):
    """Raised when a requested member ID does not exist in the `members` table."""


class RecordNotFoundError(DatabaseError):
    """Raised when an event, announcement, or officer record is not found."""


# Module-level constant label used when anonymizing un-enrolled players (FR-12).
# Scope: module-level constant; Lifetime: duration of the Python process.
FORMER_MEMBER_LABEL: str = "Former Member"

# Valid skill tiers enforced by the database schema CHECK constraint.
# Scope: module-level constant; Lifetime: duration of the Python process.
VALID_SKILL_TIERS = ("Beginner", "Casual", "Tournament")

# Valid chess match outcomes enforced by the database schema CHECK constraint.
# Scope: module-level constant; Lifetime: duration of the Python process.
VALID_OUTCOMES = ("1-0", "0-1", "1/2-1/2")


class DatabaseManager:
    """
    Encapsulated SQLite persistence manager for Emerald City Chess Hub.

    Instance Attributes:
        db_path (Path):
            Purpose: Filesystem path to the local SQLite file (e.g., data/chess_hub.db).
            Scope: Instance attribute; Lifetime: lifetime of the DatabaseManager instance.
        schema_path (Path):
            Purpose: Filesystem path to schema.sql used to bootstrap tables.
            Scope: Instance attribute; Lifetime: lifetime of the DatabaseManager instance.
    """

    def __init__(
        self,
        db_path: str = "data/chess_hub.db",
        schema_path: Optional[str] = None,
    ) -> None:
        """
        Initializes the DatabaseManager and ensures the SQLite schema exists.

        Args:
            db_path: Path to the local SQLite database file. Parent directories
                     are created automatically if they do not exist.
            schema_path: Optional path to `schema.sql`. Defaults to `schema.sql`
                         located in the same directory as this module.
        """
        # Convert db_path string into a Path object for safe cross-platform handling.
        self.db_path: Path = Path(db_path)

        # Ensure the parent directory (e.g., data/) exists before opening SQLite.
        # If db_path is ':memory:', skip filesystem directory creation.
        if str(self.db_path) != ":memory:":
            self.db_path.parent.mkdir(parents=True, exist_ok=True)

        # Resolve schema.sql location: use caller-provided path or default beside this file.
        if schema_path is not None:
            self.schema_path: Path = Path(schema_path)
        else:
            self.schema_path = Path(__file__).resolve().parent / "schema.sql"

        # Bootstrap all tables and indexes immediately upon manager construction.
        self.initialize_schema()

    @contextmanager
    def _get_connection(self) -> Iterator[sqlite3.Connection]:
        """
        Context manager that opens, commits/rolls back, and explicitly closes
        a SQLite connection for a single unit of work.

        Note:
            Python's built-in `with sqlite3.connect(...) as conn:` only commits
            or rolls back transactions without closing the file handle, which
            causes file-lock errors on Windows and leaks descriptors over time.
            This context manager guarantees `conn.close()` runs in `finally`.

        Yields:
            sqlite3.Connection configured with `sqlite3.Row` dictionary-style
            row access and foreign key enforcement enabled.
        """
        # Open connection to the local SQLite database file.
        # Scope: local variable yielded to caller; Lifetime: closed in finally block.
        conn: sqlite3.Connection = sqlite3.connect(str(self.db_path))

        # Return rows as sqlite3.Row objects so columns can be converted to dicts by name.
        conn.row_factory = sqlite3.Row

        # Enforce FOREIGN KEY constraints (required for ON DELETE SET NULL integrity).
        conn.execute("PRAGMA foreign_keys = ON;")
        try:
            # Hand the open connection to the calling `with` block.
            yield conn
            # Commit all statements executed inside the `with` block atomically.
            conn.commit()
        except Exception:
            # Roll back partial changes if any statement or Python error occurred.
            conn.rollback()
            raise
        finally:
            # Always close the connection so OS file handles are released immediately.
            conn.close()

    def initialize_schema(self) -> None:
        """
        Reads `schema.sql` and executes it idempotently (`CREATE TABLE IF NOT EXISTS`).

        Raises:
            DatabaseError: If `schema.sql` cannot be read or SQL execution fails.
        """
        try:
            # Read the complete SQL DDL script into memory.
            # Scope: local variable; Lifetime: duration of initialize_schema().
            schema_sql: str = self.schema_path.read_text(encoding="utf-8")

            # Open a connection and execute the full schema script atomically.
            with self._get_connection() as conn:
                conn.executescript(schema_sql)
        except (OSError, sqlite3.Error) as exc:
            # Wrap OS or SQLite errors in DatabaseError to preserve encapsulation.
            raise DatabaseError(f"Failed to initialize database schema: {exc}") from exc

    # =========================================================================
    # MEMBER OPERATIONS (FR-04, FR-05, FR-10, FR-11, FR-12)
    # =========================================================================

    def create_member(
        self,
        name: str,
        email: str,
        skill_tier: str,
        initial_rating: int = 1200,
    ) -> Dict[str, Any]:
        """
        Enrolls a new club member with a baseline Elo rating (FR-04).

        Args:
            name: Member's full name (non-empty string).
            email: Member's unique UO email address (normalized to lowercase).
            skill_tier: One of 'Beginner', 'Casual', or 'Tournament'.
            initial_rating: Starting Elo rating (defaults to 1200).

        Returns:
            Dict representing the newly created member row.

        Raises:
            DuplicateEmailError: If `email` is already registered (FR-05).
            DatabaseError: If `skill_tier` is invalid or SQLite fails.
        """
        # Normalize inputs to prevent whitespace or case-sensitive duplicates.
        # Scope: local variables; Lifetime: duration of create_member().
        clean_name: str = name.strip()
        clean_email: str = email.strip().lower()

        # Validate skill_tier against allowed domain values before hitting SQLite.
        if skill_tier not in VALID_SKILL_TIERS:
            raise DatabaseError(
                f"Invalid skill_tier '{skill_tier}'. Must be one of {VALID_SKILL_TIERS}."
            )

        try:
            with self._get_connection() as conn:
                # Insert the new member record using parameterized SQL (prevents SQL injection).
                cursor: sqlite3.Cursor = conn.execute(
                    """
                    INSERT INTO members (name, email, skill_tier, current_rating)
                    VALUES (?, ?, ?, ?);
                    """,
                    (clean_name, clean_email, skill_tier, int(initial_rating)),
                )
                # Retrieve the auto-generated primary key of the inserted member.
                new_id: int = int(cursor.lastrowid)

                # Fetch and return the complete persisted row (including created_at).
                row: Optional[sqlite3.Row] = conn.execute(
                    "SELECT * FROM members WHERE id = ?;",
                    (new_id,),
                ).fetchone()
                return dict(row) if row is not None else {}
        except sqlite3.IntegrityError as exc:
            # SQLite raises IntegrityError on UNIQUE constraint violations (email).
            if "UNIQUE constraint failed: members.email" in str(exc):
                raise DuplicateEmailError(
                    f"Email '{clean_email}' is already registered."
                ) from exc
            raise DatabaseError(f"Integrity error creating member: {exc}") from exc
        except sqlite3.Error as exc:
            raise DatabaseError(f"Failed to create member: {exc}") from exc

    def get_member_by_id(self, member_id: int) -> Optional[Dict[str, Any]]:
        """
        Retrieves a single active member record by its primary key.

        Args:
            member_id: Integer primary key of the member.

        Returns:
            Dict of member fields, or None if no active member has that ID.
        """
        try:
            with self._get_connection() as conn:
                row: Optional[sqlite3.Row] = conn.execute(
                    "SELECT * FROM members WHERE id = ?;",
                    (member_id,),
                ).fetchone()
                # Convert sqlite3.Row to a plain Python dict so callers stay decoupled.
                return dict(row) if row is not None else None
        except sqlite3.Error as exc:
            raise DatabaseError(f"Failed to fetch member {member_id}: {exc}") from exc

    def get_member_by_email(self, email: str) -> Optional[Dict[str, Any]]:
        """
        Retrieves a single active member record by email (case-insensitive).

        Args:
            email: Email address to look up.

        Returns:
            Dict of member fields, or None if not found.
        """
        clean_email: str = email.strip().lower()
        try:
            with self._get_connection() as conn:
                row: Optional[sqlite3.Row] = conn.execute(
                    "SELECT * FROM members WHERE email = ?;",
                    (clean_email,),
                ).fetchone()
                return dict(row) if row is not None else None
        except sqlite3.Error as exc:
            raise DatabaseError(f"Failed to fetch member by email: {exc}") from exc

    def get_active_members_sorted(self) -> List[Dict[str, Any]]:
        """
        Returns all active members sorted by Elo rating descending (FR-10).

        Called by `standings/elo_service.py` to compute dynamic leaderboard
        rankings on demand without storing static rank columns.

        Returns:
            List of member dicts ordered by `current_rating DESC, name ASC`.
        """
        try:
            with self._get_connection() as conn:
                rows: List[sqlite3.Row] = conn.execute(
                    """
                    SELECT id, name, email, skill_tier, current_rating, created_at
                    FROM members
                    ORDER BY current_rating DESC, name ASC;
                    """
                ).fetchall()
                # Convert each sqlite3.Row into a standard Python dict in a loop.
                return [dict(row) for row in rows]
        except sqlite3.Error as exc:
            raise DatabaseError(f"Failed to fetch sorted members: {exc}") from exc

    def unenroll_member(self, member_id: int) -> bool:
        """
        Un-enrolls a member while preserving opponents' match histories (FR-11 & FR-12).

        Atomic Transaction Behavior:
            1. Verifies the member exists (raises MemberNotFoundError if not).
            2. Updates all `matches` rows where the member played White:
               sets `white_label = 'Former Member'` and `white_member_id = NULL`.
            3. Updates all `matches` rows where the member played Black:
               sets `black_label = 'Former Member'` and `black_member_id = NULL`.
            4. Permanently deletes the member row from `members` (purging name,
               email, and current rating).

        Args:
            member_id: Integer primary key of the member to un-enroll.

        Returns:
            True if the member was successfully un-enrolled.

        Raises:
            MemberNotFoundError: If no member with `member_id` exists.
            DatabaseError: If the SQLite transaction fails (automatically rolled back).
        """
        try:
            with self._get_connection() as conn:
                # Step 1: Confirm the target member exists before modifying any rows.
                existing: Optional[sqlite3.Row] = conn.execute(
                    "SELECT id FROM members WHERE id = ?;",
                    (member_id,),
                ).fetchone()
                if existing is None:
                    raise MemberNotFoundError(
                        f"Cannot un-enroll: member ID {member_id} does not exist."
                    )

                # Step 2: Anonymize all matches where this member played White.
                conn.execute(
                    """
                    UPDATE matches
                    SET white_label = ?, white_member_id = NULL
                    WHERE white_member_id = ?;
                    """,
                    (FORMER_MEMBER_LABEL, member_id),
                )

                # Step 3: Anonymize all matches where this member played Black.
                conn.execute(
                    """
                    UPDATE matches
                    SET black_label = ?, black_member_id = NULL
                    WHERE black_member_id = ?;
                    """,
                    (FORMER_MEMBER_LABEL, member_id),
                )

                # Step 4: Permanently purge the member's name, email, and rating (FR-11).
                conn.execute(
                    "DELETE FROM members WHERE id = ?;",
                    (member_id,),
                )
                return True
        except MemberNotFoundError:
            # Re-raise domain error directly without wrapping.
            raise
        except sqlite3.Error as exc:
            raise DatabaseError(f"Failed to un-enroll member {member_id}: {exc}") from exc

    # =========================================================================
    # MATCH & RATING OPERATIONS (FR-08, FR-09)
    # =========================================================================

    def record_match_and_ratings(
        self,
        white_id: int,
        black_id: int,
        outcome: str,
        new_white_rating: int,
        new_black_rating: int,
    ) -> Dict[str, Any]:
        """
        Atomically logs a completed chess match and updates both players' Elo ratings.

        Called by `standings/elo_service.py` after computing the new Elo ratings.

        Args:
            white_id: Member ID of the player playing White.
            black_id: Member ID of the player playing Black.
            outcome: Match result ('1-0', '0-1', or '1/2-1/2').
            new_white_rating: Post-match Elo rating for White.
            new_black_rating: Post-match Elo rating for Black.

        Returns:
            Dict representing the newly inserted match row.

        Raises:
            MemberNotFoundError: If either player ID does not exist.
            DatabaseError: If players are identical, outcome is invalid, or SQLite fails.
        """
        # Guard against a member playing against themselves.
        if white_id == black_id:
            raise DatabaseError("White and Black players must be different members.")

        # Validate outcome against standard chess result strings.
        if outcome not in VALID_OUTCOMES:
            raise DatabaseError(
                f"Invalid outcome '{outcome}'. Must be one of {VALID_OUTCOMES}."
            )

        try:
            with self._get_connection() as conn:
                # Look up both players to verify existence and snapshot their names.
                white_row: Optional[sqlite3.Row] = conn.execute(
                    "SELECT id, name FROM members WHERE id = ?;",
                    (white_id,),
                ).fetchone()
                if white_row is None:
                    raise MemberNotFoundError(f"White player ID {white_id} not found.")

                black_row: Optional[sqlite3.Row] = conn.execute(
                    "SELECT id, name FROM members WHERE id = ?;",
                    (black_id,),
                ).fetchone()
                if black_row is None:
                    raise MemberNotFoundError(f"Black player ID {black_id} not found.")

                # Insert the match row with snapshotted player names as labels.
                cursor: sqlite3.Cursor = conn.execute(
                    """
                    INSERT INTO matches (
                        white_member_id, black_member_id,
                        white_label, black_label, outcome
                    )
                    VALUES (?, ?, ?, ?, ?);
                    """,
                    (white_id, black_id, white_row["name"], black_row["name"], outcome),
                )
                match_id: int = int(cursor.lastrowid)

                # Update White player's stored Elo rating in the same transaction.
                conn.execute(
                    "UPDATE members SET current_rating = ? WHERE id = ?;",
                    (int(new_white_rating), white_id),
                )

                # Update Black player's stored Elo rating in the same transaction.
                conn.execute(
                    "UPDATE members SET current_rating = ? WHERE id = ?;",
                    (int(new_black_rating), black_id),
                )

                # Fetch and return the persisted match record.
                saved_match: Optional[sqlite3.Row] = conn.execute(
                    "SELECT * FROM matches WHERE id = ?;",
                    (match_id,),
                ).fetchone()
                return dict(saved_match) if saved_match is not None else {}
        except MemberNotFoundError:
            raise
        except sqlite3.Error as exc:
            raise DatabaseError(f"Failed to record match and ratings: {exc}") from exc

    def get_all_matches(self) -> List[Dict[str, Any]]:
        """
        Returns all recorded matches ordered newest-to-oldest.

        Returns:
            List of match dicts (including 'Former Member' labels where applicable).
        """
        try:
            with self._get_connection() as conn:
                rows: List[sqlite3.Row] = conn.execute(
                    "SELECT * FROM matches ORDER BY played_at DESC, id DESC;"
                ).fetchall()
                return [dict(row) for row in rows]
        except sqlite3.Error as exc:
            raise DatabaseError(f"Failed to fetch matches: {exc}") from exc

    def get_matches_for_member(self, member_id: int) -> List[Dict[str, Any]]:
        """
        Returns all recorded matches in which `member_id` played White or Black.

        Args:
            member_id: Active member primary key.

        Returns:
            List of match dicts ordered newest-to-oldest.
        """
        try:
            with self._get_connection() as conn:
                rows: List[sqlite3.Row] = conn.execute(
                    """
                    SELECT * FROM matches
                    WHERE white_member_id = ? OR black_member_id = ?
                    ORDER BY played_at DESC, id DESC;
                    """,
                    (member_id, member_id),
                ).fetchall()
                return [dict(row) for row in rows]
        except sqlite3.Error as exc:
            raise DatabaseError(
                f"Failed to fetch matches for member {member_id}: {exc}"
            ) from exc

    # =========================================================================
    # EVENT OPERATIONS (FR-01, FR-07)
    # =========================================================================

    def create_event(
        self,
        title: str,
        date_time: str,
        location: str,
        description: str = "",
    ) -> Dict[str, Any]:
        """
        Creates a new club meeting, workshop, or tournament event.

        Args:
            title: Event headline.
            date_time: ISO-8601 date/time string.
            location: Campus room or building location.
            description: Optional agenda or workshop details.

        Returns:
            Dict representing the created event row.
        """
        try:
            with self._get_connection() as conn:
                cursor: sqlite3.Cursor = conn.execute(
                    """
                    INSERT INTO events (title, date_time, location, description)
                    VALUES (?, ?, ?, ?);
                    """,
                    (title.strip(), date_time.strip(), location.strip(), description.strip()),
                )
                event_id: int = int(cursor.lastrowid)
                row: Optional[sqlite3.Row] = conn.execute(
                    "SELECT * FROM events WHERE id = ?;",
                    (event_id,),
                ).fetchone()
                return dict(row) if row is not None else {}
        except sqlite3.Error as exc:
            raise DatabaseError(f"Failed to create event: {exc}") from exc

    def get_all_events(self) -> List[Dict[str, Any]]:
        """
        Returns all scheduled club events ordered chronologically by `date_time ASC`.
        """
        try:
            with self._get_connection() as conn:
                rows: List[sqlite3.Row] = conn.execute(
                    "SELECT * FROM events ORDER BY date_time ASC, id ASC;"
                ).fetchall()
                return [dict(row) for row in rows]
        except sqlite3.Error as exc:
            raise DatabaseError(f"Failed to fetch events: {exc}") from exc

    def update_event(
        self,
        event_id: int,
        title: str,
        date_time: str,
        location: str,
        description: str = "",
    ) -> Dict[str, Any]:
        """
        Updates an existing event's details by ID (FR-07).

        Raises:
            RecordNotFoundError: If `event_id` does not exist.
        """
        try:
            with self._get_connection() as conn:
                cursor: sqlite3.Cursor = conn.execute(
                    """
                    UPDATE events
                    SET title = ?, date_time = ?, location = ?, description = ?
                    WHERE id = ?;
                    """,
                    (
                        title.strip(),
                        date_time.strip(),
                        location.strip(),
                        description.strip(),
                        event_id,
                    ),
                )
                # Check rowcount to verify that a matching event was actually updated.
                if cursor.rowcount == 0:
                    raise RecordNotFoundError(f"Event ID {event_id} not found.")

                row: Optional[sqlite3.Row] = conn.execute(
                    "SELECT * FROM events WHERE id = ?;",
                    (event_id,),
                ).fetchone()
                return dict(row) if row is not None else {}
        except RecordNotFoundError:
            raise
        except sqlite3.Error as exc:
            raise DatabaseError(f"Failed to update event {event_id}: {exc}") from exc

    def delete_event(self, event_id: int) -> bool:
        """
        Deletes an event by ID (FR-07).

        Returns:
            True if deleted.

        Raises:
            RecordNotFoundError: If `event_id` does not exist.
        """
        try:
            with self._get_connection() as conn:
                cursor: sqlite3.Cursor = conn.execute(
                    "DELETE FROM events WHERE id = ?;",
                    (event_id,),
                )
                if cursor.rowcount == 0:
                    raise RecordNotFoundError(f"Event ID {event_id} not found.")
                return True
        except RecordNotFoundError:
            raise
        except sqlite3.Error as exc:
            raise DatabaseError(f"Failed to delete event {event_id}: {exc}") from exc

    # =========================================================================
    # ANNOUNCEMENT OPERATIONS (FR-03, FR-07)
    # =========================================================================

    def create_announcement(self, title: str, body: str) -> Dict[str, Any]:
        """
        Creates a new club announcement displayed on the public landing page.

        Args:
            title: Short announcement headline.
            body: Full announcement text.

        Returns:
            Dict representing the created announcement row.
        """
        try:
            with self._get_connection() as conn:
                cursor: sqlite3.Cursor = conn.execute(
                    "INSERT INTO announcements (title, body) VALUES (?, ?);",
                    (title.strip(), body.strip()),
                )
                ann_id: int = int(cursor.lastrowid)
                row: Optional[sqlite3.Row] = conn.execute(
                    "SELECT * FROM announcements WHERE id = ?;",
                    (ann_id,),
                ).fetchone()
                return dict(row) if row is not None else {}
        except sqlite3.Error as exc:
            raise DatabaseError(f"Failed to create announcement: {exc}") from exc

    def get_all_announcements(self) -> List[Dict[str, Any]]:
        """
        Returns all announcements ordered newest-to-oldest (FR-03).
        """
        try:
            with self._get_connection() as conn:
                rows: List[sqlite3.Row] = conn.execute(
                    "SELECT * FROM announcements ORDER BY created_at DESC, id DESC;"
                ).fetchall()
                return [dict(row) for row in rows]
        except sqlite3.Error as exc:
            raise DatabaseError(f"Failed to fetch announcements: {exc}") from exc

    def update_announcement(
        self,
        announcement_id: int,
        title: str,
        body: str,
    ) -> Dict[str, Any]:
        """
        Updates an existing announcement by ID (FR-07).

        Raises:
            RecordNotFoundError: If `announcement_id` does not exist.
        """
        try:
            with self._get_connection() as conn:
                cursor: sqlite3.Cursor = conn.execute(
                    "UPDATE announcements SET title = ?, body = ? WHERE id = ?;",
                    (title.strip(), body.strip(), announcement_id),
                )
                if cursor.rowcount == 0:
                    raise RecordNotFoundError(
                        f"Announcement ID {announcement_id} not found."
                    )

                row: Optional[sqlite3.Row] = conn.execute(
                    "SELECT * FROM announcements WHERE id = ?;",
                    (announcement_id,),
                ).fetchone()
                return dict(row) if row is not None else {}
        except RecordNotFoundError:
            raise
        except sqlite3.Error as exc:
            raise DatabaseError(
                f"Failed to update announcement {announcement_id}: {exc}"
            ) from exc

    def delete_announcement(self, announcement_id: int) -> bool:
        """
        Deletes an announcement by ID (FR-07).

        Raises:
            RecordNotFoundError: If `announcement_id` does not exist.
        """
        try:
            with self._get_connection() as conn:
                cursor: sqlite3.Cursor = conn.execute(
                    "DELETE FROM announcements WHERE id = ?;",
                    (announcement_id,),
                )
                if cursor.rowcount == 0:
                    raise RecordNotFoundError(
                        f"Announcement ID {announcement_id} not found."
                    )
                return True
        except RecordNotFoundError:
            raise
        except sqlite3.Error as exc:
            raise DatabaseError(
                f"Failed to delete announcement {announcement_id}: {exc}"
            ) from exc

    # =========================================================================
    # OFFICER OPERATIONS (FR-06)
    # =========================================================================

    def create_officer(self, username: str, password_hash: str) -> Dict[str, Any]:
        """
        Creates an authenticated club officer account with a pre-hashed password.

        Args:
            username: Unique login username (normalized to lowercase).
            password_hash: Salted hash generated by `backend/auth.py`.

        Returns:
            Dict containing the officer's id and username (excludes password_hash).
        """
        clean_username: str = username.strip().lower()
        try:
            with self._get_connection() as conn:
                cursor: sqlite3.Cursor = conn.execute(
                    "INSERT INTO officers (username, password_hash) VALUES (?, ?);",
                    (clean_username, password_hash),
                )
                officer_id: int = int(cursor.lastrowid)
                return {"id": officer_id, "username": clean_username}
        except sqlite3.IntegrityError as exc:
            raise DatabaseError(
                f"Officer username '{clean_username}' already exists."
            ) from exc
        except sqlite3.Error as exc:
            raise DatabaseError(f"Failed to create officer: {exc}") from exc

    def get_officer_by_username(self, username: str) -> Optional[Dict[str, Any]]:
        """
        Retrieves an officer record (including `password_hash`) for login verification.

        Called exclusively by `backend/auth.py`.

        Args:
            username: Officer username to look up.

        Returns:
            Dict with id, username, and password_hash, or None if not found.
        """
        clean_username: str = username.strip().lower()
        try:
            with self._get_connection() as conn:
                row: Optional[sqlite3.Row] = conn.execute(
                    "SELECT id, username, password_hash FROM officers WHERE username = ?;",
                    (clean_username,),
                ).fetchone()
                return dict(row) if row is not None else None
        except sqlite3.Error as exc:
            raise DatabaseError(f"Failed to fetch officer '{clean_username}': {exc}") from exc