import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../lib/api";
import { useLive } from "../lib/live";

function Column({ title, rows, unit }: { title: string; rows: any[]; unit: string }) {
  return (
    <div className="card">
      <h3>{title}</h3>
      <table className="table">
        <tbody>
          {rows.map((r) => (
            <tr key={r.company_id}>
              <td>
                <Link to={`/company/${r.company_id}`}>{r.symbol}</Link>
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
  const { revision } = useLive();
  const [data, setData] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .comparison()
      .then(setData)
      .catch((e) => setError(e.message));
  }, [revision]);

  if (error) return <div className="error">{error}</div>;
  if (!data) return <p className="muted">Loading…</p>;

  return (
    <div className="page">
      <div className="page-head">
        <h2>Cross-company comparison</h2>
        <span className="muted">last 30 days</span>
      </div>
      <div className="three-col">
        <Column title="Most volatile" rows={data.most_volatile} unit="avg daily close move" />
        <Column title="Most active" rows={data.most_active} unit="traded volume" />
        <Column title="Most in the news" rows={data.most_in_news} unit="tagged articles" />
      </div>
    </div>
  );
}