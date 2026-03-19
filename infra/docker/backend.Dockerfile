# Backend Dockerfile — containerises the FastAPI application
# Note 1: A Dockerfile is a script of instructions for building a Docker image.
# An image is a lightweight, portable snapshot of the application and all its
# dependencies. Running the image creates a container (an isolated process).
#
# Note 2: Typical multi-stage Dockerfile for a Python FastAPI backend:
#
# --- Stage 1: build dependencies ---
# FROM python:3.12-slim AS builder
# WORKDIR /app
# COPY requirements.txt .
# RUN pip install --no-cache-dir -r requirements.txt
#
# --- Stage 2: production image ---
# FROM python:3.12-slim
# WORKDIR /app
# COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
# COPY backend/ ./backend/
# COPY config/ ./config/
# EXPOSE 8000
# CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
#
# Note 3: '--host 0.0.0.0' makes the server listen on ALL network interfaces
# inside the container. Without this, the server binds to localhost only,
# which is not reachable from outside the container (e.g. by Nginx proxy).
#
# Note 4: EXPOSE 8000 documents the port the container listens on. It does NOT
# actually publish the port — docker run -p 8000:8000 does the actual publishing.
#
# TODO: Add FastAPI application containerization steps
