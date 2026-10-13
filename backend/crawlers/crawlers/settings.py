# -*- coding: utf-8 -*-
import json
from urllib.parse import urljoin

BOT_NAME = "nepse_research"

SPIDER_MODULES = ["crawlers.spiders"]
NEWSPIDER_MODULE = "crawlers.spiders"

# be polite by default; per-portal tunables come from the app config copy
ROBOTSTXT_OBEY = True
USER_AGENT = "nepse-research-bot/0.1 (+contact: dev@example.com)"
DOWNLOAD_DELAY = 1.5
CONCURRENT_REQUESTS_PER_DOMAIN = 2
CONCURRENT_REQUESTS = 4
AUTOTHROTTLE_ENABLED = True
AUTOTHROTTLE_START_DELAY = 1.0
AUTOTHROTTLE_MAX_DELAY = 15.0
AUTOTHROTTLE_TARGET_CONCURRENCY = 1.0

COOKIES_ENABLED = False
TELNETCONSOLE_ENABLED = False
REDIRECT_ENABLED = True
HTTPERROR_ALLOWED_CODES = [404]

RETRY_TIMES = 2
RETRY_HTTP_CODES = [500, 502, 503, 504, 522, 524, 408, 429]

ITEM_PIPELINES = {
    # single pipeline: spiders drop items here; ingestion happens in the
    # celery task which owns the DB session. Keeps spiders stateless.
    "crawlers.pipelines.JsonLinesWriter": 300,
}

LOG_LEVEL = "INFO"

DUPEFILTER_DEBUG = False