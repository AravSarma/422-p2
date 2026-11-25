"""
Elo rating calculation engine for Emerald City Chess Hub. 
Computes win/loss expectancy math using K=32 and handles dynamic 
leaderboard sorting.

Strict Boundary:
    Pure business logic module. It must not import `sqlite3` or handle 
    raw HTTP requests, operating purely on data passed to its functions.
"""