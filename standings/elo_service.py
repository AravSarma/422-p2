"""
Elo rating calculation engine for Emerald City Chess Hub. 
Computes win/loss expectancy math using K=32 and handles dynamic 
leaderboard sorting.

Strict Boundary:
    Pure business logic module. It must not import `sqlite3` or handle 
    raw HTTP requests, operating purely on data passed to its functions.
"""


from typing import List, Dict, Tuple, Any


class EloStandingsService:
    """
    Stateless calculation service for chess Elo ratings and dynamic rankings.
    """

    K_FACTOR: int = 32

    @staticmethod
    def calculate_expected_score(rating_a: float, rating_b: float) -> float:
        """
        Computes expected score (win probability) for Player A against Player B
        """
        return 1.0 / (1.0 + 10.0 ** ((rating_b - rating_a) / 400.0))
    

    def compute_new_ratings(
        cls, 
        rating_a: float, 
        rating_b: float, 
        actual_score_a: float
    ) -> Tuple[float, float]:
        """
        Computes updated Elo ratings for two players.

        actual_score_a: 1.0 for win, 0.5 for draw, 0.0 for loss.
        """
        
        expected_a = cls.calculate_expected_score(rating_a, rating_b)
        expected_b = cls.calculate_expected_score(rating_b, rating_a)

        actual_score_b = 1.0 - actual_score_a

        new_rating_a = rating_a + cls.K_FACTOR * (actual_score_a - expected_a)
        new_rating_b = rating_b + cls.K_FACTOR * (actual_score_b - expected_b)

        return round(new_rating_a, 2), round(new_rating_b, 2)
    

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
        db_manager: Any, 
        white_id: int, 
        black_id: int, 
        outcome: float
    ) -> None:
        """
        Dynamic Model: Processes match entry. Fetches current ratings from database,
        computes expected scores and new player ratings, then saves this new information to the database.
        
        outcome: 1.0 if White player wins, 0.5 for draw, 0.0 if Black player wins.
        """
        
        white_player = db_manager.get_member_by_id(white_id)
        black_player = db_manager.get_member_by_id(black_id)

        if not white_player or black_player:
            raise ValueError("One or both players could not be found in the database.")
        
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
    def get_leaderboard(cls, db_manager: Any) -> List[Dict[str, Any]]:
        """
        Dynamic Model: On GET /api/standings, fetches active members sorted by rating
        from Database and assigns 1-indexed ranks dynamically with skill tiers.
        """

        raw_members = db_manager.get_active_members_sorted()
        leaderboard = []

        for index, member in enumerate(raw_members, start=1):
            rating = member["rating"]
            leaderboard.append({
                "rank": index,
                "name": member["name"],
                "rating": rating,
                "skill_tier": cls.determine_skill_tier(rating)
            })

        return leaderboard
