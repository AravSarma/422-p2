"""
File: tests/test_database.py
Project: Emerald City Chess Hub (EC-ChessHub) — CS 422 Project 2
Author: Aaron Richards (Database Lead)
Created: 2026-11-27

Purpose:
    Unit test suite for the `database` module (`database/db_manager.py` and
    `database/schema.sql`). Verifies member enrollment, duplicate email
    rejection (FR-05), dynamic rating sorting (FR-10), atomic match/rating
    recording (FR-08, FR-09), "Former Member" un-enrollment history retention
    (FR-11, FR-12), and event/announcement/officer CRUD operations.

How to Run:
    From the project root (`422-p2/`):
        python3 -m unittest tests/test_database.py -v

Dependencies:
    - Python 3.11+ Standard Library only (`unittest`, `tempfile`, `pathlib`).
"""

from pathlib import Path
import tempfile
import unittest

from database import (
    DatabaseError,
    DatabaseManager,
    DuplicateEmailError,
    MemberNotFoundError,
    RecordNotFoundError,
)


class TestDatabaseManager(unittest.TestCase):
    """
    Isolated unit tests for DatabaseManager.

    Each test case receives a fresh temporary SQLite file created in `setUp()`
    and automatically cleaned up in `tearDown()` so tests never interfere with
    one another or with the production `data/chess_hub.db` file.
    """

    def setUp(self) -> None:
        """
        Creates a temporary directory and initializes a fresh DatabaseManager.

        Instance Attributes Created:
            self._tmp_dir (TemporaryDirectory): Scope: test instance; Lifetime: single test.
            self.db_path (Path): Path to the isolated temporary SQLite file.
            self.db (DatabaseManager): Fresh database manager under test.
        """
        self._tmp_dir = tempfile.TemporaryDirectory()
        self.db_path: Path = Path(self._tmp_dir.name) / "test_chess_hub.db"
        self.db = DatabaseManager(db_path=str(self.db_path))

    def tearDown(self) -> None:
        """Deletes the temporary directory and SQLite database after each test."""
        self._tmp_dir.cleanup()

    # -------------------------------------------------------------------------
    # Member & Duplicate Email Tests (FR-04, FR-05, FR-10)
    # -------------------------------------------------------------------------

    def test_create_and_fetch_member(self) -> None:
        """Verifies member enrollment stores normalized email and baseline rating."""
        created = self.db.create_member(
            name="  Emma Chen  ",
            email="Emma@UOregon.edu",
            skill_tier="Casual",
        )
        # Verify trimmed name, lowercased email, and default 1200 Elo rating.
        self.assertEqual(created["name"], "Emma Chen")
        self.assertEqual(created["email"], "emma@uoregon.edu")
        self.assertEqual(created["skill_tier"], "Casual")
        self.assertEqual(created["current_rating"], 1200)

        # Verify lookup by ID and by case-insensitive email.
        fetched_by_id = self.db.get_member_by_id(created["id"])
        fetched_by_email = self.db.get_member_by_email("EMMA@uoregon.edu")
        self.assertEqual(fetched_by_id, created)
        self.assertEqual(fetched_by_email, created)

    def test_duplicate_email_raises_error(self) -> None:
        """Verifies FR-05: duplicate emails are rejected with DuplicateEmailError."""
        self.db.create_member("Emma", "emma@uoregon.edu", "Beginner")
        with self.assertRaises(DuplicateEmailError):
            self.db.create_member("Emma Duplicate", "EMMA@UOREGON.EDU", "Casual")

    def test_invalid_skill_tier_raises_error(self) -> None:
        """Verifies invalid skill tiers are rejected before database insertion."""
        with self.assertRaises(DatabaseError):
            self.db.create_member("Alex", "alex@uoregon.edu", "Grandmaster")

    def test_active_members_sorted_by_rating_desc(self) -> None:
        """Verifies FR-10: active members are returned sorted by rating descending."""
        self.db.create_member("Beginner Player", "b@uoregon.edu", "Beginner", 1100)
        self.db.create_member("Top Player", "t@uoregon.edu", "Tournament", 1550)
        self.db.create_member("Mid Player", "m@uoregon.edu", "Casual", 1300)

        sorted_members = self.db.get_active_members_sorted()
        ratings = [m["current_rating"] for m in sorted_members]
        self.assertEqual(ratings, [1550, 1300, 1100])

    # -------------------------------------------------------------------------
    # Match Recording & "Former Member" Un-Enrollment Tests (FR-08, FR-11, FR-12)
    # -------------------------------------------------------------------------

    def test_record_match_updates_ratings_atomically(self) -> None:
        """Verifies FR-08 & FR-09: recording a match stores labels and updates ratings."""
        emma = self.db.create_member("Emma", "emma@uoregon.edu", "Casual", 1200)
        addison = self.db.create_member("Addison", "addison@uoregon.edu", "Tournament", 1200)

        match = self.db.record_match_and_ratings(
            white_id=emma["id"],
            black_id=addison["id"],
            outcome="1-0",
            new_white_rating=1216,
            new_black_rating=1184,
        )

        # Verify match row stored player names and outcome accurately.
        self.assertEqual(match["white_label"], "Emma")
        self.assertEqual(match["black_label"], "Addison")
        self.assertEqual(match["outcome"], "1-0")

        # Verify both players' ratings updated in the members table.
        self.assertEqual(self.db.get_member_by_id(emma["id"])["current_rating"], 1216)
        self.assertEqual(self.db.get_member_by_id(addison["id"])["current_rating"], 1184)

    def test_unenroll_member_purges_pii_and_preserves_history(self) -> None:
        """
        Verifies FR-11 & FR-12:
        - Un-enrolling a member deletes their name, email, and rating from `members`.
        - Historical matches replace their name with 'Former Member' and NULL FK.
        - The opponent's match history remains intact and queryable.
        """
        emma = self.db.create_member("Emma", "emma@uoregon.edu", "Casual", 1200)
        addison = self.db.create_member("Addison", "addison@uoregon.edu", "Tournament", 1200)

        # Record two matches: Emma as White in Game 1, Emma as Black in Game 2.
        self.db.record_match_and_ratings(emma["id"], addison["id"], "1-0", 1216, 1184)
        self.db.record_match_and_ratings(addison["id"], emma["id"], "1/2-1/2", 1185, 1215)

        # Un-enroll Emma.
        result = self.db.unenroll_member(emma["id"])
        self.assertTrue(result)

        # Verify Emma's PII and rating are completely deleted from `members`.
        self.assertIsNone(self.db.get_member_by_id(emma["id"]))
        self.assertIsNone(self.db.get_member_by_email("emma@uoregon.edu"))

        # Verify Addison's match history still contains both games with 'Former Member'.
        addison_matches = self.db.get_matches_for_member(addison["id"])
        self.assertEqual(len(addison_matches), 2)

        # Inspect both games to confirm Emma was replaced by 'Former Member' in both roles.
        labels_seen = {(m["white_label"], m["black_label"]) for m in addison_matches}
        self.assertIn(("Former Member", "Addison"), labels_seen)
        self.assertIn(("Addison", "Former Member"), labels_seen)

        # Confirm the foreign keys for Emma were set to NULL.
        for match in addison_matches:
            if match["white_label"] == "Former Member":
                self.assertIsNone(match["white_member_id"])
            if match["black_label"] == "Former Member":
                self.assertIsNone(match["black_member_id"])

    def test_unenroll_nonexistent_member_raises_error(self) -> None:
        """Verifies un-enrolling an unknown member ID raises MemberNotFoundError."""
        with self.assertRaises(MemberNotFoundError):
            self.db.unenroll_member(9999)

    # -------------------------------------------------------------------------
    # Event, Announcement, & Officer CRUD Tests (FR-01, FR-03, FR-06, FR-07)
    # -------------------------------------------------------------------------

    def test_event_crud_lifecycle(self) -> None:
        """Verifies creating, listing, updating, and deleting club events."""
        ev = self.db.create_event(
            title="Beginners Night",
            date_time="2026-11-19T18:00:00",
            location="Straub 145",
            description="Pawn endgames and basic checkmates.",
        )
        self.assertEqual(len(self.db.get_all_events()), 1)

        updated = self.db.update_event(
            event_id=ev["id"],
            title="Beginners Night (Room Change)",
            date_time="2026-11-19T18:00:00",
            location="EMU 119",
            description="Updated room location.",
        )
        self.assertEqual(updated["location"], "EMU 119")

        self.assertTrue(self.db.delete_event(ev["id"]))
        self.assertEqual(len(self.db.get_all_events()), 0)

        with self.assertRaises(RecordNotFoundError):
            self.db.delete_event(ev["id"])

    def test_announcement_crud_lifecycle(self) -> None:
        """Verifies creating, ordering newest-first, updating, and deleting announcements."""
        first = self.db.create_announcement("Welcome", "First meeting this Thursday!")
        second = self.db.create_announcement("Room Update", "Moved to EMU 119.")

        all_ann = self.db.get_all_announcements()
        # Most recently inserted announcement must appear first (FR-03).
        self.assertEqual(all_ann[0]["id"], second["id"])
        self.assertEqual(all_ann[1]["id"], first["id"])

        updated = self.db.update_announcement(first["id"], "Welcome Back", "Updated body.")
        self.assertEqual(updated["title"], "Welcome Back")

        self.assertTrue(self.db.delete_announcement(first["id"]))
        self.assertEqual(len(self.db.get_all_announcements()), 1)

    def test_officer_creation_and_lookup(self) -> None:
        """Verifies officer accounts store password hashes and enforce unique usernames."""
        officer = self.db.create_officer("Addison", "pbkdf2:sha256:fakehashvalue")
        self.assertEqual(officer["username"], "addison")
        self.assertNotIn("password_hash", officer)

        fetched = self.db.get_officer_by_username("ADDISON")
        self.assertIsNotNone(fetched)
        self.assertEqual(fetched["password_hash"], "pbkdf2:sha256:fakehashvalue")

        with self.assertRaises(DatabaseError):
            self.db.create_officer("addison", "anotherhash")


if __name__ == "__main__":
    unittest.main()