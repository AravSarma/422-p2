"""
Centralized data persistence layer for Emerald City Chess Hub.
Handles SQLite database connections, schema initialization, and parameterized queries.

Strict Boundary:
    Only files within the `database/` module are permitted to import `sqlite3`. 
    All other modules must interact with data exclusively through this manager.
"""