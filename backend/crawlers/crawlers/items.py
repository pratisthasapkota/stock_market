import scrapy


class NewsItem(scrapy.Item):
    title = scrapy.Field()
    excerpt = scrapy.Field()
    body = scrapy.Field()
    source = scrapy.Field()
    url = scrapy.Field()
    published_at = scrapy.Field()


class PriceItem(scrapy.Item):
    kind = scrapy.Field()
    company_id = scrapy.Field()
    symbol = scrapy.Field()
    rows = scrapy.Field()


class FloorSheetItem(scrapy.Item):
    kind = scrapy.Field()
    company_id = scrapy.Field()
    symbol = scrapy.Field()
    rows = scrapy.Field()