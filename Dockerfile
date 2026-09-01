FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS base
WORKDIR /app

ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy PYTHONUNBUFFERED=1

FROM base AS build
COPY pyproject.toml ./
RUN uv sync --no-dev --frozen 2>/dev/null || uv sync --no-dev

FROM base AS runtime
COPY --from=build /app/.venv /app/.venv
COPY app ./app
COPY migrations ./migrations
COPY oxyde_config.py ./

RUN mkdir -p /app/data

EXPOSE 8000
CMD ["/app/.venv/bin/uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]