# Build TypeScript React Frontend
FROM node:20-alpine AS frontend-builder
WORKDIR /app/frontend

# Install dependencies and build static assets
COPY frontend/package*.json ./
RUN npm install
COPY frontend/ ./
RUN npm run build

# Python Runtime
FROM python:3.11-slim AS runtime
WORKDIR /app

# Python environment setup
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Copy backend application code, database module, and standings module
COPY backend/ ./backend/
COPY database/ ./database/
COPY standings/ ./standings/

# Copy compiled frontend build artifacts into the backend's static directory
COPY --from=frontend-builder /app/frontend/dist ./backend/static

# Expose the standard HTTP server port
EXPOSE 8000

# Run the Python standard library HTTP server entrypoint
CMD ["python", "backend/server.py"]