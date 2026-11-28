"""
File: tests/test_api.py
Project: Emerald City Chess Hub (EC-ChessHub) — CS 422 Project 2
Author: Arav Sarma (Backend & API Lead)
Created: 2026-11-27

Purpose:
    End-to-end HTTP/JSON integration test suite for `backend/server.py`,
    `backend/auth.py`, and `backend/validator.py`. Spins up a real local
    `ChessHubServer` on an ephemeral port backed by a temporary SQLite
    database and issues real HTTP requests via `urllib.request`.

How to Run:
    From the project root (`422-p2/`):
        python -m unittest tests/test_api.py -v

Dependencies:
    - Python 3.11+ Standard Library only (`json`, `os`, `pathlib`, `tempfile`,
      `threading`, `unittest`, `urllib.error`, `urllib.request`).
"""

import json
import os
from pathlib import Path
import tempfile
import threading
from typing import Any, Dict, Optional, Tuple
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from backend.server import create_server


class TestBackendAPI(unittest.TestCase):
    """
    Integration tests verifying all public and officer-authenticated REST endpoints.
    """

    def setUp(self) -> None:
        """Starts an isolated ChessHubServer on localhost port 0 (OS-assigned)."""
        # Silence per-request HTTP stderr logging during unit test output.
        os.environ["QUIET_HTTP_LOGS"] = "1"

        self._tmp_dir = tempfile.TemporaryDirectory()
        self.db_path: Path = Path(self._tmp_dir.name) / "api_test.db"

        # Bind to port 0 so the OS selects an available ephemeral port.
        self.server = create_server(
            host="127.0.0.1",
            port=0,
            db_path=str(self.db_path),
            default_officer_user="addison",
            default_officer_pass="secret123",
        )
        port: int = self.server.server_address[1]
        self.base_url: str = f"http://127.0.0.1:{port}"

        # Run the HTTP server in a daemon thread for the duration of this test.
        self._thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self._thread.start()

    def tearDown(self) -> None:
        """Stops the HTTP server and cleans up the temporary SQLite directory."""
        self.server.shutdown()
        self.server.server_close()
        self._thread.join(timeout=2)
        self._tmp_dir.cleanup()

    def _request(
        self,
        method: str,
        path: str,
        body: Optional[Dict[str, Any]] = None,
        token: Optional[str] = None,
    ) -> Tuple[int, Any]:
        """
        Helper that sends an HTTP/JSON request and returns `(status_code, parsed_json)`.
        """
        headers: Dict[str, str] = {"Content-Type": "application/json"}
        if token is not None:
            headers["Authorization"] = f"Bearer {token}"

        data: Optional[bytes] = (
            json.dumps(body).encode("utf-8") if body is not None else None
        )
        req = Request(f"{self.base_url}{path}", data=data, headers=headers, method=method)
        try:
            with urlopen(req) as resp:
                return resp.status, json.loads(resp.read().decode("utf-8"))
        except HTTPError as err:
            return err.code, json.loads(err.read().decode("utf-8"))

    def _login_officer(self) -> str:
        """Authenticates the seeded officer account and returns its bearer token."""
        status, data = self._request(
            "POST",
            "/api/auth/login",
            {"username": "addison", "password": "secret123"},
        )
        self.assertEqual(status, 200)
        return str(data["token"])

    # -------------------------------------------------------------------------
    # Health & Authentication Tests (FR-06)
    # -------------------------------------------------------------------------

    def test_health_endpoint(self) -> None:
        """Verifies GET /api/health returns 200 ok."""
        status, data = self._request("GET", "/api/health")
        self.assertEqual(status, 200)
        self.assertEqual(data["status"], "ok")

    def test_officer_login_and_auth_guard(self) -> None:
        """Verifies FR-06: protected routes reject unauthenticated callers with 401."""
        # Unauthenticated request to create an event must return HTTP 401.
        status, _ = self._request(
            "POST",
            "/api/events",
            {"title": "Test", "date_time": "2026-11-20T18:00:00", "location": "EMU"},
        )
        self.assertEqual(status, 401)

        # Bad password must return HTTP 401.
        status, _ = self._request(
            "POST",
            "/api/auth/login",
            {"username": "addison", "password": "wrongpassword"},
        )
        self.assertEqual(status, 401)

        # Valid login returns bearer token that passes session check.
        token = self._login_officer()
        status, session = self._request("GET", "/api/auth/session", token=token)
        self.assertEqual(status, 200)
        self.assertEqual(session["username"], "addison")

    # -------------------------------------------------------------------------
    # Public Registration & Validation Tests (FR-04, FR-05)
    # -------------------------------------------------------------------------

    def test_public_registration_and_validation(self) -> None:
        """Verifies public member signup, UO email enforcement, and 409 duplicate check."""
        # Non-UO email must be rejected with HTTP 400.
        status, _ = self._request(
            "POST",
            "/api/members",
            {"name": "Emma", "email": "emma@gmail.com", "skill_tier": "Beginner"},
        )
        self.assertEqual(status, 400)

        # Valid UO registration succeeds with HTTP 201 and baseline 1200 rating.
        status, member = self._request(
            "POST",
            "/api/members",
            {"name": "Emma", "email": "emma@uoregon.edu", "skill_tier": "Beginner"},
        )
        self.assertEqual(status, 201)
        self.assertEqual(member["current_rating"], 1200)

        # Duplicate email must return HTTP 409 Conflict (FR-05).
        status, _ = self._request(
            "POST",
            "/api/members",
            {"name": "Emma Again", "email": "EMMA@uoregon.edu", "skill_tier": "Casual"},
        )
        self.assertEqual(status, 409)

    # -------------------------------------------------------------------------
    # Match Submission, Dynamic Standings, & Un-Enrollment (FR-08 to FR-12)
    # -------------------------------------------------------------------------

    def test_match_elo_standings_and_unenroll_flow(self) -> None:
        """Verifies end-to-end match recording, Elo standings, and 'Former Member' un-enroll."""
        token = self._login_officer()

        # Enroll two members publicly.
        _, emma = self._request(
            "POST",
            "/api/members",
            {"name": "Emma", "email": "emma@uoregon.edu", "skill_tier": "Casual"},
        )
        _, addison = self._request(
            "POST",
            "/api/members",
            {"name": "Addison", "email": "addison@uoregon.edu", "skill_tier": "Tournament"},
        )

        # Officer records a win for Emma (White) over Addison (Black).
        status, match_resp = self._request(
            "POST",
            "/api/matches",
            {"white_id": emma["id"], "black_id": addison["id"], "outcome": "1-0"},
            token=token,
        )
        self.assertEqual(status, 201)
        self.assertGreater(match_resp["white_rating"], 1200)
        self.assertLess(match_resp["black_rating"], 1200)

        # Public standings must rank Emma #1 and Addison #2.
        status, standings = self._request("GET", "/api/standings")
        self.assertEqual(status, 200)
        self.assertEqual(standings[0]["name"], "Emma")
        self.assertEqual(standings[0]["rank"], 1)
        self.assertEqual(standings[1]["name"], "Addison")
        self.assertEqual(standings[1]["rank"], 2)

        # Officer un-enrolls Emma; standings remove Emma while matches retain 'Former Member'.
        status, _ = self._request("DELETE", f"/api/members/{emma['id']}", token=token)
        self.assertEqual(status, 200)

        _, standings_after = self._request("GET", "/api/standings")
        self.assertEqual(len(standings_after), 1)
        self.assertEqual(standings_after[0]["name"], "Addison")

        _, matches_after = self._request("GET", "/api/matches")
        self.assertEqual(matches_after[0]["white_label"], "Former Member")
        self.assertEqual(matches_after[0]["black_label"], "Addison")

    # -------------------------------------------------------------------------
    # Events & Announcements CRUD Tests (FR-01, FR-03, FR-07)
    # -------------------------------------------------------------------------

    def test_events_and_announcements_crud(self) -> None:
        """Verifies officer create/update/delete and public reads for events & notices."""
        token = self._login_officer()

        # Create, update, and delete an event.
        status, ev = self._request(
            "POST",
            "/api/events",
            {
                "title": "Beginners Night",
                "date_time": "2026-11-19T18:00:00",
                "location": "Straub 145",
                "description": "Pawn endgames",
            },
            token=token,
        )
        self.assertEqual(status, 201)

        status, updated_ev = self._request(
            "PUT",
            f"/api/events/{ev['id']}",
            {
                "title": "Beginners Night",
                "date_time": "2026-11-19T18:00:00",
                "location": "EMU 119",
                "description": "Moved room",
            },
            token=token,
        )
        self.assertEqual(status, 200)
        self.assertEqual(updated_ev["location"], "EMU 119")

        status, _ = self._request("DELETE", f"/api/events/{ev['id']}", token=token)
        self.assertEqual(status, 200)

        # Create and fetch an announcement.
        status, ann = self._request(
            "POST",
            "/api/announcements",
            {"title": "Tournament", "body": "Blitz tournament next Friday!"},
            token=token,
        )
        self.assertEqual(status, 201)

        status, all_ann = self._request("GET", "/api/announcements")
        self.assertEqual(status, 200)
        self.assertEqual(len(all_ann), 1)
        self.assertEqual(all_ann[0]["title"], "Tournament")


if __name__ == "__main__":
    unittest.main()