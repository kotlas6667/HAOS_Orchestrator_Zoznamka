# HAOS Orchestrator Add-on Dockerfile
# Builds a containerized version of the AI Orchestrator for Home Assistant OS

FROM python:3.11-slim AS builder

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Create and activate virtual environment
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Install Python dependencies (main app + elitedate_bot + tinder_bot)
COPY requirements.txt /tmp/
COPY elitedate_bot/requirements.txt /tmp/elitedate_requirements.txt
COPY tinder_bot/requirements.txt /tmp/tinder_requirements.txt
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r /tmp/requirements.txt -r /tmp/elitedate_requirements.txt -r /tmp/tinder_requirements.txt

# ---------------------------------------------------------------------------
# Final stage
# ---------------------------------------------------------------------------
FROM python:3.11-slim

# Copy virtual environment from builder
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Runtime dependencies for SSL/certificates, plus Chromium + driver shared by
# the elitedate_bot and tinder_bot Selenium sessions (not available on armv7;
# that arch falls back gracefully only if both bots are left disabled via .env).
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    openssl \
    curl \
    chromium \
    chromium-driver \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy application code and configuration
COPY app/ /app/app/
COPY elitedate_bot/ /app/elitedate_bot/
COPY tinder_bot/ /app/tinder_bot/
COPY data/orchestrator/config/tinder/chrome-profile/ /app/data/orchestrator/config/tinder/chrome-profile/
COPY *.json /app/
COPY *.pickle /app/
COPY *.txt /app/
COPY run.sh /app/

# Bundle the .env into the image.
# .env is copied explicitly because it is not matched by the *.json/*.txt globs.
COPY .env /app/.env

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

RUN chmod +x /app/run.sh

EXPOSE 8000

# Runs as root so it can write to the /data add-on volume.
ENTRYPOINT ["/app/run.sh"]
