import { useEffect, useMemo, useState } from "react";
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
  monthChange: number;
  closes: number[];
}

export default function Dashboard() {
  const { revision, connected } = useLive();
  const [cards, setCards] = useState<Card[]>([]);
  const [news, setNews] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [updatedAt, setUpdatedAt] = useState<Date | null>(null);
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
              const closes: number[] = prices.map((p: any) => p.close);
              const last = closes.at(-1) ?? null;
              const prev = closes.at(-2) ?? last;
              const first = closes.at(0) ?? last;
              return {
                ...c,
                last,
                change: last && prev ? (last - prev) / prev : 0,
                monthChange: last && first ? (last - first) / first : 0,
                closes,
              };
            } catch {
              return { ...c, last: null, change: 0, monthChange: 0, closes: [] };
            }
          })
        );
        const latestNews = await api.news({});
        if (alive) {
          setCards(built);
          setNews(latestNews.slice(0, 6));
          setUpdatedAt(new Date());
          setError(null);
        }
      } catch (e: any) {
        if (alive) setError(e.message);
      } finally {
        if (alive) setLoading(false);
      }
    })();
    return () => {
      alive = false;
    };
  }, [revision]);

  const symbolById = useMemo(() => {
    const m: Record<number, string> = {};
    for (const c of cards) m[c.id] = c.symbol;
    return m;
  }, [cards]);

  const stats = useMemo(() => {
    const advancing = cards.filter((c) => c.change > 0).length;
    const declining = cards.filter((c) => c.change < 0).length;
    const ranked = [...cards].filter((c) => c.last != null).sort((a, b) => b.monthChange - a.monthChange);
    return {
      advancing,
      declining,
      best: ranked.at(0),
      worst: ranked.at(-1),
    };
  }, [cards]);

  return (
    <div className="page">
      <div className="page-head">
        <div>
          <h2>Watchlist</h2>
          <span className="muted">
            {cards.length} companies · last 30 days
            {updatedAt && <> · updated {updatedAt.toLocaleTimeString()}</>}
            {connected && <> · <span className="up">live</span></>}
          </span>
        </div>
      </div>

      {error && <div className="error">{error}</div>}

      <div className="stat-strip">
        <div className="stat">
          <span className="muted small">Tracked</span>
          <b>{cards.length}</b>
        </div>
        <div className="stat">
          <span className="muted small">Advancing</span>
          <b className="up">{stats.advancing}</b>
        </div>
        <div className="stat">
          <span className="muted small">Declining</span>
          <b className="down">{stats.declining}</b>
        </div>
        <div className="stat">
          <span className="muted small">Top 30d gain</span>
          <b className="up">
            {stats.best ? `${stats.best.symbol} ${fmtPct(stats.best.monthChange)}` : "—"}
          </b>
        </div>
        <div className="stat">
          <span className="muted small">Top 30d drop</span>
          <b className="down">
            {stats.worst && stats.worst !== stats.best
              ? `${stats.worst.symbol} ${fmtPct(stats.worst.monthChange)}`
              : "—"}
          </b>
        </div>
      </div>

      {loading && cards.length === 0 ? (
        <div className="grid cards">
          {Array.from({ length: 6 }).map((_, i) => (
            <div className="card company-card skeleton" key={i} aria-hidden="true">
              <div className="sk-line w40" />
              <div className="sk-line w70" />
              <div className="sk-line w55 tall" />
            </div>
          ))}
        </div>
      ) : (
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
                <Sparkline data={c.closes} up={c.monthChange >= 0} />
              </div>
              <div className="row between">
                <span className="muted small">{c.sector}</span>
                <span className={"small " + (c.monthChange >= 0 ? "up" : "down")}>
                  30d {fmtPct(c.monthChange)}
                </span>
              </div>
            </Link>
          ))}
          {!loading && cards.length === 0 && (
            <p className="muted">No companies tracked yet. Add one from the Admin screen.</p>
          )}
        </div>
      )}

      <div className="page-head">
        <h2>Latest news</h2>
        <span className="muted">tagged automatically by company</span>
      </div>
      <div className="card">
        {newsHint(news.length, loading)}
        {news.map((n) => {
          const tags: any[] = n.tags || [];
          const symbols = tags
            .map((t: any) => symbolById[t.company_id])
            .filter(Boolean)
            .slice(0, 4);
          return (
            <div className="news-row" key={n.id}>
              <a href={n.url} target="_blank" rel="noreferrer">
                {n.title}
              </a>
              <div className="row tags">
                {symbols.map((s) => (
                  <span className="tag" key={s}>
                    {s}
                  </span>
                ))}
                {tags.length === 0 && <span className="tag untagged">untagged</span>}
                <span className="muted small">
                  {n.source} · {new Date(n.published_at).toLocaleDateString()}
                </span>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function newsHint(count: number, loading: boolean) {
  if (count === 0) return <p className="muted">{loading ? "Loading…" : "No articles yet."}</p>;
  return null;
}
