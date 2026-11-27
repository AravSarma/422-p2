/**
 * Typed HTTP/JSON client for the EC-ChessHub backend.
 *
 * This file is the frontend's half of the API contract (SDS §2.2.1). Every
 * request the UI makes goes through here, so the backend team can read this
 * file as the authoritative list of endpoints, payloads, and response shapes.
 *
 * Conventions expected from the backend:
 *   - All bodies are JSON (`Content-Type: application/json`).
 *   - Errors return a JSON body `{ "error": "human readable message" }`.
 *   - Officer-only routes require `Authorization: Bearer <token>` and return
 *     401 when the token is missing/invalid (FR-06).
 */

// ---------- Shared types ----------

/** Registration experience level chosen by the student (FR-04). */
export type SkillTier = "Beginner" | "Casual" | "Tournament";
export const SKILL_TIERS: SkillTier[] = ["Beginner", "Casual", "Tournament"];

/** Match outcome from White's perspective (FR-08). */
export type MatchOutcome = "1-0" | "0-1" | "1/2-1/2";

export interface ChessEvent {
  id: number;
  title: string;
  /** ISO-8601 local datetime, e.g. "2026-12-03T18:00:00" */
  date_time: string;
  location: string;
  description: string;
  /** Optional: number of RSVPs (FR-14). */
  rsvp_count?: number;
}

export type EventInput = Omit<ChessEvent, "id" | "rsvp_count">;

export interface Announcement {
  id: number;
  title: string;
  body: string;
  /** ISO-8601 timestamp */
  created_at: string;
}

export type AnnouncementInput = Pick<Announcement, "title" | "body">;

/** One row of GET /api/standings — shape produced by EloStandingsService.get_leaderboard(). */
export interface LeaderboardEntry {
  rank: number;
  name: string;
  rating: number;
  /** Rating band computed by the Standings module (Novice/Intermediate/Expert/Master). */
  skill_tier: string;
}

export interface MatchRecord {
  id: number;
  /** Player name, or "Former Member" after un-enrollment (FR-12). */
  white_label: string;
  black_label: string;
  outcome: MatchOutcome;
  played_at: string;
}

/** Full member record — officer-only because it contains email (PII). */
export interface Member {
  id: number;
  name: string;
  email: string;
  skill_tier: SkillTier;
  current_rating: number;
  created_at: string;
}

export interface PublicHubData {
  events: ChessEvent[];
  announcements: Announcement[];
}

// ---------- Error handling ----------

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }

  get isUnauthorized(): boolean {
    return this.status === 401;
  }
}

async function request<T>(
  method: string,
  path: string,
  options: { body?: unknown; token?: string | null } = {},
): Promise<T> {
  const headers: Record<string, string> = { Accept: "application/json" };
  if (options.body !== undefined) headers["Content-Type"] = "application/json";
  if (options.token) headers["Authorization"] = `Bearer ${options.token}`;

  let response: Response;
  try {
    response = await fetch(path, {
      method,
      headers,
      body: options.body !== undefined ? JSON.stringify(options.body) : undefined,
    });
  } catch {
    throw new ApiError(0, "Can't reach the Chess Hub server. Check your connection and try again.");
  }

  // 204 No Content (e.g. successful DELETE)
  if (response.status === 204) return undefined as T;

  let data: unknown = null;
  const text = await response.text();
  if (text) {
    try {
      data = JSON.parse(text);
    } catch {
      data = null;
    }
  }

  if (!response.ok) {
    const message =
      (data && typeof data === "object" && "error" in data && typeof data.error === "string"
        ? data.error
        : null) ?? defaultErrorMessage(response.status);
    throw new ApiError(response.status, message);
  }

  return data as T;
}

function defaultErrorMessage(status: number): string {
  if (status === 401) return "Your officer session has expired. Please log in again.";
  if (status === 404) return "That item no longer exists.";
  if (status === 409) return "That record already exists.";
  if (status >= 500) return "The server ran into a problem. Please try again.";
  return `Request failed (HTTP ${status}).`;
}

// ---------- Public endpoints (no login) ----------

export const ApiClient = {
  /** FR-01 + FR-03: parallel fetch of events and announcements. */
  async fetchPublicHubData(): Promise<PublicHubData> {
    const [events, announcements] = await Promise.all([
      request<ChessEvent[]>("GET", "/api/events"),
      request<Announcement[]>("GET", "/api/announcements"),
    ]);
    return { events, announcements };
  },

  /** FR-10: dynamically ranked leaderboard. */
  fetchStandings(): Promise<LeaderboardEntry[]> {
    return request<LeaderboardEntry[]>("GET", "/api/standings");
  },

  /** Recent match results, newest first (UC-3 "recent match history"). */
  fetchRecentMatches(): Promise<MatchRecord[]> {
    return request<MatchRecord[]>("GET", "/api/matches");
  },

  /**
   * FR-04 / FR-05: register without an account.
   * Backend returns 201 with the created member, 400 on invalid input,
   * or 409 when the email is already enrolled.
   */
  registerMember(name: string, email: string, skillTier: SkillTier): Promise<{ id: number }> {
    return request("POST", "/api/members", {
      body: { name, email, skill_tier: skillTier },
    });
  },

  /** FR-14: RSVP to one event by the email the member registered with. */
  rsvpToEvent(eventId: number, email: string): Promise<{ rsvp_count: number }> {
    return request("POST", `/api/events/${eventId}/rsvp`, { body: { email } });
  },

  // ---------- Officer endpoints ----------

  /** FR-06: exchange officer credentials for a session token. */
  officerLogin(username: string, password: string): Promise<{ token: string }> {
    return request("POST", "/api/login", { body: { username, password } });
  },

  officerLogout(token: string): Promise<void> {
    return request("POST", "/api/logout", { token });
  },

  /** Full roster incl. emails — officer only. */
  fetchMembers(token: string): Promise<Member[]> {
    return request<Member[]>("GET", "/api/admin/members", { token });
  },

  /** FR-07: event CRUD. */
  createEvent(event: EventInput, token: string): Promise<ChessEvent> {
    return request("POST", "/api/events", { body: event, token });
  },
  updateEvent(id: number, event: EventInput, token: string): Promise<ChessEvent> {
    return request("PUT", `/api/events/${id}`, { body: event, token });
  },
  deleteEvent(id: number, token: string): Promise<void> {
    return request("DELETE", `/api/events/${id}`, { token });
  },

  /** FR-07: announcement CRUD. */
  createAnnouncement(a: AnnouncementInput, token: string): Promise<Announcement> {
    return request("POST", "/api/announcements", { body: a, token });
  },
  updateAnnouncement(id: number, a: AnnouncementInput, token: string): Promise<Announcement> {
    return request("PUT", `/api/announcements/${id}`, { body: a, token });
  },
  deleteAnnouncement(id: number, token: string): Promise<void> {
    return request("DELETE", `/api/announcements/${id}`, { token });
  },

  /** FR-08 / FR-09: record a result; backend recomputes Elo for both players. */
  submitMatch(
    whiteId: number,
    blackId: number,
    outcome: MatchOutcome,
    authToken: string,
  ): Promise<MatchRecord> {
    return request("POST", "/api/matches", {
      body: { white_id: whiteId, black_id: blackId, outcome },
      token: authToken,
    });
  },

  /** FR-11 / FR-12: delete PII, keep match history as "Former Member". */
  unenrollMember(id: number, token: string): Promise<void> {
    return request("DELETE", `/api/members/${id}`, { token });
  },
};
