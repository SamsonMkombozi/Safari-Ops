FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1 \
    DJANGO_SETTINGS_MODULE=config.settings.production

RUN apt-get update && apt-get install -y --no-install-recommends curl tini && rm -rf /var/lib/apt/lists/* \
    && useradd --system --uid 1000 --create-home app

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY --chown=app:app . .
RUN mkdir -p logs media staticfiles && chown -R app:app logs media staticfiles \
    && chmod +x deploy/docker/entrypoint.sh

USER app
EXPOSE 8000
ENTRYPOINT ["/usr/bin/tini", "--", "deploy/docker/entrypoint.sh"]
CMD ["web"]
