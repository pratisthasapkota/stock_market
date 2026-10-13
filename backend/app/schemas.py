from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: str
    username: str


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    email: str
    username: str
    role: str
    is_active: bool


class UserCreate(BaseModel):
    email: str
    username: str
    password: str = Field(min_length=6)
    role: str = "viewer"


class CompanyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    symbol: str
    name: str
    sector: str
    is_active: bool


class CompanyCreate(BaseModel):
    symbol: str
    name: str
    sector: str = ""
    aliases: str = ""


class PriceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    date: date
    open: float
    high: float
    low: float
    close: float
    volume: float


class TagOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    company_id: int
    confidence: float
    method: str
    corrected: bool


class ArticleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    title: str
    excerpt: str
    source: str
    url: str
    published_at: datetime
    tags: list[TagOut] = []


class RecategorizeIn(BaseModel):
    company_id: int
    action: str = "add"  # add | remove


class BrokerStat(BaseModel):
    broker: str
    buy_qty: float
    sell_qty: float
    net_qty: float


class BehaviorSummary(BaseModel):
    company_id: int
    symbol: str
    window_days: int
    vwap: float | None
    last_close: float | None
    pressure: str  # buy | sell | neutral
    pressure_score: float
    volume_anomalies: list[dict]
    broker_breakdown: list[BrokerStat]
    news_price_check: dict
    generated_at: datetime


class CrawlRunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    portal: str
    status: str
    started_at: datetime | None
    finished_at: datetime | None
    items_found: int
    items_new: int
    error: str


class ComparisonOut(BaseModel):
    most_volatile: list[dict]
    most_active: list[dict]
    most_in_news: list[dict]
