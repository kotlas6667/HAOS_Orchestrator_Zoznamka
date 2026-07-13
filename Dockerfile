# HAOS Orchestrator Add-on Dockerfile
# Lightweight image — bez Chromium. Elite Date a Tinder majú vlastné add-ony.

FROM python:3.11-slim AS builder

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY requirements.txt /tmp/
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r /tmp/requirements.txt

# ---------------------------------------------------------------------------
# Final stage
# ---------------------------------------------------------------------------
FROM python:3.11-slim

COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    openssl \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY app/ /app/app/
COPY requirements.txt config.json run.sh /app/

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

RUN chmod +x /app/run.sh && \
    printf '%s\n' '{"queue": []}' > /app/elitedate_state.json && \
    printf '%s\n' '{"queue": []}' > /app/tinder_state.json && \
    printf '%s\n' \
      '# Prefer persistent /data/orchestrator/config/.env at runtime.' \
      'APP_NAME=HAOS Orchestrator' \
      > /app/.env

EXPOSE 8000

ENTRYPOINT ["/app/run.sh"]
