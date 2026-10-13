FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

# curl is used by the api service healthcheck
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /srv

# dependency layer first so code edits don't bust the pip cache
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# run as a non-root user that owns the app dir. Workers write scrapy temp
# files and celery beat writes its schedule file under here.
RUN useradd --create-home --uid 10001 app \
    && chown -R app:app /srv
USER app

EXPOSE 8000

# uvicorn starts from /srv so `app` and `crawlers` resolve on the path
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
