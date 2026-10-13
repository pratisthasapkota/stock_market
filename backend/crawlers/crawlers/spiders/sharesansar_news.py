from .base import BaseNewsSpider


class SharesansarNewsSpider(BaseNewsSpider):
    name = "sharesansar_news"
    allowed_domains = ["sharesansar.com"]
    start_urls = ["https://www.sharesansar.com/category/news"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.title_selector = "h1, .title::text"
        self.body_selector = ".single-news-content, .news-detail, #main-content p::text"

    def link_filter(self, url):
        return "/category/news/" not in url and "sharesansar.com" in url