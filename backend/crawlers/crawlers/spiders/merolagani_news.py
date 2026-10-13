from .base import BaseNewsSpider


class MerolaganiNewsSpider(BaseNewsSpider):
    name = "merolagani_news"
    allowed_domains = ["merolagani.com"]
    start_urls = [
        "https://merolagani.com/NewsList.aspx",
        "https://merolagani.com/CompanyNews.aspx",
    ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.title_selector = "h1, .title::text"
        self.body_selector = ".news-content, .article-content, #ctl00_ContentPlaceHolder1 p::text"

    def link_filter(self, url):
        return "/NewsDetail" in url and "merolagani.com" in url