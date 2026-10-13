import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../lib/api";
import { useLive } from "../lib/live";
import Sparkline from "../components/Sparkline";
import { fmtPct, fmtPrice } from "../components/format";

interface Card {
  id: number;
  symbol: string;
  name: string;
  sector: string;
  last: number | null;
  change: number;
  closes: number[];
}

export default function Dashboard() {
  const { revision } = useLive();
  const [cards, setCards] = useState<Card[]>([]);
  const [news, setNews] = useState<any[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        const companies = await api.companies();
        const built = await Promise.all(
          companies.map(async (c: any): Promise<Card> => {
            try {
              const prices = await api.prices(c.id, "30d");
              const closes = prices.map((p: any) => p.close);
              const last = closes.at(-1) ?? null;
              const prev = closes.at(-2) ?? last;
              return {
                ...c,
                last,
                change: last && prev ? (last - prev) / prev : 0,
                closes,
              };
            } catch {
              return { ...c, last: null, change: 0, closes: [] };
            }
          })
        );
        const latestNews = await api.news({});
        if (alive) {
          setCards(built);
          setNews(latestNews.slice(0, 6));
          setError(null);
        }
      } catch (e: any) {
        if (alive) setError(e.message);
      }
    })();
    return () => {
      alive = false;
    };
  }, [revision]);

  return (
    <div className="page">
      <div className="page-head">
        <h2>Watchlist</h2>
        <span className="muted">{cards.length} companies · last 30 days</span>
      </div>

      {error && <div className="error">{error}</div>}

      <div className="grid cards">
        {cards.map((c) => (
          <Link to={`/company/${c.id}`} className="card company-card" key={c.id}>
            <div className="row between">
              <div>
                <div className="symbol">{c.symbol}</div>
                <div className="muted small">{c.name}</div>
              </div>
              <span className={"badge " + (c.change >= 0 ? "up" : "down")}>
                {fmtPct(c.change)}
              </span>
            </div>
            <div className="row between end">
              <div className="price">{c.last ? fmtPrice(c.last) : "—"}</div>
              <Sparkline data={c.closes} up={c.change >= 0} />
            </div>
            <div className="muted small">{c.sector}</div>
          </Link>
        ))}
      </div>

      <div className="page-head">
        <h2>Latest news</h2>
        <span className="muted">tagged automatically by company</span>
      </div>
      <div className="card">
        {news.length === 0 && <p className="muted">No articles yet.</p>}
        {news.map((n) => (
          <div className="news-row" key={n.id}>
            <a href={n.url} target="_blank" rel="noreferrer">
              {n.title}
            </a>
            <span className="muted small">
              {n.source} · {new Date(n.published_at).toLocaleDateString()}
              {" · "}
              {n.tags.map((t: any) => t.company_id).length} tag(s)
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}