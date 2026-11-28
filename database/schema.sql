-- =============================================================================
-- File: database/schema.sql
-- Project: Emerald City Chess Hub (EC-ChessHub) — CS 422 Project 2
-- Author: Aaron Richards (Database Lead)
-- Created: 2026-11-27
--
-- Purpose:
--   Defines the complete SQLite relational schema for EC-ChessHub
--   (persisted locally in data/chess_hub.db).
--
-- Relationships to Other Files:
--   - Executed by database/db_manager.py (DatabaseManager.initialize_schema).
--   - No other module (backend/, standings/, frontend/) accesses this schema
--     or sqlite3 directly, preserving strict database encapsulation (NFR-03).
--
-- Dependencies:
--   - SQLite 3 (bundled with Python 3.11+ standard library sqlite3 module).
-- =============================================================================

-- Enable foreign key constraint enforcement for this database connection.
-- SQLite disables foreign key checks by default unless explicitly enabled.
PRAGMA foreign_keys = ON;

-- -----------------------------------------------------------------------------
-- Table: events
-- Purpose: Stores upcoming and past club meetings, beginner clinics, puzzle
--          workshops, and tournaments displayed on the public hub (FR-01, FR-07).
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS events (
    id          INTEGER PRIMARY KEY AUTOINCREMENT, -- Unique surrogate key for each event
    title       TEXT    NOT NULL,                  -- Event title (e.g., "Thursday Beginners Night")
    date_time   TEXT    NOT NULL,                  -- ISO-8601 timestamp (e.g., "2026-11-19T18:00:00")
    location    TEXT    NOT NULL,                  -- Campus building and room (e.g., "Straub 145")
    description TEXT    NOT NULL DEFAULT ''        -- Optional agenda or workshop topic details
);

-- -----------------------------------------------------------------------------
-- Table: announcements
-- Purpose: Stores club-wide notices (e.g., room changes, tournament signups)
--          ordered newest-to-oldest on the public homepage (FR-03, FR-07).
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS announcements (
    id          INTEGER PRIMARY KEY AUTOINCREMENT, -- Unique surrogate key for each announcement
    title       TEXT    NOT NULL,                  -- Short headline for the announcement
    body        TEXT    NOT NULL,                  -- Full text content of the announcement
    created_at  TEXT    NOT NULL DEFAULT (datetime('now')) -- UTC creation timestamp for sorting
);

-- -----------------------------------------------------------------------------
-- Table: members
-- Purpose: Stores currently enrolled club members and their active chess Elo
--          ratings (FR-04, FR-05, FR-09, FR-10, FR-11).
-- Design Note:
--   Leaderboard rank is intentionally NOT stored as a column; rankings are
--   computed dynamically by sorting current_rating DESC (FR-10).
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS members (
    id             INTEGER PRIMARY KEY AUTOINCREMENT, -- Unique surrogate key for each member
    name           TEXT    NOT NULL,                  -- Member full name (purged on un-enrollment)
    email          TEXT    NOT NULL UNIQUE,           -- Unique UO email; enforces FR-05 duplicate check
    skill_tier     TEXT    NOT NULL CHECK (           -- Self-selected experience tier
                       skill_tier IN ('Beginner', 'Casual', 'Tournament')
                   ),
    current_rating INTEGER NOT NULL DEFAULT 1200,     -- Active chess Elo rating (baseline 1200)
    created_at     TEXT    NOT NULL DEFAULT (datetime('now')) -- UTC enrollment timestamp
);

-- -----------------------------------------------------------------------------
-- Table: matches
-- Purpose: Stores completed club chess games (FR-08, FR-12).
-- Design Note (Former Member Retention Policy — FR-11 & FR-12):
--   white_member_id and black_member_id are nullable foreign keys with
--   ON DELETE SET NULL. Before a member row is deleted during un-enrollment,
--   DatabaseManager.unenroll_member() updates white_label or black_label to
--   'Former Member' so opponents' historical match records remain valid.
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS matches (
    id              INTEGER PRIMARY KEY AUTOINCREMENT, -- Unique surrogate key for each match
    white_member_id INTEGER,                           -- FK to members(id); NULL if un-enrolled
    black_member_id INTEGER,                           -- FK to members(id); NULL if un-enrolled
    white_label     TEXT    NOT NULL,                  -- Display name or 'Former Member'
    black_label     TEXT    NOT NULL,                  -- Display name or 'Former Member'
    outcome         TEXT    NOT NULL CHECK (           -- Standard chess notation for match result
                        outcome IN ('1-0', '0-1', '1/2-1/2')
                    ),
    played_at       TEXT    NOT NULL DEFAULT (datetime('now')), -- UTC timestamp when logged
    FOREIGN KEY (white_member_id) REFERENCES members(id) ON DELETE SET NULL,
    FOREIGN KEY (black_member_id) REFERENCES members(id) ON DELETE SET NULL
);

-- -----------------------------------------------------------------------------
-- Table: officers
-- Purpose: Stores authenticated club officer credentials for accessing the
--          Officer Dashboard (FR-06). Passwords are stored only as hashes.
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS officers (
    id            INTEGER PRIMARY KEY AUTOINCREMENT, -- Unique surrogate key for each officer
    username      TEXT    NOT NULL UNIQUE,           -- Unique officer login username
    password_hash TEXT    NOT NULL                   -- Salted cryptographic hash of password
);

-- -----------------------------------------------------------------------------
-- Indexes
-- Purpose: Speed up dynamic leaderboard sorting (FR-10, NFR-04) and member
--          match history lookups while keeping local queries well under 300ms.
-- -----------------------------------------------------------------------------
CREATE INDEX IF NOT EXISTS idx_members_rating
    ON members (current_rating DESC);

CREATE INDEX IF NOT EXISTS idx_matches_white
    ON matches (white_member_id);

CREATE INDEX IF NOT EXISTS idx_matches_black
    ON matches (black_member_id);