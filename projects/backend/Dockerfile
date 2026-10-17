# FastAPI backend (MekongPulse) - uv workspace aware.
# Build from the projects/ root:  docker build -f backend/Dockerfile .
FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

ENV PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

WORKDIR /app

# Workspace manifests first so dependency layers cache well.
COPY pyproject.toml uv.lock .python-version ./
COPY shared/pyproject.toml shared/
COPY backend/pyproject.toml backend/
COPY bot/pyproject.toml bot/
RUN uv sync --frozen --no-dev --no-install-workspace --package mekong-backend \
    && rm -rf /root/.cache/uv

# Sources + bundled data (station roster, commune gazetteer).
COPY shared/src/ shared/src/
COPY backend/src/ backend/src/
COPY bot/src/ bot/src/
COPY data/ data/
RUN uv sync --frozen --no-dev --package mekong-backend \
    && rm -rf /root/.cache/uv

ENV PATH="/app/.venv/bin:$PATH" \
    DATA_DIR=/app/data \
    AUDIO_DIR=/app/data/audio

EXPOSE 8080
CMD ["uvicorn", "mekong_backend.main:app", "--host", "0.0.0.0", "--port", "8080"]
