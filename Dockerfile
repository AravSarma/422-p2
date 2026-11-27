# ---------- Stage 1: build the TypeScript React frontend ----------
# Node and all build tooling live only in this stage (NFR-02: nothing is
# installed on the host). Only the compiled static files are carried forward.
FROM node:20-alpine AS frontend-builder
WORKDIR /app/frontend

# Install exact versions from the lockfile first so Docker caches this layer
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund

COPY frontend/ ./
RUN npm run build


# ---------- Stage 2: Python standard-library runtime ----------
FROM python:3.11-slim AS runtime
WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    HOST=0.0.0.0 \
    PORT=8000 \
    DB_PATH=/app/data/chess_hub.db \
    STATIC_DIR=/app/backend/static

COPY backend/ ./backend/
COPY database/ ./database/
COPY standings/ ./standings/

# Compiled frontend is served by the Python backend as static files
COPY --from=frontend-builder /app/frontend/dist ./backend/static

# SQLite lives here; docker-compose bind-mounts ./data so it survives rebuilds
RUN mkdir -p /app/data
VOLUME ["/app/data"]

EXPOSE 8000

# Run as a module so `from database import ...` / `from standings import ...`
# resolve from /app (running `python backend/server.py` would put /app/backend
# on sys.path instead and break those imports).
CMD ["python", "-m", "backend.server"]
