import { useEffect, useState } from "react";
import { api } from "../lib/api";
import { useLive } from "../lib/live";
import { Role } from "../lib/api";

const PORTALS = ["all", "merolagani", "sharesansar", "nepsealpha", "bizmandu", "market"];

export default function Admin() {
  const { revision } = useLive();
  const [runs, setRuns] = useState<any[]>([]);
  const [users, setUsers] = useState<any[]>([]);
  const [companies, setCompanies] = useState<any[]>([]);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [newCo, setNewCo] = useState({ symbol: "", name: "", sector: "", aliases: "" });

  async function load() {
    try {
      const [r, u, c] = await Promise.all([api.crawlRuns(), api.users(), api.companies()]);
      setRuns(r);
      setUsers(u);
      setCompanies(c);
      setError(null);
    } catch (e: any) {
      setError(e.message);
    }
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [revision]);

  async function trigger(portal: string) {
    setBusy(portal);
    try {
      await api.triggerCrawl(portal);
      await load();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy(null);
    }
  }

  async function retry(id: number) {
    await api.retryRun(id);
    await load();
  }

  async function retag() {
    setBusy("retag");
    try {
      await api.retag();
      await load();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy(null);
    }
  }

  async function addCompany() {
    if (!newCo.symbol || !newCo.name) return;
    try {
      await api.addCompany(newCo);
      setNewCo({ symbol: "", name: "", sector: "", aliases: "" });
      await load();
    } catch (e: any) {
      setError(e.message);
    }
  }

  return (
    <div className="page">
      <div className="page-head">
        <h2>Admin</h2>
        <span className="muted">crawl control · watchlist · users</span>
      </div>

      {error && <div className="error">{error}</div>}

      <div className="card">
        <h3>Trigger a crawl</h3>
        <div className="row wrap">
          {PORTALS.map((p) => (
            <button
              key={p}
              className="chip"
              disabled={busy === p}
              onClick={() => trigger(p)}
            >
              {busy === p ? "starting…" : p}
            </button>
          ))}
          <button className="chip" disabled={busy === "retag"} onClick={retag}>
            {busy === "retag" ? "retagging…" : "re-tag all articles"}
          </button>
        </div>
        <p className="muted small">
          "all" queues the four news portals. Runs without redis execute inline in a worker
          thread so this screen still works locally.
        </p>
      </div>

      <div className="card">
        <h3>Crawl runs</h3>
        <table className="table">
          <thead>
            <tr>
              <th>#</th>
              <th>Portal</th>
              <th>Status</th>
              <th>Started</th>
              <th>Found</th>
              <th>New</th>
              <th>Error</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {runs.map((r) => (
              <tr key={r.id}>
                <td>{r.id}</td>
                <td>{r.portal}</td>
                <td>
                  <span className={"status " + r.status}>{r.status}</span>
                </td>
                <td className="small muted">
                  {r.started_at ? new Date(r.started_at).toLocaleString() : "—"}
                </td>
                <td>{r.items_found}</td>
                <td>{r.items_new}</td>
                <td className="small err-cell" title={r.error}>
                  {r.error ? r.error.slice(0, 60) : ""}
                </td>
                <td>
                  <button className="ghost small" onClick={() => retry(r.id)}>
                    retry
                  </button>
                </td>
              </tr>
            ))}
            {runs.length === 0 && (
              <tr>
                <td colSpan={8} className="muted">
                  no runs yet
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      <div className="two-col">
        <div className="card">
          <h3>Watchlist (add a company)</h3>
          <p className="muted small">
            Adding a company is a config change: it re-runs tagging so old articles pick it up.
          </p>
          <div className="form-grid">
            <input
              placeholder="symbol (e.g. SCB)"
              value={newCo.symbol}
              onChange={(e) => setNewCo({ ...newCo, symbol: e.target.value.toUpperCase() })}
            />
            <input
              placeholder="full name"
              value={newCo.name}
              onChange={(e) => setNewCo({ ...newCo, name: e.target.value })}
            />
            <input
              placeholder="sector"
              value={newCo.sector}
              onChange={(e) => setNewCo({ ...newCo, sector: e.target.value })}
            />
            <input
              placeholder="aliases, comma separated"
              value={newCo.aliases}
              onChange={(e) => setNewCo({ ...newCo, aliases: e.target.value })}
            />
            <button className="primary" onClick={addCompany}>
              Add / update
            </button>
          </div>
          <div className="row wrap">
            {companies.map((c) => (
              <span className="tag" key={c.id}>
                {c.symbol}
              </span>
            ))}
          </div>
        </div>

        <div className="card">
          <h3>Users</h3>
          <table className="table">
            <thead>
              <tr>
                <th>User</th>
                <th>Email</th>
                <th>Role</th>
              </tr>
            </thead>
            <tbody>
              {users.map((u) => (
                <tr key={u.id}>
                  <td>{u.username}</td>
                  <td className="muted small">{u.email}</td>
                  <td>
                    <select
                      value={u.role}
                      onChange={async (e) => {
                        await api.setRole(u.id, e.target.value as Role);
                        await load();
                      }}
                    >
                      <option value="viewer">viewer</option>
                      <option value="analyst">analyst</option>
                      <option value="admin">admin</option>
                    </select>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}