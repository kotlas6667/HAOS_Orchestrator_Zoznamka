# HAOS Elite Date Bot — samostatný add-on (jeden Chromium)
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
    tzdata \
    fonts-liberation \
    libgbm1 \
    libnss3 \
    libatk-bridge2.0-0 \
    libgtk-3-0 \
    libx11-6 \
    libxcb1 \
    libxcomposite1 \
    libxdamage1 \
    libxext6 \
    libxfixes3 \
    libxrandr2 \
    libcairo2 \
    libpango-1.0-0 \
    libasound2 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Package layout so ``python -m elitedate_bot.main`` works
RUN mkdir -p /app/elitedate_bot
COPY __init__.py browser.py chrome_lock.py config.py elitedate_client.py \
     main.py morning_greet.py poller.py server.py session.py shared_state.py \
     /app/elitedate_bot/
COPY run.sh addon_dns.py /app/

# Ranný cyklus o 07:00 = lokálny čas SK (kontajner inak často UTC).
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    TZ=Europe/Bratislava

RUN chmod +x /app/run.sh

EXPOSE 8600

ENTRYPOINT ["/app/run.sh"]
