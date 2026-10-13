from datetime import datetime, timezone

import scrapy


def parse_nepali_date(text):
    """Cover the date shapes these portals actually use. Returns None when
    nothing reliable is found so the caller can fall back to crawl time."""
    if not text:
        return None
    t = " ".join(text.strip().split())
    for fmt in (
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%m/%d/%Y",
        "%B %d, %Y",
        "%b %d, %Y",
        "%d %B %Y",
    ):
        try:
            return datetime.strptime(t, fmt)
        except ValueError:
            try:
                # some portals prefix e.g. "Posted on "
                return datetime.strptime(t.split("on ")[-1].strip(), fmt)
            except (ValueError, IndexError):
                continue
    return None


class BaseNewsSpider(scrapy.Spider):
    """Shared behaviour for the four news portals: crawl listing pages, follow
    detail links, stop after a page budget so a runaway pagination loop can
    never burn the whole day's quota."""

    page_budget = 25
    max_items = 80

    # subclasses fill these
    link_selector = 'a::attr(href)'
    link_filter = lambda self, url: True  # noqa: E731
    title_selector = "h1::text"
    body_selector = ".entry-content, .post-content, .news-content, #content p::text"

    def __init__(self, out_file=None, run_id=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not out_file:
            raise ValueError("spider requires out_file argument")
        self.out_file = out_file
        self.run_id = int(run_id or 0)
        self._pages = 0
        self._items = 0
        self._seen_urls = set()

    def parse(self, response):
        if self._pages >= self.page_budget or self._items >= self.max_items:
            return
        self._pages += 1
        for href in response.css(self.link_selector).getall():
            url = response.urljoin(href)
            if not self.link_filter(url) or url in self._seen_urls:
                continue
            if self._items >= self.max_items:
                return
            self._seen_urls.add(url)
            self._items += 1
            yield scrapy.Request(url, callback=self.parse_article)

        # next page, if any
        next_url = response.css("a:contains('Next'), .next a::attr(href), .pagination .active + a::attr(href)").get()
        if next_url and self._pages < self.page_budget:
            yield scrapy.Request(response.urljoin(next_url), callback=self.parse)

    def parse_article(self, response):
        title = self._first_text(response, self.title_selector) or response.css("title::text").get()
        body = self._join_text(response, self.body_selector) or ""
        date_text = (
            response.css("time::attr(datetime)").get()
            or response.css(".date, .meta, .published, time::text").get()
        )
        published = parse_nepali_date(date_text) or datetime.now(timezone.utc).replace(tzinfo=None)
        if not title or not body:
            return
        yield {
            "title": title,
            "excerpt": body[:260],
            "body": body,
            "source": self.name,
            "url": response.url,
            "published_at": published,
        }

    def _first_text(self, response, selector):
        val = " ".join(x.strip() for x in response.css(selector).getall() if x.strip())
        return val or None

    def _join_text(self, response, selector):
        parts = [x.strip() for x in response.css(selector).getall() if x.strip()]
        return "\n".join(parts)