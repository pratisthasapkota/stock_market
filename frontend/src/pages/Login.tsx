import { FormEvent, useState } from "react";
import { useAuth } from "../lib/auth";

const DEMO = [
  ["admin", "admin123", "full access + crawl control"],
  ["analyst", "analyst123", "can fix news categories"],
  ["viewer", "viewer123", "read only"],
];

export default function Login() {
  const { signIn } = useAuth();
  const [username, setUsername] = useState("admin");
  const [password, setPassword] = useState("admin123");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await signIn(username.trim(), password);
    } catch (err: any) {
      setError(err.message || "could not sign in");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="login-wrap">
      <form className="card login-card" onSubmit={submit}>
        <h1>NEPSE Research</h1>
        <p className="muted">
          News, trading data and buyer/seller behaviour for a small watchlist.
        </p>

        <label>
          Username
          <input value={username} onChange={(e) => setUsername(e.target.value)} autoFocus />
        </label>
        <label>
          Password
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
        </label>

        {error && <div className="error">{error}</div>}

        <button className="primary" disabled={busy} type="submit">
          {busy ? "Signing in…" : "Sign in"}
        </button>

        <div className="demo-hint">
          <div className="muted">Demo accounts</div>
          {DEMO.map(([u, p, note]) => (
            <button
              type="button"
              key={u}
              className="demo-row"
              onClick={() => {
                setUsername(u);
                setPassword(p);
              }}
            >
              <b>{u}</b>
              <span className="muted">{p}</span>
              <span className="muted">{note}</span>
            </button>
          ))}
        </div>
      </form>
    </div>
  );
}