from .base import BaseNewsSpider


class BizmanduNewsSpider(BaseNewsSpider):
    name = "bizmandu_news"
    allowed_domains = ["bizmandu.com"]
    start_urls = [
        "https://www.bizmandu.com/stock",
        "https://www.bizmandu.com/category/business",
    ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.title_selector = "h1::text"
        self.body_selector = ".entry-content p::text, #content p::text"

    def link_filter(self, url):
        return "/details/" in url or "/news/" in url