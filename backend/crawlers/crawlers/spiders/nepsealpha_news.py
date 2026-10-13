from .base import BaseNewsSpider


class NepsealphaNewsSpider(BaseNewsSpider):
    name = "nepsealpha_news"
    allowed_domains = ["nepsealpha.com"]
    start_urls = ["https://nepsealpha.com/news"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.title_selector = "h1::text"
        self.body_selector = ".article-body p::text, .article-content p::text"

    def link_filter(self, url):
        return "/news/" in url or "/news-detail" in url