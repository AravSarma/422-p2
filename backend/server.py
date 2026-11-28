"""
File: backend/server.py
Project: Emerald City Chess Hub (EC-ChessHub) — CS 422 Project 2
Author: Arav Sarma (Backend & API Lead)
Created: 2026-11-27

Purpose:
    HTTP server, request router, and officer authentication guard for
    Emerald City Chess Hub. Validates incoming JSON payloads and handles
    HTTP request lifecycles for both `/api/*` endpoints and static frontend
    assets built by the Docker multi-stage build.

Strict Boundary (NFR-03):
    This module handles HTTP logic only. It must not import `sqlite3`
    or execute raw database queries directly; all data operations must
    be delegated to the `database` module (`DatabaseManager`), and all
    Elo rating computations are delegated to the `standings` module.

Environment Variables (configured in docker-compose.yml):
    - HOST: Bind interface (default: "0.0.0.0")
    - PORT: Listening port (default: 8000)
    - DB_PATH: Local SQLite file path (default: "data/chess_hub.db")
    - STATIC_DIR: Built React frontend directory (default: "frontend/dist")
    - OFFICER_USERNAME: Seed officer username (default: "admin")
    - OFFICER_PASSWORD: Seed officer password (default: "chessclub2026")

Dependencies:
    - Python 3.11+ Standard Library only (`http.server`, `json`, `mimetypes`,
      `os`, `pathlib`, `urllib.parse`, `typing`).
"""

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import mimetypes
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

from backend.auth import AuthManager
from backend.validator import PayloadValidator, ValidationError
from database import (
    DatabaseError,
    DatabaseManager,
    DuplicateEmailError,
    MemberNotFoundError,
    RecordNotFoundError,
)


# Maximum allowed JSON request body size in bytes (1 MB) to prevent abuse.
# Scope: module-level constant; Lifetime: duration of the Python process.
MAX_BODY_BYTES: int = 1_048_576


class _FallbackStandingsAdapter:
    """
    Lightweight standard-library fallback adapter used only if
    `standings.elo_service.EloStandingsService` is not yet populated.

    Ensures `backend/server.py` and `tests/test_api.py` remain runnable
    during parallel development while seamlessly using Enzo's
    `EloStandingsService` whenever it is present.
    """

    def __init__(self, db: DatabaseManager, k_factor: int = 32) -> None:
        self.db = db
        self.k_factor = k_factor

    def get_leaderboard(self) -> List[Dict[str, Any]]:
        """Computes dynamically ranked standings from active members (FR-10)."""
        members = self.db.get_active_members_sorted()
        leaderboard: List[Dict[str, Any]] = []
        # Assign 1-indexed ranks dynamically without storing rank in SQLite.
        for idx, member in enumerate(members, start=1):
            leaderboard.append(
                {
                    "rank": idx,
                    "id": member["id"],
                    "name": member["name"],
                    "rating": member["current_rating"],
                    "skill_tier": member["skill_tier"],
                }
            )
        return leaderboard

    def process_match(self, white_id: int, black_id: int, outcome: str) -> Dict[str, Any]:
        """Computes K=32 Elo updates and commits the match atomically via Database."""
        white = self.db.get_member_by_id(white_id)
        black = self.db.get_member_by_id(black_id)
        if white is None:
            raise MemberNotFoundError(f"White player ID {white_id} not found.")
        if black is None:
            raise MemberNotFoundError(f"Black player ID {black_id} not found.")

        r_w: float = float(white["current_rating"])
        r_b: float = float(black["current_rating"])

        # Expected scores under the standard chess Elo formula.
        e_w: float = 1.0 / (1.0 + 10.0 ** ((r_b - r_w) / 400.0))
        e_b: float = 1.0 - e_w

        # Map chess outcome string to numeric scores S_w and S_b.
        if outcome == "1-0":
            s_w, s_b = 1.0, 0.0
        elif outcome == "0-1":
            s_w, s_b = 0.0, 1.0
        else:
            s_w, s_b = 0.5, 0.5

        new_w: int = round(r_w + self.k_factor * (s_w - e_w))
        new_b: int = round(r_b + self.k_factor * (s_b - e_b))

        match_row = self.db.record_match_and_ratings(
            white_id=white_id,
            black_id=black_id,
            outcome=outcome,
            new_white_rating=new_w,
            new_black_rating=new_b,
        )
        return {
            "match": match_row,
            "white_rating": new_w,
            "black_rating": new_b,
        }


class _StandingsServiceBridge:
    """
    Adapter bridging `backend/server.py` to the stateless `@classmethod` API
    of `standings.elo_service.EloStandingsService`.

    Converts chess outcome strings ('1-0', '1/2-1/2', '0-1') into the numeric
    scores (1.0, 0.5, 0.0) expected by `EloStandingsService.process_match()`.
    """

    OUTCOME_TO_FLOAT: Dict[str, float] = {
        "1-0": 1.0,
        "1/2-1/2": 0.5,
        "0-1": 0.0,
    }

    def __init__(self, db: DatabaseManager, elo_cls: Any) -> None:
        self.db = db
        self.elo_cls = elo_cls

    def get_leaderboard(self) -> List[Dict[str, Any]]:
        """Delegates dynamic leaderboard generation to EloStandingsService."""
        return self.elo_cls.get_leaderboard(self.db)

    def process_match(self, white_id: int, black_id: int, outcome: str) -> Dict[str, Any]:
        """Delegates Elo calculation and persistence to EloStandingsService."""
        numeric_outcome: float = self.OUTCOME_TO_FLOAT[outcome]
        try:
            self.elo_cls.process_match(self.db, white_id, black_id, numeric_outcome)
        except ValueError as exc:
            # Map missing-player ValueErrors to MemberNotFoundError for HTTP 404.
            if "could not be found" in str(exc):
                raise MemberNotFoundError(str(exc)) from exc
            raise ValidationError(str(exc)) from exc

        # Fetch updated ratings and latest match to return in the HTTP 201 payload.
        white = self.db.get_member_by_id(white_id)
        black = self.db.get_member_by_id(black_id)
        matches = self.db.get_all_matches()
        return {
            "match": matches[0] if matches else {},
            "white_rating": white["rating"] if white else None,
            "black_rating": black["rating"] if black else None,
        }


def _load_standings_service(db: DatabaseManager) -> Any:
    """
    Imports `standings.elo_service.EloStandingsService` and wraps its stateless
    `@classmethod` interface via `_StandingsServiceBridge`; falls back to
    `_FallbackStandingsAdapter` if the module is unavailable.
    """
    try:
        from standings.elo_service import EloStandingsService  # type: ignore

        if callable(getattr(EloStandingsService, "get_leaderboard", None)) and callable(
            getattr(EloStandingsService, "process_match", None)
        ):
            return _StandingsServiceBridge(db, EloStandingsService)
    except ImportError:
        pass
    return _FallbackStandingsAdapter(db)


class ChessHubServer(ThreadingHTTPServer):
    """
    Threaded HTTP server holding shared, encapsulated module dependencies.

    Instance Attributes:
        db (DatabaseManager): Encapsulated SQLite persistence manager.
        auth (AuthManager): Officer authentication & bearer-session manager.
        standings (Any): EloStandingsService instance for ratings/leaderboards.
        static_dir (Path): Directory containing compiled React static files.
    """

    def __init__(
        self,
        server_address: Tuple[str, int],
        db: DatabaseManager,
        auth: AuthManager,
        standings: Any,
        static_dir: Path,
    ) -> None:
        self.db = db
        self.auth = auth
        self.standings = standings
        self.static_dir = static_dir
        super().__init__(server_address, ChessHubRequestHandler)


class ChessHubRequestHandler(BaseHTTPRequestHandler):
    """
    HTTP request router for all `/api/*` JSON routes and static React assets.
    """

    # Type hint for mypy/IDE clarity: `self.server` is always ChessHubServer.
    server: ChessHubServer

    # -------------------------------------------------------------------------
    # Low-Level HTTP & JSON Helpers
    # -------------------------------------------------------------------------

    def _send_cors_headers(self) -> None:
        """Attaches standard CORS headers to support local frontend development."""
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")

    def _send_json(self, status_code: int, data: Any) -> None:
        """
        Serializes `data` to UTF-8 JSON and writes the complete HTTP response.

        Args:
            status_code: HTTP status code (e.g., 200, 201, 400, 401, 404, 409).
            data: JSON-serializable Python object (dict or list).
        """
        body: bytes = json.dumps(data).encode("utf-8")
        self.send_response(status_code)
        self._send_cors_headers()
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_error_json(self, status_code: int, message: str) -> None:
        """Convenience wrapper returning a uniform `{"error": message}` JSON body."""
        self._send_json(status_code, {"error": message})

    def _read_json_body(self) -> Dict[str, Any]:
        """
        Reads and parses the incoming HTTP request body as a JSON object.

        Raises:
            ValidationError: If Content-Length is invalid, too large, or malformed JSON.
        """
        raw_length: Optional[str] = self.headers.get("Content-Length")
        if raw_length is None:
            return {}

        try:
            content_length: int = int(raw_length)
        except ValueError as exc:
            raise ValidationError("Invalid Content-Length header.") from exc

        if content_length < 0 or content_length > MAX_BODY_BYTES:
            raise ValidationError("Request payload exceeds maximum allowed size.")

        if content_length == 0:
            return {}

        raw_bytes: bytes = self.rfile.read(content_length)
        try:
            parsed: Any = json.loads(raw_bytes.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValidationError(f"Malformed JSON body: {exc}") from exc

        if not isinstance(parsed, dict):
            raise ValidationError("JSON body must be an object.")
        return parsed

    def _require_officer(self) -> Optional[str]:
        """
        Verifies officer authentication via `AuthManager` (FR-06).

        Returns:
            Authenticated username if valid; sends HTTP 401 and returns None if not.
        """
        username: Optional[str] = self.server.auth.verify_session(self.headers)
        if username is None:
            self._send_error_json(401, "Officer authentication required.")
            return None
        return username

    def _parse_id_segment(self, path: str, prefix: str) -> Optional[int]:
        """
        Extracts a positive integer ID from paths like `/api/events/42`.

        Args:
            path: Request URL path without query string.
            prefix: Expected prefix including trailing slash (e.g., `/api/events/`).

        Returns:
            Parsed positive integer ID, or None if the path does not match.
        """
        if not path.startswith(prefix):
            return None
        remainder: str = path[len(prefix) :].strip("/")
        if remainder.isdigit() and int(remainder) > 0:
            return int(remainder)
        return None

    def _serve_static_file(self, path: str) -> None:
        """
        Serves compiled React/Tailwind static files from `static_dir` with SPA fallback.
        """
        static_root: Path = self.server.static_dir.resolve()
        if not static_root.exists():
            self._send_error_json(404, "Endpoint not found.")
            return

        # Strip leading slash and prevent path-traversal outside `static_root`.
        rel_path: str = path.lstrip("/") or "index.html"
        target: Path = (static_root / rel_path).resolve()
        if not str(target).startswith(str(static_root)) or not target.is_file():
            # Fall back to index.html for client-side React Router paths.
            target = static_root / "index.html"
            if not target.is_file():
                self._send_error_json(404, "Frontend assets not found.")
                return

        content_type, _ = mimetypes.guess_type(str(target))
        file_bytes: bytes = target.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type or "application/octet-stream")
        self.send_header("Content-Length", str(len(file_bytes)))
        self.end_headers()
        self.wfile.write(file_bytes)

    def log_message(self, format: str, *args: Any) -> None:
        """Suppresses noisy stderr logs during automated unittest runs if desired."""
        if os.environ.get("QUIET_HTTP_LOGS") == "1":
            return
        super().log_message(format, *args)

    # -------------------------------------------------------------------------
    # HTTP Method Dispatchers
    # -------------------------------------------------------------------------

    def do_OPTIONS(self) -> None:
        """Responds to CORS preflight requests with HTTP 204 No Content."""
        self.send_response(204)
        self._send_cors_headers()
        self.end_headers()

    def do_GET(self) -> None:
        """Routes all HTTP GET requests for public pages, API reads, and static files."""
        path: str = urlparse(self.path).path

        try:
            # Health check endpoint for Docker / integration readiness probes.
            if path == "/api/health":
                self._send_json(200, {"status": "ok"})
                return

            # Public schedule display (FR-01).
            if path == "/api/events":
                self._send_json(200, self.server.db.get_all_events())
                return

            # Public announcements feed ordered newest-to-oldest (FR-03).
            if path == "/api/announcements":
                self._send_json(200, self.server.db.get_all_announcements())
                return

            # Public dynamically computed Elo leaderboard (FR-10).
            if path == "/api/standings":
                self._send_json(200, self.server.standings.get_leaderboard())
                return

            # Public match history list (includes 'Former Member' labels — FR-12).
            if path == "/api/matches":
                self._send_json(200, self.server.db.get_all_matches())
                return

            # Protected officer session verification endpoint.
            if path in ("/api/auth/session", "/api/officer/session"):
                username = self._require_officer()
                if username is not None:
                    self._send_json(200, {"authenticated": True, "username": username})
                return

            # Protected member roster listing (contains student emails — officer only).
            if path == "/api/members":
                if self._require_officer() is None:
                    return
                self._send_json(200, self.server.db.get_active_members_sorted())
                return

            # Unknown /api/* routes return JSON 404 rather than HTML.
            if path.startswith("/api/"):
                self._send_error_json(404, f"Unknown API endpoint: {path}")
                return

            # Non-API paths serve the compiled React frontend.
            self._serve_static_file(path)
        except DatabaseError as exc:
            self._send_error_json(500, str(exc))

    def do_POST(self) -> None:
        """Routes all HTTP POST requests (login, public registration, officer creates)."""
        path: str = urlparse(self.path).path

        try:
            payload: Dict[str, Any] = self._read_json_body()

            # Officer login endpoint (FR-06).
            if path in ("/api/auth/login", "/api/officer/login"):
                creds = PayloadValidator.validate_login(payload)
                session = self.server.auth.login(creds["username"], creds["password"])
                if session is None:
                    self._send_error_json(401, "Invalid officer username or password.")
                    return
                self._send_json(200, session)
                return

            # Officer logout endpoint.
            if path in ("/api/auth/logout", "/api/officer/logout"):
                token = self.server.auth.extract_bearer_token(self.headers)
                if token is not None:
                    self.server.auth.logout(token)
                self._send_json(200, {"logged_out": True})
                return

            # Public in-site student registration (FR-04, FR-05) — no login required.
            if path == "/api/members":
                clean = PayloadValidator.validate_member_registration(payload)
                created = self.server.db.create_member(
                    name=clean["name"],
                    email=clean["email"],
                    skill_tier=clean["skill_tier"],
                )
                self._send_json(201, created)
                return

            # Protected: Create club event (FR-07).
            if path == "/api/events":
                if self._require_officer() is None:
                    return
                clean = PayloadValidator.validate_event(payload)
                created = self.server.db.create_event(**clean)
                self._send_json(201, created)
                return

            # Protected: Create club announcement (FR-07).
            if path == "/api/announcements":
                if self._require_officer() is None:
                    return
                clean = PayloadValidator.validate_announcement(payload)
                created = self.server.db.create_announcement(**clean)
                self._send_json(201, created)
                return

            # Protected: Record chess match and recompute Elo ratings (FR-08, FR-09).
            if path == "/api/matches":
                if self._require_officer() is None:
                    return
                clean = PayloadValidator.validate_match(payload)
                result = self.server.standings.process_match(
                    white_id=clean["white_id"],
                    black_id=clean["black_id"],
                    outcome=clean["outcome"],
                )
                self._send_json(201, result)
                return

            self._send_error_json(404, f"Unknown API endpoint: {path}")
        except ValidationError as exc:
            self._send_error_json(400, str(exc))
        except DuplicateEmailError as exc:
            self._send_error_json(409, str(exc))
        except MemberNotFoundError as exc:
            self._send_error_json(404, str(exc))
        except DatabaseError as exc:
            self._send_error_json(500, str(exc))

    def do_PUT(self) -> None:
        """Routes all HTTP PUT requests for officer updates to events/announcements."""
        path: str = urlparse(self.path).path

        try:
            if self._require_officer() is None:
                return

            payload: Dict[str, Any] = self._read_json_body()

            # Protected: Update an event by ID (FR-07).
            event_id = self._parse_id_segment(path, "/api/events/")
            if event_id is not None:
                clean = PayloadValidator.validate_event(payload)
                updated = self.server.db.update_event(event_id=event_id, **clean)
                self._send_json(200, updated)
                return

            # Protected: Update an announcement by ID (FR-07).
            ann_id = self._parse_id_segment(path, "/api/announcements/")
            if ann_id is not None:
                clean = PayloadValidator.validate_announcement(payload)
                updated = self.server.db.update_announcement(announcement_id=ann_id, **clean)
                self._send_json(200, updated)
                return

            self._send_error_json(404, f"Unknown API endpoint: {path}")
        except ValidationError as exc:
            self._send_error_json(400, str(exc))
        except RecordNotFoundError as exc:
            self._send_error_json(404, str(exc))
        except DatabaseError as exc:
            self._send_error_json(500, str(exc))

    def do_DELETE(self) -> None:
        """Routes all HTTP DELETE requests (events, announcements, member un-enrollment)."""
        path: str = urlparse(self.path).path

        try:
            if self._require_officer() is None:
                return

            # Protected: Delete an event by ID (FR-07).
            event_id = self._parse_id_segment(path, "/api/events/")
            if event_id is not None:
                self.server.db.delete_event(event_id)
                self._send_json(200, {"deleted": True, "id": event_id})
                return

            # Protected: Delete an announcement by ID (FR-07).
            ann_id = self._parse_id_segment(path, "/api/announcements/")
            if ann_id is not None:
                self.server.db.delete_announcement(ann_id)
                self._send_json(200, {"deleted": True, "id": ann_id})
                return

            # Protected: Un-enroll member (purges PII, preserves 'Former Member' games — FR-11 & FR-12).
            member_id = self._parse_id_segment(path, "/api/members/")
            if member_id is not None:
                self.server.db.unenroll_member(member_id)
                self._send_json(200, {"unenrolled": True, "id": member_id})
                return

            self._send_error_json(404, f"Unknown API endpoint: {path}")
        except (RecordNotFoundError, MemberNotFoundError) as exc:
            self._send_error_json(404, str(exc))
        except DatabaseError as exc:
            self._send_error_json(500, str(exc))


def create_server(
    host: str = "0.0.0.0",
    port: int = 8000,
    db_path: str = "data/chess_hub.db",
    static_dir: str = "frontend/dist",
    default_officer_user: str = "admin",
    default_officer_pass: str = "chessclub2026",
) -> ChessHubServer:
    """
    Factory function that wires together DatabaseManager, AuthManager,
    EloStandingsService, and ChessHubServer.

    Used by both `main()` (production Docker container) and `tests/test_api.py`.
    """
    db = DatabaseManager(db_path=db_path)
    auth = AuthManager(db=db)
    auth.ensure_default_officer(default_officer_user, default_officer_pass)
    standings = _load_standings_service(db)

    return ChessHubServer(
        server_address=(host, port),
        db=db,
        auth=auth,
        standings=standings,
        static_dir=Path(static_dir),
    )


def main() -> None:
    """Entry point launched by Docker (`python -m backend.server`)."""
    # Read runtime configuration from environment variables (see docker-compose.yml).
    host: str = os.environ.get("HOST", "0.0.0.0")
    port: int = int(os.environ.get("PORT", "8000"))
    db_path: str = os.environ.get("DB_PATH", "data/chess_hub.db")
    static_dir: str = os.environ.get("STATIC_DIR", "frontend/dist")
    officer_user: str = os.environ.get("OFFICER_USERNAME", "admin")
    officer_pass: str = os.environ.get("OFFICER_PASSWORD", "chessclub2026")

    server = create_server(
        host=host,
        port=port,
        db_path=db_path,
        static_dir=static_dir,
        default_officer_user=officer_user,
        default_officer_pass=officer_pass,
    )
    print(f"Emerald City Chess Hub listening on http://{host}:{port} (DB: {db_path})")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down EC-ChessHub server...")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()