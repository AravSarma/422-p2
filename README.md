# 422-p2

## Project File Structure

The **Emerald City Chess Hub** project follows a strictly modular, Dockerized architecture with strict separation of concerns (e.g., SQLite isolation, modular UI components). 
Below is the complete directory layout and module breakdown:

## Directory Layout

```text
ec-chesshub/
├── backend/             # HTTP server, authentication, and payload validation
├── database/            # SQLite schema and encapsulated data persistence layer
├── standings/           # Elo rating calculation engine (K=32) and sorting logic
├── frontend/            # React, TypeScript, and Tailwind CSS client interface
├── tests/               # Unit and integration test suite
├── data/                # Persistent SQLite database storage (mounted volume)
├── Dockerfile           # Multi-stage container build configuration
├── docker-compose.yml   # Service orchestration for local and production deployment
└── README.md            # Project documentation and setup guide
```


## Module Breakdown

| Module | Key Files | Responsibility & Boundaries |
| :--- | :--- | :--- |
| **`backend/`** | `server.py` | HTTP request routing, payload validation, and officer auth. No direct `sqlite3` imports. |
| **`database/`** | `schema.sql`, `db_manager.py` | **Exclusive owner of `sqlite3`**. Handles schema setup, parameterized queries, and PII purging. |
| **`standings/`** | `elo_service.py` | Computes $K=32$ Elo rating updates and sorts player standings. |
| **`frontend/`** | `src/components/`, `src/services/` | React + TypeScript + Tailwind UI and typed `ApiClient` wrapper. |
| **`tests/`** | `test_database.py`, `test_elo.py`, `test_api.py` | Unit and API integration tests using Python's `unittest`. |
| **`data/`** | `.gitkeep` *(runtime: `*.db`)* | Mounted volume for persistent SQLite storage; database files ignored in Git. |
