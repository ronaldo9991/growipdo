# Python for the app, Node and a headless browser for the Remotion summary videos.
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 NODE_MAJOR=20 REMOTION_DISABLE_HEADLESS_SHELL_DOWNLOAD_WARNING=1

RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates curl gnupg \
 && curl -fsSL https://deb.nodesource.com/setup_${NODE_MAJOR}.x | bash - \
 && apt-get install -y --no-install-recommends nodejs \
    libnss3 libdbus-1-3 libatk1.0-0 libatk-bridge2.0-0 libcups2 libdrm2 libxkbcommon0 \
    libxcomposite1 libxdamage1 libxfixes3 libxrandr2 libgbm1 libasound2 libpango-1.0-0 \
    libcairo2 fonts-liberation fonts-dejavu-core \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY video/package.json video/package-lock.json* ./video/
RUN cd video && (npm ci --omit=dev || npm install --omit=dev)

COPY . .

# Fetch the headless browser during the build so the first video does not pay for it.
RUN cd video && (npx --yes remotion browser ensure || echo "browser will be fetched on first render")

CMD ["python", "start.py"]
