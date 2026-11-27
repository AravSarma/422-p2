/**
 * Static club info shown on the public hub (FR-02).
 *
 * TODO(club officers): replace the placeholder URLs below with the club's
 * real Discord invite, Instagram, Lichess/Chess.com team pages and UO Engage
 * page before printing flyers.
 */
export interface SocialLink {
  label: string;
  href: string;
  description: string;
}

export const SOCIAL_LINKS: SocialLink[] = [
  {
    label: "Discord",
    href: "https://discord.gg/REPLACE_ME",
    description: "Chat, find games, and get meeting reminders",
  },
  {
    label: "Instagram",
    href: "https://www.instagram.com/REPLACE_ME",
    description: "Photos and event announcements",
  },
  {
    label: "Lichess Team",
    href: "https://lichess.org/team/REPLACE_ME",
    description: "Play club arenas online",
  },
  {
    label: "Chess.com Club",
    href: "https://www.chess.com/club/REPLACE_ME",
    description: "Online club matches and puzzles",
  },
  {
    label: "UO Engage",
    href: "https://uoregon.campuslabs.com/engage/organization/REPLACE_ME",
    description: "Official student organization page",
  },
];

export const CLUB_NAME = "Emerald City Chess Club";
export const CLUB_TAGLINE =
  "University of Oregon's home for chess — every skill level welcome, no experience needed.";

/** UO email rule shared by the registration and RSVP forms (FR-04). */
export const UO_EMAIL_PATTERN = /^[^\s@]+@uoregon\.edu$/i;
