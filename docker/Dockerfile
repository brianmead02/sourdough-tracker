# syntax=docker/dockerfile:1
FROM python:3.12-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /srv/app

# Dependency layer: only busted when pyproject changes.
COPY pyproject.toml README.md ./
COPY app/__init__.py ./app/__init__.py
RUN pip install --no-cache-dir -e ".[dev]"

COPY alembic.ini ./
COPY migrations ./migrations
COPY app ./app

RUN useradd --create-home --uid 10001 sourdough \
    && chown -R sourdough:sourdough /srv/app
USER sourdough

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
