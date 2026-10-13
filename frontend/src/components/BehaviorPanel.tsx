import { fmtPrice, fmtVolume } from "./format";

export default function BehaviorPanel({ summary }: { summary: any }) {
  if (!summary) return null;
  const np = summary.news_price_check || {};
  const pressure = summary.pressure as string;

  return (
    <div className="card behavior">
      <h3>Buyer / seller behaviour</h3>

      <div className="metrics">
        <div className="metric">
          <span className="muted small">VWAP (30d)</span>
          <b>{summary.vwap ? fmtPrice(summary.vwap) : "—"}</b>
        </div>
        <div className="metric">
          <span className="muted small">Last close</span>
          <b>{summary.last_close ? fmtPrice(summary.last_close) : "—"}</b>
        </div>
        <div className="metric">
          <span className="muted small">Pressure</span>
          <b className={"press " + pressure}>{pressure}</b>
          <span className="muted small">score {summary.pressure_score}</span>
        </div>
      </div>

      <h4>Volume anomalies</h4>
      {summary.volume_anomalies?.length ? (
        <table className="table">
          <thead>
            <tr>
              <th>Date</th>
              <th>Volume</th>
              <th>Median</th>
              <th>Robust z</th>
              <th>Direction</th>
            </tr>
          </thead>
          <tbody>
            {summary.volume_anomalies.map((a: any) => (
              <tr key={a.date}>
                <td>{a.date}</td>
                <td>{fmtVolume(a.volume)}</td>
                <td>{fmtVolume(a.median_volume)}</td>
                <td>{a.robust_z}</td>
                <td>{a.direction}</td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : (
        <p className="muted small">No volume spikes over the 3.5 robust-z threshold.</p>
      )}

      <h4>Top brokers (by net quantity)</h4>
      {summary.broker_breakdown?.length ? (
        <table className="table">
          <thead>
            <tr>
              <th>Broker</th>
              <th>Buy qty</th>
              <th>Sell qty</th>
              <th>Net</th>
            </tr>
          </thead>
          <tbody>
            {summary.broker_breakdown.map((b: any) => (
              <tr key={b.broker}>
                <td>{b.broker}</td>
                <td>{fmtVolume(b.buy_qty)}</td>
                <td>{fmtVolume(b.sell_qty)}</td>
                <td className={b.net_qty >= 0 ? "up" : "down"}>
                  {b.net_qty >= 0 ? "+" : ""}
                  {fmtVolume(Math.abs(b.net_qty))}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : (
        <p className="muted small">
          No floorsheet rows collected for this company. The floorsheet source needs a live
          crawl; run it from Admin or use the seeded sample.
        </p>
      )}

      <h4>News vs next-day movement</h4>
      <p className="muted small">
        {np.sample_size
          ? `Pearson r over ${np.sample_size} trading days — |return|: ${
              np.pearson_abs_return ?? "n/a"
            }, volume change: ${np.pearson_volume ?? "n/a"}.`
          : "Not enough price history yet."}
      </p>
    </div>
  );
}