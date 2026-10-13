import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../lib/api";
import { can, useAuth } from "../lib/auth";
import { useLive } from "../lib/live";

interface Row {
  company_id: number;
  symbol: string;
  value: number;
  label: string;
}

function Column({ title, rows, unit }: { title: string; rows: Row[]; unit: string }) {
  const max = rows.reduce((m, r) => Math.max(m, r.value), 0);
  return (
    <div className="card">
      <h3>{title}</h3>
      <table className="table">
        <tbody>
          {rows.map((r, i) => (
            <tr key={r.company_id}>
              <td className="rank">{i + 1}</td>
              <td>
                <Link to={`/company/${r.company_id}`}>{r.symbol}</Link>
              </td>
              <td className="bar-cell">
                <span
                  className={"hbar" + (i === 0 ? " lead" : "")}
                  style={{ width: max ? `${Math.max(6, (r.value / max) * 100)}%` : "6%" }}
                />
              </td>
              <td className="right muted small">{r.label}</td>
            </tr>
          ))}
          {rows.length === 0 && (
            <tr>
              <td className="muted">no data yet</td>
            </tr>
          )}
        </tbody>
      </table>
      <span className="muted small">{unit}</span>
    </div>
  );
}

export default function Comparison() {
  const { revision, connected } = useLive();
  const { role } = useAuth();
  const [data, setData] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    api
      .comparison()
      .then((d) => {
        if (alive) {
          setData(d);
          setError(null);
        }
      })
      .catch((e) => {
        if (alive) setError(e.message);
      });
    return () => {
      alive = false;
    };
  }, [revision]);

  if (error) return <div className="error">{error}</div>;
  if (!data) return <p className="muted">Loading…</p>;

  return (
    <div className="page">
      <div className="page-head">
        <div>
          <h2>Cross-company comparison</h2>
          <span className="muted">
            last 30 days{connected && <> · <span className="up">live</span></>}
          </span>
        </div>
        <div className="row">
          {can(role, "analyst") && (
            <button
              className="chip"
              onClick={() =>
                api.downloadReport("/api/reports/comparison.csv", "comparison.csv")
              }
            >
              export CSV
            </button>
          )}
        </div>
      </div>
      <div className="three-col">
        <Column title="Most volatile" rows={data.most_volatile} unit="avg daily close move" />
        <Column title="Most active" rows={data.most_active} unit="traded volume" />
        <Column title="Most in the news" rows={data.most_in_news} unit="tagged articles" />
      </div>
    </div>
  );
}
