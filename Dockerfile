FROM python:3.12-slim

LABEL maintainer="you@example.com" \
      description="Newznab-compliant indexer proxying a searchable RSS feed"

WORKDIR /app

# System deps for healthcheck (curl) kept minimal
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt gunicorn

COPY app.py config.py ./
COPY templates ./templates
COPY static ./static

# Unraid/self-hosted convention: a persistent volume for config overrides.
# Mount your own config.py here to override settings without rebuilding.
VOLUME ["/config"]
ENV CONFIG_DIR=/config

ENV PYTHONUNBUFFERED=1 \
    PORT=5000

EXPOSE 5000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -fsS http://localhost:5000/health || exit 1

# 2 workers is plenty for an indexer proxy; raise if you expect heavy concurrent load
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "2", "--timeout", "30", "app:app"]
