# syntax=docker/dockerfile:1

FROM python:3.12-slim

ARG APP_VERSION=pilot-001
ARG VCS_REF=unknown
ARG BUILD_DATE=unknown

LABEL org.opencontainers.image.title="RONRO / 論路" \
      org.opencontainers.image.version="$APP_VERSION" \
      org.opencontainers.image.revision="$VCS_REF" \
      org.opencontainers.image.created="$BUILD_DATE"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

WORKDIR /app

COPY requirements-dev.txt ./requirements-dev.txt
RUN pip install --no-cache-dir --disable-pip-version-check -r requirements-dev.txt \
    && useradd --create-home --uid 10001 --shell /usr/sbin/nologin appuser \
    && mkdir -p /data/evaluation/live/sessions /data/evaluation/live/reports /tmp \
    && chown -R appuser:appuser /data /tmp

COPY prototype ./prototype
COPY schemas ./schemas
COPY evaluation/fixtures ./evaluation/fixtures

# The developer UI expects the excluded real-analyzer dataset directory to
# exist at startup. Keep the dataset out of the public image while preserving
# a valid empty runtime directory for the live application.
RUN mkdir -p /app/evaluation/real-analyzer

RUN chown -R appuser:appuser /app

USER 10001:10001

EXPOSE 8000 8765

ENTRYPOINT ["python", "-m", "prototype.server", "--host", "0.0.0.0", "--port", "8000", "--live-ws-port", "8765"]
