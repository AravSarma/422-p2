import unittest
from unittest.mock import MagicMock
import math
from standings.elo_service import EloStandingsService, DatabaseProtocol


class TestEloStandingsService(unittest.TestCase):
    """Unit test suite for EloStandingsService validation, math, and database workflows."""

    def setUp(self) -> None:
        """Set up a mock database manager for testing dynamic methods."""

        self.mock_db = MagicMock(spec=DatabaseProtocol)


    def test_calculate_expected_score_equal_ratings(self) -> None:
        """Verify that equal ratings result in an expected score of 0.5."""

        expected = EloStandingsService.calculate_expected_score(1500.0, 1500.0)
        self.assertAlmostEqual(expected, 0.5, places=4)


    def test_calculate_expected_score_advantage(self) -> None:
        """Verify that a higher-rated player has an expected score greater than 0.5."""

        expected_a = EloStandingsService.calculate_expected_score(1800.0, 1400.0)
        expected_b = EloStandingsService.calculate_expected_score(1400.0, 1800.0)
        
        self.assertGreater(expected_a, 0.5)
        self.assertLess(expected_b, 0.5)
        self.assertAlmostEqual(expected_a + expected_b, 1.0, places=4)


    def test_compute_new_ratings_win_loss(self, rating_a: float = 1200.0, rating_b: float = 1200.0) -> None:
        """Verify rating updates after a clear win (actual score 1.0)."""

        new_a, new_b = EloStandingsService.compute_new_ratings(rating_a, rating_b, 1.0)
        
        # Winner (A) should gain points, Loser (B) should lose equal points (K=32, expected=0.5 -> +16 points)
        self.assertEqual(new_a, 1216.0)
        self.assertEqual(new_b, 1184.0)


    def test_compute_new_ratings_draw(self) -> None:
        """Verify ratings remain unchanged on a draw between equal players."""

        new_a, new_b = EloStandingsService.compute_new_ratings(1500.0, 1500.0, 0.5)
        self.assertEqual(new_a, 1500.0)
        self.assertEqual(new_b, 1500.0)


    def test_rating_floor_enforcement(self) -> None:
        """Verify that ratings never drop below the minimum rating floor (100.0)."""

        # A very low-rated player losing against an equal opponent
        new_a, _ = EloStandingsService.compute_new_ratings(110.0, 1200.0, 0.0)
        self.assertEqual(new_a, EloStandingsService.MIN_RATING_FLOOR)


    def test_validate_rating_rejects_invalid_types(self) -> None:
        """Verify that booleans and non-numeric types raise TypeError."""

        with self.assertRaises(TypeError):
            EloStandingsService._validate_rating(True)
        with self.assertRaises(TypeError):
            EloStandingsService._validate_rating("1500")


    def test_validate_rating_rejects_non_finite(self) -> None:
        """Verify that NaN and Infinity raise ValueError."""

        with self.assertRaises(ValueError):
            EloStandingsService._validate_rating(float("nan"))
        with self.assertRaises(ValueError):
            EloStandingsService._validate_rating(float("inf"))


    def test_compute_new_ratings_invalid_outcome(self) -> None:
        """Verify that invalid outcome values raise ValueError."""

        with self.assertRaises(ValueError):
            EloStandingsService.compute_new_ratings(1500.0, 1500.0, 2.0)


    def test_assign_skill_tier(self) -> None:
        """Verify correct skill tier mapping based on rating thresholds."""

        self.assertEqual(EloStandingsService.assign_skill_tier(2100.0), "Master")
        self.assertEqual(EloStandingsService.assign_skill_tier(1850.0), "Expert")
        self.assertEqual(EloStandingsService.assign_skill_tier(1500.0), "Intermediate")
        self.assertEqual(EloStandingsService.assign_skill_tier(1200.0), "Novice")


    def test_process_match_success(self) -> None:
        """Verify process_match correctly fetches ratings, computes math, and calls database record."""

        self.mock_db.get_member_by_id.side_effect = lambda mid: {
            1: {"id": 1, "name": "Alice", "rating": 1500.0},
            2: {"id": 2, "name": "Bob", "rating": 1500.0}
        }[mid]

        EloStandingsService.process_match(self.mock_db, white_id=1, black_id=2, outcome=1.0)

        # Verify database record method was called with expected updated ratings
        self.mock_db.record_match_and_ratings.assert_called_once_with(
            white_id=1,
            black_id=2,
            outcome=1.0,
            new_white_rating=1516.0,
            new_black_rating=1484.0
        )


    def test_process_match_self_play_raises_error(self) -> None:
        """Verify matching a player against themselves raises ValueError."""

        with self.assertRaises(ValueError):
            EloStandingsService.process_match(self.mock_db, white_id=1, black_id=1, outcome=1.0)
        self.mock_db.record_match_and_ratings.assert_not_called()


    def test_process_match_missing_player_raises_error(self) -> None:
        """Verify matching a non-existent player raises ValueError."""

        self.mock_db.get_member_by_id.return_value = None  # Player not found

        with self.assertRaises(ValueError):
            EloStandingsService.process_match(self.mock_db, white_id=1, black_id=99, outcome=1.0)


    def test_get_leaderboard(self) -> None:
        """Verify get_leaderboard dynamically formats raw members into 1-indexed ranked entries with tiers."""
        
        self.mock_db.get_active_members_sorted.return_value = [
            {"id": 1, "name": "Alice", "rating": 2100.0},
            {"id": 2, "name": "Bob", "rating": 1350.0}
        ]

        leaderboard = EloStandingsService.get_leaderboard(self.mock_db)

        self.assertEqual(len(leaderboard), 2)
        self.assertEqual(leaderboard[0], {"rank": 1, "name": "Alice", "rating": 2100.0, "skill_tier": "Master"})
        self.assertEqual(leaderboard[1], {"rank": 2, "name": "Bob", "rating": 1350.0, "skill_tier": "Novice"})


if __name__ == "__main__":
    unittest.main()