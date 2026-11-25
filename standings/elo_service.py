"""
Elo rating calculation engine for Emerald City Chess Hub. 
Computes win/loss expectancy math using K=32 and handles dynamic 
leaderboard sorting.

Strict Boundary:
    Pure business logic module. It must not import `sqlite3` or handle 
    raw HTTP requests, operating purely on data passed to its functions.
"""

import math
from typing import List, Dict, Tuple, Protocol, TypedDict


class MemberDict(TypedDict):
    id: int
    name: str
    rating: float


class LeaderboardEntry(TypedDict):
    rank: int
    name: str
    rating: float
    skill_tier: str


class DatabaseProtocol(Protocol):
    def get_member_by_id(self, member_id: int) -> MemberDict | None: ...
    def record_match_and_ratings(
        self, white_id: int, black_id: int, outcome: float,
        new_white_rating: float, new_black_rating: float
    ) -> None: ...
    def get_active_members_sorted(self) -> List[MemberDict]: ...


class EloStandingsService:
    """
    Stateless calculation service for chess Elo ratings and dynamic rankings.
    """

    K_FACTOR: int = 32
    MIN_RATING_FLOOR: float = 100.0
    MAX_RATING_DIFF: float = 4000.0
    VALID_OUTCOMES = {1.0, 0.5, 0.0}


    @classmethod
    def _validate_rating(cls, rating: float, label: str = "Rating") -> float:
        """Ensures a rating is a finite number and enforces the minimum rating floor."""
        if isinstance(rating, bool) or not isinstance(rating, (int, float)):
            raise TypeError(f"{label} must be a numeric value, got {type(rating).__name__}.")
        
        if not math.isfinite(rating):
            raise ValueError(f"{label} must be a finite number (cannot be NaN or Infinity).")
        
        # Clamp to the minimum floor so zero or negative ratings never enter the formula
        return max(cls.MIN_RATING_FLOOR, float(rating))


    @classmethod
    def calculate_expected_score(cls, rating_a: float, rating_b: float) -> float:
        """
        Computes expected score with guards against zero/negative ratings
        and floating-point overflow on extreme rating gaps.
        """
       
        safe_rating_a = cls._validate_rating(rating_a, "rating_a")
        safe_rating_b = cls._validate_rating(rating_b, "rating_b")

        rating_diff = max(-cls.MAX_RATING_DIFF, min(cls.MAX_RATING_DIFF, safe_rating_a - safe_rating_b))

        return 1.0 / (1.0 + 10.0 ** (rating_diff / 400.0))
    
    @classmethod
    def compute_new_ratings(
        cls, 
        rating_a: float, 
        rating_b: float, 
        actual_score_a: float
    ) -> Tuple[float, float]:
        """
        Computes updated Elo ratings for two players.
        Player's ratings never drops below 100.

        actual_score_a: 1.0 for win, 0.5 for draw, 0.0 for loss.
        """

        if actual_score_a not in cls.VALID_OUTCOMES:
            raise ValueError(f"Invalid outcome: {actual_score_a}.\n"
                             "The outcome must either be: 1.0 (win), 0.5 (draw), or 0.0 (loss).")
        
        safe_rating_a = cls._validate_rating(rating_a, "rating_a")
        safe_rating_b = cls._validate_rating(rating_b, "rating_b")

        expected_rating_a = cls.calculate_expected_score(safe_rating_a, safe_rating_b)
        expected_rating_b = cls.calculate_expected_score(safe_rating_b, safe_rating_a)

        actual_score_b = 1.0 - actual_score_a

        updated_rating_a = safe_rating_a + cls.K_FACTOR * (actual_score_a - expected_rating_a)
        updated_rating_b = safe_rating_b + cls.K_FACTOR * (actual_score_b - expected_rating_b)

        final_rating_a = max(cls.MIN_RATING_FLOOR, round(updated_rating_a, 2))
        final_rating_b = max(cls.MIN_RATING_FLOOR, round(updated_rating_b, 2))

        return final_rating_a, final_rating_b
    

    @staticmethod 
    def assign_skill_tier(rating: float) -> str:
        """Assigns a skill tier based on the player's Elo rating."""

        if rating >= 2000:
            return "Master"
        elif rating >= 1700:
            return "Expert"
        elif rating >= 1400:
            return "Intermediate"
        else:
            return "Novice"


    @classmethod
    def process_match(
        cls, 
        db_manager: DatabaseProtocol, 
        white_id: int, 
        black_id: int, 
        outcome: float
    ) -> None:
        """
        Dynamic Model: Processes match entry. Fetches current ratings from database,
        computes expected scores and new player ratings, then saves this new information to the database.
        
        outcome: 1.0 if White player wins, 0.5 for draw, 0.0 if Black player wins.
        """

        if white_id == black_id:
            raise ValueError("A player cannot play a match against themselves.")

        if outcome not in cls.VALID_OUTCOMES:
            raise ValueError(f"Invalid outcome: {outcome}.\n"
                             "The outcome must either be: 1.0 (win), 0.5 (draw), or 0.0 (loss).")
        
        white_player = db_manager.get_member_by_id(white_id)
        black_player = db_manager.get_member_by_id(black_id)

        if not white_player or not black_player:
            missing_id = white_id if not white_player else black_id
            raise ValueError(f"Player with ID {missing_id} could not be found in the database.")
        
        white_rating = white_player["rating"]
        black_rating = black_player["rating"]

        new_white_rating, new_black_rating = cls.compute_new_ratings(white_rating, black_rating, outcome)

        db_manager.record_match_and_ratings(
            white_id = white_id, 
            black_id = black_id, 
            outcome = outcome, 
            new_white_rating = new_white_rating, 
            new_black_rating = new_black_rating 
        )


    @classmethod
    def get_leaderboard(cls, db_manager: DatabaseProtocol) -> List[LeaderboardEntry]:
        """
        Dynamic Model: On GET /api/standings, fetches active members sorted by rating
        from Database and assigns 1-indexed ranks dynamically with skill tiers.
        """

        raw_members = db_manager.get_active_members_sorted()
        leaderboard: List[LeaderboardEntry] = []

        for index, member in enumerate(raw_members, start=1):
            rating = member["rating"]
            leaderboard.append({
                "rank": index,
                "name": member["name"],
                "rating": rating,
                "skill_tier": cls.assign_skill_tier(rating)
            })

        return leaderboard
