import { useEffect, useMemo, useState } from "react";
import { useParams } from "react-router-dom";
import { api } from "../lib/api";
import { useLive } from "../lib/live";
import PriceChart from "../components/PriceChart";
import BehaviorPanel from "../components/BehaviorPanel";
import NewsFeed from "../components/NewsFeed";
import { fmtPct, fmtPrice, fmtVolume } from "../components/format";

export default function CompanyDetail() {
  const { id } = useParams();
  const companyId = Number(id);
  const { revision } = useLive();

  const [range, setRange] = useState("30d");
  const [company, setCompany] = useState<any>(null);
  const [prices, setPrices] = useState<any[]>([]);
  const [behavior, setBehavior] = useState<any>(null);
  const [articles, setArticles] = useState<any[]>([]);
  const [companies, setCompanies] = useState<any[]>([]);
  const [error, setError] = useState<string | null>(null);

  async function load() {
    try {
      const [cos, px, b, news] = await Promise.all([
        api.companies(),
        api.prices(companyId, range),
        api.behavior(companyId),
        api.news({ company_id: companyId }),
      ]);
      setCompanies(cos);
      setCompany(cos.find((c: any) => c.id === companyId) ?? null);
      setPrices(px);
      setBehavior(b);
      setArticles(news);
      setError(null);
    } catch (e: any) {
      setError(e.message);
    }
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [companyId, range, revision]);

  const chartRows = useMemo(() => {
    let pv = 0;
    let vol = 0;
    return prices.map((p) => {
      const typical = (p.high + p.low + p.close) / 3;
      pv += typical * p.volume;
      vol += p.volume;
      return {
        date: p.date,
        close: p.close,
        volume: p.volume,
        vwap: vol ? +(pv / vol).toFixed(2) : null,
      };
    });
  }, [prices]);

  const last = prices.at(-1);
  const prev = prices.at(-2);
  const change = last && prev ? (last.close - prev.close) / prev.close : 0;

  async function correct(articleId: number, companyId: number, action: "add" | "remove") {
    await api.recategorize(articleId, companyId, action);
    await load();
  }

  if (error) return <div className="error">{error}</div>;
  if (!company) return <p className="muted">Loading…</p>;

  return (
    <div className="page">
      <div className="page-head">
        <div>
          <h2>
            {company.symbol} <span className="muted h-sub">{company.name}</span>
          </h2>
          <span className="muted">
            {company.sector} · {last ? fmtPrice(last.close) : "—"}{" "}
            <span className={change >= 0 ? "up" : "down"}>{fmtPct(change)}</span>
            {last && <> · vol {fmtVolume(last.volume)}</>}
          </span>
        </div>
        <div className="range-picker">
          {["7d", "30d", "90d"].map((r) => (
            <button
              key={r}
              className={"chip" + (range === r ? " active" : "")}
              onClick={() => setRange(r)}
            >
              {r}
            </button>
          ))}
        </div>
      </div>

      <div className="card">
        <PriceChart rows={chartRows} />
      </div>

      <div className="two-col">
        <div>
          <div className="page-head">
            <h3>News ({articles.length})</h3>
          </div>
          <div className="card scroll">
            <NewsFeed
              articles={articles}
              companies={companies}
              currentCompanyId={companyId}
              onCorrect={correct}
            />
          </div>
        </div>
        <BehaviorPanel summary={behavior} />
      </div>
    </div>
  );
}