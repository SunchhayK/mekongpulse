# Telegram bot poller (dev/staging). In production the bot runs inside the
# backend service via the webhook route instead.
# Build from the projects/ root:  docker build -f bot/Dockerfile .
FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

ENV PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

WORKDIR /app

COPY pyproject.toml uv.lock .python-version ./
COPY shared/pyproject.toml shared/
COPY backend/pyproject.toml backend/
COPY bot/pyproject.toml bot/
RUN uv sync --frozen --no-dev --no-install-workspace --package mekong-bot

COPY shared/src/ shared/src/
COPY bot/src/ bot/src/
COPY data/ data/
RUN uv sync --frozen --no-dev --package mekong-bot

ENV PATH="/app/.venv/bin:$PATH" \
    DATA_DIR=/app/data \
    AUDIO_DIR=/app/data/audio

CMD ["python", "-m", "mekong_bot.main"]
