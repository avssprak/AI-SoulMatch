# Single image for both long-running processes this app needs — the
# Streamlit UI and the webhook sidecar (webhook_server.py, V3-3). They run
# as two separate containers from this one image (see docker-compose.yml,
# which overrides CMD per service) rather than one container running both
# under a process supervisor — simpler to reason about, restart
# independently, and needs no extra supervisor dependency.
FROM python:3.12-slim

# Swiss Ephemeris (pyswisseph) and pypdf need no system packages beyond a
# C toolchain for the initial wheel build on some platforms; slim images
# lacking one will fail pip install, so build-essential is included and
# then removed to keep the final image small.
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
RUN mkdir -p data uploads

# Streamlit is the default process; docker-compose's "webhooks" service
# overrides this to `python webhook_server.py`.
EXPOSE 8501 8502
CMD ["streamlit", "run", "app.py", "--server.address=0.0.0.0", "--server.port=8501", \
     "--server.headless=true", "--browser.gatherUsageStats=false"]
