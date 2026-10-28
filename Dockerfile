# Pin the base digest as well as the Python series for reproducible rebuilds.
FROM python:3.12-slim-bookworm@sha256:e697c81897302a4c4333bade000d98038fbb21eb064f8ee1fd42d02ebcd9d337

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    STREAMLIT_BROWSER_GATHER_USAGE_STATS=false

# OpenCV/RapidOCR require these native shared libraries on Debian slim.
RUN apt-get update \
    && apt-get install --no-install-recommends -y libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --gid 10001 silverfile \
    && useradd --uid 10001 --gid silverfile --create-home silverfile

WORKDIR /app
COPY requirements-docker.txt ./
RUN python -m pip install --no-cache-dir --only-binary=:all: -r requirements-docker.txt \
    && python -m pip check

COPY . .
# Keep the existing application paths; both SQLite databases and their WAL
# journals resolve into the same named volume used by dashboard and CLI.
RUN mkdir /app/state \
    && chown silverfile:silverfile /app/state \
    && ln -s /app/state/intake_sessions.db /app/intake_sessions.db \
    && ln -s /app/state/workflow_sessions.db /app/workflow_sessions.db

USER silverfile
EXPOSE 8501
HEALTHCHECK --interval=10s --timeout=5s --start-period=20s --retries=5 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8501/_stcore/health', timeout=3).read()"]
CMD ["python", "-m", "streamlit", "run", "dashboard.py", "--server.address=0.0.0.0", "--server.port=8501", "--server.headless=true"]
