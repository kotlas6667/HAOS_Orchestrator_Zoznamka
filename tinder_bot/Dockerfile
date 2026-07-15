# HAOS Tinder Bot — samostatný add-on (jeden Chromium)
FROM python:3.11-slim AS builder

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r /tmp/requirements.txt

FROM python:3.11-slim

COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    curl \
    chromium \
    chromium-driver \
    xvfb \
    x11vnc \
    novnc \
    websockify \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

RUN mkdir -p /app/tinder_bot
COPY __init__.py browser.py chrome_lock.py config.py tinder_client.py \
     main.py poller.py server.py session.py shared_state.py \
     /app/tinder_bot/
COPY run.sh addon_dns.py /app/

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

RUN chmod +x /app/run.sh

EXPOSE 8601 6080

ENTRYPOINT ["/app/run.sh"]
